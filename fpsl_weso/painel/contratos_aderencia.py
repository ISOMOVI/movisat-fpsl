"""A WESO desempata, placa por placa (frente `D`). 2026-10-14.

As duas regras são dele, e são **opostas de propósito**:

  1. *"placas sem assinatura mas placa ativa, placa vence, pois se existe na
     weso foi feita, o erro é não ter assinatura"* — a placa **em uso** nunca
     perde o contrato. O que falta é assinatura, e isso é **achado**.
  2. *"pode ser que N placas foram rescindidas mas nao assinadas, se tiverem
     fora da Weso, é recisão mesmo"* — a placa que já **saiu** fecha, mesmo sem
     documento assinado.

🚨 A SEGUNDA NÃO PODE MORDER A PRIMEIRA. Nenhuma placa que está na WESO fecha
por este módulo, em nenhum caminho. É a asserção que a suíte cobra.

🚨 PRECEDÊNCIA: O TERMO DEFINE O QUE EXISTE (regra dele). A WESO não cria
contrato -- ela desempata o que o documento deixou ambíguo. Por isso este módulo
só fecha placa que **já tem uma rescisão na linha do tempo**: ele confirma um
documento que existe, nunca inventa um.

⚠️ O MOTOR CONTINUA SEM I/O. A consulta ao cache mora aqui; o motor só vê o
evento com `fonte="weso"` e a data do cache no `obs`. Deixar o motor olhar a
WESO faria a situação da placa mudar sem evento nenhum -- e ninguém saberia
explicar por quê.

🚨 E RECUSA CACHE VELHO, pela mesma trava da rotina C6 (`IDADE_MAXIMA_H = 48`):
fechar placa por ausência, com dado de três dias, é pior que não decidir.

Medido em 14/10, antes de rodar: das **2.986** placas sustentadas, **1.642**
estão na WESO (1.641 com rastreador) e **1.344** fora -- dessas, **549** têm
rescisão na linha do tempo e **795** não têm (são "contratada e não instalada").
"""
import json
import logging

from . import contratos_eventos as motor
from . import contratos_registro as registro
from . import contratos_tabelas

log = logging.getLogger("fpsl.contratos_aderencia")

# Os três destinos de uma placa sustentada.
EM_USO = "em uso"
FECHA = "fora da WESO, com rescisao na linha do tempo"
SEM_RESCISAO = "fora da WESO, sem rescisao: nada a fechar"

# A margem que ele definiu para a coorte aderente.
MARGEM_ADERENCIA = 1


def chaves_do_cache() -> tuple:
    """Só **presença**: `({chave}, idade_em_horas)`. Para a tela, não para a rotina.

    🚨 A ROTINA C6 LÊ CARO DE PROPÓSITO: ela faz uma consulta de rastreador por
    veículo, porque precisa saber a *situação* de cada um. O grid não precisa --
    ele responde "esta placa existe na WESO?" --, e pagar o preço da rotina a
    cada abertura de tela seria caro por nada.

    ⚠️ Devolve a idade junto, porque a tela tem de poder dizer **de quando** é o
    número. Comparação com dado velho sem avisar é tela que mente.
    """
    import sqlite3
    from datetime import datetime, timezone

    from ..services.contratos_auditoria import CACHE_WESO
    if not CACHE_WESO.exists():
        return set(), None
    conn = sqlite3.connect(f"file:{CACHE_WESO}?mode=ro", uri=True)
    try:
        idade = None
        v = conn.execute("SELECT valor FROM meta WHERE chave='atualizado_em'").fetchone()
        if v:
            quando = datetime.fromisoformat(v[0])
            if quando.tzinfo is None:
                quando = quando.replace(tzinfo=timezone.utc)
            idade = (datetime.now(timezone.utc) - quando).total_seconds() / 3600
        chaves = set()
        for placa, chave, chassi in conn.execute(
                "SELECT placa, chave_placa, chassi FROM veiculos"):
            # 🚨 Placa E chassi: são duas formas de achar o mesmo veículo, e
            # ignorar o chassi faria placa de máquina (que só tem chassi)
            # aparecer como "fora da WESO".
            for k in {motor.chave(chave or placa), motor.chave(chassi or "")} - {""}:
                chaves.add(k)
        return chaves, idade
    finally:
        conn.close()


