"""Tradução de identificadores Harmonit -> WESO, com cache local.

Harmonit identifica por ID interno (`clienteId`, `rastreadorId`); a WESO
identifica por documento (`cnpjcpf`) e por número de série. As tabelas locais
`clientes` e `rastreadores` fazem essa ponte.

**Mudança de 2026-07-22:** antes essas tabelas eram a ÚNICA fonte -- não achou,
devolvia 422 "cadastre o cliente/equipamento antes". Isso derrubava qualquer
instalação em equipamento cadastrado no Harmonit depois do último seed (entraram
2 rastreadores em 6 dias, medido em 22/07). Agora são CACHE: no miss, busca ao
vivo no Harmonit e grava. O seed deixa de precisar de rotina de atualização.

Decidido com o usuário em 2026-07-22 ("segundo caminho é melhor").
"""
from ..harmonit_client import harmonit_get, harmonit_post
from .. import storage


async def resolver_serial(rastreador_id: int) -> str | None:
    """rastreadorId (Harmonit) -> numeroSerie (WESO)."""
    reg = await storage.buscar_rastreador(rastreador_id)
    if reg:
        return reg["serial"]
    # O Harmonit não tem get-por-id de rastreador -- só a listagem completa, e
    # ela é POST (GET devolve 405). Como o miss é raro, aproveita a ida e
    # reidrata o cache inteiro de uma vez, em vez de só o registro procurado.
    lista = await harmonit_post("/Rastreador/ObterRastreadores", {})
    achado = None
    for item in lista:
        serial = (item.get("equipamento") or "").strip()
        if not serial:
            continue
        await storage.salvar_rastreador(item["id"], serial)
        if item["id"] == rastreador_id:
            achado = serial
    return achado


async def resolver_cnpjcpf(cliente_id: int) -> str | None:
    """clienteId (Harmonit) -> cnpjcpf (WESO). Devolve None se o cliente não tem
    documento -- nesse caso não há o que gravar na WESO mesmo (ela identifica
    cliente por documento). Em 22/07 eram 32 clientes nessa situação."""
    reg = await storage.buscar_cliente(cliente_id)
    if reg:
        return reg["cnpjcpf"]
    dados = await harmonit_get("/ObterCliente", params={"Id": cliente_id})
    if isinstance(dados, list):
        dados = dados[0] if dados else None
    doc = ((dados or {}).get("cnpJ_CPF") or (dados or {}).get("cnpjCpf") or "").strip()
    if not doc:
        return None
    await storage.salvar_cliente(cliente_id, doc)
    return doc
