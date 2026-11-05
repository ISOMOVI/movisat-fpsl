# -*- coding: utf-8 -*-
r"""O TERMO da OS — extração do texto e a coluna no cache (Área E, 05/11).

🚨 **O QUE ESTE ARQUIVO PROTEGE:** o termo não é campo do Harmonit. Ele é
**derivado** de um texto livre que gente digita, e derivação sem teste é
suposição com cara de dado.

📏 A expressão nasceu de 200 OS lidas ao vivo em 05/11: 173 com termo, 27 sem,
**0** com mais de um termo distinto e **0** com a palavra `TERMO` sem número ao
lado. Os quatro formatos reais viraram caso de teste, com o número da OS de
onde saíram.

Roda:  venv/bin/python -m pytest tests/teste_termo_da_os.py
"""
import pathlib
import sqlite3
import sys
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.termo_da_os import termo_da_descricao  # noqa: E402


# ============================================================================
# A extração — os formatos REAIS, com a OS de onde cada um saiu
# ============================================================================
class TestOsFormatosReais:

    def test_termo_com_espaco(self):
        """OS 17082, a mais comum: `FINANCEIRO — TERMO 8937 | placas: ...`"""
        assert termo_da_descricao(
            "FINANCEIRO — TERMO 8937 | placas: DMD 0324, GZP 8D54 | itens: x"
        ) == "8937"

    def test_termo_no_meio_da_linha(self):
        """OS 17081: o termo vem entre o equipamento e o número da OS."""
        assert termo_da_descricao(
            "Retirada: BUS 0168 | .BENZ L 1516 | 007736334 (Suntech ST310) "
            "| TERMO 8937 | O.S: 17081") == "8937"

    def test_termo_com_dois_pontos_e_sem_espaco(self):
        """OS 17038: `TERMO:8927` e `TERMO 8927` na MESMA descrição.

        🚨 É o mesmo termo escrito de duas maneiras — e isso **não** é
        ambiguidade. Se fosse tratado como tal, a OS de substituição (um
        padrão inteiro de OS) ficaria sem termo.
        """
        assert termo_da_descricao(
            "SUBSTITUICAO INSTALACAO: A_DEFINIR_2_8927 | TERMO:8927 "
            "| 007785507 (Suntech ST310) | TERMO 8927 | O.S: 17038") == "8927"

    def test_termo_logo_depois_de_dois_pontos(self):
        """OS 17025: `RESSARCIMENTO: TERMO 8924 | placas: ...`"""
        assert termo_da_descricao(
            "RESSARCIMENTO: TERMO 8924 | placas: TKZ 6A06 | O.S: 17025"
        ) == "8924"

    def test_caixa_nao_importa(self):
        """⚠️ A régua da casa: varredura de rótulo ignora caixa."""
        assert termo_da_descricao("instalacao | termo 8940 | x") == "8940"
        assert termo_da_descricao("Termo: 8940") == "8940"


class TestQuandoNaoHaTermo:
    """⚠️ **OS SEM TERMO É NORMAL** — 27 das 200 medidas. Venda, compra de
    cartão RFID, entrega de chaveiro e manutenção não nascem de termo."""

    @pytest.mark.parametrize("descricao", [
        "ENTREGA DE CARTOES RFID: 10 CARTOES | ORCAMENTO 1313 | VENDA 434",
        "ENTREGA DE CHAVEIRO iBUTTON: 08 UNIDADES | VENDA 433 | O.S: 17050",
        "16 TAXA DE RETIRADA R$ 299,00 R$ 299,00 R$ 4.784,00",
    ])
    def test_descricao_real_sem_termo(self, descricao):
        assert termo_da_descricao(descricao) is None

    def test_descricao_vazia_e_nula(self):
        """🚨 Não estoura: a `descricao` é nula em OS do ERP, e um extrator que
        levanta aqui derrubaria a varredura inteira."""
        assert termo_da_descricao(None) is None
        assert termo_da_descricao("") is None
        assert termo_da_descricao("   ") is None

    def test_a_palavra_sem_numero_nao_vira_termo(self):
        r"""🚨 A guarda que motivou exigir dígitos: com `\S+` isto devolveria
        *DE*, e o card mostraria `TERMO DE`."""
        assert termo_da_descricao("TERMO DE ADESAO ASSINADO") is None
        assert termo_da_descricao("conforme o termo, sem numero") is None


