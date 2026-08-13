"""Rotula chassi no campo `placa` da WESO: '9BWKB45U8KP018607' -> 'CHASSI: 9BWKB45U8KP018607'.

ESCREVE NA WESO (producao). Autorizado pelo usuario em 2026-08-13.
Irmao de normalizar_espacos_placas.py (29/07) e corrigir_placas_espaco.py
(27/07) -- mesma disciplina, transformacao diferente.

Por que: o campo `placa` da WESO e texto livre e e o ALVO da busca. A regra de
07/08 so autoriza o extrator a tratar valor nao convencional como identificador
quando o ROTULO e explicito (`CHASSI`/`SERIE`); sem rotulo, o veiculo cai em
`veiculos_sem_placa` e vira revisao humana. Havia 33 chassis crus, sem rotulo:
esses veiculos nao eram reconhecidos automaticamente em nenhum termo.

🚨 REGRA ESTRITA: CHASSI E 17 ALFANUMERICOS. Uma versao anterior deste
levantamento usou "9 a 20 caracteres, token unico" e teria proposto virar
chassi os recipientes `-UPGRADE`, a `TAG identificacao` e os codigos `OBD 4G`.
Adivinhar identificador a partir de texto solto foi como nasceu o `RFD 2447`.

Seguranca (mesma dos irmaos):
  - nada roda sem --aplicar (sem a flag, so mostra o que faria)
  - --somente <id> processa UM registro, pra validar antes do lote
  - le o estado ANTES, escreve, RE-LE e confirma; falhou, para tudo na hora
  - aborta se o rastreador_id mudar
  - COLISOES sao excluidas
  - imprime o comando de reversao de cada alteracao

Uso na VPS:
  venv/bin/python rotular_chassi_weso.py                        # dry-run
  venv/bin/python rotular_chassi_weso.py --aplicar --somente 15225
  venv/bin/python rotular_chassi_weso.py --aplicar              # o resto
"""
import argparse
import asyncio
import re
from collections import defaultdict

import httpx

from fpsl_weso.config import settings

TIMEOUT = 180
ROTULO = "CHASSI: "

# 🚨 FORA POR DECISAO DO USUARIO (13/08). `TRATOR MF3147165M1` da 17
# alfanumericos por COINCIDENCIA -- "TRATOR" e a palavra trator, e o apelido do
# registro ja e "MASSEY FERGUSON". O identificador real e MF3147165M1, com 11.
# Incluir seria gravar a palavra dentro do chassi.
EXCLUIDOS = {72390}

# convencoes conhecidas que nao se toca
INTOCAVEIS = ("-UPGRADE", "-MANUT", "SUBST", "TERMO", "TAG", "OBD",
              "MOVEL", "MÓVEL", "COD:", "SERIE", "SÉRIE", "ISCA")

_ROTULO_RE = re.compile(r"^\s*(CHASSI|CHSS)\s*:?\s*", re.I)


def alnum(v) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(v or "").upper())


def alvo_de(placa: str) -> str | None:
    """Valor padronizado, ou None se este registro nao e chassi evidente."""
    bruta = str(placa or "")
    up = bruta.upper()
    if any(t in up for t in INTOCAVEIS):
        return None
    numero = alnum(_ROTULO_RE.sub("", bruta))
    if len(numero) != 17:                 # 🚨 evidente = 17, sem excecao
        return None
    novo = ROTULO + numero
    return novo if novo != bruta else None


async def baixar_base(c) -> list[dict]:
    """⚠️ O ENVELOPE E {"Data": {"veiculos": [...]}}. Ler `veiculos` na raiz
    devolve None -> `or []` -> ZERO registros, sem erro nenhum. Aconteceu na
    primeira versao deste script. Mesma familia do {sumario, lista} do
    Harmonit: envelope errado nao levanta, so entrega vazio."""
    r = await c.get("/Veiculos/Consultar", params={"key": settings.weso_api_key})
    r.raise_for_status()
    corpo = r.json()
    dados = corpo.get("Data", corpo)
    veic = dados.get("veiculos") or []
    if not veic:
        raise SystemExit("ABORTADO: base vazia -- envelope mudou ou chave invalida.")
    return veic


def por_id(base, vid):
    return next((v for v in base if v.get("id") == vid), None)


async def confirmar(c, vid, esperado, base_antes):
    """RE-LE o estado. A prova nao e o HTTP 200 -- os dois sistemas mentem no
    codigo de retorno."""
    base = await baixar_base(c)
    return por_id(base, vid)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--somente", type=int)
    args = ap.parse_args()

    async with httpx.AsyncClient(base_url=settings.weso_base_url, timeout=TIMEOUT) as c:
        base = await baixar_base(c)
        print(f"base: {len(base)} veiculos\n")

        # chaves ocupadas, para nao criar colisao
        ocupadas = defaultdict(list)
        for v in base:
            ocupadas[alnum(v.get("placa"))].append(v.get("id"))

        alvos = []
        for v in base:
            vid = v.get("id")
            if vid in EXCLUIDOS:
                continue
            novo = alvo_de(v.get("placa"))
            if not novo:
                continue
            outros = [i for i in ocupadas.get(alnum(novo), []) if i != vid]
            if outros:
                print(f"  PULADO id={vid} [{v.get('placa')}] -> colidiria com {outros}")
                continue
            alvos.append((vid, v.get("placa"), novo, v))

        if args.somente:
            alvos = [a for a in alvos if a[0] == args.somente]

        print(f"{len(alvos)} registro(s) a alterar"
              f"{' (DRY-RUN)' if not args.aplicar else ''}\n")

        for vid, de, para, antes in alvos:
            print(f"  id={vid}  [{de}]  ->  [{para}]   {antes.get('descricao') or ''}")
            if not args.aplicar:
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
