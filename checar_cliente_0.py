import asyncio
import json
import re

from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_get)


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


async def main():
    await start_harmonit_client()
    try:
        print("=== /ObterCliente Id=0 ===")
        r = await harmonit_get("/ObterCliente", {"Id": 0})
        print(json.dumps(r, ensure_ascii=False, indent=2)[:1500])

        print("\n=== /ObterClientes primeira pagina (sem double-unwrap) ===")
        r2 = await harmonit_get("/ObterClientes",
                                {"skip": 0, "take": 5, "somenteAtivos": "true"})
        print("chaves do retorno:", list((r2 or {}).keys()))
        print("sumario:", json.dumps((r2 or {}).get("sumario"), ensure_ascii=False))
        lista = (r2 or {}).get("lista") or []
        print(f"lista: {len(lista)} item(ns)")
        if lista:
            print(json.dumps(lista[0], ensure_ascii=False, indent=2)[:800])

        print("\n=== paginando tudo (ativos e inativos) atras de MOTO HELP ===")
        achados = []
        skip = 0
        total_visto = 0
        for somente in ("true", "false"):
            skip = 0
            while True:
                rr = await harmonit_get(
                    "/ObterClientes",
                    {"skip": skip, "take": 100, "somenteAtivos": somente})
                lista = (rr or {}).get("lista") or []
                if not lista:
                    break
                total_visto += len(lista)
                achados += [c for c in lista if "MOTOHELP" in norm(c.get("nome"))
                            or "MOTOHELP" in norm(c.get("nomeFantasia"))
                            or "MOTO HELP" in (c.get("nome") or "").upper()
                            or "MOTO HELP" in (c.get("nomeFantasia") or "").upper()]
                sumario = (rr or {}).get("sumario") or {}
                contador_total = sumario.get("contador", 0)
                skip += 100
                if skip >= contador_total or contador_total == 0:
                    break
        print(f"total de linhas vistas (ativos+inativos, com duplicidade entre os dois): {total_visto}")
        print(f"achados 'MOTO HELP': {len(achados)}")
        print(json.dumps(achados, ensure_ascii=False, indent=2)[:3000])
    finally:
        await stop_harmonit_client()


asyncio.run(main())
