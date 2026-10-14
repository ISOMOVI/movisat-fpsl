"""Gravação da Gestão de Contratos (`CTR_1.1`) — etapa C3. 2026-10-13.

Grava termo, eventos e itens; recalcula a situação derivada; monta a ficha do
cliente. **Não escreve no Harmonit, na WESO nem na Clicksign** -- em nenhuma
fase da aba, por decisão de escopo (doc 31).

🚨 NÚCLEO SÍNCRONO, SUPERFÍCIE ASSÍNCRONA. As funções que recebem `conn` são o
núcleo e rodam em banco de memória num teste, sem asyncio e sem o arquivo real.
As `async` são as que o router chama, no padrão do `storage.py`
(`run_in_executor` em volta de um `_run`). Foi o que permitiu travar as regras
antes de existir tela.

🚨 EVENTO NÃO SE ATUALIZA, SE ACRESCENTA. Nenhum `UPDATE` em
`contrato_evento`: corrigir é lançar outro evento. É o oposto do que o Harmonit
faz hoje -- editar o PDF do termo depois de assinado e anotar a troca em texto
livre -- e é o que faz a pergunta "por que esta placa está ativa?" ter resposta.

🚨 `contrato_placa` É CACHE, NUNCA FONTE. Ela existe para a tela não recalcular
731 clientes a cada abertura. Em caso de divergência o evento ganha, e
`recalcular` a refaz do zero. Nenhuma regra decide lendo ela.
"""
import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .. import storage
from . import contratos_eventos as motor
from . import contratos_tabelas

def pasta_pdf() -> Path:
    """Onde o PDF assinado é guardado. **Resolvida na hora, nunca no import.**

    ⚠️ Era uma constante de módulo e isso tornava o caminho impossível de
    desviar: o teste do router gravaria na pasta de dados de verdade, porque o
    valor fica congelado na importação. Mesma família do erro de ler
    configuração uma vez e nunca mais.
    """
    return Path(storage.DB_PATH).parent / "contratos"


class TermoJaGravado(Exception):
    """Mesmo PDF subindo duas vezes.

    🚨 É O QUE IMPEDE O EVENTO DOBRADO. Clicar duas vezes em "confirmar" já
    duplicou card no Painel Financeiro; aqui o `hash` do arquivo é UNIQUE e a
    segunda tentativa vira erro com o id do primeiro, não um segundo termo.
    """

    def __init__(self, termo_id, numero):
        self.termo_id, self.numero = termo_id, numero
        super().__init__(f"Este PDF já foi gravado no termo {numero} (id {termo_id}).")


