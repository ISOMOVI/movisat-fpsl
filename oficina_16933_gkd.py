"""Oficina de INSTALACAO do 907112547 (rast 10655) na placa GKD 3D08
(veic 86503, Moto Help Matriz 886302), na OS 16933.
AUTORIZADO 29/09 ("na OS 16933, vincule a oficina do ID 907112547 na placa GKD").

Guardas: OS existe; parceiro da OS = 886302; ainda nao ha oficina do
907112547 nela. Rele depois (o HTTP mente).
"""
import asyncio
import json

import httpx

from fpsl_weso import harmonit_client as hc
from fpsl_weso.config import settings
from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_post, harmonit_get)

NUM_OS = 16933
RAST = 10655
SERIAL = "907112547"
VEIC = 86503
PLACA = "GKD 3D08"
NOME_VEIC = "Anderson Fernandes Esporadico"
CLIENTE = 886302
EMPRESA = 98


async def oficinas(osid):
    of = await harmonit_get("/OrdemServico/ObterOficinas", {"osId": osid})
    return of if isinstance(of, list) else (of or {}).get("data") or []


async def rast():
    d = await harmonit_post("/Rastreador/ObterRastreadores", {})
    rs = d if isinstance(d, list) else (d or {}).get("dados") or []
    return next(x for x in rs if x.get("id") == RAST)


async def main():
    await start_harmonit_client()
    try:
        o = await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero", {"numeroOs": NUM_OS})
        o = o if isinstance(o, dict) else (o[0] if isinstance(o, list) and o else {})
        osid = o.get("id")
        print(f"OS {NUM_OS}: osId={osid} status={o.get('statusStr')!r} parceiro={o.get('parceiro')} "
              f"produto={o.get('produtoDescricao')!r}")
        print(f"   descricao: {o.get('descricao')!r}")
        if not osid:
            print("!! PARANDO: OS nao encontrada")
            return
        if o.get("parceiro") != CLIENTE:
            print(f"!! PARANDO: o cliente da OS e {o.get('parceiro')}, nao {CLIENTE} (Moto Help Matriz)")
            return

        of0 = await oficinas(osid)
        print(f"oficinas ANTES: {len(of0)}")
        for x in of0:
            print("   " + json.dumps(x, ensure_ascii=False))
        if any(str(x.get("equipamentoId")) == SERIAL for x in of0):
            print("!! PARANDO: ja existe oficina do 907112547 nesta OS")
            return

        r0 = await rast()
        print(f"rast ANTES: instalado={r0.get('instalado')} veiculoId={r0.get('veiculoId')} "
              f"placa={r0.get('placa')!r} contato={r0.get('contato')!r}")

        corpo = {"empresaId": EMPRESA, "osId": osid,
                 "tipoVeic": 1, "tipo": 1,
                 "idAparelho": SERIAL,
                 "idVeiculo": str(VEIC),
                 "rastreadorId": RAST,
                 "placaVeiculo": PLACA,
                 "nomeVeiculo": NOME_VEIC,
                 "trocaOficinaAntigaId": 0}
        print(f"\nPOST /OrdemServico/AdicionarOficina {json.dumps(corpo, ensure_ascii=False)}")
        async with httpx.AsyncClient(base_url=settings.harmonit_base_url, timeout=90) as c:
            resp = await c.post("/OrdemServico/AdicionarOficina", headers=hc._headers(), json=corpo)
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")

        of1 = await oficinas(osid)
        print(f"\noficinas DEPOIS: {len(of1)}")
        for x in of1:
            print("   " + json.dumps(x, ensure_ascii=False))
        r1 = await rast()
        print(f"rast DEPOIS: instalado={r1.get('instalado')} veiculoId={r1.get('veiculoId')} "
              f"placa={r1.get('placa')!r} contato={r1.get('contato')!r}")
        nova = [x for x in of1 if x not in of0]
        print(f"\n>>> oficina gravada? {'SIM' if nova else 'NAO'}")
    finally:
        await stop_harmonit_client()


asyncio.run(main())
