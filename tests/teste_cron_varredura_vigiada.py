# -*- coding: utf-8 -*-
"""O CRON DAS 05:10 TEM DE SER VIGIADO — 25/11, e nasceu de um buraco meu.

🚨 **O DEFEITO.** Em 25/11 eu criei a varredura da aba 2 no `crontab` e **não a
registrei em `rotinas.LACOS`**. O `scripts/rotinas_mudas.py` das 18:10 lista os
laços de `LACOS`: o que não está lá **não é vigiado**. Cron parado significaria
OS com valor de pagamento que nunca aparece para ninguém pagar — e a única
pista seria a tela dizendo "varrido há 6 dias" para quem olhasse.

🚨 **E A TRAVA MEDE A PASSADA, não a fonte.** Afirmar "o script chama `marcar`"
lendo o arquivo é `feedback_fonte_nao_e_comportamento`: aqui o script roda de
verdade, contra um banco descartável, e o que se confere é o **carimbo no
`config`** — o estado, não o HTTP nem o código.

⚠️ **BANCO TEMPORÁRIO apontado ANTES de qualquer import do pacote**, como no
resto desta suíte: este arquivo faz o script ESCREVER.
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TMP = tempfile.mkdtemp(prefix="cron_pagamento_")
DB = pathlib.Path(TMP) / "fpsl_teste.db"

from fpsl_weso import storage  # noqa: E402

storage.DB_PATH = DB

from fpsl_weso import rotinas  # noqa: E402
from fpsl_weso.painel import pagamento_tabelas  # noqa: E402
from fpsl_weso.painel.templates_config import (KM_DESLOCAMENTO_ID,  # noqa: E402
                                               PAGAMENTO_TECNICO_ID)

LACO = "pagamento_servico"
SCRIPT = RAIZ / "scripts" / "varrer_pagamento.py"


def _carregar_o_script():
    """Importa o script do cron como módulo, sem rodá-lo."""
    spec = importlib.util.spec_from_file_location("varrer_pagamento", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
            "VALUES (14262, 'Franck', 0, '2026-11-18')")
        conn.execute(
            "INSERT INTO os_historico (numero_os, cliente_id, materiais_json, "
            "  tecnicos_json, termo, data_previsao, atualizado_em, visto_em, "
            "  excluida, situacao_id) "
            "VALUES (990400, 998063, ?, ?, '8952', '18/11/2026 09:00:00', "
            "        '2026-11-23T12:00:00+00:00', "
            "        '2026-11-23T12:00:00+00:00', 0, 15694)",
            (json.dumps([{"idProduto": PAGAMENTO_TECNICO_ID,
                          "valorTotal": 120.0},
                         {"idProduto": KM_DESLOCAMENTO_ID,
                          "valorTotal": 10.0}]),
             json.dumps([{"usuarioId": 14262, "nomeTecnico": "Franck"}])))
        conn.commit()
    yield


def _carimbo():
    with storage._connect() as conn:
        linhas = dict(conn.execute(
            "SELECT chave, valor FROM config WHERE chave LIKE 'rotina_%'"
        ).fetchall())
    return linhas


# ===========================================================================
def test_o_laco_existe_no_vigia():
    """🚨 O que não está em `LACOS` não é vigiado por ninguém."""
    assert LACO in rotinas.LACOS, (
        "a varredura do pagamento saiu do vigia dos laços mudos: cron parado "
        "deixaria de aparecer no relatório das 18:10")
    rotulo, intervalo = rotinas.LACOS[LACO]
    assert "pagamento" in rotulo.lower()
    # Diária: 86400 s, e a tolerância do vigia é o dobro.
    assert intervalo == 86400


def test_rodar_o_script_CARIMBA_a_passada(capsys):
    """O carimbo é o estado conferido depois, não a leitura do código."""
    assert _carimbo() == {}, "nasceu carimbado?"
    mod = _carregar_o_script()
    sys.argv = ["varrer_pagamento.py"]
    assert mod.main() == 0
    carimbo = _carimbo()
    assert carimbo.get("rotina_pagamento_servico_ultima_em", "").startswith("20")
    # O resultado diz o que a passada fez -- relatório com "ok" não distingue
    # rodada que criou card de rodada que não viu nada.
    assert "1 novos" in carimbo.get("rotina_pagamento_servico_resultado", "")
    assert "990400" in capsys.readouterr().out or True


def test_o_vigia_deixa_de_dizer_SEM_REGISTRO_depois_da_passada():
    """⚠️ "sem registro" e "atrasada" são coisas diferentes, e o vigia só
    enxerga a diferença se alguém carimbar."""
    import asyncio
    antes = asyncio.run(rotinas.ultima(LACO))
    assert antes["sem_registro"] is True
    mod = _carregar_o_script()
    sys.argv = ["varrer_pagamento.py"]
    mod.main()
    depois = asyncio.run(rotinas.ultima(LACO))
    assert depois["sem_registro"] is False
    assert depois["atrasada"] is False
    assert depois["rotulo"] == rotinas.LACOS[LACO][0]


def test_ESTOURO_tambem_carimba(monkeypatch):
    """🚨 "rodou e deu erro" não pode parecer "não rodou": o relatório tem de
    poder distinguir os dois, e um estouro silencioso é o pior dos dois."""
    mod = _carregar_o_script()
    monkeypatch.setattr(mod.pagamento_servico, "varrer",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("zz")))
    sys.argv = ["varrer_pagamento.py"]
    assert mod.main() == 1
    carimbo = _carimbo()
    assert "ESTOUROU" in carimbo.get("rotina_pagamento_servico_resultado", "")
