# -*- coding: utf-8 -*-
"""Classifica no Harmonit os SIM Cards que estao sem operadora util.

Autorizado pelo usuario em 2026-09-04: "se baterem por ICCID pode ajustar,
teste 1 para validar e depois os demais".

Escopo: so os chips cujo ICCID ja EXISTE no Harmonit e que estao com
operadoraId = 0 ou 856 ("NAO IDENTIFICADOS"). A operadora vem do prefixo do
ICCID, regra validada contra as 914 linhas que o Harmonit ja responde
(concordou em 914, divergiu em 0).

CUIDADOS medidos, nao supostos:
  - o payload PRECISA levar numeroChip e numeroLinha. Sem eles o Harmonit grava
    VAZIO e APAGA o ICCID do chip (aconteceu com o SIM 124194 em 27/07).
  - a confirmacao e RELER O ESTADO, nunca o codigo HTTP -- os sistemas mentem
    no retorno.
  - o total de SIM Cards e conferido antes e depois: se subir, o
    CadastrarOuAtualizar criou registro novo em vez de atualizar, e isso e
    falha, nao sucesso.

Uso:
  venv/bin/python ajustar_operadora_harmonit.py                    # dry-run
  venv/bin/python ajustar_operadora_harmonit.py --aplicar --limite 1
  venv/bin/python ajustar_operadora_harmonit.py --aplicar
"""
import argparse
import asyncio
import json
import re
import sys

sys.path.insert(0, "/home/claude/fpsl_weso")
from fpsl_weso import harmonit_client as hc  # noqa: E402

ALVOS = "/home/claude/alvos_operadora.json"


def digitos(s):
    return re.sub(r"\D", "", str(s or ""))


async def ler_base():
    r = await hc.harmonit_post("/SIMCard/ObterSIMCards", {})
    lst = r if isinstance(r, list) else (r or {}).get("dados") or []
    return {x["id"]: x for x in lst}


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
        antes = await ler_base()
        print(f"SIM Cards no Harmonit ANTES: {len(antes)}")

        # confere que cada alvo esta como esperado, ao vivo, antes de tocar
        plano = []
        for a in alvos:
            reg = antes.get(a["sim_id"])
            if reg is None:
                print(f"  PULA sim_id={a['sim_id']}: nao existe mais na base")
                continue
            if digitos(reg.get("numeroChip")) != a["iccid"]:
                print(f"  PULA sim_id={a['sim_id']}: ICCID mudou "
                      f"({reg.get('numeroChip')!r})")
                continue
            if reg.get("operadoraId") not in (0, None, 856):
                print(f"  PULA sim_id={a['sim_id']}: ja tem operadora "
                      f"{reg.get('operadoraId')}")
                continue
            plano.append((a, reg))

        print(f"a aplicar: {len(plano)} de {len(alvos)}")
        for a, reg in plano:
            print(f"  sim_id={a['sim_id']:<7} {a['iccid']:<20} "
                  f"{reg.get('operadoraId')} -> {a['operadora_depois']} ({a['familia']})")

        if not args.aplicar:
            print("\nDRY-RUN. Nada foi gravado. Use --aplicar.")
            return 0

        for a, reg in plano:
            corpo = {"id": a["sim_id"],
                     # sem estes dois o Harmonit apaga o ICCID do chip
                     "numeroChip": reg.get("numeroChip"),
                     "numeroLinha": reg.get("numeroLinha"),
                     "operadoraId": a["operadora_depois"]}
            try:
                await hc.harmonit_post("/SIMCard/CadastrarOuAtualizar", corpo)
                print(f"  enviado sim_id={a['sim_id']}")
            except Exception as e:
                print(f"  ERRO sim_id={a['sim_id']}: {str(e)[:160]}")

        # --- a unica prova: reler o estado
        depois = await ler_base()
        print(f"\nSIM Cards no Harmonit DEPOIS: {len(depois)}")
        if len(depois) != len(antes):
            print(f"  ALERTA: o total mudou ({len(antes)} -> {len(depois)}). "
                  f"CadastrarOuAtualizar pode ter CRIADO registro em vez de atualizar.")

        ok = falha = 0
        for a, _ in plano:
            d = depois.get(a["sim_id"])
            if d is None:
                print(f"  FALHA sim_id={a['sim_id']}: sumiu da base")
                falha += 1
                continue
            icc_ok = digitos(d.get("numeroChip")) == a["iccid"]
            lin_ok = str(d.get("numeroLinha") or "") == str(_.get("numeroLinha") or "")
            op_ok = d.get("operadoraId") == a["operadora_depois"]
            if icc_ok and lin_ok and op_ok:
                ok += 1
            else:
                falha += 1
                print(f"  FALHA sim_id={a['sim_id']}: "
                      f"iccid_intacto={icc_ok} linha_intacta={lin_ok} "
                      f"operadora={d.get('operadoraId')} (queria {a['operadora_depois']})")
        print(f"\nconferido relendo a base: {ok} OK, {falha} falha(s)")
        return 1 if falha else 0
    finally:
        await hc.stop_harmonit_client()


sys.exit(asyncio.run(main()))