def _weso():
    """O cache da WESO, pela MESMA função da rotina C6.

    ⚠️ Importado aqui dentro, e não no topo: `services.contratos_auditoria`
    importa `painel`, e o caminho inverso no topo fecharia o ciclo de import.
    """
    from ..services.contratos_auditoria import _weso_do_cache, IDADE_MAXIMA_H
    placas, idade, n = _weso_do_cache()
    return placas, idade, n, IDADE_MAXIMA_H


def _rescisao_e_a_ultima_palavra(conn, cnpj: str, chave: str, rescisao: dict) -> bool:
    """A rescisão é o ÚLTIMO evento desta placa, ou um termo posterior a trouxe de volta?

    🚨 MEDIDO EM 14/10: 5 das 32 primeiras confirmações eram placas reativadas
    por um termo **posterior** à rescisão (a `SWL1I23`, pelo termo 8708). Ali
    "fora da WESO" não quer dizer que saiu -- quer dizer que **ainda não foi
    instalada**. Confirmar a saída dessas é dar por encerrado um contrato que o
    próprio cliente reabriu.

    ⚠️ A ordem é o NÚMERO do termo, nunca a data: a data do Harmonit vem
    `01-01-2000` quando não existe, e há contrato datado depois da própria
    rescisão (é a regra que o motor já segue).
    """
    def _n(v):
        try:
            return (0, int(v))
        except (TypeError, ValueError):
            return (1, 0)

    desta = _n(rescisao["termo"])
    for numero, in conn.execute(
            """SELECT t.numero FROM contrato_evento e JOIN contrato_termo t ON t.id = e.termo_id
                WHERE t.cnpj = ? AND e.placa_chave = ? AND e.acao IN (?, ?)""",
            (cnpj, chave, motor.ENTRA, motor.UPGRADE)):
        if _n(numero) > desta:
            return False
    return True


