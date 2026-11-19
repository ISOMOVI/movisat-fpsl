# -*- coding: utf-8 -*-
"""A varredura de **Serviço dos Técnicos** — 🔵 a aba 2 do Financeiro, 18/11.

🔵 *"Rotina automatizada visita todas as OS das ultimas 24hrs e vai agrupando os
dados. Cards são gerados por técnico automaticamente."*

🚨 BANCO TEMPORÁRIO, apontado ANTES de qualquer import do pacote — o mesmo
padrão do `teste_ponte_rotas_http`. ⚠️ `Path`, não texto: o `storage._connect`
faz `DB_PATH.parent.mkdir(...)`, e com uma string isso estoura.

O que estes testes guardam, e cada número veio do ensaio a seco de 18/11 contra
o cache de produção (633 OS):

  · **79** OS têm valor de pagamento ou de km;
  · **21** delas não têm técnico de verdade -- e **entram**, porque artefato de
    pagamento que some é dinheiro que ninguém cobra nem paga. 🚨 São o funil que
    ele mandou consertar em 11/11 (70 → 16 → 8 OS);
  · **8** técnicos, Franck com 40 OS (R$ 3.430,00 + R$ 933,10);
  · varrer duas vezes **não duplica** nem sobrescreve o que o operador já mexeu.
"""
import json
import pathlib
import sys
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TMP = tempfile.mkdtemp(prefix="pagamento_")
DB = pathlib.Path(TMP) / "fpsl_teste.db"

from fpsl_weso import storage  # noqa: E402

storage.DB_PATH = DB

from fpsl_weso.painel import pagamento_tabelas  # noqa: E402
from fpsl_weso.painel.templates_config import (KM_DESLOCAMENTO_ID,  # noqa: E402
                                               PAGAMENTO_TECNICO_ID)
from fpsl_weso.services import pagamento_servico  # noqa: E402

# 🚨 O CLIENTE DOS TESTES É A VELASCO (998063), E SÓ ELA — regra dele.
VELASCO = 998063
EMPRESA = pagamento_servico.EMPRESA_COMO_TECNICO   # 629, a Movisat
FRANCK = 14262
EXCLUIDO = 643      # "Implantação Fullcontrol", `excluido = 1` no cadastro


def _materiais(pagamento=0.0, km=0.0, outro=0.0):
    itens = []
    if pagamento:
        itens.append({"idProduto": PAGAMENTO_TECNICO_ID,
                      "valorTotal": pagamento})
    if km:
        itens.append({"idProduto": KM_DESLOCAMENTO_ID, "valorTotal": km})
    if outro:
        # ⚠️ Material que NÃO é pagamento nem km: um rastreador, por exemplo.
        itens.append({"idProduto": 141363, "valorTotal": outro})
    return json.dumps(itens)


def _tecnicos(*ids):
    return json.dumps([{"usuarioId": i, "nomeTecnico": f"Tec {i}"}
                       for i in ids])


