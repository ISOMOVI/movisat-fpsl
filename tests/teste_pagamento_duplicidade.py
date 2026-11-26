# -*- coding: utf-8 -*-
"""A MESMA OS DUAS VEZES NO QUADRO — o defeito que ELE achou (25/11).

🔵 Ele, olhando a tela: *"OS 17131 aparece sem tecnico no painel, mas não tem
agendamento no harmonit corretamente?"*

🚨 **O DEFEITO, E ELE É MEU, DE HOJE.** A OS 17131 ficou com **duas** linhas em
`pagamento_artefato`: a de 18/11 com `tecnico_id` NULL e a que a minha varredura
criou em 25/11 11:07 com o Franck (14262). A trava de duplicidade é pelo par
`(numero_os, tecnico_id)` e, no SQLite, **NULL não colide com nada** — então,
quando o cache ganha o técnico depois, a OS nasce de novo.

📏 No Harmonit o agendamento estava certo o tempo todo: `agendamentoId 970805`,
início 18/11 09:00, `usuarioId 14262`, situação 15694.

🚨 **POR QUE DUPLICAR AQUI É GRAVE:** cada linha é dinheiro a pagar. Duas linhas
da mesma OS em dois cards é pagar duas vezes o mesmo serviço.

**A regra que este arquivo prende:**
1. artefato sem técnico que **não andou** (`movimentacao`, sem lote, sem ciente,
   sem comprovante e sem justificativa) **ADOTA** o técnico quando ele aparece;
2. artefato sem técnico que **já andou** não é tocado — e o segundo **não
   nasce**: conta em `conflito`, porque duplicar dinheiro é pior que esperar;
3. e a OS com técnico desde o começo segue com uma linha só.

⚠️ Banco temporário apontado ANTES do import do pacote: este arquivo escreve.
"""
import json
import pathlib
import sys
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TMP = tempfile.mkdtemp(prefix="pagamento_dup_")
DB = pathlib.Path(TMP) / "fpsl_teste.db"

from fpsl_weso import storage  # noqa: E402

storage.DB_PATH = DB

from fpsl_weso.painel import pagamento_tabelas  # noqa: E402
from fpsl_weso.painel.templates_config import (KM_DESLOCAMENTO_ID,  # noqa: E402
                                               PAGAMENTO_TECNICO_ID)
from fpsl_weso.services import pagamento_servico  # noqa: E402

FRANCK = 14262
MOVISAT = 629          # 🚨 NÃO é técnico: é a empresa. Filtro permanente.
OS = 990400


def _materiais(pagamento=120.0, km=10.0):
    return json.dumps([{"idProduto": PAGAMENTO_TECNICO_ID,
                        "valorTotal": pagamento},
                       {"idProduto": KM_DESLOCAMENTO_ID, "valorTotal": km}])


def _sem_tecnico():
    """O json que o cache tinha em 18/11: só a Movisat, que não é técnico."""
    return json.dumps([{"usuarioId": MOVISAT,
                        "nomeTecnico": "MOVISAT SOLUCOES TECNOLOGICAS LTDA."}])


def _com_franck():
    return json.dumps([{"usuarioId": MOVISAT,
                        "nomeTecnico": "MOVISAT SOLUCOES TECNOLOGICAS LTDA."},
                       {"usuarioId": FRANCK, "nomeTecnico": "Franck"}])


@pytest.fixture(autouse=True)
def base():
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
        for t in ("os_historico", "tecnicos", "config", "pagamento_artefato",
                  "pagamento_lote", "pagamento_evento"):
            conn.execute("DELETE FROM %s" % t)
        conn.execute(
            "INSERT INTO tecnicos (tecnico_id, nome, excluido, atualizado_em) "
            "VALUES (?, 'Franck', 0, '2026-11-18')", (FRANCK,))
        # 🚨 A Movisat está no cadastro como EXCLUÍDA, igual à produção.
        conn.execute(
            "INSERT INTO tecnicos (tecnico_id, nome, excluido, atualizado_em) "
            "VALUES (?, 'MOVISAT SOLUCOES TECNOLOGICAS LTDA.', 1, "
            "        '2026-11-18')", (MOVISAT,))
        conn.commit()
    yield


