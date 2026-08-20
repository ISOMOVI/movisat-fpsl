"""O vínculo OS ↔ recipiente da aba OPERAÇÕES — o que a rotina (F5) consome.

🚨 POR QUE ISTO EXISTE, E POR QUE VEM ANTES DA ROTINA. A spec lista três riscos
da rotina, e este é o primeiro: **ela precisa de um vínculo OS ↔ recipiente que
hoje não existe.** A alternativa seria deduzir depois, pela descrição da OS —
frágil e falha em silêncio, que é a família de defeito que mais custou caro
neste projeto.

Grava-se na GERAÇÃO qual OS ficou esperando o quê. Quem gerou sabe; quem varre
seis horas depois não.

⚠️ TABELA PRÓPRIA DA ABA. Não reaproveita `os_historico`, que é do varredor e
da tela de Histórico de OS: aquela tabela responde "o que existe no Harmonit",
esta responde "o que esta aba está devendo". Misturar as duas obrigaria toda
consulta de histórico a lembrar de filtrar — e filtro em vários lugares é
defeito com data marcada.

Os quatro casos da rotina, na ordem da spec:

    recipiente ..... série apareceu na WESO -> escreve na OS -> devolve ao
                     estoque -> remove o recipiente
    rescisao ....... oficina "desinstalado" -> devolve ao estoque
    ressarcimento .. oficina na híbrida -> devolve ao estoque
    substituicao ... solta do veículo antigo -> confere Estoque relendo ->
                     vincula na placa_entrada

🚨 DEVOLVER AO ESTOQUE É SEMPRE O PRIMEIRO PASSO. Excluir o veículo NÃO libera
o rastreador — são duas chamadas, e `situacao` é objeto, não texto. Medido em
14/08 na Velasco: apagado o veículo, o rastreador continuou `Instalado` sem
veículo nenhum.
"""
import asyncio
import json
import sqlite3
from datetime import datetime, timezone

from .. import storage

# Os quatro casos. Nome fixo: o `estado` e o `caso` são lidos por consulta, e
# string solta num `if` espalhado é como uma tabela ganha valor que ninguém
# sabe de onde veio.
CASOS = ("recipiente", "rescisao", "ressarcimento", "substituicao")
ESTADOS = ("esperando", "concluido", "desistiu", "falhou")

# 🚨 TETO DE TENTATIVAS — É DECISÃO SUA, E ESTE NÚMERO É PROVISÓRIO.
#
# A spec pede o teto porque um recipiente cuja série nunca aparece seria
# consultado a cada 6 h para sempre. 28 rodadas a cada 6 h dão 7 dias.
#
# ⚠️ Não escolhi 28 por saber que 7 dias é o prazo certo: escolhi para o laço
# não ser infinito. Teto, limite e filtro são seus. Quando você disser o número,
# ele muda aqui e o teste que o prende muda junto.
TETO_TENTATIVAS = 28


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _criar():
    with storage._connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operacoes_espera (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                lote                TEXT,
                perfil              TEXT NOT NULL,
                caso                TEXT NOT NULL,
                os_id               INTEGER,
                numero_os           INTEGER,
                placa               TEXT NOT NULL,
                placa_entrada       TEXT,
                recipiente_placa    TEXT,
                veiculo_id          INTEGER,
                rastreador_id       INTEGER,
                estado              TEXT NOT NULL DEFAULT 'esperando',
                tentativas          INTEGER NOT NULL DEFAULT 0,
                ultimo_erro         TEXT,
                passos_json         TEXT,
                criado_em           TEXT NOT NULL,
                atualizado_em       TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_espera_estado "
                     "ON operacoes_espera(estado, caso)")
        # ⚠️ SEM UNIQUE em `os_id`. A substituição gera DUAS OS para a mesma
        # placa (retirada e instalação) e as duas podem ter pendência; e uma OS
        # regerada depois de falha legítima precisa poder entrar de novo. A
        # duplicidade que importa é (os_id, caso), e essa sim é única.
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_espera_os_caso "
                     "ON operacoes_espera(os_id, caso) WHERE os_id IS NOT NULL")


