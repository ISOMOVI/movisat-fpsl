"""Normaliza espaco/caixa das placas na WESO: ' TTX 0H91' -> 'TTX 0H91'.

ESCREVE NA WESO (producao). Autorizado pelo usuario em 2026-07-29.
Irmao de corrigir_placas_espaco.py (27/07), que tratava outro caso (placa
convencional SEM espaco: 'MCJ0232' -> 'MCJ 0232').

Problema: 110 de 1.962 veiculos tem espaco nas pontas, espaco duplo ou
minuscula. `/Veiculos/Consultar?placa=` compara por igualdade EXATA, entao
esses registros ficam invisiveis para qualquer rotina que consulte por placa —
falha silenciosa, devolve vazio em vez de erro. Achado ao buscar o equipamento
da placa TTX 0H91 do termo 8788.

Diferenca de metodo em relacao ao script de 27/07: la o estado era relido
consultando as duas grafias. Aqui isso NAO serve — a grafia velha tem espaco e
a consulta por placa e exatamente o que falha. Entao o estado e lido baixando a
base completa e procurando por ID, que e o unico identificador confiavel.

Seguranca (mesma disciplina do script de 27/07):
  - nada roda sem --aplicar (sem a flag, so mostra o que faria)
  - --somente <id> processa UM registro, pra validar antes do lote
  - le o estado ANTES, escreve, RE-LE e confirma; falhou, para tudo na hora
  - aborta se o rastreador_id mudar
  - COLISOES sao excluidas: aparar espaco de duas placas que colidem
    transformaria duplicata escondida em conflito ativo
  - imprime o comando de reversao de cada alteracao

Uso na VPS:
  venv/bin/python normalizar_espacos_placas.py                        # dry-run
  venv/bin/python normalizar_espacos_placas.py --aplicar --somente 73945
  venv/bin/python normalizar_espacos_placas.py --aplicar              # o resto
"""
import argparse
import asyncio
import re
from collections import defaultdict

import httpx

from fpsl_weso.config import settings

TIMEOUT = 180


def normalizar(p: str) -> str:
    """Apara as pontas, colapsa espaco duplo, caixa alta. NAO reformata:
    'chassi como vier' (decisao PADRAO DE PLACA, 27/07) — identificador nao
    convencional como 'DZCACCDBBAHB' ou 'LS ABG' e placa valida e so tem as
    pontas aparadas."""
    return re.sub(r"\s+", " ", str(p or "")).strip().upper()


def chave(p: str) -> str:
    return re.sub(r"\s+", "", str(p or "")).upper()


async def baixar_base(c):
    r = await c.get("/Veiculos/Consultar", params={"key": settings.weso_api_key})
    corpo = r.json()
    dados = corpo.get("Data", corpo)
    return dados.get("veiculos") or []


def levantar_alvos(veic):
    """Quem precisa mudar, ja excluindo colisoes."""
    grupos = defaultdict(list)
    for v in veic:
        k = chave(v.get("placa"))
        if k:
            grupos[k].append(v["id"])
    em_colisao = {k for k, ids in grupos.items() if len(ids) > 1}

    alvos, pulados = [], []
    for v in veic:
        atual = str(v.get("placa") or "")
        novo = normalizar(atual)
        if not novo or atual == novo:
            continue
        if chave(atual) in em_colisao:
            pulados.append((v["id"], atual, novo))
            continue
        alvos.append({"veiculo_id": v["id"], "de": atual, "para": novo,
                      "rastreador_id": v.get("rastreador_id")})
    return alvos, pulados


async def por_placa(c, placa):
    r = await c.get("/Veiculos/Consultar",
                    params={"key": settings.weso_api_key, "placa": placa})
    corpo = r.json()
    dados = corpo.get("Data", corpo)
    return dados.get("veiculos") or []


async def confirmar(c, veiculo_id, placa_nova, base_cache):
    """Estado APOS a escrita. Consulta pela placa NOVA — que ja esta limpa,
    entao a igualdade exata da API funciona (1 chamada em vez de baixar 1.962).
    Se nao achar, cai na base completa: nao confirmar e motivo de PARAR, e
    'nao achei rapido' nao pode ser confundido com 'nao gravou'."""
    for v in await por_placa(c, placa_nova):
        if v.get("id") == veiculo_id:
            return v
    for v in await baixar_base(c):
        if v.get("id") == veiculo_id:
            return v
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--somente", type=int)
    args = ap.parse_args()

    async with httpx.AsyncClient(base_url=settings.weso_base_url, timeout=TIMEOUT) as c:
        base = await baixar_base(c)
        alvos, pulados = levantar_alvos(base)
        mapa_base = {v["id"]: v for v in base}
        print(f"base: {len(base)} veiculos | a normalizar: {len(alvos)} | "
              f"pulados por colisao: {len(pulados)}")
        for vid, de, para in pulados:
            print(f"   PULADO (colisao) id={vid} {de!r} -> {para!r}")
        print()

        if args.somente:
            alvos = [a for a in alvos if a["veiculo_id"] == args.somente]
            if not alvos:
                print("nenhum alvo com esse id (pode ja estar correto ou estar em colisao)")
                return

        modo = "APLICANDO (escreve na WESO)" if args.aplicar else "DRY-RUN (nao escreve nada)"
        print(f"== {modo} == {len(alvos)} registro(s)\n")

        for a in alvos:
            vid, de, para = a["veiculo_id"], a["de"], a["para"]
            print(f"--- id={vid}  {de!r} -> {para!r}")
            antes = mapa_base.get(vid)
            if not antes:
                print("    ABORTADO: id nao encontrado na base. PARANDO.")
                return
            if str(antes.get("placa")) == para:
                print("    JA ESTAVA CORRIGIDO, pulando\n")
                continue
            print(f"    antes: placa={antes.get('placa')!r} rastreador_id={antes.get('rastreador_id')}")

            if not args.aplicar:
                print("    (dry-run, nada enviado)\n")
                continue

            r = await c.post("/Veiculos/Atualizar",
                             params={"key": settings.weso_api_key},
                             json={"veiculo_id": vid, "placa": para})
            print(f"    POST /Veiculos/Atualizar -> HTTP {r.status_code}: {r.text[:160]}")

            depois = await confirmar(c, vid, para, base)
            if not depois or str(depois.get("placa")) != para:
                print(f"    !! FALHOU: continua {depois.get('placa') if depois else None!r}. PARANDO.")
                return
            if depois.get("rastreador_id") != antes.get("rastreador_id"):
                print("    !! ATENCAO: rastreador_id MUDOU. PARANDO.")
                return
            print(f"    OK confirmado: placa={depois.get('placa')!r} "
                  f"rastreador_id={depois.get('rastreador_id')} (inalterado)")
            print(f"    reverter: json={{'veiculo_id': {vid}, 'placa': {de!r}}}\n")

    print("fim.")


asyncio.run(main())
