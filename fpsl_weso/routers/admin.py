from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import verificar_chave
from .. import storage
from ..services.sync_inadimplencia import run_sync

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verificar_chave)],
)


class ConfigInput(BaseModel):
    valor: str


@router.get("/config")
async def listar_config():
    itens = await storage.listar_config()
    return {"ok": True, "total": len(itens), "config": itens}


@router.put("/config/{chave}")
async def atualizar_config(chave: str, body: ConfigInput):
    if chave == "inadimplencia_grace_days":
        try:
            if int(body.valor) < 1:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422,
                detail="inadimplencia_grace_days deve ser inteiro >= 1")
    if chave == "inadimplencia_sync" and body.valor not in ("true", "false"):
        raise HTTPException(status_code=422,
            detail="inadimplencia_sync aceita apenas 'true' ou 'false'")
    await storage.set_config(chave, body.valor)
    return {"ok": True, "chave": chave, "valor": body.valor}


@router.post("/sync/inadimplencia")
async def trigger_sync():
    resultado = await run_sync()
    return {"ok": True, "resultado": resultado}
