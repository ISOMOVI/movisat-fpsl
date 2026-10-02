"""Conferência de Fechamento — primeira peça do Painel Financeiro (29/09).

Objetivo, nas palavras dele: *"saber quais OS finalizadas realmente já
tiveram o serviço executado no Datascope e WESO"*. A OS "Finalizado" no
Harmonit é a alegação de quem fechou (Erika); esta rotina confere se os
outros dois sistemas que o técnico e o equipamento tocam de fato concordam.

🚨 NÃO É A `HST_3.1` (Aderência, apagada em 19/08). Aquela comparava
Harmonit×WESO de forma genérica e virou ruído sem dono -- divergir é normal
entre os dois. Esta pergunta é estreita: **para uma OS específica que
acabou de fechar, os três sinais batem?**

Roda a cada 1h, atrás do flag `conferencia_fechamento_ativa`, que se liga na
própria tela (🔵 *"coloque interruptor nesse recurso, na propria tela dele"*).

🔵 E3 (01/10) -- A PORTA MUDOU. Antes entrava a OS cujo *status* virou
"Finalizado". Agora entra a OS cuja *situação* é **15694 "Serviço Realizado"**:
*"será feito justamente por uma pessoa mesmo, por isso que a rotina valida ele
primeiro e parte dali"*. E só os **últimos 30 dias**: *"deve varrer somente a
partir dos ultimos 30 dias"*.

A cada rodada:
  1. Relê no Harmonit as OS com oficina dos últimos 30 dias (63 em 01/10), para
     pegar quem acabou de ser marcado "Serviço Realizado".
  2. Sincroniza o DataScope (form "Serviços Técnicos") incrementalmente.
  3. Confere TODA a fila de novo (OS em 15694 com oficina, 30 dias): a regra da
     oficina (`services/conferencia_oficina.py`, a mesma da sub-aba do Histórico
     de OS), com a WESO lida AO VIVO -- a OS acabou de ser marcada e o cache é
     de 04:15 -- mais o DataScope e a data real de finalização.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from .. import storage
from . import conferencia_oficina as co
from ..harmonit_client import harmonit_get
from ..client import weso_get
from ..datascope_client import datascope_get

logger = logging.getLogger("fpsl.conferencia_fechamento")

FORM_ID_SERVICOS_TECNICOS = 455616
CAMPO_NUMERO_OS = "Nº da O.S."

# Universo de `form_state` medido ao vivo em 29/09 (GET /api/external/list_states).
ESTADOS_PROBLEMA = {
    "Rejeitado pela área técnica",
    "Informações não coincidem",
    "Cancelado",
    "Finalizado com divergências",
    "Rejeitado pela área Financeira",
    "Duplicidade",
}
ESTADO_OK = "Finalizado"
# null e "Aprovado análise técnica" (e qualquer outro fora das duas listas
# acima) contam como "ainda não fechou no DataScope" -- não é erro, é cedo.

INTERVALO_ROTINA = 60 * 60  # 1h, pedido dele
JANELA_STATUS = 400  # mesma ordem de grandeza do resync geral (os_para_resync)
# 🔵 *"deve varrer somente a partir dos ultimos 30 dias"* (01/10). Decisão dele.
JANELA_DIAS = 30

# ── Linha do tempo: quando a OS finalizou DE FATO ────────────────────────────
# Códigos de `status` medidos ao vivo em 01/10 nas OS 16450 e 16991:
#   1 Agendado · 2 Nova · 4 Finalizado · 7 Reagendado · 14 Cancelamento da Conclusão
# Status fora desta lista é IGNORADO (neutro) -- supor significado para código
# que nunca vi é o erro que o `M15` cobra.
STATUS_TL_FINALIZADO = 4
STATUS_TL_CANCELA_CONCLUSAO = 14
# O Harmonit devolve `data` em horário de Brasília, sem fuso no texto. O Brasil
# não tem horário de verão desde 2019, então o deslocamento é fixo.
FUSO_HARMONIT = timedelta(hours=-3)
BACKFILL_TIMELINE = 60  # quantas OS antigas preencher por rodada


def _unwrap_harmonit(r):
    d = r.get("data") if (isinstance(r, dict) and r.get("data")) else r
    return d[0] if isinstance(d, list) else d


def _numero_os_do_campo(valor) -> int | None:
    """O campo `Nº da O.S.` do DataScope é texto livre digitado/selecionado
    por gente -- às vezes vem com espaço ou prefixo. Extrai só os dígitos."""
    if valor is None:
        return None
    m = re.search(r"\d+", str(valor))
    return int(m.group()) if m else None


def _data_harmonit(texto) -> datetime | None:
    """`dd/mm/aaaa HH:MM:SS` de Brasília -> datetime em UTC.

    Devolve `None` em qualquer formato inesperado: data que não dá para ler é
    "não sei", nunca uma data errada ordenando a fila."""
    if not texto:
        return None
    try:
        d = datetime.strptime(str(texto).strip(), "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None
    return d.replace(tzinfo=timezone(FUSO_HARMONIT)).astimezone(timezone.utc)


def finalizacao_da_timeline(eventos: list[dict]) -> tuple[str | None, str | None]:
    """(quando finalizou em UTC ISO, quem finalizou) a partir de `ObterTimeLine`.

    🚨 FINALIZAÇÃO SE DESFAZ, e foi medido: a OS 16991 tem `Finalizado`
    (10:06) e depois `Cancelamento da Conclusão` (11:22). Quem lesse só o
    último `Finalizado` diria que ela está finalizada desde 10:06 -- e ela
    não está. Vale o último `Finalizado` que NÃO foi cancelado depois.

    ⚠️ Não confia na ordem em que a API devolve: ordena pela data lida. E
    evento sem data legível é descartado, não chutado.
    """
    datados = []
    for ev in eventos or []:
        quando = _data_harmonit(ev.get("data"))
        if quando is not None:
            datados.append((quando, ev))
    datados.sort(key=lambda par: par[0])

    achado = None
    for quando, ev in datados:
        status = ev.get("status")
        if status == STATUS_TL_FINALIZADO:
            achado = (quando.isoformat(), ev.get("usuario") or None)
        elif status == STATUS_TL_CANCELA_CONCLUSAO:
            achado = None          # cancelou a conclusão: não está finalizada
    return achado if achado else (None, None)


async def _ler_finalizacao(os_id: int | None) -> tuple[str | None, str | None]:
    """Uma chamada a `ObterTimeLine`. Falha é `(None, None)` -- a conferência
    não para por não saber a data, só fica sem ela."""
    if not os_id:
        return None, None
    try:
        r = await harmonit_get("/OrdemServico/ObterTimeLine", params={"osId": os_id})
    except HTTPException:
        return None, None
    eventos = r.get("data") if isinstance(r, dict) else r
    if not isinstance(eventos, list):
        return None, None
    return finalizacao_da_timeline(eventos)


# ── 1. Reler as OS com oficina da janela ─────────────────────────────────────

async def _atualizar_status_recentes(dias: int = JANELA_DIAS) -> int:
    """Relê no Harmonit as OS com oficina vistas nos últimos `dias`. Devolve
    quantas estão em "Serviço Realizado" depois da releitura.

    ⚠️ Relê TODAS da janela, inclusive as que já estão em 15694: a situação pode
    ser desfeita, e a oficina e os materiais podem mudar depois de marcada."""
    numeros = await storage.os_com_oficina_recentes(dias)
    viraram = 0
    for num in numeros:
        try:
            d = _unwrap_harmonit(await harmonit_get(
                "/OrdemServico/ObterOrdemServicoPorNumero", params={"numeroOs": num}))
        except HTTPException:
            continue
        if not d:
            continue
        # 🔵 01/10: repassa também `materiais`/`situacaoId`/`id`, que já vêm nesta
        # mesma resposta. Sem isso, esta rotina (1h) voltaria com os campos vazios
        # e a guarda do `salvar_os_historico` só os PRESERVARIA -- ou seja, uma OS
        # que acabou de virar "Serviço Realizado" só apareceria no resync de 12h.
        await storage.salvar_os_historico(
            numero_os=num, tipo=d.get("tipo"), problema=d.get("problema"),
            produto_id=d.get("produtoId"), cliente_id=d.get("parceiro") or d.get("clienteId"),
            data_previsao=d.get("dataPrevisao"), oficinas=d.get("oficina") or [],
            status=d.get("status"), status_str=d.get("statusStr"),
            materiais=d.get("materiais"), situacao_id=d.get("situacaoId"),
            os_id=d.get("id"),
        )
        if d.get("situacaoId") == storage.SITUACAO_SERVICO_REALIZADO:
            viraram += 1
    return viraram


# ── 2. Sincronizar o DataScope ───────────────────────────────────────────────

async def _sincronizar_datascope(limite_paginas: int = 20) -> int:
    """Pagina /v5/answers do form Serviços Técnicos, só o que mudou desde o
    último cursor salvo. `date_modified=true&order_date=true` é o que traz
    respostas EDITADAS (mudar form_state é edição, não resposta nova) --
    sem isso a rotina nunca veria a Erika fechando o checklist."""
    cursor = await storage.get_config("datascope_sync_cursor", "")
    gravadas = 0
    for _ in range(limite_paginas):
        params = {"form_id": FORM_ID_SERVICOS_TECNICOS, "limit": 200,
                  "date_modified": "true", "order_date": "true"}
        if cursor:
            params["since"] = cursor
        corpo = await datascope_get("/v5/answers", params)
        itens = corpo if isinstance(corpo, list) else (corpo.get("data") or corpo.get("answers") or [])
        if not itens:
            break
        for item in itens:
            form_answer_id = item.get("form_answer_id")
            if not form_answer_id:
                continue
            numero_os = _numero_os_do_campo(item.get(CAMPO_NUMERO_OS))
            await storage.salvar_resposta_datascope(
                form_answer_id=form_answer_id, numero_os=numero_os,
                form_state=item.get("form_state"),
                updated_at=item.get("updated_at") or "",
            )
            gravadas += 1
        ultimo = itens[-1]
        cursor = f"{ultimo.get('updated_at')}|{ultimo.get('form_answer_id')}"
        await storage.set_config("datascope_sync_cursor", cursor)
        if len(itens) < 200:
            break
    return gravadas


# ── 3. Cruzar os três sinais para uma OS finalizada ──────────────────────────

def _checar_datascope(numero_os: int, resposta: dict | None) -> tuple[bool | None, str | None, str]:
    """(datascope_ok, form_state, detalhe). `None` = ainda não fechou lá --
    sinal próprio, não é falha (mesma lição do `ignorado` em Operações:
    'ainda não aconteceu' não é 'está errado')."""
    if not resposta:
        return False, None, "sem registro no DataScope para esta OS"
    estado = resposta.get("form_state")
    if estado == ESTADO_OK:
        return True, estado, ""
    if estado in ESTADOS_PROBLEMA:
        return False, estado, f"DataScope em estado de problema: {estado!r}"
    return None, estado, f"DataScope ainda não finalizou (estado atual: {estado!r})"


async def _checar_weso(oficinas: list[dict]) -> tuple[bool | None, str]:
    """Para cada item de `oficina[]`, confere a situação do rastreador na
    WESO contra o desfecho esperado: status 1 (instalação) -> 'Instalado';
    status 2 (desinstalação) -> 'Estoque'. Sem oficina nenhuma, não há o que
    conferir (`None`, não é falha)."""
    if not oficinas:
        return None, "OS sem oficina registrada — nada para conferir na WESO"
    problemas = []
    for of in oficinas:
        serial = of.get("equipamentoId")
        tipo = of.get("status")
        if not serial or tipo not in (1, 2):
            continue
        esperado = "Instalado" if tipo == 1 else "Estoque"
        try:
            r = await weso_get("/Rastreadores/Consultar", {"numeroSerie": serial})
        except HTTPException as exc:
            problemas.append(f"{serial}: WESO indisponível ({exc.detail})")
            continue
        rastreadores = r.get("rastreadores") or []
        if not rastreadores:
            problemas.append(f"{serial}: não encontrado na WESO")
            continue
        atual = rastreadores[0].get("situacao")
        if atual != esperado:
            placa = of.get("veiculoPlaca") or "?"
            problemas.append(f"{serial} (placa {placa}): esperava {esperado!r}, WESO diz {atual!r}")
    if problemas:
        return False, "; ".join(problemas)
    return True, ""


# ── 3a. WESO ao vivo ─────────────────────────────────────────────────────────

def mapas_weso(veiculos: list[dict], rastreadores: list[dict]) -> dict:
    """Monta as três buscas que a regra da oficina precisa, a partir das listas
    cruas da WESO. Puro -- testável sem rede.

    🚨 POR QUE A BASE INTEIRA DE VEÍCULOS, E NÃO `/Veiculos/Consultar?placa=`:
    essa consulta compara por igualdade EXATA e devolve VAZIO, não erro, quando a
    placa difere por espaço (`painel/equipamentos.py`, 29/07: 110 placas com
    espaço nas pontas). Placa "não achada" seria lida como "placa excluída" -- e
    numa retirada isso vira um OK falso. Uma chamada da base inteira (2,3 s
    medidos) por rodada casa por placa normalizada, e ainda dá de graça o
    caminho inverso (onde a série está agora) e o chassi do veículo.
    """
    por_placa, por_rastreador = {}, {}
    for v in veiculos or []:
        comp = v.get("complemento") or {}
        veic = {"placa": v.get("placa"), "chassi": comp.get("chassi"),
                "descricao": v.get("descricao"), "rastreador_id": v.get("rastreador_id")}
        chave = co._norm(v.get("placa"))
        if chave:
            por_placa[chave] = veic
        if v.get("rastreador_id"):
            por_rastreador[v["rastreador_id"]] = veic
    por_serial = {str(r.get("numeroSerie") or "").strip(): r for r in rastreadores or []
                  if r.get("numeroSerie")}
    return {
        "rastreador_por_serial": lambda s: por_serial.get(str(s or "").strip()),
        "veiculo_por_placa": lambda p: por_placa.get(co._norm(p)),
        "placa_do_rastreador": lambda rid: por_rastreador.get(rid),
    }


async def _ler_weso_ao_vivo(seriais: set) -> dict | None:
    """Uma chamada da base de veículos + uma por série. `None` = WESO fora: a
    conferência não chuta, deixa o vínculo indefinido."""
    try:
        rv = await weso_get("/Veiculos/Consultar", {})
        veiculos = (rv.get("veiculos") or []) if isinstance(rv, dict) else []
    except HTTPException:
        return None
    rastreadores = []
    for s in sorted(seriais):
        try:
            rr = await weso_get("/Rastreadores/Consultar", {"numeroSerie": s})
        except HTTPException:
            continue
        rastreadores.extend((rr.get("rastreadores") or []) if isinstance(rr, dict) else [])
    return mapas_weso(veiculos, rastreadores)


def _datascope_na_porta(resposta: dict | None) -> tuple[bool | None, str | None, str]:
    """Como `_checar_datascope`, com uma diferença que a PORTA cria.

    🔵 *"a situação de 'Serviço Realizado' só acontece depois que OS datascope
    existe"*. Então, aqui, faltar a resposta não é "ainda não": é anomalia -- mas
    continua CINZA (não se sabe qual lado errou: a situação marcada cedo demais,
    ou o técnico digitou outro número no `Nº da O.S.`). A Ação fica bloqueada."""
    if not resposta:
        return None, None, ("sem resposta no DataScope, mas a OS está em "
                            "Serviço Realizado -- confira o Nº da O.S. digitado")
    return _checar_datascope(0, resposta)


async def _conferir_uma(linha: dict, weso: dict | None, de_para: dict,
                        ultima_do_serial: dict) -> None:
    """Confere UMA OS da fila. A regra da oficina é a MESMA da sub-aba "ID ×
    modelo" (`conferencia_oficina.conferir_os`) -- uma regra só, duas telas."""
    numero_os = linha["numero_os"]
    if weso:
        v = co.conferir_os(linha, de_para, weso["rastreador_por_serial"],
                           weso["veiculo_por_placa"], weso["placa_do_rastreador"],
                           ultima_do_serial)
        weso_ok = {co.OK: True, co.DIVERGENTE: False}.get(v["veredito_weso"])
        acao_ok = {co.OK: True, co.DIVERGENTE: False}.get(v["veredito_acao"])
        modelo_ok = {co.OK: True, co.DIVERGENTE: False}.get(v["veredito_modelo"])
        detalhe_oficina = v["detalhe"]
    else:
        weso_ok = acao_ok = modelo_ok = None
        detalhe_oficina = "WESO indisponível nesta passada -- nada se afirma"

    resposta = await storage.resposta_datascope_por_os(numero_os)
    datascope_ok, form_state, motivo_ds = _datascope_na_porta(resposta)

    # Data real da finalização: UMA chamada, só na primeira conferência desta OS
    # (`salvar_conferencia_fechamento` preserva o que já souber).
    fim, por = await _ler_finalizacao(await storage.os_id_de(numero_os))

    partes = [m for m in (detalhe_oficina if detalhe_oficina != "bate com a WESO" else "",
                          motivo_ds) if m]
    detalhe = " | ".join(partes) if partes else "bate em tudo"

    await storage.salvar_conferencia_fechamento(
        numero_os=numero_os, harmonit_ok=True,
        datascope_ok=datascope_ok, datascope_form_state=form_state,
        weso_ok=weso_ok, detalhe=detalhe,
        finalizado_em=fim, finalizado_por=por,
        acao_ok=acao_ok, modelo_ok=modelo_ok,
    )


