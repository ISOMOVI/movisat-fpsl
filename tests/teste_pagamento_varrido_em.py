# -*- coding: utf-8 -*-
"""QUANDO A ABA 2 FOI VARRIDA — a linha que mata a mentira da tela (`M12`).

🚨 **POR QUE ISTO EXISTE.** A tela diz *"serviço a partir de 16/11/2026"* e não
diz **quando** olhou. Com o cron das 05:10, um quadro de seis dias atrás tem a
mesma cara de um varrido hoje — e quadro velho com cara de novo é a tela
mentindo por omissão, que é o defeito que o `M12` nomeia.

🚨 **O VERMELHO VEM ANTES DO VERDE** (`M17`, linha 1): quando este arquivo
nasceu, `varrido_em` não existia em lugar nenhum do projeto — as quatro travas
abaixo falhavam com `KeyError`.

🚨 **BANCO TEMPORÁRIO, apontado ANTES de qualquer import do pacote.** Medido em
19/11: a suíte falava com o banco de PRODUÇÃO. Aqui se grava `config` e
`pagamento_artefato`, então o banco é descartável e é a primeira coisa do
arquivo — mesma régua do `teste_pagamento_desde.py`.

🚨 **E POR HTTP, não só por função** (`feedback_rota_nova_pede_teste_http`): o
campo tem de **atravessar a ponte**, porque quem o desenha é o MoviZap. Trava de
função não mede o que a rota serializa.
"""
import json
import pathlib
import sys
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TMP = tempfile.mkdtemp(prefix="pagamento_varrido_")
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
    """As tabelas que a aba 2 lê e UMA OS dentro do corte, com valor."""
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
        conn.execute(
            "INSERT INTO os_historico (numero_os, cliente_id, materiais_json, "
            "  tecnicos_json, termo, data_previsao, atualizado_em, visto_em, "
            "  excluida, situacao_id) "
            "VALUES (?, ?, ?, ?, '8952', '18/11/2026 09:00:00', "
            "        '2026-11-23T12:00:00+00:00', "
            "        '2026-11-23T12:00:00+00:00', 0, 15694)",
            (990400, VELASCO,
             json.dumps([{"idProduto": PAGAMENTO_TECNICO_ID,
                          "valorTotal": 120.0},
                         {"idProduto": KM_DESLOCAMENTO_ID,
                          "valorTotal": 10.0}]),
             json.dumps([{"usuarioId": FRANCK, "nomeTecnico": "Franck"}])))
        conn.commit()
    yield


def _no_config():
    with storage._connect() as conn:
        row = conn.execute(
            "SELECT valor FROM config WHERE chave = ?",
            (pagamento_servico.CHAVE_VARRIDO,)).fetchone()
    return row[0] if row else None


# ===========================================================================
class TestAVarreduraCarimba:

    def test_varrer_grava_o_carimbo_no_config(self):
        """🚨 A varredura é quem sabe que varreu — ninguém mais."""
        assert _no_config() is None
        pagamento_servico.varrer(horas=None)
        gravado = _no_config()
        assert gravado and gravado.startswith("2026-")
        assert "T" in gravado

    def test_o_carimbo_avanca_na_rodada_seguinte(self):
        """⚠️ Carimbo que não avança é o mesmo defeito com outra cara: a
        segunda rodada não cria nada (`ja_existiam`) e **ainda assim** olhou."""
        pagamento_servico.varrer(horas=None)
        primeiro = _no_config()
        resumo = pagamento_servico.varrer(horas=None)
        assert resumo["novos"] == 0 and resumo["ja_existiam"] == 1
        assert _no_config() > primeiro


class TestOQuadroDevolve:

    def test_sem_varredura_o_campo_vem_vazio_e_nao_estoura(self):
        """⚠️ Nunca varrido não é erro: é a tela não exibir a linha."""
        assert pagamento_servico.quadro()["varrido_em"] == ""

    def test_depois_de_varrer_o_quadro_traz_o_mesmo_valor(self):
        pagamento_servico.varrer(horas=None)
        assert pagamento_servico.quadro()["varrido_em"] == _no_config()

    def test_o_campo_atravessa_a_ponte(self, cliente):
        """🚨 Quem desenha é o MoviZap: o campo tem de chegar por HTTP."""
        pagamento_servico.varrer(horas=None)
        resposta = cliente.get("/api/pagamento/quadro", headers=CAB)
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["varrido_em"] == _no_config()
        # 🔵 D6/D7 continuam no mesmo corpo — o campo novo não empurrou nada.
        assert corpo["desde"] == "2026-11-16"
        assert "escondidos_pela_data" in corpo
