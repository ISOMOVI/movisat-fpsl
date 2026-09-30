"""SO LEITURA. Levanta tudo sobre a OS 16972 antes de qualquer escrita:
osId, status, cliente, oficinas, materiais, e o cliente 'Moto Help Matriz'
na base viva do Harmonit (para achar o clienteId real).
"""
import asyncio
import json
import re

from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_post, harmonit_get)

NUM_OS = 16972


def j(x, n=4000):
    return json.dumps(x, ensure_ascii=False, indent=2)[:n]


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


async def main():
    await start_harmonit_client()
    try:
        print("=" * 78)
        print(f"1) OS {NUM_OS} — ObterOrdemServicoPorNumero")
        print("=" * 78)
        os_ = await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero",
                                 {"numeroOs": NUM_OS})
        o = os_ if isinstance(os_, dict) else (os_[0] if isinstance(os_, list) and os_ else {})
        print(j(o))
        osid = o.get("id") or o.get("osId")

        if not osid:
            print("\n!! nao achei osId -- parando aqui.")
            return

        print("\n" + "=" * 78)
        print(f"2) ObterOficinas(osId={osid})")
        print("=" * 78)
        of = await harmonit_get("/OrdemServico/ObterOficinas", {"osId": osid})
        itens = of if isinstance(of, list) else (of or {}).get("data") or []
        print(f"{len(itens)} registro(s)")
        print(j(itens))

        print("\n" + "=" * 78)
        print(f"3) ObterMateriaisOrdemServico(ordemServicoId={osid})")
        print("=" * 78)
        mats = await harmonit_get("/OrdemServico/ObterMateriaisOrdemServico",
                                  {"ordemServicoId": osid})
        mitens = mats if isinstance(mats, list) else (mats or {}).get("data") or []
        print(f"{len(mitens)} registro(s)")
        print(j(mitens))

        print("\n" + "=" * 78)
        print("4) Rastreador/Veiculo ligados ao que a OS descreve")
        print("=" * 78)
        placa_os = o.get("placa") or o.get("placaVeiculo")
        print(f"placa na OS: {placa_os!r}")
        if placa_os:
            rasts = await harmonit_post("/Rastreador/ObterRastreadores", {})
            rs = rasts if isinstance(rasts, list) else (rasts or {}).get("dados") or []
            achados = [x for x in rs if norm(x.get("placa")) == norm(placa_os)]
            print(f"{len(achados)} rastreador(es) com essa placa:")
            print(j(achados))

            veics = await harmonit_get("/Veiculo/ObterVeiculos", {})
            vs = veics if isinstance(veics, list) else (veics or {}).get("data") or []
            achados_v = [x for x in vs if norm(x.get("placa")) == norm(placa_os)]
            print(f"\n{len(achados_v)} veiculo(s) com essa placa:")
            print(j(achados_v))

        print("\n" + "=" * 78)
        print("5) Procurando cliente 'MOTO HELP' na base viva (paginado)")
        print("=" * 78)
        skip = 0
        achados_cli = []
        while True:
            r = await harmonit_get("/ObterClientes",
                                   {"skip": skip, "take": 100, "somenteAtivos": "false"})
            d = (r or {}).get("data") or {}
            lista = d.get("lista") or []
            if not lista:
                break
            achados_cli += [c for c in lista if "MOTO HELP" in norm(c.get("nome"))
                            or "MOTO HELP" in norm(c.get("nomeFantasia"))]
            if len(lista) < 100:
                break
            skip += 100
        print(f"{len(achados_cli)} cliente(s) 'MOTO HELP':")
        print(j(achados_cli))
    finally:
        await stop_harmonit_client()


asyncio.run(main())
