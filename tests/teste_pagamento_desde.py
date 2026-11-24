# -*- coding: utf-8 -*-
"""A DATA INICIAL DA ABA 2 — 🔵 D6 e D7 dele, 23/11.

🔵 *"use 16/11/2026 de inicio para o financeiro, não mexa na data do OP"* · e,
sobre os anteriores: **esconder, não apagar**.

🚨 **POR HTTP, e não só por função** (`feedback_rota_nova_pede_teste_http`): o
que quebrou em 17/11 na outra ponte foi a ROTA — a função recusava e a rota
devolvia 200 com `ok: False`, que é justamente o par que teste de função não
mede. A `POST /api/pagamento/desde` é rota nova, então ela vem por HTTP.

🚨 **BANCO TEMPORÁRIO, apontado ANTES de qualquer import do pacote.** Medido em
19/11: a suíte falava com o banco de PRODUÇÃO, e um teste de fila resolveu uma
escrita real. Aqui se grava `config` e `pagamento_artefato`, então o banco é
descartável e é a primeira coisa deste arquivo.

📏 OS NÚMEROS QUE ESTE ARQUIVO GUARDA, medidos em 23/11 no `fpsl.db` de
verdade: 79 artefatos; o corte de 16/11 deixa **2** à vista (OS 17124 do
Franck, em Validação, e OS 17131 sem técnico, em Movimentação) e esconde **77**.
Ele soube desses números antes de decidir e escolheu esconder.
"""
import json
import pathlib
import sys
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TMP = tempfile.mkdtemp(prefix="pagamento_desde_")
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
from fpsl_weso.services import pagamento_servico  # noqa: E402

CHAVE = "zz-chave-de-teste"
CAB = {"X-Ponte-Key": CHAVE}
VELASCO = 998063
FRANCK = 14262

# 🔵 D6: o padrão é 16/11/2026, e é o que o código traz quando o `config` está
# vazio. A trava `test_o_padrao_e_16_11` prende o número, que é o DELE.
PADRAO = "2026-11-16"


@pytest.fixture(autouse=True)
def segredo(monkeypatch):
    monkeypatch.setattr(settings, "ponte_fpsl_segredo", CHAVE)


@pytest.fixture
def cliente():
    app = FastAPI()
    app.include_router(pagamento_ponte.router)
    return TestClient(app)


def _os(conn, numero, data_previsao, *, pagamento=120.0, km=10.0,
        tecnico=FRANCK):
    conn.execute(
        "INSERT INTO os_historico (numero_os, cliente_id, materiais_json, "
        "  tecnicos_json, termo, data_previsao, atualizado_em, visto_em, "
        "  excluida, situacao_id) "
        "VALUES (?, ?, ?, ?, '8952', ?, "
        "        '2026-11-23T12:00:00+00:00', '2026-11-23T12:00:00+00:00', "
        "        0, 15694)",
        (numero, VELASCO,
         json.dumps([{"idProduto": PAGAMENTO_TECNICO_ID,
                      "valorTotal": pagamento},
                     {"idProduto": KM_DESLOCAMENTO_ID, "valorTotal": km}]),
         json.dumps([{"usuarioId": tecnico, "nomeTecnico": "Franck"}])
         if tecnico else json.dumps([]),
         data_previsao))


@pytest.fixture(autouse=True)
def base():
    """As tabelas que a aba 2 lê, e QUATRO OS em datas diferentes.

    📏 Uma de agosto, uma de outubro (as duas antes do corte), uma EXATAMENTE
    no dia do corte e uma depois. O dia do corte é a borda, e borda é onde erro
    de comparação mora.
    """
    with storage._connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS os_historico (
                numero_os INTEGER PRIMARY KEY, cliente_id INTEGER,
                data_previsao TEXT, atualizado_em TEXT, visto_em TEXT,
                excluida INTEGER DEFAULT 0, materiais_json TEXT,
                situacao_id INTEGER, tecnicos_json TEXT, termo TEXT,
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                harmonit_id INTEGER PRIMARY KEY, cnpjcpf TEXT, criado_em TEXT)
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
                  "clientes", "contrato_cliente", "tipos_os", "config",
                  "pagamento_artefato", "pagamento_lote", "pagamento_evento"):
            conn.execute("DELETE FROM %s" % t)
        conn.execute(
            "INSERT INTO tecnicos (tecnico_id, nome, excluido, atualizado_em) "
            "VALUES (?, 'Franck', 0, '2026-11-18')", (FRANCK,))
        _os(conn, 990100, "05/08/2026 09:00:00")   # antes
        _os(conn, 990200, "20/10/2026 09:00:00")   # antes
        _os(conn, 990300, "16/11/2026 09:00:00")   # NO DIA do corte
        _os(conn, 990400, "18/11/2026 09:00:00")   # depois
        conn.commit()
    yield


