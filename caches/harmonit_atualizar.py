"""Cache local da base de veiculos do Harmonit. Roda 1x por dia via cron.

🚨 POR QUE EXISTE. A lista de placas da etapa 3 dos perfis SEM TERMO saia da
tabela `harmonit_veiculos`, dentro do banco do app, e NADA a atualizava --
nenhum cron, nenhum caminho no codigo. Ela andava quando alguem lembrava de
rodar um script a mao.

Medido em 2026-08-24: Harmonit ao vivo 9.116 x espelho 9.114. As duas que
faltavam eram `ENU 2H80` e `FWB 0E36` -- e a segunda tinha sido criada pelo
PROPRIO painel, tres horas antes. A regra da casa e que manutencao so acontece
em placa que ja esta na WESO ha pelo menos um dia; essa regra so se sustenta se
a base for refeita todo dia, e ela nao era refeita nunca.

Este script e o IRMAO do `weso_cache/atualizar.py`, de proposito: mesma forma,
mesma estrategia, mesmo formato de log. Um arquivo por sistema, um cron por
arquivo (decisao do usuario, 24/08).

Estrategia igual a do irmao: monta um banco NOVO num arquivo temporario e so
troca pelo bom no fim, atomicamente. Se o Harmonit cair no meio, o cache antigo
continua servindo -- cache pela metade e pior que cache velho, porque parece
completo.

Reusa o cliente do FPSL para nao duplicar a chave da API em lugar nenhum. Por
isso roda com o venv do FPSL.

Uso:
    /home/claude/fpsl_weso/venv/bin/python /home/claude/harmonit_cache/atualizar.py
"""
import asyncio
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# O Settings do FPSL le o .env RELATIVO ao diretorio de trabalho, entao e
# preciso entrar na raiz dele antes de importar. Assim a credencial do Harmonit
# fica num lugar so.
FPSL = "/home/claude/fpsl_weso"
os.chdir(FPSL)
sys.path.insert(0, FPSL)
from fpsl_weso.harmonit_client import (  # noqa: E402
    harmonit_get, start_harmonit_client, stop_harmonit_client)

# 🚨 O SCRIPT MORA NO REPOSITORIO, OS DADOS FICAM FORA DELE. Banco de cache e
# dado gerado: pesa MB, e refeito todo dia e nao tem o que fazer no historico
# do git. O caminho e o mesmo que o router usa em `CACHE_HARMONIT`.
DADOS = Path("/home/claude/harmonit_cache")
DB = DADOS / "harmonit.db"
TMP = DADOS / "harmonit.db.novo"

ESQUEMA = """
CREATE TABLE veiculos (
    id          INTEGER PRIMARY KEY,
    placa       TEXT,
    chave_placa TEXT,
    veiculo     TEXT,
    cliente_id  INTEGER,
    cliente     TEXT
);
CREATE INDEX idx_veic_cliente ON veiculos(cliente_id);
CREATE INDEX idx_veic_chave   ON veiculos(chave_placa);

CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
"""

TENTATIVAS = 3

# 🚨 PISO DE SANIDADE. A base tem 9.116 veiculos; uma resposta com 40 e um
# problema do outro lado, nao a base tendo encolhido. Sem este piso, um dia
# ruim do Harmonit trocaria o cache bom por um quase vazio -- e a etapa 3
# passaria a dizer "este cliente nao tem veiculo na base", que e uma mentira
# indistinguivel da verdade.
MINIMO = 8000


def chave_placa(p) -> str:
    """Mesma normalizacao do `weso_cache`, de proposito: as duas bases sao
    cruzadas por placa, e duas normalizacoes diferentes nao cruzam."""
    return re.sub(r"[^A-Z0-9]", "", str(p or "").upper())


async def baixar():
    """⚠️ `/Veiculo/ObterVeiculos` IGNORA TODOS OS FILTROS (medido) e devolve
    uma LISTA na raiz, nao um envelope. Custa ~1,9 s para a base inteira."""
    ultimo = "sem tentativa"
    for n in range(1, TENTATIVAS + 1):
        t0 = time.time()
        try:
            r = await harmonit_get("/Veiculo/ObterVeiculos")
            lista = (r.get("lista") if isinstance(r, dict) else r) or []
            if len(lista) >= MINIMO:
                print(f"  veiculos       {len(lista):6} registros  "
                      f"{time.time() - t0:5.1f}s", flush=True)
                return lista
            ultimo = f"so {len(lista)} registros (piso e {MINIMO})"
        except Exception as exc:
            ultimo = f"{type(exc).__name__}: {str(exc)[:80]}"
        print(f"  veiculos       tentativa {n}/{TENTATIVAS} falhou ({ultimo})",
              flush=True)
        if n < TENTATIVAS:
            await asyncio.sleep(5 * n)
    raise RuntimeError(f"/Veiculo/ObterVeiculos: {ultimo} — abortando para nao "
                       f"substituir o cache bom por um incompleto.")


def gravar(veiculos):
    if TMP.exists():
        TMP.unlink()
    c = sqlite3.connect(TMP)
    c.executescript(ESQUEMA)
    c.executemany(
        "INSERT OR REPLACE INTO veiculos VALUES (?,?,?,?,?,?)",
        [(v.get("id"), v.get("placa"), chave_placa(v.get("placa")),
          v.get("veiculo"), v.get("clienteId"), v.get("cliente"))
         for v in veiculos])
    c.execute("INSERT INTO meta VALUES ('atualizado_em', ?)",
              (datetime.now().isoformat(timespec="seconds"),))
    c.commit()

    # integridade antes de promover — cache corrompido e pior que cache velho
    if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        c.close()
        TMP.unlink()
        raise RuntimeError("integrity_check falhou — cache antigo preservado.")
    n = c.execute("SELECT count(*) FROM veiculos").fetchone()[0]
    c.close()
    if n < MINIMO:
        TMP.unlink()
        raise RuntimeError(f"gravou so {n} — cache antigo preservado.")
    os.replace(TMP, DB)   # atomico: leitor nunca ve meio caminho
    return n


async def main():
    print(f"== cache Harmonit — {datetime.now():%d/%m/%Y %H:%M:%S}")
    await start_harmonit_client()
    try:
        veiculos = await baixar()
    finally:
        await stop_harmonit_client()
    n = gravar(veiculos)
    with sqlite3.connect(DB) as c:
        clientes = c.execute(
            "SELECT count(DISTINCT cliente_id) FROM veiculos").fetchone()[0]
        quando = c.execute(
            "SELECT valor FROM meta WHERE chave='atualizado_em'").fetchone()[0]
    print("  ---")
    print(f"  veiculos {n} · clientes {clientes} · atualizado_em {quando}")


if __name__ == "__main__":
    asyncio.run(main())
