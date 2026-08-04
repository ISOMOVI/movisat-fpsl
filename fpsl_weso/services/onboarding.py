from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..auth import verificar_chave
from ..routers.clientes import ClienteInput, cadastrar_cliente
from ..routers.simcards import SimCardInput, cadastrar_simcard
from ..routers.rastreadores import RastreadorInput, cadastrar_rastreador
from ..routers.veiculos import VeiculoInput, cadastrar_veiculo

router = APIRouter(
    prefix="/weso/onboarding",
    tags=["onboarding"],
    dependencies=[Depends(verificar_chave)],
)


class OnboardingInput(BaseModel):
    cliente:    ClienteInput
    simcard:    SimCardInput
    rastreador: RastreadorInput
    veiculo:    VeiculoInput


@router.post("")
async def onboarding(body: OnboardingInput):
    resultado = {"cliente": None, "simcard": None, "rastreador": None, "veiculo": None}

    if body.veiculo.serial_rastreador != body.rastreador.numeroSerie:
        return {
            "ok": False,
            "etapas": resultado,
            "erro": f"veiculo.serial_rastreador '{body.veiculo.serial_rastreador}' diverge de rastreador.numeroSerie '{body.rastreador.numeroSerie}'",
            "etapa_falhou": "veiculo",
        }

    def _erro(e: Exception) -> str:
        return e.detail if hasattr(e, "detail") else str(e)

    try:
        r = await cadastrar_cliente(body.cliente)
        resultado["cliente"] = {"acao": r["acao"], "id": r["id"]}
    except Exception as e:
        return {"ok": False, "etapas": resultado, "erro": _erro(e), "etapa_falhou": "cliente"}

    try:
        r = await cadastrar_simcard(body.simcard)
        resultado["simcard"] = {"acao": r["acao"], "id": r.get("id")}
    except Exception as e:
        return {"ok": False, "etapas": resultado, "erro": _erro(e), "etapa_falhou": "simcard"}

    try:
        r = await cadastrar_rastreador(body.rastreador)
        resultado["rastreador"] = {"acao": r["acao"], "id": r.get("id")}
    except Exception as e:
        return {"ok": False, "etapas": resultado, "erro": _erro(e), "etapa_falhou": "rastreador"}

    try:
        r = await cadastrar_veiculo(body.veiculo)
        resultado["veiculo"] = {"acao": r["acao"], "id": r.get("id")}
    except Exception as e:
        return {"ok": False, "etapas": resultado, "erro": _erro(e), "etapa_falhou": "veiculo"}

    return {"ok": True, "etapas": resultado, "erro": None, "etapa_falhou": None}
