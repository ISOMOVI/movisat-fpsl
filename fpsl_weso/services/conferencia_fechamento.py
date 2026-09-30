"""Conferência de Fechamento — primeira peça do Painel Financeiro (29/09).

Objetivo, nas palavras dele: *"saber quais OS finalizadas realmente já
tiveram o serviço executado no Datascope e WESO"*. A OS "Finalizado" no
Harmonit é a alegação de quem fechou (Erika); esta rotina confere se os
outros dois sistemas que o técnico e o equipamento tocam de fato concordam.

🚨 NÃO É A `HST_3.1` (Aderência, apagada em 19/08). Aquela comparava
Harmonit×WESO de forma genérica e virou ruído sem dono -- divergir é normal
entre os dois. Esta pergunta é estreita: **para uma OS específica que
acabou de fechar, os três sinais batem?**

Roda a cada 1h, atrás do flag `conferencia_fechamento_ativa` (nasce
`false` -- liga por decisão dele).

A cada rodada:
  1. Relê o status das OS recentes ainda não vistas como 'Finalizado'
     (⚠️ NÃO é o resync geral de oficina -- ver `os_nao_finalizadas_recentes`).
  2. Sincroniza o DataScope (form "Serviços Técnicos") incrementalmente.
  3. Para cada OS que virou 'Finalizado' e ainda não foi conferida, cruza
     os três sinais e grava uma linha em `conferencia_fechamento`.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone

from fastapi import HTTPException

from .. import storage
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


# ── 1. Reler o status das OS recentes ainda abertas ──────────────────────────

async def _atualizar_status_recentes(janela: int = JANELA_STATUS) -> int:
    """Relê no Harmonit as OS recentes que localmente ainda não são
    'Finalizado', só para atualizar `status`/`status_str`. Retorna quantas
    viraram 'Finalizado' nesta passada."""
    numeros = await storage.os_nao_finalizadas_recentes(janela)
    viraram = 0
    for num in numeros:
        try:
            d = _unwrap_harmonit(await harmonit_get(
                "/OrdemServico/ObterOrdemServicoPorNumero", params={"numeroOs": num}))
        except HTTPException:
            continue
        if not d:
            continue
        await storage.salvar_os_historico(
            numero_os=num, tipo=d.get("tipo"), problema=d.get("problema"),
            produto_id=d.get("produtoId"), cliente_id=d.get("parceiro") or d.get("clienteId"),
            data_previsao=d.get("dataPrevisao"), oficinas=d.get("oficina") or [],
            status=d.get("status"), status_str=d.get("statusStr"),
        )
        if d.get("statusStr") == "Finalizado":
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


async def _conferir_uma(numero_os: int, oficinas: list[dict]) -> None:
    resposta = await storage.resposta_datascope_por_os(numero_os)
    datascope_ok, form_state, motivo_ds = _checar_datascope(numero_os, resposta)
    weso_ok, motivo_weso = await _checar_weso(oficinas)

    partes = [m for m in (motivo_ds, motivo_weso) if m]
    detalhe = " | ".join(partes) if partes else "bate nos três sistemas"

    await storage.salvar_conferencia_fechamento(
        numero_os=numero_os, harmonit_ok=True,
        datascope_ok=datascope_ok, datascope_form_state=form_state,
        weso_ok=weso_ok, detalhe=detalhe,
    )


# ── Rotina ────────────────────────────────────────────────────────────────────

async def run_conferencia() -> dict:
    viraram = await _atualizar_status_recentes()
    sincronizadas = await _sincronizar_datascope()
    pendentes = await storage.os_finalizadas_sem_conferencia()
    for p in pendentes:
        try:
            await _conferir_uma(p["numero_os"], p["oficinas"])
        except Exception:
            logger.exception("conferencia_fechamento: falha ao conferir OS %s", p["numero_os"])
    return {"viraram_finalizado": viraram, "datascope_sincronizadas": sincronizadas,
            "conferidas": len(pendentes)}


async def loop_conferencia_fechamento():
    while True:
        try:
            ativa = await storage.get_config("conferencia_fechamento_ativa", "false")
            if ativa == "true":
                r = await run_conferencia()
                if r["conferidas"]:
                    logger.info("conferencia_fechamento: %s OS conferidas (%s viraram "
                               "Finalizado nesta passada, %s respostas DataScope sincronizadas)",
                               r["conferidas"], r["viraram_finalizado"], r["datascope_sincronizadas"])
        except Exception:
            logger.exception("conferencia_fechamento: falha na rotina periódica")
        await asyncio.sleep(INTERVALO_ROTINA)
