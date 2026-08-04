"""Qual campo faz o /Veiculos/Cadastro devolver 400? Bisseccao. (2026-07-27)

O 400 vem SEM corpo de erro ('Bad Request' seco), entao a unica saida e isolar:
vai acrescentando um bloco por vez e ve onde quebra. Cada tentativa usa placa e
serial proprios pra nao colidir com a anterior.

Limpa o que criar (a WESO tem DELETE real nos 3).
"""
import asyncio
import json

import httpx

from fpsl_weso.config import settings

TIMEOUT = 180
CNPJ = "WQ0P6GLD000108"
criados = {"veiculos": [], "rastreadores": [], "chips": []}


async def tentar(c, rotulo, equipamento):
    r = await c.post("/Veiculos/Cadastro", params={"key": settings.weso_api_key},
                     json={"equipamento": equipamento})
    ok = r.status_code in (200, 201)
    print(f"\n  {rotulo}")
    print(f"    HTTP {r.status_code} {'OK' if ok else 'FALHOU'}: {r.text[:260]}")
    if ok:
        try:
            d = (r.json().get("Data", r.json()))
            criados["veiculos"].append(d.get("id"))
            print(f"    criou: veiculo={d.get('id')} rastreador={d.get('rastreador_id')} "
                  f"simcard={d.get('simcard_id')} | {d.get('objetos_processados')}")
        except Exception:
            pass
    return ok


async def main():
    async with httpx.AsyncClient(base_url=settings.weso_base_url, timeout=TIMEOUT) as c:
        cliente = {"cnpjcpf": CNPJ, "razaoSocial": "PASTELARIA VELASCO LTDA",
                   "tipoCliente": "Juridica"}

        print("=" * 70)
        print("BISSECCAO — acrescentando um bloco por vez")
        print("=" * 70)

        await tentar(c, "A. so placa + cliente (controle, sabemos que funciona)",
                     {"placa": "TST 1A21", "descricao": "bisseccao A", "cliente": cliente})

        await tentar(c, "B. + rastreador com modelo STRING (como a doc do Veiculos mostra)",
                     {"placa": "TST 1A22", "descricao": "bisseccao B", "cliente": cliente,
                      "rastreador": {"numeroSerie": "FPSLBIS0002", "modelo": "Suntech ST310"}})

        await tentar(c, "C. + rastreador com modelo OBJETO (como a doc de Rastreadores manda)",
                     {"placa": "TST 1A23", "descricao": "bisseccao C", "cliente": cliente,
                      "rastreador": {"numeroSerie": "FPSLBIS0003",
                                     "modelo": {"descricao": "Suntech ST310"}}})

        await tentar(c, "D. rastreador STRING + simCard",
                     {"placa": "TST 1A24", "descricao": "bisseccao D", "cliente": cliente,
                      "rastreador": {"numeroSerie": "FPSLBIS0004", "modelo": "Suntech ST310",
                                     "simCard": {"iccId": "8955000000000099904"}}})

        await tentar(c, "E. rastreador so com numeroSerie (sem modelo)",
                     {"placa": "TST 1A25", "descricao": "bisseccao E", "cliente": cliente,
                      "rastreador": {"numeroSerie": "FPSLBIS0005"}})

        print("\n" + "=" * 70)
        print("estado final dos alvos")
        print("=" * 70)
        for placa in ["TST 1A21", "TST 1A22", "TST 1A23", "TST 1A24", "TST 1A25"]:
            v = (await (await c.get("/Veiculos/Consultar",
                 params={"key": settings.weso_api_key, "placa": placa})).aread()) and None
            rr = await c.get("/Veiculos/Consultar",
                             params={"key": settings.weso_api_key, "placa": placa})
            lst = (rr.json().get("Data", rr.json())).get("veiculos") or []
            print(f"  {placa}: {len(lst)}" +
                  (f" -> id={lst[0].get('id')} rastreador_id={lst[0].get('rastreador_id')}" if lst else ""))
        for serial in ["FPSLBIS0002", "FPSLBIS0003", "FPSLBIS0004", "FPSLBIS0005"]:
            rr = await c.get("/Rastreadores/Consultar",
                             params={"key": settings.weso_api_key, "numeroSerie": serial})
            try:
                lst = (rr.json().get("Data", rr.json())).get("rastreadores") or []
            except Exception:
                lst = []
            print(f"  {serial}: {len(lst)}" +
                  (f" -> id={lst[0].get('id')} simcard={lst[0].get('simcard')}" if lst else ""))
        rr = await c.get("/SimCard/Consultar",
                         params={"key": settings.weso_api_key, "iccId": "8955000000000099904"})
        lst = (rr.json().get("Data", rr.json())).get("simcards") or []
        print(f"  chip ...99904: {len(lst)}" + (f" -> id={lst[0].get('id')}" if lst else ""))


asyncio.run(main())
