import asyncio
import re
import sys
sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso import harmonit_client as hc

ALVO_PLACA = "EPW 0I21"


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


async def main():
    await hc.start_harmonit_client()
    try:
        v = await hc.harmonit_get("/Veiculo/ObterVeiculos", {})
        veiculos = v if isinstance(v, list) else (v or {}).get("data") or []
        print(f"total de veiculos: {len(veiculos)}")

        alvo_norm = norm(ALVO_PLACA)
        achados = [x for x in veiculos if norm(x.get("placa")) == alvo_norm]
        print(f"veiculos com placa {ALVO_PLACA!r}: {len(achados)}")
        for x in achados:
            for k in sorted(x.keys()):
                print(f"    {k}: {x[k]!r}")
            print()

        # tambem confere se o id 10655 do rastreador aponta a algum
        # veiculoId != 0 hoje (o registro anterior mostrou veiculoId: 0)
        r = await hc.harmonit_post("/Rastreador/ObterRastreadores", {})
        rastreadores = r if isinstance(r, list) else (r or {}).get("data") or []
        rast = next((x for x in rastreadores if x.get("id") == 10655), None)
        print("rastreador id 10655 agora:")
        print(f"  {rast!r}")
    finally:
        await hc.stop_harmonit_client()


asyncio.run(main())
