from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import verificar_chave
from ..client import weso_get, weso_post
from .. import storage
from ..logger import log_req
from ..translators.weso import situacao_cliente

router = APIRouter(
    prefix="/weso/clientes",
    tags=["clientes"],
    dependencies=[Depends(verificar_chave)],
)


class ClienteInput(BaseModel):
    cnpjcpf:       str
    razaoSocial:   str
    harmonit_id:   int | None = None
    nomeFantasia:  str | None = None
    tipoCliente:   str | None = None
    situacao:      str | None = None
    contato:       str | None = None
    telefone:      str | None = None
    emailCobranca: str | None = None
    plano:         str | None = None
    endereco:      str | None = None
    numeroEnd:     str | None = None
    bairro:        str | None = None
    cep:           str | None = None
    obs:           str | None = None


@router.get("")
async def consultar_cliente(cnpjcpf: str):
    data = await weso_get("/Clientes/Consultar", params={"cnpjcpf": cnpjcpf})
    clientes = data.get("clientes", [])
    if not clientes:
        log_req("cliente", "GET", "/weso/clientes", None, None, cnpjcpf, False, "Cliente não encontrado")
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    log_req("cliente", "GET", "/weso/clientes", "encontrado", clientes[0]["id"], cnpjcpf, True, None)
    return {"ok": True, "acao": "encontrado", "id": clientes[0]["id"], "dados": clientes[0], "erro": None}


@router.post("")
async def cadastrar_cliente(body: ClienteInput):
    data = await weso_get("/Clientes/Consultar", params={"cnpjcpf": body.cnpjcpf})
    clientes = data.get("clientes", [])
    if clientes:
        c = clientes[0]
        if body.harmonit_id:
            await storage.salvar_cliente(body.harmonit_id, body.cnpjcpf)
        log_req("cliente", "POST", "/weso/clientes", "ja_existe", c["id"], body.cnpjcpf, True, None)
        return {"ok": True, "acao": "ja_existe", "id": c["id"], "dados": c, "erro": None}

    payload = {k: v for k, v in body.model_dump(exclude_none=True).items() if k != "harmonit_id"}
    if "situacao" in payload:
        weso_sit = situacao_cliente(payload["situacao"])
        if weso_sit:
            payload["situacao"] = weso_sit
        else:
            payload.pop("situacao")
    result = await weso_post("/Clientes/Cadastro", payload)
    if body.harmonit_id:
        await storage.salvar_cliente(body.harmonit_id, body.cnpjcpf)
    log_req("cliente", "POST", "/weso/clientes", "criado", result["id"], body.cnpjcpf, True, None)
    return {"ok": True, "acao": "criado", "id": result["id"], "dados": result, "erro": None}


class ClienteUpdate(BaseModel):
    razaoSocial:   str | None = None
    nomeFantasia:  str | None = None
    tipoCliente:   str | None = None
    situacao:      str | None = None
    contato:       str | None = None
    telefone:      str | None = None
    emailCobranca: str | None = None
    plano:         str | None = None
    endereco:      str | None = None
    numeroEnd:     str | None = None
    bairro:        str | None = None
    cep:           str | None = None
    obs:           str | None = None


@router.put("/{cnpjcpf}")
async def atualizar_cliente(cnpjcpf: str, body: ClienteUpdate):
    payload = {"cnpjcpf": cnpjcpf, **body.model_dump(exclude_none=True)}
    if body.situacao is not None:
        weso_sit = situacao_cliente(body.situacao)
        if weso_sit:
            payload["situacao"] = weso_sit
        else:
            payload.pop("situacao", None)
    data = await weso_post("/Clientes/Atualizar", payload)
    log_req("cliente", "PUT", f"/weso/clientes/{cnpjcpf}", "atualizado", data.get("id"), cnpjcpf, True, None)
    return {"ok": True, "acao": "atualizado", "id": data.get("id"), "dados": data, "erro": None}
