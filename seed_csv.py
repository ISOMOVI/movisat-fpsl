"""
Importa CSV pipe-delimitado para o banco local do FPSL.

Uso:
  python3 seed_csv.py rastreadores arquivo.csv
  python3 seed_csv.py veiculos     arquivo.csv

Formatos esperados (primeira linha = cabeçalho, ignorada):
  rastreadores:  ID_SERIAL | ID_EQUIPAMENTO
  veiculos:      PLACA     | ID_VEICULO
"""
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "fpsl.db"

CONFIGS = {
    "rastreadores": {
        "table":   "rastreadores_serials",
        "col_a":   "serial",
        "col_b":   "weso_id",
        "cast_b":  int,
        "label_a": "serial",
        "label_b": "weso_id",
    },
    "veiculos": {
        "table":   "veiculos",
        "col_a":   "placa",
        "col_b":   "veiculo_id",
        "cast_b":  int,
        "label_a": "placa",
        "label_b": "veiculo_id",
    },
}


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    tipo, csv_path = sys.argv[1], sys.argv[2]
    if tipo not in CONFIGS:
        print(f"Tipo inválido: '{tipo}'. Use 'rastreadores' ou 'veiculos'.")
        sys.exit(1)

    cfg = CONFIGS[tipo]
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"Arquivo não encontrado: {csv_path}")
        sys.exit(1)

    linhas = csv_file.read_text(encoding="utf-8").splitlines()
    if not linhas:
        print("Arquivo vazio.")
        sys.exit(1)

    # Ignora cabeçalho (primeira linha)
    dados = []
    erros = []
    for n, linha in enumerate(linhas[1:], start=2):
        if not linha.strip():
            continue
        partes = [p.strip() for p in linha.split("|")]
        if len(partes) < 2:
            erros.append(f"  linha {n}: formato inválido — '{linha}'")
            continue
        val_a = partes[0]
        try:
            val_b = cfg["cast_b"](partes[1])
        except ValueError:
            erros.append(f"  linha {n}: '{partes[1]}' não é inteiro válido")
            continue
        if not val_a:
            erros.append(f"  linha {n}: {cfg['label_a']} vazio")
            continue
        dados.append((val_a, val_b))

    if erros:
        print(f"Erros encontrados ({len(erros)}):")
        for e in erros:
            print(e)
        if not dados:
            sys.exit(1)
        print()

    criado_em = datetime.now(timezone.utc).isoformat()
    sql = (
        f"INSERT OR REPLACE INTO {cfg['table']} "
        f"({cfg['col_a']}, {cfg['col_b']}, criado_em) VALUES (?, ?, ?)"
    )

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.executemany(sql, [(a, b, criado_em) for a, b in dados])
        conn.commit()
        print(f"[{tipo}] {cursor.rowcount} registro(s) importado(s) para '{cfg['table']}'.")
        if erros:
            print(f"[{tipo}] {len(erros)} linha(s) ignorada(s) por erro.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
