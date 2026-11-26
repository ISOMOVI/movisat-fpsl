# -*- coding: utf-8 -*-
r"""A CORREÇÃO DA SITUAÇÃO NO DATASCOPE — passo 5, 25/11.

🔵 Ele: *"sim, aprovado - que tem como base as etapas de validacao que permitem
o card do pagamento tecnico avancar"*.

📏 MEDIDO ANTES DE ESCREVER, e isto desenhou a funcao:
  · o `change_state` **existe, foi testado e esta documentado** --
    `POST /api/external/change_state` com `form_name`, `form_code` e
    `form_state_id`; funciona nos dois sentidos, sem trava de prazo;
  · `74341` = *"Aprovado analise tecnica"* (tabela do `30_Painel_Financeiro`);
  · 🚨 o nosso CACHE **NAO TEM o `form_code`** (guarda `form_answer_id`,
    `numero_os`, `form_state`, `updated_at`), e sem o `code` nao da para
    escrever. Medi uma resposta real do `/v5/answers`: ela **traz** `code` e
    `form_name`. Entao a escrita LE a resposta antes, e le fresco.

🚨 **DISPARA WEBHOOK DELES E PUSH PARA O TECNICO.** Esta documentado e medido.
Por isso: interruptor **nasce desligado**, a funcao recusa quando ele esta
desligado, e e idempotente -- aprovar o que ja esta aprovado nao escreve nada
e nao manda push de novo.

🚨 O DUBLE FICA NA BORDA: o cliente do DataScope (`get` e `post`). A regra --
o estado de origem, a idempotencia, o interruptor, a trilha, o estado gravado
-- roda de verdade, contra um SQLite de teste.

Roda:  venv/bin/python -m pytest tests/teste_datascope_aprovar.py
"""
import pathlib
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.services import pagamento_servico as ps  # noqa: E402

