"""Traz para a hora local os carimbos do painel de demandas gravados em UTC.

🚨 O `datetime('now')` do SQLite é UTC. Medido em 07/08: hora local 18:12,
`datetime('now')` 21:12 -- 3 horas à frente. O código já foi corrigido para
`datetime('now','localtime')`; este script cuida do que entrou antes.

⚠️ POR QUE CORRIGIR, SE NINGUÉM VÊ ESSAS HORAS HOJE

A tela só mostra "último toque: quem", nunca quando. Deixar como está pareceria
inofensivo -- mas a partir da correção do código os carimbos NOVOS nascem
locais, e aí a coluna passa a misturar dois fusos. Dado uniformemente errado
alguém conserta; dado misturado ninguém sabe qual metade acreditar.

⚠️ O Brasil não tem horário de verão desde 2019, então o deslocamento é -3h
constante. Se voltasse, este script precisaria de fuso, não de subtração.

Uso:  corrigir_hora_demandas.py [--aplicar]
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

BANCO = Path("/home/claude/fpsl_weso/data/fpsl.db")
CAMPOS = [
    ("demanda_item", "atualizado_em"),
    ("demanda_etapa", "concluida_em"),
    ("demanda_quadro", "criado_em"),
]
CORTE = "2026-08-07 18:30:00"   # nada gravado depois disto é UTC


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--aplicar", action="store_true")
    args = p.parse_args()

    con = sqlite3.connect(BANCO)
    con.row_factory = sqlite3.Row

    print("ANTES:")
    total = 0
    for tabela, col in CAMPOS:
        linhas = con.execute(
            f"SELECT id, {col} AS v FROM {tabela} "
            f"WHERE {col} IS NOT NULL AND {col} < ? ORDER BY id", (CORTE,)).fetchall()
        total += len(linhas)
        print(f"  {tabela}.{col}: {len(linhas)} a corrigir")
        for r in linhas[:3]:
            novo = con.execute("SELECT datetime(?, '-3 hours')", (r["v"],)).fetchone()[0]
            print(f"     id={r['id']}  {r['v']}  ->  {novo}")

    if not total:
        print("\nnada a corrigir.")
        return 0
    if not args.aplicar:
        print("\n(simulação -- rode com --aplicar)")
        return 0

    # 🚨 O banco é o mesmo do FPSL inteiro. Cópia antes de mexer.
    backup = BANCO.with_suffix(".db.bak_hora_2026-08-07")
    shutil.copy2(BANCO, backup)
    print(f"\nbackup: {backup}")

    for tabela, col in CAMPOS:
        con.execute(
            f"UPDATE {tabela} SET {col} = datetime({col}, '-3 hours') "
            f"WHERE {col} IS NOT NULL AND {col} < ?", (CORTE,))
    con.commit()

    # A única prova é reler.
    print("\nDEPOIS, relendo:")
    sobrou = 0
    for tabela, col in CAMPOS:
        n = con.execute(
            f"SELECT COUNT(*) FROM {tabela} WHERE {col} IS NOT NULL AND {col} < ?",
            (CORTE,)).fetchone()[0]
        sobrou += n
        exemplo = con.execute(
            f"SELECT {col} FROM {tabela} WHERE {col} IS NOT NULL "
            f"ORDER BY id DESC LIMIT 1").fetchone()
        print(f"  {tabela}.{col}: {n} ainda antigos | último = {exemplo[0] if exemplo else '—'}")
    print(f"\nesperado 0 restantes; obtido {sobrou}")
    return 0 if sobrou == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
