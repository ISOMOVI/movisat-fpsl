# -*- coding: utf-8 -*-
"""As rotas HTTP da ponte de **Serviço dos Técnicos** — 18/11.

🚨 **POR HTTP, e não só por função.** `feedback_rota_nova_pede_teste_http`: o
que quebrou em 17/11 na outra ponte foi a ROTA -- a função recusava e a rota
devolvia 200 com `ok: False`, que é exatamente o par que teste de função não
mede. E aqui o par importa mais: uma recusa silenciosa faria a tela avançar um
card de pagamento.

🚨 BANCO TEMPORÁRIO, apontado ANTES de qualquer import do pacote.
"""
import json
import pathlib
import sys
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TMP = tempfile.mkdtemp(prefix="pagamento_rotas_")
DB = pathlib.Path(TMP) / "fpsl_teste.db"

from fpsl_weso import storage  # noqa: E402

storage.DB_PATH = DB

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from fpsl_weso.config import settings  # noqa: E402
from fpsl_weso.painel import pagamento_tabelas  # noqa: E402
from fpsl_weso.painel.templates_config import (KM_DESLOCAMENTO_ID,  # noqa: E402
                                               PAGAMENTO_TECNICO_ID)
from fpsl_weso.routers import pagamento_ponte  # noqa: E402

CHAVE = "zz-chave-de-teste"
CAB = {"X-Ponte-Key": CHAVE}
VELASCO = 998063
FRANCK = 14262


@pytest.fixture(autouse=True)
def segredo(monkeypatch):
    monkeypatch.setattr(settings, "ponte_fpsl_segredo", CHAVE)


@pytest.fixture
def cliente():
    app = FastAPI()
    app.include_router(pagamento_ponte.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def base():
    with storage._connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS os_historico (
                numero_os INTEGER PRIMARY KEY, cliente_id INTEGER,
                data_previsao TEXT, atualizado_em TEXT, visto_em TEXT,
                excluida INTEGER DEFAULT 0, materiais_json TEXT,
                situacao_id INTEGER, tecnicos_json TEXT, termo TEXT,
                -- 🚨 AS TRÊS QUE O ENRIQUECIMENTO DE 19/11 LÊ. Sem elas o
                -- `quadro()` morre com *"no such column: h.tipo"* -- e o
                -- defeito seria do banco de teste, não do código.
                tipo INTEGER, status_str TEXT, n_oficinas INTEGER)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tecnicos (
                tecnico_id INTEGER PRIMARY KEY, nome TEXT NOT NULL,
                excluido INTEGER NOT NULL DEFAULT 0, atualizado_em TEXT)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS datascope_respostas (
                form_answer_id INTEGER PRIMARY KEY, numero_os INTEGER,
                form_state TEXT, updated_at TEXT, sincronizado_em TEXT)
        """)
        # 🚨 O CAMINHO DO NOME DO CLIENTE DÁ TRÊS SALTOS (19/11), porque a
        # `clientes` não guarda nome:
        #   os_historico.cliente_id -> clientes.cnpjcpf -> contrato_cliente.nome
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                harmonit_id INTEGER PRIMARY KEY, cnpjcpf TEXT,
                criado_em TEXT)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contrato_cliente (
                cnpj TEXT PRIMARY KEY, nome TEXT, nome_fonte TEXT,
                atualizado_em TEXT, atualizado_por TEXT)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tipos_os (
                tipo_id INTEGER PRIMARY KEY, nome TEXT, codigo TEXT,
                atualizado_em TEXT)
        """)
        pagamento_tabelas.criar(conn)
        for t in ("os_historico", "tecnicos", "datascope_respostas",
                  "clientes", "contrato_cliente", "tipos_os",
                  "pagamento_artefato", "pagamento_lote", "pagamento_evento"):
            conn.execute("DELETE FROM %s" % t)
        conn.execute(
            "INSERT INTO tecnicos (tecnico_id, nome, excluido, atualizado_em) "
            "VALUES (?, 'Franck', 0, '2026-11-18')", (FRANCK,))
        conn.execute(
            "INSERT INTO os_historico (numero_os, cliente_id, materiais_json, "
            "  tecnicos_json, termo, data_previsao, atualizado_em, visto_em, "
            "  excluida, situacao_id) "
            "VALUES (990300, ?, ?, ?, '8952', '18/11/2026 09:00:00', "
            "        '2026-11-18T12:00:00+00:00', '2026-11-18T12:00:00+00:00', "
            "        0, 15694)",
            (VELASCO,
             json.dumps([{"idProduto": PAGAMENTO_TECNICO_ID,
                          "valorTotal": 120.0},
                         {"idProduto": KM_DESLOCAMENTO_ID, "valorTotal": 10.0}]),
             json.dumps([{"usuarioId": FRANCK, "nomeTecnico": "Franck"}])))
        conn.commit()
    yield


