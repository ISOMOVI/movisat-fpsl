"""Verificacao ao vivo da Conferencia de Fechamento (29/09).

1) roda a rotina uma vez e mostra o resultado
2) lista o que foi gravado em conferencia_fechamento
3) testa direto a OS 16450 (caso de referencia ja confirmado pelos agentes:
   equipamento retirado -> Estoque, equipamento instalado -> Instalado) --
   mesmo que ela caia fora da janela de 400, para provar a logica de
   cruzamento em si, independente da janela de deteccao.
"""
import asyncio
import json

from fpsl_weso import storage
from fpsl_weso.harmonit_client import start_harmonit_client, stop_harmonit_client, harmonit_get
from fpsl_weso.client import start_client, stop_client
from fpsl_weso.datascope_client import start_datascope_client, stop_datascope_client
from fpsl_weso.services import conferencia_fechamento as cf


def _unwrap(r):
    d = r.get("data") if (isinstance(r, dict) and r.get("data")) else r
    return d[0] if isinstance(d, list) else d


async def main():
    storage.init_db()
    await start_client()
    await start_harmonit_client()
    await start_datascope_client()
    try:
        print("=" * 74)
        print("1) rodando a conferencia uma vez")
        print("=" * 74)
        r = await cf.run_conferencia()
        print(json.dumps(r, ensure_ascii=False))

        print("\n" + "=" * 74)
        print("2) o que esta em conferencia_fechamento agora")
        print("=" * 74)
        itens = await storage.listar_conferencia_fechamento(50)
        print(f"{len(itens)} linha(s)")
        for i in itens:
            print("   " + json.dumps(i, ensure_ascii=False))

        print("\n" + "=" * 74)
        print("3) teste direto contra a OS 16450 (caso de referencia)")
        print("=" * 74)
        d = _unwrap(await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero",
                                       params={"numeroOs": 16450}))
        print(f"statusStr: {d.get('statusStr')!r}")
        oficinas = d.get("oficina") or []
        print(f"oficinas: {json.dumps(oficinas, ensure_ascii=False)}")
        weso_ok, motivo = await cf._checar_weso(oficinas)
        print(f"weso_ok={weso_ok} motivo={motivo!r}")

        resposta = await storage.resposta_datascope_por_os(16450)
        ds_ok, estado, motivo_ds = cf._checar_datascope(16450, resposta)
        print(f"datascope: resposta={resposta} -> ok={ds_ok} estado={estado!r} motivo={motivo_ds!r}")
    finally:
        await stop_datascope_client()
        await stop_harmonit_client()
        await stop_client()


asyncio.run(main())
