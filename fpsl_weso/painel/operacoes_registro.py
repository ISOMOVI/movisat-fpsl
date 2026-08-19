"""Registro da aba OPERAÇÕES — o que aconteceu em cada lote, passo a passo.

🚨 TABELA PRÓPRIA, NÃO O `cadastro_placas_log`. O critério da spec 28 é claro:
o banco se reusa, as tabelas são da aba. Quando o Cadastro de Placas sair (F7),
a tabela dele sai junto ou fica como histórico morto -- de qualquer jeito, a
aba nova não pode depender dela.

⚠️ E o formato é OUTRO. Aquela tabela nasceu para uma tela de dois passos; esta
registra QUATRO etapas, e a de cliente não existia lá.

🚨 POR QUE ISTO EXISTE, E POR QUE VEIO ANTES DA ESCRITA. A aba grava em DOIS
sistemas externos e o resultado é invisível: OS errada alguém abre e vê;
veículo criado errado some no meio de 9.114 no Harmonit e 1.955 na WESO. Sem
registro, auditar exigiria comparar as bases inteiras.

🚨 E É ELE QUE PERMITE RETOMAR. Um termo de 11 placas leva mais de um minuto só
na etapa 3 (~4s por placa), e a WESO oscila entre 6s e timeout de 30s. Se cair
no meio, o operador NÃO PODE recomeçar do PDF -- metade já nasceu. O `lote`
amarra a rodada e diz de onde continuar.

UMA LINHA POR (PLACA, SISTEMA), não por placa. A mesma placa produz DUAS
tentativas -- Harmonit e WESO -- e elas podem terminar diferente: criada no
primeiro e recusada no segundo é o caso que mais importa registrar, porque é o
que deixa os dois sistemas fora de sincronia.
"""
import asyncio
import datetime as _dt
import sqlite3
import uuid

from .. import storage


def _agora() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def novo_lote() -> str:
    """Identificador da rodada. Curto o bastante para caber num log e único o
    bastante para não colidir entre dois operadores no mesmo minuto."""
    return uuid.uuid4().hex[:12]


def _criar():
    with storage._connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operacoes_lote (
                lote                TEXT PRIMARY KEY,
                criado_em           TEXT NOT NULL,
                usuario             TEXT,
                perfil              TEXT,
                termo               TEXT,
                documento           TEXT,
                cliente_harmonit_id INTEGER,
                cliente_weso_id     INTEGER,
                etapa               INTEGER NOT NULL DEFAULT 1,
                encerrado_em        TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operacoes_passo (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                lote           TEXT NOT NULL,
                criado_em      TEXT NOT NULL,
                etapa          INTEGER NOT NULL,
                sistema        TEXT NOT NULL,
                acao           TEXT NOT NULL,
                placa_digitada TEXT,
                placa_gravada  TEXT,
                descricao      TEXT,
                recipiente     INTEGER NOT NULL DEFAULT 0,
                id_externo     INTEGER,
                erro           TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_opp_lote ON operacoes_passo(lote)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_opp_placa ON operacoes_passo(placa_gravada)")


# Valores aceitos em `acao`. 🚨 CHECK NÃO ENTRA NA TABELA de propósito:
# registro que se recusa a gravar perde justamente o caso que interessa, o
# inesperado. A conferência é aqui, e valor desconhecido vira `desconhecido`
# com o original preservado no erro.
#
# ⚠️ NÃO EXISTE `simulado`. Ele era do interruptor do Cadastro de Placas, que
# saiu em 19/08: a aba é rotina nativa, subir grava.
ACOES = ("criado", "ja_existia", "confere_ok", "confere_falta", "falhou", "ignorado")
SISTEMAS = ("harmonit", "weso")


async def abrir_lote(usuario: str | None, perfil: str, termo: str | None,
                     documento: str | None) -> str:
    def _run():
        _criar()
        lote = novo_lote()
        with storage._connect() as conn:
            conn.execute(
                "INSERT INTO operacoes_lote (lote, criado_em, usuario, perfil, "
                "termo, documento) VALUES (?,?,?,?,?,?)",
                (lote, _agora(), usuario, perfil, termo, documento))
        return lote
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def guardar_cliente(lote: str, harmonit_id: int | None,
                          weso_id: int | None) -> None:
    def _run():
        _criar()
        with storage._connect() as conn:
            conn.execute(
                "UPDATE operacoes_lote SET cliente_harmonit_id = ?, "
                "cliente_weso_id = ?, etapa = MAX(etapa, 2) WHERE lote = ?",
                (harmonit_id, weso_id, lote))
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def registrar(lote: str, etapa: int, sistema: str, acao: str, *,
                    placa_digitada: str | None = None,
                    placa_gravada: str | None = None,
                    descricao: str | None = None, recipiente: bool = False,
                    id_externo: int | None = None,
                    erro: str | None = None) -> int:
    """Grava UM passo. Devolve o id da linha. NUNCA levanta por valor estranho."""
    if acao not in ACOES:
        erro = f"acao desconhecida {acao!r}" + (f" | {erro}" if erro else "")
        acao = "desconhecido"
    if sistema not in SISTEMAS:
        erro = f"sistema desconhecido {sistema!r}" + (f" | {erro}" if erro else "")

    def _run():
        _criar()
        with storage._connect() as conn:
            cur = conn.execute(
                "INSERT INTO operacoes_passo (lote, criado_em, etapa, sistema, "
                "acao, placa_digitada, placa_gravada, descricao, recipiente, "
                "id_externo, erro) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (lote, _agora(), etapa, sistema, acao, placa_digitada,
                 placa_gravada, descricao, int(bool(recipiente)), id_externo, erro))
            return cur.lastrowid
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def passos(lote: str) -> list[dict]:
    def _run():
        _criar()
        with storage._connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM operacoes_passo WHERE lote = ? ORDER BY id", (lote,))]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def ler_lote(lote: str) -> dict | None:
    def _run():
        _criar()
        with storage._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT * FROM operacoes_lote WHERE lote = ?",
                             (lote,)).fetchone()
            return dict(r) if r else None
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def ja_resolvidas(lote: str) -> dict[str, set]:
    """{placa_gravada: {sistemas onde já terminou}} -- a base do retomar.

    🚨 SÓ CONTA O QUE TERMINOU BEM. `falhou` não entra: a graça de retomar é
    tentar de novo o que falhou, não pulá-lo.
    """
    saida: dict[str, set] = {}
    for p in await passos(lote):
        if p["acao"] in ("criado", "ja_existia", "confere_ok") and p["placa_gravada"]:
            saida.setdefault(p["placa_gravada"], set()).add(p["sistema"])
    return saida


async def resumo(lote: str) -> dict:
    linhas = await passos(lote)
    por_acao: dict[str, int] = {}
    for p in linhas:
        por_acao[p["acao"]] = por_acao.get(p["acao"], 0) + 1
    return {"passos": len(linhas), "por_acao": por_acao}