def _id_do_artefato():
    with storage._connect() as conn:
        return conn.execute(
            "SELECT id FROM pagamento_artefato WHERE numero_os = 990300"
        ).fetchone()[0]


class TestAChave:
    """🚨 Servidor-a-servidor: sem a chave, nada responde."""

    def test_toda_rota_exige_a_chave(self, cliente):
        for caminho, corpo in (("/api/pagamento/varrer", {"horas": None}),
                               ("/api/pagamento/preparar", {"artefatos": []}),
                               ("/api/pagamento/ciente", {"artefato_id": 1}),
                               ("/api/pagamento/auditar", {"lote_id": 1})):
            assert cliente.post(caminho, json=corpo).status_code == 422, caminho
        assert cliente.get("/api/pagamento/quadro").status_code == 422

    def test_chave_ERRADA_nao_passa(self, cliente):
        r = cliente.get("/api/pagamento/quadro",
                        headers={"X-Ponte-Key": "errada"})
        assert r.status_code in (401, 403)


class TestOFluxoInteiro:
    """🚨 As cinco colunas de ponta a ponta, por HTTP — é o teste que prova que
    o card chega ao Procfy."""

    def test_da_varredura_ao_pagamento_enviado(self, cliente):
        # ---- coluna 1
        r = cliente.post("/api/pagamento/varrer", json={"horas": None},
                         headers=CAB)
        assert r.status_code == 200, r.text
        assert r.json()["novos"] == 1

        q = cliente.get("/api/pagamento/quadro", headers=CAB).json()
        assert [c["chave"] for c in q["colunas"]] == list(
            pagamento_tabelas.COLUNAS)
        assert q["colunas"][0]["total"] == 1

        aid = _id_do_artefato()

        # ---- coluna 2
        r = cliente.post("/api/pagamento/preparar", headers=CAB, json={
            "artefatos": [{"id": aid, "orcamento_numero": 3}],
            "por": "Zz Teste"})
        assert r.json()["preparados"] == 1
        lote = r.json()["lotes"][0]

        r = cliente.post("/api/pagamento/conferir-situacao", headers=CAB,
                         json={"artefato_id": aid, "etapas_nossas": []})
        assert r.json()["libera"] is True
        assert r.json()["situacao_do_erp"] == 15694

        assert cliente.post("/api/pagamento/ciente", headers=CAB,
                            json={"artefato_id": aid}).json()["ok"] is True
        r = cliente.post("/api/pagamento/auditar", headers=CAB,
                         json={"lote_id": lote})
        assert r.json()["avancaram"] == 1

        # ---- coluna 3
        r = cliente.post("/api/pagamento/datascope", headers=CAB,
                         json={"artefato_id": aid})
        assert r.json()["form_state"] is None
        r = cliente.post("/api/pagamento/comprovante", headers=CAB, json={
            "artefato_id": aid, "arquivo": "recibo.pdf", "valor": 130.0})
        assert r.json()["semaforo"] == "verde"

        # ---- coluna 4
        r = cliente.post("/api/pagamento/previa-do-arquivo", headers=CAB,
                         json={"lote_id": lote, "config": {}})
        assert r.json()["ok"] is True
        assert len(r.json()["linhas"]) == 1
        r = cliente.post("/api/pagamento/montar-arquivo", headers=CAB,
                         json={"lote_id": lote, "config": {}})
        assert r.json()["ok"] is True
        assert r.json()["arquivo"].endswith(".xlsx")

        # ---- coluna 5
        assert cliente.post("/api/pagamento/enviar", headers=CAB,
                            json={"lote_id": lote}).json()["ok"] is True
        q = cliente.get("/api/pagamento/quadro", headers=CAB).json()
        assert q["colunas"][4]["total"] == 1

        # ---- TAREFA 2.5: reabrir na coluna 5 e GERAR DE NOVO
        # 🔵 *"Reabrir na coluna 5 e gerar o arquivo de novo"*.
        # 🚨 O CICLO INTEIRO, porque e isso que prova: reabre, confere que o
        # arquivo SAIU do lote, monta outra vez e volta para a coluna 5. Medir
        # so o "reabriu" deixaria a segunda metade (*"gerar de novo"*) sem
        # prova -- e e nela que o `montar_arquivo` "aceita lote reaberto".
        antes = r.json()  # o montar-arquivo do bloco acima
        r = cliente.post("/api/pagamento/reabrir", headers=CAB,
                         json={"lote_id": lote, "por": "Zz Teste"})
        assert r.json()["ok"] is True, r.json()
        assert r.json()["reabertos"] == 1
        assert r.json()["para"] == "validacao"
        q2 = cliente.get("/api/pagamento/quadro", headers=CAB).json()
        assert q2["colunas"][4]["total"] == 0, q2["colunas"][4]
        assert q2["colunas"][2]["total"] == 1, q2["colunas"][2]
        # 🚨 NAO E DEVOLVER: o comprovante e o ciente FICAM. Se saissem, o
        # operador refaria conferencia que estava boa.
        item = q2["colunas"][2]["cards"][0]["artefatos"][0]
        assert item["comprovante_arquivo"] == "recibo.pdf", item
        assert item["semaforo"] == "verde", item
        assert item["coluna"] == "validacao", item
        # ⚠️ E O ARQUIVO SAIU DO LOTE: se ficasse, o `enviar` aceitaria mandar
        # de novo sem ninguem ter gerado nada -- ele so confere que o campo
        # existe.
        r = cliente.post("/api/pagamento/enviar", headers=CAB,
                         json={"lote_id": lote})
        assert r.json()["ok"] is False, r.json()
        # 🚨 E O "GERAR DE NOVO" FUNCIONA, com nome NOVO de arquivo.
        r = cliente.post("/api/pagamento/montar-arquivo", headers=CAB,
                         json={"lote_id": lote, "config": {}})
        assert r.json()["ok"] is True, r.json()
        assert r.json()["arquivo"] != antes["arquivo"], (
            "o arquivo novo tem o mesmo nome do antigo")
        assert cliente.post("/api/pagamento/enviar", headers=CAB,
                            json={"lote_id": lote}).json()["ok"] is True
        q2 = cliente.get("/api/pagamento/quadro", headers=CAB).json()
        assert q2["colunas"][4]["total"] == 1

        # ---- TAREFA 2.4: excluir o card inteiro, da ULTIMA coluna
        # 🔵 *"Excluir o card inteiro devolvendo tudo a coluna 1, com
        # justificativa unica"*.
        # 🚨 Daqui, da coluna 5, de proposito: e o caso mais duro -- o arquivo
        # ja foi montado e marcado como enviado, e e onde um "sempre para a
        # anterior" estragaria tudo. 🔵 Dele: *"nao retorna para a anterior e
        # sim para o 1"*.
        r = cliente.post("/api/pagamento/devolver-lote", headers=CAB, json={
            "lote_id": lote, "justificativa": "zz lote inteiro de volta",
            "por": "Zz Teste"})
        assert r.json()["ok"] is True, r.json()
        assert r.json()["devolvidos"] == 1, r.json()
        assert r.json()["para"] == "movimentacao"
        q = cliente.get("/api/pagamento/quadro", headers=CAB).json()
        # O lote SAI do quadro sozinho: os cards vem dos artefatos.
        assert q["colunas"][4]["total"] == 0, q["colunas"][4]
        assert q["colunas"][0]["total"] == 1, q["colunas"][0]
        # 🚨 A JUSTIFICATIVA VAI NO ITEM, e o semaforo fica laranja: e o que o
        # card da coluna 1 mostra. Guardar so no lote deixaria o item mudo.
        item = q["colunas"][0]["cards"][0]["artefatos"][0]
        assert item["semaforo"] == "laranja", item
        assert item["justificativa"] == "zz lote inteiro de volta", item
        # ⚠️ E o ciente SAI: o artefato volta ao comeco, e herdar um ciente
        # dado sobre outro estado seria confirmar o que ninguem olhou.
        assert not item.get("ciente_em"), item


