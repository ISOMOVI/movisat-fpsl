"""SO LEITURA. Por que o 907112547 nao pode ser usado: WESO + Harmonit."""
import asyncio
import json
import re

from fpsl_weso.client import weso_get, start_client, stop_client
from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_post)

SERIE = "907112547"
ICCID = "8955170000200467554"


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def j(x):
    return json.dumps(x, ensure_ascii=False, indent=2)[:3000]


async def main():
    await start_client()
    print("=== WESO: rastreador ===")
    r = await weso_get("/Rastreadores/Consultar", {"numeroSerie": SERIE})
    lst = (r.get("rastreadores") if isinstance(r, dict) else r) or []
    alvo = [t for t in lst if str(t.get("numeroSerie")) == SERIE]
    print(j(alvo or lst[:3]))

    print("\n=== WESO: veiculos com placa EPW 0I21 ou com esse rastreador ===")
    v = await weso_get("/Veiculos/Consultar", {"placa": "EPW0I21"})
    vs = (v.get("veiculos") if isinstance(v, dict) else v) or []
    print(j(vs))

    await start_harmonit_client()
    try:
        print("\n=== Harmonit: SIM Card 10655 e o ICCID antigo ===")
        s = await harmonit_post("/SIMCard/ObterSIMCards", {})
        ss = s if isinstance(s, list) else (s or {}).get("lista") or (s or {}).get("dados") or []
        for x in ss:
            if x.get("id") == 10655 or norm(x.get("numeroChip")) == ICCID \
                    or ICCID in norm(x.get("numeroChip")):
                print(j(x))
    finally:
        await stop_harmonit_client()


asyncio.run(main())
