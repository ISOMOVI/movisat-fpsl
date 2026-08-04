"""Formato das placas na WESO + o que vem no payload — só leitura.

Responde 2 perguntas do usuário (2026-07-27):
  1. "sem espaço" é só placa NÃO convencional (apelido/lixo), ou tem placa real?
  2. o Consultar já devolve o id do EQUIPAMENTO junto, ou precisa de 2ª chamada?
"""
import asyncio
import re
import collections

from fpsl_weso.client import start_client, stop_client, weso_get

# ABC1234 (antiga) e ABC1D23 (Mercosul), com ou sem separador
RE_ANTIGA = re.compile(r"^[A-Z]{3}[ -]?\d{4}$")
RE_MERCOSUL = re.compile(r"^[A-Z]{3}[ -]?\d[A-Z]\d{2}$")


def classificar(p):
    limpa = p.strip().upper()
    limpa = re.sub(r"\s*\(RD\)\s*", "", limpa)
    if RE_ANTIGA.match(limpa):
        return "convencional antiga"
    if RE_MERCOSUL.match(limpa):
        return "convencional Mercosul"
    return "NAO convencional"


async def main():
    await start_client()
    try:
        r = await weso_get("/Veiculos/Consultar", {})
        veics = r.get("veiculos") or []
        print(f"total: {len(veics)}\n")

        print("=" * 64)
        print("1. CAMPOS do payload (o que ja vem sem 2a chamada)")
        print("=" * 64)
        chaves = collections.Counter()
        for v in veics:
            for k in v:
                chaves[k] += 1
        for k, n in chaves.most_common():
            preenchidos = sum(1 for v in veics if v.get(k) not in (None, "", 0))
            print(f"  {k:24s} presente={n:5d}  preenchido={preenchidos}")

        print()
        print("=" * 64)
        print("2. ESPACO x tipo de placa  (a hipotese do usuario)")
        print("=" * 64)
        cruz = collections.Counter()
        for v in veics:
            p = str(v.get("placa") or "")
            espaco = "com espaco" if " " in p.strip() else "SEM espaco"
            cruz[(espaco, classificar(p))] += 1
        for (esp, tipo), n in sorted(cruz.items()):
            print(f"  {esp:11s} | {tipo:22s} | {n}")

        print("\n  --- as SEM espaco, uma a uma ---")
        sem = [v for v in veics if " " not in str(v.get("placa") or "").strip()]
        for v in sorted(sem, key=lambda x: str(x.get("placa"))):
            p = str(v.get("placa"))
            print(f"    {p:22s} {classificar(p):22s} id={v.get('id')}")
    finally:
        await stop_client()


asyncio.run(main())
