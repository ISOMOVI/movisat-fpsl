# -*- coding: utf-8 -*-
import csv
import sqlite3

DB_PATH = "/home/claude/fpsl_weso/data/fpsl.db"
RASTREADORES_CSV = "/home/claude/fpsl_weso/data/rastreadores.csv"
CHIPS_CSV = "/home/claude/fpsl_weso/data/chips.csv"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("DROP TABLE IF EXISTS weso_rastreadores")
cur.execute("""
CREATE TABLE weso_rastreadores (
    numero_serie TEXT PRIMARY KEY,
    modelo TEXT,
    situacao TEXT,
    iccid TEXT,
    operadora TEXT,
    apn TEXT,
    telefone TEXT,
    tipo TEXT,
    fornecedor TEXT,
    nota_fiscal TEXT,
    lote TEXT,
    data_cadastro TEXT
)
""")

cur.execute("DROP TABLE IF EXISTS weso_chips")
cur.execute("""
CREATE TABLE weso_chips (
    iccid TEXT PRIMARY KEY,
    numero TEXT,
    operadora TEXT,
    apn TEXT,
    numero_serie TEXT,
    fornecedor TEXT,
    data_cadastro TEXT
)
""")

n_rast = 0
with open(RASTREADORES_CSV, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        cur.execute(
            "INSERT OR REPLACE INTO weso_rastreadores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["Número de Série"].strip(),
                row["Modelo"].strip(),
                row["Situação"].strip(),
                row["ICCID"].strip(),
                row["Operadora"].strip(),
                row["Apn"].strip(),
                row["Telefone"].strip(),
                row["Tipo"].strip(),
                row["Fornecedor"].strip(),
                row["Nota Fiscal"].strip(),
                row["Lote"].strip(),
                row["Data Cadastro"].strip(),
            ),
        )
        n_rast += 1

n_chips = 0
with open(CHIPS_CSV, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        cur.execute(
            "INSERT OR REPLACE INTO weso_chips VALUES (?,?,?,?,?,?,?)",
            (
                row["ICCID"].strip(),
                row["Número"].strip(),
                row["Operadora"].strip(),
                row["APN"].strip(),
                row["Número de Série"].strip(),
                row["Fornecedor"].strip(),
                row["Data Cadastro"].strip(),
            ),
        )
        n_chips += 1

conn.commit()

print(f"weso_rastreadores importados: {n_rast}")
print(f"weso_chips importados: {n_chips}")

print("\n--- validação rápida ---")
cur.execute("SELECT COUNT(*) FROM weso_rastreadores")
print("total na tabela rastreadores:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM weso_chips")
print("total na tabela chips:", cur.fetchone()[0])

cur.execute("SELECT situacao, COUNT(*) FROM weso_rastreadores GROUP BY situacao ORDER BY 2 DESC")
print("\nrastreadores por situação:")
for situacao, qtd in cur.fetchall():
    print(f"  {situacao}: {qtd}")

conn.close()
