"""Router das Contas a Receber (`CAR_1.1`) — etapa E7. 2026-10-28.

Prefixo: /painel/api/car
Spec: `docs/fpsl/32_Contas_a_Receber.md`. Controle da frente:
`C:\\Users\\Lenovo\\Desktop\\CAR_1.1_Financeiro_FPSL.md`.

🚨 PERMISSÃO PRÓPRIA, `contas_receber`, por decisão dele em 28/10 — e não a
`financeiro` que já existe. O motivo é medido, não estético: esta aba cancela
cobrança e lança preço em **335 placas num clique**, e quem hoje tem
`financeiro` confere OS e fecha pagamento de técnico. Reusar a aba daria esse
poder de carona, sem ninguém decidir. Conceder a nova é ato dele, no modal de
perfil, e é essa a vantagem.

🚨 ESTE MÓDULO NÃO TEM REGRA DENTRO. Toda régua mora em `car_motor` (puro),
`car_prefatura` (leitura) e `car_registro` (escrita). Aqui só entram: validação
de entrada, a transação e o autor. Régua repetida na rota seria a segunda
verdade que a tela mostraria quando o cache estivesse quente.

🚨 `por` SAI DO TOKEN, NUNCA DO CORPO. Dinheiro sem autor é dinheiro sem
responsável, e autor que o cliente da tela manda é autor que o cliente da tela
escolhe. É a mesma régua do `enviado_por` da CTR.

⚠️ `_exec` CRIA AS TABELAS DA CAR, como o `_exec` da CTR faz com as dela. Não é
zelo: um banco que nasceu por outro caminho (teste, cópia restaurada) não tem
as três tabelas, e a rota responderia `no such table: car_evento` em vez de
trabalhar. É `CREATE IF NOT EXISTS` + `PRAGMA`, idempotente.
"""
import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ... import rotinas, storage
from ...services import sync_faturado
from ..auth import requer_aba
from .. import car_busca as busca
from .. import car_faturado as cf
from .. import car_lote as lote
from .. import car_motor as motor
from .. import car_prefatura as prefatura
from .. import car_registro as registro
from .. import car_tabelas as tabelas
from .. import car_variavel as cvar

log = logging.getLogger("fpsl.car_router")

router = APIRouter(
    prefix="/painel/api/car",
    tags=["contas_receber"],
    dependencies=[Depends(requer_aba("contas_receber"))],
)