def _artefatos():
    with storage._connect() as conn:
        return sorted(r[0] for r in conn.execute(
            "SELECT numero_os FROM pagamento_artefato").fetchall())


def _na_movimentacao(quadro):
    col = next(c for c in quadro["colunas"] if c["chave"] == "movimentacao")
    return sorted(a["numero_os"] for card in col["cards"]
                  for a in card["artefatos"])


# ===========================================================================
class TestOPadrao:
    """🔵 O número é DELE: 16/11/2026."""

    def test_o_padrao_e_16_11(self):
        assert pagamento_servico.desde() == PADRAO

    def test_valor_torto_no_config_cai_no_padrao_e_nao_derruba(self):
        """⚠️ `desde` inválido não pode esvaziar a aba 2 nem estourar."""
        with storage._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO config (chave, valor, atualizado_em) "
                "VALUES (?, 'ontem', '2026-11-23')",
                (pagamento_servico.CHAVE_DESDE,))
            conn.commit()
        assert pagamento_servico.desde() == PADRAO

    def test_a_data_da_OPERACAO_nao_e_tocada(self):
        """🚨 D6: *"não mexa na data do OP"*. Chaves diferentes, bancos
        diferentes — e esta trava prende o NOME, que é o que colidiria."""
        assert pagamento_servico.CHAVE_DESDE == "pagamento_servico_desde"
        assert pagamento_servico.CHAVE_DESDE != "painel_operacao_desde"


# ===========================================================================
class TestAVarredura:
    """🔵 *"o artefato anterior à data nem nasce"*."""

    def test_nao_cria_artefato_anterior_a_data(self):
        r = pagamento_servico.varrer(horas=None)
        assert r["desde"] == PADRAO
        assert r["antes_da_data"] == 2          # 05/08 e 20/10
        assert _artefatos() == [990300, 990400]

    def test_o_DIA_do_corte_ENTRA(self):
        """🚨 A borda é INCLUSIVA: 16/11 não é anterior a 16/11."""
        pagamento_servico.varrer(horas=None)
        assert 990300 in _artefatos()

    def test_OS_sem_data_ENTRA(self):
        """🚨 **DECISÃO MINHA, DECLARADA.** A OS sem `data_previsao` não pode
        ser PROVADA anterior ao corte, e descartá-la sumiria com dinheiro em
        silêncio. Ela entra, e o card já diz "sem data".
        📏 Medido em 23/11: 0 das 79 estão assim — a trava é para o dia em que
        houver uma."""
        with storage._connect() as conn:
            _os(conn, 990500, None)
            conn.commit()
        pagamento_servico.varrer(horas=None)
        assert 990500 in _artefatos()

    def test_mudar_a_data_muda_o_que_a_varredura_cria(self):
        pagamento_servico.definir_desde("2026-08-01", por="zz teste")
        r = pagamento_servico.varrer(horas=None)
        assert r["antes_da_data"] == 0
        assert _artefatos() == [990100, 990200, 990300, 990400]


# ===========================================================================
class TestOQuadro:
    """🔵 D7: **esconder, não apagar.**"""

    def test_esconde_na_movimentacao_e_NAO_apaga_do_banco(self):
        """🚨 A linha que separa esconder de apagar: a tela não mostra, o
        banco continua tendo. Trocando a data, voltam."""
        pagamento_servico.definir_desde("2026-08-01", por="zz teste")
        pagamento_servico.varrer(horas=None)
        assert _artefatos() == [990100, 990200, 990300, 990400]

        pagamento_servico.definir_desde(PADRAO, por="zz teste")
        q = pagamento_servico.quadro()
        assert q["desde"] == PADRAO
        assert q["escondidos_pela_data"] == 2
        assert _na_movimentacao(q) == [990300, 990400]
        # 🚨 E NADA SAIU DO BANCO.
        assert _artefatos() == [990100, 990200, 990300, 990400]

    def test_voltar_a_data_TRAZ_os_escondidos_de_volta(self):
        pagamento_servico.definir_desde("2026-08-01", por="zz teste")
        pagamento_servico.varrer(horas=None)
        pagamento_servico.definir_desde(PADRAO, por="zz teste")
        assert _na_movimentacao(pagamento_servico.quadro()) == [990300, 990400]
        pagamento_servico.definir_desde("2026-08-01", por="zz teste")
        q = pagamento_servico.quadro()
        assert q["escondidos_pela_data"] == 0
        assert _na_movimentacao(q) == [990100, 990200, 990300, 990400]

    def test_LOTE_JA_FORMADO_nao_e_peneirado_pela_data(self):
        """🚨 **A REGRA QUE A PRÓPRIA TELA JÁ ESCREVEU** sobre o filtro de
        período: *"o lote já foi fechado, e peneirá-lo por data esconderia
        parte de um pagamento que vai sair inteiro"*. Esconder metade de um
        lote faria o total da tela discordar do arquivo do Procfy."""
        pagamento_servico.definir_desde("2026-08-01", por="zz teste")
        pagamento_servico.varrer(horas=None)
        with storage._connect() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM pagamento_artefato "
                " WHERE numero_os IN (990100, 990200)").fetchall()]
            conn.commit()
        # ⚠️ `preparar` lê **`id`**, não `artefato_id`: medido em 23/11 no
        # docstring dele -- `{"id": .., "orcamento_numero": .. | None}`. E ele
        # não devolve `ok`: devolve `preparados` e `recusados`.
        r = pagamento_servico.preparar([{"id": i} for i in ids],
                                       por="zz teste")
        assert r["preparados"] == 2, r
        assert r["recusados"] == [], r

        # Agora aperta a data: os dois são de agosto e outubro, antes do corte.
        pagamento_servico.definir_desde(PADRAO, por="zz teste")
        q = pagamento_servico.quadro()
        fora = [a["numero_os"] for c in q["colunas"]
                if c["chave"] != "movimentacao"
                for card in c["cards"] for a in card["artefatos"]]
        assert sorted(fora) == [990100, 990200], (
            "lote formado NAO se peneira por data")
        assert q["escondidos_pela_data"] == 0

    def test_o_quadro_DIZ_a_data_e_quantos_escondeu(self):
        """🚨 `M12`: contagem que cai sem explicação é a tela mentindo por
        omissão. O servidor manda os dois números; a tela os diz."""
        pagamento_servico.definir_desde("2026-08-01", por="zz teste")
        pagamento_servico.varrer(horas=None)
        pagamento_servico.definir_desde(PADRAO, por="zz teste")
        q = pagamento_servico.quadro()
        assert q["desde"] == PADRAO
        assert q["escondidos_pela_data"] == 2