class TestDoisTermosDiferentes:
    """🚨 **DOIS TERMOS DISTINTOS DEVOLVEM NULO, de propósito.**

    Nenhuma das 200 descrições medidas tinha dois, então o caso é
    desconhecido. Escolher o primeiro calado poria no card um termo que pode
    ser o errado — e termo errado no card é pior que termo nenhum, porque
    ninguém confere o que parece certo.
    """

    def test_dois_distintos_viram_nulo(self):
        assert termo_da_descricao("TERMO 8937 e tambem TERMO 8940") is None

    def test_o_mesmo_repetido_nao_e_ambiguo(self):
        assert termo_da_descricao("TERMO 8937 ... TERMO 8937") == "8937"

    def test_zero_a_esquerda_e_o_mesmo_termo(self):
        """⚠️ `08937` e `8937` são o mesmo número escrito de dois jeitos."""
        assert termo_da_descricao("TERMO 08937 | TERMO 8937") == "8937"


# ============================================================================
# A coluna no cache — e a proteção de não sobrescrever
# ============================================================================
TMP = tempfile.mkdtemp(prefix="termo_cache_")
DB = pathlib.Path(TMP) / "fpsl_teste.db"

from fpsl_weso import storage  # noqa: E402


class TestATermoNoCache:
    """🚨 **O `DB_PATH` É TROCADO NA FIXTURE E DEVOLVIDO DEPOIS**, nunca no
    import do módulo. Apontá-lo no topo do arquivo é global compartilhado: o
    `pytest` importa todos os arquivos antes de rodar qualquer um, e o último
    import ganha — foi exatamente isso que fez 10 testes do
    `teste_ponte_rotas_http` reprovarem **só quando rodados junto com este**.
    A casa já tem um `teste_colisao_de_globais` por esta mesma razão."""

    @pytest.fixture(autouse=True)
    def banco(self, monkeypatch):
        monkeypatch.setattr(storage, "DB_PATH", DB)
        conn = sqlite3.connect(str(DB))
        conn.execute("DROP TABLE IF EXISTS os_historico")
        conn.execute("""
            CREATE TABLE os_historico (
                numero_os INTEGER PRIMARY KEY, tipo INTEGER, problema INTEGER,
                produto_id INTEGER, cliente_id INTEGER, data_previsao TEXT,
                oficinas_json TEXT, n_oficinas INTEGER NOT NULL DEFAULT 0,
                visto_em TEXT NOT NULL, atualizado_em TEXT NOT NULL,
                excluida INTEGER NOT NULL DEFAULT 0, status INTEGER,
                status_str TEXT, materiais_json TEXT, situacao_id INTEGER,
                os_id INTEGER, tecnicos_json TEXT, prioridade INTEGER,
                termo TEXT)""")
        conn.commit()
        conn.close()
        yield

    def _salvar(self, **kw):
        import asyncio
        base = dict(numero_os=90101, tipo=1783, problema=None, produto_id=None,
                    cliente_id=998063, data_previsao="05/11/2026 09:00:00",
                    oficinas=[])
        base.update(kw)
        return asyncio.run(storage.salvar_os_historico(**base))

    def _termo(self, numero=90101):
        with storage._connect() as conn:
            return conn.execute("SELECT termo FROM os_historico WHERE numero_os = ?",
                                (numero,)).fetchone()[0]

    def test_o_termo_e_gravado(self):
        self._salvar(termo="8937")
        assert self._termo() == "8937"

    def test_quem_nao_tem_o_dado_nao_apaga_quem_tem(self):
        """🚨 A PROTEÇÃO QUE MAIS PESA NESTA COLUNA. O termo só existe na
        `descricao`, e **nem todo chamador a lê** — um save sem ela apagaria o
        termo de todas as OS que já o tinham."""
        self._salvar(termo="8937")
        self._salvar()                      # sem termo nenhum
        assert self._termo() == "8937"

    def test_termo_novo_substitui_o_antigo(self):
        """⚠️ Quem TEM o dado manda: a descrição mudou no ERP, o termo muda."""
        self._salvar(termo="8937")
        self._salvar(termo="8940")
        assert self._termo() == "8940"

    def test_os_nova_sem_termo_nasce_nula(self):
        self._salvar(numero_os=90102)
        assert self._termo(90102) is None


# ============================================================================
# 🚨 RODA NOS DOIS MODOS, e isto NÃO é decoração
# ============================================================================
# O critério oficial de verde do FPSL é o laço de `docs/fpsl/18_Testes.md`:
#
#     for t in tests/teste_*.py; do venv/bin/python "$t"; ... done
#
# Arquivo só-de-pytest executado assim **não roda nada e sai com 0**: o laço o
# conta como verde sem ter verificado uma linha. Medido em 05/11 — e os dois
# arquivos da ponte (`teste_ponte_rotas_http`, `teste_criar_os_ponte`) estão
# exatamente nesse estado desde 29/10, embora a doc afirme que *"rodam nos
# dois modos"*. Isto é falha do INSTRUMENTO de medida, que é pior que teste
# faltando: teste faltando se vê, falso verde não.
#
# ⚠️ Consertar os dois da ponte é decisão dele (mexe no placar do projeto);
# este arquivo pelo menos não nasce entrando na conta sem rodar.
if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
