# -*- coding: utf-8 -*-
"""Cadastra no Harmonit os SIM Cards da planilha que nao existiam la.

Autorizado pelo usuario em 2026-09-04. Sao 16 ICCIDs que estao na planilha e na
WESO, mas nunca entraram na base do Harmonit -- e o Harmonit e a lei da
auditoria dos chips. 14 deles sao buraco no meio de um lote Eseye ja cadastrado
(o chip anterior e o seguinte da sequencia existem la).

Dado de origem: ICCID e serial da planilha; numeroLinha da WESO; operadora pelo
prefixo do ICCID (regra validada contra 914 linhas, 0 divergencias).

CUIDADOS:
  - `id: 0` CRIA. Conferido antes de rodar que nenhum dos 16 ICCIDs e nenhum
    dos 16 numeros de linha existe no Harmonit, nem atras de um registro
    `DUPLICADO-`.
  - a confirmacao e RELER A BASE, nunca o codigo HTTP.
  - o total de SIM Cards tem de subir exatamente pelo numero de criados. Subir
    mais significa duplicata; subir menos significa que algo nao gravou.

Uso:
  venv/bin/python criar_simcards_harmonit.py                    # dry-run
  venv/bin/python criar_simcards_harmonit.py --aplicar --limite 1
  venv/bin/python criar_simcards_harmonit.py --aplicar
"""
import argparse
import asyncio
import json
import re
import sys

sys.path.insert(0, "/home/claude/fpsl_weso")
from fpsl_weso import harmonit_client as hc  # noqa: E402

ALVOS = "/home/claude/alvos_criar.json"


def digitos(s):
    return re.sub(r"\D", "", str(s or ""))


async def ler_base():
    r = await hc.harmonit_post("/SIMCard/ObterSIMCards", {})
    return r if isinstance(r, list) else (r or {}).get("dados") or []


def por_iccid(base):
    d = {}
    for x in base:
        d.setdefault(digitos(x.get("numeroChip")), []).append(x)
    return d


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--limite", type=int)
    args = ap.parse_args()

    alvos = json.load(open(ALVOS, encoding="utf-8"))
    if args.limite:
        alvos = alvos[:args.limite]

    await hc.start_harmonit_client()
    try:
        base = await ler_base()
        idx = por_iccid(base)
        print(f"SIM Cards no Harmonit ANTES: {len(base)}")

        plano = []
        for a in alvos:
            if idx.get(a["iccid"]):
                print(f"  PULA {a['iccid']}: ja existe (id "
                      f"{[x['id'] for x in idx[a['iccid']]]})")
                continue
            if not a.get("numeroLinha") or not a.get("operadoraId"):
                print(f"  PULA {a['iccid']}: falta numeroLinha ou operadoraId")
                continue
            plano.append(a)

        print(f"a criar: {len(plano)} de {len(alvos)}")
        for a in plano:
            print(f"  {a['iccid']:<20} linha={a['numeroLinha']:<15} "
                  f"operadoraId={a['operadoraId']} ({a['familia']})  "
                  f"serial do equipamento: {a['serial']}")

        if not args.aplicar:
            print("\nDRY-RUN. Nada foi gravado. Use --aplicar.")
            return 0

        for a in plano:
            corpo = {"id": 0,
                     "numeroChip": a["iccid"],
                     "numeroLinha": str(a["numeroLinha"]),
                     "operadoraId": a["operadoraId"]}
            try:
                await hc.harmonit_post("/SIMCard/CadastrarOuAtualizar", corpo)
                print(f"  enviado {a['iccid']}")
            except Exception as e:
                print(f"  ERRO {a['iccid']}: {str(e)[:160]}")

        # --- a unica prova: reler a base
        base2 = await ler_base()
        idx2 = por_iccid(base2)
        print(f"\nSIM Cards no Harmonit DEPOIS: {len(base2)} "
              f"(esperado {len(base) + len(plano)})")
        if len(base2) != len(base) + len(plano):
            print("  ALERTA: o total nao subiu exatamente pelo numero de criados.")

        ok = falha = 0
        for a in plano:
            achados = idx2.get(a["iccid"], [])
            if len(achados) != 1:
                print(f"  FALHA {a['iccid']}: {len(achados)} registro(s) na base")
                falha += 1
                continue
            d = achados[0]
            lin_ok = digitos(d.get("numeroLinha")) == digitos(a["numeroLinha"])
            op_ok = d.get("operadoraId") == a["operadoraId"]
            if lin_ok and op_ok:
                ok += 1
                print(f"  OK {a['iccid']} -> id={d['id']} "
                      f"linha={d.get('numeroLinha')} operadoraId={d.get('operadoraId')}")
            else:
                falha += 1
                print(f"  FALHA {a['iccid']}: id={d['id']} "
                      f"linha={d.get('numeroLinha')!r} (queria {a['numeroLinha']!r}) "
                      f"operadoraId={d.get('operadoraId')} (queria {a['operadoraId']})")
        print(f"\nconferido relendo a base: {ok} OK, {falha} falha(s)")
        return 1 if falha else 0
    finally:
        await hc.stop_harmonit_client()


sys.exit(asyncio.run(main()))
