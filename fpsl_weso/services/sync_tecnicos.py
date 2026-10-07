"""Rotina diaria oculta: separa tecnicos reais de usuarios do sistema.

Duas camadas de exclusao:
1. Quem aparece em ObterUsuarios E em ObterTecnicos (cruzamento por ID).
2. Quem tem o mesmo email de um usuario do painel FPSL (painel_usuarios).
A API do Harmonit nao devolve todos os usuarios em ObterUsuarios, entao a
segunda camada pega quem escapou (ex: owner cadastrado so como tecnico).
"""

import asyncio
import logging
from datetime import datetime, timezone

from fpsl_weso.harmonit_client import harmonit_get
from fpsl_weso import storage

log = logging.getLogger("fpsl.sync_tecnicos")

INTERVALO_SEG = 86_400  # 1x/dia


async def sync_tecnicos() -> dict:
    """Consulta Harmonit e atualiza a tabela `tecnicos`."""
    tec_resp = await harmonit_get("/Usuario/ObterTecnicos")
    usr_resp = await harmonit_get("/Usuario/ObterUsuarios")

    if not tec_resp or not usr_resp:
        log.warning("sync_tecnicos: resposta vazia do Harmonit, pulando")
        return {"ok": False, "motivo": "resposta vazia"}

    tecnicos = tec_resp if isinstance(tec_resp, list) else []
    usuarios = usr_resp if isinstance(usr_resp, list) else []

    ids_usuarios = {u.get("id") for u in usuarios if u.get("id")}
    emails_painel = await storage.listar_emails_painel()

    total = 0
    excluidos = 0
    for t in tecnicos:
        tid = t.get("id")
        nome = t.get("nome", "").strip()
        if not tid:
            continue
        email_tec = (t.get("email") or "").strip().lower()
        eh_usuario = tid in ids_usuarios or email_tec in emails_painel
        await storage.salvar_tecnico(tid, nome, excluido=eh_usuario)
        total += 1
        if eh_usuario:
            excluidos += 1

    reais = total - excluidos
    log.info("sync_tecnicos: %d tecnicos, %d excluidos (usuarios), %d reais",
             total, excluidos, reais)
    return {"ok": True, "total": total, "excluidos": excluidos, "reais": reais}


async def loop_sync_tecnicos():
    """Roda sync_tecnicos() uma vez por dia."""
    log.info("loop_sync_tecnicos: iniciando (intervalo=%ds)", INTERVALO_SEG)
    while True:
        try:
            await sync_tecnicos()
        except Exception:
            log.exception("loop_sync_tecnicos: erro na rodada")
        await asyncio.sleep(INTERVALO_SEG)
