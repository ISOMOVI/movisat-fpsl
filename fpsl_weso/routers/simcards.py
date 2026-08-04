from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..auth import verificar_chave
from ..client import weso_post
from ..logger import log_req

router = APIRouter(
    prefix="/weso/simcards",
    tags=["simcards"],
    dependencies=[Depends(verificar_chave)],
)


class SimCardInput(BaseModel):
    iccId:            str
    numero:           int | None = None
    operadora:        str | None = None
    apn:              str | None = None
    situacao:         str | None = None
    valorMensalidade: float | None = None
    obs:              str | None = None


class SimCardUpdate(BaseModel):
    numero:           int | None = None
    operadora:        str | None = None
    apn:              str | None = None
    situacao:         str | None = None
    valorMensalidade: float | None = None


@router.post("")
async def cadastrar_simcard(body: SimCardInput):
    result = await weso_post("/SimCard/Cadastro", body.model_dump(exclude_none=True), allow_409=True)
    if result.get("_ja_existe"):
        log_req("simcard", "POST", "/weso/simcards", "ja_existe", None, body.iccId, True, None)
        return {"ok": True, "acao": "ja_existe", "id": None, "dados": {"iccId": body.iccId}, "erro": None}
    log_req("simcard", "POST", "/weso/simcards", "criado", result["id"], body.iccId, True, None)
    return {"ok": True, "acao": "criado", "id": result["id"], "dados": result, "erro": None}


@router.put("/{iccid}")
async def atualizar_simcard(iccid: str, body: SimCardUpdate):
    payload = {"iccId": iccid, **body.model_dump(exclude_none=True)}
    result = await weso_post("/SimCard/Atualizar", payload)
    log_req("simcard", "PUT", f"/weso/simcards/{iccid}", "atualizado", result.get("id"), iccid, True, None)
    return {"ok": True, "acao": "atualizado", "id": result.get("id"), "dados": result, "erro": None}