class TestAsRecusasSaoRESPOSTA:
    """🚨 Recusa devolve 200 com `ok: False` e **motivo por extenso** — nunca
    estoura. 🔵 *"os motivos de recusa deve aparecer descritos ao inves de erro
    generico, para que me tragam o problema ja cientes"*."""

    def test_devolver_sem_justificativa(self, cliente):
        cliente.post("/api/pagamento/varrer", json={"horas": None},
                     headers=CAB)
        aid = _id_do_artefato()
        cliente.post("/api/pagamento/preparar", headers=CAB,
                     json={"artefatos": [{"id": aid}]})
        r = cliente.post("/api/pagamento/devolver", headers=CAB,
                         json={"artefato_id": aid, "justificativa": " "})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert "justificativa" in r.json()["motivo"]

    def test_devolver_LOTE_sem_justificativa(self, cliente):
        """🔵 *"com justificativa unica"* -- e sem ela nao se devolve, igual ao
        de um item: os itens ficariam laranjas e mudos na coluna 1."""
        cliente.post("/api/pagamento/varrer", json={"horas": None},
                     headers=CAB)
        aid = _id_do_artefato()
        lote = cliente.post("/api/pagamento/preparar", headers=CAB,
                            json={"artefatos": [{"id": aid}]}
                            ).json()["lotes"][0]
        r = cliente.post("/api/pagamento/devolver-lote", headers=CAB,
                         json={"lote_id": lote, "justificativa": "  "})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert "justificativa" in r.json()["motivo"]

    def test_devolver_LOTE_que_nao_existe(self, cliente):
        r = cliente.post("/api/pagamento/devolver-lote", headers=CAB,
                         json={"lote_id": 999999, "justificativa": "zz"})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert "nao existe" in r.json()["motivo"]

    def test_devolver_LOTE_vazio_diz_que_esta_vazio(self, cliente):
        """⚠️ Nao e erro, e nao e "ok" tambem: um "ok" que nao mexeu em nada
        faria o operador achar que devolveu."""
        cliente.post("/api/pagamento/varrer", json={"horas": None},
                     headers=CAB)
        aid = _id_do_artefato()
        lote = cliente.post("/api/pagamento/preparar", headers=CAB,
                            json={"artefatos": [{"id": aid}]}
                            ).json()["lotes"][0]
        cliente.post("/api/pagamento/devolver", headers=CAB,
                     json={"artefato_id": aid, "justificativa": "zz um"})
        r = cliente.post("/api/pagamento/devolver-lote", headers=CAB,
                         json={"lote_id": lote, "justificativa": "zz dois"})
        assert r.json()["ok"] is False
        assert r.json()["devolvidos"] == 0
        assert "nao tem item" in r.json()["motivo"]

    def test_reabrir_lote_que_nao_esta_na_coluna_5(self, cliente):
        """🔵 Ele pediu reabrir NA COLUNA 5. De `procfy` o caminho e montar o
        arquivo de novo, que ja existe; antes disso nao ha o que reabrir."""
        cliente.post("/api/pagamento/varrer", json={"horas": None},
                     headers=CAB)
        aid = _id_do_artefato()
        lote = cliente.post("/api/pagamento/preparar", headers=CAB,
                            json={"artefatos": [{"id": aid}]}
                            ).json()["lotes"][0]
        r = cliente.post("/api/pagamento/reabrir", headers=CAB,
                         json={"lote_id": lote})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert "coluna 5" in r.json()["motivo"]

    def test_reabrir_lote_que_nao_existe(self, cliente):
        r = cliente.post("/api/pagamento/reabrir", headers=CAB,
                         json={"lote_id": 999999})
        assert r.json()["ok"] is False
        assert "nao existe" in r.json()["motivo"]

    def test_auditar_lote_que_nao_existe(self, cliente):
        r = cliente.post("/api/pagamento/auditar", headers=CAB,
                         json={"lote_id": 999999})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert "nao existe" in r.json()["motivo"]

    def test_comprovante_sem_arquivo_nem_dispensa(self, cliente):
        cliente.post("/api/pagamento/varrer", json={"horas": None},
                     headers=CAB)
        r = cliente.post("/api/pagamento/comprovante", headers=CAB,
                         json={"artefato_id": _id_do_artefato()})
        assert r.json()["ok"] is False
        assert "comprovante" in r.json()["motivo"]