async def registrar(*, lote: str | None, perfil: str, caso: str,
                    os_id: int | None, numero_os: int | None, placa: str,
                    placa_entrada: str | None = None,
                    recipiente_placa: str | None = None,
                    veiculo_id: int | None = None,
                    rastreador_id: int | None = None) -> int | None:
    """Grava UMA pendência. NUNCA levanta por valor estranho.

    Devolve o id, ou None quando já existia — regerar a mesma OS não cria
    pendência dobrada.
    """
    if caso not in CASOS:
        raise ValueError(f"caso desconhecido: {caso!r}")

    def _run():
        _criar()
        with storage._connect() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO operacoes_espera (lote, perfil, caso, os_id, "
                    "numero_os, placa, placa_entrada, recipiente_placa, "
                    "veiculo_id, rastreador_id, criado_em, atualizado_em) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (lote, perfil, caso, os_id, numero_os, placa, placa_entrada,
                     recipiente_placa, veiculo_id, rastreador_id,
                     _agora(), _agora()))
                return cur.lastrowid
            except sqlite3.IntegrityError:
                # Já havia pendência desta OS para este caso.
                return None
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def pendentes(caso: str | None = None) -> list[dict]:
    """O que ainda está esperando, mais antigo primeiro.

    🚨 SÓ `esperando`. `desistiu` não volta sozinho: ele virou aviso no
    Registro e quem decide retomar é uma pessoa. Reprocessar o que desistiu
    calado devolveria o laço infinito que o teto existe para cortar.
    """
    def _run():
        _criar()
        with storage._connect() as conn:
            conn.row_factory = sqlite3.Row
            sql = ("SELECT * FROM operacoes_espera WHERE estado = 'esperando'")
            args: tuple = ()
            if caso:
                sql += " AND caso = ?"
                args = (caso,)
            sql += " ORDER BY id"
            return [dict(r) for r in conn.execute(sql, args)]
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def concluir(espera_id: int, passos: list[str] | None = None) -> None:
    await _mudar(espera_id, "concluido", None, passos)


async def falhar(espera_id: int, erro: str,
                 passos: list[str] | None = None) -> str:
    """Conta a tentativa e decide entre continuar esperando e desistir.

    🚨 DESISTIR NÃO É FALHAR EM SILÊNCIO. Passado o teto, o estado vira
    `desistiu` e a linha continua na tabela, com o último erro — é ela que o
    Registro (F6) mostra. O que não pode é seguir tentando para sempre e o
    operador nunca saber que existe um recipiente preso.
    """
    def _run():
        _criar()
        with storage._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT tentativas FROM operacoes_espera "
                             "WHERE id = ?", (espera_id,)).fetchone()
            if not r:
                return "sumiu"
            n = int(r["tentativas"]) + 1
            estado = "desistiu" if n >= TETO_TENTATIVAS else "esperando"
            conn.execute(
                "UPDATE operacoes_espera SET tentativas = ?, estado = ?, "
                "ultimo_erro = ?, passos_json = ?, atualizado_em = ? "
                "WHERE id = ?",
                (n, estado, erro, json.dumps(passos or [], ensure_ascii=False),
                 _agora(), espera_id))
            return estado
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def _mudar(espera_id: int, estado: str, erro: str | None,
                 passos: list[str] | None) -> None:
    if estado not in ESTADOS:
        raise ValueError(f"estado desconhecido: {estado!r}")

    def _run():
        _criar()
        with storage._connect() as conn:
            conn.execute(
                "UPDATE operacoes_espera SET estado = ?, ultimo_erro = ?, "
                "passos_json = ?, atualizado_em = ? WHERE id = ?",
                (estado, erro, json.dumps(passos or [], ensure_ascii=False),
                 _agora(), espera_id))
    await asyncio.get_running_loop().run_in_executor(None, _run)


async def resumo() -> dict:
    """Quantas em cada estado — é o que a tela do Registro mostra no topo."""
    def _run():
        _criar()
        with storage._connect() as conn:
            linhas = conn.execute(
                "SELECT estado, caso, COUNT(*) FROM operacoes_espera "
                "GROUP BY estado, caso").fetchall()
        saida: dict = {"por_estado": {}, "por_caso": {}}
        for estado, caso, n in linhas:
            saida["por_estado"][estado] = saida["por_estado"].get(estado, 0) + n
            saida["por_caso"][caso] = saida["por_caso"].get(caso, 0) + n
        saida["desistiu"] = saida["por_estado"].get("desistiu", 0)
        return saida
    return await asyncio.get_running_loop().run_in_executor(None, _run)