def _por_os(numero=OS):
    with storage._connect() as conn:
        return [dict(zip(("id", "tecnico_id", "tecnico_nome", "coluna",
                          "valor_pagamento", "valor_km"), r))
                for r in conn.execute(
                    "SELECT id, tecnico_id, tecnico_nome, coluna, "
                    "       valor_pagamento, valor_km "
                    "  FROM pagamento_artefato WHERE numero_os = ? "
                    " ORDER BY id", (numero,)).fetchall()]


def _os_no_cache(tecnicos_json, *, data="18/11/2026 09:00:00"):
    with storage._connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO os_historico "
            "  (numero_os, cliente_id, materiais_json, tecnicos_json, termo, "
            "   data_previsao, atualizado_em, visto_em, excluida, situacao_id) "
            "VALUES (?, 998063, ?, ?, '8952', ?, "
            "        '2026-11-23T12:00:00+00:00', "
            "        '2026-11-23T12:00:00+00:00', 0, 15694)",
            (OS, _materiais(), tecnicos_json, data))
        conn.commit()


# ===========================================================================
class TestOTecnicoQueApareceDepois:
    """O caso da OS 17131, reproduzido."""

    def test_a_OS_NAO_nasce_duas_vezes(self):
        """🚨 O defeito, em duas rodadas: sem técnico, depois com."""
        _os_no_cache(_sem_tecnico())
        pagamento_servico.varrer(horas=None)
        linhas = _por_os()
        assert len(linhas) == 1 and linhas[0]["tecnico_id"] is None

        _os_no_cache(_com_franck())
        resumo = pagamento_servico.varrer(horas=None)

        linhas = _por_os()
        assert len(linhas) == 1, (
            "a mesma OS nasceu de novo quando o técnico apareceu — duas "
            "linhas é pagar duas vezes o mesmo serviço")
        assert linhas[0]["tecnico_id"] == FRANCK
        assert linhas[0]["tecnico_nome"] == "Franck"
        # O resumo DIZ que adotou: rodada que muda dado e se declara "0 novos"
        # esconde o que fez.
        assert resumo["adotados"] == 1
        assert resumo["novos"] == 0

    def test_a_adocao_mantem_o_MESMO_id(self):
        """⚠️ O id e os eventos de antes se preservam: adotar é a linha
        existente passar a ter dono, não uma linha nova."""
        _os_no_cache(_sem_tecnico())
        pagamento_servico.varrer(horas=None)
        antes = _por_os()[0]["id"]
        _os_no_cache(_com_franck())
        pagamento_servico.varrer(horas=None)
        assert _por_os()[0]["id"] == antes

    def test_a_terceira_rodada_nao_mexe_em_nada(self):
        _os_no_cache(_sem_tecnico())
        pagamento_servico.varrer(horas=None)
        _os_no_cache(_com_franck())
        pagamento_servico.varrer(horas=None)
        resumo = pagamento_servico.varrer(horas=None)
        assert resumo["adotados"] == 0
        assert resumo["ja_existiam"] == 1
        assert len(_por_os()) == 1


class TestArtefatoQueJaAndou:
    """🚨 O que já andou NÃO se toca — e o segundo não nasce."""

    def _fazer_andar(self):
        with storage._connect() as conn:
            conn.execute(
                "UPDATE pagamento_artefato SET coluna = 'validacao', "
                "       lote_id = 7, ciente_em = '2026-11-20T10:00:00+00:00' "
                " WHERE numero_os = ?", (OS,))
            conn.commit()

    def test_nao_adota_e_NAO_cria_o_segundo(self):
        _os_no_cache(_sem_tecnico())
        pagamento_servico.varrer(horas=None)
        self._fazer_andar()
        _os_no_cache(_com_franck())
        resumo = pagamento_servico.varrer(horas=None)

        linhas = _por_os()
        assert len(linhas) == 1, "criou o segundo artefato de uma OS que andou"
        # Não foi tocado: segue sem técnico, no lote onde estava.
        assert linhas[0]["tecnico_id"] is None
        assert linhas[0]["coluna"] == "validacao"
        # 🚨 E o resumo NOMEIA o caso, para alguém poder resolver à mão.
        assert resumo["conflito"] == 1
        assert resumo["adotados"] == 0
        assert resumo["novos"] == 0


class TestOQueJaTinhaTecnico:
    def test_segue_com_uma_linha_so(self):
        _os_no_cache(_com_franck())
        pagamento_servico.varrer(horas=None)
        pagamento_servico.varrer(horas=None)
        linhas = _por_os()
        assert len(linhas) == 1
        assert linhas[0]["tecnico_id"] == FRANCK