@pytest.fixture(autouse=True)
def base():
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
        # ⚠️ A `datascope_respostas` existe em produção (o `init_db` a cria) e
        # a coluna 3 a lê. Sem ela aqui, cinco testes morriam com *"no such
        # table"* -- e o defeito seria do banco de teste, não do código.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS datascope_respostas (
                form_answer_id INTEGER PRIMARY KEY, numero_os INTEGER,
                form_state TEXT, updated_at TEXT, sincronizado_em TEXT)
        """)
        pagamento_tabelas.criar(conn)
        conn.execute("DELETE FROM datascope_respostas")
        conn.execute("DELETE FROM os_historico")
        conn.execute("DELETE FROM pagamento_artefato")
        conn.execute("DELETE FROM pagamento_lote")
        conn.execute("DELETE FROM pagamento_evento")
        conn.execute("DELETE FROM tecnicos")
        for tid, nome, fora in ((EMPRESA, "MOVISAT SOLUCOES", 1),
                                (EXCLUIDO, "Implantacao Fullcontrol", 1),
                                (FRANCK, "Franck", 0),
                                (14316, "Pedro Felipe Aguilar", 0)):
            conn.execute(
                "INSERT INTO tecnicos (tecnico_id, nome, excluido, "
                "  atualizado_em) VALUES (?, ?, ?, '2026-11-18')",
                (tid, nome, fora))
        conn.commit()
    yield


def _os(numero, *, materiais, tecnicos="[]", termo=None,
        previsao="18/11/2026 09:00:00", atualizado="2026-11-18T12:00:00+00:00"):
    with storage._connect() as conn:
        conn.execute(
            "INSERT INTO os_historico (numero_os, cliente_id, materiais_json, "
            "  tecnicos_json, termo, data_previsao, atualizado_em, visto_em, "
            "  excluida) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (numero, VELASCO, materiais, tecnicos, termo, previsao,
             atualizado, atualizado))
        conn.commit()


def _artefatos():
    with storage._connect() as conn:
        return conn.execute(
            "SELECT numero_os, tecnico_id, valor_pagamento, valor_km, termo, "
            "       coluna, semaforo, orcamento_numero, data_os "
            "  FROM pagamento_artefato ORDER BY numero_os").fetchall()


class TestOQueEntra:
    def test_OS_com_pagamento_entra(self):
        _os(990001, materiais=_materiais(pagamento=120.0),
            tecnicos=_tecnicos(FRANCK), termo="8952")
        r = pagamento_servico.varrer(horas=None)
        assert r["com_valor"] == 1
        assert r["novos"] == 1
        linha = _artefatos()[0]
        assert linha[0] == 990001
        assert linha[1] == FRANCK
        assert linha[2] == 120.0
        assert linha[4] == "8952"

    def test_OS_com_SO_KM_tambem_entra(self):
        """🔵 *"os valores são dos serviços no corpo da OS do deslocamento E
        pagamento do técnico"* — deslocamento sozinho é serviço pago."""
        _os(990002, materiais=_materiais(km=45.80), tecnicos=_tecnicos(FRANCK))
        r = pagamento_servico.varrer(horas=None)
        assert r["com_valor"] == 1
        assert _artefatos()[0][3] == 45.80

    def test_OS_SEM_nenhum_dos_dois_NAO_entra(self):
        """⚠️ Material que não é pagamento nem km (um rastreador) não é serviço
        a pagar ao técnico."""
        _os(990003, materiais=_materiais(outro=900.0),
            tecnicos=_tecnicos(FRANCK))
        r = pagamento_servico.varrer(horas=None)
        assert r["com_valor"] == 0
        assert _artefatos() == []

    def test_OS_excluida_nao_entra(self):
        _os(990004, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        with storage._connect() as conn:
            conn.execute("UPDATE os_historico SET excluida = 1 "
                         " WHERE numero_os = 990004")
            conn.commit()
        assert pagamento_servico.varrer(horas=None)["com_valor"] == 0


class TestQuemNaoEhTecnico:
    """🚨 Três coisas não são técnico, e as três foram medidas."""

    def test_a_EMPRESA_629_nao_e_tecnico(self):
        """🔵 Regra permanente dele, de 18/11: `usuarioId 629` é a Movisat."""
        _os(990010, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(EMPRESA))
        r = pagamento_servico.varrer(horas=None)
        assert r["sem_tecnico"] == 1
        assert _artefatos()[0][1] is None

    def test_tecnico_EXCLUIDO_do_cadastro_nao_conta(self):
        _os(990011, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(EXCLUIDO))
        assert pagamento_servico.varrer(horas=None)["sem_tecnico"] == 1

    def test_OS_com_ZERO_linha_de_tecnico(self):
        _os(990012, materiais=_materiais(pagamento=100.0), tecnicos="[]")
        assert pagamento_servico.varrer(horas=None)["sem_tecnico"] == 1

    def test_o_PRIMEIRO_tecnico_de_verdade_e_o_que_vale(self):
        """⚠️ A OS pode ter a linha da empresa E a do técnico; o que conta é a
        de verdade, em qualquer ordem."""
        _os(990013, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(EMPRESA, EXCLUIDO, FRANCK))
        pagamento_servico.varrer(horas=None)
        assert _artefatos()[0][1] == FRANCK

    def test_SEM_TECNICO_O_ARTEFATO_AINDA_ENTRA(self):
        """🚨 O TESTE QUE GUARDA O FUNIL. Medido em 18/11: **21** OS com valor
        de pagamento e sem técnico, somando R$ 1.740,00 + R$ 841,90 = **R$
        2.581,90** sem destinatário.

        ⚠️ Descartá-las aqui é que seria o defeito -- é o que o Fechamento
        antigo fazia, e foi por isso que 70 OS viraram 8 (medido em 11/11).
        Artefato de pagamento que some é dinheiro que ninguém cobra nem paga.
        """
        _os(990014, materiais=_materiais(pagamento=100.0, km=20.0),
            tecnicos=_tecnicos(EMPRESA))
        pagamento_servico.varrer(horas=None)
        linhas = _artefatos()
        assert len(linhas) == 1, "a OS sem tecnico foi descartada"
        assert linhas[0][1] is None
        assert linhas[0][2] == 100.0

    def test_o_card_dos_sem_tecnico_DIZ_o_que_e_e_nao_prepara(self):
        """⚠️ Sem técnico não há a quem pagar: o card existe para o dinheiro não
        sair de vista, e não para avançar."""
        _os(990015, materiais=_materiais(pagamento=100.0), tecnicos="[]")
        pagamento_servico.varrer(horas=None)
        card = pagamento_servico.quadro()["colunas"][0]["cards"][0]
        assert card["tecnico_id"] is None
        assert card["tecnico_nome"] == "sem técnico identificado"
        assert card["pode_preparar"] is False


class TestOOrcamento:
    def test_sem_orcamento_ENTRA_e_o_numero_nasce_NULO(self):
        """🔵 Decisão dele: *"Entra, e o card diz que falta"*.

        🚨 **E O NÚMERO NASCE NULO AQUI DE PROPÓSITO.** O orçamento é o do
        MoviZap (🔵 decisão dele) -- a tabela `orcamento`, com numeração nossa,
        que vive na outra base e liga técnico + lista de OS + total + PDF. A
        varredura do FPSL não tem como sabê-lo, e **adivinhar seria inventar
        dado**. Quem o descobre é o MoviZap, cruzando `ordens_os` com a OS, e
        ele o persiste no `preparar`.

        ⚠️ Consequência que ele aceitou sabendo: só **4** orçamentos foram
        emitidos no total, então a maioria vai aparecer sem orçamento. A
        ausência fica à vista em vez de o artefato não existir.
        """
        _os(990020, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        r = pagamento_servico.varrer(horas=None)
        assert r["sem_orcamento"] == 1
        linha = _artefatos()[0]
        assert linha[7] is None          # orcamento_numero

    def test_o_SEMAFORO_tambem_nasce_NULO(self):
        """🚨 Nulo quer dizer *"não avaliado"*, e não verde nem amarelo.

        ⚠️ Eu havia escrito a varredura pintando de amarelo todo artefato sem
        orçamento -- e isso faria DOIS escritores para a mesma coluna, porque o
        MoviZap, que sabe do orçamento, pintaria de novo. Duas verdades na
        mesma célula é o caminho curto para a tela afirmar uma coisa e o banco
        outra. Quem pinta é quem sabe, no momento em que sabe.
        """
        _os(990021, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        pagamento_servico.varrer(horas=None)
        assert _artefatos()[0][6] is None


class TestNaoDuplicaENaoSobrescreve:
    def test_varrer_DUAS_VEZES_nao_duplica(self):
        _os(990030, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        pagamento_servico.varrer(horas=None)
        r2 = pagamento_servico.varrer(horas=None)
        assert r2["novos"] == 0
        assert r2["ja_existiam"] == 1
        assert len(_artefatos()) == 1

    def test_nao_duplica_NEM_SEM_TECNICO(self):
        """🚨 No SQLite, NULL não colide com NULL num UNIQUE — então a trava do
        banco **não** cobre os 21 sem técnico. Quem os cobre é a consulta da
        varredura, e é isto que este teste mede."""
        _os(990031, materiais=_materiais(pagamento=100.0), tecnicos="[]")
        pagamento_servico.varrer(horas=None)
        pagamento_servico.varrer(horas=None)
        assert len(_artefatos()) == 1

    def test_NAO_SOBRESCREVE_o_que_o_operador_mexeu(self):
        """🚨 O operador pode já ter dado ciente, anexado comprovante ou
        devolvido com justificativa. A varredura da noite seguinte não pode
        apagar isso — e apagaria, se ela atualizasse em vez de pular."""
        _os(990032, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        pagamento_servico.varrer(horas=None)
        with storage._connect() as conn:
            conn.execute(
                "UPDATE pagamento_artefato SET coluna = 'validacao', "
                "  ciente_em = '2026-11-18T10:00:00', "
                "  justificativa = 'conferido a mao', semaforo = 'verde' "
                " WHERE numero_os = 990032")
            conn.commit()
        pagamento_servico.varrer(horas=None)
        linha = _artefatos()[0]
        assert linha[5] == "validacao", "a varredura devolveu o artefato"
        assert linha[6] == "verde", "a varredura reescreveu o semaforo"


class TestAJanela:
    def test_a_PRIMEIRA_rodada_varre_tudo(self):
        """🚨 `horas=None` é o que a primeira rodada precisa. Com 24h ela
        nasceria com 2 artefatos em vez de 79, e o histórico começaria
        truncado."""
        _os(990040, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK), atualizado="2026-09-01T10:00:00+00:00")
        assert pagamento_servico.varrer(horas=None)["novos"] == 1

    def test_a_rodada_de_24h_ignora_o_que_e_velho(self):
        _os(990041, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK), atualizado="2026-09-01T10:00:00+00:00")
        assert pagamento_servico.varrer(horas=24)["novos"] == 0

    def test_a_janela_olha_ATUALIZADO_EM_e_nao_VISTO_EM(self):
        """🚨 `visto_em` é a PRIMEIRA vez que a OS foi vista e é preservado para
        sempre. Filtrar por ele perderia toda OS antiga que ganhou valor de
        pagamento hoje — e é justamente o caso do serviço lançado depois."""
        import datetime
        agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with storage._connect() as conn:
            conn.execute(
                "INSERT INTO os_historico (numero_os, cliente_id, "
                "  materiais_json, tecnicos_json, data_previsao, visto_em, "
                "  atualizado_em, excluida) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                (990042, VELASCO, _materiais(pagamento=100.0),
                 _tecnicos(FRANCK), "18/11/2026 09:00:00",
                 "2026-09-01T10:00:00+00:00", agora))
            conn.commit()
        assert pagamento_servico.varrer(horas=24)["novos"] == 1


class TestOQuadro:
    def test_as_CINCO_colunas_na_ordem_dele(self):
        q = pagamento_servico.quadro()
        assert [c["chave"] for c in q["colunas"]] == [
            "movimentacao", "preparacao", "validacao", "procfy", "enviado"]

    def test_o_card_da_coluna_1_e_POR_TECNICO_e_ACUMULA(self):
        """🔵 Decisão dele: um card por técnico, permanente, acumulando o
        histórico. ⚠️ Duas OS do mesmo técnico são UM card com dois artefatos,
        não dois cards."""
        _os(990050, materiais=_materiais(pagamento=120.0),
            tecnicos=_tecnicos(FRANCK))
        _os(990051, materiais=_materiais(pagamento=55.0, km=10.0),
            tecnicos=_tecnicos(FRANCK))
        pagamento_servico.varrer(horas=None)
        cards = pagamento_servico.quadro()["colunas"][0]["cards"]
        assert len(cards) == 1
        assert len(cards[0]["artefatos"]) == 2
        assert cards[0]["total_pagamento"] == 175.0
        assert cards[0]["total_km"] == 10.0

    def test_cada_tecnico_tem_o_SEU_card(self):
        _os(990052, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        _os(990053, materiais=_materiais(pagamento=70.0),
            tecnicos=_tecnicos(14316))
        pagamento_servico.varrer(horas=None)
        cards = pagamento_servico.quadro()["colunas"][0]["cards"]
        assert len(cards) == 2
        assert {c["tecnico_id"] for c in cards} == {FRANCK, 14316}

    def test_a_DATA_DO_SERVICO_vem_no_artefato(self):
        """🔵 É por ela que o filtro do card corta: *"só quero fechar de
        16-18/11/26 filtro isso e flego"*. E é ela que vai ao Procfy como data
        de competência."""
        _os(990054, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK), previsao="17/11/2026 14:30:00")
        pagamento_servico.varrer(horas=None)
        assert _artefatos()[0][8] == "17/11/2026 14:30:00"


class TestOsDoisLadosDaMesmaLeitura:
    def test_os_IDS_DE_PRODUTO_sao_os_do_fechamento(self):
        """🚨 A mesma leitura vive em dois arquivos (`services/fechamento.py` e
        aqui). Se o cadastro do Harmonit renomear esses produtos, os dois têm
        de mudar juntos — e esta trava é o que faz alguém notar."""
        from fpsl_weso.services import fechamento
        import inspect
        fonte = inspect.getsource(fechamento._extrair_valores_materiais)
        assert "PAGAMENTO_TECNICO_ID" in fonte
        assert "KM_DESLOCAMENTO_ID" in fonte
        nossa = inspect.getsource(pagamento_servico._valores_do_corpo)
        assert "PAGAMENTO_TECNICO_ID" in nossa
        assert "KM_DESLOCAMENTO_ID" in nossa

    def test_a_varredura_NAO_fala_com_o_harmonit(self):
        """🚨 Trava por texto, e o que ela guarda é a diferença entre custar
        zero e custar 79 leituras num ERP que esgota o pool todo dia."""
        import inspect
        fonte = inspect.getsource(pagamento_servico)
        assert "harmonit_get" not in fonte
        assert "harmonit_post" not in fonte
        assert "os_historico" in fonte


# ===========================================================================
# OS GESTOS DAS CINCO COLUNAS
# ===========================================================================
def _preparar_um(numero=990100, *, pagamento=120.0, km=10.0, tecnico=FRANCK,
                 orcamento=3, termo="8952"):
    """Põe um artefato na coluna 2 e devolve `(artefato_id, lote_id)`."""
    _os(numero, materiais=_materiais(pagamento=pagamento, km=km),
        tecnicos=_tecnicos(tecnico) if tecnico else "[]", termo=termo)
    pagamento_servico.varrer(horas=None)
    with storage._connect() as conn:
        aid = conn.execute(
            "SELECT id FROM pagamento_artefato WHERE numero_os = ?",
            (numero,)).fetchone()[0]
    r = pagamento_servico.preparar(
        [{"id": aid, "orcamento_numero": orcamento}], por="Zz Teste")
    return aid, (r["lotes"][0] if r["lotes"] else None)


def _situacao_da_os(numero, situacao):
    with storage._connect() as conn:
        conn.execute("UPDATE os_historico SET situacao_id = ? "
                     " WHERE numero_os = ?", (situacao, numero))
        conn.commit()


def _eventos(artefato_id):
    with storage._connect() as conn:
        return [r[0] for r in conn.execute(
            "SELECT acao FROM pagamento_evento WHERE artefato_id = ? "
            " ORDER BY id", (artefato_id,)).fetchall()]


class TestPreparar:
    def test_os_marcados_viram_LOTE_do_tecnico(self):
        """🔵 *"Os itens flegados e clicados em preparar, vão gerar novo card do
        técnico, agora preparando para pagamento."*"""
        aid, lote = _preparar_um()
        assert lote is not None
        with storage._connect() as conn:
            linha = conn.execute(
                "SELECT coluna, lote_id, orcamento_numero "
                "  FROM pagamento_artefato WHERE id = ?", (aid,)).fetchone()
        assert linha[0] == "preparacao"
        assert linha[1] == lote
        # 🚨 O orçamento vem do MoviZap e é PERSISTIDO aqui: é o que vai ao
        # arquivo do Procfy como "Nº de Documento".
        assert linha[2] == 3

    def test_UM_LOTE_POR_TECNICO_e_nao_um_por_clique(self):
        """⚠️ Pagamento é por pessoa: marcar dois técnicos num clique gera dois
        cards, não um misturado."""
        _os(990110, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        _os(990111, materiais=_materiais(pagamento=70.0),
            tecnicos=_tecnicos(14316))
        pagamento_servico.varrer(horas=None)
        with storage._connect() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM pagamento_artefato ORDER BY numero_os"
            ).fetchall()]
        r = pagamento_servico.preparar([{"id": i} for i in ids])
        assert len(r["lotes"]) == 2
        assert r["preparados"] == 2

    def test_SEM_TECNICO_nao_prepara_e_DIZ_por_que(self):
        """🚨 O card dos 21 existe para o dinheiro não sair de vista, não para
        avançar: sem técnico não há a quem pagar."""
        _os(990112, materiais=_materiais(pagamento=100.0), tecnicos="[]")
        pagamento_servico.varrer(horas=None)
        with storage._connect() as conn:
            aid = conn.execute("SELECT id FROM pagamento_artefato "
                               " WHERE numero_os = 990112").fetchone()[0]
        r = pagamento_servico.preparar([{"id": aid}])
        assert r["preparados"] == 0
        assert r["recusados"][0]["numero_os"] == 990112
        assert "sem tecnico" in r["recusados"][0]["porque"]

    def test_preparar_DUAS_VEZES_nao_duplica(self):
        """⚠️ Preparar de novo o poria em dois lotes, e o mesmo serviço seria
        pago duas vezes."""
        aid, _ = _preparar_um(990113)
        r = pagamento_servico.preparar([{"id": aid}])
        assert r["preparados"] == 0
        assert "ja esta na coluna preparacao" in r["recusados"][0]["porque"]

    def test_grava_EVENTO(self):
        aid, _ = _preparar_um(990114)
        assert "preparar" in _eventos(aid)


class TestAPortaDuplaDaColuna2:
    """🚨 O conserto do funil que ele mandou medir em 11/11 (70 → 16 → 8 OS)."""

    def test_situacao_do_ERP_que_libera(self):
        for situacao in pagamento_tabelas.SITUACOES_QUE_LIBERAM:
            aid, _ = _preparar_um(990120 + situacao % 100)
            _situacao_da_os(990120 + situacao % 100, situacao)
            r = pagamento_servico.situacao_para_conferir(aid)
            assert r["libera"] is True, situacao

    def test_ETAPA_NOSSA_2322_tambem_libera(self):
        """🚨 *"Serviço Realizado"* é etapa NOSSA, não situação do Harmonit —
        e o Fechamento antigo exigia só a 15694, que foi o que derrubou 70 OS
        para 16."""
        aid, _ = _preparar_um(990130)
        _situacao_da_os(990130, 890)        # "Agendar serviço": não libera
        r = pagamento_servico.situacao_para_conferir(
            aid, etapas_nossas={990130})
        assert r["libera"] is True
        assert r["etapa_nossa"] is True

    def test_situacao_FORA_das_quatro_nao_libera_e_a_frase_DIZ_qual(self):
        aid, _ = _preparar_um(990131)
        _situacao_da_os(990131, 890)
        r = pagamento_servico.situacao_para_conferir(aid)
        assert r["libera"] is False
        # 🚨 A frase diz O QUE FOI LIDO: cor sozinha não é portadora de
        # informação, e a decisão aqui é do operador.
        assert "890" in r["motivo"]
        assert r["situacao_do_erp"] == 890

    def test_o_semaforo_acompanha(self):
        aid, _ = _preparar_um(990132)
        _situacao_da_os(990132, 15694)
        pagamento_servico.situacao_para_conferir(aid)
        with storage._connect() as conn:
            cor = conn.execute("SELECT semaforo FROM pagamento_artefato "
                               " WHERE id = ?", (aid,)).fetchone()[0]
        assert cor == "verde"

    def test_etapas_nossas_VAZIO_nao_significa_nenhuma(self):
        """⚠️ Vazio quer dizer *"o MoviZap não informou"*, e a porta do ERP
        continua valendo sozinha."""
        aid, _ = _preparar_um(990133)
        _situacao_da_os(990133, 15696)
        assert pagamento_servico.situacao_para_conferir(
            aid, etapas_nossas=None)["libera"] is True


class TestCienteEDevolver:
    def test_ciente_guarda_A_SITUACAO_do_momento(self):
        """⚠️ Sem isso, ninguém saberia depois do que a pessoa estava ciente."""
        aid, _ = _preparar_um(990140)
        _situacao_da_os(990140, 890)
        pagamento_servico.situacao_para_conferir(aid)
        assert pagamento_servico.dar_ciente(aid, por="Zz")["ok"] is True
        with storage._connect() as conn:
            detalhe = conn.execute(
                "SELECT detalhe FROM pagamento_evento "
                " WHERE artefato_id = ? AND acao = 'ciente'",
                (aid,)).fetchone()[0]
        assert "890" in detalhe

    def test_ciente_de_situacao_QUE_NAO_LIBERA_e_permitido(self):
        """⚠️ Ciente não é aprovação automática: é a decisão do operador, e o
        log guarda qual era a situação."""
        aid, _ = _preparar_um(990141)
        _situacao_da_os(990141, 890)
        pagamento_servico.situacao_para_conferir(aid)
        assert pagamento_servico.dar_ciente(aid)["ok"] is True

    def test_devolver_SEM_justificativa_recusa(self):
        """🚨 Laranja sem motivo é cor sem informação."""
        aid, _ = _preparar_um(990142)
        r = pagamento_servico.devolver(aid, "   ")
        assert r["ok"] is False
        assert "justificativa" in r["motivo"]

    def test_devolver_poe_na_COLUNA_1_em_LARANJA(self):
        """🔵 *"devolvido ao card na coluna de Movimentação (...) agora tem a
        cor laranja"*."""
        aid, _ = _preparar_um(990143)
        r = pagamento_servico.devolver(aid, "OS ainda em Agendar servico",
                                       por="Zz")
        assert r["ok"] is True
        with storage._connect() as conn:
            linha = conn.execute(
                "SELECT coluna, semaforo, justificativa, lote_id, ciente_em "
                "  FROM pagamento_artefato WHERE id = ?", (aid,)).fetchone()
        assert linha[0] == "movimentacao"
        assert linha[1] == "laranja"
        assert linha[2] == "OS ainda em Agendar servico"
        assert linha[3] is None
        # ⚠️ O ciente SAI: manter faria a próxima preparação herdar uma
        # confirmação dada sobre outro estado.
        assert linha[4] is None

    def test_devolver_da_COLUNA_3_tambem_vai_para_a_1(self):
        """🔵 *"veja que aqui não retorna para a anterior e sim para o 1"*."""
        aid, lote = _preparar_um(990144)
        _situacao_da_os(990144, 15694)
        pagamento_servico.situacao_para_conferir(aid)
        pagamento_servico.dar_ciente(aid)
        pagamento_servico.auditar(lote)
        with storage._connect() as conn:
            assert conn.execute(
                "SELECT coluna FROM pagamento_artefato WHERE id = ?",
                (aid,)).fetchone()[0] == "validacao"
        pagamento_servico.devolver(aid, "recibo nao bate")
        with storage._connect() as conn:
            assert conn.execute(
                "SELECT coluna FROM pagamento_artefato WHERE id = ?",
                (aid,)).fetchone()[0] == "movimentacao"


class TestAuditar:
    def test_SO_OS_CIENTES_andam(self):
        """🔵 *"irá mover o card somente com os cientes de situação e não
        negados para a próxima coluna"*.

        🚨 Quem não recebeu ciente FICA — não é devolvido nem avança. Devolver
        automaticamente seria decidir pelo operador."""
        _os(990150, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        _os(990151, materiais=_materiais(pagamento=80.0),
            tecnicos=_tecnicos(FRANCK))
        pagamento_servico.varrer(horas=None)
        with storage._connect() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM pagamento_artefato ORDER BY numero_os"
            ).fetchall()]
        lote = pagamento_servico.preparar(
            [{"id": i} for i in ids])["lotes"][0]
        pagamento_servico.dar_ciente(ids[0])     # só um
        r = pagamento_servico.auditar(lote, por="Zz")
        assert r["avancaram"] == 1
        assert r["ficaram"] == 1
        with storage._connect() as conn:
            colunas = {x[0]: x[1] for x in conn.execute(
                "SELECT id, coluna FROM pagamento_artefato").fetchall()}
        assert colunas[ids[0]] == "validacao"
        assert colunas[ids[1]] == "preparacao"

    def test_o_que_FICOU_ganha_card_proprio(self):
        """🚨 Sem isto, o artefato sem ciente ficaria órfão de card — visível em
        nenhuma coluna."""
        _os(990152, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        _os(990153, materiais=_materiais(pagamento=80.0),
            tecnicos=_tecnicos(FRANCK))
        pagamento_servico.varrer(horas=None)
        with storage._connect() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM pagamento_artefato ORDER BY numero_os"
            ).fetchall()]
        lote = pagamento_servico.preparar(
            [{"id": i} for i in ids])["lotes"][0]
        pagamento_servico.dar_ciente(ids[0])
        pagamento_servico.auditar(lote)
        with storage._connect() as conn:
            novo = conn.execute(
                "SELECT lote_id FROM pagamento_artefato WHERE id = ?",
                (ids[1],)).fetchone()[0]
            coluna = conn.execute(
                "SELECT coluna FROM pagamento_lote WHERE id = ?",
                (novo,)).fetchone()[0]
        assert novo != lote
        assert coluna == "preparacao"

    def test_lote_SEM_NENHUM_ciente_nao_audita(self):
        _, lote = _preparar_um(990154)
        r = pagamento_servico.auditar(lote)
        assert r["ok"] is False
        assert r["avancaram"] == 0
        assert "nenhum artefato" in r["motivo"]


