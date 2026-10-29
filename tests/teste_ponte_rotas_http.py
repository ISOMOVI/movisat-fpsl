# -*- coding: utf-8 -*-
"""As rotas da ponte POR HTTP — `/api/os/criar` e `/api/os/por-situacao`.

🚨 ESTE ARQUIVO NASCEU DE UMA AUDITORIA DELE no mesmo dia da entrega:
*"auditou e validou o entregue? as rotas?"*. A resposta era **não** — as duas
rotas novas da ponte tinham teste de FUNÇÃO e nenhum teste de ROTA.

🚨 POR QUE NÃO BASTA TESTAR A FUNÇÃO, e o `teste_car_router` desta casa já diz
há um dia: a função não exercita a **chave da ponte**, o **código de estado**,
a **validação do corpo** nem a **serialização**. E `py_compile` não pega import
faltando — hoje mesmo um `Query` não importado no MoviZap derrubou o serviço em
produção por 13 segundos.

🚨 O BANCO É TEMPORÁRIO, apontado ANTES de qualquer import do pacote, como o
`teste_car_router` faz: `storage.DB_PATH` é lido na hora da conexão. Nada toca
o `data/fpsl.db`.

⚠️ E NADA FALA COM O HARMONIT: a escrita e a leitura do ERP são trocadas por
dublê. Teste que cria OS em ERP de produção deixa sujeira que fica, e o número
da OS não volta à sequência.

Roda:  venv/bin/python -m pytest tests/teste_ponte_rotas_http.py
"""
import pathlib
import sqlite3
import sys
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TMP = tempfile.mkdtemp(prefix="ponte_rotas_")
# 🚨 `Path`, NAO texto: o `storage._connect` faz `DB_PATH.parent.mkdir(...)`, e
# com uma string isso estoura `'str' object has no attribute 'parent'`. Medido
# aqui -- e o `teste_car_router` de 28/10 aponta um `str`, o que vale conferir.
DB = pathlib.Path(TMP) / "fpsl_teste.db"

from fpsl_weso import storage  # noqa: E402

storage.DB_PATH = DB

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from fpsl_weso.config import settings  # noqa: E402
from fpsl_weso.routers import os_ponte  # noqa: E402

# 🚨 O CLIENTE DOS TESTES E A VELASCO (998063), E SO ELA. Regra dele, 29/10:
# *"nao pode usar outro CNPJ alem da VELASCO para teste, pois os tickets nascem
# e tem ligacoes. OS com outros clientes podem ser mal interpretadas pela OP"*.
#
# ⚠️ Aqui o id vive em DUBLE e nenhuma escrita chega ao ERP -- mas e de um teste
# que se copia o numero para um script que escreve, e foi exatamente o que eu
# fiz em 29/10: a OS 17056 nasceu na DCBM porque o numero dela estava a mao.
CLIENTE_SANDBOX = 998063


CHAVE = "zz-chave-de-teste-da-ponte"

# As OS do banco de mentira. 🚨 A `data_previsao` vai no formato do Harmonit
# (`dd/mm/aaaa HH:MM:SS`) de propósito: é ele que o corte por data tem de
# saber recortar, e `date()` devolveria zero linha.
OS_DE_MENTIRA = [
    # numero, situacao, status_str, cliente, previsao, excluida
    (90001, 38, "Nova", 998063, "25/10/2026 09:00:00", 0),
    (90002, 1316, "Iniciada", 998063, "26/10/2026 09:00:00", 0),
    (90003, 15746, "Finalizado", 54406, "27/10/2026 09:00:00", 0),
    (90004, 0, "Nova", 54406, "28/10/2026 09:00:00", 0),
    # ⚠️ ANTES do corte: tem de ficar de fora.
    (90005, 38, "Nova", 998063, "10/10/2026 09:00:00", 0),
    # 🚨 EXCLUÍDA: nunca entra, com interruptor ou sem.
    (90006, 38, "Nova", 998063, "27/10/2026 09:00:00", 1),
]


