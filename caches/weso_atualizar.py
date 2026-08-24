"""Cache local da base WESO — construcao. Roda 1x por dia via cron.

Estrategia: monta um banco NOVO num arquivo temporario e so troca pelo bom no
fim, atomicamente. Se a WESO cair no meio, o cache antigo continua servindo —
cache pela metade e pior que cache velho, porque parece completo.

Reusa o cliente do FPSL (fpsl_weso.client) para nao duplicar a chave da API em
lugar nenhum. Por isso roda com o venv do FPSL.

Uso:
    /home/claude/fpsl_weso/venv/bin/python /home/claude/weso_cache/atualizar.py
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
# preciso entrar na raiz dele antes de importar. Assim a chave da WESO fica
# num lugar so — nao ha credencial duplicada aqui.
FPSL = "/home/claude/fpsl_weso"
os.chdir(FPSL)
sys.path.insert(0, FPSL)
import httpx  # noqa: E402
from fpsl_weso.config import settings  # noqa: E402

# 🚨 O SCRIPT MORA NO REPOSITORIO, OS DADOS FICAM FORA DELE (24/08). Ate aqui
# ele usava o proprio diretorio (`Path(__file__).parent`), o que so funcionava
# porque codigo e banco moravam juntos em /home/claude/weso_cache -- e nada
# disso estava em git.
#
# O banco NAO se muda de lugar: `equipamentos.py` e `placas_router.py` apontam
# para `/home/claude/weso_cache` numa constante absoluta, e o `cache.py` que
# eles importam vive la. Mover o dado custaria mexer em codigo de producao para
# ganhar nada.
DADOS = Path("/home/claude/weso_cache")
DB = DADOS / "weso.db"
TMP = DADOS / "weso.db.novo"

ESQUEMA = """
CREATE TABLE veiculos (
    id            INTEGER PRIMARY KEY,
    placa         TEXT,
    chave_placa   TEXT,
    descricao     TEXT,
    status        INTEGER,
    rastreador_id INTEGER,
    cliente_id    INTEGER,
    chassi        TEXT,
    data_cadastro TEXT
);
CREATE INDEX idx_veic_chave  ON veiculos(chave_placa);
CREATE INDEX idx_veic_rastr  ON veiculos(rastreador_id);
CREATE INDEX idx_veic_cli    ON veiculos(cliente_id);

CREATE TABLE rastreadores (
    id            INTEGER PRIMARY KEY,
    numero_serie  TEXT,
    modelo        TEXT,
    situacao      TEXT,
    tipo          TEXT,
    firmware      TEXT,
    simcard_id    INTEGER,
    data_cadastro TEXT
);
CREATE INDEX idx_rastr_serie ON rastreadores(numero_serie);

CREATE TABLE simcards (
    id            INTEGER PRIMARY KEY,
    iccid         TEXT,
    numero        TEXT,
    operadora     TEXT,
    apn           TEXT,
    situacao      TEXT,
    disponivel    INTEGER,
    data_cadastro TEXT
);
CREATE INDEX idx_sim_iccid ON simcards(iccid);

CREATE TABLE clientes (
    id            INTEGER PRIMARY KEY,
    cnpjcpf       TEXT,
    razao_social  TEXT,
    nome_fantasia TEXT,
    situacao      TEXT
);
CREATE INDEX idx_cli_doc ON clientes(cnpjcpf);

CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
"""


def chave_placa(p) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(p or "").upper())


def _sub(d, *caminho):
    """Campo aninhado que pode vir None em qualquer nivel."""
    for c in caminho:
        if not isinstance(d, dict):
            return None
        d = d.get(c)
    return d


# Timeout PROPRIO, generoso. Reusar o client do FPSL herdava o corte de 30s,
# desenhado para rota web -- e o /Veiculos/Consultar sozinho ja variou de 21s a
# mais de 30s em 29/07. Job de fundo pode esperar; rota web nao. Foi exatamente
# por isso que a primeira tentativa de build falhou.
TIMEOUT = 240
TENTATIVAS = 3


async def _puxar(client, rota, params, chave):
    """Uma fonte, com tentativa repetida. A WESO oscila muito: falhar na
    primeira nao significa que esta fora."""
    ultimo = None
    for n in range(1, TENTATIVAS + 1):
        t0 = time.time()
        try:
            r = await client.get(rota, params={"key": settings.weso_api_key, **params})
            r.raise_for_status()
            corpo = r.json()
            dados = corpo.get("Data", corpo)
            lista = dados.get(chave) or []
            if lista:
                print(f"  {chave:14} {len(lista):6} registros  {time.time()-t0:5.1f}s", flush=True)
                return lista
            ultimo = "resposta sem registros"
        except Exception as exc:
            ultimo = f"{type(exc).__name__}: {str(exc)[:80]}"
        print(f"  {chave:14} tentativa {n}/{TENTATIVAS} falhou ({ultimo})", flush=True)
        if n < TENTATIVAS:
            await asyncio.sleep(5 * n)
    raise RuntimeError(f"{rota}: {ultimo} — abortando para nao substituir o "
                       f"cache bom por um incompleto.")


async def baixar():
    fontes = {}
    async with httpx.AsyncClient(base_url=settings.weso_base_url, timeout=TIMEOUT) as c:
        for nome, rota, params, chave in (
            ("veiculos",     "/Veiculos/Consultar",     {},                  "veiculos"),
            ("rastreadores", "/Rastreadores/Consultar", {"numeroSerie": ""}, "rastreadores"),
            ("simcards",     "/SimCard/Consultar",      {},                  "simcards"),
            ("clientes",     "/Clientes/Consultar",     {},                  "clientes"),
        ):
            fontes[nome] = await _puxar(c, rota, params, chave)
    return fontes


def gravar(fontes):
    if TMP.exists():
        TMP.unlink()
    c = sqlite3.connect(TMP)
    c.executescript(ESQUEMA)

    c.executemany(
        "INSERT OR REPLACE INTO veiculos VALUES (?,?,?,?,?,?,?,?,?)",
        [(v.get("id"), v.get("placa"), chave_placa(v.get("placa")),
          v.get("descricao"), v.get("status_veiculo"), v.get("rastreador_id"),
          _sub(v, "cliente", "id"), _sub(v, "complemento", "chassi"),
          v.get("data_cadastro")) for v in fontes["veiculos"]])

    c.executemany(
        "INSERT OR REPLACE INTO rastreadores VALUES (?,?,?,?,?,?,?,?)",
        [(r.get("id"), (r.get("numeroSerie") or "").strip(), r.get("modelo"),
          r.get("situacao"), r.get("tipo"), r.get("firmware"),
          _sub(r, "simcard", "id"), r.get("data_cadastro"))
         for r in fontes["rastreadores"]])

    c.executemany(
        "INSERT OR REPLACE INTO simcards VALUES (?,?,?,?,?,?,?,?)",
        [(s.get("id"), s.get("iccId"), str(s.get("numero") or ""),
          _sub(s, "operadora", "nome") or s.get("operadora"),
          _sub(s, "apn", "nome") or s.get("apn"),
          s.get("situacao"), 1 if s.get("disponivel") else 0,
          s.get("data_cadastro")) for s in fontes["simcards"]])

    c.executemany(
        "INSERT OR REPLACE INTO clientes VALUES (?,?,?,?,?)",
        [(cl.get("id"), cl.get("cnpjcpf"), cl.get("razaoSocial"),
          cl.get("nomeFantasia"), cl.get("situacao")) for cl in fontes["clientes"]])

    c.execute("INSERT INTO meta VALUES ('atualizado_em', ?)",
              (datetime.now().isoformat(timespec="seconds"),))
    c.commit()

    # integridade antes de promover — cache corrompido e pior que cache velho
    if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        c.close(); TMP.unlink()
        raise RuntimeError("integrity_check falhou — cache antigo preservado.")
    c.close()
    os.replace(TMP, DB)   # atomico: leitor nunca ve meio caminho


async def main():
    print(f"== cache WESO — {datetime.now():%d/%m/%Y %H:%M:%S}")
    fontes = await baixar()
    gravar(fontes)

    # `cache.py` continua em /home/claude/weso_cache: e ele que o painel
    # importa em producao, pela constante CACHE_DIR.
    sys.path.insert(0, str(DADOS))
    import cache
    print("  ---")
    for k, v in cache.resumo().items():
        print(f"  {k:15} {v}")


asyncio.run(main())
