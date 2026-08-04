from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import verificar_chave
from ..client import weso_get, weso_post
from .. import placas
from .. import storage
from ..logger import log_req

router = APIRouter(
    prefix="/weso/veiculos",
    tags=["veiculos"],
    dependencies=[Depends(verificar_chave)],
)


class VeiculoInput(BaseModel):
    placa:             str
    cnpjcpf_cliente:   str
    serial_rastreador: str
    tipoEqp:           int | None = None
    descricao:         str | None = None
    cor:               str | None = None
    chassi:            str | None = None
    renavam:           str | None = None
    anoFab:            int | None = None
    anoMod:            int | None = None
    valorMensalidade:  float | None = None
    observacoes:       str | None = None
    observacoesGestor: str | None = None


class VeiculoUpdate(BaseModel):
    tipoEqp:           int | None = None
    descricao:         str | None = None
    cor:               str | None = None
    valorMensalidade:  float | None = None
    observacoes:       str | None = None
    observacoesGestor: str | None = None


class VeiculoLocalInput(BaseModel):
    placa:      str
    veiculo_id: int


@router.get("/local")
async def listar_veiculos_local():
    veiculos = await storage.listar_veiculos()
    return {"ok": True, "total": len(veiculos), "veiculos": veiculos}


@router.post("/local")
async def registrar_veiculo_local(body: VeiculoLocalInput):
    await storage.salvar_veiculo(body.placa, body.veiculo_id)
    log_req("veiculo", "POST", "/weso/veiculos/local", "registrado_manual",
            body.veiculo_id, body.placa, True, None)
    return {"ok": True, "acao": "registrado_manual",
            "placa": body.placa, "veiculo_id": body.veiculo_id}


@router.post("")
async def cadastrar_veiculo(body: VeiculoInput):
    rastreador_id = await storage.buscar_weso_id_por_serial(body.serial_rastreador)
    if rastreador_id is None:
        raise HTTPException(status_code=404,
            detail=f"Rastreador '{body.serial_rastreador}' nao registrado — execute POST /weso/rastreadores primeiro")

    complemento = {k: v for k, v in {
        "tipoEqp": body.tipoEqp, "cor": body.cor,
        "chassi": body.chassi, "renavam": body.renavam,
        "anoFab": body.anoFab, "anoMod": body.anoMod,
    }.items() if v is not None}

    # Etapa 1 do plano 21: TODA escrita de placa passa por placas.formatar.
    # Antes ia o texto cru, e foi assim que entraram 110 placas com espaco na
    # base. Nao-convencional (chassi, nº de serie) sai intacta -- decisao
    # PADRAO DE PLACA de 27/07.
    placa_fmt = placas.formatar(body.placa) or body.placa

    payload = {
        "equipamento": {
            "placa": placa_fmt,
            "cliente": {"cnpjcpf": body.cnpjcpf_cliente},
            "rastreador": {"id": rastreador_id},
            **({} if body.descricao is None else {"descricao": body.descricao}),
            **({} if body.observacoes is None else {"observacoes": body.observacoes}),
            **({} if body.observacoesGestor is None else {"observacoesGestor": body.observacoesGestor}),
            **({} if body.valorMensalidade is None else {"valorMensalidade": body.valorMensalidade}),
            **({} if not complemento else {"complemento": complemento}),
        }
    }
    result = await weso_post("/Veiculos/Cadastro", payload, allow_409=True)
    acao = "ja_existe" if result.get("_ja_existe") else "criado"
    veiculo_id = result.get("id")
    if acao == "criado" and veiculo_id:
        await storage.salvar_veiculo(body.placa, veiculo_id)
    log_req("veiculo", "POST", "/weso/veiculos", acao, veiculo_id, body.placa, True, None)
    return {"ok": True, "acao": acao, "id": veiculo_id, "dados": result, "erro": None}


@router.put("/{veiculo_id}")
async def atualizar_veiculo(veiculo_id: int, body: VeiculoUpdate):
    payload = {"veiculo_id": veiculo_id}
    if body.descricao is not None:        payload["descricao"] = body.descricao
    if body.cor is not None:              payload["cor"] = body.cor
    if body.observacoes is not None:      payload["observacoes"] = body.observacoes
    if body.tipoEqp is not None:           payload["tipoEqp"] = body.tipoEqp
    if body.valorMensalidade is not None:  payload["valor_mensalidade"] = body.valorMensalidade
    if body.observacoesGestor is not None: payload["observacoesGestor"] = body.observacoesGestor
    result = await weso_post("/Veiculos/Atualizar", payload)
    log_req("veiculo", "PUT", f"/weso/veiculos/{veiculo_id}", "atualizado", veiculo_id, str(veiculo_id), True, None)
    return {"ok": True, "acao": "atualizado", "id": veiculo_id, "dados": result, "erro": None}


@router.delete("/placa/{placa}")
async def excluir_veiculo_por_placa(placa: str):
    registro = await storage.buscar_veiculo(placa)
    if not registro:
        log_req("veiculo", "DELETE", f"/weso/veiculos/placa/{placa}", None, None, placa, False,
                "Placa não registrada localmente")
        raise HTTPException(status_code=404, detail=f"Placa '{placa}' não registrada localmente")
    result = await weso_post("/Veiculos/Excluir", {"veiculo_id": registro["veiculo_id"]})
    await storage.remover_veiculo(placa)
    log_req("veiculo", "DELETE", f"/weso/veiculos/placa/{placa}", "excluido",
            registro["veiculo_id"], placa, True, None)
    return {"ok": True, "acao": "excluido", "id": registro["veiculo_id"], "dados": result, "erro": None}


@router.delete("/{veiculo_id}")
async def excluir_veiculo(veiculo_id: int):
    result = await weso_post("/Veiculos/Excluir", {"veiculo_id": veiculo_id})
    await storage.remover_veiculo_por_id(veiculo_id)
    log_req("veiculo", "DELETE", f"/weso/veiculos/{veiculo_id}", "excluido", veiculo_id, str(veiculo_id), True, None)
    return {"ok": True, "acao": "excluido", "id": veiculo_id, "dados": result, "erro": None}