def classificar(conn, weso: dict, cnpj: str | None = None) -> list:
    """Uma linha por placa sustentada, com o destino e a razão. **Não grava.**"""
    sql = """SELECT p.cnpj, p.placa_chave, p.placa_texto, p.situacao, p.base, p.termo_vigente
               FROM contrato_placa p
              WHERE p.situacao IN (?, ?)"""
    args = [motor.ATIVA, motor.EM_AVISO_PREVIO]
    if cnpj:
        sql += " AND p.cnpj = ?"
        args.append(cnpj)

    # As rescisões que já existem na linha do tempo, por (cliente, placa) --
    # 🚨 inclusive as NÃO assinadas, que são justamente o caso da regra 2.
    rescisoes: dict = {}
    for c, k, eid, numero, assinado in conn.execute(
            """SELECT t.cnpj, e.placa_chave, e.id, t.numero, t.assinado
                 FROM contrato_evento e JOIN contrato_termo t ON t.id = e.termo_id
                WHERE e.acao = ? AND e.fonte <> ?
                ORDER BY e.id""", (motor.RESCINDE, motor.WESO)):
        rescisoes.setdefault((c, k), []).append(
            {"evento_id": eid, "termo": numero, "assinado": bool(assinado)})

    # O que este módulo já confirmou antes: não se confirma duas vezes.
    ja = {(c, k) for c, k in conn.execute(
        """SELECT t.cnpj, e.placa_chave FROM contrato_evento e
             JOIN contrato_termo t ON t.id = e.termo_id
            WHERE e.fonte = ?""", (motor.WESO,))}

    saida = []
    for c, k, texto, situacao, base, termo_vigente in conn.execute(sql, tuple(args)):
        na_weso = k in weso
        linha = {"cnpj": c, "chave": k, "placa": texto, "situacao": situacao, "base": base,
                 "termo_vigente": termo_vigente, "na_weso": na_weso,
                 "rastreador": weso.get(k)}
        if na_weso:
            # 🚨 REGRA 1: a placa vence. Nada a fazer no contrato -- o que falta
            # é assinatura, e isso é achado, não demissão de placa.
            linha["destino"] = EM_USO
            linha["falta_assinar"] = (base == "nao assinado")
        elif (c, k) in ja:
            linha["destino"] = FECHA
            linha["ja_confirmada"] = True
        elif situacao == motor.EM_AVISO_PREVIO:
            # ⚠️ MEDIDO EM 14/10: 12 das 32 primeiras confirmações caíram aqui e
            # não mudaram nada. Aviso prévio quer dizer que **uma rescisão já
            # está valendo** e o prazo corre pelo calendário, sozinho --
            # confirmar pelo uso só acrescentaria evento inerte ao histórico.
            linha["destino"] = SEM_RESCISAO
            linha["motivo"] = "a rescisão já está valendo: o aviso prévio vence pelo calendário"
        elif rescisoes.get((c, k)) and _rescisao_e_a_ultima_palavra(conn, c, k, rescisoes[(c, k)][-1]):
            # 🚨 REGRA 2: fora da WESO e com rescisão na linha do tempo -- mesmo
            # não assinada -- é rescisão mesmo. Confirma-se a ÚLTIMA rescisão
            # registrada, porque é ela que descreve a saída atual.
            r = rescisoes[(c, k)][-1]
            linha["destino"] = FECHA
            linha["confirma_evento"] = r["evento_id"]
            linha["confirma_termo"] = r["termo"]
            linha["rescisao_assinada"] = r["assinado"]
        else:
            # Sem rescisão não há documento para confirmar, e este módulo não
            # inventa um: a placa fica como está.
            linha["destino"] = SEM_RESCISAO
        saida.append(linha)
    return saida


def aderencia_por_cliente(linhas: list) -> dict:
    """`{cnpj: {sustentadas, em_uso, fora, diferenca, coorte}}`.

    A coorte é a dele: **±1** é "100% de aderência".
    ⚠️ Esta conta é "contrato sem uso". Ela não acusa a placa que está na WESO
    sem contrato -- isso é outro achado da C6 (320 casos), e segue por lá.
    """
    por: dict = {}
    for linha in linhas:
        d = por.setdefault(linha["cnpj"], {"sustentadas": 0, "em_uso": 0, "fora": 0})
        d["sustentadas"] += 1
        d["em_uso" if linha["na_weso"] else "fora"] += 1
    for cnpj, d in por.items():
        d["diferenca"] = d["sustentadas"] - d["em_uso"]
        d["coorte"] = ("aderente" if abs(d["diferenca"]) <= MARGEM_ADERENCIA
                       else "contrato maior que o uso")
    return por


def confirmar_saida_pelo_uso(conn, linha: dict, quando_cache: str, por: str) -> dict:
    """Insere o `RESCINDE` com `fonte="weso"` que confirma a rescisão existente.

    🚨 NADA DE `UPDATE`: o evento de rescisão não assinado **continua lá**,
    apontado por este. A ficha mostra os dois, e é assim que se explica por que
    a placa fechou sem documento assinado.
    """
    cur = conn.execute(
        """INSERT INTO contrato_evento
           (termo_id, placa_chave, placa_texto, acao, fonte, obs, corrige_evento_id, criado_em)
           SELECT e.termo_id, e.placa_chave, e.placa_texto, ?, ?, ?, e.id, ?
             FROM contrato_evento e WHERE e.id = ?""",
        (motor.RESCINDE, motor.WESO,
         f"D: fora da WESO no cache de {quando_cache} — rescisão do termo "
         f"{linha.get('confirma_termo')} confirmada pelo uso (por {por})",
         registro._agora(), linha["confirma_evento"]))
    return {"evento_id": cur.lastrowid, "placa": linha["placa"],
            "confirmou": linha["confirma_evento"]}


