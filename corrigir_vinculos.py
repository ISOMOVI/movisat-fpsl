"""Correcao dos vinculos veiculo<->rastreador quebrados pelo lote de 27/07.

CAUSA: corrigir_chips_harmonit.py mandou PUT /Rastreador/Atualizar com a placa
como texto e SEM veiculoId. O Harmonit criou um veiculo novo por chamada
(ids 107703-107792, consecutivos) e moveu o rastreador para o duplicado.

CORRECAO: repontar cada rastreador para o veiculoId original, agora COM o campo
veiculoId no payload.

Fonte do estado anterior: espelho local harmonit_rastreadores (snapshot 03/07).
Cada linha so entra no plano se passar em 4 validacoes:
   V1 o rastreador existe hoje
   V2 hoje ele aponta para a faixa duplicada (107703-107792) ou para 0
   V3 o veiculo original do espelho AINDA EXISTE
   V4 a placa do veiculo original bate com a placa gravada no rastreador

Modos:
   python corrigir_vinculos.py                  -> so o plano (nada e enviado)
   python corrigir_vinculos.py --aplicar 10117  -> aplica nos ids listados
   python corrigir_vinculos.py --aplicar todos  -> aplica no plano inteiro

Toda escrita e seguida de RELEITURA do estado (o HTTP mente), e o script
confere se o total de veiculos cresceu -- se crescer, o Harmonit criou duplicata
de novo e o script PARA.
"""
import asyncio
import csv
import re
import sqlite3
import sys
from datetime import datetime

import httpx

from fpsl_weso import harmonit_client as hc
from fpsl_weso.config import settings
from fpsl_weso.harmonit_client import (start_harmonit_client, stop_harmonit_client,
                                       harmonit_post, harmonit_get)

FAIXA = range(107703, 107793)
LOG = f"logs/correcao_vinculos_{datetime.now():%Y-%m-%d}.csv"


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


async def estado():
    d = await harmonit_post("/Rastreador/ObterRastreadores", {})
    rs = d if isinstance(d, list) else (d or {}).get("dados") or []
    v = await harmonit_get("/Veiculo/ObterVeiculos", {})
    vs = v if isinstance(v, list) else (v or {}).get("data") or []
    return {x["id"]: x for x in rs}, {x["id"]: x for x in vs}


def montar_plano(rast, veic, antes):
    plano, descartados = [], []
    for rid, vid_antigo in antes.items():
        if not vid_antigo:
            continue
        r = rast.get(rid)
        if not r:
            descartados.append((rid, "V1 rastreador nao existe hoje"))
            continue
        atual = r.get("veiculoId") or 0
        if atual == vid_antigo:
            continue                      # nao foi afetado
        if atual not in FAIXA and atual != 0:
            descartados.append((rid, f"V2 aponta para {atual}, fora da faixa"))
            continue
        vo = veic.get(vid_antigo)
        if not vo:
            descartados.append((rid, f"V3 veiculo original {vid_antigo} sumiu"))
            continue
        if norm(r.get("placa")) and norm(vo.get("placa")) != norm(r.get("placa")):
            descartados.append((rid, f"V4 placa {r.get('placa')!r} != "
                                     f"{vo.get('placa')!r}"))
            continue
        plano.append({"rid": rid, "de": atual, "para": vid_antigo,
                      "placa": vo.get("placa"), "veiculo": vo.get("veiculo"),
                      "cliente": vo.get("cliente"), "r": r})
    return plano, descartados


def corpo_para(p):
    r = p["r"]
    return {"id": p["rid"],
            "modeloEquipamentoId": r.get("modeloEquipamentoId"),
            "modeloEquipamento": r.get("modeloEquipamento"),
            "equipamento": r.get("equipamento"),
            "simCardId": r.get("simCardId") or 0,
            # obrigatorios: omitir apaga o ICCID do SIM Card
            "numeroChip": r.get("numeroChip") or "",
            "numeroLinha": r.get("numeroLinha") or "",
            # o campo que faltava em 27/07 e causou tudo isto
            "veiculoId": p["para"],
            "placa": p["placa"] or " ",
            "veiculo": p["veiculo"] or " "}


async def main():
    alvos = None
    if "--aplicar" in sys.argv:
        arg = sys.argv[sys.argv.index("--aplicar") + 1]
        alvos = "todos" if arg == "todos" else {int(x) for x in arg.split(",")}

    await start_harmonit_client()
    try:
        rast, veic = await estado()
        con = sqlite3.connect("data/fpsl.db")
        antes = {r[0]: r[1] for r in
                 con.execute("SELECT id, veiculo_id FROM harmonit_rastreadores")}
        con.close()

        plano, desc = montar_plano(rast, veic, antes)
        print(f"veiculos na base agora : {len(veic)}")
        print(f"PLANO                  : {len(plano)} rastreadores a repontar")
        print(f"descartados na validacao: {len(desc)}")
        for rid, motivo in desc[:10]:
            print(f"   rast {rid}: {motivo}")

        print("\n-- plano (primeiros 15):")
        for p in plano[:15]:
            print(f"   rast {p['rid']:<7} veic {p['de']:<7} -> {p['para']:<7} "
                  f"placa={p['placa']!r} cliente={str(p['cliente'])[:34]!r}")

        if alvos is None:
            print("\n(dry-run — nada enviado. use --aplicar <ids|todos>)")
            return

        fila = plano if alvos == "todos" else [p for p in plano if p["rid"] in alvos]
        if not fila:
            print(f"\nnenhum item do plano casa com {alvos}")
            return

        print(f"\n{'=' * 70}\nAPLICANDO em {len(fila)} registro(s)\n{'=' * 70}")
        n_veic_antes = len(veic)
        linhas, ok, falha = [], 0, 0

        async with httpx.AsyncClient(base_url=settings.harmonit_base_url,
                                     timeout=90) as c:
            for i, p in enumerate(fila, 1):
                corpo = corpo_para(p)
                r = await c.put("/Rastreador/Atualizar", headers=hc._headers(),
                                json=corpo)
                # RELEITURA — o HTTP mente
                rast2, veic2 = await estado()
                d = rast2.get(p["rid"], {})
                gravou = (d.get("veiculoId") == p["para"])
                cresceu = len(veic2) - n_veic_antes

                print(f"[{i}/{len(fila)}] rast {p['rid']} -> veic {p['para']} "
                      f"({p['placa']!r})")
                print(f"    HTTP {r.status_code} | conferido veiculoId="
                      f"{d.get('veiculoId')} | {'OK' if gravou else 'NAO GRAVOU'}")
                print(f"    ICCID apos: {d.get('numeroChip')!r}")

                ok += gravou
                falha += (not gravou)
                linhas.append([p["rid"], p["de"], p["para"], p["placa"],
                               r.status_code, d.get("veiculoId"),
                               d.get("numeroChip"), "ok" if gravou else "falhou"])

                if cresceu > 0:
                    print(f"\n!! PARANDO: a base de veiculos cresceu {cresceu} "
                          f"({n_veic_antes} -> {len(veic2)}). O Harmonit criou "
                          f"duplicata de novo.")
                    break
                n_veic_antes = len(veic2)

        novo = not __import__("os").path.exists(LOG)
        with open(LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            if novo:
                w.writerow(["rastreador_id", "veiculo_de", "veiculo_para", "placa",
                            "http", "veiculo_conferido", "iccid_apos", "resultado"])
            w.writerows(linhas)

        print(f"\n{'=' * 70}\n  ok={ok}  falha={falha}   log: {LOG}")
    finally:
        await stop_harmonit_client()


asyncio.run(main())
