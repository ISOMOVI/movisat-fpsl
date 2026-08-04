"""Padroniza o marcador de redundancia na WESO para '(RD) ABC 1234'.

Decisao do usuario em 2026-07-27: marcador ANTES, entre parenteses, um espaco,
seguido da placa no formato com espaco (antiga ou Mercosul).

ESCREVE NA WESO (producao).

Seguranca:
  - dry-run por padrao; so escreve com --aplicar
  - --somente <id> processa um registro
  - so mexe em redundancia GENUINA: tira o marcador e o que sobra tem que ser
    placa valida. 'RDM 0G81' (prefixo RDM legitimo) fica de fora.
  - VALIDACAO DE DUPLICATA: compara (placa_base, tem_RD). Se ja existir OUTRO
    registro com a mesma base marcada RD, nao aplica e reporta.
  - re-le apos escrever; se nao confirmar, para tudo.

Uso na VPS:
  venv/bin/python padronizar_rd.py                    # dry-run
  venv/bin/python padronizar_rd.py --aplicar --somente 18747
  venv/bin/python padronizar_rd.py --aplicar
"""
import argparse
import asyncio
import re

import httpx

from fpsl_weso.config import settings

TIMEOUT = 180
RE_PLACA = re.compile(r"^[A-Z]{3}\s?(\d{4}|\d[A-Z]\d{2})$")


def so_alfanum(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def tem_rd(p):
    """Marcador presente? (nao confunde com prefixo tipo RDM/RDQ/DRD)."""
    return base_da_placa(p) is not None


def base_da_placa(p):
    """Tira o marcador RD; devolve a placa base FORMATADA 'ABC 1234'.

    None quando o 'RD' faz parte da placa (RDM 0G81 -> 'M 0G81', invalido).
    """
    s = re.sub(r"\s+", " ", str(p).strip().upper())
    candidatos = [
        re.sub(r"\s*\(\s*RD\s*\)\s*", " ", s),
        re.sub(r"\s+RD\s*$", "", s),
        re.sub(r"^\s*RD\s+", "", s),
        re.sub(r"^RD", "", s),
        re.sub(r"RD$", "", s),
    ]
    for cand in candidatos:
        if cand == s:
            continue
        limpo = re.sub(r"\s+", " ", cand).strip()
        if RE_PLACA.match(limpo):
            n = so_alfanum(limpo)
            return f"{n[:3]} {n[3:]}"
    return None


def alvo(p):
    base = base_da_placa(p)
    return f"(RD) {base}" if base else None


async def get(c, path, params=None):
    r = await c.get(path, params={"key": settings.weso_api_key, **(params or {})})
    corpo = r.json()
    return corpo.get("Data", corpo)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--somente", type=int)
    args = ap.parse_args()

    async with httpx.AsyncClient(base_url=settings.weso_base_url, timeout=TIMEOUT) as c:
        veics = (await get(c, "/Veiculos/Consultar")).get("veiculos") or []
        print(f"base: {len(veics)} veiculos")

        # indice (base_normalizada, tem_rd) -> [ids]  para achar duplicata
        indice = {}
        for v in veics:
            p = str(v.get("placa") or "")
            b = base_da_placa(p)
            chave = (so_alfanum(b), True) if b else (so_alfanum(p), False)
            indice.setdefault(chave, []).append(v["id"])

        pendentes = []
        for v in veics:
            p = str(v.get("placa") or "")
            a = alvo(p)
            if not a:
                continue           # nao e redundancia genuina
            if p == a:
                continue           # ja esta no padrao
            pendentes.append((v, a))

        if args.somente:
            pendentes = [(v, a) for v, a in pendentes if v["id"] == args.somente]

        modo = "APLICANDO (escreve na WESO)" if args.aplicar else "DRY-RUN (nao escreve)"
        print(f"== {modo} == {len(pendentes)} registro(s) fora do padrao\n")

        for v, a in sorted(pendentes, key=lambda x: x[1]):
            vid, atual = v["id"], str(v["placa"])
            base_norm = so_alfanum(base_da_placa(atual))
            irmaos = [i for i in indice.get((base_norm, True), []) if i != vid]
            sem_rd = indice.get((base_norm, False), [])

            print(f"--- id={vid}  {atual!r} -> {a!r}")
            print(f"    placa base: {base_da_placa(atual)}  | registro sem RD existe? "
                  f"{'SIM ids=' + str(sem_rd) if sem_rd else 'NAO (orfa)'}")
            if irmaos:
                print(f"    !! DUPLICATA: ja existe outro RD com a mesma base (ids={irmaos}). PULANDO.")
                continue

            if not args.aplicar:
                print("    (dry-run)\n")
                continue

            r = await c.post("/Veiculos/Atualizar",
                             params={"key": settings.weso_api_key},
                             json={"veiculo_id": vid, "placa": a})
            print(f"    POST -> HTTP {r.status_code}: {r.text[:150]}")

            achados = [x for x in (await get(c, "/Veiculos/Consultar", {"placa": a})).get("veiculos") or []
                       if x.get("id") == vid]
            if not achados:
                print(f"    !! FALHOU: {a!r} nao encontra o id {vid}. PARANDO.")
                return
            novo = achados[0]
            if novo.get("rastreador_id") != v.get("rastreador_id"):
                print(f"    !! rastreador_id MUDOU ({v.get('rastreador_id')} -> "
                      f"{novo.get('rastreador_id')}). PARANDO.")
                return
            print(f"    OK placa={novo.get('placa')!r} rastreador_id={novo.get('rastreador_id')} (intacto)")
            print(f"    reverter: {{'veiculo_id': {vid}, 'placa': {atual!r}}}\n")

    print("fim.")


asyncio.run(main())
