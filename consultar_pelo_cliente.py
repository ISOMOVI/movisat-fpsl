"""SO LEITURA. Onde o 907112547 aparece, visto por cliente."""
import asyncio
import json

from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_post, harmonit_get)

SERIAL = "907112547"
CLIENTES = {886302: "MOTO HELP MATRIZ", 60743: "COLONIAL"}


async def main():
    await start_harmonit_client()
    try:
        d = await harmonit_post("/Rastreador/ObterRastreadores", {})
        rs = d if isinstance(d, list) else (d or {}).get("dados") or []
        v = await harmonit_get("/Veiculo/ObterVeiculos", {})
        vs = v if isinstance(v, list) else (v or {}).get("data") or []
        vid = {x.get("id"): x for x in vs}

        r = next(x for x in rs if str(x.get("equipamento")) == SERIAL)
        print("RASTREADOR:")
        print("   " + json.dumps(r, ensure_ascii=False))
        ve = vid.get(r.get("veiculoId"))
        if ve:
            print(f"   veiculo ligado: id={ve['id']} placa={ve.get('placa')!r} "
                  f"cliente={ve.get('cliente')!r} clienteId={ve.get('clienteId')}")

        for cid, rotulo in CLIENTES.items():
            print(f"\n=== {rotulo} ({cid}) ===")
            veics = [x for x in vs if x.get("clienteId") == cid]
            ids = {x["id"] for x in veics}
            rasts = [x for x in rs if x.get("veiculoId") in ids]
            print(f"   veiculos: {len(veics)} | rastreadores ligados a eles: {len(rasts)}")
            nosso = [x for x in rasts if str(x.get("equipamento")) == SERIAL]
            print(f"   907112547 aparece pelos veiculos? {'SIM' if nosso else 'NAO'}")
            por_contato = [x for x in rs if (x.get("contato") or "").upper().startswith(
                "MOTO HELP" if cid == 886302 else "COLONIAL")]
            print(f"   rastreadores com contato deste cliente: {len(por_contato)}")
            print(f"   907112547 aparece pelo contato? "
                  f"{'SIM' if any(str(x.get('equipamento')) == SERIAL for x in por_contato) else 'NAO'}")

        o = await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero", {"numeroOs": 16933})
        o = o if isinstance(o, dict) else (o[0] if isinstance(o, list) and o else {})
        print(f"\nOS 16933: status={o.get('statusStr')!r}")
    finally:
        await stop_harmonit_client()


asyncio.run(main())
