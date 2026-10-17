"""Quais laços do FPSL estão mudos — SÓ RELATA (16/10/2026).

🔵 Parte C da proposta aceita em 16/10: *"proponha"* sobre o FPSL não ter onde
deixar rastro. Nasce **só relatando**, no molde do `agentes_mudos.py` do
MoviZap, mas **sem mandar WhatsApp** — primeiro uma semana de saída em arquivo,
depois se decide se vira aviso. Alarme que ninguém leu uma vez é alarme que
todos ignoram depois.

🚨 "MUDO" É SUSPEITA, NÃO SENTENÇA. O limite é o dobro do intervalo esperado
(`rotinas.TOLERANCIA`), e "sem registro" **não** é mudo: é laço que ainda não
passou uma vez desde que o serviço subiu. Confundir os dois acusaria a VPS
recém-reiniciada de estar quebrada — foi justamente o que o reinício de 16/10
mostrou que a tela fazia.

Uso:
    venv/bin/python scripts/rotinas_mudas.py            tabela
    venv/bin/python scripts/rotinas_mudas.py --json     o mesmo, em JSON

Saída de processo: 0 sempre. Quem lê decide o que fazer — este script não
derruba nada e não escreve nada.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fpsl_weso import rotinas, storage  # noqa: E402

AQUI = ZoneInfo("America/Sao_Paulo")


def _local(iso: str) -> str:
    """UTC no banco, hora de casa na tela. A mesma regra do módulo de demandas."""
    if not iso:
        return "—"
    try:
        q = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if q.tzinfo is None:
        q = q.replace(tzinfo=timezone.utc)
    return q.astimezone(AQUI).strftime("%d/%m %H:%M")


def _idade(iso: str) -> str:
    if not iso:
        return "—"
    try:
        q = datetime.fromisoformat(iso)
    except ValueError:
        return "?"
    if q.tzinfo is None:
        q = q.replace(tzinfo=timezone.utc)
    seg = (datetime.now(timezone.utc) - q).total_seconds()
    if seg < 90:
        return f"{int(seg)}s"
    if seg < 5400:
        return f"{int(seg // 60)}min"
    return f"{seg / 3600:.1f}h"


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    storage.init_db()
    estado = await rotinas.estado()

    if a.json:
        print(json.dumps(estado, ensure_ascii=False, indent=2))
        return 0

    print(f"Laços do FPSL — {datetime.now(AQUI):%d/%m/%Y %H:%M} (hora local)")
    print(f"{'laço':26} {'última':12} {'idade':>7}  situação / resultado")
    mudos, sem_registro = [], []
    for r in estado:
        if r["sem_registro"]:
            situacao = "SEM REGISTRO (ainda não passou desde o boot)"
            sem_registro.append(r["rotulo"])
        elif r["atrasada"]:
            situacao = f"MUDA (esperado a cada {r['intervalo_seg'] // 60} min) — {r['resultado']}"
            mudos.append(r["rotulo"])
        else:
            situacao = r["resultado"] or "ok"
        print(f"{r['rotulo'][:26]:26} {_local(r['ultima_em']):12} "
              f"{_idade(r['ultima_em']):>7}  {situacao}")

    print()
    # 🚨 O resumo DIZ NÚMERO. "Tudo ok" não distingue vigia funcionando de vigia
    # olhando para base vazia — a lição do vigia das Ligações, de 15/10.
    print(f"{len(estado)} laços: {len(estado) - len(mudos) - len(sem_registro)} em dia, "
          f"{len(mudos)} mudos, {len(sem_registro)} sem registro.")
    if mudos:
        print("mudos: " + ", ".join(mudos))
    if sem_registro:
        print("sem registro: " + ", ".join(sem_registro))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
