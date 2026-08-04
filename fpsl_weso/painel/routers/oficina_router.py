"""Rotas do painel para sincronizar Oficina (Harmonit) -> vinculo (WESO)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import requer_aba
from ...harmonit_client import harmonit_get
from ...client import weso_get, weso_post
from ...services.resolucao import resolver_cnpjcpf
from ... import storage

router = APIRouter(prefix="/painel/api/oficina", tags=["painel-oficina"])


# A busca por número de OS foi REMOVIDA em 2026-07-22. A oficina é o gatilho:
# registrar a oficina no Harmonit dispara a gravação na WESO (`routers/os.py`,
# `/weso/os/adicionar` e `/desinstalar`). Esta aba é só o histórico -- e o Resync,
# pra quando a WESO estiver fora do ar na hora do disparo.
# NÃO reintroduzir busca por OS, varredura, polling nem cron. Decisão fechada.


async def _verificar_weso(placa: str, deve_existir: bool, veiculo_id: int | None) -> bool:
    """Reconfere direto na WESO depois da escrita -- achado 2026-07-03/16:
    respostas da WESO (e do Harmonit) não são sempre confiáveis (`PUT
    /SIMCard/Atualizar` já retornou 200 sem persistir; `{"status": false}` do
    Harmonit também não é garantia de falha real). Nunca bloqueia o resultado
    -- só marca `verificado_weso` pra dar visibilidade na aba de auditoria."""
    try:
        consulta = await weso_get("/Veiculos/Consultar", {"placa": placa})
    except HTTPException:
        return False
    achados = consulta.get("veiculos") or []
    if deve_existir:
        if veiculo_id:
            return any(str(a.get("id")) == str(veiculo_id) for a in achados)
        return bool(achados)
    return not achados


async def _sincronizar_evento(ev: dict, cliente_id: int) -> dict:
    """Processa 1 evento de oficina -- retorna {"resultado": str, "foi_real": bool,
    "verificado_weso": bool}. Lanca excecao em erro (o chamador persiste como falha)."""
    ativo = (await storage.get_config("oficina_registro_ativo", "false")) == "true"
    placa = ev["veiculoPlaca"]

    if ev["status"] == 1:
        # Cache local -> ao vivo (2026-07-22). Antes era só a tabela local e
        # o erro era "rode o seed", o que quebrava cliente cadastrado depois
        # do último seed. Ver services/resolucao.py.
        cnpjcpf = await resolver_cnpjcpf(cliente_id)
        if not cnpjcpf:
            raise HTTPException(422, f"Cliente harmonit_id={cliente_id} sem CNPJ/CPF — a WESO identifica cliente por documento.")
        if not ativo:
            return {"resultado": f"[simulado] criaria vínculo WESO: placa={placa}, serial={ev['equipamentoId']}, cliente={cnpjcpf}", "foi_real": False, "verificado_weso": False}
        payload = {
            "equipamento": {
                "placa": placa,
                "cliente": {"cnpjcpf": cnpjcpf},
                "rastreador": {"numeroSerie": ev["equipamentoId"]},
                **({} if not ev.get("veiculoNome") else {"descricao": ev["veiculoNome"]}),
            }
        }
        result = await weso_post("/Veiculos/Cadastro", payload, allow_409=True)
        veiculo_id = result.get("id")
        if veiculo_id:
            await storage.salvar_veiculo(placa, veiculo_id)
        verificado = await _verificar_weso(placa, deve_existir=True, veiculo_id=veiculo_id)
        return {"resultado": f"vínculo criado/atualizado na WESO (veiculo_id={veiculo_id or 'já existia'})", "foi_real": True, "verificado_weso": verificado}

    if ev["status"] == 2:
        registro = await storage.buscar_veiculo(placa)
        veiculo_id = registro["veiculo_id"] if registro else None
        if not veiculo_id:
            consulta = await weso_get("/Veiculos/Consultar", {"placa": placa})
            achados = consulta.get("veiculos") or []
            if achados:
                veiculo_id = achados[0]["id"]
        if not veiculo_id:
            raise HTTPException(422, f"Vínculo da placa '{placa}' não encontrado na WESO (nem local, nem consultando por placa) -- verifique manualmente.")
        if not ativo:
            return {"resultado": f"[simulado] apagaria vínculo WESO: placa={placa}, veiculo_id={veiculo_id}", "foi_real": False, "verificado_weso": False}
        await weso_post("/Veiculos/Excluir", {"veiculo_id": veiculo_id})
        await storage.remover_veiculo(placa)
        verificado = await _verificar_weso(placa, deve_existir=False, veiculo_id=None)
        return {"resultado": f"vínculo removido da WESO (veiculo_id={veiculo_id})", "foi_real": True, "verificado_weso": verificado}

    raise HTTPException(422, f"status de oficina desconhecido: {ev['status']}")


@router.post("/resync/{registro_id}")
async def resync(registro_id: int, _=Depends(requer_aba("oficinas"))):
    """Reprocessa UMA tentativa que falhou -- o caso de uso é a WESO estar fora do
    ar na hora em que a oficina foi registrada no Harmonit.

    **Confere antes de refazer.** A resposta da WESO não é confiável (achado
    2026-07-03/16: `PUT /SIMCard/Atualizar` já devolveu 200 sem persistir), então
    um timeout não significa que não gravou. Reconsulta a WESO primeiro: se o
    vínculo já está no estado certo, marca como resolvido e NÃO reenvia -- é o que
    evita criar vínculo duplicado a cada clique."""
    reg = await storage.buscar_oficina_historico(registro_id)
    if not reg:
        raise HTTPException(404, "Registro de histórico não encontrado")
    if reg["sucesso"]:
        raise HTTPException(409, "Esse registro já foi concluído com sucesso — nada a refazer.")
    if not reg["placa"]:
        raise HTTPException(422, "Registro antigo, sem placa gravada — não é possível reprocessar automaticamente.")

    deve_existir = reg["status"] == 1  # 1=instalação (deve existir na WESO), 2=desinstalação (não deve)
    ja_esta_certo = await _verificar_weso(reg["placa"], deve_existir=deve_existir, veiculo_id=None)
    if ja_esta_certo:
        novo_id = await storage.marcar_oficina_processada(
            reg["evento_id"], reg["numero_os"], reg["status"],
            "resync: já estava correto na WESO (a gravação original tinha ido, o erro foi só na resposta) — nada reenviado",
            sucesso=True, verificado_weso=True, placa=reg["placa"],
            equipamento_id=reg["equipamento_id"], veiculo_nome=reg["veiculo_nome"], origem="resync",
        )
        return {"ok": True, "acao": "ja_estava_certo", "registro_id": novo_id}

    ev = {
        "id": reg["evento_id"], "status": reg["status"], "veiculoPlaca": reg["placa"],
        "equipamentoId": reg["equipamento_id"], "veiculoNome": reg["veiculo_nome"],
    }
    os_data = await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero", params={"numeroOs": reg["numero_os"]})
    cliente_id = (os_data or {}).get("parceiro")
    try:
        r = await _sincronizar_evento(ev, cliente_id)
        novo_id = await storage.marcar_oficina_processada(
            reg["evento_id"], reg["numero_os"], reg["status"], f"resync: {r['resultado']}",
            sucesso=r["foi_real"], verificado_weso=r["verificado_weso"], placa=reg["placa"],
            equipamento_id=reg["equipamento_id"], veiculo_nome=reg["veiculo_nome"], origem="resync",
        )
        return {"ok": True, "acao": "reenviado", "resultado": r["resultado"],
                "verificado_weso": r["verificado_weso"], "registro_id": novo_id}
    except HTTPException as exc:
        erro_txt = str(exc.detail)
        novo_id = await storage.marcar_oficina_processada(
            reg["evento_id"], reg["numero_os"], reg["status"], f"resync falhou: {erro_txt}",
            sucesso=False, placa=reg["placa"], equipamento_id=reg["equipamento_id"],
            veiculo_nome=reg["veiculo_nome"], origem="resync",
        )
        return {"ok": False, "acao": "falhou", "erro": erro_txt, "registro_id": novo_id}


@router.get("/historico")
async def historico(limit: int = Query(200, le=500), _=Depends(requer_aba("oficinas"))):
    """Histórico geral (todas as OS já sincronizadas), pra aba de auditoria."""
    return await storage.listar_historico_oficinas(limit)


class ToggleInput(BaseModel):
    ativo: bool


@router.get("/config/ativo")
async def obter_toggle(_=Depends(requer_aba("config"))):
    valor = await storage.get_config("oficina_registro_ativo", "false")
    return {"ativo": valor == "true"}


@router.put("/config/ativo")
async def definir_toggle(body: ToggleInput, _=Depends(requer_aba("config"))):
    await storage.set_config("oficina_registro_ativo", "true" if body.ativo else "false")
    return {"ok": True, "ativo": body.ativo}