def rodar(cnpj: str | None = None, coorte: str | None = None, por: str = "d-aderencia",
          dry_run: bool = True, limite_clientes: int | None = None) -> dict:
    """Classifica e, valendo, confirma as saídas. Uma transação por cliente.

    ⚠️ Transação por cliente, e não uma só: o banco está em
    `journal_mode=delete` e cada escrita tranca o serviço.
    """
    weso, idade, n_veiculos, teto = _weso()
    if not weso:
        return {"rodou": False, "motivo": "o cache da WESO não está disponível"}
    if idade is not None and idade > teto:
        return {"rodou": False,
                "motivo": f"o cache da WESO está com {idade:.0f} h (teto {teto} h) — "
                          "fechar placa por ausência com dado velho é pior que não decidir"}

    with registro._connect() as conn:
        conn.execute("PRAGMA busy_timeout = 10000")
        contratos_tabelas.criar(conn)
        contratos_tabelas.migrar(conn)
        linhas = classificar(conn, weso, cnpj)
        por_cliente = aderencia_por_cliente(linhas)
        quando = conn.execute(
            "SELECT MAX(calculado_em) FROM contrato_placa").fetchone()[0] or ""

    alvos = {c for c, d in por_cliente.items() if not coorte or d["coorte"] == coorte}
    if limite_clientes:
        alvos = set(sorted(alvos)[:limite_clientes])

    resumo = {"rodou": True, "dry_run": dry_run, "veiculos_weso": n_veiculos,
              "idade_cache_h": round(idade, 1) if idade is not None else None,
              "placas": len(linhas), "clientes": len(por_cliente),
              "clientes_alvo": len(alvos), "por_destino": {}, "coortes": {},
              "em_uso_sem_assinatura": sum(1 for x in linhas if x.get("falta_assinar")),
              "confirmadas": [], "quando_cache": quando[:10]}
    for linha in linhas:
        resumo["por_destino"][linha["destino"]] = resumo["por_destino"].get(linha["destino"], 0) + 1
    for d in por_cliente.values():
        resumo["coortes"][d["coorte"]] = resumo["coortes"].get(d["coorte"], 0) + 1

    a_fechar = [x for x in linhas
                if x["destino"] == FECHA and x["cnpj"] in alvos and not x.get("ja_confirmada")]
    resumo["a_fechar"] = len(a_fechar)
    if dry_run:
        resumo["exemplos"] = a_fechar[:10]
        return resumo

    data_cache = (resumo["quando_cache"] or "sem data")
    for c in sorted({x["cnpj"] for x in a_fechar}):
        with registro._connect() as conn:
            conn.execute("PRAGMA busy_timeout = 10000")
            try:
                for linha in [x for x in a_fechar if x["cnpj"] == c]:
                    resumo["confirmadas"].append(
                        confirmar_saida_pelo_uso(conn, linha, data_cache, por))
                registro.recalcular(conn, c)
                conn.commit()
            except Exception as e:                               # pragma: no cover
                conn.rollback()
                log.exception("falha confirmando saidas de %s", c)
                resumo.setdefault("erros", []).append({"cnpj": c, "erro": str(e)})
    return resumo


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    p = argparse.ArgumentParser(description="A WESO desempata, placa por placa (D)")
    p.add_argument("--cnpj", default=None)
    p.add_argument("--coorte", default=None, choices=["aderente", "contrato maior que o uso"])
    p.add_argument("--clientes", type=int, default=None, help="limita quantos clientes entram")
    p.add_argument("--por", default="d-aderencia")
    p.add_argument("--valendo", action="store_true", help="sem isto, é ensaio")
    a = p.parse_args()
    r = rodar(a.cnpj, a.coorte, a.por, dry_run=not a.valendo, limite_clientes=a.clientes)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
