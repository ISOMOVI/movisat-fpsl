"""
Importa todos os clientes ativos da Harmonit (GET /ObterClientes, paginado)
para uma tabela local no banco do FPSL.

Uso:
  python3 import_harmonit_clientes.py
"""
import asyncio
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fpsl_weso import harmonit_client as hc

DB_PATH = Path(__file__).parent / "data" / "fpsl.db"
TAKE = 100

SCHEMA = """
CREATE TABLE IF NOT EXISTS harmonit_clientes (
    id                 INTEGER PRIMARY KEY,
    nome               TEXT,
    nome_fantasia      TEXT,
    codigo_cliente     TEXT,
    situacao_desc      TEXT,
    situacao_id        INTEGER,
    cnpj_cpf           TEXT,
    tipo_pessoa        INTEGER,
    ativo              INTEGER,
    bloqueado          INTEGER,
    cep                TEXT,
    endereco           TEXT,
    numero             TEXT,
    bairro             TEXT,
    cidade             TEXT,
    uf                 TEXT,
    email              TEXT,
    importado_em       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_harmonit_clientes_nome ON harmonit_clientes(nome);
CREATE INDEX IF NOT EXISTS idx_harmonit_clientes_cidade_uf ON harmonit_clientes(cidade, uf);
"""


async def main():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM harmonit_clientes")

    await hc.start_harmonit_client()
    total_importado = 0
    importado_em = datetime.now(timezone.utc).isoformat()
    try:
        skip = 0
        while True:
            resultado = await hc.harmonit_get(
                "/ObterClientes",
                {"skip": skip, "take": TAKE, "somenteAtivos": "true"},
            )
            lista = resultado.get("lista", [])
            if not lista:
                break

            for c in lista:
                end = c.get("enderecoPrincipal") or {}
                contato = c.get("contatoPrincipal") or {}
                conn.execute(
                    """INSERT OR REPLACE INTO harmonit_clientes
                    (id, nome, nome_fantasia, codigo_cliente, situacao_desc, situacao_id,
                     cnpj_cpf, tipo_pessoa, ativo, bloqueado, cep, endereco, numero,
                     bairro, cidade, uf, email, importado_em)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        c.get("id"),
                        c.get("nome"),
                        c.get("nomeFantasia"),
                        c.get("codigoCliente"),
                        c.get("situacaoClienteDesc"),
                        c.get("situacaoClienteId"),
                        c.get("cnpJ_CPF"),
                        c.get("tipoPessoa"),
                        1 if c.get("ativo") else 0,
                        1 if c.get("bloqueado") else 0,
                        end.get("cep"),
                        end.get("endereco"),
                        end.get("numero"),
                        end.get("bairro"),
                        end.get("cidade"),
                        end.get("uf"),
                        contato.get("email"),
                        importado_em,
                    ),
                )
                total_importado += 1

            sumario = resultado.get("sumario", {})
            contador_total = sumario.get("contador", 0)
            skip += TAKE
            print(f"  ... {min(skip, contador_total)}/{contador_total}")
            if skip >= contador_total:
                break
    finally:
        await hc.stop_harmonit_client()

    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM harmonit_clientes").fetchone()[0]
    com_cidade = conn.execute(
        "SELECT COUNT(*) FROM harmonit_clientes WHERE cidade IS NOT NULL AND cidade != ''"
    ).fetchone()[0]
    sem_cidade = total - com_cidade
    conn.close()

    print(f"\nImportado: {total_importado} clientes ativos da Harmonit")
    print(f"Total na tabela: {total}")
    print(f"Com cidade/UF preenchida: {com_cidade}")
    print(f"Sem cidade/UF (endereço vazio): {sem_cidade}")


if __name__ == "__main__":
    asyncio.run(main())