class TestOSemaforoDosValores:
    """🔵 As três regras dele, e cada uma é um teste."""

    def test_recibo_IGUAL_e_verde(self):
        assert pagamento_servico.semaforo_do_valor(
            120.0, 10.0, 130.0, tem_comprovante=True) == "verde"

    def test_a_pagar_MAIOR_que_o_recibo_e_vermelho(self):
        """🔵 *"valor a pagar maior que recibo em vermelho"*."""
        assert pagamento_servico.semaforo_do_valor(
            120.0, 10.0, 100.0, tem_comprovante=True) == "vermelho"

    def test_recibo_MAIOR_e_amarelo_e_nao_vermelho(self):
        """⚠️ Vermelho é SÓ um sentido. Recibo maior é divergência, não
        pagamento a descoberto — e tratá-lo como vermelho treinaria a pessoa a
        ignorar a cor que importa."""
        assert pagamento_servico.semaforo_do_valor(
            100.0, 0.0, 120.0, tem_comprovante=True) == "amarelo"

    def test_AUSENCIA_e_amarelo(self):
        """🔵 *"divergências ou ausências"* — as duas em amarelo."""
        assert pagamento_servico.semaforo_do_valor(
            100.0, 0.0, None, tem_comprovante=False) == "amarelo"

    def test_dispensa_SEM_arquivo_e_ausencia(self):
        """⚠️ Justificativa escrita não é comprovante: é ausência justificada,
        e continua amarela."""
        assert pagamento_servico.semaforo_do_valor(
            100.0, 0.0, 100.0, tem_comprovante=False) == "amarelo"

    def test_a_FOLGA_de_um_centavo(self):
        """🚨 Os valores vêm de duas origens: os nossos saem de `valorTotal`
        (float) e o do recibo é digitado. Sem a folga, 120.00 contra
        119.999999 viraria divergência."""
        assert pagamento_servico.semaforo_do_valor(
            120.0, 0.0, 119.995, tem_comprovante=True) == "verde"


