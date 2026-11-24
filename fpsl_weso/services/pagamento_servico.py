# -*- coding: utf-8 -*-
"""A varredura que enche a coluna 1 de **Serviço dos Técnicos** — 18/11.

🔵 *"Rotina automatizada visita todas as OS das ultimas 24hrs e vai agrupando os
dados. Cards são gerados por técnico automaticamente. Ex: Encontrou um
agendamento do tec X já haverá card com serviços a pagar - card gerado."*

🚨 **LÊ O CACHE, NÃO O ERP, e isso não é otimização: é a diferença entre custar
zero e custar 79 leituras.** A `os_historico` já guarda `materiais_json`,
`tecnicos_json`, `termo`, `situacao_id` e `data_previsao`, varrida a cada 5 min
pelo `os_scan_router`. O Harmonit esgota o pool de conexões todo dia (46 em
17/11, 164 em 07/11), e uma rotina de madrugada que pedisse OS por OS entraria
na fila junto com o painel da manhã.

🚨 **A UNIDADE É O ARTEFATO**, e não a OS nem o técnico: *(técnico, OS)*. Ver o
`pagamento_tabelas` para o porquê — é o que faz *"os removidos voltam para o
card da primeira coluna"* funcionar de qualquer etapa.

📏 Medido em 18/11, e é o que esta rotina deve reproduzir:

    OS no cache com materiais ................ 633
    com valor de pagamento ou de km .......... 79
    sem técnico de verdade ................... 21
    artefatos, em 8 técnicos ................. 58
    o maior: Franck (tid 14262) .............. 40 OS, R$ 3.430,00 + R$ 933,10

⚠️ **A JANELA DE 24h É DA ROTINA, NÃO DO ARTEFATO.** Ele pediu que a rotina
visite as OS das últimas 24h, e o card acumula (🔵 *"vai fazendo um
histórico"*). Então a varredura diária vê um dia e o card guarda tudo o que já
foi visto -- e o operador escolhe o período no **filtro dentro do card**
(🔵 *"só quero fechar de 16-18/11/26 filtro isso e flego"*).

🚨 E A PRIMEIRA RODADA NÃO PODE OLHAR SÓ 24h, senão nasce com 2 artefatos em vez
de 58 e o histórico começa truncado -- por isso `horas=None` varre tudo o que
está no cache. É o que o ensaio a seco usa.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

# ⚠️ IMPORT ABSOLUTO, como o `services/fechamento.py` vizinho faz: este
# pacote mistura os dois estilos, e seguir o do vizinho é o que evita o
# `ImportError` que o `py_compile` NÃO pega.
from fpsl_weso import storage
from fpsl_weso.painel import pagamento_tabelas
from fpsl_weso.painel.templates_config import (KM_DESLOCAMENTO_ID,
                                               PAGAMENTO_TECNICO_ID)

log = logging.getLogger(__name__)

# 🚨 A Movisat aparece como técnico na OS e NÃO é um: `usuarioId 629` é a
# própria empresa. 🔵 Regra permanente dele, de 18/11. O mesmo número que a
# ponte do agendamento filtra.
EMPRESA_COMO_TECNICO = 629


def _valores_do_corpo(materiais_json) -> tuple[float, float]:
    """Pagamento do técnico e km de deslocamento, do corpo da OS.

    🔵 *"os valores são dos serviços no corpo da OS do deslocamento e pagamento
    do técnico"*.

    ⚠️ MESMA LEITURA do `services/fechamento.py`, e os mesmos dois ids: se um
    dia o cadastro do Harmonit renomear esses produtos, os dois lugares têm de
    mudar juntos -- e há teste que compara os dois.
    """
    pagamento = km = 0.0
    try:
        materiais = json.loads(materiais_json or "[]")
    except (TypeError, ValueError):
        return 0.0, 0.0
    for item in materiais or []:
        if not isinstance(item, dict):
            continue
        pid = item.get("idProduto") or item.get("produtoId")
        bruto = item.get("valorTotal") or item.get("valor") or 0
        try:
            valor = float(bruto or 0)
        except (TypeError, ValueError):
            valor = 0.0
        if pid == PAGAMENTO_TECNICO_ID:
            pagamento += valor
        elif pid == KM_DESLOCAMENTO_ID:
            km += valor
    return pagamento, km


def _tecnico_da_os(tecnicos_json, excluidos: set) -> tuple[int | None, str]:
    """O técnico de verdade da OS. `(None, "")` quando não há.

    🚨 TRÊS COISAS NÃO SÃO TÉCNICO, e as três foram medidas:
      · `usuarioId 629`, que é a **própria empresa** (🔵 18/11);
      · quem está `excluido` no cadastro (10 dos 201 técnicos);
      · a linha sem `usuarioId`.

    ⚠️ E QUANDO NÃO HÁ, O ARTEFATO AINDA ENTRA, com `tecnico_id` nulo. São 21
    OS medidas em 18/11, e são o funil que ele mandou consertar em 11/11 (70 →
    16 → 8). Descartá-las aqui é que seria o defeito: artefato de pagamento que
    some é dinheiro que ninguém cobra nem paga.
    """
    try:
        linhas = json.loads(tecnicos_json or "[]")
    except (TypeError, ValueError):
        return None, ""
    for linha in linhas or []:
        if not isinstance(linha, dict):
            continue
        uid = linha.get("usuarioId")
        if not uid or uid == EMPRESA_COMO_TECNICO or uid in excluidos:
            continue
        return uid, (linha.get("nomeTecnico") or "").strip()
    return None, ""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===========================================================================
# A DATA INICIAL DA ABA 2 — 🔵 D6 e D7 dele, 23/11
# ===========================================================================
# 🔵 *"use 16/11/2026 de inicio para o financeiro, não mexa na data do OP"*, e
# os artefatos anteriores se **escondem, não se apagam**.
#
# 🚨 **CHAVE PRÓPRIA, E NO CONFIG DO FPSL.** Não é a `painel_operacao_desde` do
# Postgres do MoviZap: ele foi explícito em não mexer na data da Operação, e
# compartilhar a chave faria mover uma mover a outra. E mora **aqui** porque
# quem precisa dela primeiro é a VARREDURA, que roda neste lado — a do MoviZap
# o painel nem veria na hora de criar artefato.
#
# 📏 MEDIDO EM 23/11, e ele soube antes de decidir: dos 79 artefatos do
# `fpsl.db`, o corte de 16/11 deixa **2** à vista (OS 17124 do Franck, em
# Validação, e OS 17131 sem técnico, em Movimentação) e esconde **77**.
CHAVE_DESDE = "pagamento_servico_desde"
DESDE_PADRAO = "2026-11-16"


def _iso_da_data(bruto) -> str:
    """`dd/mm/aaaa HH:MM:SS` ou `aaaa-mm-dd...` -> `aaaa-mm-dd`.

    ⚠️ A `data_previsao` do cache e a `data_os` do artefato são TEXTO no
    formato brasileiro, não ISO. Comparar os dois como string daria ordem
    alfabética, que para datas é lixo -- foi a armadilha de 05/11.
    """
    if not bruto:
        return ""
    s = str(bruto).strip()
    if len(s) >= 10 and s[2] == "/" and s[5] == "/":
        return "%s-%s-%s" % (s[6:10], s[3:5], s[0:2])
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return ""


def desde(conn=None) -> str:
    """Desde quando a aba 2 enxerga serviço. 🔵 D6: 16/11/2026, só o owner muda.

    ⚠️ Valor torto no banco NÃO derruba a tela e NÃO vira silêncio: cai no
    padrão e registra. É a mesma régua da `paineis.data_matriz` do MoviZap.
    """
    def _ler(c):
        row = c.execute("SELECT valor FROM config WHERE chave = ?",
                        (CHAVE_DESDE,)).fetchone()
        return (row[0] if row else "") or ""

    valor = _ler(conn) if conn is not None else None
    if valor is None:
        with storage._connect() as c:
            valor = _ler(c)
    if _iso_da_data(valor) == valor and len(valor) == 10:
        return valor
    if valor:
        log.warning("data inicial da aba 2 invalida no config (%r); usando %s",
                    valor, DESDE_PADRAO)
    return DESDE_PADRAO


def definir_desde(valor: str, *, por: str | None = None) -> dict:
    """🔵 *"a data inicial é somente do Owner"*. Quem cobra isso é a rota."""
    iso = _iso_da_data(valor)
    if iso != (valor or "").strip() or len(iso) != 10:
        return {"ok": False,
                "motivo": "a data tem de estar no formato aaaa-mm-dd"}
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        conn.execute(
            "INSERT OR REPLACE INTO config (chave, valor, atualizado_em) "
            "VALUES (?, ?, ?)", (CHAVE_DESDE, iso, _agora()))
        _evento(conn, acao="definir_desde", de=None, para=iso, por=por)
        conn.commit()
    log.info("data inicial da aba 2: %s (por %s)", iso, por)
    return {"ok": True, "desde": iso}


def varrer(*, horas: int | None = 24) -> dict:
    """Uma rodada da varredura. 🚨 NÃO fala com o Harmonit.

    `horas=None` varre o cache inteiro — é o que a primeira rodada precisa, e é
    o modo do ensaio a seco. `horas=24` é o da madrugada.

    Devolve o resumo; os artefatos ficam em `pagamento_artefato`.
    """
    resumo = {"lidas": 0, "com_valor": 0, "novos": 0, "ja_existiam": 0,
              "sem_tecnico": 0, "tecnicos": 0, "sem_orcamento": 0}
    corte = None
    if horas is not None:
        corte = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()

    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        excluidos = {r[0] for r in conn.execute(
            "SELECT tecnico_id FROM tecnicos WHERE excluido = 1").fetchall()}

        sql = ("SELECT numero_os, materiais_json, tecnicos_json, termo, "
               "       data_previsao, situacao_id "
               "  FROM os_historico "
               " WHERE excluida = 0 AND materiais_json IS NOT NULL")
        params: tuple = ()
        if corte is not None:
            # ⚠️ `atualizado_em`, NÃO `visto_em`: `visto_em` é a PRIMEIRA vez
            # que a OS foi vista e é preservado para sempre -- filtrar por ele
            # perderia toda OS antiga que ganhou valor de pagamento hoje.
            sql += " AND atualizado_em >= ?"
            params = (corte,)
        linhas = conn.execute(sql, params).fetchall()

        # 🔵 D6/D7: o corte entra AQUI, e não só na tela. Artefato anterior à
        # data **nem nasce** -- que é o que ele pediu: *"o artefato anterior à
        # data nem nasce"*. Esconder só na tela deixaria a varredura criando
        # linha nova de agosto toda madrugada.
        corte_iso = desde(conn)
        resumo["desde"] = corte_iso
        resumo["antes_da_data"] = 0

        tecnicos_vistos = set()
        for numero, materiais, tecnicos, termo, previsao, _situacao in linhas:
            resumo["lidas"] += 1
            # ⚠️ **SEM DATA NÃO SE DESCARTA**, e esta é decisão minha,
            # declarada: a OS sem `data_previsao` não pode ser PROVADA anterior
            # ao corte, e descartá-la sumiria com dinheiro em silêncio. Ela
            # entra, e o card já diz "sem data". 📏 Medido em 23/11: 0 das 79.
            data_iso = _iso_da_data(previsao)
            if data_iso and data_iso < corte_iso:
                resumo["antes_da_data"] += 1
                continue
            pagamento, km = _valores_do_corpo(materiais)
            if pagamento <= 0 and km <= 0:
                continue
            resumo["com_valor"] += 1
            tid, nome = _tecnico_da_os(tecnicos, excluidos)
            if tid is None:
                resumo["sem_tecnico"] += 1
            else:
                tecnicos_vistos.add(tid)

            # 🚨 JÁ EXISTE? A pergunta é pelo par (técnico, OS), e com
            # `tecnico_id` nulo ela é só pela OS -- no SQLite, NULL não colide
            # com NULL num UNIQUE, então a trava do banco não cobre os 21 sem
            # técnico. Esta consulta cobre.
            if tid is None:
                achado = conn.execute(
                    "SELECT id FROM pagamento_artefato "
                    " WHERE numero_os = ? AND tecnico_id IS NULL",
                    (numero,)).fetchone()
            else:
                achado = conn.execute(
                    "SELECT id FROM pagamento_artefato "
                    " WHERE numero_os = ? AND tecnico_id = ?",
                    (numero, tid)).fetchone()
            if achado:
                # ⚠️ NÃO SE SOBRESCREVE ARTEFATO QUE JÁ ANDOU. O operador pode
                # já ter dado ciente, anexado comprovante ou devolvido com
                # justificativa -- e a varredura da noite seguinte não pode
                # apagar isso. O que o `[ atualizar ]` do card faz é outra
                # coisa, e é pedido explícito.
                resumo["ja_existiam"] += 1
                continue

            # 🚨 O ORÇAMENTO NÃO É DESTE LADO, e por isso nasce NULO aqui.
            # 🔵 Decisão dele: *"o orçamento do MoviZap"* -- a tabela
            # `orcamento`, com numeração nossa, que vive na outra base e liga
            # técnico + lista de OS + total + PDF. A varredura do FPSL não tem
            # como sabê-lo, e **adivinhar seria inventar dado**.
            #
            # ⚠️ Quem o descobre é o MoviZap, cruzando `orcamento.ordens_os`
            # com o `numero_os`, e ele o PERSISTE aqui no `preparar` -- que é o
            # momento em que o número passa a importar de verdade, porque é o
            # que vai para o arquivo do Procfy como "Nº de Documento".
            resumo["sem_orcamento"] += 1
            conn.execute(
                "INSERT INTO pagamento_artefato "
                "  (tecnico_id, tecnico_nome, numero_os, orcamento_numero, "
                "   termo, valor_pagamento, valor_km, data_os, coluna, "
                "   semaforo, criado_em, atualizado_em) "
                "VALUES (?, ?, ?, NULL, ?, ?, ?, ?, 'movimentacao', NULL, ?, ?)",
                (tid, nome or None, numero, termo, pagamento, km, previsao,
                 _agora(), _agora()))
            resumo["novos"] += 1

        resumo["tecnicos"] = len(tecnicos_vistos)
        conn.commit()
    log.info("varredura de pagamento: %s", resumo)
    return resumo


def quadro() -> dict:
    """As cinco colunas, com os cards e os artefatos. Somente leitura."""
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        cols = ("id", "tecnico_id", "tecnico_nome", "numero_os",
                "orcamento_numero", "termo", "valor_pagamento", "valor_km",
                "data_os", "coluna", "lote_id", "semaforo", "situacao_do_erp",
                "etapa_nossa", "ciente_em", "justificativa", "devolvido_em",
                "datascope_form_state", "comprovante_arquivo",
                "valor_do_comprovante", "comprovante_dispensa")
        linhas = [dict(zip(cols, r)) for r in conn.execute(
            "SELECT %s FROM pagamento_artefato ORDER BY tecnico_id, numero_os"
            % ", ".join(cols)).fetchall()]

        # 🔵 D7: os anteriores à data se **ESCONDEM, não se apagam**. Nada sai
        # do `fpsl.db`; trocando a data, voltam.
        #
        # 🚨 **O CORTE VALE SÓ NA MOVIMENTAÇÃO.** Em lote já formado, não --
        # e o motivo é o mesmo que esta tela já escreveu sobre o filtro de
        # período: *"o lote já foi fechado, e peneirá-lo por data esconderia
        # parte de um pagamento que vai sair inteiro"*. Esconder metade de um
        # lote faria o total da tela discordar do arquivo do Procfy.
        #
        # ⚠️ E artefato SEM data fica, pelo mesmo motivo da varredura: não se
        # prova anterior ao corte, e sumir com ele perderia dinheiro calado.
        corte_iso = desde(conn)
        escondidos = 0
        a_mostrar = []
        for a in linhas:
            if a["coluna"] == "movimentacao":
                d = _iso_da_data(a.get("data_os"))
                if d and d < corte_iso:
                    escondidos += 1
                    continue
            a_mostrar.append(a)
        linhas = a_mostrar

        # 🔵 19/11: os dados da OS no artefato -- *"faltam várias coisas (...)
        # como a aba1 apresenta"*. 🚨 O card da aba 1 mostra cliente, tipo e
        # status; o da aba 2 mostrava só OS, termo e valor, e nenhum estilo
        # conserta campo que o servidor não manda.
        #
        # 🚨 JOIN NA LEITURA, NÃO COLUNA NOVA: o dono deste fato é o
        # `os_historico`, que a varredura relê. Copiá-lo para o artefato faria
        # dois donos do mesmo dado -- e um retrato velho no dia em que a OS
        # trocasse de status. ⚠️ Sem coluna nova não há migração.
        #
        # ⚠️ O NOME DO CLIENTE DÁ TRÊS SALTOS porque a `clientes` não o guarda:
        # cliente_id -> clientes.cnpjcpf -> contrato_cliente.cnpj -> nome.
        # 📏 Medido em 19/11: 65 dos 79 artefatos resolvem nome. Os outros a
        # tela DIZ, com a frase da aba 1 ("fora do nosso cadastro").
        dados_da_os: dict = {}
        if linhas:
            numeros = sorted({a["numero_os"] for a in linhas})
            lacunas = ",".join("?" * len(numeros))
            for r in conn.execute(
                    "SELECT h.numero_os, h.cliente_id, cc.nome, t.nome, "
                    "       h.status_str, h.situacao_id, h.n_oficinas "
                    "  FROM os_historico h "
                    "  LEFT JOIN clientes cl ON cl.harmonit_id = h.cliente_id "
                    "  LEFT JOIN contrato_cliente cc ON cc.cnpj = cl.cnpjcpf "
                    "  LEFT JOIN tipos_os t ON t.tipo_id = h.tipo "
                    " WHERE h.numero_os IN (%s)" % lacunas, numeros).fetchall():
                dados_da_os[r[0]] = {
                    "cliente_id": r[1], "cliente": r[2], "tipo_nome": r[3],
                    "status_str": r[4], "situacao_id_os": r[5],
                    "n_oficinas": r[6],
                }
        for a in linhas:
            # ⚠️ AUSENTE É AUSENTE: a OS que não está mais no cache entra com
            # os campos nulos, e não com cadeia vazia -- nulo quer dizer "não
            # medido", e a tela sabe dizer isso.
            a.update(dados_da_os.get(a["numero_os"]) or {
                "cliente_id": None, "cliente": None, "tipo_nome": None,
                "status_str": None, "situacao_id_os": None,
                "n_oficinas": None})

    # 🚨 O CARD DA COLUNA 1 É POR TÉCNICO E PERMANENTE (🔵 decisão dele); os das
    # outras colunas são LOTES. Por isso o agrupamento é diferente nas duas, e
    # não é inconsistência: é o desenho dele.
    por_tecnico: dict = {}
    for a in linhas:
        if a["coluna"] != "movimentacao":
            continue
        chave = a["tecnico_id"] or 0
        card = por_tecnico.setdefault(chave, {
            "tecnico_id": a["tecnico_id"],
            # ⚠️ O card dos 21 sem técnico DIZ o que é, não fica sem nome.
            "tecnico_nome": a["tecnico_nome"] or (
                "sem técnico identificado" if not a["tecnico_id"] else None),
            "artefatos": [], "total_pagamento": 0.0, "total_km": 0.0,
            # 🚨 Sem técnico não há a quem pagar: o card existe para o dinheiro
            # não sair de vista, e não para avançar.
            "pode_preparar": bool(a["tecnico_id"]),
        })
        card["artefatos"].append(a)
        card["total_pagamento"] += a["valor_pagamento"] or 0
        card["total_km"] += a["valor_km"] or 0

    lotes: dict = {}
    for a in linhas:
        if a["coluna"] == "movimentacao":
            continue
        lotes.setdefault(a["lote_id"], {"lote_id": a["lote_id"],
                                        "coluna": a["coluna"],
                                        "tecnico_id": a["tecnico_id"],
                                        "tecnico_nome": a["tecnico_nome"],
                                        "artefatos": []})
        lotes[a["lote_id"]]["artefatos"].append(a)

    colunas = []
    for nome in pagamento_tabelas.COLUNAS:
        if nome == "movimentacao":
            cards = sorted(por_tecnico.values(),
                           key=lambda c: -len(c["artefatos"]))
        else:
            cards = [l for l in lotes.values() if l["coluna"] == nome]
        colunas.append({"chave": nome, "cards": cards, "total": len(cards)})
    # 🚨 A TELA TEM DE DIZER O CORTE E O QUE ELE ESCONDEU. Contagem que cai de
    # 79 para 2 sem explicação é a tela mentindo por omissão -- e foi assim que
    # o "sumiço" de 19/11 pareceu defeito. 🔵 É a régua do `M12`.
    return {"colunas": colunas, "artefatos": len(linhas),
            "desde": corte_iso, "escondidos_pela_data": escondidos}


# ===========================================================================
# OS GESTOS DAS CINCO COLUNAS
# ===========================================================================
# 🚨 TODO GESTO GRAVA EVENTO, e isto não é zelo: este fluxo move dinheiro e
# avisa gente de fora da empresa (a correção no DataScope dispara os webhooks
# deles e manda push ao técnico). 🔵 *"deve ter o log de quem faz o que
# SEMPRE"* é régua dele desde 29/10.
#
# ⚠️ E O EVENTO É GRAVADO NA MESMA TRANSAÇÃO do gesto: gravar depois deixaria
# gesto sem log quando algo estourasse no meio -- e log que falta é pior que
# log nenhum, porque dá a impressão de que nada aconteceu.


def _evento(conn, *, artefato_id=None, lote_id=None, acao, de=None, para=None,
            detalhe=None, por=None) -> None:
    conn.execute(
        "INSERT INTO pagamento_evento "
        "  (artefato_id, lote_id, acao, de, para, detalhe, por, em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (artefato_id, lote_id, acao, de, para, detalhe, por, _agora()))


ARTEFATO_COLS = (
    "id", "tecnico_id", "tecnico_nome", "numero_os", "orcamento_numero",
    "termo", "valor_pagamento", "valor_km", "data_os", "coluna", "lote_id",
    "semaforo", "situacao_do_erp", "etapa_nossa", "ciente_em",
    "justificativa", "datascope_form_state", "comprovante_arquivo",
    "valor_do_comprovante", "comprovante_dispensa")


def _artefato(conn, artefato_id: int) -> dict | None:
    linha = conn.execute(
        "SELECT %s FROM pagamento_artefato WHERE id = ?"
        % ", ".join(ARTEFATO_COLS), (artefato_id,)).fetchone()
    return dict(zip(ARTEFATO_COLS, linha)) if linha else None


def preparar(artefatos: list[dict], *, por: str | None = None) -> dict:
    """🔵 *"Os itens flegados e clicados em preparar, vão gerar novo card do
    técnico, agora preparando para pagamento."*

    `artefatos` são `{"id": .., "orcamento_numero": .. | None}` — 🚨 o número do
    orçamento vem do MoviZap, que é o dono dele, e é **aqui** que ele se torna
    persistente: é o que vai ao arquivo do Procfy como *"Nº de Documento"*.

    🚨 **UM LOTE POR TÉCNICO**, e não um por clique: 🔵 o card da coluna 2 é
    *"novo card do técnico"*. Marcar artefatos de dois técnicos num clique gera
    dois lotes, porque pagamento é por pessoa.

    ⚠️ **ARTEFATO SEM TÉCNICO NÃO PREPARA.** Sem técnico não há a quem pagar, e
    o card deles existe para o dinheiro não sair de vista -- não para avançar.
    São os 21 medidos em 18/11, R$ 2.581,90.
    """
    feito = {"lotes": [], "preparados": 0, "recusados": []}
    if not artefatos:
        return feito
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        por_tecnico: dict = {}
        for entrada in artefatos:
            a = _artefato(conn, int(entrada.get("id") or 0))
            if not a:
                feito["recusados"].append(
                    {"id": entrada.get("id"), "porque": "artefato nao existe"})
                continue
            if a["coluna"] != "movimentacao":
                # ⚠️ Já saiu da coluna 1: preparar de novo o duplicaria em dois
                # lotes, e o mesmo serviço seria pago duas vezes.
                feito["recusados"].append(
                    {"id": a["id"], "numero_os": a["numero_os"],
                     "porque": "ja esta na coluna " + str(a["coluna"])})
                continue
            if not a["tecnico_id"]:
                feito["recusados"].append(
                    {"id": a["id"], "numero_os": a["numero_os"],
                     "porque": "sem tecnico identificado na OS, nao ha a quem "
                               "pagar"})
                continue
            por_tecnico.setdefault(a["tecnico_id"], []).append(
                (a, entrada.get("orcamento_numero")))

        for tid, itens in por_tecnico.items():
            nome = itens[0][0]["tecnico_nome"]
            lote = conn.execute(
                "INSERT INTO pagamento_lote "
                "  (tecnico_id, tecnico_nome, coluna, criado_em, criado_por, "
                "   atualizado_em) "
                "VALUES (?, ?, 'preparacao', ?, ?, ?)",
                (tid, nome, _agora(), por, _agora()))
            lote_id = lote.lastrowid
            feito["lotes"].append(lote_id)
            for a, orcamento in itens:
                conn.execute(
                    "UPDATE pagamento_artefato "
                    "   SET coluna = 'preparacao', lote_id = ?, "
                    "       orcamento_numero = COALESCE(?, orcamento_numero), "
                    # 🚨 O semáforo volta a NULO: a coluna 2 ainda não conferiu
                    # nada, e deixar a cor da coluna anterior faria a tela
                    # afirmar uma conferência que não houve.
                    "       semaforo = NULL, situacao_do_erp = NULL, "
                    "       etapa_nossa = NULL, ciente_em = NULL, "
                    "       ciente_por = NULL, justificativa = NULL, "
                    "       atualizado_em = ? "
                    " WHERE id = ?",
                    (lote_id, orcamento, _agora(), a["id"]))
                _evento(conn, artefato_id=a["id"], lote_id=lote_id,
                        acao="preparar", de="movimentacao", para="preparacao",
                        detalhe=("orcamento " + str(orcamento) if orcamento
                                 else "sem orcamento"), por=por)
                feito["preparados"] += 1
        conn.commit()
    return feito


def situacao_para_conferir(artefato_id: int, *, etapas_nossas=None) -> dict:
    """O que a coluna 2 mostra para o operador dar ciente, um a um.

    🔵 *"A preparação vai trazer essas situações a tela e exibir para o operador
    confirmar 1 a 1 na tela modal que abrir."*

    🚨 **PORTA DUPLA, e é o conserto do funil que ele mandou medir em 11/11.**
    *"Serviço Realizado"* é **etapa NOSSA** (a 2322, que vive no MoviZap), e as
    outras três são situações do Harmonit. O Fechamento antigo exigia **só** a
    15694 -- e foi isso que derrubou 70 OS para 16, e 16 para 8.

    `etapas_nossas` é o conjunto de OS que o MoviZap diz estarem na etapa 2322:
    só ele sabe, porque a etapa é dele. ⚠️ Vazio quer dizer *"o MoviZap não
    informou"*, e não *"nenhuma OS está lá"* -- por isso a porta do ERP continua
    valendo sozinha.
    """
    etapas_nossas = set(etapas_nossas or ())
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        a = _artefato(conn, artefato_id)
        if not a:
            return {"ok": False, "motivo": "artefato nao existe"}
        linha = conn.execute(
            "SELECT situacao_id FROM os_historico WHERE numero_os = ?",
            (a["numero_os"],)).fetchone()
        situacao = linha[0] if linha else None
        na_etapa_nossa = a["numero_os"] in etapas_nossas
        libera = (situacao in pagamento_tabelas.SITUACOES_QUE_LIBERAM
                  or na_etapa_nossa)
        conn.execute(
            "UPDATE pagamento_artefato SET situacao_do_erp = ?, "
            "       etapa_nossa = ?, semaforo = ?, atualizado_em = ? "
            " WHERE id = ?",
            (situacao, 1 if na_etapa_nossa else 0,
             "verde" if libera else "amarelo", _agora(), artefato_id))
        conn.commit()
    return {"ok": True, "numero_os": a["numero_os"],
            "situacao_do_erp": situacao, "etapa_nossa": na_etapa_nossa,
            "libera": libera,
            # 🚨 A frase diz O QUE FOI LIDO, não só a cor: cor sozinha não é
            # portadora de informação, e aqui a decisão é do operador.
            "motivo": ("a OS esta numa situacao que libera o pagamento"
                       if libera else
                       "a OS esta na situacao " + str(situacao) + ", que nao e "
                       "uma das quatro que liberam o pagamento")}


def dar_ciente(artefato_id: int, *, por: str | None = None) -> dict:
    """🔵 *"Dando ciência das etapas que estiver"*. O operador assume a leitura.

    ⚠️ CIENTE NÃO É APROVAÇÃO AUTOMÁTICA: ele pode dar ciente de uma situação
    que **não** libera, e seguir. É a decisão dele, e o log guarda qual era a
    situação no momento -- senão ninguém saberia depois do que a pessoa estava
    ciente.
    """
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        a = _artefato(conn, artefato_id)
        if not a:
            return {"ok": False, "motivo": "artefato nao existe"}
        conn.execute(
            "UPDATE pagamento_artefato SET ciente_em = ?, ciente_por = ?, "
            "       atualizado_em = ? WHERE id = ?",
            (_agora(), por, _agora(), artefato_id))
        _evento(conn, artefato_id=artefato_id, lote_id=a["lote_id"],
                acao="ciente", de=a["coluna"], para=a["coluna"],
                detalhe=("situacao " + str(a["situacao_do_erp"])
                         + ", etapa nossa=" + str(a["etapa_nossa"])), por=por)
        conn.commit()
    return {"ok": True}


def devolver(artefato_id: int, justificativa: str, *,
             por: str | None = None) -> dict:
    """🔵 *"é possível clicar em remover, onde o item de pagamento será removido
    e devolvido ao card na coluna de Movimentação abrindo um campo de
    justificativa"*, e 🔵 *"agora tem a cor laranja"*.

    🚨 **SEMPRE PARA A COLUNA 1, nunca para a anterior.** 🔵 Ele foi explícito
    na coluna 3: *"veja que aqui não retorna para a anterior e sim para o 1"*.

    ⚠️ **SEM JUSTIFICATIVA NÃO SE DEVOLVE.** Devolver calado deixaria o artefato
    laranja no card e ninguém saberia por quê -- e laranja sem motivo é cor sem
    informação.
    """
    texto = (justificativa or "").strip()
    if not texto:
        return {"ok": False,
                "motivo": "devolver exige a justificativa: sem ela o artefato "
                          "fica laranja no card e ninguem sabe por que"}
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        a = _artefato(conn, artefato_id)
        if not a:
            return {"ok": False, "motivo": "artefato nao existe"}
        if a["coluna"] == "movimentacao":
            return {"ok": False,
                    "motivo": "este artefato ja esta na Movimentacao"}
        conn.execute(
            "UPDATE pagamento_artefato "
            "   SET coluna = 'movimentacao', lote_id = NULL, "
            "       semaforo = 'laranja', justificativa = ?, "
            "       devolvido_em = ?, devolvido_por = ?, "
            # ⚠️ O ciente e a conferência SAEM: o artefato volta para o começo,
            # e manter o ciente faria a próxima preparação herdar uma
            # confirmação dada sobre outro estado.
            "       ciente_em = NULL, ciente_por = NULL, atualizado_em = ? "
            " WHERE id = ?",
            (texto, _agora(), por, _agora(), artefato_id))
        _evento(conn, artefato_id=artefato_id, lote_id=a["lote_id"],
                acao="devolver", de=a["coluna"], para="movimentacao",
                detalhe=texto, por=por)
        conn.commit()
    return {"ok": True, "de": a["coluna"], "para": "movimentacao"}


def devolver_lote(lote_id: int, justificativa: str, *,
                  por: str | None = None) -> dict:
    """🔵 *"Excluir o card inteiro devolvendo tudo à coluna 1, com
    justificativa única"* -- tarefa 2.4.

    🚨 **CHAMA O `devolver` DE UM, ARTEFATO POR ARTEFATO**, e isto é o ponto:
    o que acontece com cada um (coluna 1, laranja, justificativa, ciente
    apagado) é regra dele, já escrita e já travada. Repetir o UPDATE aqui
    criaria uma segunda verdade que divergiria na primeira mudança -- foi
    exatamente o que o `operacoes_retirada` do FPSL existe para evitar.

    ⚠️ **A JUSTIFICATIVA É UMA, e vai em TODOS:** é o pedido dele. Cada
    artefato guarda o mesmo texto, porque é o artefato que o mostra laranja no
    card da coluna 1 -- guardar só no lote deixaria os itens laranjas e mudos.

    ⚠️ **O LOTE FICA**, como registro, e sai do quadro sozinho: `colunas()`
    monta os cards a partir dos artefatos, então lote sem artefato não
    aparece. Apagar a linha perderia o rastro de que ele existiu.
    """
    texto = (justificativa or "").strip()
    if not texto:
        return {"ok": False,
                "motivo": "excluir o card exige a justificativa: ela vai em "
                          "todos os itens, e laranja sem motivo e cor sem "
                          "informacao"}
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        lote = conn.execute(
            "SELECT id, coluna FROM pagamento_lote WHERE id = ?",
            (lote_id,)).fetchone()
        if not lote:
            return {"ok": False, "motivo": "lote nao existe"}
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM pagamento_artefato "
            " WHERE lote_id = ? AND coluna <> 'movimentacao' "
            " ORDER BY id", (lote_id,)).fetchall()]
        de = lote[1]
    if not ids:
        # ⚠️ Não é erro: o card já está vazio, e dizer isso é melhor que um
        # "ok" que não mexeu em nada.
        return {"ok": False, "devolvidos": 0,
                "motivo": "este lote nao tem item para devolver"}

    devolvidos, recusados = [], []
    for artefato_id in ids:
        r = devolver(artefato_id, texto, por=por)
        (devolvidos if r.get("ok") else recusados).append(
            artefato_id if r.get("ok") else (artefato_id, r.get("motivo")))

    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        # 🚨 O EVENTO DO LOTE, além do de cada artefato: é o que responde
        # depois *"quem esvaziou este lote, e por quê?"*. Sem ele, a resposta
        # estaria espalhada em N linhas de artefato.
        _evento(conn, artefato_id=None, lote_id=lote_id,
                acao="devolver_lote", de=de, para="movimentacao",
                detalhe="%d item(ns): %s" % (len(devolvidos), texto), por=por)
        conn.commit()
    return {"ok": bool(devolvidos), "devolvidos": len(devolvidos),
            "recusados": recusados, "de": de, "para": "movimentacao"}


def auditar(lote_id: int, *, por: str | None = None) -> dict:
    """🔵 *"O botão no card será de 'Auditar' que irá mover o card somente com
    os cientes de situação e não negados para a próxima coluna."*

    🚨 **SÓ OS CIENTES ANDAM.** Quem não recebeu ciente **fica** na coluna 2 --
    não é devolvido nem avança. ⚠️ Devolver automaticamente seria decidir pelo
    operador, e avançar sem ciente seria pagar sem ninguém ter olhado.
    """
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        lote = conn.execute(
            "SELECT id, tecnico_id, tecnico_nome, coluna FROM pagamento_lote "
            " WHERE id = ?", (lote_id,)).fetchone()
        if not lote:
            return {"ok": False, "motivo": "lote nao existe"}
        if lote[3] != "preparacao":
            return {"ok": False,
                    "motivo": "este lote esta em " + str(lote[3])
                              + ", nao em preparacao"}
        cientes = [r[0] for r in conn.execute(
            "SELECT id FROM pagamento_artefato "
            " WHERE lote_id = ? AND coluna = 'preparacao' "
            "   AND ciente_em IS NOT NULL", (lote_id,)).fetchall()]
        ficaram = conn.execute(
            "SELECT COUNT(*) FROM pagamento_artefato "
            " WHERE lote_id = ? AND coluna = 'preparacao' "
            "   AND ciente_em IS NULL", (lote_id,)).fetchone()[0]
        if not cientes:
            return {"ok": False, "avancaram": 0, "ficaram": ficaram,
                    "motivo": "nenhum artefato deste lote tem ciente, entao "
                              "nao ha o que auditar"}
        for aid in cientes:
            conn.execute(
                "UPDATE pagamento_artefato SET coluna = 'validacao', "
                "       semaforo = NULL, atualizado_em = ? WHERE id = ?",
                (_agora(), aid))
            _evento(conn, artefato_id=aid, lote_id=lote_id, acao="auditar",
                    de="preparacao", para="validacao", por=por)
        if ficaram:
            # 🚨 O QUE FICOU CONTINUA EXISTINDO, e num lote próprio: o lote
            # antigo avança e os sem ciente precisam de um card para continuar
            # na coluna 2. Sem isto eles ficariam órfãos de card, visíveis em
            # nenhuma coluna.
            novo = conn.execute(
                "INSERT INTO pagamento_lote "
                "  (tecnico_id, tecnico_nome, coluna, criado_em, criado_por, "
                "   atualizado_em) VALUES (?, ?, 'preparacao', ?, ?, ?)",
                (lote[1], lote[2], _agora(), por, _agora()))
            conn.execute(
                "UPDATE pagamento_artefato SET lote_id = ? "
                " WHERE lote_id = ? AND coluna = 'preparacao'",
                (novo.lastrowid, lote_id))
        conn.execute(
            "UPDATE pagamento_lote SET coluna = 'validacao', "
            "       atualizado_em = ? WHERE id = ?", (_agora(), lote_id))
        conn.commit()
    return {"ok": True, "avancaram": len(cientes), "ficaram": ficaram}


# ===========================================================================
# COLUNA 3 — VALIDAÇÃO: o DataScope, o comprovante e o semáforo dos valores
# ===========================================================================

def datascope_do_artefato(artefato_id: int) -> dict:
    """A situação que está no DataScope para a OS deste artefato.

    🔵 *"fará a validação com o Datascope, trazendo a situação que estiver la"*.

    ⚠️ LÊ O CACHE (`datascope_respostas`, 175 linhas), não a API: a chave e o
    cliente são do FPSL e a sincronização já roda. 🚨 E `None` quer dizer
    **"sem registro no DataScope para esta OS"**, que é diferente de "o técnico
    não preencheu" -- a `conferencia_fechamento` já usava essa frase exata, e
    repetir a frase é o que evita duas leituras do mesmo fato.
    """
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        a = _artefato(conn, artefato_id)
        if not a:
            return {"ok": False, "motivo": "artefato nao existe"}
        linha = conn.execute(
            "SELECT form_state, updated_at FROM datascope_respostas "
            " WHERE numero_os = ? ORDER BY updated_at DESC LIMIT 1",
            (a["numero_os"],)).fetchone()
        estado = linha[0] if linha else None
        conn.execute(
            "UPDATE pagamento_artefato SET datascope_form_state = ?, "
            "       datascope_lido_em = ?, atualizado_em = ? WHERE id = ?",
            (estado, _agora(), _agora(), artefato_id))
        conn.commit()
    return {"ok": True, "numero_os": a["numero_os"], "form_state": estado,
            "motivo": (("o DataScope diz: " + estado) if estado
                       else "sem registro no DataScope para esta OS")}


def guardar_comprovante(artefato_id: int, *, arquivo: str | None,
                        valor: float | None, dispensa: str | None = None,
                        por: str | None = None) -> dict:
    """🔵 *"haverá campo para que em cada 1 dos artefatos de pagamento seja
    inserido anexo que comprove o pagamento. Após o envio do anexo, abre o
    campo que pede o valor inserido no documento depois de enviado, já faz a
    conferência completa dos valores a receber e destaca as diferenças."*

    🔵 E a dispensa: *"avança com os que tiveram ou arquivo enviado ou
    justificativa escrita na tela de envio de anexo (pode não ter)"*.

    🚨 **UM DOS DOIS É OBRIGATÓRIO.** Sem arquivo e sem justificativa de
    dispensa, não há o que registrar -- e deixar passar vazio faria a coluna 4
    gerar arquivo de pagamento sobre nada.
    """
    arquivo = (arquivo or "").strip() or None
    dispensa = (dispensa or "").strip() or None
    if not arquivo and not dispensa:
        return {"ok": False,
                "motivo": "e preciso o comprovante OU a justificativa de "
                          "quem nao tem: sem um dos dois, nao ha o que "
                          "registrar"}
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        a = _artefato(conn, artefato_id)
        if not a:
            return {"ok": False, "motivo": "artefato nao existe"}
        conn.execute(
            "UPDATE pagamento_artefato SET comprovante_arquivo = ?, "
            "       valor_do_comprovante = ?, comprovante_dispensa = ?, "
            "       semaforo = ?, atualizado_em = ? WHERE id = ?",
            (arquivo, valor, dispensa,
             semaforo_do_valor(a["valor_pagamento"], a["valor_km"], valor,
                               tem_comprovante=bool(arquivo)),
             _agora(), artefato_id))
        _evento(conn, artefato_id=artefato_id, lote_id=a["lote_id"],
                acao="comprovante", detalhe=(arquivo or ("dispensa: "
                                                         + str(dispensa))),
                para=(str(valor) if valor is not None else None), por=por)
        conn.commit()
    return {"ok": True, "semaforo": semaforo_do_valor(
        a["valor_pagamento"], a["valor_km"], valor,
        tem_comprovante=bool(arquivo))}


# 🚨 Um centavo de folga, e ela existe porque os valores vêm de duas origens:
# os nossos saem de `valorTotal` do corpo da OS (float) e o do recibo é
# digitado. Sem a folga, 120.00 contra 119.999999 viraria divergência.
FOLGA = 0.01


def semaforo_do_valor(pagamento, km, do_comprovante, *,
                      tem_comprovante: bool) -> str:
    """🔵 O semáforo dos valores, com as três regras dele:

    | cor | regra dele |
    |---|---|
    | 🟢 verde | *"conformidade"* -- o recibo bate com os serviços |
    | 🟡 amarelo | *"divergências ou ausências"* |
    | 🔴 vermelho | *"valor a pagar maior que recibo"* |

    ⚠️ AUSÊNCIA É AMARELO, e por isso `tem_comprovante` entra: dispensa escrita
    sem arquivo é ausência, não conformidade. 🚨 E vermelho é só **um** sentido
    -- a pagar MAIOR que o recibo. O contrário (recibo maior) é amarelo: é
    divergência, e não um pagamento a descoberto.
    """
    nosso = float(pagamento or 0) + float(km or 0)
    if do_comprovante is None or not tem_comprovante:
        return "amarelo"
    recibo = float(do_comprovante)
    if abs(nosso - recibo) <= FOLGA:
        return "verde"
    if nosso > recibo:
        return "vermelho"
    return "amarelo"


def revalidar(lote_id: int, *, etapas_nossas=None,
              por: str | None = None) -> dict:
    """🔵 *"todos os cards tem botão de 'atualizar' para rodar novamente as
    verificações daquele card, caso algum ajuste tenha sido feito depos que ele
    nasceu e tbm roda automaticamente a cada etapa, validando os envolvidos no
    card."*

    🚨 **NÃO MOVE NADA, e isto é o ponto.** Ele relê a situação da OS, a
    situação do DataScope e recalcula o semáforo dos valores -- e deixa o
    artefato onde está. Mover aqui seria decidir pelo operador, e o botão que
    ele pediu é de *atualizar*, não de avançar.

    ⚠️ O CIENTE SOBREVIVE: o operador já olhou, e a releitura não apaga a
    assinatura dele. O que muda é o que a tela mostra ao lado.
    """
    etapas_nossas = set(etapas_nossas or ())
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM pagamento_artefato WHERE lote_id = ?",
            (lote_id,)).fetchall()]
    if not ids:
        return {"ok": False, "motivo": "este lote nao tem artefato"}
    feito = {"ok": True, "revalidados": 0, "liberam": 0, "verdes": 0}
    for aid in ids:
        r = situacao_para_conferir(aid, etapas_nossas=etapas_nossas)
        if r.get("libera"):
            feito["liberam"] += 1
        datascope_do_artefato(aid)
        with storage._connect() as conn:
            a = _artefato(conn, aid)
            cor = semaforo_do_valor(
                a["valor_pagamento"], a["valor_km"], a["valor_do_comprovante"],
                tem_comprovante=bool(a["comprovante_arquivo"]))
            # 🚨 Na coluna 3 a cor que vale é a DO VALOR; na 2 é a da situação.
            # ⚠️ Sobrescrever a da situação na coluna 2 apagaria a leitura que o
            # operador está conferindo naquele momento.
            if a["coluna"] in ("validacao", "procfy", "enviado"):
                conn.execute(
                    "UPDATE pagamento_artefato SET semaforo = ?, "
                    "       atualizado_em = ? WHERE id = ?",
                    (cor, _agora(), aid))
                if cor == "verde":
                    feito["verdes"] += 1
            _evento(conn, artefato_id=aid, lote_id=lote_id, acao="revalidar",
                    para=cor, por=por)
            conn.commit()
        feito["revalidados"] += 1
    return feito


# ===========================================================================
# COLUNA 4 — PROCFY: o arquivo
# ===========================================================================
# 🔵 *"Os cards clicados em montar arquivo, serão gerados e dentro deles um
# resumo dos artefatos que vão para pagamento e disponibiliza o arquivo de cada
# card - ou seja de cada técnico."*
#
# 📏 O modelo (`modelo_importacao_procfy.xlsx`) tem **14 colunas e ZERO linhas
# de exemplo** -- só o cabeçalho. A ordem abaixo é a dele, lida do arquivo.
PROCFY_COLUNAS = (
    "Tipo de Lançamento", "Data de pagamento", "Data de competência",
    "Descrição", "Valor", "Categoria", "Recebido de/Pago a", "Pago?",
    "Observações", "Contas bancárias",
    "Número de Documento / Nosso número", "Modo de pagamento",
    "Centro de Custo", "Tags (Por Marcação)")

# 🔵 OS QUATRO QUE SÃO DO CADASTRO DO PROCFY — e **o arquivo é gerado mesmo
# com eles em branco**, por decisão dele de 18/11:
#
#   🔵 *"pode gerar com elas em branco nesse momento, pois podem preencher a
#   mão por informação confidencial ou depois nos passar"*.
#
# ⚠️ ISTO REVERTE O QUE EU TINHA ESCRITO. Eu havia travado a geração enquanto
# os quatro estivessem vazios, com o argumento de que *"arquivo que o Procfy
# recusa é pior que arquivo nenhum"*. O argumento ignorava duas coisas que só
# ele sabia: os valores podem ser **confidenciais** (conta bancária, centro de
# custo), e quem importa consegue preencher na planilha. Travar não protegia
# ninguém -- só impedia o trabalho.
#
# 🚨 O QUE FICA DA PREOCUPAÇÃO: o arquivo sai, e a resposta **diz quais colunas
# saíram em branco**. A tela mostra isso ao lado do botão de baixar. Gerar
# calado é que seria `M12` -- quem importasse descobriria na recusa do Procfy,
# e não aqui.
PROCFY_CONFIG = ("procfy_categoria", "procfy_conta_bancaria",
                 "procfy_modo_pagamento", "procfy_centro_de_custo")
PROCFY_CONFIG_OPCIONAL = ("procfy_tags",)

# ⚠️ O NOME DA COLUNA, para o aviso falar a língua da planilha dele e não a do
# nosso `/config`: quem lê o aviso vai preencher no Excel, e lá a coluna se
# chama "Categoria", não `procfy_categoria`.
COLUNA_DA_CONFIG = {
    "procfy_categoria": "Categoria",
    "procfy_conta_bancaria": "Contas bancárias",
    "procfy_modo_pagamento": "Modo de pagamento",
    "procfy_centro_de_custo": "Centro de Custo",
    "procfy_tags": "Tags (Por Marcação)",
}

# 🚨 Constantes que são NOSSAS e não dele: o lançamento é despesa, e sai não
# pago -- quem marca como pago é o Procfy depois da conciliação.
PROCFY_TIPO = "Despesa"
PROCFY_PAGO = "Não"


def _data_br(texto) -> str:
    """A data no formato que o Procfy lê. ⚠️ A `data_previsao` do cache vem
    `dd/mm/aaaa HH:MM:SS`; o arquivo quer só a data."""
    if not texto:
        return ""
    bruto = str(texto).strip()
    return bruto.split(" ")[0] if " " in bruto else bruto


def linhas_do_procfy(lote_id: int, config: dict) -> dict:
    """As linhas do arquivo, uma por artefato. 🚨 NÃO escreve nada.

    ⚠️ Separado de quem grava de propósito: é o que permite a tela mostrar o
    resumo antes de gerar, e o teste conferir o conteúdo sem mexer no banco.
    """
    faltando = [c for c in PROCFY_CONFIG if not (config.get(c) or "").strip()]
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        lote = conn.execute(
            "SELECT tecnico_nome, coluna FROM pagamento_lote WHERE id = ?",
            (lote_id,)).fetchone()
        if not lote:
            return {"ok": False, "motivo": "lote nao existe"}
        artefatos = [dict(zip(ARTEFATO_COLS, r)) for r in conn.execute(
            "SELECT %s FROM pagamento_artefato WHERE lote_id = ? "
            " ORDER BY numero_os" % ", ".join(ARTEFATO_COLS),
            (lote_id,)).fetchall()]
    if not artefatos:
        return {"ok": False, "motivo": "este lote nao tem artefato"}

    hoje = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y")
    linhas = []
    for a in artefatos:
        valor = float(a["valor_pagamento"] or 0) + float(a["valor_km"] or 0)
        descricao = "OS " + str(a["numero_os"])
        if a["termo"]:
            descricao += " | TERMO " + str(a["termo"])
        if a["tecnico_nome"]:
            descricao += " | " + a["tecnico_nome"]
        linhas.append({
            "Tipo de Lançamento": PROCFY_TIPO,
            "Data de pagamento": hoje,
            # 🔵 A competência é a data do SERVIÇO, não a do pagamento.
            "Data de competência": _data_br(a["data_os"]),
            "Descrição": descricao,
            # ⚠️ Vírgula decimal: o arquivo é lido por uma planilha em pt-BR.
            "Valor": ("%.2f" % valor).replace(".", ","),
            "Categoria": (config.get("procfy_categoria") or ""),
            "Recebido de/Pago a": a["tecnico_nome"] or "",
            "Pago?": PROCFY_PAGO,
            # 🔵 Sem orçamento, o campo DIZ isso em vez de ficar vazio: vazio
            # seria indistinguível de "esqueci de preencher".
            "Observações": ("Orcamento " + str(a["orcamento_numero"])
                            if a["orcamento_numero"] else "sem orcamento"),
            "Contas bancárias": (config.get("procfy_conta_bancaria") or ""),
            "Número de Documento / Nosso número": (
                str(a["orcamento_numero"]) if a["orcamento_numero"] else ""),
            "Modo de pagamento": (config.get("procfy_modo_pagamento") or ""),
            "Centro de Custo": (config.get("procfy_centro_de_custo") or ""),
            "Tags (Por Marcação)": (config.get("procfy_tags") or ""),
        })
    return {"ok": True, "tecnico": lote[0], "linhas": linhas,
            "total": sum(float(a["valor_pagamento"] or 0)
                         + float(a["valor_km"] or 0) for a in artefatos),
            "artefatos": len(artefatos),
            # 🚨 O ARQUIVO SAI, E DIZ O QUE SAIU EM BRANCO. 🔵 Decisão dele:
            # *"pode gerar com elas em branco nesse momento, pois podem
            # preencher a mão por informação confidencial ou depois nos
            # passar"*. ⚠️ Gerar calado é que seria `M12` -- quem importasse
            # descobriria na recusa do Procfy, e não aqui.
            "em_branco": faltando,
            "aviso": ("estas colunas saem em branco e precisam ser preenchidas "
                      "na planilha antes de importar: " + ", ".join(
                          COLUNA_DA_CONFIG[c] for c in faltando)
                      if faltando else None)}


def montar_arquivo(lote_id: int, config: dict, *,
                   por: str | None = None) -> dict:
    """Gera o `.xlsx` do lote e o move para a coluna 4.

    🔵 *"o botão de ação da vez é 'Montar Arquivo' e avança com os que tiveram
    ou arquivo enviado ou justificativa escrita na tela de envio de anexo (pode
    não ter)."*

    🚨 **QUEM NÃO TEM NEM COMPROVANTE NEM DISPENSA FICA.** Não é devolvido nem
    avança: é a mesma régua do `auditar`, e por isso o lote antigo ganha um
    irmão com os que ficaram.
    """
    montado = linhas_do_procfy(lote_id, config)
    if not montado.get("ok"):
        return montado
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        prontos, ficaram = [], []
        for r in conn.execute(
                "SELECT id, comprovante_arquivo, comprovante_dispensa "
                "  FROM pagamento_artefato WHERE lote_id = ? "
                "   AND coluna = 'validacao'", (lote_id,)).fetchall():
            (prontos if (r[1] or r[2]) else ficaram).append(r[0])
        if not prontos:
            return {"ok": False, "avancaram": 0, "ficaram": len(ficaram),
                    "motivo": "nenhum artefato deste lote tem comprovante nem "
                              "justificativa de dispensa"}
        # 🚨 O SUFIXO DA REGERAÇÃO (23/11, tarefa 2.5). O nome tem segundo
        # de precisão, e reabrir+gerar no mesmo segundo gerava o MESMO nome --
        # o segundo arquivo sobrescrevia o primeiro no disco e a prova do que
        # foi ao Procfy antes desaparecia, com os dois eventos apontando para
        # ele. Antes da 2.5 não havia segunda geração; reabrir criou.
        # ⚠️ Conta REABERTURAS, não é só anticolisão: o nome passa a dizer que
        # este arquivo é a 2ª (ou 3ª) saída do mesmo lote. Microssegundo
        # resolveria a colisão e não contaria nada a quem olha a pasta.
        reaberturas = conn.execute(
            "SELECT COUNT(*) FROM pagamento_evento "
            " WHERE lote_id = ? AND acao = 'reabrir_lote'",
            (lote_id,)).fetchone()[0]
        nome = "procfy_lote%s%s_%s.xlsx" % (
            lote_id, ("_r%d" % reaberturas) if reaberturas else "",
            datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
        for aid in prontos:
            conn.execute(
                "UPDATE pagamento_artefato SET coluna = 'procfy', "
                "       atualizado_em = ? WHERE id = ?", (_agora(), aid))
            _evento(conn, artefato_id=aid, lote_id=lote_id,
                    acao="montar_arquivo", de="validacao", para="procfy",
                    detalhe=nome, por=por)
        if ficaram:
            novo = conn.execute(
                "INSERT INTO pagamento_lote "
                "  (tecnico_id, tecnico_nome, coluna, criado_em, criado_por, "
                "   atualizado_em) "
                "SELECT tecnico_id, tecnico_nome, 'validacao', ?, ?, ? "
                "  FROM pagamento_lote WHERE id = ?",
                (_agora(), por, _agora(), lote_id))
            conn.execute(
                "UPDATE pagamento_artefato SET lote_id = ? "
                " WHERE lote_id = ? AND coluna = 'validacao'",
                (novo.lastrowid, lote_id))
        conn.execute(
            "UPDATE pagamento_lote SET coluna = 'procfy', arquivo_procfy = ?, "
            "       gerado_em = ?, gerado_por = ?, atualizado_em = ? "
            " WHERE id = ?", (nome, _agora(), por, _agora(), lote_id))
        conn.commit()
    return {"ok": True, "arquivo": nome, "avancaram": len(prontos),
            "ficaram": len(ficaram), "linhas": montado["linhas"],
            "total": montado["total"]}


def reabrir_lote(lote_id: int, *, por: str | None = None) -> dict:
    """🔵 *"Reabrir na coluna 5 e gerar o arquivo de novo"* -- tarefa 2.5.

    O lote volta da `enviado` para a `validacao`, que é de onde o
    `montar_arquivo` monta. 🚨 Por isso ele não precisou de nenhum `if` novo:
    *"aceitar lote reaberto"* é o lote estar onde ele já olha.

    🚨 **NÃO É DEVOLVER (2.4):** ciente, comprovante e semáforo FICAM. O lote
    estava certo; o arquivo é que precisa sair outra vez. Apagar a conferência
    aqui faria o operador refazer trabalho que estava bom.

    ⚠️ **O `arquivo_procfy` É LIMPO**, e o nome antigo vai para o evento: se
    ficasse no lote, o `enviar` aceitaria mandar de novo sem ninguém ter
    gerado nada -- ele só confere que o campo existe.
    """
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        lote = conn.execute(
            "SELECT coluna, arquivo_procfy FROM pagamento_lote WHERE id = ?",
            (lote_id,)).fetchone()
        if not lote:
            return {"ok": False, "motivo": "lote nao existe"}
        if lote[0] != "enviado":
            # 🔵 Ele pediu reabrir NA COLUNA 5. De `procfy` o caminho é montar
            # o arquivo de novo, que já existe; de antes disso não há o que
            # reabrir.
            return {"ok": False,
                    "motivo": "reabrir vale na coluna 5 (enviado); este lote "
                              "esta em " + str(lote[0])}
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM pagamento_artefato "
            " WHERE lote_id = ? AND coluna = 'enviado'",
            (lote_id,)).fetchall()]
        if not ids:
            return {"ok": False, "reabertos": 0,
                    "motivo": "este lote nao tem item na coluna 5"}
        for aid in ids:
            conn.execute(
                "UPDATE pagamento_artefato SET coluna = 'validacao', "
                "       atualizado_em = ? WHERE id = ?", (_agora(), aid))
            _evento(conn, artefato_id=aid, lote_id=lote_id, acao="reabrir",
                    de="enviado", para="validacao", detalhe=lote[1], por=por)
        conn.execute(
            "UPDATE pagamento_lote SET coluna = 'validacao', "
            "       arquivo_procfy = NULL, gerado_em = NULL, "
            "       gerado_por = NULL, atualizado_em = ? WHERE id = ?",
            (_agora(), lote_id))
        _evento(conn, artefato_id=None, lote_id=lote_id, acao="reabrir_lote",
                de="enviado", para="validacao",
                detalhe="arquivo anterior: %s" % (lote[1] or "nenhum"),
                por=por)
        conn.commit()
    return {"ok": True, "reabertos": len(ids), "de": "enviado",
            "para": "validacao", "arquivo_anterior": lote[1]}


def enviar_pagamento(lote_id: int, *, por: str | None = None) -> dict:
    """O lote vai para a coluna 5 depois de o arquivo ser baixado.

    🔵 *"Depois de ter o arquivo gerado e baixado, os artefatos de valores
    usados nesse arquivo ficam neste card que vai para a próxima coluna."*
    """
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        lote = conn.execute(
            "SELECT coluna, arquivo_procfy FROM pagamento_lote WHERE id = ?",
            (lote_id,)).fetchone()
        if not lote:
            return {"ok": False, "motivo": "lote nao existe"}
        if lote[0] != "procfy":
            return {"ok": False,
                    "motivo": "este lote esta em " + str(lote[0])
                              + ", nao em procfy"}
        if not lote[1]:
            # ⚠️ Sem arquivo gerado não há o que ter sido baixado.
            return {"ok": False,
                    "motivo": "este lote ainda nao tem arquivo gerado"}
        conn.execute(
            "UPDATE pagamento_artefato SET coluna = 'enviado', "
            "       atualizado_em = ? WHERE lote_id = ? AND coluna = 'procfy'",
            (_agora(), lote_id))
        conn.execute(
            "UPDATE pagamento_lote SET coluna = 'enviado', baixado_em = ?, "
            "       atualizado_em = ? WHERE id = ?",
            (_agora(), _agora(), lote_id))
        _evento(conn, lote_id=lote_id, acao="enviar", de="procfy",
                para="enviado", detalhe=lote[1], por=por)
        conn.commit()
    return {"ok": True}
