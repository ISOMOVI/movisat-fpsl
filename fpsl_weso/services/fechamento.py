"""Fechamento de Contas dos Tecnicos — geracao e atualizacao de cards.

Card = 1 tecnico + 1 periodo. Padrao semanal. Regerar substitui.
5 estados: aberto -> conferencia -> preparado -> pagamento -> pago
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fpsl_weso import storage
from fpsl_weso.painel.templates_config import PAGAMENTO_TECNICO_ID, KM_DESLOCAMENTO_ID

log = logging.getLogger("fpsl.fechamento")

INTERVALO_ATUALIZAR_SEG = 3600  # 1h

ESTADOS_VALIDOS = ("aberto", "conferencia", "preparado", "pagamento", "pago")
TRANSICOES = {
    "aberto": ("conferencia",),
    "conferencia": ("preparado", "aberto"),
    "preparado": ("pagamento", "conferencia"),
    "pagamento": ("pago", "preparado"),
    "pago": (),
}


def _extrair_valores_materiais(materiais_json: str | None) -> tuple[float, float]:
    """Extrai valor de PAGAMENTO DE TECNICO e KM DESLOCAMENTO dos materiais."""
    if not materiais_json:
        return 0.0, 0.0
    try:
        materiais = json.loads(materiais_json)
    except (json.JSONDecodeError, TypeError):
        return 0.0, 0.0
    valor_pag = 0.0
    valor_km = 0.0
    for m in materiais:
        pid = m.get("idProduto")
        vt = m.get("valorTotal") or m.get("valor") or 0
        if pid == PAGAMENTO_TECNICO_ID:
            valor_pag += float(vt)
        elif pid == KM_DESLOCAMENTO_ID:
            valor_km += float(vt)
    return valor_pag, valor_km


def _tecnico_real_da_os(tecnicos_json: str | None, ids_excluidos: set) -> int | None:
    """Retorna o ID do tecnico real (nao-usuario) da OS, ou None."""
    if not tecnicos_json:
        return None
    try:
        tecnicos = json.loads(tecnicos_json)
    except (json.JSONDecodeError, TypeError):
        return None
    for t in tecnicos:
        uid = t.get("usuarioId")
        if uid and uid not in ids_excluidos:
            return uid
    return None


async def gerar_cartoes(periodo_inicio: str, periodo_fim: str,
                        tecnico_id: int | None = None) -> dict:
    """Gera (ou regenera) cards de fechamento para o periodo.

    Se `tecnico_id` e informado, gera so para aquele tecnico.
    Regerar substitui o card anterior do mesmo tecnico+periodo.
    """
    ids_excluidos = set(await storage.listar_ids_tecnicos_excluidos())

    if tecnico_id:
        tecnicos = [await storage.buscar_tecnico(tecnico_id)]
        tecnicos = [t for t in tecnicos if t and not t["excluido"]]
    else:
        tecnicos = await storage.listar_tecnicos(apenas_reais=True)

    if not tecnicos:
        return {"ok": False, "motivo": "nenhum tecnico real encontrado"}

    SITUACAO_SERVICO_REALIZADO = 15694

    os_do_periodo = await storage.listar_os_historico_periodo(
        periodo_inicio, periodo_fim,
        situacao_id=SITUACAO_SERVICO_REALIZADO,
    )

    os_por_tecnico: dict[int, list] = {}
    for os_row in os_do_periodo:
        tid = _tecnico_real_da_os(os_row.get("tecnicos_json"), ids_excluidos)
        if tid is None:
            continue
        conf = await storage.buscar_conferencia_fechamento(os_row["numero_os"])
        if not conf:
            continue
        conferencia_ok = bool(
            conf.get("harmonit_ok")
            and conf.get("datascope_ok")
            and conf.get("weso_ok")
        )
        valor_pag, valor_km = _extrair_valores_materiais(os_row.get("materiais_json"))
        os_por_tecnico.setdefault(tid, []).append({
            "numero_os": os_row["numero_os"],
            "valor_pagamento": valor_pag,
            "valor_km": valor_km,
            "conferencia_ok": conferencia_ok,
        })

    cards_criados = 0
    for tec in tecnicos:
        tid = tec["tecnico_id"]
        os_list = os_por_tecnico.get(tid, [])
        if not os_list:
            continue

        await storage.deletar_cartao_fechamento_por_periodo(
            tid, periodo_inicio, periodo_fim)

        valor_total = sum(o["valor_pagamento"] + o["valor_km"] for o in os_list)
        cartao_id = await storage.salvar_cartao_fechamento(
            tecnico_id=tid,
            tecnico_nome=tec["nome"],
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            estado="aberto",
            valor_servicos=valor_total,
        )
        for o in os_list:
            await storage.salvar_fechamento_os(
                cartao_id=cartao_id,
                numero_os=o["numero_os"],
                valor_pagamento=o["valor_pagamento"],
                valor_km=o["valor_km"],
                conferencia_ok=o["conferencia_ok"],
            )
        cards_criados += 1

    log.info("gerar_cartoes: %d cards criados (periodo %s a %s)",
             cards_criados, periodo_inicio, periodo_fim)
    os_total = sum(len(v) for v in os_por_tecnico.values())
    return {"ok": True, "cards_criados": cards_criados, "os_vinculadas": os_total}


async def atualizar_semaforo(cartao_id: int) -> str | None:
    """Rele conferencia e calcula semaforo do card."""
    cartao = await storage.buscar_cartao_fechamento(cartao_id)
    if not cartao or cartao["estado"] == "pago":
        return None

    os_list = await storage.listar_fechamento_os(cartao_id)
    algum_conferencia_nok = False

    for o in os_list:
        conf = await storage.buscar_conferencia_fechamento(o["numero_os"])
        if conf:
            ok = bool(conf.get("harmonit_ok") and conf.get("datascope_ok") and conf.get("weso_ok"))
            await storage.atualizar_fechamento_os_conferencia(o["id"], ok)
            if not ok:
                algum_conferencia_nok = True
        else:
            algum_conferencia_nok = True

    if algum_conferencia_nok:
        semaforo = "yellow"
    elif cartao["valor_recibo"] is not None:
        diff = abs(cartao["valor_recibo"] - cartao["valor_servicos"])
        semaforo = "red" if diff > 0.01 else "green"
    else:
        semaforo = "green"

    await storage.atualizar_semaforo_cartao(cartao_id, semaforo)
    return semaforo


def avancar_estado(estado_atual: str, novo_estado: str) -> str | None:
    """Valida transicao de estado. Retorna o novo estado ou None se invalido."""
    permitidos = TRANSICOES.get(estado_atual, ())
    if novo_estado in permitidos:
        return novo_estado
    return None


async def loop_atualizar_cartoes():
    """A cada 1h, atualiza semaforos de todos os cards nao-pagos."""
    log.info("loop_atualizar_cartoes: iniciando (intervalo=%ds)", INTERVALO_ATUALIZAR_SEG)
    while True:
        try:
            cartoes = await storage.listar_cartoes_fechamento_ativos()
            for c in cartoes:
                await atualizar_semaforo(c["id"])
            if cartoes:
                log.info("loop_atualizar_cartoes: %d cards atualizados", len(cartoes))
        except Exception:
            log.exception("loop_atualizar_cartoes: erro na rodada")
        await asyncio.sleep(INTERVALO_ATUALIZAR_SEG)
