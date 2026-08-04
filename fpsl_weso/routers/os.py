from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import verificar_chave
from ..client import weso_get, weso_post
from ..weso_lookup import buscar_veiculo_id
from ..harmonit_client import harmonit_get
from .. import storage
from ..logger import log_req
from ..services.resolucao import resolver_serial as _resolver_serial, resolver_cnpjcpf as _resolver_cnpjcpf

router = APIRouter(
    prefix="/weso/os",
    tags=["os"],
    dependencies=[Depends(verificar_chave)],
)


class AdicionarOficinaInput(BaseModel):
    empresaId:            int
    osId:                 int
    rastreadorId:         int
    placaVeiculo:         str
    nomeVeiculo:          str | None = None
    tipoVeic:             int | None = None
    idAparelho:           str | None = None
    idVeiculo:            str | None = None
    trocaOficinaAntigaId: int | None = None
    tipo:                 int | None = None


class DesinstalarOficinaInput(BaseModel):
    empresaId:   int
    osId:        int
    rastreadorId: int
    placaVeiculo: str
    nomeVeiculo:  str | None = None
    ras_ins_id:   str | None = None
    idAparelho:   str | None = None
    idVeiculo:    str | None = None
    tipo:         int | None = None
    veiculoId:    int | None = None


@router.post("/adicionar")
async def adicionar_oficina(body: AdicionarOficinaInput):
    placa = body.placaVeiculo
    os_data = await harmonit_get("/OrdemServico/ObterOrdemServico", params={"osId": body.osId})
    numero_os = (os_data or {}).get("numeroOrdem") or 0

    async def registrar(resultado: str, sucesso: bool, verificado: bool = False):
        """Toda tentativa entra no historico da aba Oficinas -- e a falha e o que
        habilita o botao Resync (caso de uso: WESO fora do ar no disparo)."""
        await storage.marcar_oficina_processada(
            evento_id=body.rastreadorId, numero_os=numero_os, status=1,
            resultado=resultado, sucesso=sucesso, verificado_weso=verificado,
            placa=placa, equipamento_id=body.idAparelho, veiculo_nome=body.nomeVeiculo,
            origem="oficina_harmonit",
        )

    # 1. serial (cache local -> ao vivo)
    serial = await _resolver_serial(body.rastreadorId)
    if not serial:
        msg = f"Rastreador harmonit_id={body.rastreadorId} não encontrado nem no cache nem no Harmonit."
        log_req("os", "POST", "/weso/os/adicionar", None, None, placa, False, msg)
        await registrar(msg, sucesso=False)
        raise HTTPException(status_code=422, detail=msg)

    # 2. clienteId da OS -> cnpjcpf (cache local -> ao vivo)
    cliente_id = (os_data or {}).get("clienteId")
    if not cliente_id:
        msg = "clienteId não encontrado na OS Harmonit"
        log_req("os", "POST", "/weso/os/adicionar", None, None, placa, False, msg)
        await registrar(msg, sucesso=False)
        raise HTTPException(status_code=422, detail=msg)

    cnpjcpf = await _resolver_cnpjcpf(cliente_id)
    if not cnpjcpf:
        msg = f"Cliente harmonit_id={cliente_id} sem CNPJ/CPF — a WESO identifica cliente por documento."
        log_req("os", "POST", "/weso/os/adicionar", None, None, placa, False, msg)
        await registrar(msg, sucesso=False)
        raise HTTPException(status_code=422, detail=msg)

    # Interruptor de seguranca -- em producao, desligado por padrao ate
    # validarmos o fluxo (combinado com o usuario em 2026-07-16). Harmonit
    # sempre recebe o AdicionarOficina; so o disparo pra WESO fica condicionado.
    if (await storage.get_config("oficina_registro_ativo", "false")) != "true":
        log_req("os", "POST", "/weso/os/adicionar", "harmonit_only", None, placa, True, None)
        await registrar(f"[simulado] criaria vínculo WESO: placa={placa}, serial={serial}, cliente={cnpjcpf}",
                        sucesso=False)
        return {"ok": True, "acao": "harmonit_only", "id": None, "placa": placa, "erro": None}

    # 4. cria/atualiza vínculo no WESO
    payload = {
        "equipamento": {
            "placa": placa,
            "cliente": {"cnpjcpf": cnpjcpf},
            "rastreador": {"numeroSerie": serial},
            **({} if not body.nomeVeiculo else {"descricao": body.nomeVeiculo}),
        }
    }
    try:
        result = await weso_post("/Veiculos/Cadastro", payload, allow_409=True)
    except HTTPException as exc:
        # WESO fora do ar / timeout: fica no historico como falha, com Resync disponivel.
        msg = f"falha ao gravar na WESO: {exc.detail}"
        log_req("os", "POST", "/weso/os/adicionar", None, None, placa, False, msg)
        await registrar(msg, sucesso=False)
        raise
    acao = "ja_existe" if result.get("_ja_existe") else "criado"
    veiculo_id = result.get("id")
    if acao == "criado" and veiculo_id:
        await storage.salvar_veiculo(placa, veiculo_id)

    log_req("os", "POST", "/weso/os/adicionar", acao, veiculo_id, placa, True, None)
    await registrar(f"vínculo {acao} na WESO (veiculo_id={veiculo_id or 'já existia'})", sucesso=True)
    return {"ok": True, "acao": acao, "id": veiculo_id, "placa": placa, "erro": None}


