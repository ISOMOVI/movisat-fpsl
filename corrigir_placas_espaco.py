"""Padroniza placa convencional sem espaco na WESO: 'MCJ0232' -> 'MCJ 0232'.

ESCREVE NA WESO (producao). Autorizado pelo usuario em 2026-07-27.

Seguranca:
  - nada roda sem --aplicar (sem a flag, so mostra o que faria)
  - --somente <id> processa UM registro, pra validar antes do resto
  - le o estado ANTES, escreve, e RE-LE pra confirmar; se a confirmacao falhar,
    para tudo na hora (nao segue pro proximo)
  - imprime o comando de reversao de cada alteracao aplicada

Uso na VPS:
  venv/bin/python corrigir_placas_espaco.py                      # dry-run, todas
  venv/bin/python corrigir_placas_espaco.py --aplicar --somente 57146
  venv/bin/python corrigir_placas_espaco.py --aplicar            # o resto
"""
import argparse
import asyncio

import httpx

from fpsl_weso.config import settings

TIMEOUT = 180

# levantadas em 2026-07-27 (listar_placas_padronizar.py, grupo A)
ALVOS = [
    {"veiculo_id": 57146, "de": "MCJ0232", "para": "MCJ 0232"},
    {"veiculo_id": 77097, "de": "RET5662", "para": "RET 5662"},
    {"veiculo_id": 69648, "de": "RET5816", "para": "RET 5816"},
    {"veiculo_id": 69655, "de": "RET5819", "para": "RET 5819"},
    {"veiculo_id": 69652, "de": "RET6007", "para": "RET 6007"},
]


async def consultar_por_placa(c, placa):
    r = await c.get("/Veiculos/Consultar", params={"key": settings.weso_api_key, "placa": placa})
    corpo = r.json()
    dados = corpo.get("Data", corpo)
    return dados.get("veiculos") or []


async def estado(c, veiculo_id, placa_velha, placa_nova):
    """Onde o registro esta AGORA, sem baixar os 1.965: consulta as duas grafias.

    Devolve (grafia_encontrada, objeto) ou (None, None) se sumiu das duas.
    """
    for grafia in (placa_nova, placa_velha):
        for v in await consultar_por_placa(c, grafia):
            if v.get("id") == veiculo_id:
                return grafia, v
    return None, None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--somente", type=int)
    args = ap.parse_args()

    alvos = [a for a in ALVOS if not args.somente or a["veiculo_id"] == args.somente]
    if not alvos:
        print("nenhum alvo com esse id")
        return

    modo = "APLICANDO (escreve na WESO)" if args.aplicar else "DRY-RUN (nao escreve nada)"
    print(f"== {modo} == {len(alvos)} registro(s)\n")

    async with httpx.AsyncClient(base_url=settings.weso_base_url, timeout=TIMEOUT) as c:
        for a in alvos:
            vid, de, para = a["veiculo_id"], a["de"], a["para"]
            print(f"--- id={vid}  {de!r} -> {para!r}")

            grafia, antes = await estado(c, vid, de, para)
            if not antes:
                print("    ABORTADO: id nao encontrado por nenhuma das duas grafias")
                return
            if grafia == para:
                print(f"    JA ESTAVA CORRIGIDO (placa={para!r}), pulando\n")
                continue
            print(f"    antes: placa={antes.get('placa')!r} rastreador_id={antes.get('rastreador_id')}")

            if not args.aplicar:
                print("    (dry-run, nada enviado)\n")
                continue

            r = await c.post("/Veiculos/Atualizar",
                             params={"key": settings.weso_api_key},
                             json={"veiculo_id": vid, "placa": para})
            print(f"    POST /Veiculos/Atualizar -> HTTP {r.status_code}: {r.text[:200]}")

            grafia2, depois = await estado(c, vid, de, para)
            if grafia2 != para:
                print(f"    !! FALHOU: o registro continua como {grafia2!r}. PARANDO, nada mais sera tocado.")
                return
            print(f"    OK confirmado: placa={depois.get('placa')!r} "
                  f"rastreador_id={depois.get('rastreador_id')} (era {antes.get('rastreador_id')})")
            if depois.get("rastreador_id") != antes.get("rastreador_id"):
                print("    !! ATENCAO: o rastreador_id MUDOU. PARANDO.")
                return

            sobrou = [v for v in await consultar_por_placa(c, de) if v.get("id") == vid]
            print(f"    grafia antiga {de!r} ainda acha este id? {'SIM (ruim)' if sobrou else 'nao (ok)'}")
            print(f"    reverter: json={{'veiculo_id': {vid}, 'placa': '{de}'}}\n")

    print("fim.")


asyncio.run(main())
