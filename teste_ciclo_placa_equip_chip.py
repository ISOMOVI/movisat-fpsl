"""Ciclo completo placa+equipamento+chip na WESO — responde a pergunta D. (2026-07-27)

Perguntas do usuario:
  1. mandando o serial na oficina, a WESO CADASTRA o rastreador se nao existir?
     -> NAO. Qualquer bloco `rastreador` com numeroSerie da 400. Só `rastreador:{id}`
        (referenciando um que JA existe) funciona. Por isso aqui o fluxo e de 2 passos.
  2. quando a PLACA for excluida, o que acontece com o rastreador?
  3. e com o ICCID?

Cria tudo, exclui a placa, confere o que sobrou, e limpa no fim.
NAO toca nos 3 veiculos da Velasco que o usuario quer ver no painel.
"""
import argparse
import asyncio

import httpx

from fpsl_weso.config import settings

TIMEOUT = 180
PLACA = "TST 1A11"
SERIAL = "FPSLCICLO0001"
ICCID = "8955000000000099901"
CNPJ_VELASCO = "WQ0P6GLD000108"


async def get(c, path, params=None):
    r = await c.get(path, params={"key": settings.weso_api_key, **(params or {})})
    try:
        return (r.json().get("Data", r.json()))
    except Exception:
        return {}


async def ver_veiculo(c):
    return (await get(c, "/Veiculos/Consultar", {"placa": PLACA})).get("veiculos") or []


async def ver_rastreador(c):
    return (await get(c, "/Rastreadores/Consultar", {"numeroSerie": SERIAL})).get("rastreadores") or []


async def ver_chip(c):
    return (await get(c, "/SimCard/Consultar", {"iccId": ICCID})).get("simcards") or []


async def estado(c, titulo):
    v, r, s = await ver_veiculo(c), await ver_rastreador(c), await ver_chip(c)
    print(f"  [{titulo}]")
    print(f"    veiculo {PLACA!r}: {len(v)}" +
          (f" -> id={v[0].get('id')} rastreador_id={v[0].get('rastreador_id')}" if v else ""))
    print(f"    rastreador {SERIAL!r}: {len(r)}" +
          (f" -> id={r[0].get('id')} situacao={r[0].get('situacao')!r} simcard={r[0].get('simcard')}" if r else ""))
    print(f"    chip {ICCID!r}: {len(s)}" +
          (f" -> id={s[0].get('id')} situacao={s[0].get('situacao')!r}" if s else ""))
    return v, r, s


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()
    print(f"== {'APLICANDO' if args.aplicar else 'DRY-RUN'} ==\n")

    async with httpx.AsyncClient(base_url=settings.weso_base_url, timeout=TIMEOUT) as c:
        print("ANTES de tudo:")
        v, r, s = await estado(c, "inicial")
        if v or r or s:
            print("\n!! algum dos 3 ja existe -- abortando")
            return
        if not args.aplicar:
            print("\n(dry-run)")
            return

        print("\n" + "=" * 70)
        print("1. CADASTRO em 2 PASSOS (o de 1 tacada esta quebrado)")
        print("=" * 70)
        rr = await c.post("/Rastreadores/Cadastro", params={"key": settings.weso_api_key},
                          json={"numeroSerie": SERIAL, "modelo": {"descricao": "Suntech ST310"},
                                "tipo": {"descricao": "Veiculo"},
                                "simCard": {"iccId": ICCID, "numero": 5599000000001}})
        print(f"  1a. /Rastreadores/Cadastro -> HTTP {rr.status_code}: {rr.text[:220]}")
        rid = (rr.json().get("Data", rr.json())).get("id") if rr.status_code in (200, 201) else None

        rv = await c.post("/Veiculos/Cadastro", params={"key": settings.weso_api_key},
                          json={"equipamento": {
                              "placa": PLACA, "descricao": "TESTE ciclo FPSL 2026-07-27",
                              "cliente": {"cnpjcpf": CNPJ_VELASCO,
                                          "razaoSocial": "PASTELARIA VELASCO LTDA",
                                          "tipoCliente": "Juridica"},
                              "rastreador": {"id": rid}}})
        print(f"  1b. /Veiculos/Cadastro (rastreador:{{id:{rid}}}) -> HTTP {rv.status_code}: {rv.text[:260]}")
        v, r, s = await estado(c, "depois do cadastro")
        print(f"\n  >> chip criado junto do RASTREADOR? {'SIM' if s else 'NAO'}")

        print("\n" + "=" * 70)
        print("2. EXCLUIR A PLACA — o que sobra?")
        print("=" * 70)
        if not v:
            print("  veiculo nao existe")
            return
        vid = v[0]["id"]
        rx = await c.post("/Veiculos/Excluir", params={"key": settings.weso_api_key},
                          json={"veiculo_id": vid})
        print(f"  /Veiculos/Excluir {{veiculo_id:{vid}}} -> HTTP {rx.status_code}: {rx.text[:200]}")
        v2, r2, s2 = await estado(c, "depois de excluir a placa")

        print("\n" + "=" * 70)
        print("RESPOSTA")
        print("=" * 70)
        print(f"  veiculo    : {'SUMIU' if not v2 else 'CONTINUA'}")
        print(f"  rastreador : {'SUMIU junto' if not r2 else 'SOBREVIVEU — fica solto no acervo'}")
        print(f"  chip       : {'SUMIU junto' if not s2 else 'SOBREVIVEU — fica solto no acervo'}")

        print("\n3. LIMPEZA")
        for x in await ver_veiculo(c):
            await c.post("/Veiculos/Excluir", params={"key": settings.weso_api_key},
                         json={"veiculo_id": x["id"]})
        for x in await ver_rastreador(c):
            rl = await c.post("/Rastreadores/Excluir", params={"key": settings.weso_api_key},
                              json={"id": x["id"]})
            print(f"  rastreador {x['id']}: HTTP {rl.status_code}")
        for x in await ver_chip(c):
            cl = await c.post("/SimCard/Excluir", params={"key": settings.weso_api_key},
                              json={"iccId": ICCID})
            print(f"  chip {x['id']}: HTTP {cl.status_code}")
        await estado(c, "apos limpeza")


asyncio.run(main())
