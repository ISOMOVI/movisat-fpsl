import sqlite3
import asyncio
import json
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "fpsl.db"


def _connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS veiculos (
                placa      TEXT PRIMARY KEY,
                veiculo_id INTEGER NOT NULL,
                criado_em  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                harmonit_id INTEGER PRIMARY KEY,
                cnpjcpf     TEXT NOT NULL,
                criado_em   TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rastreadores (
                harmonit_id INTEGER PRIMARY KEY,
                serial      TEXT NOT NULL,
                criado_em   TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rastreadores_serials (
                serial    TEXT PRIMARY KEY,
                weso_id   INTEGER NOT NULL,
                criado_em TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                chave         TEXT PRIMARY KEY,
                valor         TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS painel_usuarios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                login       TEXT UNIQUE NOT NULL,
                senha_hash  TEXT NOT NULL,
                admin       INTEGER NOT NULL DEFAULT 0,
                ativo       INTEGER NOT NULL DEFAULT 1,
                criado_em   TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS painel_vinculos_itens (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_contrato       TEXT UNIQUE NOT NULL,
                harmonit_id         INTEGER,
                harmonit_tipo       TEXT,
                harmonit_descricao  TEXT,
                oculto              INTEGER NOT NULL DEFAULT 0,
                criado_em           TEXT NOT NULL
            )
        """)
        # Histórico de OS varridas do Harmonit (scan sequencial por número) --
        # base do painel "Histórico de OS" e do gatilho de oficina->WESO (Fase 1
        # só leitura). `oficinas_json` guarda o array de eventos embutido na OS.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS os_historico (
                numero_os     INTEGER PRIMARY KEY,
                tipo          INTEGER,
                problema      INTEGER,
                produto_id    INTEGER,
                cliente_id    INTEGER,
                data_previsao TEXT,
                oficinas_json TEXT,
                n_oficinas    INTEGER NOT NULL DEFAULT 0,
                visto_em      TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS harmonit_chamadas (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                momento    TEXT NOT NULL,
                servico    TEXT NOT NULL,
                rota       TEXT NOT NULL,
                metodo     TEXT NOT NULL,
                ms         INTEGER NOT NULL,
                ok         INTEGER NOT NULL,
                http       INTEGER,
                erro       TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hc_momento ON harmonit_chamadas(momento)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hc_servico ON harmonit_chamadas(servico, momento)")
        cols_hc = [r[1] for r in conn.execute("PRAGMA table_info(harmonit_chamadas)").fetchall()]
        if "categoria" not in cols_hc:
            conn.execute("ALTER TABLE harmonit_chamadas ADD COLUMN categoria TEXT")
        # migração: coluna `excluida` (resync marca OS que sumiram do Harmonit)
        _cols = [r[1] for r in conn.execute("PRAGMA table_info(os_historico)").fetchall()]
        if "excluida" not in _cols:
            conn.execute("ALTER TABLE os_historico ADD COLUMN excluida INTEGER NOT NULL DEFAULT 0")

        # migração: perfil de acesso por aba + owner. Antes disso só existia o
        # booleano `admin`, e as 4 abas operacionais ficavam abertas a qualquer
        # usuário logado. `abas` guarda um JSON de ids de aba (ver painel/abas.py).
        _cols = [r[1] for r in conn.execute("PRAGMA table_info(painel_usuarios)").fetchall()]
        if "abas" not in _cols:
            conn.execute("ALTER TABLE painel_usuarios ADD COLUMN abas TEXT NOT NULL DEFAULT '[]'")
        if "owner" not in _cols:
            conn.execute("ALTER TABLE painel_usuarios ADD COLUMN owner INTEGER NOT NULL DEFAULT 0")
            # o usuário original (menor id) vira o owner -- é a conta que já
            # existia antes de haver perfis, e não pode ficar órfã de dono.
            conn.execute(
                "UPDATE painel_usuarios SET owner = 1, admin = 1 "
                "WHERE id = (SELECT MIN(id) FROM painel_usuarios)"
            )


# ── veiculos ──────────────────────────────────────────────────────────────────

async def salvar_veiculo(placa: str, veiculo_id: int) -> None:
    def _run():
        criado_em = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO veiculos (placa, veiculo_id, criado_em) VALUES (?, ?, ?)",
                (placa, veiculo_id, criado_em),
            )
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def buscar_veiculo(placa: str) -> dict | None:
    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT placa, veiculo_id, criado_em FROM veiculos WHERE placa = ?", (placa,)
            ).fetchone()
        return {"placa": row[0], "veiculo_id": row[1], "criado_em": row[2]} if row else None
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def remover_veiculo(placa: str) -> None:
    def _run():
        with _connect() as conn:
            conn.execute("DELETE FROM veiculos WHERE placa = ?", (placa,))
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def remover_veiculo_por_id(veiculo_id: int) -> None:
    def _run():
        with _connect() as conn:
            conn.execute("DELETE FROM veiculos WHERE veiculo_id = ?", (veiculo_id,))
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def listar_veiculos() -> list[dict]:
    def _run():
        with _connect() as conn:
            rows = conn.execute(
                "SELECT placa, veiculo_id, criado_em FROM veiculos ORDER BY criado_em"
            ).fetchall()
        return [{"placa": r[0], "veiculo_id": r[1], "criado_em": r[2]} for r in rows]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── clientes ──────────────────────────────────────────────────────────────────

async def salvar_cliente(harmonit_id: int, cnpjcpf: str) -> None:
    def _run():
        criado_em = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO clientes (harmonit_id, cnpjcpf, criado_em) VALUES (?, ?, ?)",
                (harmonit_id, cnpjcpf, criado_em),
            )
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def buscar_cliente(harmonit_id: int) -> dict | None:
    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT harmonit_id, cnpjcpf, criado_em FROM clientes WHERE harmonit_id = ?",
                (harmonit_id,),
            ).fetchone()
        return {"harmonit_id": row[0], "cnpjcpf": row[1], "criado_em": row[2]} if row else None
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def listar_clientes() -> list[dict]:
    def _run():
        with _connect() as conn:
            rows = conn.execute(
                "SELECT harmonit_id, cnpjcpf, criado_em FROM clientes ORDER BY criado_em"
            ).fetchall()
        return [{"harmonit_id": r[0], "cnpjcpf": r[1], "criado_em": r[2]} for r in rows]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── rastreadores ──────────────────────────────────────────────────────────────

async def salvar_rastreador(harmonit_id: int, serial: str) -> None:
    def _run():
        criado_em = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO rastreadores (harmonit_id, serial, criado_em) VALUES (?, ?, ?)",
                (harmonit_id, serial, criado_em),
            )
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def buscar_rastreador(harmonit_id: int) -> dict | None:
    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT harmonit_id, serial, criado_em FROM rastreadores WHERE harmonit_id = ?",
                (harmonit_id,),
            ).fetchone()
        return {"harmonit_id": row[0], "serial": row[1], "criado_em": row[2]} if row else None
    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── rastreadores_serials (serial → weso_id) ───────────────────────────────────

async def salvar_rastreador_serial(serial: str, weso_id: int) -> None:
    def _run():
        criado_em = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO rastreadores_serials (serial, weso_id, criado_em) VALUES (?, ?, ?)",
                (serial, weso_id, criado_em),
            )
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def buscar_weso_id_por_serial(serial: str) -> int | None:
    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT weso_id FROM rastreadores_serials WHERE serial = ?", (serial,)
            ).fetchone()
        return row[0] if row else None
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def buscar_serial_por_weso_id(weso_id: int) -> str | None:
    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT serial FROM rastreadores_serials WHERE weso_id = ?", (weso_id,)
            ).fetchone()
        return row[0] if row else None
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def listar_rastreadores_serials() -> list[dict]:
    def _run():
        with _connect() as conn:
            rows = conn.execute(
                "SELECT serial, weso_id, criado_em FROM rastreadores_serials ORDER BY criado_em"
            ).fetchall()
        return [{"serial": r[0], "weso_id": r[1], "criado_em": r[2]} for r in rows]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── espelho harmonit_rastreadores (busca por serial, tolerante a espaco) ──────

async def buscar_harmonit_rastreador_por_serial(serial: str) -> dict | None:
    """Busca no espelho local harmonit_rastreadores (populado por import_harmonit_ativos.py).
    Comparacao com TRIM dos dois lados -- achado 2026-07-16: varios registros no
    Harmonit tem espaco/tab grudado no campo equipamento (ex: "007575408 "),
    igualdade exata perde esses casos."""
    def _run():
        with _connect() as conn:
            row = conn.execute(
                """SELECT id, equipamento, modelo_equipamento_id, modelo_equipamento,
                          veiculo_id, veiculo, placa, simcard_id, numero_chip
                   FROM harmonit_rastreadores WHERE TRIM(equipamento) = TRIM(?)""",
                (serial,),
            ).fetchone()
        if not row:
            return None
        return {
            "harmonit_id": row[0], "equipamento": row[1],
            "modelo_equipamento_id": row[2], "modelo_equipamento": row[3],
            "veiculo_id": row[4], "veiculo": row[5], "placa": row[6],
            "simcard_id": row[7], "numero_chip": row[8],
        }
    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── oficinas_processadas (histórico + dedup do sync manual Harmonit -> WESO) ──
# Reformulado 2026-07-16: antes só gravava sucesso (1 linha por evento_id,
# INSERT OR REPLACE). Agora grava toda tentativa (sucesso e falha), pra virar
# histórico auditável na aba "Oficinas" -- dedup continua funcionando (só
# ignora evento com tentativa de SUCESSO já registrada; falha nunca bloqueia
# reclique/retry).

def _init_oficinas_processadas():
    with _connect() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(oficinas_processadas)").fetchall()]
        if cols and "sucesso" not in cols:
            conn.execute("DROP TABLE oficinas_processadas")  # schema antigo, tabela sempre vazia em produção
        conn.execute("""
            CREATE TABLE IF NOT EXISTS oficinas_processadas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                evento_id       INTEGER NOT NULL,
                numero_os       INTEGER NOT NULL,
                status          INTEGER NOT NULL,
                sucesso         INTEGER NOT NULL,
                verificado_weso INTEGER NOT NULL DEFAULT 0,
                resultado       TEXT NOT NULL,
                processado_em   TEXT NOT NULL
            )
        """)
        # 2026-07-22: placa e serial existiam só dentro do texto de `resultado`,
        # o que impedia usá-los como coluna do histórico. ALTER (não DROP) porque
        # a partir de agora a tabela guarda dado de produção que não pode sumir.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(oficinas_processadas)").fetchall()]
        for coluna, tipo in (("placa", "TEXT"), ("equipamento_id", "TEXT"),
                             ("veiculo_nome", "TEXT"), ("origem", "TEXT")):
            if coluna not in cols:
                conn.execute(f"ALTER TABLE oficinas_processadas ADD COLUMN {coluna} {tipo}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oficinas_evento ON oficinas_processadas(evento_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oficinas_numero_os ON oficinas_processadas(numero_os)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oficinas_placa ON oficinas_processadas(placa)")


async def oficina_ja_processada(evento_id: int) -> dict | None:
    def _run():
        _init_oficinas_processadas()
        with _connect() as conn:
            row = conn.execute(
                "SELECT evento_id, numero_os, status, resultado, verificado_weso, processado_em "
                "FROM oficinas_processadas WHERE evento_id = ? AND sucesso = 1 "
                "ORDER BY processado_em DESC LIMIT 1",
                (evento_id,),
            ).fetchone()
        if not row:
            return None
        return {"evento_id": row[0], "numero_os": row[1], "status": row[2], "resultado": row[3],
                "verificado_weso": bool(row[4]), "processado_em": row[5]}
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def marcar_oficina_processada(
    evento_id: int, numero_os: int, status: int, resultado: str, sucesso: bool, verificado_weso: bool = False,
    placa: str | None = None, equipamento_id: str | None = None, veiculo_nome: str | None = None,
    origem: str = "painel",
) -> int:
    """Grava uma tentativa (sucesso ou falha) e devolve o id da linha -- o id é o
    que o botão Resync usa pra reprocessar exatamente aquela tentativa."""
    def _run():
        _init_oficinas_processadas()
        processado_em = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO oficinas_processadas (evento_id, numero_os, status, sucesso, verificado_weso, "
                "resultado, processado_em, placa, equipamento_id, veiculo_nome, origem) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (evento_id, numero_os, status, int(sucesso), int(verificado_weso), resultado, processado_em,
                 placa, equipamento_id, veiculo_nome, origem),
            )
            return cur.lastrowid
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def buscar_oficina_historico(registro_id: int) -> dict | None:
    """Uma linha do histórico pelo id -- usado pelo Resync."""
    def _run():
        _init_oficinas_processadas()
        with _connect() as conn:
            row = conn.execute(
                "SELECT id, evento_id, numero_os, status, sucesso, verificado_weso, resultado, "
                "processado_em, placa, equipamento_id, veiculo_nome, origem "
                "FROM oficinas_processadas WHERE id = ?", (registro_id,),
            ).fetchone()
        if not row:
            return None
        return {"id": row[0], "evento_id": row[1], "numero_os": row[2], "status": row[3],
                "sucesso": bool(row[4]), "verificado_weso": bool(row[5]), "resultado": row[6],
                "processado_em": row[7], "placa": row[8], "equipamento_id": row[9],
                "veiculo_nome": row[10], "origem": row[11]}
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def listar_oficinas_processadas(numero_os: int) -> list[dict]:
    def _run():
        _init_oficinas_processadas()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT evento_id, numero_os, status, sucesso, verificado_weso, resultado, processado_em "
                "FROM oficinas_processadas WHERE numero_os = ? ORDER BY processado_em DESC",
                (numero_os,),
            ).fetchall()
        return [{"evento_id": r[0], "numero_os": r[1], "status": r[2], "sucesso": bool(r[3]),
                 "verificado_weso": bool(r[4]), "resultado": r[5], "processado_em": r[6]} for r in rows]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def listar_historico_oficinas(limit: int = 200) -> list[dict]:
    """Histórico geral (todas as OS), mais recente primeiro -- fonte da aba de auditoria."""
    def _run():
        _init_oficinas_processadas()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, evento_id, numero_os, status, sucesso, verificado_weso, resultado, processado_em, "
                "placa, equipamento_id, veiculo_nome, origem "
                "FROM oficinas_processadas ORDER BY processado_em DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"id": r[0], "evento_id": r[1], "numero_os": r[2], "status": r[3], "sucesso": bool(r[4]),
                 "verificado_weso": bool(r[5]), "resultado": r[6], "processado_em": r[7],
                 "placa": r[8], "equipamento_id": r[9], "veiculo_nome": r[10], "origem": r[11]} for r in rows]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── config (chave-valor) ──────────────────────────────────────────────────────

async def get_config(chave: str, default: str = "") -> str:
    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT valor FROM config WHERE chave = ?", (chave,)
            ).fetchone()
        return row[0] if row else default
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def set_config(chave: str, valor: str) -> None:
    def _run():
        atualizado_em = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO config (chave, valor, atualizado_em) VALUES (?, ?, ?)",
                (chave, valor, atualizado_em),
            )
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def listar_config() -> list[dict]:
    def _run():
        with _connect() as conn:
            rows = conn.execute(
                "SELECT chave, valor, atualizado_em FROM config ORDER BY chave"
            ).fetchall()
        return [{"chave": r[0], "valor": r[1], "atualizado_em": r[2]} for r in rows]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── os_historico (scan sequencial de OS) ─────────────────────────────────────

async def salvar_os_historico(numero_os: int, tipo, problema, produto_id, cliente_id,
                              data_previsao, oficinas: list) -> bool:
    """Grava/atualiza uma OS no histórico. Retorna True se era NOVA (não existia)."""
    def _run():
        agora = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            existe = conn.execute(
                "SELECT 1 FROM os_historico WHERE numero_os = ?", (numero_os,)
            ).fetchone() is not None
            visto = agora if not existe else conn.execute(
                "SELECT visto_em FROM os_historico WHERE numero_os = ?", (numero_os,)
            ).fetchone()[0]
            conn.execute(
                "INSERT OR REPLACE INTO os_historico "
                "(numero_os, tipo, problema, produto_id, cliente_id, data_previsao, "
                " oficinas_json, n_oficinas, visto_em, atualizado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (numero_os, tipo, problema, produto_id, cliente_id, data_previsao,
                 json.dumps(oficinas or [], ensure_ascii=False), len(oficinas or []), visto, agora),
            )
        return not existe
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def listar_os_historico(limit: int = 300, apenas_com_oficina: bool = False) -> list[dict]:
    def _run():
        with _connect() as conn:
            sql = ("SELECT numero_os, tipo, problema, produto_id, cliente_id, data_previsao, "
                   "oficinas_json, n_oficinas, visto_em, atualizado_em, excluida FROM os_historico ")
            if apenas_com_oficina:
                sql += "WHERE n_oficinas > 0 "
            sql += "ORDER BY numero_os DESC LIMIT ?"
            rows = conn.execute(sql, (limit,)).fetchall()
        return [{"numero_os": r[0], "tipo": r[1], "problema": r[2], "produto_id": r[3],
                 "cliente_id": r[4], "data_previsao": r[5], "oficinas": json.loads(r[6] or "[]"),
                 "n_oficinas": r[7], "visto_em": r[8], "atualizado_em": r[9], "excluida": bool(r[10])} for r in rows]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def contar_os_historico() -> int:
    def _run():
        with _connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM os_historico").fetchone()[0]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def marcar_os_excluida(numero_os: int) -> None:
    def _run():
        with _connect() as conn:
            conn.execute(
                "UPDATE os_historico SET excluida = 1, atualizado_em = ? WHERE numero_os = ?",
                (datetime.now(timezone.utc).isoformat(), numero_os),
            )
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def os_para_resync(janela: int = 400) -> list[int]:
    """Números das últimas `janela` OS (não-excluídas) por número -- o resync
    re-lê essa janela recente pra pegar oficina adicionada depois e detectar
    exclusão. Janela por número (~2 dias úteis), simples e robusta."""
    def _run():
        with _connect() as conn:
            rows = conn.execute(
                "SELECT numero_os FROM os_historico WHERE excluida = 0 "
                "ORDER BY numero_os DESC LIMIT ?", (janela,),
            ).fetchall()
        return [r[0] for r in rows]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── painel_usuarios ─────────────────────────────────────────────────────────

def _abas_de(bruto: str | None) -> list[str]:
    """Lê a coluna `abas`. Linha antiga/corrompida vira lista vazia (fecha o acesso)."""
    if not bruto:
        return []
    try:
        valor = json.loads(bruto)
    except (ValueError, TypeError):
        return []
    return [str(i) for i in valor] if isinstance(valor, list) else []


async def criar_usuario_painel(
    login: str, senha_hash: str, admin: bool = False, abas: list[str] | None = None, owner: bool = False
) -> None:
    def _run():
        with _connect() as conn:
            conn.execute(
                "INSERT INTO painel_usuarios (login, senha_hash, admin, ativo, criado_em, abas, owner) "
                "VALUES (?, ?, ?, 1, ?, ?, ?)",
                (
                    login,
                    senha_hash,
                    int(admin),
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(abas or []),
                    int(owner),
                ),
            )
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def buscar_usuario_painel(login: str) -> dict | None:
    """Acha o usuário do painel IGNORANDO MAIÚSCULA e espaço nas pontas.

    🚨 CORRIGIDO EM 07/08, depois de o acesso ser recusado com a senha certa.
    A busca era `WHERE login = ?`, exata: digitar `Admin` devolvia 401 SEM NEM
    CHEGAR NO BCRYPT, e a mensagem genérica ("login ou senha inválidos") não
    dava como desconfiar. Pior: o `ratelimit.chave_de` já usava `casefold`,
    então o log registrava `admin` mesmo quando o digitado era outro -- e a
    evidência apontava para o lado errado.

    Login é identificador de pessoa, não segredo: quem protege é a senha.
    Exigir a caixa exata só rende chamado. É a mesma correção que o MoviZap
    recebeu em 05/08 e que nunca foi propagada para cá.
    """
    login = (login or "").strip()

    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT id, login, senha_hash, admin, ativo, abas, owner "
                "FROM painel_usuarios WHERE lower(login) = lower(?)",
                (login,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "login": row[1], "senha_hash": row[2], "admin": bool(row[3]),
            "ativo": bool(row[4]), "abas": _abas_de(row[5]), "owner": bool(row[6]),
        }
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def buscar_usuario_painel_por_id(usuario_id: int) -> dict | None:
    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT id, login, admin, ativo, abas, owner FROM painel_usuarios WHERE id = ?",
                (usuario_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "login": row[1], "admin": bool(row[2]),
            "ativo": bool(row[3]), "abas": _abas_de(row[4]), "owner": bool(row[5]),
        }
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def listar_usuarios_painel() -> list[dict]:
    def _run():
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, login, admin, ativo, criado_em, abas, owner FROM painel_usuarios "
                "ORDER BY owner DESC, login"
            ).fetchall()
        return [
            {
                "id": r[0], "login": r[1], "admin": bool(r[2]), "ativo": bool(r[3]),
                "criado_em": r[4], "abas": _abas_de(r[5]), "owner": bool(r[6]),
            }
            for r in rows
        ]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def contar_usuarios_painel() -> int:
    def _run():
        with _connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM painel_usuarios").fetchone()[0]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def atualizar_usuario_painel(
    usuario_id: int, *, ativo: bool | None = None, admin: bool | None = None,
    senha_hash: str | None = None, abas: list[str] | None = None,
) -> None:
    def _run():
        campos, valores = [], []
        if ativo is not None:
            campos.append("ativo = ?"); valores.append(int(ativo))
        if admin is not None:
            campos.append("admin = ?"); valores.append(int(admin))
        if senha_hash is not None:
            campos.append("senha_hash = ?"); valores.append(senha_hash)
        if abas is not None:
            campos.append("abas = ?"); valores.append(json.dumps(abas))
        if not campos:
            return
        valores.append(usuario_id)
        with _connect() as conn:
            # o owner nunca é alterado por esta rota -- nem por ele mesmo, pra não
            # existir caminho que deixe o painel sem dono.
            conn.execute(
                f"UPDATE painel_usuarios SET {', '.join(campos)} WHERE id = ? AND owner = 0", valores
            )
    await asyncio.get_running_loop().run_in_executor(None, _run)


# ── painel_vinculos_itens ────────────────────────────────────────────────────

def _normalizar_nome_item(nome: str) -> str:
    # Sem stripping de acento antes: "Instalação" e "INSTALACAO" (sem cedilha
    # nem til, comum em texto extraído de PDF com fonte estranha) caíam em
    # 2 vínculos diferentes -- achado auditando os 7 documentos de exemplo.
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.strip().upper().split())


async def buscar_vinculo_item(nome_contrato: str) -> dict | None:
    nome_norm = _normalizar_nome_item(nome_contrato)
    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT id, nome_contrato, harmonit_id, harmonit_tipo, harmonit_descricao, oculto "
                "FROM painel_vinculos_itens WHERE nome_contrato = ?",
                (nome_norm,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "nome_contrato": row[1], "harmonit_id": row[2],
            "harmonit_tipo": row[3], "harmonit_descricao": row[4], "oculto": bool(row[5]),
        }
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def salvar_vinculo_item(nome_contrato: str, harmonit_id: int | None, harmonit_tipo: str | None,
                                harmonit_descricao: str | None, oculto: bool = False) -> None:
    nome_norm = _normalizar_nome_item(nome_contrato)
    def _run():
        with _connect() as conn:
            conn.execute(
                "INSERT INTO painel_vinculos_itens "
                "(nome_contrato, harmonit_id, harmonit_tipo, harmonit_descricao, oculto, criado_em) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(nome_contrato) DO UPDATE SET "
                "harmonit_id=excluded.harmonit_id, harmonit_tipo=excluded.harmonit_tipo, "
                "harmonit_descricao=excluded.harmonit_descricao, oculto=excluded.oculto",
                (nome_norm, harmonit_id, harmonit_tipo, harmonit_descricao, int(oculto),
                 datetime.now(timezone.utc).isoformat()),
            )
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def listar_vinculos_itens() -> list[dict]:
    def _run():
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, nome_contrato, harmonit_id, harmonit_tipo, harmonit_descricao, oculto, criado_em "
                "FROM painel_vinculos_itens ORDER BY nome_contrato"
            ).fetchall()
        return [
            {"id": r[0], "nome_contrato": r[1], "harmonit_id": r[2], "harmonit_tipo": r[3],
             "harmonit_descricao": r[4], "oculto": bool(r[5]), "criado_em": r[6]}
            for r in rows
        ]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── harmonit_chamadas (auditoria dos servicos ligados ao Harmonit) ───────────
# Grava TODA chamada. O custo e 1 insert; o valor e conseguir responder "o
# Harmonit esta lento hoje?" com numero em vez de impressao. Retencao de 30
# dias -- ver RETENCAO_CHAMADAS_DIAS.
RETENCAO_CHAMADAS_DIAS = 30


def _servico_de(rota: str) -> str:
    """Agrupa a rota no servico que o painel exibe como sub-aba.

    /OrdemServico/SalvarOrdemServico -> OrdemServico
    /ObterClientes                   -> Clientes
    """
    partes = [p for p in str(rota or "").split("/") if p]
    if not partes:
        return "(desconhecido)"
    if len(partes) > 1:
        return partes[0]
    nome = partes[0]
    for prefixo in ("Obter", "Salvar", "Cadastrar", "Atualizar", "Remover"):
        if nome.startswith(prefixo):
            return nome[len(prefixo):] or nome
    return nome


# "Ordem de Servico nao encontrada" NAO e falha da API -- e resposta legitima.
# A varredura sonda numeros de OS sequencialmente e a numeracao do Harmonit e
# global, com buracos; a maioria das sondagens volta vazia por natureza.
# Contar isso como falha faria o painel mostrar 100% de erro num sistema
# saudavel, que e exatamente o ruido que o usuario pediu para evitar (29/07).
_MARCAS_VAZIO = (
    "nao encontrad", "não encontrad", "not found",
    "nenhum registro", "sem resultado",
)


def _eh_resposta_vazia(erro: str | None) -> bool:
    e = (erro or "").lower()
    return any(m in e for m in _MARCAS_VAZIO)


async def registrar_chamada_harmonit(rota: str, metodo: str, ms: int,
                                     ok: bool, http: int | None = None,
                                     erro: str | None = None) -> None:
    """Nunca levanta: auditoria que derruba a operacao auditada e pior que
    auditoria nenhuma."""
    try:
        criado_em = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            categoria = "ok" if ok else ("vazio" if _eh_resposta_vazia(erro) else "erro")
            conn.execute(
                "INSERT INTO harmonit_chamadas "
                "(momento, servico, rota, metodo, ms, ok, http, erro, categoria) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (criado_em, _servico_de(rota), rota, metodo.upper(), int(ms),
                 1 if ok else 0, http, (erro or "")[:300] or None, categoria),
            )
            conn.commit()
    except Exception:
        pass


async def limpar_chamadas_antigas() -> int:
    corte = (datetime.now(timezone.utc) - timedelta(days=RETENCAO_CHAMADAS_DIAS)).isoformat()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM harmonit_chamadas WHERE momento < ?", (corte,))
        conn.commit()
        return cur.rowcount


# ── De-para modelo da WESO -> produto do Harmonit ────────────────────────────
# 🚨 SINCRONO DE PROPOSITO. E lido de dentro de `_montar_operacoes`, que e
# sincrona. Envolver em executor so para manter o padrao async obrigaria a
# tornar toda a montagem assincrona sem ganho nenhum -- sqlite3 e sincrono de
# qualquer jeito e a consulta e por indice.

def produto_do_modelo(modelo: str) -> dict | None:
    """Produto do Harmonit para um modelo de rastreador da WESO, ou None.

    None e "nao ha de-para", e NUNCA bloqueia: sem produto a OS sai com o
    equipamento apenas na descricao. Modelos sem produto no catalogo do
    Harmonit (TK-100, ST500, NT2x, Concox...) sao exatamente esse caso.
    """
    alvo = str(modelo or "").strip()
    if not alvo:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT harmonit_produto_id, harmonit_descricao, valor_patrimonial "
            "FROM painel_modelos_produto WHERE modelo_weso = ? COLLATE NOCASE",
            (alvo,)).fetchone()
    if not row or not row[0]:
        return None
    return {"harmonit_id": row[0], "descricao": row[1], "valor": row[2] or 0.0}