class TestComprovante:
    def test_exige_arquivo_OU_dispensa(self):
        aid, _ = _preparar_um(990160)
        r = pagamento_servico.guardar_comprovante(
            aid, arquivo=None, valor=None, dispensa=None)
        assert r["ok"] is False
        assert "comprovante" in r["motivo"]

    def test_arquivo_com_valor_que_bate_fica_VERDE(self):
        aid, _ = _preparar_um(990161, pagamento=120.0, km=10.0)
        r = pagamento_servico.guardar_comprovante(
            aid, arquivo="recibo.pdf", valor=130.0, por="Zz")
        assert r["ok"] is True
        assert r["semaforo"] == "verde"

    def test_a_DISPENSA_sozinha_e_aceita(self):
        """🔵 *"ou justificativa escrita na tela de envio de anexo (pode não
        ter)"*."""
        aid, _ = _preparar_um(990162)
        r = pagamento_servico.guardar_comprovante(
            aid, arquivo=None, valor=None, dispensa="tecnico nao emite recibo")
        assert r["ok"] is True
        assert r["semaforo"] == "amarelo"


class TestOProcfy:
    def _ate_validacao(self, numero=990170, **kw):
        aid, lote = _preparar_um(numero, **kw)
        _situacao_da_os(numero, 15694)
        pagamento_servico.situacao_para_conferir(aid)
        pagamento_servico.dar_ciente(aid)
        pagamento_servico.auditar(lote)
        return aid, lote

    CONFIG = {"procfy_categoria": "Servicos de terceiros",
              "procfy_conta_bancaria": "Conta Movisat",
              "procfy_modo_pagamento": "PIX",
              "procfy_centro_de_custo": "Operacao"}

    def test_as_14_colunas_na_ORDEM_do_modelo(self):
        """📏 Lidas do `modelo_importacao_procfy.xlsx`, que tem 14 colunas e
        ZERO linhas de exemplo."""
        aid, lote = self._ate_validacao(990170)
        pagamento_servico.guardar_comprovante(aid, arquivo="r.pdf", valor=130.0)
        r = pagamento_servico.linhas_do_procfy(lote, self.CONFIG)
        assert r["ok"] is True
        assert list(r["linhas"][0].keys()) == list(
            pagamento_servico.PROCFY_COLUNAS)

    def test_a_descricao_traz_OS_TERMO_e_tecnico(self):
        aid, lote = self._ate_validacao(990171)
        pagamento_servico.guardar_comprovante(aid, arquivo="r.pdf", valor=130.0)
        linha = pagamento_servico.linhas_do_procfy(
            lote, self.CONFIG)["linhas"][0]
        assert "OS 990171" in linha["Descrição"]
        assert "TERMO 8952" in linha["Descrição"]

    def test_o_valor_soma_pagamento_e_km_com_VIRGULA(self):
        """⚠️ Vírgula decimal: o arquivo é lido por uma planilha em pt-BR."""
        aid, lote = self._ate_validacao(990172, pagamento=120.0, km=10.5)
        pagamento_servico.guardar_comprovante(aid, arquivo="r.pdf", valor=130.5)
        linha = pagamento_servico.linhas_do_procfy(
            lote, self.CONFIG)["linhas"][0]
        assert linha["Valor"] == "130,50"

    def test_a_competencia_e_a_data_do_SERVICO(self):
        """🔵 Não a do pagamento."""
        aid, lote = self._ate_validacao(990173)
        pagamento_servico.guardar_comprovante(aid, arquivo="r.pdf", valor=130.0)
        linha = pagamento_servico.linhas_do_procfy(
            lote, self.CONFIG)["linhas"][0]
        assert linha["Data de competência"] == "18/11/2026"

    def test_GERA_COM_OS_QUATRO_EM_BRANCO_e_DIZ_quais(self):
        """🔵 Decisão dele, 18/11: *"pode gerar com elas em branco nesse
        momento, pois podem preencher a mão por informação confidencial ou
        depois nos passar"*.

        ⚠️ ISTO REVERTEU O QUE EU TINHA ESCRITO. Eu havia travado a geração,
        com o argumento de que arquivo recusado é pior que arquivo nenhum. O
        argumento ignorava que os valores podem ser **confidenciais** e que
        quem importa preenche na planilha — travar não protegia ninguém.

        🚨 O que fica da preocupação: o arquivo sai e a resposta DIZ quais
        colunas saíram em branco, com o nome que elas têm na planilha dele.
        """
        aid, lote = self._ate_validacao(990174)
        pagamento_servico.guardar_comprovante(aid, arquivo="r.pdf", valor=130.0)
        r = pagamento_servico.linhas_do_procfy(lote, {})
        assert r["ok"] is True
        assert r["linhas"][0]["Categoria"] == ""
        assert set(r["em_branco"]) == set(pagamento_servico.PROCFY_CONFIG)
        # 🚨 O aviso fala a língua da PLANILHA, não a do nosso `/config`.
        assert "Centro de Custo" in r["aviso"]
        assert "procfy_centro_de_custo" not in r["aviso"]

    def test_sem_orcamento_o_campo_DIZ_isso(self):
        """⚠️ Vazio seria indistinguível de "esqueci de preencher"."""
        aid, lote = self._ate_validacao(990175, orcamento=None)
        pagamento_servico.guardar_comprovante(aid, arquivo="r.pdf", valor=130.0)
        linha = pagamento_servico.linhas_do_procfy(
            lote, self.CONFIG)["linhas"][0]
        assert linha["Observações"] == "sem orcamento"
        assert linha["Número de Documento / Nosso número"] == ""

    def test_montar_arquivo_move_SO_quem_tem_comprovante_ou_dispensa(self):
        _os(990180, materiais=_materiais(pagamento=100.0),
            tecnicos=_tecnicos(FRANCK))
        _os(990181, materiais=_materiais(pagamento=80.0),
            tecnicos=_tecnicos(FRANCK))
        pagamento_servico.varrer(horas=None)
        with storage._connect() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM pagamento_artefato ORDER BY numero_os"
            ).fetchall()]
        lote = pagamento_servico.preparar([{"id": i} for i in ids])["lotes"][0]
        for i in ids:
            pagamento_servico.dar_ciente(i)
        pagamento_servico.auditar(lote)
        pagamento_servico.guardar_comprovante(ids[0], arquivo="r.pdf",
                                              valor=100.0)
        r = pagamento_servico.montar_arquivo(lote, self.CONFIG, por="Zz")
        assert r["ok"] is True
        assert r["avancaram"] == 1
        assert r["ficaram"] == 1
        assert r["arquivo"].endswith(".xlsx")

    def test_enviar_exige_arquivo_gerado(self):
        aid, lote = self._ate_validacao(990182)
        r = pagamento_servico.enviar_pagamento(lote)
        assert r["ok"] is False
        assert "validacao" in r["motivo"]