async def _os_id_resolvido(numero_os: int) -> int | None:
    """O `os_id` do banco; se faltar, busca no Harmonit e GRAVA.

    🚨 POR QUE NÃO BASTA ESPERAR A VARREDURA: o resync cobre as 400 OS mais
    RECENTES, e as linhas desta conferência envelhecem. Toda OS que sai dessa
    janela nunca mais receberia `os_id` -- e ficaria sem data de finalização
    para sempre. Medido em 01/10: 16450, 16551 e 16552 já estavam nesse caso.
    Uma chamada por OS, UMA VEZ na vida dela.
    """
    os_id = await storage.os_id_de(numero_os)
    if os_id:
        return os_id
    try:
        d = _unwrap_harmonit(await harmonit_get(
            "/OrdemServico/ObterOrdemServicoPorNumero", params={"numeroOs": numero_os}))
    except HTTPException:
        return None
    if not d or not d.get("id"):
        return None
    await storage.salvar_os_historico(
        numero_os=numero_os, tipo=d.get("tipo"), problema=d.get("problema"),
        produto_id=d.get("produtoId"), cliente_id=d.get("parceiro") or d.get("clienteId"),
        data_previsao=d.get("dataPrevisao"), oficinas=d.get("oficina") or [],
        status=d.get("status"), status_str=d.get("statusStr"),
        materiais=d.get("materiais"), situacao_id=d.get("situacaoId"),
        os_id=d.get("id"),
    )
    return d.get("id")


