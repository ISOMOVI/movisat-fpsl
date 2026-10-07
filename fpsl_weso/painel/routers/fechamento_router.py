"""Router do Fechamento de Contas dos Tecnicos.

Prefixo: /painel/api/fechamento
Protegido por requer_aba("financeiro").
"""

import csv
import io
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from fpsl_weso import storage
from fpsl_weso.painel.auth import requer_aba
from fpsl_weso.services.fechamento import gerar_cartoes, atualizar_semaforo, avancar_estado
from fpsl_weso.services.sync_tecnicos import sync_tecnicos

log = logging.getLogger("fpsl.fechamento_router")

router = APIRouter(
    prefix="/painel/api/fechamento",
    tags=["fechamento"],
    dependencies=[Depends(requer_aba("financeiro"))],
)

RECIBOS_DIR = Path(__file__).parent.parent.parent / "data" / "recibos"


class GerarBody(BaseModel):
    periodo_inicio: str
    periodo_fim: str
    tecnico_id: int | None = None


class AvancarBody(BaseModel):
    estado: str


# ── Tecnicos ─────────────────────────────────────────────────────────────────

@router.get("/tecnicos")
async def listar_tecnicos():
    return await storage.listar_tecnicos(apenas_reais=True)


@router.post("/tecnicos/sync")
async def sincronizar_tecnicos():
    return await sync_tecnicos()


# ── Cartoes ──────────────────────────────────────────────────────────────────

@router.get("/cartoes")
async def listar_cartoes(tecnico_id: int | None = None,
                         estado: str | None = None,
                         periodo_inicio: str | None = None,
                         periodo_fim: str | None = None):
    return await storage.listar_cartoes_fechamento(
        tecnico_id=tecnico_id,
        estado=estado,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
    )


@router.get("/cartoes/{cartao_id}")
async def detalhe_cartao(cartao_id: int):
    cartao = await storage.buscar_cartao_fechamento(cartao_id)
    if not cartao:
        raise HTTPException(404, "Card nao encontrado")
    os_list = await storage.listar_fechamento_os(cartao_id)
    cartao["os"] = os_list
    return cartao


@router.post("/cartoes/gerar")
async def api_gerar_cartoes(body: GerarBody):
    return await gerar_cartoes(
        periodo_inicio=body.periodo_inicio,
        periodo_fim=body.periodo_fim,
        tecnico_id=body.tecnico_id,
    )


@router.post("/cartoes/{cartao_id}/avancar")
async def api_avancar_estado(cartao_id: int, body: AvancarBody):
    cartao = await storage.buscar_cartao_fechamento(cartao_id)
    if not cartao:
        raise HTTPException(404, "Card nao encontrado")

    novo = avancar_estado(cartao["estado"], body.estado)
    if novo is None:
        raise HTTPException(
            400,
            f"Transicao invalida: {cartao['estado']} -> {body.estado}",
        )
    await storage.atualizar_estado_cartao(cartao_id, novo)
    # "Iniciar Conferencia" (aberto->conferencia) e "Marcar Preparado"
    # (conferencia->preparado) releem a conferencia de cada OS e recalculam o
    # semaforo. Sao as unicas transicoes com efeito real; as demais so andam
    # o card de coluna.
    if novo in ("conferencia", "preparado"):
        await atualizar_semaforo(cartao_id)
    return {"ok": True, "estado": novo}


# ── Recibo ───────────────────────────────────────────────────────────────────

@router.post("/cartoes/{cartao_id}/recibo")
async def upload_recibo(cartao_id: int,
                        valor_recibo: float = Form(...),
                        arquivo: UploadFile = File(...)):
    cartao = await storage.buscar_cartao_fechamento(cartao_id)
    if not cartao:
        raise HTTPException(404, "Card nao encontrado")

    RECIBOS_DIR.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"{cartao_id}_{arquivo.filename}"
    destino = RECIBOS_DIR / nome_arquivo

    with open(destino, "wb") as f:
        shutil.copyfileobj(arquivo.file, f)

    await storage.atualizar_recibo_cartao(cartao_id, str(nome_arquivo), valor_recibo)
    await atualizar_semaforo(cartao_id)
    return {"ok": True, "arquivo": nome_arquivo, "valor_recibo": valor_recibo}


@router.get("/cartoes/{cartao_id}/recibo")
async def download_recibo(cartao_id: int):
    cartao = await storage.buscar_cartao_fechamento(cartao_id)
    if not cartao or not cartao.get("recibo_arquivo"):
        raise HTTPException(404, "Recibo nao encontrado")
    caminho = RECIBOS_DIR / cartao["recibo_arquivo"]
    if not caminho.exists():
        raise HTTPException(404, "Arquivo do recibo nao encontrado no disco")
    return FileResponse(str(caminho), filename=cartao["recibo_arquivo"])


# ── Planilha ─────────────────────────────────────────────────────────────────

@router.get("/cartoes/{cartao_id}/planilha")
async def download_planilha(cartao_id: int):
    cartao = await storage.buscar_cartao_fechamento(cartao_id)
    if not cartao:
        raise HTTPException(404, "Card nao encontrado")

    os_list = await storage.listar_fechamento_os(cartao_id)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "Tecnico", "Periodo", "Nro OS",
        "Pagamento Tecnico (R$)", "KM Deslocamento (R$)", "Total (R$)",
        "Conferencia OK",
    ])
    for o in os_list:
        writer.writerow([
            cartao["tecnico_nome"],
            f"{cartao['periodo_inicio']} a {cartao['periodo_fim']}",
            o["numero_os"],
            f"{o['valor_pagamento']:.2f}",
            f"{o['valor_km']:.2f}",
            f"{o['valor_pagamento'] + o['valor_km']:.2f}",
            "Sim" if o["conferencia_ok"] else "Nao",
        ])
    writer.writerow([])
    writer.writerow(["", "", "TOTAL",
                     f"{sum(o['valor_pagamento'] for o in os_list):.2f}",
                     f"{sum(o['valor_km'] for o in os_list):.2f}",
                     f"{cartao['valor_servicos']:.2f}", ""])
    if cartao.get("valor_recibo") is not None:
        writer.writerow(["", "", "Valor Recibo/NFS", "", "",
                         f"{cartao['valor_recibo']:.2f}", ""])

    conteudo = buf.getvalue().encode("utf-8-sig")
    nome = f"fechamento_{cartao['tecnico_nome']}_{cartao['periodo_inicio']}.csv"
    return StreamingResponse(
        io.BytesIO(conteudo),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