class TestOQueANaoDeveAcontecer:
    def test_a_PREVIA_nao_move_card(self, cliente):
        """⚠️ Ver o resumo não pode mover card: por isso a prévia é rota
        separada de quem grava."""
        cliente.post("/api/pagamento/varrer", json={"horas": None},
                     headers=CAB)
        aid = _id_do_artefato()
        lote = cliente.post(
            "/api/pagamento/preparar", headers=CAB,
            json={"artefatos": [{"id": aid}]}).json()["lotes"][0]
        cliente.post("/api/pagamento/ciente", headers=CAB,
                     json={"artefato_id": aid})
        cliente.post("/api/pagamento/auditar", headers=CAB,
                     json={"lote_id": lote})
        cliente.post("/api/pagamento/previa-do-arquivo", headers=CAB,
                     json={"lote_id": lote, "config": {}})
        with storage._connect() as conn:
            assert conn.execute(
                "SELECT coluna FROM pagamento_artefato WHERE id = ?",
                (aid,)).fetchone()[0] == "validacao"

    def test_a_ponte_NAO_fala_com_o_harmonit(self):
        """🚨 Trava por texto: é a diferença entre custar zero e entrar na fila
        do pool com o painel da manhã."""
        import inspect
        fonte = inspect.getsource(pagamento_ponte)
        assert "harmonit_get" not in fonte
        assert "harmonit_post" not in fonte

    def test_a_ponte_NAO_serve_binario(self):
        """🚨 Ela fala JSON com o MoviZap e nada mais: abrir um caminho de
        download aqui exporia o FPSL a quem só deveria falar com o painel."""
        import inspect
        fonte = inspect.getsource(pagamento_ponte)
        assert "FileResponse" not in fonte
        assert "StreamingResponse" not in fonte
