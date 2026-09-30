"""Oficina de desinstalacao na OS 16972 (osId 898322), equipamento 907112547.

AUTORIZADO pelo usuario em 2026-09-29 ("desinstale como pedi").
Cliente: o que esta na OS (parceiro 60743, Colonial).
Read-after-write obrigatorio: o Harmonit mente no codigo de retorno.

Sem --aplicar: so le e mostra o plano.
"""
import asyncio
import json
import sqlite3
import sys

import httpx

from fpsl_weso import harmonit_client as hc
from fpsl_weso.config import settings
from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_post, harmonit_get)

OSID = 898322
NUM_OS = 16972
RAST = 10655
SERIAL = "907112547"
VEIC = 6251
PLACA = "EPW 0I21"
NOME_VEIC = "IVECO DAILY35S14 CS"
EMPRESA = 98
DB = "/home/claude/fpsl_weso/data/fpsl.db"
APLICAR = "--aplicar" in sys.argv


async def rast():
    d = await harmonit_post("/Rastreador/ObterRastreadores", {})
    rs = d if isinstance(d, list) else (d or {}).get("dados") or []
    return next((x for x in rs if x.get("id") == RAST), None)


async def oficinas(osid):
    of = await harmonit_get("/OrdemServico/ObterOficinas", {"osId": osid})
    return of if isinstance(of, list) else (of or {}).get("data") or []


def instalacoes_no_cache():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT numero_os, cliente_id, oficinas_json FROM os_historico "
        "WHERE oficinas_json LIKE ?", (f"%{SERIAL}%",)).fetchall()
    con.close()
    achados = []
    for num, cli, js in rows:
        for o in json.loads(js or "[]"):
            if SERIAL in json.dumps(o, ensure_ascii=False):
                achados.append((num, cli, o))
    return achados


async def mostrar(rotulo):
    r = await rast()
    of = await oficinas(OSID)
    print(f"[{rotulo}] rast {RAST}: instalado={r.get('instalado')} ativar={r.get('ativar')} "
          f"veiculoId={r.get('veiculoId')} placa={r.get('placa')!r} contato={r.get('contato')!r}")
    print(f"[{rotulo}] oficinas na OS {NUM_OS}: {len(of)}")
    for x in of:
        print("    " + json.dumps(x, ensure_ascii=False))
    return r, of


async def main():
    await start_harmonit_client()
    try:
        print("=== instalacoes do 907112547 no cache os_historico ===")
        inst = instalacoes_no_cache()
        for num, cli, o in inst:
            print(f"  OS {num} cliente {cli}: {json.dumps(o, ensure_ascii=False)}")
        if not inst:
            print("  nenhuma no cache (cache cobre so OS recentes)")

        r0, of0 = await mostrar("ANTES")

        if any(x.get("status") == 2 for x in of0):
            print("\nJa existe oficina de desinstalacao nesta OS. Nada a fazer.")
            return

        if not APLICAR:
            print("\n(dry-run) nada enviado")
            return

        async with httpx.AsyncClient(base_url=settings.harmonit_base_url,
                                     timeout=90) as c:
            # passo A: registrar a oficina na OS (AdicionarOficina), como no
            # experimento de 08/2026 -- o id dela vira o ras_ins_id
            if not of0:
                corpo_a = {"empresaId": EMPRESA, "osId": OSID,
                           "tipoVeic": 1, "tipo": 1,
                           "idAparelho": SERIAL,
                           "idVeiculo": str(VEIC),
                           "rastreadorId": RAST,
                           "placaVeiculo": PLACA,
                           "nomeVeiculo": NOME_VEIC,
                           "trocaOficinaAntigaId": 0}
                print(f"\nPOST /OrdemServico/AdicionarOficina {json.dumps(corpo_a, ensure_ascii=False)}")
                ra = await c.post("/OrdemServico/AdicionarOficina",
                                  headers=hc._headers(), json=corpo_a)
                print(f"  HTTP {ra.status_code}: {ra.text[:300]}")
                r1, of1 = await mostrar("DEPOIS AdicionarOficina")
                novas = [x for x in of1 if x not in of0]
                if not novas:
                    print("!! nenhuma oficina criada -- PARANDO")
                    return
                ras_ins = str(novas[0].get("id"))
            else:
                ras_ins = str(of0[0].get("id"))
            print(f"\nras_ins_id = {ras_ins}")

            antes_r, antes_of = await mostrar("ANTES DesinstalarOficina")
            for tipo in (1, 2):
                corpo_d = {"empresaId": EMPRESA, "osId": OSID,
                           "ras_ins_id": ras_ins,
                           "idAparelho": SERIAL,
                           "idVeiculo": str(VEIC),
                           "veiculoId": VEIC,
                           "rastreadorId": RAST,
                           "placaVeiculo": PLACA,
                           "nomeVeiculo": NOME_VEIC,
                           "tipo": tipo}
                print(f"\nPOST /OrdemServico/DesinstalarOficina {json.dumps(corpo_d, ensure_ascii=False)}")
                rd = await c.post("/OrdemServico/DesinstalarOficina",
                                  headers=hc._headers(), json=corpo_d)
                print(f"  HTTP {rd.status_code}: {rd.text[:300]}")
                dep_r, dep_of = await mostrar(f"DEPOIS DesinstalarOficina tipo={tipo}")
                tem_desinst = any(x.get("status") == 2 for x in dep_of)
                if tem_desinst or dep_r.get("instalado") != antes_r.get("instalado"):
                    print(f"\n>>> tipo={tipo} surtiu efeito. Parando.")
                    break
                print(f">>> tipo={tipo}: nada mudou na releitura.")
    finally:
        await stop_harmonit_client()


asyncio.run(main())
