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

from ... import storage
from ..auth import requer_aba
from .. import car_busca as busca
from .. import car_motor as motor
from .. import car_prefatura as prefatura
from .. import car_registro as registro
from .. import car_tabelas as tabelas

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
        return prefatura.montar(conn, comp, cnpj=_resolver_cnpj(conn, bruto))
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
        pre = prefatura.montar(conn, comp, cnpj=doc)
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
    return await _exec(
        lambda conn: {"competencia": comp, "limite": limite,
                      "fila": registro.contratos_sem_valor(conn, comp, limite)})


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
        return prefatura.montar(
            conn, comp, cnpj=_resolver_cnpj(conn, doc) if doc else None)
    return await _exec(_ler)


@router.get("/prefatura.csv", response_class=PlainTextResponse)
async def prefatura_csv(competencia: str | None = Query(None),
                        cnpj: str | None = Query(None)):
    """A mesma pré-fatura, uma linha por linha de cobrança, em CSV."""
    comp = _competencia(competencia)
    doc = (cnpj or "").strip() or None

    def _ler(conn):
        return prefatura.montar(
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
        pre = prefatura.montar(conn, comp, cnpj=doc)
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