# ===========================================================================
class TestARotaHTTP:
    """🚨 Rota nova pede teste HTTP."""

    def test_sem_a_chave_nao_responde(self, cliente):
        """🚨 **422, e não 401.** A `X-Ponte-Key` é um header OBRIGATÓRIO do
        Pydantic, então quem recusa é a validação, antes de qualquer código
        nosso. ⚠️ Eu havia escrito 401/403 aqui e o teste reprovou — a forma
        certa é a que a trava da casa já afirmava desde 18/11
        (`teste_pagamento_rotas.py::test_toda_rota_exige_a_chave`)."""
        r = cliente.post("/api/pagamento/desde", json={"desde": "2026-11-16"})
        assert r.status_code == 422, r.text

    def test_com_a_chave_ERRADA_nao_grava(self, cliente):
        """⚠️ Header presente e errado é outro caminho: aí quem recusa é o
        `verificar_segredo`, e o que importa é que NADA foi gravado."""
        r = cliente.post("/api/pagamento/desde", json={"desde": "2026-08-01"},
                         headers={"X-Ponte-Key": "zz-errada"})
        assert r.status_code != 200, r.text
        assert pagamento_servico.desde() == PADRAO

    def test_grava_e_o_quadro_passa_a_dizer(self, cliente):
        r = cliente.post("/api/pagamento/desde",
                         json={"desde": "2026-08-01", "por": "zz teste"},
                         headers=CAB)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "desde": "2026-08-01"}
        q = cliente.get("/api/pagamento/quadro", headers=CAB).json()
        assert q["desde"] == "2026-08-01"

    def test_data_torta_e_RECUSA_COM_MOTIVO_e_200(self, cliente):
        """🚨 A régua desta ponte: *"toda escrita devolve `ok` + `motivo`,
        nunca estoura"*. ⚠️ E o `min_length` do Pydantic pega o tamanho antes,
        então a recusa com motivo é para o que TEM 10 caracteres e não é data."""
        r = cliente.post("/api/pagamento/desde",
                         json={"desde": "16/11/2026", "por": "zz"},
                         headers=CAB)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is False
        assert "aaaa-mm-dd" in r.json()["motivo"]
        # E NADA foi gravado.
        assert pagamento_servico.desde() == PADRAO

    def test_data_curta_demais_e_422_do_pydantic(self, cliente):
        r = cliente.post("/api/pagamento/desde", json={"desde": "2026-11"},
                         headers=CAB)
        assert r.status_code == 422, r.text
        assert pagamento_servico.desde() == PADRAO

    def test_a_gravacao_deixa_EVENTO(self, cliente):
        """🔵 *"deve ter o log de quem faz o que SEMPRE"*."""
        cliente.post("/api/pagamento/desde",
                     json={"desde": "2026-10-01", "por": "Iago"}, headers=CAB)
        with storage._connect() as conn:
            linha = conn.execute(
                "SELECT acao, para, por FROM pagamento_evento "
                " WHERE acao = 'definir_desde' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        assert linha == ("definir_desde", "2026-10-01", "Iago")