async def _preencher_finalizacoes(limite: int = BACKFILL_TIMELINE) -> int:
    """Preenche `finalizado_em` das linhas que ainda não a têm -- as 76 de 29/09
    nasceram sem ela. Teto por rodada para não virar rajada no Harmonit.

    ⚠️ OS cuja finalização foi CANCELADA fica sem data de propósito, e volta a
    ser tentada em toda rodada (são poucas, e um dia podem finalizar de novo).
    """
    preenchidas = 0
    for num in await storage.conferencia_sem_finalizado_em(limite):
        os_id = await _os_id_resolvido(num)
        if not os_id:
            continue
        fim, por = await _ler_finalizacao(os_id)
        if not fim:
            continue    # cancelada, sem data legível, ou nunca finalizada
        await storage.salvar_conferencia_fechamento_datas(num, fim, por)
        preenchidas += 1
    return preenchidas


# ── Rotina ────────────────────────────────────────────────────────────────────

async def run_conferencia() -> dict:
    em_servico = await _atualizar_status_recentes()
    sincronizadas = await _sincronizar_datascope()
    fila = await storage.os_para_conferir(JANELA_DIAS)

    conferidas = 0
    if fila:
        # WESO ao vivo UMA vez por rodada, e só se houver o que conferir.
        seriais = {str(of.get("equipamentoId") or "").strip()
                   for ln in fila for of in ln["oficinas"]} - {""}
        weso = await _ler_weso_ao_vivo(seriais)
        de_para = co.de_para_do_banco()
        ultima = await co.ultima_os_por_serial()
        for linha in fila:
            try:
                await _conferir_uma(linha, weso, de_para, ultima)
                conferidas += 1
            except Exception:
                logger.exception("conferencia_fechamento: falha ao conferir OS %s",
                                 linha["numero_os"])
    try:
        datas = await _preencher_finalizacoes()
    except Exception:
        logger.exception("conferencia_fechamento: falha ao preencher datas de finalização")
        datas = 0
    return {"em_servico_realizado": em_servico, "datascope_sincronizadas": sincronizadas,
            "conferidas": conferidas, "datas_preenchidas": datas,
            "janela_dias": JANELA_DIAS}


async def loop_conferencia_fechamento():
    while True:
        try:
            ativa = await storage.get_config("conferencia_fechamento_ativa", "false")
            if ativa == "true":
                r = await run_conferencia()
                if r["conferidas"] or r["datas_preenchidas"]:
                    logger.info("conferencia_fechamento: %s OS conferidas (%s em Serviço "
                               "Realizado na janela de %s dias, %s respostas DataScope "
                               "sincronizadas, %s datas de finalização preenchidas)",
                               r["conferidas"], r["em_servico_realizado"], r["janela_dias"],
                               r["datascope_sincronizadas"], r["datas_preenchidas"])
        except Exception:
            logger.exception("conferencia_fechamento: falha na rotina periódica")
        await asyncio.sleep(INTERVALO_ROTINA)
