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
    """Gera cards de fechamento para o periodo -- SEM apagar nada.

    Pega as OS em "Servico Realizado" conferidas do periodo que ainda NAO estao
    em nenhum card ativo (trava de OS: uma OS so vive em um card por vez) e as
    coloca num card 'aberto' do tecnico -- criando o card ou completando o
    'aberto' que ja exista. Cards ja avancados (conferencia..pago) e cancelados
    nunca sao tocados. Reclicar e idempotente: OS ja consumidas nao voltam.
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

    # trava de OS: ignora as que ja estao presas a um card ativo
    os_consumidas = await storage.listar_numeros_os_consumidas()

    os_por_tecnico: dict[int, list] = {}
    os_ja_consumidas = 0
    for os_row in os_do_periodo:
        if os_row["numero_os"] in os_consumidas:
            os_ja_consumidas += 1
            continue
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
    cards_completados = 0
    os_novas = 0
    tecnicos_por_id = {t["tecnico_id"]: t for t in tecnicos}
    for tid, os_list in os_por_tecnico.items():
        tec = tecnicos_por_id.get(tid)
        if not tec or not os_list:
            continue

        aberto = await storage.buscar_cartao_aberto_por_periodo(
            tid, periodo_inicio, periodo_fim)
        if aberto:
            cartao_id = aberto["id"]
            cards_completados += 1
        else:
            cartao_id = await storage.salvar_cartao_fechamento(
                tecnico_id=tid,
                tecnico_nome=tec["nome"],
                periodo_inicio=periodo_inicio,
                periodo_fim=periodo_fim,
                estado="aberto",
                valor_servicos=0,
            )
            cards_criados += 1

        for o in os_list:
            await storage.salvar_fechamento_os(
                cartao_id=cartao_id,
                numero_os=o["numero_os"],
                valor_pagamento=o["valor_pagamento"],
                valor_km=o["valor_km"],
                conferencia_ok=o["conferencia_ok"],
            )
            os_novas += 1

        # recalcula o total a partir de TODAS as OS do card (existentes + novas)
        todas = await storage.listar_fechamento_os(cartao_id)
        valor_total = sum(o["valor_pagamento"] + o["valor_km"] for o in todas)
        await storage.atualizar_valor_servicos_cartao(cartao_id, valor_total)

    log.info("gerar_cartoes: %d criados, %d completados, %d OS novas, %d ja "
             "consumidas (periodo %s a %s)", cards_criados, cards_completados,
             os_novas, os_ja_consumidas, periodo_inicio, periodo_fim)
    return {"ok": True, "cards_criados": cards_criados,
            "cards_completados": cards_completados, "os_novas": os_novas,
            "os_ja_consumidas": os_ja_consumidas, "os_vinculadas": os_novas}


async def atualizar_semaforo(cartao_id: int) -> str | None:
    """Rele conferencia e calcula semaforo do card."""
    cartao = await storage.buscar_cartao_fechamento(cartao_id)
    if not cartao or cartao["estado"] in ("pago", "cancelado"):
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