# ── Infraestrutura: conexão, transação e o executor ──────────────────────────
def _connect():
    conn = sqlite3.connect(storage.DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


async def _exec(fn, *a, **kw):
    """Roda `fn(conn, ...)` fora do laço de eventos, com as tabelas garantidas.

    ⚠️ COMMIT NO FIM, SEMPRE O DO CHAMADOR. Os módulos da CAR não commitam de
    propósito (é o que deixa o teste controlar a transação dele), então quem
    abre é quem fecha. Exceção levanta antes do commit e o SQLite descarta --
    lote que morre no meio não deixa metade lançada.
    """
    def _run():
        with _connect() as conn:
            tabelas.criar(conn)
            tabelas.migrar(conn)
            r = fn(conn, *a, **kw)
            conn.commit()
            return r
    return await asyncio.get_running_loop().run_in_executor(None, _run)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _competencia(c: str | None) -> str:
    """A competência pedida, ou o mês de hoje. Inválida levanta 400.

    ⚠️ O DEFAULT É O MÊS DE HOJE, e isso é decisão: pré-fatura sem mês seria
    pré-fatura de mês nenhum. O mês passado se pede, e ele reproduz o mês
    passado -- não o hoje (travado em `teste_car_prefatura`).
    """
    if not c:
        return motor.competencia_de(date.today())
    try:
        return motor.validar_competencia(c)
    except motor.CompetenciaInvalida as e:
        raise HTTPException(400, str(e))


def _autor(usuario: dict) -> str:
    """Quem está lançando. Nunca vazio -- é o que o registro exige."""
    return (usuario or {}).get("login") or "?"


def _texto_obrigatorio(corpo: dict, campo: str) -> str:
    v = (corpo or {}).get(campo)
    v = str(v).strip() if v is not None else ""
    if not v:
        raise HTTPException(400, f"{campo} é obrigatório")
    return v


def _recusa(e: Exception):
    """Entrada recusada pelo registro vira 400 COM A FRASE DELE.

    🚨 A mensagem do `car_registro` é escrita para quem senta na tela ("preço
    lançado à mão exige motivo"). Trocá-la por "dados inválidos" apagaria a
    única coisa útil da resposta.
    """
    return HTTPException(400, str(e))


def _resolver_cnpj(conn, bruto: str) -> str:
    """O documento digitado vira o CNPJ **como esta base o guarda**.

    🚨 NÃO FILTRA DÍGITO, e isso é o conserto do X1 aplicado desde o nascimento:
    `WQ0P6GLD000108` passado por um `isdigit()` vira `000108`, e `000108` é
    chave de sete tabelas. A comparação é pela forma normalizada
    (`car_busca._limpo`, que preserva letra), e o que volta é a grafia da base
    -- usar a digitada num `WHERE cnpj = ?` não acharia o cliente guardado com
    pontuação.
    """
    if not busca.parece_documento(bruto):
        raise HTTPException(400, "CNPJ/CPF inválido: esperado 11 ou 14 posições "
                                 "(o formato alfanumérico é aceito).")
    limpo = busca._limpo(bruto)
    for c, in conn.execute("SELECT cnpj FROM contrato_cliente"):
        if busca._limpo(c) == limpo:
            return c
    raise HTTPException(404, f"o documento {limpo} não está nesta base")


def _weso() -> tuple:
    """O cache diário da WESO: `({chave: situação}, idade em horas)`.

    🚨 REUSA O LEITOR QUE JÁ EXISTE, `services.contratos_auditoria._weso_do_cache`
    -- o mesmo que a `CTR_1.1` usa desde 13/10. ⚠️ E ele continua com o nome
    privado de propósito: `teste_contratos_auditoria` troca a função **pelo
    nome** em 9 lugares, e um apelido público não seguiria a troca. Quem já o
    importava assim é o `contratos_aderencia` -- não sou o primeiro.

    Cache ausente volta `({}, None)`, e a pré-fatura trata mapa vazio como
    "nenhuma placa em uso", que é o que o cache de fato diz. Falha de leitura
    levanta, e a rota responde o erro -- comparação com dado que não deu para
    ler seria pior.
    """
    from ...services.contratos_auditoria import _weso_do_cache
    placas, idade, _n = _weso_do_cache()
    return placas, idade


def _montar_com_weso(conn, competencia: str, cnpj: str | None = None) -> dict:
    """A pré-fatura com a régua da WESO já injetada. Um lugar só."""
    placas, idade = _weso()
    return prefatura.montar(conn, competencia, cnpj=cnpj,
                            weso=placas, idade_weso=idade)


def _cnpj_do_termo(conn, termo_id: int) -> str:
    linha = conn.execute("SELECT cnpj FROM contrato_termo WHERE id = ?",
                         (termo_id,)).fetchone()
    if linha is None:
        raise HTTPException(404, f"o termo {termo_id} não existe nesta base")
    return linha[0]


# ─────────────────────────────────────────────────────────────────────────────
# Leitura: o grid, a ficha e o contrato
# ─────────────────────────────────────────────────────────────────────────────
def _cache_velho(conn, competencia: str) -> str | None:
    """Por que `car_contrato` precisa ser refeita, ou `None` quando está em dia.

    Duas causas, e as duas aconteceram no molde da CTR (`contratos_grid:148`):
      1. **vazia com evento na base** -- banco restaurado, ou termos gravados
         por um caminho que não recalculou. Devolver "em dia" mostraria 0
         contratos com 4.599 termos do lado: tela que mente.
      2. **calculada em outro dia, ou em outra competência** -- o status muda
         sozinho pelo calendário (aviso prévio vence sem nenhum evento novo), e
         a competência pedida pode simplesmente não ser a do cache.
    """
    linha = conn.execute(
        "SELECT MIN(calculado_em), MIN(competencia), COUNT(*) FROM car_contrato"
    ).fetchone()
    mais_antigo, comp_cache, quantos = (linha or (None, None, 0))
    if not quantos:
        tem_termo = conn.execute("SELECT 1 FROM contrato_termo LIMIT 1").fetchone()
        return "cache vazio com termos na base" if tem_termo else None
    if comp_cache != competencia:
        return f"cache é da competência {comp_cache}, e a pedida é {competencia}"
    hoje = _agora()[:10]
    return mais_antigo if (mais_antigo or "")[:10] < hoje else None


def _grid(conn, competencia: str, q=None, situacao=None, empresa=None,
          divergencia=False, refazer_se_velho=True) -> dict:
    """Uma linha por CONTRATO, lida de `car_contrato`.

    ⚠️ O grid da CAR é por contrato, e não por cliente como o da CTR. O motivo
    é o que ele pediu: *"saber o que está sendo cobrado do cliente por mês
    conforme contrato"* -- preço, cancelamento e renovação são fatos do termo,
    e um cliente com 4 termos tem 4 preços. Agrupar por cliente esconderia
    justamente a linha onde a ação acontece.
    """
    porque = _cache_velho(conn, competencia) if refazer_se_velho else None
    refeito = None
    if porque:
        log.info("CAR: refazendo car_contrato (%s)", porque)
        refeito = {"porque": porque, **registro.recalcular_todos(conn, competencia)}

    sql = ["""SELECT termo_id, cnpj, numero, empresa, situacao, motivo,
                     placas_ativas, placas_com_valor, placas_sem_valor,
                     valor_mensal_total, divergencia, competencia, calculado_em
                FROM car_contrato"""]
    onde, p = [], []
    if situacao:
        onde.append("situacao = ?")
        p.append(situacao.upper())
    if empresa:
        onde.append("empresa = ?")
        p.append(empresa)
    if divergencia:
        onde.append("divergencia IS NOT NULL")
    if q:
        alvo = f"%{q.strip().lower()}%"
        onde.append("(LOWER(COALESCE(numero,'')) LIKE ? OR cnpj LIKE ?)")
        p += [alvo, f"%{''.join(ch for ch in q if ch.isalnum())}%"]
    if onde:
        sql.append("WHERE " + " AND ".join(onde))
    # Quem senta na tela ataca o que mais pesa: placa cobrável sem preço
    # primeiro, como na pré-fatura.
    sql.append("ORDER BY placas_sem_valor DESC, placas_ativas DESC, numero")

    nomes = prefatura.nomes_dos_clientes(conn)
    linhas = []
    for (tid, cnpj, numero, emp, sit, mot, ativas, com, sem, total, div,
         comp, calc) in conn.execute(" ".join(sql), p):
        linhas.append({
            "termo_id": tid, "cnpj": cnpj, "nome": nomes.get(cnpj),
            "numero": numero, "empresa": emp, "situacao": sit, "motivo": mot,
            "placas_ativas": ativas, "placas_com_valor": com,
            "placas_sem_valor": sem, "valor_mensal_total": total,
            "divergencia": div, "competencia": comp, "calculado_em": calc,
        })

    return {
        "competencia": competencia,
        "contratos": linhas,
        "totais": {
            "contratos": len(linhas),
            "ativos": sum(1 for l in linhas if l["situacao"] == motor.ATIVO),
            "inativos": sum(1 for l in linhas if l["situacao"] == motor.INATIVO),
            "divergencias": sum(1 for l in linhas if l["divergencia"]),
            "placas_ativas": sum(l["placas_ativas"] or 0 for l in linhas),
            "placas_sem_valor": sum(l["placas_sem_valor"] or 0 for l in linhas),
        },
        # 🚨 `M12`: a tela diz QUANDO o cache foi feito e se esta chamada o
        # refez. Número derivado sem a hora dele é número sem prazo.
        "cache": {"refeito_agora": refeito,
                  "calculado_em": min((l["calculado_em"] for l in linhas),
                                      default=None)},
    }


@router.get("/clientes")
async def clientes(competencia: str | None = Query(None),
                   q: str | None = Query(None),
                   situacao: str | None = Query(None),
                   empresa: str | None = Query(None),
                   divergencia: bool = Query(False)):
    """O grid da aba: um contrato por linha, com situação, placas e valor."""
    comp = _competencia(competencia)
    return await _exec(_grid, comp, q=q, situacao=situacao, empresa=empresa,
                       divergencia=divergencia)


@router.get("/clientes.csv", response_class=PlainTextResponse)
async def clientes_csv(competencia: str | None = Query(None),
                       q: str | None = Query(None),
                       situacao: str | None = Query(None),
                       empresa: str | None = Query(None),
                       divergencia: bool = Query(False)):
    """O mesmo grid, com o mesmo filtro, em CSV. Separador `;`, como a casa."""
    comp = _competencia(competencia)
    d = await _exec(_grid, comp, q=q, situacao=situacao, empresa=empresa,
                    divergencia=divergencia)
    cab = ("cnpj;cliente;termo;empresa;situacao;motivo;placas_ativas;"
           "placas_com_valor;placas_sem_valor;valor_mensal_total;divergencia")
    corpo = [";".join(str(x if x is not None else "") for x in (
        l["cnpj"], l["nome"], l["numero"], l["empresa"], l["situacao"],
        (l["motivo"] or "").replace(";", ","), l["placas_ativas"],
        l["placas_com_valor"], l["placas_sem_valor"], l["valor_mensal_total"],
        (l["divergencia"] or "").replace(";", ",")))
        for l in d["contratos"]]
    return PlainTextResponse(
        "\n".join([cab] + corpo), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=car_{comp}.csv"})


@router.get("/cliente/{cnpj}")
async def cliente(cnpj: str, competencia: str | None = Query(None)):
    """A ficha do cliente na competência: contratos, placas e o valor de cada.

    ⚠️ O CNPJ VEM COMO ESTÁ, sem `isdigit()`. É o conserto do X1 aplicado desde
    o nascimento: `WQ0P6GLD000108` passado por um filtro de dígitos vira
    `000108`, e `000108` é chave de sete tabelas. Quem valida a forma é
    `car_busca.parece_documento`, que conhece o formato alfanumérico.
    """
    bruto = (cnpj or "").strip()
    comp = _competencia(competencia)

    def _ler(conn):
        return _montar_com_weso(conn, comp, cnpj=_resolver_cnpj(conn, bruto))
    return await _exec(_ler)


@router.get("/termo/{termo_id}")
async def termo(termo_id: int, competencia: str | None = Query(None)):
    """Um contrato: as linhas de cobrança do mês e a linha do tempo do preço.

    🚨 AS DUAS COISAS NA MESMA RESPOSTA, de propósito. "Quanto se cobra" sem
    "por que esse valor" é o número que ninguém consegue defender -- e é
    exatamente a pergunta que esta aba existe para responder.
    """
    comp = _competencia(competencia)

    def _ler(conn):
        doc = _cnpj_do_termo(conn, termo_id)
        pre = _montar_com_weso(conn, comp, cnpj=doc)
        achado = None
        for c in pre["clientes"]:
            for ct in c["contratos"]:
                if ct["termo_id"] == termo_id:
                    achado = {"cliente": {"cnpj": c["cnpj"], "nome": c["nome"]},
                              **ct}
        return {
            "competencia": comp, "termo_id": termo_id, "cnpj": doc,
            # 🚨 `None` quando o contrato NÃO entra na pré-fatura do mês, e a
            # tela diz por quê em vez de desenhar um contrato vazio: sem placa
            # cobrável nesta competência ele não tem linha de cobrança, e isso
            # é informação, não ausência de dado.
            "contrato": achado,
            "porque_sem_linhas": None if achado else
            ("nenhuma placa deste contrato estava cobrável em " + comp +
             " (a régua é ATIVA ou EM_AVISO_PREVIO na CTR)"),
            "historico_preco": registro.historico_de_preco(conn, termo_id),
        }
    return await _exec(_ler)


@router.get("/busca")
async def buscar(q: str = Query(...)):
    """A caixa única: nome, CNPJ, placa, número de termo e ID em uso.

    ⚠️ Responde com `achou_por` e `como` SEMPRE, inclusive no vazio. É o que faz
    a tela dizer *por onde* procurou: busca que devolve nada sem dizer o que
    tentou manda o operador digitar de novo a mesma coisa.
    """
    return await _exec(busca.resolver, q)


@router.get("/fila-sem-valor")
async def fila_sem_valor(competencia: str | None = Query(None),
                         limite: int = Query(200, le=2000)):
    """Os contratos com placa cobrável e SEM preço, do que mais pesa ao menos.

    É a fila de trabalho do lançamento em lote, e existe por um número medido
    em 28/10: das 2.993 placas cobráveis, **zero** tinha valor.
    """
    comp = _competencia(competencia)

    def _ler(conn):
        placas, idade = _weso()
        return {"competencia": comp, "limite": limite,
                "weso": {"lido": True, "idade_h": idade, "chaves": len(placas)},
                "fila": registro.contratos_sem_valor(conn, comp, limite,
                                                     weso=placas,
                                                     idade_weso=idade)}
    return await _exec(_ler)


@router.get("/termo/{termo_id}/historico-preco")
async def historico_preco(termo_id: int):
    """A linha do tempo do preço, **com os anulados marcados**."""
    return await _exec(
        lambda conn: {"termo_id": termo_id,
                      "eventos": registro.historico_de_preco(conn, termo_id)})


# ─────────────────────────────────────────────────────────────────────────────
# Pré-fatura
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/prefatura")
async def prefatura_do_mes(competencia: str | None = Query(None),
                           cnpj: str | None = Query(None)):
    """O que cobrar na competência. Só leitura, e **não grava nada**.

    🚨 NÃO É FATURA, E A RESPOSTA DIZ ISSO (`variavel.ligada = false`): a parte
    de serviço espera a lista de itens do catálogo do Harmonit que se cobram do
    cliente, que é decisão dele. Somar só a mensalidade e chamar de total seria
    tela que mente por omissão.
    """
    comp = _competencia(competencia)
    doc = (cnpj or "").strip() or None

    def _ler(conn):
        return _montar_com_weso(
            conn, comp, cnpj=_resolver_cnpj(conn, doc) if doc else None)
    return await _exec(_ler)


@router.get("/prefatura.csv", response_class=PlainTextResponse)
async def prefatura_csv(competencia: str | None = Query(None),
                        cnpj: str | None = Query(None)):
    """A mesma pré-fatura, uma linha por linha de cobrança, em CSV."""
    comp = _competencia(competencia)
    doc = (cnpj or "").strip() or None

    def _ler(conn):
        return _montar_com_weso(
            conn, comp, cnpj=_resolver_cnpj(conn, doc) if doc else None)
    pre = await _exec(_ler)
    return PlainTextResponse(
        prefatura.para_csv(pre), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=prefatura_{comp}.csv"})


@router.post("/prefatura/fechar")
async def fechar_prefatura(corpo: dict | None = None,
                           usuario: dict = Depends(requer_aba("contas_receber"))):
    """Registra em `car_leitura` que esta leitura do mês foi tirada, com autor.

    🚨 ESTA É A ÚNICA ESCRITA QUE NÃO É UM FATO DE DINHEIRO, e ela existe para
    uma pergunta só, que vai aparecer: *"reabri outubro e o número mudou, por
    quê?"*. Com a assinatura guardada, a mudança é **fato** e a causa se explica
    pelos eventos; sem ela, é discussão. **Não cria recebível** -- recebível
    copiado congela, e no mês seguinte ninguém sabe dizer de onde veio.
    """
    corpo = corpo or {}
    comp = _competencia(corpo.get("competencia"))
    pedido = (corpo.get("cnpj") or "").strip() or None
    por = _autor(usuario)

    def _gravar(conn):
        doc = _resolver_cnpj(conn, pedido) if pedido else None
        pre = _montar_com_weso(conn, comp, cnpj=doc)
        # A assinatura é do RESULTADO NORMALIZADO, não da resposta inteira: o
        # cache e a hora mudam a cada chamada e fariam toda leitura parecer
        # diferente da anterior.
        corpo_assinado = [
            (c["cnpj"], ct["numero"], l["placa"], l["valor"])
            for c in pre["clientes"] for ct in c["contratos"] for l in ct["linhas"]]
        assinatura = hashlib.sha256(
            json.dumps(corpo_assinado, ensure_ascii=False,
                       sort_keys=True).encode("utf-8")).hexdigest()
        t = pre["totais"]
        cur = conn.execute(
            """INSERT INTO car_leitura (competencia, cnpj, gerada_em, por,
                                        clientes, placas, sem_valor, total, assinatura)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (comp, doc, _agora(), por, t["clientes"], t["placas"],
             t["sem_valor"], t["total"], assinatura))
        anteriores = [
            {"id": i, "gerada_em": g, "por": p, "total": tt, "assinatura": a,
             "igual_a_esta": a == assinatura}
            for i, g, p, tt, a in conn.execute(
                """SELECT id, gerada_em, por, total, assinatura FROM car_leitura
                    WHERE competencia = ? AND id <> ?
                    ORDER BY id DESC LIMIT 10""", (comp, cur.lastrowid))]
        return {"leitura_id": cur.lastrowid, "competencia": comp, "cnpj": doc,
                "por": por, "assinatura": assinatura, "totais": t,
                "leituras_anteriores": anteriores}
    return await _exec(_gravar)


# ─────────────────────────────────────────────────────────────────────────────
# G1 · G2 · G3 · G4 · G5 — a tela operacional: gerar os contas a receber
# ─────────────────────────────────────────────────────────────────────────────
# 🔵 Pedido dele em 30/10: *"proponha uma tela operacional paa o contas a
# receber, onde possamos realmente gerar os contas a receber exibindo claramente
# o que é fixo de contrato (com essa informação para consulta se precisar
# - aqueles vinculos atraves de clique que falei - e tbm os variaveis que vierem
# de OS do tipo financeiro que estão marcados para cobrar e finalizados)"*.
# Mockup APROVADO: `https://claude.ai/artifact/RnvbtMzgCE44mgfqQsvKDt`.
#
# 🚨 TUDO AQUI É LEITURA, menos o fechamento. Gerar não escreve no Harmonit --
# a API financeira dele é 100% leitura (varrida no `swagger.json`), e o lote é
# a lista pronta para lançamento. A tela declara isso em `limites`.
def _os_financeiras(conn) -> list:
    """As OS da situação 15746, com o cliente já resolvido. Uma consulta.

    🚨 A FONTE É A `os_historico`, a varredura que já roda de 5 em 5 minutos --
    e não o Harmonit. Não existe no `swagger.json` rota que LISTE OS por
    situação (só `ObterOrdemServico` por id e `ObterOrdemServicoPorNumero`), e
    montar esta fila pela API seria uma chamada por OS.

    ⚠️ `excluida = 0`: OS apagada no Harmonit continua na tabela, marcada, e
    cobrar por ela seria cobrar pelo que não existe mais.

    ⚠️ `clientes` é indexada pelo `harmonit_id`, e o LEFT JOIN é de propósito:
    OS cujo cliente não está nesta base **aparece** na tela com a causa (medido
    em 03/11: a OS 16846, `cliente_id` 1036572). Um JOIN interno a esconderia,
    e com ela R$ 1.080,00 de cobrança real.
    """
    try:
        cru = conn.execute(
            """SELECT h.numero_os, h.os_id, h.situacao_id, h.status_str,
                      h.cliente_id, h.data_previsao, h.materiais_json,
                      c.cnpjcpf, cc.nome
                 FROM os_historico h
                 LEFT JOIN clientes c ON c.harmonit_id = h.cliente_id
                 LEFT JOIN contrato_cliente cc ON cc.cnpj = c.cnpjcpf
                WHERE h.excluida = 0 AND h.situacao_id = ?""",
            (cvar.SITUACAO_FINANCEIRO,)).fetchall()
    except sqlite3.Error:
        # Banco sem a varredura (cópia restaurada, banco de teste de outra
        # suíte): ausência da tabela é "a varredura não passou aqui", e a fila
        # variável nasce vazia -- nunca erro na tela do lote inteiro.
        log.warning("os_historico indisponível: a fila variável sai vazia")
        return []

    linhas = []
    for (numero, os_id, situacao, status, cliente_id, previsao, materiais,
         cnpj, nome) in cru:
        try:
            itens = json.loads(materiais) if materiais else []
        except (ValueError, TypeError):
            # 🚨 JSON ILEGÍVEL NÃO VIRA "OS SEM ITEM": sem item a cobrar e item
            # que não deu para ler são afirmações diferentes, e a segunda é
            # defeito de dado que tem de aparecer.
            itens = []
            log.warning("materiais_json ilegível na OS %s", numero)
        linhas.append({
            "numero_os": numero, "os_id": os_id, "situacao_id": situacao,
            "status_str": status, "cliente_id": cliente_id,
            "data_previsao": previsao, "materiais": itens,
            "cnpj": cnpj, "cliente": nome})
    return linhas


def _faturadas(conn) -> set:
    """Os `numero_os` que o Harmonit já lançou, do espelho (F1).

    ⚠️ SEM FILTRO DE COMPETÊNCIA, de propósito: o lançamento de serviço do
    Harmonit **não traz período de referência** na descrição (é o grupo
    "sem competência" da `faturado_do_mes`), então restringir a comparação a um
    mês deixaria passar OS já faturada em outro vencimento -- e o cliente
    receberia dois boletos da mesma OS.
    """
    try:
        return {r[0] for r in conn.execute(
            "SELECT DISTINCT numero_os FROM car_faturado "
            "WHERE numero_os IS NOT NULL")}
    except sqlite3.Error:
        # Banco anterior ao bloco F1: ausência da tabela é "o espelho não leu",
        # e nesse caso NENHUMA OS pode ser dita já faturada.
        return set()


def _variavel(conn, competencia: str | None) -> dict:
    return cvar.fila(_os_financeiras(conn), competencia, _faturadas(conn))


def _vencimento(bruto) -> str | None:
    """A data escolhida pelo operador, `AAAA-MM-DD`. Vazia é `None`.

    🔴 NÃO EXISTE DIA DE VENCIMENTO EM COLUNA NENHUMA desta base (medido em
    30/10), e por isso ele é entrada da tela, não derivação. Data ilegível é
    recusada com 400 em vez de virar `None` em silêncio: lote com vencimento
    perdido é lote que ninguém consegue lançar.
    """
    t = (bruto or "").strip()
    if not t:
        return None
    try:
        return date.fromisoformat(t).isoformat()
    except ValueError:
        raise HTTPException(400, f"vencimento inválido: {t!r} (use AAAA-MM-DD)")


def _montar_lote(conn, competencia: str, vencimento: str | None,
                 apenas=None) -> dict:
    pre = _montar_com_weso(conn, competencia)
    var = _variavel(conn, competencia)
    saida = lote.montar(pre, var, vencimento=vencimento, apenas=apenas)
    # O que a tela precisa para desenhar o cabeçalho sem uma segunda chamada:
    # de quando é a WESO, se o espelho leu, e a cobertura da janela.
    saida["weso"] = pre["weso"]
    saida["faturado"] = {
        "lido": pre["faturado"].get("lido"),
        "lido_em": pre["faturado"].get("lido_em"),
        "porque": pre["faturado"].get("porque"),
        "cobertura": pre["faturado"].get("cobertura"),
        "totais": pre["faturado"].get("totais"),
    }
    saida["variavel"] = {k: v for k, v in var.items() if k != "por_cliente"}
    saida["prefatura_totais"] = pre["totais"]
    return saida


@router.get("/variavel")
async def variavel_do_mes(competencia: str | None = Query(None),
                          todas: bool = Query(False)):
    """A fila variável: OS em "Financeiro", finalizada, com item a cobrar.

    `todas = true` ignora a competência -- serve à conferência *"esta OS caiu em
    que mês?"*, que a tela faz ao abrir a ficha de uma OS.
    """
    comp = None if todas else _competencia(competencia)

    def _ler(conn):
        fila = _variavel(conn, comp)
        # `por_cliente` tem a mesma informação de `a_gerar`, agrupada; mandar as
        # duas dobraria a resposta sem acrescentar fato.
        return {k: v for k, v in fila.items() if k != "por_cliente"}
    return await _exec(_ler)


@router.get("/os/{numero_os}")
async def os_do_variavel(numero_os: int):
    """A ficha de UMA OS: os itens com o `cobrar` de cada um à vista (G3).

    🚨 É o vínculo por clique do lado variável, e ele mostra o `cobrar` item por
    item porque é esse booleano que decide o valor da linha. Tela que mostra só
    o total faz o operador abrir o Harmonit para saber de onde ele veio.
    """
    def _ler(conn):
        todas = _os_financeiras(conn)
        achada = next((o for o in todas if o["numero_os"] == numero_os), None)
        if achada is None:
            raise HTTPException(
                404, f"a OS {numero_os} não está na varredura local com "
                     f"situação {cvar.SITUACAO_FINANCEIRO} (Financeiro)")
        ficha = cvar.classificar(achada, _faturadas(conn))
        # 🚨 TODOS os itens, não só os a cobrar: é o contraste que explica a
        # conta. O item com `cobrar = false` (PAGAMENTO DE TÉCNICO, KM) aparece
        # esmaecido no mockup, e sem ele a soma parece arbitrária.
        ficha["itens_todos"] = [
            {"descricao": i.get("descricao"),
             "quantidade": i.get("quantidade"),
             "valor": cvar.valor_texto(i.get("valor")),
             "valor_total": cvar.valor_texto(i.get("valorTotal")),
             "cobrar": bool(i.get("cobrar")),
             "comodato": bool(i.get("comodato"))}
            for i in achada["materiais"] if isinstance(i, dict)]
        # Os lançamentos que o Harmonit já tem desta OS -- a prova de "já
        # faturada", com número e valor, em vez da palavra sozinha.
        try:
            ficha["lancamentos_no_harmonit"] = [
                {"lancamento_id": i, "estado": e, "valor": v, "vencimento": vc,
                 "descricao": d}
                for i, e, v, vc, d in conn.execute(
                    """SELECT id, estado, valor, vencimento, descricao
                         FROM car_faturado WHERE numero_os = ?
                        ORDER BY id""", (numero_os,))]
        except sqlite3.Error:
            ficha["lancamentos_no_harmonit"] = []
        return ficha
    return await _exec(_ler)


@router.get("/gerar")
async def gerar(competencia: str | None = Query(None),
                vencimento: str | None = Query(None)):
    """O lote da competência: um documento por cliente, fixo × variável.

    🚨 **NÃO GRAVA NADA.** É a tela de conferência antes do fechamento, e o
    fechamento é outra rota, com autor. Gerar na leitura faria recarregar a
    página lançar dinheiro.
    """
    comp = _competencia(competencia)
    venc = _vencimento(vencimento)

    def _ler(conn):
        return _montar_lote(conn, comp, venc)
    return await _exec(_ler)


@router.get("/gerar.csv", response_class=PlainTextResponse)
async def gerar_csv(competencia: str | None = Query(None),
                    vencimento: str | None = Query(None),
                    cnpjs: str | None = Query(None)):
    """As linhas de lançamento do lote, em CSV -- o formato do Harmonit.

    🚨 É ISTO QUE TORNA A SUBSTITUIÇÃO POSSÍVEL HOJE: a API financeira do
    Harmonit não tem rota de criar cobrança, então a ponte entre a CAR e o
    lançamento é a lista. O Asaas (que é quem de fato emite) é o bloco G6/D8.
    """
    comp = _competencia(competencia)
    venc = _vencimento(vencimento)
    # 🚨 `None` (parâmetro ausente) É A CARTEIRA INTEIRA; lista VAZIA é seleção
    # vazia, e as duas não podem colapsar. O `or None` que eu havia escrito
    # fazia a seleção vazia virar "tudo" -- e foi o teste do fechamento que
    # pegou isso, na versão gêmea desta linha: quem desmarca todos e exporta
    # receberia a carteira inteira, calado.
    apenas = (None if cnpjs is None
              else [c.strip() for c in cnpjs.split(",") if c.strip()])

    def _ler(conn):
        return _montar_lote(conn, comp, venc, apenas=apenas)
    doc = await _exec(_ler)
    return PlainTextResponse(
        lote.para_csv(doc), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f"attachment; filename=contas_a_receber_{comp}.csv"})


@router.post("/gerar/fechar")
async def fechar_lote(corpo: dict | None = None,
                      usuario: dict = Depends(requer_aba("contas_receber"))):
    """Fecha o lote da competência: grava em `car_leitura` com escopo `lote`.

    🚨 ISTO FECHA O ACHADO **A2** da auditoria de 28/10: a rota
    `POST /prefatura/fechar` existia **sem botão**, e `car_leitura` seguia sem
    escritor *pelo uso* -- que é justo o que eu disse ter consertado ao criar a
    rota. Agora o fechamento tem tela, e tem a sua, própria: fechar o lote e
    tirar uma leitura analítica são fatos diferentes (coluna `escopo`).

    🚨 **NÃO EMITE NADA E NÃO ESCREVE NO HARMONIT**, e a resposta repete isso em
    `limites`. O que ele grava é a assinatura das linhas geradas, para a
    pergunta que vai aparecer: *"reabri setembro e o número mudou, por quê?"*.
    """
    corpo = corpo or {}
    comp = _competencia(corpo.get("competencia"))
    venc = _vencimento(corpo.get("vencimento"))
    apenas = corpo.get("cnpjs")
    if apenas is not None and not isinstance(apenas, list):
        raise HTTPException(400, "cnpjs deve ser uma lista de CNPJ")
    por = _autor(usuario)

    def _gravar(conn):
        # 🚨 LISTA VAZIA É SELEÇÃO VAZIA, não "a carteira inteira". O
        # `if apenas else None` que eu havia escrito aqui fazia `cnpjs: []`
        # fechar TODOS os clientes -- quem desmarcasse tudo e clicasse em fechar
        # fecharia o mês inteiro, calado. Quem pegou foi o teste.
        doc = _montar_lote(conn, comp, venc,
                           apenas=None if apenas is None
                           else [str(c).strip() for c in apenas])
        if not doc["lancamentos"]:
            # 🚨 FECHAR LOTE VAZIO É RECUSADO, e a frase diz a causa provável.
            # Em 03/11 `car_evento` tem 0 linhas: sem adotar as propostas, o
            # fixo inteiro é R$ 0 e o lote traz só as 3 OS. Gravar um
            # fechamento vazio deixaria a assinatura de um mês que ninguém
            # gerou, e no mês seguinte ela pareceria prova.
            raise HTTPException(
                400, "o lote não tem nenhuma linha para fechar. Se o fixo está "
                     "vazio, é porque nenhum preço foi lançado na CAR ainda — "
                     "adote as propostas da semeadura antes de fechar")
        # A assinatura é das LINHAS, normalizadas: a hora e o cache mudam a cada
        # chamada e fariam todo fechamento parecer diferente do anterior.
        corpo_assinado = sorted(
            (l["cnpj"], l["tipo"], l.get("numero_contrato"), l.get("numero_os"),
             l["valor"]) for l in doc["lancamentos"])
        assinatura = hashlib.sha256(
            json.dumps(corpo_assinado, ensure_ascii=False,
                       sort_keys=True).encode("utf-8")).hexdigest()
        t = doc["totais"]
        cur = conn.execute(
            """INSERT INTO car_leitura (competencia, cnpj, gerada_em, por,
                                        clientes, placas, sem_valor, total,
                                        assinatura, escopo, vencimento,
                                        lancamentos)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (comp, None, _agora(), por, t["a_gerar"],
             doc["prefatura_totais"]["placas"],
             doc["prefatura_totais"]["sem_valor"], t["total"], assinatura,
             "lote", venc, t["lancamentos"]))
        anteriores = [
            {"id": i, "gerada_em": g, "por": p, "total": tt,
             "lancamentos": n, "vencimento": vc, "assinatura": a,
             "igual_a_este": a == assinatura}
            for i, g, p, tt, n, vc, a in conn.execute(
                """SELECT id, gerada_em, por, total, lancamentos, vencimento,
                          assinatura
                     FROM car_leitura
                    WHERE competencia = ? AND escopo = 'lote' AND id <> ?
                    ORDER BY id DESC LIMIT 10""", (comp, cur.lastrowid))]
        return {"leitura_id": cur.lastrowid, "competencia": comp,
                "vencimento": venc, "por": por, "assinatura": assinatura,
                "totais": t, "fechamentos_anteriores": anteriores,
                "limites": doc["limites"]}
    return await _exec(_gravar)


@router.get("/gerar/fechamentos")
async def fechamentos(competencia: str | None = Query(None)):
    """Os fechamentos de lote desta competência, do mais novo para o mais velho.

    É o que permite a tela dizer *"este mês já foi fechado, por quem e quando"*
    em vez de oferecer o botão como se fosse a primeira vez.
    """
    comp = _competencia(competencia)

    def _ler(conn):
        return {"competencia": comp, "fechamentos": [
            {"id": i, "gerada_em": g, "por": p, "total": t,
             "lancamentos": n, "clientes": cl, "vencimento": v,
             "assinatura": a}
            for i, g, p, t, n, cl, v, a in conn.execute(
                """SELECT id, gerada_em, por, total, lancamentos, clientes,
                          vencimento, assinatura
                     FROM car_leitura
                    WHERE competencia = ? AND escopo = 'lote'
                    ORDER BY id DESC LIMIT 20""", (comp,))]}
    return await _exec(_ler)


# ─────────────────────────────────────────────────────────────────────────────
# F1 — o espelho do faturado: o interruptor, o botão e o que ele trouxe
# ─────────────────────────────────────────────────────────────────────────────
def _resumo_do_espelho(conn) -> dict:
    """Quantas linhas o espelho tem, por competência e por tipo. Só leitura."""
    linha = conn.execute(
        "SELECT COUNT(*), MAX(lido_em), MIN(competencia), MAX(competencia) "
        "FROM car_faturado").fetchone()
    quantas, lido_em, comp_min, comp_max = linha or (0, None, None, None)
    por_tipo = {t: n for t, n in conn.execute(
        "SELECT tipo, COUNT(*) FROM car_faturado GROUP BY tipo")}
    venc = [m for m, in conn.execute(
        "SELECT DISTINCT venc_ano_mes FROM car_faturado "
        "WHERE venc_ano_mes IS NOT NULL ORDER BY venc_ano_mes")]
    return {"lancamentos": quantas, "lido_em": lido_em,
            "competencia_de": comp_min, "competencia_ate": comp_max,
            "por_tipo": por_tipo,
            # 🚨 De quais meses de VENCIMENTO o espelho foi lido. E a resposta
            # honesta a "esta conta esta completa?" -- ver o achado de 30/10 na
            # `meses_da_passada`.
            "meses_de_vencimento": venc,
            "sem_cnpj": conn.execute(
                "SELECT COUNT(*) FROM car_faturado WHERE cnpj IS NULL").fetchone()[0],
            "sem_termo": conn.execute(
                "SELECT COUNT(*) FROM car_faturado "
                "WHERE termo_numero IS NOT NULL AND termo_id IS NULL").fetchone()[0]}


async def _estado_do_espelho() -> dict:
    """Interruptor + última passada + a régua do botão, num lugar só."""
    ativa = (await storage.get_config(sync_faturado.FLAG, "false")) == "true"
    passada = await rotinas.ultima("faturado")
    manual = await storage.get_config(sync_faturado.CHAVE_MANUAL, "")
    botao = cf.pode_atualizar_agora(ativa, passada["ultima_em"], manual)
    return {
        "ativa": ativa,
        "intervalo_h": sync_faturado.INTERVALO_ROTINA // 3600,
        "ultima_em": passada["ultima_em"],
        "ultimo_resultado": passada["resultado"],
        "atrasada": passada["atrasada"],
        "sem_registro": passada["sem_registro"],
        "ultima_manual_em": manual or None,
        # 🚨 A TELA RECEBE O MOTIVO, não só o `false`. Botão esmaecido que não
        # diz por quê é botão que mente (`M12`).
        "botao": botao,
        "espera_apos_automatica_h": cf.ESPERA_APOS_AUTOMATICA_H,
    }


@router.get("/faturado/interruptor")
async def ler_interruptor_faturado():
    """Estado da rotina do espelho, a última passada e a régua do botão.

    🚨 "LIGADA" NÃO É "RODOU", e a `FIN_1.1` provou isso do jeito caro: ficou
    desligada de 02/10 a 08/10 e nada na tela dizia. Aqui vêm as duas coisas.
    """
    estado = await _estado_do_espelho()
    return {**estado, "espelho": await _exec(_resumo_do_espelho)}


@router.put("/faturado/interruptor")
async def mudar_interruptor_faturado(corpo: dict,
                                     _=Depends(requer_aba("config"))):
    """Liga/desliga a rotina diária.

    🚨 LER EXIGE `contas_receber` (a tranca do router), MUDAR EXIGE `config` --
    a mesma régua do interruptor da `FIN_1.1`. Quem opera a cobrança não
    precisa ligar laço, e laço ligado por engano fala com o Harmonit todo dia.
    """
    if not isinstance(corpo, dict) or "ativa" not in corpo:
        raise HTTPException(400, "informe `ativa` (true/false)")
    ativa = bool(corpo.get("ativa"))
    await storage.set_config(sync_faturado.FLAG, "true" if ativa else "false")
    log.info("CAR: rotina do espelho do faturado %s",
             "LIGADA" if ativa else "DESLIGADA")
    return await _estado_do_espelho()


@router.post("/faturado/atualizar")
async def atualizar_faturado(corpo: dict | None = None,
                             usuario: dict = Depends(requer_aba("contas_receber"))):
    """O botão "atualizar agora": lê o Harmonit e refaz o espelho dos meses.

    🔵 REGRA DELE, 30/10: com a rotina **desligada** o botão é livre; **ligada**,
    vale **uma vez por dia** e só **4 h depois da passada automática**. Quem
    decide é `car_faturado.pode_atualizar_agora`, pura e travada por teste; aqui
    só se obedece.

    🚨 RECUSA É **429 COM O MOTIVO**, não 403 nem silêncio: o operador precisa
    saber que a janela existe e quando ela abre.
    """
    corpo = corpo or {}
    estado = await _estado_do_espelho()
    if not estado["botao"]["pode"]:
        raise HTTPException(429, estado["botao"]["motivo"])

    meses = None
    pedido = corpo.get("meses")
    if pedido:
        # Carga à mão de um intervalo (a inicial, 2026-01 a 2027-12). Formato
        # 'AAAA-MM', validado pela mesma função da competência -- um lugar só.
        try:
            meses = [(int(motor.validar_competencia(str(m))[:4]),
                      int(str(m)[5:7])) for m in pedido]
        except motor.CompetenciaInvalida as e:
            raise HTTPException(400, str(e))
        if len(meses) > 36:
            raise HTTPException(400, f"{len(meses)} meses é mais que o teto de 36 "
                                     "por chamada (são 2 GET por mês)")

    r = await sync_faturado.run_sync(meses=meses)
    await storage.set_config(sync_faturado.CHAVE_MANUAL, _agora())
    log.info("CAR: espelho atualizado à mão por %s — %s lançamentos, %s gravados",
             _autor(usuario), r["lidos"], r["gravadas"])
    return {"por": _autor(usuario), **r,
            "estado": await _estado_do_espelho(),
            "espelho": await _exec(_resumo_do_espelho)}


# ─────────────────────────────────────────────────────────────────────────────
# F4 — semear preço do que o Harmonit já fatura
# ─────────────────────────────────────────────────────────────────────────────
def _propostas(conn, competencia: str) -> dict:
    """As propostas de preço da competência, lidas do espelho. Não grava nada."""
    faturado = [
        {"id": i, "tipo": t, "competencia": c, "valor": v,
         "termo_id": tid, "termo_numero": tn, "contato": ct}
        for i, t, c, v, tid, tn, ct in conn.execute(
            """SELECT id, tipo, competencia, valor, termo_id, termo_numero, contato
                 FROM car_faturado WHERE competencia = ?""", (competencia,))]
    termos = {tid: {"id": tid, "cnpj": cnpj, "numero": num, "empresa": emp}
              for tid, cnpj, num, emp in conn.execute(
                  "SELECT id, cnpj, numero, empresa FROM contrato_termo")}
    eventos = prefatura.eventos_por_termo(conn)
    nomes = prefatura.nomes_dos_clientes(conn)

    def vigente(termo_id):
        # 🚨 `preco_vigente` devolve o EVENTO, não o número -- e o campo dele é
        # `valor_mensal`. Ler `"valor"` aqui daria `None` em todo contrato, e a
        # semeadura proporia preço para quem já tem, sem conflito nenhum.
        e = motor.preco_vigente(eventos.get(termo_id, []), competencia)
        return (e or {}).get("valor_mensal")

    r = cf.propor_precos(faturado, termos, vigente, competencia)
    for lista in (r["propostas"], r["conflitos"]):
        for p in lista:
            p["nome"] = nomes.get(p.get("cnpj"))
    return r


@router.get("/semear")
async def ler_semeadura(competencia: str | None = Query(None)):
    """O que o Harmonit cobra e a CAR ainda não sabe — **proposta, não fato**.

    Os conflitos saem à parte e **não entram no lote**: contrato que já tem
    outro preço vigente pede decisão, não cópia. É a regra do "adotar por linha"
    que ele mandou manter em 30/10.
    """
    comp = _competencia(competencia)
    return await _exec(_propostas, comp)


@router.post("/semear")
async def semear(corpo: dict,
                 usuario: dict = Depends(requer_aba("contas_receber"))):
    """Lança `PRECO` nos contratos escolhidos, com o valor que o Harmonit cobra.

    🚨 O CORPO DIZ **QUAIS**, NUNCA **QUANTO**. `termos` é uma lista de
    `termo_id`; o valor, a competência e o documento saem do espelho desta base.
    Aceitar valor do corpo deixaria a tela (ou quem chama a rota) escolher
    preço, e o preço é fato medido -- é a mesma razão de `por` sair do token.

    `termos` ausente ou vazio = **todas as propostas sem conflito** da
    competência, que é o lote dos 272 que ele aprovou.
    """
    comp = _competencia(corpo.get("competencia"))
    por = _autor(usuario)
    pedidos = corpo.get("termos")
    if pedidos is not None and not isinstance(pedidos, list):
        raise HTTPException(400, "termos: lista de termo_id, ou nada para o lote inteiro")
    if isinstance(pedidos, list):
        try:
            pedidos = {int(x) for x in pedidos}
        except (TypeError, ValueError):
            raise HTTPException(400, "termos: só aceita termo_id numérico")

    def _grava(conn):
        r = _propostas(conn, comp)
        # O conflito também pode ser adotado -- mas só **nomeado**, nunca pelo
        # lote: é o "alguém alterou" que ele pediu que continuasse possível.
        disponiveis = {p["termo_id"]: p for p in r["propostas"]}
        if pedidos:
            for p in r["conflitos"]:
                if p.get("valor") and p["termo_id"] in pedidos:
                    disponiveis[p["termo_id"]] = p
            escolhidas = [p for tid, p in disponiveis.items() if tid in pedidos]
            faltam = [{"termo_id": t, "cnpj": None,
                       "motivo": "não há proposta para este contrato nesta competência"}
                      for t in sorted(pedidos) if t not in disponiveis]
        else:
            escolhidas = list(r["propostas"])
            faltam = []
        if not escolhidas:
            raise HTTPException(
                400, "nenhuma proposta para lançar nesta competência "
                     f"({r['totais']['propostas']} propostas, "
                     f"{r['totais']['conflitos']} conflitos)")
        try:
            saida = registro.semear_em_lote(conn, escolhidas, por,
                                            motivo=corpo.get("motivo"))
        except registro.DadoInvalido as e:
            raise _recusa(e)
        saida["recusados"] = faltam + saida["recusados"]
        saida.update({"competencia": comp, "por": por,
                      "pedidos": len(escolhidas),
                      "propostas_disponiveis": r["totais"]["propostas"],
                      "conflitos": r["totais"]["conflitos"]})
        # A derivada é cache de uma régua que acabou de mudar: refaz na mesma
        # transação, para a tela não mostrar a carteira velha depois do lote.
        saida["recalculado"] = registro.recalcular_todos(conn, comp)
        return saida
    return await _exec(_grava)


# ─────────────────────────────────────────────────────────────────────────────
# As cinco ações + o lote. Toda uma transação, todo autor do token.
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/termo/{termo_id}/preco")
async def preco(termo_id: int, corpo: dict,
                usuario: dict = Depends(requer_aba("contas_receber"))):
    """A mensalidade passa a ser `valor` a partir de `competencia`.

    🚨 NÃO EXISTE "EDITAR PREÇO". Existe preço novo, com data, autor e motivo --
    e o anterior continua na linha do tempo, que é o histórico de reajuste de
    graça.
    """
    comp = _competencia(corpo.get("competencia"))
    valor = _texto_obrigatorio(corpo, "valor")
    por = _autor(usuario)

    def _grava(conn):
        doc = _cnpj_do_termo(conn, termo_id)
        try:
            eid = registro.lancar_preco(
                conn, doc, termo_id, valor, comp, por,
                motivo=corpo.get("motivo"), documento=corpo.get("documento"),
                placa_chave=corpo.get("placa_chave"))
        except registro.DadoInvalido as e:
            raise _recusa(e)
        return {"evento_id": eid, "termo_id": termo_id, "cnpj": doc,
                "competencia": comp, "por": por,
                "historico_preco": registro.historico_de_preco(conn, termo_id)}
    return await _exec(_grava)


@router.post("/termo/{termo_id}/cancelar")
async def cancelar(termo_id: int, corpo: dict,
                   usuario: dict = Depends(requer_aba("contas_receber"))):
    """Interrompe a COBRANÇA a partir da competência. Motivo obrigatório.

    🚨 NÃO MEXE EM PLACA. Rescisão de placa é evento da CTR e sai do documento.
    Se as placas seguem sustentadas lá, a CAR mostra isso como **divergência**,
    em vez de as duas abas discordarem caladas.
    """
    comp = _competencia(corpo.get("competencia"))
    por = _autor(usuario)

    def _grava(conn):
        doc = _cnpj_do_termo(conn, termo_id)
        try:
            eid = registro.cancelar(conn, doc, termo_id, comp, por,
                                    corpo.get("motivo"))
        except registro.DadoInvalido as e:
            raise _recusa(e)
        return {"evento_id": eid, "termo_id": termo_id, "cnpj": doc,
                "competencia": comp, "por": por}
    return await _exec(_grava)


@router.post("/termo/{termo_id}/renovar")
async def renovar(termo_id: int, corpo: dict,
                  usuario: dict = Depends(requer_aba("contas_receber"))):
    """A vigência recomeça nesta competência."""
    comp = _competencia((corpo or {}).get("competencia"))
    por = _autor(usuario)

    def _grava(conn):
        doc = _cnpj_do_termo(conn, termo_id)
        try:
            eid = registro.renovar(conn, doc, termo_id, comp, por,
                                   documento=(corpo or {}).get("documento"),
                                   motivo=(corpo or {}).get("motivo"))
        except registro.DadoInvalido as e:
            raise _recusa(e)
        return {"evento_id": eid, "termo_id": termo_id, "cnpj": doc,
                "competencia": comp, "por": por}
    return await _exec(_grava)


@router.post("/termo/{termo_id}/excecao")
async def excecao(termo_id: int, corpo: dict,
                  usuario: dict = Depends(requer_aba("contas_receber"))):
    """A negociação do mês: outro valor nesta competência, ou nada a cobrar.

    🚨 VALE SÓ NO MÊS LANÇADO (decisão de 28/10). Desconto permanente é `PRECO`
    novo, com motivo: desconto que se renova sozinho é o que ninguém lembra de
    desligar, e seis meses depois a receita caiu e nenhuma tela sabe dizer por
    quê.
    """
    comp = _competencia(corpo.get("competencia"))
    por = _autor(usuario)

    def _grava(conn):
        doc = _cnpj_do_termo(conn, termo_id)
        try:
            eid = registro.excecao(conn, doc, termo_id, comp, por,
                                   corpo.get("motivo"), valor=corpo.get("valor"),
                                   placa_chave=corpo.get("placa_chave"))
        except registro.DadoInvalido as e:
            raise _recusa(e)
        return {"evento_id": eid, "termo_id": termo_id, "cnpj": doc,
                "competencia": comp, "por": por,
                "vale_so_em": comp}
    return await _exec(_grava)


@router.post("/evento/{evento_id}/anular")
async def anular(evento_id: int, corpo: dict,
                 usuario: dict = Depends(requer_aba("contas_receber"))):
    """Anula um evento da CAR **sem apagá-lo**: o errado continua visível.

    ⚠️ Anular duas vezes responde 409, não 400: não é entrada inválida, é um
    estado que já existe -- e a mensagem diz qual anulação é.
    """
    por = _autor(usuario)

    def _grava(conn):
        try:
            eid = registro.anular(conn, evento_id, por, corpo.get("motivo"))
        except registro.JaAnulado as e:
            raise HTTPException(409, str(e))
        except registro.DadoInvalido as e:
            raise _recusa(e)
        return {"evento_id": eid, "anulou": evento_id, "por": por}
    return await _exec(_grava)


@router.post("/lote/preco")
async def lote_preco(corpo: dict,
                     usuario: dict = Depends(requer_aba("contas_receber"))):
    """Um `PRECO` por contrato, para vários contratos de uma vez.

    `termos` é uma lista de `termo_id`; o CNPJ de cada um sai desta base, não do
    corpo -- quem manda a chave manda o contrato.

    🚨 IDEMPOTENTE POR (termo, competência, valor): clicar duas vezes não lança
    duas vezes. E contrato recusado **não derruba o lote**: volta em
    `recusados`, com o motivo, e os outros entram. Lote que morre no meio deixa
    metade da carteira precificada e ninguém sabe qual metade.

    ⚠️ Teto de 2.000 contratos por chamada. Não é medo do volume (4.599 termos
    recalculam em 0,45 s): é que um lote maior que a carteira é quase sempre
    engano de quem chamou, e a resposta diz isso em vez de executar.
    """
    valor = _texto_obrigatorio(corpo, "valor")
    _texto_obrigatorio(corpo, "motivo")
    comp = _competencia(corpo.get("competencia"))
    por = _autor(usuario)
    ids = corpo.get("termos")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "termos: informe ao menos um termo_id")
    if len(ids) > 2000:
        raise HTTPException(400, f"lote de {len(ids)} contratos é maior que o "
                                 "teto de 2.000 por chamada")
    try:
        ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        raise HTTPException(400, "termos: só aceita termo_id numérico")

    def _grava(conn):
        pares, faltam = [], []
        por_id = {r[0]: r[1] for r in conn.execute(
            "SELECT id, cnpj FROM contrato_termo WHERE id IN (%s)"
            % ",".join("?" * len(ids)), ids)}
        for tid in ids:
            doc = por_id.get(tid)
            if doc is None:
                faltam.append({"termo_id": tid, "cnpj": None,
                               "motivo": "o termo não existe nesta base"})
                continue
            pares.append((doc, tid))
        try:
            r = registro.lancar_preco_em_lote(conn, pares, valor, comp, por,
                                              corpo.get("motivo"))
        except registro.DadoInvalido as e:
            raise _recusa(e)
        r["recusados"] = faltam + r["recusados"]
        r["competencia"] = comp
        r["por"] = por
        r["pedidos"] = len(ids)
        return r
    return await _exec(_grava)
