import asyncio
import json

from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_get, harmonit_post)


async def main():
    await start_harmonit_client()
    try:
        v = await harmonit_get("/Veiculo/ObterVeiculos", {})
        veiculos = v if isinstance(v, list) else (v or {}).get("data") or []
        print(f"total de veiculos: {len(veiculos)}")

        sem_cliente_id = [x for x in veiculos if not x.get("clienteId")]
        print(f"veiculos com clienteId vazio/0/None: {len(sem_cliente_id)}")
        for x in sem_cliente_id[:5]:
            print(f"   id={x.get('id')} placa={x.get('placa')!r} clienteId={x.get('clienteId')!r} "
                  f"cliente={x.get('cliente')!r}")

        moto_help = [x for x in veiculos if x.get("clienteId") == 886302]
        print(f"\nveiculos com clienteId == 886302 (Moto Help Matriz): {len(moto_help)}")
        for x in moto_help[:10]:
            print(f"   id={x.get('id')} placa={x.get('placa')!r} veiculo={x.get('veiculo')!r} "
                  f"cliente={x.get('cliente')!r}")

        # confere tambem pelos rastreadores: quantos tem veiculoId=0 (sem veiculo)
        r = await harmonit_post("/Rastreador/ObterRastreadores", {})
        rasts = r if isinstance(r, list) else (r or {}).get("dados") or []
        sem_veic = [x for x in rasts if not x.get("veiculoId")]
        print(f"\nrastreadores com veiculoId vazio/0: {len(sem_veic)} de {len(rasts)}")
        for x in sem_veic[:5]:
            print(f"   id={x.get('id')} equip={x.get('equipamento')!r} "
                  f"contato={x.get('contato')!r} instalado={x.get('instalado')}")
    finally:
        await stop_harmonit_client()


asyncio.run(main())