def _connect():
    conn = sqlite3.connect(storage.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _agora():
    return datetime.now(timezone.utc).isoformat()


def hash_pdf(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


# ── núcleo (recebe conn; testável em memória) ────────────────────────────────

def gravar(conn, cnpj: str, lido: dict, *, assinado: bool, assinado_em: str | None,
           origem: str, enviado_por: str, hash_arquivo: str | None = None,
           arquivo: str | None = None, saida_confirmada: list | None = None,
           eventos_do_harmonit: list | None = None, troca_registrada: str | None = None,
           revisar_motivo: str | None = None) -> int:
    """Grava o termo e seus eventos. Devolve o `termo_id`.

    `saida_confirmada` são as placas que o OPERADOR disse que saem numa troca.
    🚨 ELAS SÓ EXISTEM PORQUE A ANOTAÇÃO NÃO DIZ QUEM SAI. A anotação da Maxi
    Confort 8872 nomeia só a placa que entra (`FAC 5H30`), e no PDF do Harmonit
    as duas ficam na tabela, no mesmo item -- não há dado que aponte a antiga.
    Em vez de adivinhar (regra 13: **não se inventa identificador**), a saída
    vem confirmada por gente e fica gravada como evento, com a autoria.
    """
    if hash_arquivo:
        ja = conn.execute("SELECT id, numero FROM contrato_termo WHERE hash = ?", (hash_arquivo,)).fetchone()
        if ja:
            raise TermoJaGravado(ja[0], ja[1])

    agora = _agora()
    cur = conn.execute(
        """INSERT INTO contrato_termo
           (cnpj, numero, empresa, tipo, assinado, assinado_em, troca_registrada, a_definir,
            origem, arquivo, hash, revisar, revisar_motivo, enviado_por, enviado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cnpj, str(lido.get("numero") or ""), lido.get("empresa") or "MOVISAT", lido.get("perfil"),
         1 if assinado else 0, assinado_em, troca_registrada, 1 if lido.get("a_definir") else 0,
         origem, arquivo, hash_arquivo, 1 if revisar_motivo else 0, revisar_motivo,
         enviado_por, agora))
    termo_id = cur.lastrowid

    confirmadas = {motor.chave(p) for p in (saida_confirmada or [])}
    eventos = list(lido.get("eventos") or [])

    # ⚠️ Os eventos lidos no PDF do Harmonit entram marcados `fonte=harmonit`.
    # Quem decide se eles valem como assinados é o MOTOR, pela regra da troca /
    # do "a definir" -- não este gravador. Gravar já "resolvido" perderia a
    # razão, e é a razão que a ficha mostra.
    for e in (eventos_do_harmonit or []):
        eventos.append(dict(e, fonte=motor.HARMONIT))

    for p in (saida_confirmada or []):
        eventos.append({"acao": motor.SAI, "placa": p, "fonte": motor.HARMONIT,
                        "obs": f"saída confirmada por {enviado_por} (troca registrada no Harmonit)"})

    for e in eventos:
        placa = (e.get("placa") or "").strip()
        if not placa:
            continue
        rec = e.get("recursos")
        conn.execute(
            """INSERT INTO contrato_evento
               (termo_id, placa_chave, placa_texto, acao, fonte, recursos, valor_mensal, obs, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (termo_id, motor.chave(placa), placa, e["acao"], e.get("fonte") or motor.ASSINADO,
             json.dumps(rec, ensure_ascii=False) if isinstance(rec, (dict, list)) else rec,
             e.get("valor_mensal"), e.get("obs"), agora))

        if e["acao"] == motor.ENTRA and motor.chave(placa) not in confirmadas:
            conn.execute(
                """INSERT INTO contrato_item
                   (cnpj, placa_chave, placa_texto, recursos, valor_mensal, inicio, termo_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (cnpj, motor.chave(placa), placa,
                 json.dumps(rec, ensure_ascii=False) if isinstance(rec, (dict, list)) else rec,
                 e.get("valor_mensal"), assinado_em, termo_id))
    return termo_id


def termos_do_cliente(conn, cnpj: str) -> list:
    """Os termos do cliente no formato que o motor entende."""
    linhas = conn.execute(
        """SELECT id, numero, empresa, tipo, assinado, assinado_em, troca_registrada, a_definir,
                  origem, arquivo, revisar, revisar_motivo
             FROM contrato_termo WHERE cnpj = ?""", (cnpj,)).fetchall()
    por_id = {}
    for (tid, numero, empresa, tipo, assinado, assinado_em, troca, adef,
         origem, arquivo, revisar, revisar_motivo) in linhas:
        por_id[tid] = {
            "id": tid, "numero": numero, "empresa": empresa, "tipo": tipo,
            "assinado": bool(assinado), "assinado_em": assinado_em,
            "troca_registrada": troca, "a_definir": bool(adef), "origem": origem,
            "arquivo": arquivo, "revisar": bool(revisar), "revisar_motivo": revisar_motivo,
            "eventos": [],
        }
    if not por_id:
        return []
    marcas = ",".join("?" * len(por_id))
    for tid, placa_texto, acao, fonte, recursos, valor, obs in conn.execute(
            f"""SELECT termo_id, placa_texto, acao, fonte, recursos, valor_mensal, obs
                  FROM contrato_evento WHERE termo_id IN ({marcas}) ORDER BY id""",
            tuple(por_id)):
        por_id[tid]["eventos"].append({"acao": acao, "placa": placa_texto, "fonte": fonte,
                                       "recursos": recursos, "valor_mensal": valor, "obs": obs})
    return list(por_id.values())


def recalcular(conn, cnpj: str, hoje=None) -> dict:
    """Refaz `contrato_placa` do cliente a partir dos eventos. Idempotente."""
    situacoes = motor.situacao_das_placas(termos_do_cliente(conn, cnpj), hoje)
    agora = _agora()
    conn.execute("DELETE FROM contrato_placa WHERE cnpj = ?", (cnpj,))
    for k, v in situacoes.items():
        conn.execute(
            """INSERT INTO contrato_placa
               (cnpj, placa_chave, placa_texto, situacao, base, termo_vigente, desde, aviso_ate, obs, calculado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (cnpj, k, v.get("placa") or k, v["situacao"], v.get("base"),
             str(v.get("termo_vigente") or ""), v.get("desde"), v.get("aviso_ate"), v.get("obs"), agora))
    return situacoes


def ficha(conn, cnpj: str, hoje=None) -> dict:
    """Ficha do cliente: placas (situação derivada) e linha do tempo dos termos.

    ⚠️ CALCULA NA HORA e grava o cache no mesmo passo. Ler `contrato_placa`
    sem recalcular devolveria aviso prévio vencido como se ainda valesse -- o
    prazo passa sozinho, sem nenhum evento novo para disparar a conta.
    """
    termos = termos_do_cliente(conn, cnpj)
    situacoes = recalcular(conn, cnpj, hoje)

    def _ordem(t):
        try:
            return (0, int(t["numero"]), "")
        except (TypeError, ValueError):
            return (1, 0, str(t["numero"] or ""))

    placas = [dict(v, chave=k) for k, v in situacoes.items()]
    placas.sort(key=lambda p: (p["situacao"] != motor.ATIVA, p.get("placa") or ""))
    return {
        "cnpj": cnpj,
        "placas": placas,
        "sustentadas": motor.ativas(situacoes),
        "termos": [{k: v for k, v in sorted(t.items()) if k != "eventos"} | {"eventos": t["eventos"]}
                   for t in sorted(termos, key=_ordem)],
        "sem_assinatura": [t["numero"] for t in termos if not t["assinado"]],
        "a_revisar": [{"numero": t["numero"], "motivo": t["revisar_motivo"]} for t in termos if t["revisar"]],
    }


# ── superfície assíncrona (o que o router chama) ─────────────────────────────

async def _exec(fn, *a, **kw):
    def _run():
        with _connect() as conn:
            contratos_tabelas.criar(conn)
            r = fn(conn, *a, **kw)
            conn.commit()
            return r
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def gravar_termo(cnpj: str, lido: dict, **kw) -> dict:
    conteudo = kw.pop("conteudo", None)
    nome = kw.pop("nome_arquivo", None)
    h = hash_pdf(conteudo) if conteudo else None
    destino = None
    if conteudo:
        # Guarda o PDF que foi assinado. O nome usa o hash: arquivo de mesmo
        # nome vindo de cliente diferente não se sobrescreve.
        pasta = pasta_pdf()
        pasta.mkdir(parents=True, exist_ok=True)
        destino = f"{cnpj}_{str(lido.get('numero') or 'sem-numero')}_{h[:12]}.pdf"
        (pasta / destino).write_bytes(conteudo)

    def _grava(conn):
        tid = gravar(conn, cnpj, lido, hash_arquivo=h, arquivo=destino or nome, **kw)
        recalcular(conn, cnpj)
        return tid

    termo_id = await _exec(_grava)
    return {"termo_id": termo_id, "arquivo": destino, "hash": h}


async def ficha_do_cliente(cnpj: str) -> dict:
    return await _exec(ficha, cnpj)
