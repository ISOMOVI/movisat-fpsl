"""Rotina do espelho do faturado (`CAR_1.1`, bloco **F1**). 2026-10-30.

Lê o financeiro do Harmonit e grava em `car_faturado`. **Só `GET`** -- a API
financeira do Harmonit é **100% leitura** (varrido no `swagger.json` em 28/10:
não existe rota de criar cobrança, faturar, lançar parcela ou emitir), então
esta rotina não tem como escrever lá nem por acidente.

🚨 NASCE DESLIGADA, com interruptor NA PRÓPRIA TELA -- convenção do FPSL, oposta
à do MoviZap. 🔵 E ela tem o botão que ele pediu em 30/10: *"nasce desligada mas
tbm pode ser feita pelo botão, até que decidam deixar ligada, aí o botão esmaece
ou só pode ser usado mais 1 vez no dia 4hrs após a automática, quando ligada"*.
A régua do botão é `car_faturado.pode_atualizar_agora`, pura e travada por teste.

🚨 DUAS CHAMADAS POR MÊS, e os dois estados importam:
  `ObterMovimentacaoFinanceiraABaixar`  -> o que está em aberto (a cobrar)
  `ObterMovimentacaoFinanceiraBaixados` -> o que já foi pago
Com `tipo=1` (receita) e **sem CNPJ**: o mês inteiro vem numa resposta. Medido em
30/10: 297 lançamentos no vencimento 10/2026, em ~1 s.

⚠️ A **v2** destas rotas recusa esta empresa (*"Este método não atende a sua
empresa, por favor tente novamente em /v1"*, conferido em 30/10) -- e é ela que
traria `competencia` como campo pronto. Por isso a competência sai do TEXTO.

🚨 A AMARRAÇÃO É (CLIENTE, NÚMERO DO CONTRATO), NUNCA O NÚMERO SOLTO. Medido em
30/10 nos vencimentos 09 e 10/2026: dos **544** lançamentos com número de
contrato, **537 (98,7%)** acham termo **do próprio cliente**; sobram **2**
números que não existem nesta base e **5** lançamentos cujo `contatoId` não está
em `clientes`. Procurar o número sem o cliente penduraria dinheiro no contrato de
outra empresa -- é o mesmo cuidado do `_exigir_termo` do `car_registro`.
"""
import asyncio
import logging
import sqlite3
from datetime import date, datetime, timezone

from fastapi import HTTPException

from .. import rotinas, storage
from ..harmonit_client import harmonit_get
from ..painel import car_faturado as cf
from ..painel import car_prefatura as prefatura
from ..painel import car_tabelas as tabelas

logger = logging.getLogger("fpsl.sync_faturado")

FLAG = "faturado_sync_ativa"
CHAVE_MANUAL = "faturado_sync_manual_em"
INTERVALO_ROTINA = 24 * 60 * 60          # 1x/dia, como ele decidiu em 30/10

ROTAS = {
    cf.A_BAIXAR: "/Financeiro/v1/ObterMovimentacaoFinanceiraABaixar",
    cf.BAIXADO: "/Financeiro/v1/ObterMovimentacaoFinanceiraBaixados",
}

COLUNAS = ("id", "tipo", "estado", "competencia", "vencimento", "pagamento",
           "valor", "valor_final", "contato_id", "contato", "cnpj",
           "termo_numero", "termo_id", "numero_os", "numero_venda", "parcela",
           "centro_custo", "categoria", "conta_corrente", "nosso_numero",
           "descricao", "venc_ano_mes", "lido_em")