APROVADO = "Aprovado análise técnica"
ESTADO_ID = 74341


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um fpsl.db só deste teste, com um artefato em validação."""
    import sqlite3

    from fpsl_weso.painel import pagamento_tabelas

    caminho = tmp_path / "fpsl.db"

    def conectar():
        conn = sqlite3.connect(caminho)
        return conn

    monkeypatch.setattr(ps.storage, "_connect", conectar)
    conn = conectar()
    pagamento_tabelas.criar(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS datascope_respostas ("
        " form_answer_id INTEGER PRIMARY KEY, numero_os INTEGER,"
        " form_state TEXT, updated_at TEXT, sincronizado_em TEXT)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY,"
        " valor TEXT, atualizado_em TEXT)")
    conn.execute(
        "INSERT INTO pagamento_artefato (numero_os, tecnico_id, tecnico_nome,"
        " coluna, valor_pagamento, valor_km, data_os, datascope_form_state,"
        " criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (17120, 14262, "Franck", "validacao", 100.0, 0.0, "18/11/2026 09:00:00",
         "Finalizado", ps._agora(), ps._agora()))
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def datascope(monkeypatch):
    """A borda: o cliente do DataScope."""
    estado = {"respostas": [{"code": 356430079894384, "form_name": "Serviços Técnicos",
                             "form_answer_id": 33062063, "form_state": "Finalizado",
                             "Nº da O.S.": "17120"}],
              "posts": [], "erro": None}

    async def get(path, params=None):
        return list(estado["respostas"])

    async def post(path, dados=None):
        if estado["erro"]:
            raise estado["erro"]
        estado["posts"].append((path, dict(dados or {})))
        return {"status": "ok"}

    monkeypatch.setattr(ps, "datascope_get", get, raising=False)
    monkeypatch.setattr(ps, "datascope_post", post, raising=False)
    return estado


def _ligar(banco, ligado=True):
    import sqlite3
    conn = sqlite3.connect(banco)
    conn.execute("INSERT OR REPLACE INTO config (chave, valor, atualizado_em)"
                 " VALUES (?,?,?)",
                 (ps.CHAVE_DATASCOPE_ESCRITA, "true" if ligado else "false",
                  ps._agora()))
    conn.commit()
    conn.close()


def _artefato(banco):
    import sqlite3
    conn = sqlite3.connect(banco)
    linha = conn.execute(
        "SELECT id, coluna, datascope_form_state FROM pagamento_artefato"
    ).fetchone()
    conn.close()
    return linha


def _eventos(banco):
    import sqlite3
    conn = sqlite3.connect(banco)
    linhas = conn.execute(
        "SELECT acao, de, para, por FROM pagamento_evento ORDER BY id").fetchall()
    conn.close()
    return linhas


# ---------------------------------------------------------- o interruptor ----
def teste_DESLIGADO_nao_escreve_nada(banco, datascope):
    """🚨 Nasce desligado, e é a regra desta frente: o interruptor fica na tela
    dela. Escrever em sistema de terceiro não começa ligado."""
    aid = _artefato(banco)[0]
    r = ps.aprovar_no_datascope(aid, por="Iago")
    assert r["ok"] is False
    assert "desligad" in (r.get("motivo") or "").lower(), r
    assert datascope["posts"] == []
    assert _eventos(banco) == []


def teste_o_interruptor_e_LIDO_do_config(banco, datascope):
    _ligar(banco, True)
    assert ps.escrita_no_datascope_ligada() is True
    _ligar(banco, False)
    assert ps.escrita_no_datascope_ligada() is False


# ------------------------------------------------------------- a escrita -----
def teste_LIGADO_escreve_com_o_payload_da_regra(banco, datascope):
    _ligar(banco)
    aid = _artefato(banco)[0]
    r = ps.aprovar_no_datascope(aid, por="Iago")
    assert r["ok"] is True, r
    assert len(datascope["posts"]) == 1
    caminho, dados = datascope["posts"][0]
    assert "change_state" in caminho
    # 📏 Os três campos que a API exige, com o id medido na tabela do doc.
    assert dados["form_name"] == "Serviços Técnicos"
    assert str(dados["form_code"]) == "356430079894384"
    assert int(dados["form_state_id"]) == ESTADO_ID


def teste_o_ESTADO_fica_gravado_no_artefato(banco, datascope):
    _ligar(banco)
    aid = _artefato(banco)[0]
    ps.aprovar_no_datascope(aid, por="Iago")
    assert _artefato(banco)[2] == APROVADO


def teste_a_TRILHA_diz_de_onde_para_onde_e_quem(banco, datascope):
    _ligar(banco)
    aid = _artefato(banco)[0]
    ps.aprovar_no_datascope(aid, por="Iago")
    eventos = _eventos(banco)
    assert len(eventos) == 1
    acao, de, para, por = eventos[0]
    assert acao == "datascope_aprovar"
    assert de == "Finalizado"
    assert para == APROVADO
    assert por == "Iago"


# ---------------------------------------------------------- as recusas -------
def teste_IDEMPOTENTE_nao_manda_push_de_novo(banco, datascope):
    """🚨 A chamada manda PUSH para o técnico. Aprovar o que já está aprovado
    não pode escrever outra vez -- seria notificar sem fato novo."""
    _ligar(banco)
    aid = _artefato(banco)[0]
    ps.aprovar_no_datascope(aid, por="Iago")
    datascope["respostas"][0]["form_state"] = APROVADO
    r = ps.aprovar_no_datascope(aid, por="Iago")
    assert r["ok"] is True
    assert r.get("ja_estava") is True, r
    assert len(datascope["posts"]) == 1, "escreveu duas vezes"


def teste_artefato_FORA_da_validacao_e_recusado(banco, datascope):
    """🔵 *"tem como base as etapas de validacao que permitem o card avancar"*:
    a ação é da Validação, não de qualquer coluna."""
    _ligar(banco)
    import sqlite3
    conn = sqlite3.connect(banco)
    conn.execute("UPDATE pagamento_artefato SET coluna = 'movimentacao'")
    conn.commit()
    conn.close()
    aid = _artefato(banco)[0]
    r = ps.aprovar_no_datascope(aid, por="Iago")
    assert r["ok"] is False
    assert datascope["posts"] == []


def teste_sem_resposta_no_datascope_NAO_inventa_code(banco, datascope):
    """⚠️ Sem resposta para a OS não há `code`, e escrever sem ele seria pedir
    ao DataScope para mudar o estado de outra coisa."""
    _ligar(banco)
    datascope["respostas"] = []
    aid = _artefato(banco)[0]
    r = ps.aprovar_no_datascope(aid, por="Iago")
    assert r["ok"] is False
    assert "datascope" in (r.get("motivo") or "").lower()
    assert datascope["posts"] == []


def teste_erro_do_datascope_NAO_grava_estado_nem_trilha_de_sucesso(banco,
                                                                   datascope):
    """🚨 `ok` do nosso lado não é prova: se o POST falhar, o artefato não pode
    ficar dizendo que foi aprovado."""
    _ligar(banco)
    datascope["erro"] = RuntimeError("502 do DataScope")
    aid = _artefato(banco)[0]
    r = ps.aprovar_no_datascope(aid, por="Iago")
    assert r["ok"] is False
    assert _artefato(banco)[2] == "Finalizado", "o estado antigo fica"
    for acao, _de, _para, _por in _eventos(banco):
        assert acao != "datascope_aprovar"
