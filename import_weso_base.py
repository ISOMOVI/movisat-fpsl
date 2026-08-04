"""
Importa o export de equipamentos/veiculos da WESO (planilha completa,
ponto-e-virgula, com cabecalho) para uma tabela nova no banco local do FPSL.

Uso:
  python3 import_weso_base.py arquivo.csv
"""
import sys
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "fpsl.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS weso_equipamentos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    placa         TEXT,
    apelido       TEXT,
    razao_social  TEXT NOT NULL,
    nome_fantasia TEXT,
    perfil        TEXT,
    numero_serie  TEXT,
    rastreador    TEXT,
    grupo_eventos TEXT,
    telefone      TEXT,
    operadora     TEXT,
    iccid         TEXT,
    apn           TEXT,
    marca         TEXT,
    modelo        TEXT,
    data_cadastro TEXT,
    acessorios    TEXT,
    importado_em  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weso_equip_razao_social ON weso_equipamentos(razao_social);
CREATE INDEX IF NOT EXISTS idx_weso_equip_placa ON weso_equipamentos(placa);
"""

COLS = [
    "placa", "apelido", "razao_social", "nome_fantasia", "perfil",
    "numero_serie", "rastreador", "grupo_eventos", "telefone", "operadora",
    "iccid", "apn", "marca", "modelo", "data_cadastro", "acessorios",
]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"Arquivo nao encontrado: {csv_path}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    # limpa import anterior (essa tabela representa "estado atual" da WESO,
    # nao historico -- reimportar substitui, nao acumula)
    conn.execute("DELETE FROM weso_equipamentos")

    importado_em = datetime.now(timezone.utc).isoformat()
    linhas_importadas = 0
    linhas_ignoradas = 0

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            razao_social = (row.get("Razão Social") or "").strip()
            if not razao_social:
                linhas_ignoradas += 1
                continue
            valores = (
                (row.get("Placa") or "").strip(),
                (row.get("Apelido") or "").strip(),
                razao_social,
                (row.get("Nome Fantasia") or "").strip(),
                (row.get("Perfil") or "").strip(),
                (row.get("Numero de Série") or "").strip(),
                (row.get("Rastreador") or "").strip(),
                (row.get("Grupo de Eventos") or "").strip(),
                (row.get("Telefone") or "").strip(),
                (row.get("Operadora") or "").strip(),
                (row.get("IccId") or "").strip(),
                (row.get("Apn") or "").strip(),
                (row.get("Marca") or "").strip(),
                (row.get("Modelo") or "").strip(),
                (row.get("Data Cadastro") or "").strip(),
                (row.get("Acessórios") or "").strip(),
                importado_em,
            )
            conn.execute(
                f"INSERT INTO weso_equipamentos ({', '.join(COLS)}, importado_em) "
                f"VALUES ({', '.join(['?'] * (len(COLS) + 1))})",
                valores,
            )
            linhas_importadas += 1

    conn.commit()

    # estatisticas rapidas
    total_registros = conn.execute("SELECT COUNT(*) FROM weso_equipamentos").fetchone()[0]
    total_clientes = conn.execute("SELECT COUNT(DISTINCT razao_social) FROM weso_equipamentos").fetchone()[0]
    total_placas_validas = conn.execute(
        "SELECT COUNT(DISTINCT placa) FROM weso_equipamentos "
        "WHERE placa NOT LIKE 'A DEFINIR%' AND placa NOT LIKE 'CHASSI%' AND placa NOT LIKE 'TERMO%'"
    ).fetchone()[0]
    total_pendentes = conn.execute(
        "SELECT COUNT(*) FROM weso_equipamentos "
        "WHERE placa LIKE 'A DEFINIR%' OR placa LIKE 'CHASSI%' OR placa LIKE 'TERMO%'"
    ).fetchone()[0]

    conn.close()

    print(f"Importado: {linhas_importadas} registros ({linhas_ignoradas} ignorados por falta de razao_social)")
    print(f"Total na tabela: {total_registros}")
    print(f"Clientes distintos (razao_social): {total_clientes}")
    print(f"Placas validas distintas: {total_placas_validas}")
    print(f"Equipamentos com placa pendente (A DEFINIR/CHASSI/TERMO): {total_pendentes}")


if __name__ == "__main__":
    main()
