# -*- coding: utf-8 -*-
"""OS DADOS DA OS NO ARTEFATO DE PAGAMENTO — 19/11.

🔵 Dele: *"faltam várias coisas e melhorias de UX/UI principalmente em relação
a funcionalidade e estilos dos cards -- como a aba1 apresenta"*.

🚨 **O QUE FALTAVA ERA DADO, NÃO ESTILO.** O card da aba 1 mostra cliente, tipo
da OS e status; o artefato da aba 2 tinha OS, termo e valor. Nenhum estilo
conserta um campo que o servidor não manda — é o mesmo defeito de omissão do
card cru de 18/11, um degrau abaixo.

🚨 **E ESTE ARQUIVO EXISTE POR UM MOTIVO ESPECÍFICO:** o enriquecimento é um
`LEFT JOIN`, e `LEFT JOIN` com tabela **vazia** devolve nulo sem reclamar. Se a
única prova fosse a suíte de sempre — que roda com `clientes`,
`contrato_cliente` e `tipos_os` vazias — um JOIN pela coluna ERRADA passaria
verde para sempre. 📏 O caminho do nome dá três saltos, e é fácil errar:

    os_historico.cliente_id -> clientes.harmonit_id -> clientes.cnpjcpf
                            -> contrato_cliente.cnpj -> contrato_cliente.nome

⚠️ **Medido em produção em 19/11**, nos 79 artefatos: 79 com tipo, **65 com
nome de cliente**, 63 com termo. Os 14 sem nome NÃO ficam em branco na tela —
ela diz *"cliente N, fora do nosso cadastro"*, a frase do card da aba 1.

Roda:  venv/bin/python -m pytest tests/teste_pagamento_dados_da_os.py
"""
import json
import pathlib
import sys
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# 🚨 BANCO TEMPORÁRIO, apontado ANTES de qualquer import do pacote — o mesmo
# padrão do `teste_pagamento_servico`. ⚠️ `Path`, não texto: o
# `storage._connect` faz `DB_PATH.parent.mkdir(...)`.
TMP = tempfile.mkdtemp(prefix="pagamento_os_")
DB = pathlib.Path(TMP) / "fpsl_teste.db"

from fpsl_weso import storage  # noqa: E402

storage.DB_PATH = DB

from fpsl_weso.painel import pagamento_tabelas  # noqa: E402
from fpsl_weso.painel.templates_config import (KM_DESLOCAMENTO_ID,  # noqa: E402
                                               PAGAMENTO_TECNICO_ID)
from fpsl_weso.services import pagamento_servico  # noqa: E402

FRANCK = 14262
# 📏 A OS 16689 e o cliente 249119 são reais no quadro de 19/11; os valores
# aqui são de teste.
OS_COM_CLIENTE = 16689
CLIENTE_COM_NOME = 249119
CNPJ = "11222333000181"
NOME_DO_CLIENTE = "SWM - COMERCIO E LOCACAO DE IMOVEIS LTDA"
# ⚠️ Este cliente existe na OS e NÃO está no nosso cadastro: são os 14 de 79.
OS_SEM_CLIENTE = 16705
CLIENTE_SEM_NOME = 1015624
TIPO_CONTRATO = 7


def _materiais(pagamento=0.0, km=0.0):
    itens = []
    if pagamento:
        itens.append({"produtoId": PAGAMENTO_TECNICO_ID,
                      "valorTotal": pagamento})
    if km:
        itens.append({"produtoId": KM_DESLOCAMENTO_ID, "valorTotal": km})
    return json.dumps(itens)


def _tecnicos(*ids):
    return json.dumps([{"usuarioId": i, "nomeTecnico": f"Tec {i}"}
                       for i in ids])