class TestRevalidar:
    def test_NAO_MOVE_nada(self):
        """🚨 O botão que ele pediu é de *atualizar*, não de avançar: mover
        aqui seria decidir pelo operador."""
        aid, lote = _preparar_um(990190)
        _situacao_da_os(990190, 890)
        r = pagamento_servico.revalidar(lote, etapas_nossas=set())
        assert r["ok"] is True
        with storage._connect() as conn:
            assert conn.execute(
                "SELECT coluna FROM pagamento_artefato WHERE id = ?",
                (aid,)).fetchone()[0] == "preparacao"

    def test_o_CIENTE_sobrevive(self):
        """⚠️ O operador já olhou, e a releitura não apaga a assinatura dele."""
        aid, lote = _preparar_um(990191)
        _situacao_da_os(990191, 15694)
        pagamento_servico.situacao_para_conferir(aid)
        pagamento_servico.dar_ciente(aid)
        pagamento_servico.revalidar(lote)
        with storage._connect() as conn:
            assert conn.execute(
                "SELECT ciente_em FROM pagamento_artefato WHERE id = ?",
                (aid,)).fetchone()[0] is not None

    def test_pega_o_AJUSTE_feito_depois(self):
        """🔵 *"caso algum ajuste tenha sido feito depos que ele nasceu"*."""
        aid, lote = _preparar_um(990192)
        _situacao_da_os(990192, 890)
        pagamento_servico.situacao_para_conferir(aid)
        with storage._connect() as conn:
            assert conn.execute(
                "SELECT semaforo FROM pagamento_artefato WHERE id = ?",
                (aid,)).fetchone()[0] == "amarelo"
        _situacao_da_os(990192, 15694)        # alguém moveu a OS no ERP
        r = pagamento_servico.revalidar(lote)
        assert r["liberam"] == 1
        with storage._connect() as conn:
            assert conn.execute(
                "SELECT situacao_do_erp FROM pagamento_artefato WHERE id = ?",
                (aid,)).fetchone()[0] == 15694


