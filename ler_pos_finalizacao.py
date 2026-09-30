"""SO LEITURA. Estado da OS 16972 e do rastreador 10655 depois da finalizacao."""
import asyncio
import json

from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_post, harmonit_get)

OSID = 898322
RAST = 10655
VEIC = 6251


async def main():
    await start_harmonit_client()
    try:
        o = await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero", {"numeroOs": 16972})
        o = o if isinstance(o, dict) else (o[0] if isinstance(o, list) and o else {})
        print(f"OS 16972: status={o.get('status')} statusStr={o.get('statusStr')!r} "
              f"parceiro={o.get('parceiro')}")

        of = await harmonit_get("/OrdemServico/ObterOficinas", {"osId": OSID})
        of = of if isinstance(of, list) else (of or {}).get("data") or []
        print(f"oficinas: {len(of)}")
        for x in of:
            print("   " + json.dumps(x, ensure_ascii=False))

        d = await harmonit_post("/Rastreador/ObterRastreadores", {})
        rs = d if isinstance(d, list) else (d or {}).get("dados") or []
        r = next((x for x in rs if x.get("id") == RAST), None)
        print(f"\nrastreador {RAST}:")
        print("   " + json.dumps(r, ensure_ascii=False))

        v = await harmonit_get("/Veiculo/ObterVeiculos", {})
        vs = v if isinstance(v, list) else (v or {}).get("data") or []
        ve = next((x for x in vs if x.get("id") == VEIC), None)
        print(f"\nveiculo {VEIC}: placa={ve.get('placa')!r} cliente={ve.get('cliente')!r} "
              f"clienteId={ve.get('clienteId')}")
        outros = [x for x in rs if x.get("veiculoId") == VEIC]
        print(f"rastreadores apontando para o veiculo {VEIC}: {len(outros)}")
        for x in outros:
            print(f"   id={x.get('id')} equip={x.get('equipamento')!r} instalado={x.get('instalado')}")

        t = await harmonit_get("/OrdemServico/ObterTimeLine", {"osId": OSID})
        ti = t if isinstance(t, list) else (t or {}).get("data") or []
        print(f"\ntimeline: {len(ti)} evento(s)")
        for x in ti:
            print(f"   {x.get('data')} | {x.get('statusDesc')} | {x.get('usuario')}")
    finally:
        await stop_harmonit_client()


asyncio.run(main())
