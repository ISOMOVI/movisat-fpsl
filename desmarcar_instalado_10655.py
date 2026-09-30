"""Inverte instalado=true -> false no rastreador 10655 (907112547). AUTORIZADO 29/09 ("inverta o true, da instalado").

AUTORIZADO pelo usuario em 2026-09-29 ("pode fazer nesse mesmo").
PUT /Rastreador/Atualizar com veiculoId explicito (0), placa e veiculo em
branco -- mesmo formato de corrigir_vinculos.py. numeroChip/numeroLinha vao
junto (omitir apaga o ICCID). Relê depois e confere se a base de veiculos
cresceu (duplicata).
"""
import asyncio
import json

import httpx

from fpsl_weso import harmonit_client as hc
from fpsl_weso.config import settings
from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_post, harmonit_get)

RAST = 10655


async def estado():
    d = await harmonit_post("/Rastreador/ObterRastreadores", {})
    rs = d if isinstance(d, list) else (d or {}).get("dados") or []
    v = await harmonit_get("/Veiculo/ObterVeiculos", {})
    vs = v if isinstance(v, list) else (v or {}).get("data") or []
    return next((x for x in rs if x.get("id") == RAST), None), vs


async def main():
    await start_harmonit_client()
    try:
        r0, vs0 = await estado()
        print(f"ANTES : {json.dumps(r0, ensure_ascii=False)}")
        print(f"veiculos na base: {len(vs0)}")
        ids0 = {x.get("id") for x in vs0}

        corpo = {"id": RAST,
                 "modeloEquipamentoId": r0.get("modeloEquipamentoId"),
                 "modeloEquipamento": r0.get("modeloEquipamento"),
                 "equipamento": r0.get("equipamento"),
                 "simCardId": r0.get("simCardId") or 0,
                 "numeroChip": r0.get("numeroChip") or "",
                 "numeroLinha": r0.get("numeroLinha") or "",
                 "veiculoId": 0,
                 "placa": " ",
                 "veiculo": " ",
                 "instalado": False,
                 "ativar": False}
        print(f"\nPUT /Rastreador/Atualizar {json.dumps(corpo, ensure_ascii=False)}")
        async with httpx.AsyncClient(base_url=settings.harmonit_base_url,
                                     timeout=90) as c:
            resp = await c.put("/Rastreador/Atualizar", headers=hc._headers(), json=corpo)
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")

        r1, vs1 = await estado()
        print(f"\nDEPOIS: {json.dumps(r1, ensure_ascii=False)}")
        print(f"veiculos na base: {len(vs0)} -> {len(vs1)}")
        novos = [x for x in vs1 if x.get("id") not in ids0]
        if novos:
            print("!! DUPLICATA CRIADA:")
            for x in novos:
                print("   " + json.dumps(x, ensure_ascii=False))
        else:
            print("nenhum veiculo novo criado")
    finally:
        await stop_harmonit_client()


asyncio.run(main())