@router.post("/desinstalar")
async def desinstalar_oficina(body: DesinstalarOficinaInput):
    placa = body.placaVeiculo
    os_data = await harmonit_get("/OrdemServico/ObterOrdemServico", params={"osId": body.osId})
    numero_os = (os_data or {}).get("numeroOrdem") or 0

    async def registrar(resultado: str, sucesso: bool, verificado: bool = False):
        await storage.marcar_oficina_processada(
            evento_id=body.rastreadorId, numero_os=numero_os, status=2,
            resultado=resultado, sucesso=sucesso, verificado_weso=verificado,
            placa=placa, equipamento_id=body.idAparelho, veiculo_nome=body.nomeVeiculo,
            origem="oficina_harmonit",
        )

    if (await storage.get_config("oficina_registro_ativo", "false")) != "true":
        log_req("os", "POST", "/weso/os/desinstalar", "harmonit_only", None, placa, True, None)
        await registrar(f"[simulado] apagaria vínculo WESO: placa={placa}", sucesso=False)
        return {"ok": True, "acao": "harmonit_only", "id": None, "placa": placa, "erro": None}

    # Cache local primeiro; se nao tiver, pergunta a WESO pela placa (mesma logica
    # que o oficina_router ja usava -- placa registrada por outro caminho ou seed antigo).
    registro = await storage.buscar_veiculo(placa)
    veiculo_id = registro["veiculo_id"] if registro else None
    if not veiculo_id:
        try:
            # Busca TOLERANTE a grafia: a consulta por placa e igualdade
            # exata e devolve vazio (nao erro) quando a WESO tem a placa com
            # espaco/caixa diferente -- ver weso_lookup e o plano 21.
            veiculo_id = await buscar_veiculo_id(placa)
        except HTTPException as exc:
            msg = f"falha ao consultar a WESO pela placa: {exc.detail}"
            log_req("os", "POST", "/weso/os/desinstalar", None, None, placa, False, msg)
            await registrar(msg, sucesso=False)
            raise
    if not veiculo_id:
        msg = f"Vínculo da placa '{placa}' não encontrado na WESO (nem no cache, nem consultando)."
        log_req("os", "POST", "/weso/os/desinstalar", None, None, placa, False, msg)
        await registrar(msg, sucesso=False)
        raise HTTPException(status_code=404, detail=msg)

    try:
        await weso_post("/Veiculos/Excluir", {"veiculo_id": veiculo_id})
    except HTTPException as exc:
        msg = f"falha ao remover na WESO: {exc.detail}"
        log_req("os", "POST", "/weso/os/desinstalar", None, None, placa, False, msg)
        await registrar(msg, sucesso=False)
        raise
    await storage.remover_veiculo(placa)
    log_req("os", "POST", "/weso/os/desinstalar", "excluido", veiculo_id, placa, True, None)
    await registrar(f"vínculo removido da WESO (veiculo_id={veiculo_id})", sucesso=True)
    return {"ok": True, "acao": "excluido", "id": veiculo_id, "placa": placa, "erro": None}