@pytest.fixture(scope="module", autouse=True)
def banco_de_mentira():
    conn = sqlite3.connect(str(DB))
    conn.execute("""
        CREATE TABLE os_historico (
            numero_os INTEGER PRIMARY KEY, tipo INTEGER, problema INTEGER,
            produto_id INTEGER, cliente_id INTEGER, data_previsao TEXT,
            oficinas_json TEXT, n_oficinas INTEGER NOT NULL DEFAULT 0,
            visto_em TEXT NOT NULL, atualizado_em TEXT NOT NULL,
            excluida INTEGER NOT NULL DEFAULT 0, status INTEGER,
            status_str TEXT, materiais_json TEXT, situacao_id INTEGER,
            os_id INTEGER, tecnicos_json TEXT)""")
    conn.execute("CREATE TABLE tipos_os (tipo_id INTEGER PRIMARY KEY, nome TEXT)")
    conn.executemany("INSERT INTO tipos_os VALUES (?, ?)",
                     [(1783, "Solicitação de Cliente"), (76, "Instalação rastreador")])
    for numero, situacao, status, cliente, previsao, excluida in OS_DE_MENTIRA:
        conn.execute(
            """INSERT INTO os_historico
                   (numero_os, situacao_id, status_str, cliente_id,
                    data_previsao, excluida, tipo, os_id, visto_em,
                    atualizado_em, oficinas_json, tecnicos_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (numero, situacao, status, cliente, previsao, excluida, 1783,
             900000 + numero, "2026-10-29T18:00:00Z", "2026-10-29T18:00:00Z",
             '[{"veiculoPlaca": "ABC1D23", "veiculoNome": "zz"}]',
             '[{"usuarioId": 14316, "nome": "zz Tecnico"}]'))
    conn.commit()
    conn.close()
    yield


@pytest.fixture(scope="module")
def cliente(banco_de_mentira):
    """O app com SÓ o router da ponte — o painel inteiro não é o que se mede."""
    settings.ponte_fpsl_segredo = CHAVE
    app = FastAPI()
    app.include_router(os_ponte.router)
    with TestClient(app) as c:
        yield c


CAB = {"X-Ponte-Key": CHAVE}


# ============================================================================
# A chave da ponte
# ============================================================================
class TestAChaveDaPonte:
    """🚨 ESTA ROTA NÃO USA SESSÃO DE PESSOA: chamada servidor-a-servidor não
    tem cookie. O que a protege é o segredo, e é a única coisa entre quem
    alcança a porta e a CRIAÇÃO DE OS NO ERP."""

    def test_sem_chave_nao_passa(self, cliente):
        assert cliente.get("/api/os/por-situacao?desde=2026-10-24"
                           ).status_code == 422  # header obrigatório

    def test_chave_errada_nao_passa(self, cliente):
        r = cliente.get("/api/os/por-situacao?desde=2026-10-24",
                        headers={"X-Ponte-Key": "nao-e-a-chave"})
        assert r.status_code == 401

    def test_a_criacao_tambem_exige_a_chave(self, cliente):
        """🚨 A rota que ESCREVE no ERP não pode ser a desprotegida."""
        r = cliente.post("/api/os/criar", json={},
                         headers={"X-Ponte-Key": "nao-e-a-chave"})
        assert r.status_code == 401


# ============================================================================
# GET /api/os/por-situacao
# ============================================================================
class TestPorSituacao:
    def test_o_corte_por_data_funciona_no_formato_brasileiro(self, cliente):
        """🚨 `data_previsao` é TEXTO `dd/mm/aaaa`, e `date()` devolveria ZERO
        linha — custou um plano inteiro em 19/10."""
        r = cliente.get("/api/os/por-situacao?desde=2026-10-24&so_abertas=0",
                        headers=CAB)
        assert r.status_code == 200, r.text
        numeros = {o["numero_os"] for o in r.json()["os"]}
        # 90005 é de 10/10, antes do corte; 90006 é excluída.
        assert numeros == {90001, 90002, 90003, 90004}

    def test_a_excluida_nunca_entra(self, cliente):
        """⚠️ Excluída no ERP não é "fechada", é inexistente."""
        for so_abertas in (0, 1):
            r = cliente.get(
                f"/api/os/por-situacao?desde=2026-10-01&so_abertas={so_abertas}",
                headers=CAB)
            assert 90006 not in {o["numero_os"] for o in r.json()["os"]}

    def test_so_abertas_tira_a_finalizada(self, cliente):
        r = cliente.get("/api/os/por-situacao?desde=2026-10-24&so_abertas=1",
                        headers=CAB)
        numeros = {o["numero_os"] for o in r.json()["os"]}
        assert 90003 not in numeros   # Finalizado
        assert 90001 in numeros

    def test_o_nome_do_tipo_vem_do_dicionario(self, cliente):
        """🚨 Desde 29/10 o dicionário tem os 28 do catálogo, não os 5 da rota
        curta — era a rota curta que fazia 189 OS aparecerem sem nome."""
        r = cliente.get("/api/os/por-situacao?desde=2026-10-24", headers=CAB)
        um = next(o for o in r.json()["os"] if o["numero_os"] == 90001)
        assert um["tipo_nome"] == "Solicitação de Cliente"

    def test_zero_e_nulo_sao_distinguidos(self, cliente):
        """🚨 `0` ≠ `NULL`: `0` é "o ERP gravou zero" e `NULL` é "a varredura
        não leu". Já custou uma coluna inteira em 22/10."""
        r = cliente.get("/api/os/por-situacao?desde=2026-10-24&so_abertas=0",
                        headers=CAB)
        zero = next(o for o in r.json()["os"] if o["numero_os"] == 90004)
        assert zero["situacao_zero"] is True
        assert zero["sem_situacao"] is False
        assert zero["tem_coluna"] is False

    def test_a_os_conhecida_tem_coluna(self, cliente):
        r = cliente.get("/api/os/por-situacao?desde=2026-10-24", headers=CAB)
        um = next(o for o in r.json()["os"] if o["numero_os"] == 90001)
        assert um["tem_coluna"] is True

    def test_placa_e_tecnico_vem_partidos(self, cliente):
        r = cliente.get("/api/os/por-situacao?desde=2026-10-24", headers=CAB)
        um = next(o for o in r.json()["os"] if o["numero_os"] == 90001)
        assert um["placas"] == [{"placa": "ABC1D23", "veiculo": "zz"}]
        assert um["tecnicos"][0]["usuario_id"] == 14316
        assert um["tecnicos"][0]["vinculos"] == 1

    @pytest.mark.parametrize("torta", ["24/10/2026", "2026-13-01", "ontem"])
    def test_data_torta_e_recusada_com_422(self, cliente, torta):
        r = cliente.get(f"/api/os/por-situacao?desde={torta}", headers=CAB)
        assert r.status_code == 422, r.text

    def test_sem_desde_nao_passa(self, cliente):
        """⚠️ `desde` não tem padrão de propósito: um padrão aqui esconderia a
        decisão D9 dele sobre a data matriz dentro desta rota."""
        assert cliente.get("/api/os/por-situacao",
                           headers=CAB).status_code == 422

    def test_o_teto_e_DITO_quando_bate(self, cliente):
        """🚨 Cortado em silêncio é o que não se pode fazer."""
        r = cliente.get("/api/os/por-situacao?desde=2026-10-01&teto=2",
                        headers=CAB)
        assert r.json()["no_teto"] is True
        assert len(r.json()["os"]) == 2

    def test_teto_fora_da_faixa_e_recusado(self, cliente):
        for valor in (0, 9999):
            assert cliente.get(
                f"/api/os/por-situacao?desde=2026-10-01&teto={valor}",
                headers=CAB).status_code == 422


# ============================================================================
# POST /api/os/criar
# ============================================================================
class TestCriar:
    CORPO = {"cliente_id": 998063, "tipo_id": 1782, "problema_id": 12760,
             "situacao_id": 38, "prioridade_id": 382,
             "descricao": "zz teste de rota", "produto_servico_id": 670990}

    def test_o_ensaio_a_seco_responde_e_nao_escreve(self, cliente, monkeypatch):
        def nao_devia(*a, **k):
            raise AssertionError("o ensaio a seco escreveu no Harmonit")

        monkeypatch.setattr(os_ponte, "harmonit_post", nao_devia)
        r = cliente.post("/api/os/criar",
                         json={**self.CORPO, "conferir": True}, headers=CAB)
        assert r.status_code == 200, r.text
        assert r.json()["conferido_sem_gravar"] is True
        assert r.json()["corpo"]["id"] == 0

    def test_a_criacao_relê_e_confere(self, cliente, monkeypatch):
        async def postar(caminho, corpo):
            return {"data": {"numeroOrdem": 90100, "ordemServicoId": 990100}}

        async def ler(caminho, params=None):
            return {"data": {"id": 990100, "numeroOrdem": 90100, "tipo": 1782,
                             "problema": 12760, "situacaoId": 38,
                             "prioridade": 382, "parceiro": 998063}}

        monkeypatch.setattr(os_ponte, "harmonit_post", postar)
        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        r = cliente.post("/api/os/criar", json=self.CORPO, headers=CAB)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "criada": True, "numero_os": 90100,
                            "os_id": 990100, "situacao_id": 38,
                            "cliente_id": 998063, "divergencias": None}

    @pytest.mark.parametrize("falta", ["cliente_id", "tipo_id", "problema_id",
                                       "situacao_id", "prioridade_id",
                                       "descricao"])
    def test_corpo_incompleto_e_recusado_com_422(self, cliente, falta):
        """🚨 Nada de catálogo tem padrão: um padrão aqui faria a ponte decidir
        regra de negócio que é do MoviZap."""
        corpo = dict(self.CORPO)
        corpo.pop(falta)
        assert cliente.post("/api/os/criar", json=corpo,
                            headers=CAB).status_code == 422

    def test_resposta_sem_numero_nao_e_falhou(self, cliente, monkeypatch):
        """🚨 O PIOR CASO, pelo caminho HTTP: pode haver OS criada e nós não
        sabermos qual. Responde 200 com `criada: null` — não um erro, porque
        erro faria quem chama tentar de novo e abrir a segunda."""
        async def postar(caminho, corpo):
            return {"data": {}}

        monkeypatch.setattr(os_ponte, "harmonit_post", postar)
        r = cliente.post("/api/os/criar", json=self.CORPO, headers=CAB)
        assert r.status_code == 200, r.text
        assert r.json()["criada"] is None
        assert "nascem duas" in r.json()["motivo"]