@pytest.fixture(autouse=True)
def base():
    """As seis tabelas que este caminho toca, e a limpeza das seis.

    ⚠️ LIMPA NO COMEÇO, e não no fim: teste que deixa lixo passa na primeira
    rodada e reprova na segunda, e foi o que a suíte do FPSL fazia com a
    `operacoes_espera` até 18/11.
    """
    with storage._connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS os_historico (
                numero_os INTEGER PRIMARY KEY, tipo INTEGER, problema INTEGER,
                produto_id INTEGER, cliente_id INTEGER, data_previsao TEXT,
                oficinas_json TEXT, n_oficinas INTEGER, visto_em TEXT,
                atualizado_em TEXT, excluida INTEGER DEFAULT 0,
                status INTEGER, status_str TEXT, materiais_json TEXT,
                situacao_id INTEGER, os_id INTEGER, tecnicos_json TEXT,
                prioridade INTEGER, termo TEXT)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tecnicos (
                tecnico_id INTEGER PRIMARY KEY, nome TEXT NOT NULL,
                excluido INTEGER NOT NULL DEFAULT 0, atualizado_em TEXT,
                email TEXT)
        """)
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
        for tabela in ("os_historico", "tecnicos", "clientes",
                       "contrato_cliente", "tipos_os", "pagamento_artefato",
                       "pagamento_lote", "pagamento_evento"):
            conn.execute("DELETE FROM " + tabela)

        # A OS com cliente no nosso cadastro, e a sem.
        conn.execute(
            "INSERT INTO os_historico (numero_os, tipo, cliente_id, "
            "  data_previsao, materiais_json, tecnicos_json, termo, "
            "  status_str, situacao_id, excluida, atualizado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (OS_COM_CLIENTE, TIPO_CONTRATO, CLIENTE_COM_NOME,
             "05/08/2026 08:00:00", _materiais(80.0, 12.5), _tecnicos(FRANCK),
             "8937", "Iniciada", 16490, "2026-11-19T10:00:00"))
        conn.execute(
            "INSERT INTO os_historico (numero_os, tipo, cliente_id, "
            "  data_previsao, materiais_json, tecnicos_json, termo, "
            "  status_str, situacao_id, excluida, atualizado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, 0, ?)",
            (OS_SEM_CLIENTE, TIPO_CONTRATO, CLIENTE_SEM_NOME,
             "10/09/2026 08:00:00", _materiais(60.0), _tecnicos(FRANCK),
             "Iniciada", 1316, "2026-11-19T10:00:00"))

        # 🚨 OS TRÊS SALTOS, montados de verdade: só o primeiro cliente
        # percorre o caminho inteiro até o nome.
        conn.execute("INSERT INTO clientes (harmonit_id, cnpjcpf) "
                     "VALUES (?, ?)", (CLIENTE_COM_NOME, CNPJ))
        conn.execute("INSERT INTO contrato_cliente (cnpj, nome) "
                     "VALUES (?, ?)", (CNPJ, NOME_DO_CLIENTE))
        conn.execute("INSERT INTO tipos_os (tipo_id, nome) VALUES (?, ?)",
                     (TIPO_CONTRATO, "Contrato"))
        conn.commit()
    yield


def _artefatos_da_coluna_1():
    cards = pagamento_servico.quadro()["colunas"][0]["cards"]
    return {a["numero_os"]: a for c in cards for a in c["artefatos"]}


class TestOsDadosDaOsChegamNoArtefato:

    def test_o_NOME_DO_CLIENTE_percorre_os_tres_saltos(self):
        """🚨 A trava que a suíte de sempre NÃO faz: lá as três tabelas estão
        vazias, e `LEFT JOIN` com tabela vazia devolve nulo sem reclamar — um
        JOIN pela coluna errada passaria verde para sempre."""
        pagamento_servico.varrer(horas=None)
        a = _artefatos_da_coluna_1()[OS_COM_CLIENTE]
        assert a["cliente"] == NOME_DO_CLIENTE
        assert a["cliente_id"] == CLIENTE_COM_NOME

    def test_o_TIPO_da_OS_vem_pelo_catalogo(self):
        pagamento_servico.varrer(horas=None)
        assert _artefatos_da_coluna_1()[OS_COM_CLIENTE]["tipo_nome"] == "Contrato"

    def test_o_STATUS_vem_junto(self):
        pagamento_servico.varrer(horas=None)
        assert _artefatos_da_coluna_1()[OS_COM_CLIENTE]["status_str"] == "Iniciada"

    def test_cliente_FORA_DO_CADASTRO_e_nulo_com_o_id_preservado(self):
        """⚠️ São os 14 de 79 medidos. 🚨 NULO É "não medido", e o `cliente_id`
        fica: é com ele que a tela diz *"cliente N, fora do nosso cadastro"*,
        a frase do card da aba 1. Cadeia vazia aqui faria a tela escrever
        *"cliente , fora do nosso cadastro"*."""
        pagamento_servico.varrer(horas=None)
        a = _artefatos_da_coluna_1()[OS_SEM_CLIENTE]
        assert a["cliente"] is None
        assert a["cliente_id"] == CLIENTE_SEM_NOME

    def test_o_artefato_continua_com_tudo_que_ja_tinha(self):
        """⚠️ O enriquecimento ACRESCENTA; ele não pode comer campo nenhum —
        o `update` é sobre o dicionário do artefato."""
        pagamento_servico.varrer(horas=None)
        a = _artefatos_da_coluna_1()[OS_COM_CLIENTE]
        assert a["termo"] == "8937"
        assert a["valor_pagamento"] == 80.0
        assert a["valor_km"] == 12.5
        assert a["data_os"] == "05/08/2026 08:00:00"
        assert a["coluna"] == "movimentacao"

    def test_OS_que_saiu_do_cache_entra_com_os_campos_NULOS(self):
        """🚨 AUSENTE É AUSENTE. O artefato é permanente e a OS pode sumir do
        cache; quando some, os campos da OS vêm nulos — e não como cadeia
        vazia, que a tela não distinguiria de "o ERP respondeu em branco"."""
        pagamento_servico.varrer(horas=None)
        with storage._connect() as conn:
            conn.execute("DELETE FROM os_historico WHERE numero_os = ?",
                         (OS_COM_CLIENTE,))
            conn.commit()
        a = _artefatos_da_coluna_1()[OS_COM_CLIENTE]
        assert a["cliente"] is None
        assert a["cliente_id"] is None
        assert a["tipo_nome"] is None
        assert a["status_str"] is None
        # ⚠️ E o artefato CONTINUA LÁ, com o valor: o dinheiro não some porque
        # o cache esqueceu a OS.
        assert a["valor_pagamento"] == 80.0


class TestOEnriquecimentoNaoCustaUmaConsultaPorArtefato:

    def test_uma_consulta_so_para_o_quadro_inteiro(self):
        """⚠️ O quadro de produção tem 79 artefatos e vai crescer. Uma consulta
        POR ARTEFATO seria 79 idas ao banco a cada abertura da tela — por isso
        o enriquecimento é um `IN (...)` só, e esta trava guarda isso."""
        pagamento_servico.varrer(horas=None)
        fonte = (RAIZ / "fpsl_weso" / "services"
                 / "pagamento_servico.py").read_text(encoding="utf-8")
        trecho = fonte.split("def quadro(")[1].split("\ndef ")[0]
        assert "IN (%s)" in trecho
        assert trecho.count("FROM os_historico") == 1