def _connect():
    conn = sqlite3.connect(storage.DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Resolução de cliente e de contrato ───────────────────────────────────────
def mapa_clientes(conn) -> dict:
    """`contatoId` do Harmonit -> o CNPJ **como esta base o guarda**."""
    return {h: c for h, c in conn.execute(
        "SELECT harmonit_id, cnpjcpf FROM clientes "
        "WHERE cnpjcpf IS NOT NULL AND cnpjcpf <> ''")}


def termos_por_cnpj(conn) -> dict:
    """`cnpj -> [termos]`, o que `resolver_termo` precisa para desempatar."""
    saida: dict = {}
    for tid, cnpj, numero, empresa in conn.execute(
            "SELECT id, cnpj, numero, empresa FROM contrato_termo"):
        saida.setdefault(cnpj, []).append(
            {"id": tid, "cnpj": cnpj, "numero": numero, "empresa": empresa})
    return saida


def resolver(linha: dict, clientes: dict, termos: dict) -> dict:
    """Preenche `cnpj` e `termo_id` na linha já classificada.

    🚨 O TERMO SÓ É PROCURADO DENTRO DO PRÓPRIO CLIENTE, e o desempate entre
    empresas homônimas é o `resolver_termo` da pré-fatura (**MOVISAT vence**) --
    a mesma função, não uma segunda régua.

    O que não resolve fica **NULO**, e a tela mostra a lista. Nulo é "não sei";
    pendurar no contrato errado seria dinheiro no cliente errado.
    """
    cnpj = clientes.get(linha.get("contato_id"))
    termo_id = None
    numero = (linha.get("termo_numero") or "").strip()
    if cnpj and numero:
        achado = prefatura.resolver_termo(termos.get(cnpj) or [], numero)
        if achado:
            termo_id = achado["id"]
    return {**linha, "cnpj": cnpj, "termo_id": termo_id}


def gravar(conn, linhas: list) -> dict:
    """`INSERT OR REPLACE` por `id` do Harmonit. Devolve o que entrou.

    🚨 IDEMPOTENTE POR DESENHO: a chave é o `id` de lá, então reler o mesmo mês
    **substitui** a linha em vez de empilhar cópia. E a releitura é necessária,
    não opcional: um lançamento em aberto vira baixado, e a linha tem de mudar
    de estado sem virar duas.
    """
    agora = _agora()
    sql = (f"INSERT OR REPLACE INTO car_faturado ({', '.join(COLUNAS)}) "
           f"VALUES ({', '.join('?' * len(COLUNAS))})")
    gravadas = sem_cnpj = sem_termo = 0
    for linha in linhas:
        if linha.get("id") is None:
            continue
        conn.execute(sql, tuple(linha.get(c) for c in COLUNAS[:-1]) + (agora,))
        gravadas += 1
        if not linha.get("cnpj"):
            sem_cnpj += 1
        if linha.get("termo_numero") and not linha.get("termo_id"):
            sem_termo += 1
    return {"gravadas": gravadas, "sem_cnpj": sem_cnpj,
            "sem_termo": sem_termo, "lido_em": agora}


# ── A leitura no Harmonit ────────────────────────────────────────────────────
async def ler_mes(ano: int, mes: int) -> tuple:
    """As duas chamadas de um mês de vencimento. Devolve `(linhas, falhas)`.

    ⚠️ Falha de uma das duas rotas **não derruba a passada**: a outra entra e a
    falha é DITA. Espelho pela metade com o aviso é melhor que espelho nenhum --
    e melhor que espelho pela metade em silêncio.
    """
    linhas, falhas = [], []
    for estado, rota in ROTAS.items():
        try:
            r = await harmonit_get(rota, {"anoVencimento": ano,
                                          "mesVencimento": mes, "tipo": 1})
        except HTTPException as exc:
            falhas.append({"ano": ano, "mes": mes, "estado": estado,
                           "erro": str(exc.detail)})
            continue
        bruto = r if isinstance(r, list) else (
            r.get("data") if isinstance(r, dict) else None)
        if not isinstance(bruto, list):
            falhas.append({"ano": ano, "mes": mes, "estado": estado,
                           "erro": "resposta sem lista de lançamentos"})
            continue
        for item in bruto:
            if isinstance(item, dict):
                # A proveniencia e do MES DA CHAMADA, nao do corpo: so quem
                # chamou sabe de que mes de vencimento a resposta veio.
                linhas.append({**cf.classificar(item, estado),
                               "venc_ano_mes": f"{ano}-{mes:02d}"})
    return linhas, falhas


async def run_sync(meses: list | None = None, hoje=None) -> dict:
    """Uma passada: lê os meses, resolve e grava. Não decide nada de cobrança."""
    meses = meses or cf.meses_da_passada(hoje or date.today())

    todas, falhas = [], []
    for ano, mes in meses:
        linhas, f = await ler_mes(ano, mes)
        todas += linhas
        falhas += f

    def _grava():
        with _connect() as conn:
            tabelas.criar(conn)
            tabelas.migrar(conn)
            clientes = mapa_clientes(conn)
            termos = termos_por_cnpj(conn)
            r = gravar(conn, [resolver(l, clientes, termos) for l in todas])
            conn.commit()
            return r
    r = await asyncio.get_running_loop().run_in_executor(None, _grava)

    por_tipo: dict = {}
    for l in todas:
        por_tipo[l["tipo"]] = por_tipo.get(l["tipo"], 0) + 1
    return {"meses": [f"{a}-{m:02d}" for a, m in meses], "lidos": len(todas),
            "por_tipo": por_tipo, "falhas": falhas, **r}


async def loop_sync_faturado():
    """Laço diário. **Relê a flag a cada volta** — ligar não roda na hora."""
    while True:
        # "desligada" é o carimbo honesto da passada que viu a flag em false:
        # laço vivo com rotina parada é uma coisa, laço morto é outra.
        resultado = "desligada"
        try:
            if await storage.get_config(FLAG, "false") == "true":
                r = await run_sync()
                resultado = (f"{r['lidos']} lançamentos, {r['gravadas']} gravados"
                             + (f", {len(r['falhas'])} falhas" if r["falhas"] else ""))
                logger.info("sync_faturado: %s (meses %s, por tipo %s)",
                            resultado, ", ".join(r["meses"]), r["por_tipo"])
        except Exception as exc:
            logger.exception("sync_faturado: falha na rotina periódica")
            resultado = f"ERRO: {exc}"
        await rotinas.marcar("faturado", resultado)
        await asyncio.sleep(INTERVALO_ROTINA)