class TestODataScope:
    def test_le_o_CACHE_e_nao_a_API(self):
        """⚠️ A chave e o cliente são do FPSL e a sincronização já roda. 🚨 E o
        `datascope_client` é GET-only por decisão de projeto."""
        import inspect
        fonte = inspect.getsource(pagamento_servico.datascope_do_artefato)
        assert "datascope_respostas" in fonte
        assert "change_state" not in fonte

    def test_SEM_REGISTRO_diz_a_frase_que_a_conferencia_ja_usava(self):
        """🚨 Repetir a frase exata é o que evita duas leituras do mesmo fato —
        a `conferencia_fechamento` já diz *"sem registro no DataScope para esta
        OS"*."""
        aid, _ = _preparar_um(990200)
        r = pagamento_servico.datascope_do_artefato(aid)
        assert r["ok"] is True
        assert r["form_state"] is None
        assert r["motivo"] == "sem registro no DataScope para esta OS"

    def test_com_registro_traz_o_estado(self):
        aid, _ = _preparar_um(990201)
        with storage._connect() as conn:
            conn.execute(
                "INSERT INTO datascope_respostas (form_answer_id, numero_os, "
                "  form_state, updated_at) VALUES (1, 990201, 'Finalizado', "
                "  '2026-11-18T10:00:00Z')")
            conn.commit()
        r = pagamento_servico.datascope_do_artefato(aid)
        assert r["form_state"] == "Finalizado"


class TestOLogDeTudo:
    def test_cada_gesto_deixa_EVENTO(self):
        """🔵 *"deve ter o log de quem faz o que SEMPRE"*. 🚨 Aqui pesa mais que
        em qualquer outra tela: este fluxo move dinheiro."""
        aid, lote = _preparar_um(990210)
        _situacao_da_os(990210, 15694)
        pagamento_servico.situacao_para_conferir(aid)
        pagamento_servico.dar_ciente(aid, por="Zz")
        pagamento_servico.auditar(lote, por="Zz")
        pagamento_servico.guardar_comprovante(aid, arquivo="r.pdf",
                                              valor=130.0, por="Zz")
        acoes = _eventos(aid)
        for esperada in ("preparar", "ciente", "auditar", "comprovante"):
            assert esperada in acoes, acoes

    def test_o_evento_guarda_QUEM(self):
        aid, _ = _preparar_um(990211)
        pagamento_servico.dar_ciente(aid, por="Zz Operador")
        with storage._connect() as conn:
            quem = conn.execute(
                "SELECT por FROM pagamento_evento WHERE artefato_id = ? "
                "  AND acao = 'ciente'", (aid,)).fetchone()[0]
        assert quem == "Zz Operador"
