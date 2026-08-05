"""Painel de demandas — quadro aberto por link, hospedado no FPSL.

Veio do MoviZap em 05/08, e a mudança foi decisão do usuário: demanda
comercial não tem relação nenhuma com o comunicador, e hospedar por
conveniência é como um sistema vira depósito.

🚨 ROTA PÚBLICA. O token da URL é a única credencial. Duas consequências que
valem para todo código deste módulo:

  1. nada aqui toca tabela do FPSL. Só as quatro `demanda_*`;
  2. toda escrita vem de desconhecido: campo tem teto e o texto nunca é
     interpretado como HTML na tela.

Encadeamento é DENTRO da frente: as frentes andam em paralelo. Um item só
libera quando o anterior da MESMA frente conclui.
"""
import logging
import secrets
import sqlite3
from datetime import date
from pathlib import Path

log = logging.getLogger("fpsl.demandas")

BANCO = Path(__file__).resolve().parent.parent / "data" / "fpsl.db"

MAX_TITULO = 120
MAX_OBS = 500
MAX_NOME = 60

AGUARDANDO, LIBERADO, CONCLUIDO = "aguardando", "liberado", "concluido"
CANCELADO = "cancelado"

# 🚨 Paleta SEM verde e SEM vermelho, de propósito: essas duas cores já
# significam "concluído" e "atrasado" no card. Pessoa com cor verde faria o
# card parecer pronto quando não está.
PALETA = [
    "#2563EB",  # azul
    "#7C3AED",  # roxo
    "#D97706",  # âmbar
    "#0891B2",  # ciano
    "#DB2777",  # rosa
    "#EA580C",  # laranja
    "#4F46E5",  # índigo
    "#0D9488",  # teal
    "#9333EA",  # violeta
    "#0369A1",  # azul-petróleo
]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS demanda_quadro (
    id INTEGER PRIMARY KEY, titulo TEXT NOT NULL, token TEXT NOT NULL UNIQUE,
    ativo INTEGER NOT NULL DEFAULT 1, criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS demanda_frente (
    id INTEGER PRIMARY KEY,
    quadro_id INTEGER NOT NULL REFERENCES demanda_quadro(id) ON DELETE CASCADE,
    nome TEXT NOT NULL, contato TEXT, ordem INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS demanda_item (
    id INTEGER PRIMARY KEY,
    frente_id INTEGER NOT NULL REFERENCES demanda_frente(id) ON DELETE CASCADE,
    titulo TEXT NOT NULL, ordem INTEGER NOT NULL DEFAULT 0,
    prazo TEXT, sem_prazo INTEGER NOT NULL DEFAULT 0, obs TEXT,
    atualizado_em TEXT, atualizado_por TEXT,
    CHECK (NOT (sem_prazo = 1 AND prazo IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS demanda_etapa (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES demanda_item(id) ON DELETE CASCADE,
    descricao TEXT NOT NULL, responsavel TEXT NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0,
    concluida INTEGER NOT NULL DEFAULT 0, concluida_em TEXT,
    CHECK ((concluida = 1) = (concluida_em IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS demanda_pessoa (
    id INTEGER PRIMARY KEY,
    quadro_id INTEGER NOT NULL REFERENCES demanda_quadro(id) ON DELETE CASCADE,
    nome TEXT NOT NULL, cor TEXT NOT NULL, ativo INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_dem_frente ON demanda_frente (quadro_id, ordem);
CREATE INDEX IF NOT EXISTS ix_dem_item ON demanda_item (frente_id, ordem);
CREATE INDEX IF NOT EXISTS ix_dem_etapa ON demanda_etapa (item_id, ordem);
-- 🚨 Nome e cor UNICOS por quadro. A cor identifica a pessoa na tela inteira:
-- duas pessoas com a mesma cor tornam a leitura da faixa inutil, e o banco e
-- que tem de impedir -- nao a tela.
CREATE UNIQUE INDEX IF NOT EXISTS ux_dem_pessoa_nome ON demanda_pessoa (quadro_id, nome);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dem_pessoa_cor ON demanda_pessoa (quadro_id, cor);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(BANCO, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")   # sem isto o CASCADE não acontece
    return c


def preparar() -> None:
    """Cria o esquema e a semente. Idempotente: roda em todo arranque."""
    with _conn() as c:
        c.executescript(ESQUEMA)
        novo = not c.execute("SELECT COUNT(*) FROM demanda_quadro").fetchone()[0]
        if novo:
            _semear(c)
            log.info("quadro de demandas criado")
        _migrar_pessoas(c)


def _migrar_pessoas(c: sqlite3.Connection) -> None:
    """Transforma o texto `responsavel` em cadastro de pessoa com cor.

    Antes a cor saía de um hash do nome: estável, mas ninguém escolhia, e duas
    pessoas podiam cair na mesma. Agora a cor é cadastrada e o banco impede
    repetição.

    Idempotente: roda em todo arranque e não faz nada depois da primeira vez.
    """
    colunas = {r["name"] for r in c.execute("PRAGMA table_info(demanda_etapa)")}
    if "pessoa_id" not in colunas:
        c.execute("ALTER TABLE demanda_etapa ADD COLUMN pessoa_id INTEGER "
                  "REFERENCES demanda_pessoa(id)")
        log.info("demanda_etapa ganhou pessoa_id")

    # `modo` escolhe a VISTA, não o motor: os dados são os mesmos.
    # 'esteira'  = cards horizontais em raia (o primeiro quadro)
    # 'planilha' = tabela com semáforo (formato de cronograma)
    quadro_cols = {r["name"] for r in c.execute("PRAGMA table_info(demanda_quadro)")}
    if "modo" not in quadro_cols:
        c.execute("ALTER TABLE demanda_quadro ADD COLUMN modo TEXT NOT NULL "
                  "DEFAULT 'esteira'")
    if "gerente" not in quadro_cols:
        c.execute("ALTER TABLE demanda_quadro ADD COLUMN gerente TEXT")

    item_cols = {r["name"] for r in c.execute("PRAGMA table_info(demanda_item)")}
    if "cancelado" not in item_cols:
        # 🚨 Cancelado NÃO é concluído: a tarefa não vai acontecer. Tratar como
        # concluído liberaria a de baixo e mentiria no contador.
        c.execute("ALTER TABLE demanda_item ADD COLUMN cancelado INTEGER "
                  "NOT NULL DEFAULT 0")

    quadros = c.execute("SELECT id FROM demanda_quadro").fetchall()
    for q in quadros:
        qid = q["id"]
        # nomes que ainda não viraram pessoa
        nomes = [r["responsavel"] for r in c.execute(
            "SELECT DISTINCT e.responsavel FROM demanda_etapa e "
            "JOIN demanda_item i ON i.id = e.item_id "
            "JOIN demanda_frente f ON f.id = i.frente_id "
            "WHERE f.quadro_id = ? AND e.responsavel IS NOT NULL "
            "AND e.responsavel <> '' AND e.pessoa_id IS NULL", (qid,))]
        for nome in nomes:
            pid = _garantir_pessoa(c, qid, nome)
            c.execute(
                "UPDATE demanda_etapa SET pessoa_id = ? WHERE pessoa_id IS NULL "
                "AND responsavel = ? AND item_id IN (SELECT i.id FROM demanda_item i "
                "JOIN demanda_frente f ON f.id = i.frente_id WHERE f.quadro_id = ?)",
                (pid, nome, qid))
        if nomes:
            log.info("quadro %s: %d pessoa(s) cadastrada(s): %s",
                     qid, len(nomes), ", ".join(nomes))


def _cor_livre(c: sqlite3.Connection, qid: int) -> str | None:
    usadas = {r["cor"] for r in c.execute(
        "SELECT cor FROM demanda_pessoa WHERE quadro_id = ?", (qid,))}
    for cor in PALETA:
        if cor not in usadas:
            return cor
    return None   # paleta esgotada: quem chama decide o que dizer


def _garantir_pessoa(c: sqlite3.Connection, qid: int, nome: str) -> int | None:
    nome = (nome or "").strip()[:MAX_NOME]
    if not nome:
        return None
    r = c.execute("SELECT id FROM demanda_pessoa WHERE quadro_id = ? AND nome = ?",
                  (qid, nome)).fetchone()
    if r:
        return r["id"]
    cor = _cor_livre(c, qid)
    if not cor:
        return None
    return c.execute("INSERT INTO demanda_pessoa (quadro_id, nome, cor) VALUES (?,?,?)",
                     (qid, nome, cor)).lastrowid


def _semear(c: sqlite3.Connection) -> None:
    token = secrets.token_hex(32)
    qid = c.execute(
        "INSERT INTO demanda_quadro (titulo, token) VALUES (?,?)",
        ("Comercial Interno × Externo", token)).lastrowid

    estrutura = [
        ("Governança", "comercial@movisat.com.br · Rodrigo", [
            ("Manutenções nas bases", [("Manutenções nas bases", "Rodrigo")]),
            ("Logins e acessos", [("Logins e acessos", "Rodrigo")]),
            ("Planos integrados", [("Planos integrados", "Rodrigo")]),
        ]),
        ("Prospecta", None, [
            ("Chip disparo", [("Chip disparo", "Karla")]),
            ("Teste disparo mensagens", [("Teste disparo mensagens", "Iago")]),
            ("Base atual fora do prospect", [("Base atual fora do prospect", "Iago")]),
        ]),
        ("SDR / Nina", None, [
            ("E-sim para API oficial", [("E-sim para API oficial", "Karla"),
                                        ("Ativar e vincular", "Iago")]),
            ("Testes atendimento", [("Testes atendimento", "Iago"),
                                    ("On fire", "Rodrigo")]),
            ("Prompt atendimento", [("Prompt atendimento", "Rodrigo")]),
            ("Configurações e registro", [("Configurações e registro", "Rodrigo")]),
        ]),
        ("Reunião inteligente / Live coach", None, [
            ("Base clonada", [("Base clonada", "Iago")]),
            ("Firefile", [("Firefile", "Rodrigo"), ("Integração", "Iago")]),
            ("Controle de acessos", [("Controle de acessos", "Iago")]),
        ]),
    ]

    for of, (nome, contato, itens) in enumerate(estrutura, 1):
        fid = c.execute(
            "INSERT INTO demanda_frente (quadro_id, nome, contato, ordem) VALUES (?,?,?,?)",
            (qid, nome, contato, of)).lastrowid
        for oi, (titulo, etapas) in enumerate(itens, 1):
            # "Base clonada - Iago - 05/08" veio com data no enunciado
            prazo = "2026-08-05" if titulo == "Base clonada" else None
            iid = c.execute(
                "INSERT INTO demanda_item (frente_id, titulo, ordem, prazo) "
                "VALUES (?,?,?,?)", (fid, titulo, oi, prazo)).lastrowid
            for oe, (desc, resp) in enumerate(etapas, 1):
                c.execute(
                    "INSERT INTO demanda_etapa (item_id, descricao, responsavel, ordem) "
                    "VALUES (?,?,?,?)", (iid, desc, resp, oe))


# ----------------------------------------------------------------- leitura

def quadro(token: str) -> dict | None:
    if not token or len(token) > 80:
        return None
    with _conn() as c:
        q = c.execute("SELECT id, titulo, token, modo, gerente FROM demanda_quadro "
                      "WHERE token = ? AND ativo = 1", (token,)).fetchone()
        if not q:
            return None

        frentes = [dict(r) for r in c.execute(
            "SELECT id, nome, contato FROM demanda_frente WHERE quadro_id = ? "
            "ORDER BY ordem, id", (q["id"],))]
        itens = [dict(r) for r in c.execute(
            "SELECT i.* FROM demanda_item i JOIN demanda_frente f ON f.id = i.frente_id "
            "WHERE f.quadro_id = ? ORDER BY i.ordem, i.id", (q["id"],))]
        # A cor vem do CADASTRO, por junção -- não é copiada para a etapa.
        # "Evento referencia, nunca copia": pessoa que troca de cor troca em
        # todo card de uma vez.
        etapas = [dict(r) for r in c.execute(
            "SELECT e.id, e.item_id, e.descricao, e.ordem, e.concluida, "
            "       e.concluida_em, e.pessoa_id, "
            "       COALESCE(p.nome, e.responsavel) AS responsavel, "
            "       COALESCE(p.cor, '#94A3B8') AS cor "
            "FROM demanda_etapa e JOIN demanda_item i ON i.id = e.item_id "
            "JOIN demanda_frente f ON f.id = i.frente_id "
            "LEFT JOIN demanda_pessoa p ON p.id = e.pessoa_id "
            "WHERE f.quadro_id = ? ORDER BY e.ordem, e.id", (q["id"],))]

        pessoas = [dict(r) for r in c.execute(
            "SELECT id, nome, cor FROM demanda_pessoa WHERE quadro_id = ? AND ativo = 1 "
            "ORDER BY nome", (q["id"],))]
        usadas = {p["cor"] for p in pessoas}

    por_item = {}
    for e in etapas:
        e["concluida"] = bool(e["concluida"])
        por_item.setdefault(e["item_id"], []).append(e)

    hoje = date.today().isoformat()
    for i in itens:
        i["sem_prazo"] = bool(i["sem_prazo"])
        i["cancelado"] = bool(i.get("cancelado"))
        i["etapas"] = por_item.get(i["id"], [])
        i["concluido"] = bool(i["etapas"]) and all(e["concluida"] for e in i["etapas"])
        # 🚨 `atrasado` é DERIVADO, nunca gravado: prazo que venceu enquanto
        # ninguém olhava tem que virar vermelho sozinho.
        i["atrasado"] = bool(i["prazo"] and not i["concluido"]
                             and not i["cancelado"] and i["prazo"] < hoje)

    # `n` é o número da linha DENTRO da frente -- é ele que aparece no
    # "Aguardando N" da planilha, dizendo qual linha está travando.
    for f in frentes:
        f["itens"] = [i for i in itens if i["frente_id"] == f["id"]]
        livre = True
        trava_n = None
        for n, i in enumerate(f["itens"], 1):
            i["n"] = n
            if i["concluido"]:
                i["estado"] = CONCLUIDO
            elif i["cancelado"]:
                # 🚨 Cancelado NÃO libera a de baixo: a tarefa não aconteceu.
                i["estado"] = CANCELADO
            elif livre:
                i["estado"] = LIBERADO
            else:
                i["estado"] = AGUARDANDO
            i["aguardando_n"] = trava_n if i["estado"] == AGUARDANDO else None
            if not i["concluido"] and trava_n is None:
                trava_n = n          # a primeira não-concluída é quem trava
            livre = livre and i["concluido"]

    # quem tem tarefa PENDENTE -- é o que a legenda mostra
    com_tarefa = {e["pessoa_id"] for f in frentes for i in f["itens"]
                  for e in i["etapas"] if not e["concluida"] and e["pessoa_id"]}
    for p in pessoas:
        p["tem_tarefa"] = p["id"] in com_tarefa
        p["pendentes"] = sum(
            1 for f in frentes for i in f["itens"] for e in i["etapas"]
            if e["pessoa_id"] == p["id"] and not e["concluida"])

    return {
        "titulo": q["titulo"], "token": q["token"], "frentes": frentes,
        "modo": q["modo"] or "esteira", "gerente": q["gerente"],
        "total": len(itens),
        "concluidos": sum(1 for i in itens if i["concluido"]),
        "atrasados": sum(1 for i in itens if i["atrasado"]),
        "pessoas": pessoas,
        "cores_livres": [c for c in PALETA if c not in usadas],
        "paleta": PALETA,
    }


# ----------------------------------------------------------------- escrita

def _qid(c, token):
    r = c.execute("SELECT id FROM demanda_quadro WHERE token = ? AND ativo = 1",
                  (token,)).fetchone()
    return r["id"] if r else None


def _liberado(c, item_id: int) -> bool:
    """🚨 Conferido no BACKEND. A tela trava o campo, mas quem tem o link tem
    o endereço da rota -- e desabilitar no HTML nunca impediu ninguém."""
    it = c.execute("SELECT frente_id, ordem FROM demanda_item WHERE id = ?",
                   (item_id,)).fetchone()
    if not it:
        return False
    for a in c.execute("SELECT id FROM demanda_item WHERE frente_id = ? AND ordem < ?",
                       (it["frente_id"], it["ordem"])):
        et = c.execute("SELECT concluida FROM demanda_etapa WHERE item_id = ?",
                       (a["id"],)).fetchall()
        if not et or not all(e["concluida"] for e in et):
            return False
    return True


def _pertence(c, qid: int, item_id: int) -> bool:
    return bool(c.execute(
        "SELECT 1 FROM demanda_item i JOIN demanda_frente f ON f.id = i.frente_id "
        "WHERE i.id = ? AND f.quadro_id = ?", (item_id, qid)).fetchone())


def atualizar_item(token, item_id, prazo, sem_prazo, obs, quem) -> bool:
    with _conn() as c:
        qid = _qid(c, token)
        if not qid or not _pertence(c, qid, item_id) or not _liberado(c, item_id):
            return False
        if sem_prazo:
            prazo = None   # o CHECK recusa os dois juntos; a intenção ganha
        c.execute(
            "UPDATE demanda_item SET prazo=?, sem_prazo=?, obs=?, "
            "atualizado_em=datetime('now'), atualizado_por=? WHERE id=?",
            (prazo or None, 1 if sem_prazo else 0, (obs or "")[:MAX_OBS] or None,
             (quem or "").strip()[:MAX_NOME] or None, item_id))
    return True


def marcar_etapa(token, etapa_id, concluida, quem) -> bool:
    with _conn() as c:
        qid = _qid(c, token)
        if not qid:
            return False
        r = c.execute(
            "SELECT e.item_id FROM demanda_etapa e JOIN demanda_item i ON i.id = e.item_id "
            "JOIN demanda_frente f ON f.id = i.frente_id WHERE e.id = ? AND f.quadro_id = ?",
            (etapa_id, qid)).fetchone()
        if not r or not _liberado(c, r["item_id"]):
            return False
        c.execute("UPDATE demanda_etapa SET concluida=?, "
                  "concluida_em = CASE WHEN ? THEN datetime('now') END WHERE id=?",
                  (1 if concluida else 0, 1 if concluida else 0, etapa_id))
        c.execute("UPDATE demanda_item SET atualizado_em=datetime('now'), "
                  "atualizado_por=? WHERE id=?",
                  ((quem or "").strip()[:MAX_NOME] or None, r["item_id"]))
    return True


# --------------------------------------------------- estrutura (pipeline)

def criar_frente(token, nome, contato) -> dict | None:
    nome = (nome or "").strip()[:MAX_TITULO]
    if not nome:
        return None
    with _conn() as c:
        qid = _qid(c, token)
        if not qid:
            return None
        ordem = (c.execute("SELECT COALESCE(MAX(ordem),0)+1 AS n FROM demanda_frente "
                           "WHERE quadro_id=?", (qid,)).fetchone()["n"])
        fid = c.execute("INSERT INTO demanda_frente (quadro_id,nome,contato,ordem) "
                        "VALUES (?,?,?,?)",
                        (qid, nome, (contato or "").strip()[:MAX_TITULO] or None,
                         ordem)).lastrowid
    return {"id": fid}


def _pessoa_valida(c, qid: int, pessoa_id) -> tuple[int, str] | None:
    """A pessoa tem de existir NESTE quadro. Não se aceita id solto."""
    r = c.execute("SELECT id, nome FROM demanda_pessoa "
                  "WHERE id=? AND quadro_id=? AND ativo=1", (pessoa_id, qid)).fetchone()
    return (r["id"], r["nome"]) if r else None


def criar_item(token, frente_id, titulo, pessoa_id) -> dict | None:
    titulo = (titulo or "").strip()[:MAX_TITULO]
    if not titulo:
        return None
    with _conn() as c:
        qid = _qid(c, token)
        if not qid:
            return None
        if not c.execute("SELECT 1 FROM demanda_frente WHERE id=? AND quadro_id=?",
                         (frente_id, qid)).fetchone():
            return None
        p = _pessoa_valida(c, qid, pessoa_id)
        if not p:
            return None
        ordem = (c.execute("SELECT COALESCE(MAX(ordem),0)+1 AS n FROM demanda_item "
                           "WHERE frente_id=?", (frente_id,)).fetchone()["n"])
        iid = c.execute("INSERT INTO demanda_item (frente_id,titulo,ordem) VALUES (?,?,?)",
                        (frente_id, titulo, ordem)).lastrowid
        c.execute("INSERT INTO demanda_etapa (item_id,descricao,responsavel,pessoa_id,ordem) "
                  "VALUES (?,?,?,?,1)", (iid, titulo, p[1], p[0]))
    return {"id": iid}


def criar_etapa(token, item_id, descricao, pessoa_id) -> dict | None:
    """A segunda etapa é o handoff: 'Karla → Iago'."""
    descricao = (descricao or "").strip()[:MAX_TITULO]
    if not descricao:
        return None
    with _conn() as c:
        qid = _qid(c, token)
        if not qid or not _pertence(c, qid, item_id):
            return None
        p = _pessoa_valida(c, qid, pessoa_id)
        if not p:
            return None
        ordem = (c.execute("SELECT COALESCE(MAX(ordem),0)+1 AS n FROM demanda_etapa "
                           "WHERE item_id=?", (item_id,)).fetchone()["n"])
        eid = c.execute("INSERT INTO demanda_etapa "
                        "(item_id,descricao,responsavel,pessoa_id,ordem) VALUES (?,?,?,?,?)",
                        (item_id, descricao, p[1], p[0], ordem)).lastrowid
    return {"id": eid}


def criar_pessoa(token, nome, cor) -> dict | None:
    """Cadastra pessoa com cor escolhida.

    🚨 Devolve um MOTIVO quando recusa. "não deu" sem dizer por quê faz a
    pessoa tentar de novo igual.
    """
    nome = (nome or "").strip()[:MAX_NOME]
    cor = (cor or "").strip().upper()
    if not nome:
        return {"erro": "nome_vazio"}
    if cor not in PALETA:
        return {"erro": "cor_invalida"}
    with _conn() as c:
        qid = _qid(c, token)
        if not qid:
            return None
        if c.execute("SELECT 1 FROM demanda_pessoa WHERE quadro_id=? AND nome=?",
                     (qid, nome)).fetchone():
            return {"erro": "nome_repetido"}
        if c.execute("SELECT 1 FROM demanda_pessoa WHERE quadro_id=? AND cor=?",
                     (qid, cor)).fetchone():
            return {"erro": "cor_em_uso"}
        pid = c.execute("INSERT INTO demanda_pessoa (quadro_id,nome,cor) VALUES (?,?,?)",
                        (qid, nome, cor)).lastrowid
    return {"id": pid, "nome": nome, "cor": cor}


def apagar_item(token, item_id) -> bool:
    with _conn() as c:
        qid = _qid(c, token)
        if not qid or not _pertence(c, qid, item_id):
            return False
        c.execute("DELETE FROM demanda_item WHERE id=?", (item_id,))
    return True


def apagar_frente(token, frente_id) -> bool:
    with _conn() as c:
        qid = _qid(c, token)
        if not qid:
            return False
        if not c.execute("SELECT 1 FROM demanda_frente WHERE id=? AND quadro_id=?",
                         (frente_id, qid)).fetchone():
            return False
        c.execute("DELETE FROM demanda_frente WHERE id=?", (frente_id,))
    return True


def token_do_quadro() -> str | None:
    """Só para o log de arranque e para os scripts. Nunca vai para tela."""
    with _conn() as c:
        r = c.execute("SELECT token FROM demanda_quadro LIMIT 1").fetchone()
    return r["token"] if r else None


def listar_quadros() -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT q.id, q.titulo, q.token, q.ativo, q.criado_em, "
            "(SELECT COUNT(*) FROM demanda_frente f WHERE f.quadro_id = q.id) AS frentes "
            "FROM demanda_quadro q ORDER BY q.id")]


def renomear_item(token, item_id, titulo, quem) -> bool:
    """Editar o texto direto na célula, como planilha."""
    titulo = (titulo or "").strip()[:MAX_TITULO]
    if not titulo:
        return False
    with _conn() as c:
        qid = _qid(c, token)
        if not qid or not _pertence(c, qid, item_id) or not _liberado(c, item_id):
            return False
        c.execute("UPDATE demanda_item SET titulo=?, atualizado_em=datetime('now'), "
                  "atualizado_por=? WHERE id=?",
                  (titulo, (quem or "").strip()[:MAX_NOME] or None, item_id))
    return True


def trocar_responsavel(token, item_id, pessoa_id, quem) -> bool:
    """Troca o dono da PRIMEIRA etapa pendente -- é dela que sai a cor.

    Item com handoff mantém as demais etapas: trocar o responsável não é
    desfazer o encadeamento.
    """
    with _conn() as c:
        qid = _qid(c, token)
        if not qid or not _pertence(c, qid, item_id):
            return False
        p = _pessoa_valida(c, qid, pessoa_id)
        if not p:
            return False
        alvo = c.execute("SELECT id FROM demanda_etapa WHERE item_id=? AND concluida=0 "
                         "ORDER BY ordem LIMIT 1", (item_id,)).fetchone()
        if not alvo:   # tudo concluído: troca a última, para o histórico ficar certo
            alvo = c.execute("SELECT id FROM demanda_etapa WHERE item_id=? "
                             "ORDER BY ordem DESC LIMIT 1", (item_id,)).fetchone()
        if not alvo:
            return False
        c.execute("UPDATE demanda_etapa SET pessoa_id=?, responsavel=? WHERE id=?",
                  (p[0], p[1], alvo["id"]))
        c.execute("UPDATE demanda_item SET atualizado_em=datetime('now'), "
                  "atualizado_por=? WHERE id=?",
                  ((quem or "").strip()[:MAX_NOME] or None, item_id))
    return True


def cancelar_item(token, item_id, cancelado: bool) -> bool:
    """Cancelado não é concluído: a tarefa não vai acontecer.

    🚨 Por isso NÃO libera a de baixo. Tratar cancelado como concluído faria a
    fila andar sobre uma tarefa que ninguém fez.
    """
    with _conn() as c:
        qid = _qid(c, token)
        if not qid or not _pertence(c, qid, item_id):
            return False
        c.execute("UPDATE demanda_item SET cancelado=?, atualizado_em=datetime('now') "
                  "WHERE id=?", (1 if cancelado else 0, item_id))
    return True


def criar_quadro(titulo: str, modo: str = "esteira", gerente: str = None) -> dict | None:
    """Um quadro NOVO, com link próprio.

    🚨 É por aqui que nasce o segundo painel rápido -- não por copiar código.
    O esquema é multi-quadro desde o começo: `token` identifica, e toda
    consulta filtra por `quadro_id`. Um painel novo é uma LINHA, e as pessoas,
    as cores e as regras vêm de graça.

    Ver /home/claude/docs/03_Painel_Rapido.md.
    """
    titulo = (titulo or "").strip()[:MAX_TITULO]
    if not titulo or modo not in ("esteira", "planilha"):
        return None
    with _conn() as c:
        c.executescript(ESQUEMA)
        token = secrets.token_hex(32)
        qid = c.execute(
            "INSERT INTO demanda_quadro (titulo, token, modo, gerente) VALUES (?,?,?,?)",
            (titulo, token, modo, (gerente or "").strip()[:MAX_NOME] or None)).lastrowid
    log.info("quadro %s criado (%s): %s", qid, modo, titulo)
    return {"id": qid, "titulo": titulo, "token": token, "modo": modo}
