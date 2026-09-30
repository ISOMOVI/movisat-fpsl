"""Tela `FIN_1.1` — Conferência de Fechamento. Só leitura: a rotina em
`fpsl_weso/services/conferencia_fechamento.py` escreve; este router só lista."""
from fastapi import APIRouter, Depends, Query

from ..auth import requer_aba
from ...services.conferencia_fechamento import run_conferencia
from ... import storage

router = APIRouter(prefix="/painel/api/conferencia-fechamento", tags=["painel-financeiro"])


@router.get("")
async def listar(limit: int = Query(300, le=1000),
                 _=Depends(requer_aba("financeiro"))):
    return {"itens": await storage.listar_conferencia_fechamento(limit)}


@router.post("/rodar-agora")
async def rodar_agora(_=Depends(requer_aba("financeiro"))):
    """Roda a conferência na hora, sem esperar o próximo ciclo de 1h --
    para validar a rotina sem esperar."""
    return await run_conferencia()
