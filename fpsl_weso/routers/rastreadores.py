from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import verificar_chave
from ..client import weso_get, weso_post
from .. import storage
from ..logger import log_req

router = APIRouter(
    prefix="/weso/rastreadores",
    tags=["rastreadores"],
    dependencies=[Depends(verificar_chave)],
)


class RastreadorInput(BaseModel):
    numeroSerie:  str
    modelo:       str
    harmonit_id:  int | None = None
    iccId:        str | None = None
    tipo:         str | None = None
    situacao:     str | None = None
    lote:         str | None = None
    notaFiscal:   str | None = None
    valorPago:    float | None = None


class ChipInput(BaseModel):
    iccId: str


class RastreadorLocalInput(BaseModel):
    serial:  str
    weso_id: int


@router.get("/local")
async def listar_rastreadores_local():
    itens = await storage.listar_rastreadores_serials()
    return {"ok": True, "total": len(itens), "rastreadores": itens}


@router.post("/local")
async def registrar_rastreador_local(body: RastreadorLocalInput):
    await storage.salvar_rastreador_serial(body.serial, body.weso_id)
    log_req("rastreador", "POST", "/weso/rastreadores/local", "registrado_manual",
            body.weso_id, body.serial, True, None)
    return {"ok": True, "acao": "registrado_manual", "serial": body.serial, "weso_id": body.weso_id}


@router.get("/{rastreador_id}")
async def consultar_rastreador(rastreador_id: int):
    serial = await storage.buscar_serial_por_weso_id(rastreador_id)
    if serial is not None:
        log_req("rastreador", "GET", f"/weso/rastreadores/{rastreador_id}",
                "encontrado_local", rastreador_id, serial, True, None)
        return {"ok": True, "acao": "encontrado_local", "id": rastreador_id,
                "dados": {"id": rastreador_id, "serial": serial}, "erro": None}
    # fallback WESO — endpoint pode estar bloqueado (W7)
    data = await weso_get("/Rastreadores/Consultar", params={"id": rastreador_id})
    items = data.get("rastreadores", [])
    if not items:
        log_req("rastreador", "GET", f"/weso/rastreadores/{rastreador_id}", None, None,
                str(rastreador_id), False, "Rastreador não encontrado")
        raise HTTPException(status_code=404, detail="Rastreador não encontrado")
    log_req("rastreador", "GET", f"/weso/rastreadores/{rastreador_id}", "encontrado",
            items[0]["id"], str(rastreador_id), True, None)
    return {"ok": True, "acao": "encontrado", "id": items[0]["id"], "dados": items[0], "erro": None}


@router.post("")
async def cadastrar_rastreador(body: RastreadorInput):
    payload = {
        "numeroSerie": body.numeroSerie,
        "modelo": {"descricao": body.modelo},
        **({} if not body.tipo else {"tipo": {"descricao": body.tipo}}),
        **({} if not body.situacao else {"situacao": {"descricao": body.situacao}}),
        **({k: v for k, v in {"lote": body.lote, "notaFiscal": body.notaFiscal,
                               "valorPago": body.valorPago}.items() if v is not None}),
    }
    result = await weso_post("/Rastreadores/Cadastro", payload, allow_409=True)

    if result.get("_ja_existe"):
        if body.iccId:
            upd = await weso_post("/Rastreadores/Atualizar",
                                  {"numeroSerie": body.numeroSerie, "simCard": {"iccId": body.iccId}})
            rastreador_id = upd.get("id")
        else:
            rastreador_id = await storage.buscar_weso_id_por_serial(body.numeroSerie)
        if rastreador_id:
            await storage.salvar_rastreador_serial(body.numeroSerie, rastreador_id)
        if body.harmonit_id and rastreador_id:
            await storage.salvar_rastreador(body.harmonit_id, body.numeroSerie)
        log_req("rastreador", "POST", "/weso/rastreadores", "ja_existe",
                rastreador_id, body.numeroSerie, True, None)
        return {"ok": True, "acao": "ja_existe", "id": rastreador_id, "dados": result, "erro": None}

    rastreador_id = result.get("id")
    if body.iccId and rastreador_id:
        await weso_post("/Rastreadores/Atualizar", {"id": rastreador_id, "simCard": {"iccId": body.iccId}})
    if rastreador_id:
        await storage.salvar_rastreador_serial(body.numeroSerie, rastreador_id)
    if body.harmonit_id and rastreador_id:
        await storage.salvar_rastreador(body.harmonit_id, body.numeroSerie)
    log_req("rastreador", "POST", "/weso/rastreadores", "criado",
            rastreador_id, body.numeroSerie, True, None)
    return {"ok": True, "acao": "criado", "id": rastreador_id, "dados": result, "erro": None}


@router.put("/{rastreador_id}/chip")
async def vincular_chip(rastreador_id: int, body: ChipInput):
    result = await weso_post("/Rastreadores/Atualizar", {"id": rastreador_id, "simCard": {"iccId": body.iccId}})
    log_req("rastreador", "PUT", f"/weso/rastreadores/{rastreador_id}/chip",
            "atualizado", rastreador_id, body.iccId, True, None)
    return {"ok": True, "acao": "atualizado", "id": rastreador_id, "dados": result, "erro": None}
