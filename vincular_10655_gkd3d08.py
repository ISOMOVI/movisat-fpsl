"""Vincula o rastreador 10655 (907112547) ao veiculo de placa GKD 3D08
(Moto Help Matriz, cliente 886302). AUTORIZADO 29/09 ("tente vincular a placa
GKD 3D08 que e da moto help matriz - 0").

Formato de corrigir_vinculos.py: veiculoId EXPLICITO + placa/veiculo iguais
aos do veiculo (sem veiculoId o Harmonit cria veiculo -- 27/07).
Guardas: 1 veiculo so com a placa, cliente 886302, nenhum outro rastreador
nele. Rele e confere contagem de veiculos.
"""
import asyncio
import json
import re

import httpx

from fpsl_weso import harmonit_client as hc
from fpsl_weso.config import settings
from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_post, harmonit_get)

RAST = 10655
PLACA = "GKD 3D08"
CLIENTE = 886302


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


async def estado():
    d = await harmonit_post("/Rastreador/ObterRastreadores", {})
    rs = d if isinstance(d, list) else (d or {}).get("dados") or []
    v = await harmonit_get("/Veiculo/ObterVeiculos", {})
    vs = v if isinstance(v, list) else (v or {}).get("data") or []
    return rs, vs


async def main():
    await start_harmonit_client()
    try:
        rs, vs = await estado()
        r0 = next(x for x in rs if x.get("id") == RAST)
        print(f"ANTES rast: {json.dumps(r0, ensure_ascii=False)}")
        print(f"veiculos na base: {len(vs)}")

        alvos = [x for x in vs if norm(x.get("placa")) == norm(PLACA)]
        print(f"\nveiculos com placa {PLACA!r}: {len(alvos)}")
        for x in alvos:
            print("   " + json.dumps(x, ensure_ascii=False))
        if len(alvos) != 1:
            print("!! PARANDO: esperava exatamente 1 veiculo com a placa")
            return
        v = alvos[0]
        if v.get("clienteId") != CLIENTE:
            print(f"!! PARANDO: o veiculo e do cliente {v.get('clienteId')} "
                  f"({v.get('cliente')!r}), nao do {CLIENTE}")
            return
        outros = [x for x in rs if x.get("veiculoId") == v["id"]]
        if outros:
            print("!! PARANDO: o veiculo ja tem rastreador:")
            for x in outros:
                print("   " + json.dumps(x, ensure_ascii=False))
            return

        corpo = {"id": RAST,
                 "modeloEquipamentoId": r0.get("modeloEquipamentoId"),
                 "modeloEquipamento": r0.get("modeloEquipamento"),
                 "equipamento": r0.get("equipamento"),
                 "simCardId": r0.get("simCardId") or 0,
                 "numeroChip": r0.get("numeroChip") or "",
                 "numeroLinha": r0.get("numeroLinha") or "",
                 "veiculoId": v["id"],
                 "placa": v.get("placa") or " ",
                 "veiculo": v.get("veiculo") or " "}
        print(f"\nPUT /Rastreador/Atualizar {json.dumps(corpo, ensure_ascii=False)}")
        async with httpx.AsyncClient(base_url=settings.harmonit_base_url,
                                     timeout=90) as c:
            resp = await c.put("/Rastreador/Atualizar", headers=hc._headers(), json=corpo)
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")

        rs2, vs2 = await estado()
        r1 = next(x for x in rs2 if x.get("id") == RAST)
        print(f"\nDEPOIS rast: {json.dumps(r1, ensure_ascii=False)}")
        print(f"veiculos na base: {len(vs)} -> {len(vs2)}")
        ids0 = {x.get("id") for x in vs}
        novos = [x for x in vs2 if x.get("id") not in ids0]
        if novos:
            print("!! DUPLICATA CRIADA:")
            for x in novos:
                print("   " + json.dumps(x, ensure_ascii=False))
        print(f"\n>>> vinculou? {'SIM' if r1.get('veiculoId') == v['id'] else 'NAO'}")
    finally:
        await stop_harmonit_client()


asyncio.run(main())
