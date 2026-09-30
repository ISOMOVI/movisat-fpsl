"""SO LEITURA. Qual veiculo da WESO segura o rastreador 8527 (907112547)."""
import asyncio
import json
import re

from fpsl_weso.client import weso_get, start_client, stop_client

RID = 8527


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


async def main():
    await start_client()
    try:
        for grafia in ("EPW 0I21", "EPW-0I21", "EPW0I21"):
            v = await weso_get("/Veiculos/Consultar", {"placa": grafia})
            vs = (v.get("veiculos") if isinstance(v, dict) else v) or []
            print(f"placa {grafia!r}: {len(vs)}")
            for x in vs:
                print(json.dumps(x, ensure_ascii=False)[:1500])

        v = await weso_get("/Veiculos/Consultar", {})
        vs = (v.get("veiculos") if isinstance(v, dict) else v) or []
        print(f"\ntotal de veiculos na WESO: {len(vs)}")
        donos = [x for x in vs if RID in json.dumps(x) and
                 (str(RID) in json.dumps(x.get("rastreador") or x.get("rastreadores") or ""))]
        parecidos = [x for x in vs if norm(x.get("placa")).startswith("EPW0I2")]
        print(f"veiculos que citam o rastreador {RID}: {len(donos)}")
        for x in donos:
            print(json.dumps(x, ensure_ascii=False)[:1500])
        print(f"placas parecidas com EPW0I2*: {len(parecidos)}")
        for x in parecidos:
            print(json.dumps(x, ensure_ascii=False)[:1500])
        if vs:
            print("\nchaves de um veiculo:", list(vs[0].keys()))
    finally:
        await stop_client()


asyncio.run(main())
