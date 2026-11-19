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

from fastapi import FastAPI, HTTPException  # noqa: E402
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
            os_id INTEGER, tecnicos_json TEXT,
            -- 🔵 A prioridade entrou no cache em 29/10: o card fechado precisa
            -- dela, e a varredura ja lia a OS inteira.
            prioridade INTEGER,
            -- 🔵 O termo entrou em 05/11 (Area E). 🚨 NAO e campo do Harmonit:
            -- e extraido do texto da `descricao`, que nao esta neste cache.
            termo TEXT)""")
    conn.execute("CREATE TABLE tipos_os (tipo_id INTEGER PRIMARY KEY, nome TEXT)")
    conn.executemany("INSERT INTO tipos_os VALUES (?, ?)",
                     [(1783, "Solicitação de Cliente"), (76, "Instalação rastreador")])
    for numero, situacao, status, cliente, previsao, excluida in OS_DE_MENTIRA:
        conn.execute(
            """INSERT INTO os_historico
                   (numero_os, situacao_id, status_str, cliente_id,
                    data_previsao, excluida, tipo, os_id, visto_em,
                    atualizado_em, oficinas_json, tecnicos_json, prioridade,
                    termo)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (numero, situacao, status, cliente, previsao, excluida, 1783,
             900000 + numero, "2026-10-29T18:00:00Z", "2026-10-29T18:00:00Z",
             '[{"veiculoPlaca": "ABC1D23", "veiculoNome": "zz"}]',
             '[{"usuarioId": 14316, "nome": "zz Tecnico"}]', 382,
             # ⚠️ A 90004 fica SEM termo de proposito: OS sem termo e o caso
             # normal (27 de 200 medidas) e tem de atravessar a rota como nulo.
             None if numero == 90004 else "88%02d" % (numero - 90000)))
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

    def test_o_termo_vem_na_rota(self, cliente):
        """🔵 Área E (05/11): o card escreve *"OS 90001 · TERMO 8801"*, e a
        busca do painel casa por ele. Sem este campo na rota, achar uma OS
        pelo termo custaria **uma leitura do ERP por card**."""
        r = cliente.get("/api/os/por-situacao?desde=2026-10-24", headers=CAB)
        um = next(o for o in r.json()["os"] if o["numero_os"] == 90001)
        assert um["termo"] == "8801"

    def test_os_sem_termo_devolve_nulo_e_nao_some(self, cliente):
        """⚠️ **OS SEM TERMO É NORMAL** — 27 de 200 medidas em 05/11 (venda,
        cartão RFID, manutenção). Ela continua no quadro, com `termo` nulo;
        quem desenha escreve só o número da OS."""
        r = cliente.get("/api/os/por-situacao?desde=2026-10-24&so_abertas=0",
                        headers=CAB)
        sem = next(o for o in r.json()["os"] if o["numero_os"] == 90004)
        assert sem["termo"] is None

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


# ============================================================================
# A GUARDA DO CORPO E A TRAVA REORDENADA — 18/11
# ============================================================================
class TestAGuardaDoCorpo:
    """🔵 Decisão dele, 18/11: leitura furada **aborta e não escreve**.

    🚨 O DEFEITO QUE ESTE TESTE GUARDA. Medido em 18/11: as 2 únicas recusas
    de `SalvarOrdemServico` em 650 chamadas foram *"o Produto é obrigatório"*,
    e as duas caíram em minutos nos quais as leituras da OS estavam **todas**
    falhando. Como **0 das 643** OS da base carece de produto, a recusa veio de
    corpo montado a partir de leitura degradada — e a rota só checava
    `if not antes`, que pega objeto vazio e **deixa passar objeto parcial**.

    🚨 E A RECUSA FOI SORTE: nos campos que o Harmonit não valida, a escrita
    gravaria nulo em cima de dado real, calada. Este teste é o que impede isso
    de voltar.
    """

    # A OS 90001 do banco de mentira, lida PELA METADE: tem id e número, e
    # nada do que a escrita precisa. É o retrato de uma leitura degradada.
    PARCIAL = {"id": 990001, "numeroOrdem": 90001, "empresaId": 98}

    COMPLETA = {"id": 990001, "numeroOrdem": 90001, "empresaId": 98,
                "tipo": 1783, "problema": 12760, "situacaoId": 38,
                "prioridade": 382, "produtoId": 670990, "parceiro": 998063,
                "dataPrevisao": "25/10/2026 09:00:00", "status": 2,
                "descricao": "zz", "solucaoTecnica": None,
                "localServico": 1, "tecnico": []}

    def _ler(self, monkeypatch, os_dict, proibir_escrita=True):
        async def ler(caminho, params=None):
            return {"data": dict(os_dict)}

        async def postar(caminho, corpo):
            if proibir_escrita:
                raise AssertionError(
                    "escreveu no Harmonit com o corpo furado: %r" % corpo)
            return {"data": {}}

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_post", postar)

    def test_a_SITUACAO_nao_grava_com_corpo_furado(self, cliente, monkeypatch):
        """🚨 A rota do CARD é onde isto pesa mais: 15 das 95 passagens
        falharam por leitura, e uma leitura meio-degradada gravaria nulo em
        cima da OS inteira."""
        self._ler(monkeypatch, self.PARCIAL)
        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "conferir_antes": False}, headers=CAB)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is False
        assert corpo["gravou"] is False
        assert corpo["causa"] == "corpo_furado"
        # 🔵 Pendência 4 dele: o motivo diz o que é E o que significa.
        assert "veio incompleta" in corpo["motivo"]
        assert "apagaria dado da OS" in corpo["motivo"]
        assert "produtoServicoId" in corpo["motivo"]

    def test_o_ENDERECO_tambem_nao_grava(self, cliente, monkeypatch):
        """O montador é um só, a proteção também."""
        self._ler(monkeypatch, self.PARCIAL)
        r = cliente.post("/api/os/endereco",
                         json={"numero_os": 90001, "endereco": "Rua zz",
                               "numero": "10"}, headers=CAB)
        assert r.json()["causa"] == "corpo_furado", r.text

    def test_o_ENSAIO_A_SECO_tambem_acusa(self, cliente, monkeypatch):
        """🚨 A guarda vem ANTES do `conferir`: o ensaio existe para dizer o
        que aconteceria, e dizer "pode gravar" sobre um corpo que a guarda
        recusaria seria o ensaio mentindo."""
        self._ler(monkeypatch, self.PARCIAL)
        r = cliente.post("/api/os/endereco",
                         json={"numero_os": 90001, "endereco": "Rua zz",
                               "conferir": True}, headers=CAB)
        assert r.json()["causa"] == "corpo_furado", r.text
        assert "conferido_sem_gravar" not in r.json()

    def test_a_PRIORIDADE_tambem_nao_grava(self, cliente, monkeypatch):
        self._ler(monkeypatch, self.PARCIAL)
        r = cliente.post("/api/os/prioridade",
                         json={"numero_os": 90001, "prioridade_id": 383},
                         headers=CAB)
        assert r.json()["causa"] == "corpo_furado", r.text

    def test_leitura_COMPLETA_grava_normalmente(self, cliente, monkeypatch):
        """⚠️ A guarda não pode virar trava: com a OS inteira na mão, grava.

        🔵 *"somente o cache ou timeout daria erro, pois as informações de
        preenchimento estao corretas"* — e os 0 de 643 confirmam.
        """
        estado = {"os": dict(self.COMPLETA)}

        async def ler(caminho, params=None):
            return {"data": dict(estado["os"])}

        async def postar(caminho, corpo):
            estado["os"]["situacaoId"] = corpo["situacaoId"]
            return {"data": {}}

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_post", postar)
        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "conferir_antes": False}, headers=CAB)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True, r.json()
        assert r.json()["gravou"] is True

    def test_zero_conta_como_AUSENCIA(self, cliente, monkeypatch):
        """⚠️ `0` não é id: `tipoId` 0 não existe no catálogo do Harmonit, e
        foi um `produtoServicoId` vazio que gerou a recusa de 08/09."""
        self._ler(monkeypatch, dict(self.COMPLETA, produtoId=0))
        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "conferir_antes": False}, headers=CAB)
        assert r.json()["causa"] == "corpo_furado", r.text


class TestARetentativaDaLeitura:
    """🚨 100% das 15 falhas de passagem medidas desde 29/10 foram a MESMA:
    *"nao deu para ler a OS no Harmonit antes de mover"*. O pool do Harmonit
    esgota todo dia (46 em 17/11, 83 em 14/11, 164 em 07/11) e a pior leitura
    levou 15,8s.

    ⚠️ E quem retentava era o OPERADOR: na OS 17105, em 09/11, nove cliques
    na mesma OS -- nove leituras de 15s contra um pool ja esgotado.
    """

    COMPLETA = TestAGuardaDoCorpo.COMPLETA

    def test_a_segunda_tentativa_SALVA_a_escrita(self, cliente, monkeypatch):
        """A 1ª leitura estoura, a 2ª vai, e a escrita acontece UMA vez."""
        chamadas = {"leituras": 0, "escritas": 0}
        estado = {"situacao": 38}

        async def ler(caminho, params=None):
            chamadas["leituras"] += 1
            if chamadas["leituras"] == 1:
                raise RuntimeError("pool esgotado (encenado)")
            return {"data": dict(self.COMPLETA, situacaoId=estado["situacao"])}

        async def postar(caminho, corpo):
            chamadas["escritas"] += 1
            estado["situacao"] = corpo["situacaoId"]
            return {"data": {}}

        async def sem_espera(_):
            return None

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_post", postar)
        monkeypatch.setattr(os_ponte.asyncio, "sleep", sem_espera)

        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "conferir_antes": False}, headers=CAB)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True, r.json()
        # 🚨 UMA escrita, nao duas: so a LEITURA retenta.
        assert chamadas["escritas"] == 1

    def test_as_duas_leituras_falhando_recusa_COM_a_causa(self, cliente,
                                                          monkeypatch):
        """🔵 Pendência 4 dele: a recusa diz a causa, não `HTTPException`."""
        chamadas = {"leituras": 0}

        async def ler(caminho, params=None):
            chamadas["leituras"] += 1
            raise RuntimeError("pool esgotado (encenado)")

        async def postar(caminho, corpo):
            raise AssertionError("escreveu sem ter lido a OS")

        async def sem_espera(_):
            return None

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_post", postar)
        monkeypatch.setattr(os_ponte.asyncio, "sleep", sem_espera)

        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "conferir_antes": False}, headers=CAB)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is False
        assert corpo["gravou"] is False
        assert corpo["causa"] == "leitura_falhou"
        assert "2 tentativas" in corpo["motivo"]
        assert "sobrecarregado" in corpo["motivo"]
        assert "Nada foi escrito" in corpo["motivo"]
        # ⚠️ Tentou as duas, nao uma nem tres.
        assert chamadas["leituras"] == os_ponte.LEITURAS_DA_OS == 2

    def test_SO_A_LEITURA_retenta(self):
        """⚠️ GET é idempotente; POST não. Repetir escrita cega nesta camada
        abriria o segundo compromisso ou a segunda OS."""
        import inspect
        fonte = inspect.getsource(os_ponte._ler_os)
        assert "harmonit_get" in fonte
        assert "harmonit_post" not in fonte


class TestOSQueNaoExisteNaoEhPoolEsgotado:
    """🚨 ESTA CLASSE GUARDA UM DEFEITO MEU, no ar por uma hora em 18/11.

    A retentativa da leitura trouxe junto um texto único, e ele passou a dizer
    *"o ERP esta sobrecarregado"* também sobre OS que simplesmente **não
    existe**. A prova ao vivo na OS 999999, depois do restart, devolveu
    "sobrecarregado" sobre um Harmonit que respondeu de primeira, em 140ms.

    ⚠️ 🔵 A pendência dele era *"os motivos de recusa deve aparecer descritos
    ao inves de erro generico, para que me tragam o problema ja cientes"* — e
    motivo descrito e **errado** é pior que genérico: manda consertar a coisa
    errada. É `M12` dentro da própria correção que o pedido dele gerou.

    🚨 E o custo não é só a frase: a OS inexistente era lida **duas** vezes,
    contra um pool que esgota todo dia.
    """

    COMPLETA = TestAGuardaDoCorpo.COMPLETA

    def test_nao_encontrada_tem_CAUSA_PROPRIA_e_nao_fala_de_sobrecarga(
            self, cliente, monkeypatch):
        chamadas = {"leituras": 0}

        async def ler(caminho, params=None):
            chamadas["leituras"] += 1
            raise HTTPException(
                status_code=502,
                detail="Harmonit: Ordem de Serviço não encontrada")

        async def postar(caminho, corpo):
            raise AssertionError("escreveu numa OS que nao existe")

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_post", postar)

        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 999999, "situacao_id": 1316,
                               "conferir_antes": False}, headers=CAB)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is False
        assert corpo["gravou"] is False
        assert corpo["causa"] == "os_nao_encontrada"
        assert "999999" in corpo["motivo"]
        assert "nao existe" in corpo["motivo"]
        # 🚨 A frase NAO pode culpar o ERP: ele respondeu, e respondeu claro.
        assert "sobrecarregado" not in corpo["motivo"]
        assert "tentativas" not in corpo["motivo"]
        # ⚠️ E NAO RETENTA: repetir nao faz a OS passar a existir.
        assert chamadas["leituras"] == 1

    def test_pool_esgotado_CONTINUA_dizendo_sobrecarregado(self, cliente,
                                                           monkeypatch):
        """⚠️ Guarda-de-regressão: separar os dois casos não pode apagar o
        primeiro. Este passa no código antigo **e** no novo, de propósito."""
        async def ler(caminho, params=None):
            raise RuntimeError("pool esgotado (encenado)")

        async def postar(caminho, corpo):
            raise AssertionError("escreveu sem ter lido a OS")

        async def sem_espera(_):
            return None

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_post", postar)
        monkeypatch.setattr(os_ponte.asyncio, "sleep", sem_espera)

        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "conferir_antes": False}, headers=CAB)
        corpo = r.json()
        assert corpo["causa"] == "leitura_falhou"
        assert "sobrecarregado" in corpo["motivo"]

    def test_timeout_NAO_vira_os_inexistente(self, cliente, monkeypatch):
        """🚨 O inverso, que é o erro mais caro dos dois: dizer que a OS não
        existe porque o ERP demorou afirmaria um fato sobre o dado dele a
        partir de um defeito nosso — e mandaria alguém conferir um número que
        está certo."""
        async def ler(caminho, params=None):
            raise HTTPException(status_code=504,
                                detail="tempo esgotado (encenado)")

        async def sem_espera(_):
            return None

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte.asyncio, "sleep", sem_espera)

        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "conferir_antes": False}, headers=CAB)
        assert r.json()["causa"] == "leitura_falhou"

    def test_a_frase_de_os_inexistente_EXISTE_no_MoviZap(self):
        """🚨 A ponte nomeia a causa, o MoviZap escreve a frase — causa nova
        sem frase sai por extenso, e o texto cru do FPSL é bom, mas a tabela é
        onde a tela fala. ⚠️ E ela NÃO se retenta."""
        import pathlib
        fonte = pathlib.Path(__file__).resolve()
        # O arquivo do MoviZap nao e importavel daqui (outra base, outro
        # venv), entao a trava le o texto -- e o que ela guarda e que as duas
        # metades da mesma verdade nao se separem sem alguem notar.
        caminho = None
        for raiz in (fonte.parents[2] / "movizap_painel" / "movizap",
                     fonte.parents[3] / "movizap_painel" / "movizap"):
            if (raiz / "fpsl_ponte.py").exists():
                caminho = raiz / "fpsl_ponte.py"
                break
        if caminho is None:
            pytest.skip("o MoviZap nao esta ao lado desta base")
        texto = caminho.read_text(encoding="utf-8")
        assert '"os_nao_encontrada":' in texto
        corte = texto.split("CAUSAS_QUE_NAO_SE_RETENTA", 1)[1][:400]
        assert "os_nao_encontrada" in corte


class TestOOrcamentoDaChamada:
    """🚨 Os tetos estavam ANINHADOS AO CONTRÁRIO: o MoviZap esperava 25s pela
    ponte e o cliente do Harmonit esperava 30s **por chamada** — o de dentro
    maior que o de fora — e a rota faz três chamadas. O resultado era
    `incerto: True`: a escrita pode ter chegado e ninguém sabe. É o único
    estado que não se audita.
    """

    COMPLETA = TestAGuardaDoCorpo.COMPLETA

    def test_prazo_consumido_NAO_comeca_a_escrever(self, cliente, monkeypatch):
        """🚨 Desistir aqui é verdade: nada foi escrito. Começar e não
        terminar é o que produz o `incerto` do outro lado."""
        async def ler(caminho, params=None):
            return {"data": dict(self.COMPLETA)}

        async def postar(caminho, corpo):
            raise AssertionError("comecou a escrever sem prazo para terminar")

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_post", postar)
        # O prazo nasce ja estourado: e o retrato da leitura que levou 15,8s
        # duas vezes.
        monkeypatch.setattr(os_ponte, "PRAZO_DA_ESCRITA", 0.0)

        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "conferir_antes": False}, headers=CAB)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is False
        assert corpo["gravou"] is False
        assert corpo["causa"] == "leitura_falhou"
        assert "nada foi" in corpo["motivo"].lower()

    def test_a_reserva_cabe_dentro_do_prazo(self):
        """⚠️ A reserva para gravar e reler tem de ser MENOR que o prazo, senao
        nenhuma escrita comecaria nunca."""
        assert os_ponte.RESERVA_PARA_GRAVAR_E_RELER < os_ponte.PRAZO_DA_ESCRITA

    def test_A_CONTA_DOS_TRES_NUMEROS_FECHA(self):
        """🚨 A TRAVA QUE IMPEDE O `incerto` DE VOLTAR.

        Sao tres numeros em dois repositorios, e mexer num sem os outros
        reabre exatamente o defeito de 18/11: teto de dentro maior que o de
        fora, a rota comecando o que nao tem tempo de terminar, e o MoviZap
        desistindo primeiro.

        🔵 Decididos por ele em 18/11: 18s por chamada ao Harmonit, 60s de
        ponte, e aqui 55s de prazo com 22s de reserva.

        ⚠️ O teto da ponte (60s) vive no OUTRO repositorio
        (`movizap/fpsl_ponte.py`) e este teste nao o ve. O que ele guarda e a
        metade que mora aqui -- e o comentario de cada um nomeia o outro.
        """
        from fpsl_weso import harmonit_client

        por_chamada = harmonit_client.TETO_POR_CHAMADA
        assert por_chamada == 18, (
            "o teto por chamada mudou; refazer a conta com os outros dois")

        # Duas leituras no pior caso, mais a reserva de gravar e reler.
        pior_caso = por_chamada * os_ponte.LEITURAS_DA_OS             + os_ponte.ESPERA_ENTRE_LEITURAS * (os_ponte.LEITURAS_DA_OS - 1)             + os_ponte.RESERVA_PARA_GRAVAR_E_RELER
        assert pior_caso <= 60.0, (
            f"o pior caso da 4 chamadas = {pior_caso}s, e a ponte do MoviZap "
            f"espera 60s -- o de dentro nao pode sobreviver ao de fora")

        # E a reserva tem de caber em duas chamadas (gravar + reler).
        assert os_ponte.RESERVA_PARA_GRAVAR_E_RELER >= por_chamada, (
            "a reserva nao cobre nem uma chamada: a escrita comecaria para "
            "morrer no meio")


class TestATravaReordenada:
    """🚨 O ramo "já está no destino" passou à FRENTE da trava em 18/11.

    O motivo é a retentativa: se a 1ª escrita chegou e a resposta se perdeu na
    volta, na retentativa o ERP já está no destino — e a trava, comparando com
    a `situacao_esperada` que a tela carregou, recusaria com *"alguem mudou no
    meio"*. Seria **conflito falso sobre a escrita que deu certo**, e justo no
    caso que a retentativa existe para resolver.
    """

    COMPLETA = TestAGuardaDoCorpo.COMPLETA

    def _ler(self, monkeypatch, situacao):
        async def ler(caminho, params=None):
            return {"data": dict(self.COMPLETA, situacaoId=situacao)}

        async def postar(caminho, corpo):
            raise AssertionError("gravou a OS inteira por nada")

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_post", postar)

    def test_ja_no_destino_com_esperada_ANTIGA_e_SUCESSO(self, cliente,
                                                         monkeypatch):
        """🚨 ESTE É O CONFLITO FALSO, e antes de 18/11 ele aconteceria.

        O ERP está em 1316 (a escrita chegou); a tela carregou 38. Pedir 1316
        de novo é a retentativa — e a resposta tem de ser sucesso, não
        conflito.
        """
        self._ler(monkeypatch, 1316)
        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "situacao_esperada": 38,
                               "conferir_antes": True}, headers=CAB)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is True, corpo
        assert corpo["gravou"] is False
        assert "ja estava nesta situacao" in corpo["motivo"]
        assert "conflito" not in corpo

    def test_a_trava_CONTINUA_recusando_situacao_diferente(self, cliente,
                                                           monkeypatch):
        """⚠️ A trava não enfraqueceu: só saiu da frente do caso em que o ERP
        já está onde se queria chegar."""
        self._ler(monkeypatch, 16487)
        r = cliente.post("/api/os/situacao",
                         json={"numero_os": 90001, "situacao_id": 1316,
                               "situacao_esperada": 38,
                               "conferir_antes": True}, headers=CAB)
        corpo = r.json()
        assert corpo["ok"] is False, corpo
        assert corpo["conflito"] is True
        assert corpo["causa"] == "conflito_de_situacao"
        assert "recarregue o painel" in corpo["motivo"]


# ============================================================================
# AGENDAR O TÉCNICO DO MOVIZAP NA OS — 18/11
# ============================================================================
class TestAgendarTecnico:
    """🔵 Decisão dele, 17/11: *"Mesmo se tiver técnico na OS, deve inserir o
    que foi fechado no MoviZap e agendar nele. Os demais devem ser ignorados,
    vão ficar lá e não interessam para a validação do MoviZap."*

    🚨 POR HTTP e não só por função: o que estava quebrado em 17/11 era a ROTA
    -- a função `_escolher_vinculo` recusava e a rota devolvia 200 com
    `ok: False`, que é exatamente o par que teste de função não mede.

    ⚠️ A OS 90001 do banco de mentira é da VELASCO e existe na `os_historico`:
    sem isso a rota recusaria por *"nao sei o cliente desta OS"*, que é outro
    motivo e esconderia este.
    """

    EMPRESA = {"id": 1166101, "usuarioId": 629,
               "nomeTecnico": "MOVISAT SOLUCOES TECNOLOGICAS LTDA. - ME ",
               "email": "comercial@movisat.com.br", "agendamentoId": 0}
    OUTRO = {"id": 700, "usuarioId": 9617, "nomeTecnico": "Karla Alves",
             "email": "karla@movisat.com.br", "agendamentoId": 930447}

    CORPO = {"numero_os": 90001, "inicio": "2026-11-20T14:30:00",
             "tecnico_id": 14262}

    def _dubles(self, monkeypatch, antes, compromisso=944000):
        """Encena o Harmonit: a OS antes, a linha criada e o compromisso.

        🚨 A rota RELÊ a OS depois de criar o vínculo e depois de agendar, e
        é essa releitura que é a prova. O dublê devolve estados diferentes a
        cada leitura, senão o teste provaria o retorno da rota em vez do
        estado -- que é justamente o que o código se recusa a fazer.
        """
        estado = {"tecnico": list(antes)}
        chamadas = {"salvar_vinculo": 0, "agendar": [], "leituras": 0}

        async def postar(caminho, corpo):
            if caminho.endswith("SalvarTecnicoOrdemServico"):
                chamadas["salvar_vinculo"] += 1
                estado["tecnico"] = list(estado["tecnico"]) + [
                    {"id": 1199999, "usuarioId": corpo["tecnicoId"],
                     "nomeTecnico": "Franck",
                     "email": "997394026@movisat.com.br",
                     "agendamentoId": 0}]
                return {"data": {"osxTecId": 1199999}}
            chamadas["agendar"].append(corpo)
            estado["tecnico"] = [
                dict(t, agendamentoId=compromisso)
                if t.get("id") == corpo["ordemServicoxTecnicoId"] else t
                for t in estado["tecnico"]]
            return {"data": {}}

        async def ler(caminho, params=None):
            chamadas["leituras"] += 1
            return {"data": {"id": 990001, "numeroOrdem": 90001,
                             "empresaId": 98,
                             "tecnico": list(estado["tecnico"])}}

        monkeypatch.setattr(os_ponte, "harmonit_post", postar)
        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        return chamadas

    def test_a_rota_exige_a_chave(self, cliente):
        assert cliente.post("/api/os/agendar-tecnico",
                            json=self.CORPO).status_code == 422

    def test_OS_SEM_TECNICO_NENHUM_ganha_a_linha_e_agenda(self, cliente,
                                                          monkeypatch):
        """🚨 O caso de 3 dos 6 parados em 18/11 (518, 2227, 2228): a OS que o
        painel do FPSL cria nasce sem técnico, e a rota recusava antes de olhar
        o `tecnico_id`. 🔵 *"nas próximas deve criar o agendamento na OS sim"*.
        """
        chamadas = self._dubles(monkeypatch, antes=[])
        r = cliente.post("/api/os/agendar-tecnico", json=self.CORPO, headers=CAB)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is True, corpo
        assert corpo["agendamento_id"] == 944000
        assert corpo["vinculo_criado"] is True
        assert chamadas["salvar_vinculo"] == 1

    def test_so_a_EMPRESA_na_OS_tambem_agenda(self, cliente, monkeypatch):
        """🚨 O caso exato da OS 17128 (agendamento 2226). A linha da empresa
        629 não é técnico: a OS é lida como vazia, que é o que ela é."""
        chamadas = self._dubles(monkeypatch, antes=[self.EMPRESA])
        r = cliente.post("/api/os/agendar-tecnico", json=self.CORPO, headers=CAB)
        assert r.json()["ok"] is True, r.text
        assert chamadas["salvar_vinculo"] == 1

    def test_os_DEMAIS_tecnicos_nao_recusam_e_ficam_INTACTOS(self, cliente,
                                                             monkeypatch):
        """*"Os demais devem ser ignorados, vão ficar lá"* -- dos dois lados.

        ⚠️ Karla já tem o compromisso 930447: ele continua dela, e o
        `AgendarTecnico` só é chamado para a linha nova.
        """
        chamadas = self._dubles(monkeypatch, antes=[self.EMPRESA, self.OUTRO])
        r = cliente.post("/api/os/agendar-tecnico", json=self.CORPO, headers=CAB)
        assert r.json()["ok"] is True, r.text
        assert len(chamadas["agendar"]) == 1
        assert chamadas["agendar"][0]["ordemServicoxTecnicoId"] == 1199999
        # 🚨 O compromisso de outra pessoa não foi tocado nem reaproveitado.
        assert chamadas["agendar"][0]["ordemServicoxTecnicoId"] != self.OUTRO["id"]
        assert r.json()["agendamento_id"] != 930447

    def test_o_tecnico_que_JA_ESTA_na_OS_usa_a_linha_dele(self, cliente,
                                                          monkeypatch):
        """🔵 18/11: *"usa a linha existente"* -- nenhuma linha nova."""
        ja_la = {"id": 2, "usuarioId": 14262, "nomeTecnico": "Franck",
                 "email": "997394026@movisat.com.br", "agendamentoId": 0}
        chamadas = self._dubles(monkeypatch, antes=[self.EMPRESA, ja_la])
        r = cliente.post("/api/os/agendar-tecnico", json=self.CORPO, headers=CAB)
        assert r.json()["ok"] is True, r.text
        assert r.json()["vinculo_criado"] is False
        assert chamadas["salvar_vinculo"] == 0
        assert chamadas["agendar"][0]["ordemServicoxTecnicoId"] == 2

    def test_linha_OCUPADA_do_mesmo_tecnico_ganha_a_segunda(self, cliente,
                                                            monkeypatch):
        """🔵 21/10 e reafirmado em 18/11: *"não tem problema se já tiver
        agendamento no horário tbm"*. A recusa `TecnicoJaAgendado` é do
        VÍNCULO, nunca do técnico."""
        ocupada = {"id": 2, "usuarioId": 14262, "nomeTecnico": "Franck",
                   "email": "997394026@movisat.com.br", "agendamentoId": 944780}
        chamadas = self._dubles(monkeypatch, antes=[ocupada])
        r = cliente.post("/api/os/agendar-tecnico", json=self.CORPO, headers=CAB)
        assert r.json()["ok"] is True, r.text
        assert r.json()["vinculo_criado"] is True
        assert chamadas["salvar_vinculo"] == 1
        assert chamadas["agendar"][0]["ordemServicoxTecnicoId"] == 1199999

    def test_SEM_tecnico_id_a_OS_vazia_continua_recusando(self, cliente,
                                                          monkeypatch):
        """⚠️ A guarda não caiu, mudou de lugar: sem vínculo e sem telefone
        que case, continua não havendo em quem agendar."""
        self._dubles(monkeypatch, antes=[])
        corpo = dict(self.CORPO)
        corpo.pop("tecnico_id")
        r = cliente.post("/api/os/agendar-tecnico", json=corpo, headers=CAB)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is False
        assert "nao tem tecnico vinculado" in r.json()["motivo"]

    def test_a_OS_fora_do_cache_recusa_por_OUTRO_motivo(self, cliente,
                                                        monkeypatch):
        """🚨 Dois motivos diferentes não podem virar um: a OS que não está na
        `os_historico` não tem `clienteId` no corpo do Harmonit, e isso não é
        problema de técnico."""
        self._dubles(monkeypatch, antes=[])
        r = cliente.post("/api/os/agendar-tecnico",
                         json={**self.CORPO, "numero_os": 97777}, headers=CAB)
        assert r.json()["ok"] is False
        assert "nao sei o cliente desta OS" in r.json()["motivo"]


# ============================================================================
# O AVISO DE CONFLITO DIZ O NOME DA ETAPA — 11/11
# ============================================================================
class TestOAvisoDeConflitoDizONome:
    """🔵 Ele: *"O aviso de, po exemplo: 'a OS 17118 esta na situação 890 no
    harmonit, e a tela carregou 38...' ajustar para aparecer o nome das etapas
    entre \" \" ao invés do numero, somente nesse aviso."*

    🚨 ESTE AVISO É LIDO POR QUEM OPERA, e era o único da ponte que mostrava
    número de situação a quem move card. "890" não diz nada para quem está
    olhando colunas com nome.
    """

    def test_o_nome_entre_aspas_no_lugar_do_numero(self):
        assert os_ponte._nome_da_situacao(890) == '"Agendar serviço"'
        assert os_ponte._nome_da_situacao(38) == '"Novo Solicitação 1ª"'

    def test_situacao_DESCONHECIDA_cai_no_numero(self):
        """⚠️ Nunca um rótulo inventado: este aviso dispara justamente quando a
        OS está onde a tela não esperava, e isso inclui situação fora das 17.
        "situacao 99999" diz a verdade; um nome inventado não."""
        assert os_ponte._nome_da_situacao(99999) == "situacao 99999"

    def test_nulo_e_legitimo_e_tem_frase_propria(self):
        """A tela manda `situacao_esperada` nulo quando o card nunca teve
        situação lida."""
        assert os_ponte._nome_da_situacao(None) == "nenhuma situacao lida"

    def test_o_nome_sai_do_CATALOGO_do_arquivo(self):
        """🚨 Uma segunda lista de nomes divergiria na primeira renomeação -- e
        as etapas JÁ foram renomeadas uma vez (30/10: a 15694 era "Serviço
        Realizado" e virou "Atendimento finalizado")."""
        for sid, nome in os_ponte._SITUACOES_DO_PAINEL:
            assert os_ponte._nome_da_situacao(sid) == f'"{nome}"', sid

    def test_o_aviso_de_conflito_NAO_tem_mais_o_numero_cru(self):
        """A prova na frase montada, e não só no auxiliar."""
        import inspect
        fonte = inspect.getsource(os_ponte.gravar_situacao
                                  if hasattr(os_ponte, "gravar_situacao")
                                  else os_ponte)
        trecho = fonte[fonte.index("A TRAVA DE CONCORR"):]
        trecho = trecho[:trecho.index("conflito")]
        assert "_nome_da_situacao(de)" in trecho
        assert "{de} no" not in trecho


# ============================================================================
# CANCELAR E REAGENDAR — 🔵 demanda dele, 18/11
# ============================================================================
class TestCancelarAgendamento:
    """🚨 A MEDIÇÃO NA VELASCO (OS 17105) DECIDIU ESTE DESENHO: `AgendarTecnico`
    com o `id` do compromisso **recusa** (H1 e H2), e o `DELETE` é o único
    caminho — mas ele leva **o compromisso E a linha do técnico** juntos. Não
    existe cancelar o compromisso deixando a linha.

    🔵 Por isso a regra dele: *"apaga, só se a linha for nossa"*.
    """

    NOSSA = {"id": 1199999, "usuarioId": 14262, "nomeTecnico": "Franck",
             "agendamentoId": 944000}
    DE_OUTRO = {"id": 700, "usuarioId": 9617, "nomeTecnico": "Karla Alves",
                "agendamentoId": 930447}

    def _dubles(self, monkeypatch, antes, apaga=True):
        estado = {"tecnico": list(antes)}
        chamadas = {"delete": [], "leituras": 0}

        async def ler(caminho, params=None):
            chamadas["leituras"] += 1
            return {"data": {"id": 990001, "numeroOrdem": 90001,
                             "tecnico": list(estado["tecnico"])}}

        async def apagar(caminho, params=None):
            chamadas["delete"].append(params)
            if apaga:
                estado["tecnico"] = [t for t in estado["tecnico"]
                                     if t.get("id") != params["id"]]
            return {"data": {}}

        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_delete", apagar)
        return chamadas

    def test_a_rota_exige_a_chave(self, cliente):
        assert cliente.post("/api/os/cancelar-agendamento", json={
            "numero_os": 90001, "agendamento_id": 944000,
            "vinculo_id": 1199999}).status_code == 422

    def test_linha_NOSSA_apaga_e_PROVA_pela_releitura(self, cliente,
                                                      monkeypatch):
        chamadas = self._dubles(monkeypatch, antes=[self.NOSSA])
        r = cliente.post("/api/os/cancelar-agendamento", json={
            "numero_os": 90001, "agendamento_id": 944000,
            "vinculo_id": 1199999, "vinculo_criado": True}, headers=CAB)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is True, corpo
        assert corpo["apagou"] is True
        # 🚨 Os TRÊS ids, como o swagger pede e como a Velasco provou.
        assert chamadas["delete"] == [{"osId": 990001, "id": 1199999,
                                       "agendaId": 944000}]
        # ⚠️ Releu DEPOIS de apagar: a prova é o estado, não o retorno.
        assert chamadas["leituras"] == 2

    def test_linha_QUE_NAO_E_NOSSA_recusa_SEM_NEM_LER(self, cliente,
                                                      monkeypatch):
        """🚨 Recusa antes de qualquer chamada ao Harmonit: não se gasta pool
        para descobrir que não se pode mexer. E o DELETE nunca sai."""
        chamadas = self._dubles(monkeypatch, antes=[self.DE_OUTRO])
        r = cliente.post("/api/os/cancelar-agendamento", json={
            "numero_os": 90001, "agendamento_id": 930447,
            "vinculo_id": 700, "vinculo_criado": False}, headers=CAB)
        corpo = r.json()
        assert corpo["ok"] is False
        assert corpo["apagou"] is False
        assert corpo["causa"] == "vinculo_nao_e_nosso"
        assert chamadas["delete"] == []
        assert chamadas["leituras"] == 0

    def test_SEM_O_CAMPO_tambem_recusa(self, cliente, monkeypatch):
        """⚠️ O padrão é `False`: chamador antigo, que não guardava o
        `vinculo_criado`, recebe a recusa em vez de arrancar a linha de outra
        pessoa. Quem não sabe não apaga."""
        chamadas = self._dubles(monkeypatch, antes=[self.NOSSA])
        r = cliente.post("/api/os/cancelar-agendamento", json={
            "numero_os": 90001, "agendamento_id": 944000,
            "vinculo_id": 1199999}, headers=CAB)
        assert r.json()["causa"] == "vinculo_nao_e_nosso"
        assert chamadas["delete"] == []

    def test_linha_JA_FORA_da_OS_e_SUCESSO(self, cliente, monkeypatch):
        """🚨 Já não está lá = feito, não erro. Devolver falha aqui faria a
        tela pedir para repetir o que já está pronto — e repetir um DELETE
        contra um pool esgotado é o *"só cansa a req"* dele."""
        chamadas = self._dubles(monkeypatch, antes=[self.DE_OUTRO])
        r = cliente.post("/api/os/cancelar-agendamento", json={
            "numero_os": 90001, "agendamento_id": 944000,
            "vinculo_id": 1199999, "vinculo_criado": True}, headers=CAB)
        corpo = r.json()
        assert corpo["ok"] is True, corpo
        assert corpo["apagou"] is False
        assert chamadas["delete"] == []

    def test_COMPROMISSO_TROCADO_na_nossa_linha_recusa(self, cliente,
                                                       monkeypatch):
        """⚠️ A linha é nossa, mas carrega outro compromisso: apagar levaria um
        compromisso que não é o alvo."""
        chamadas = self._dubles(
            monkeypatch, antes=[dict(self.NOSSA, agendamentoId=966835)])
        r = cliente.post("/api/os/cancelar-agendamento", json={
            "numero_os": 90001, "agendamento_id": 944000,
            "vinculo_id": 1199999, "vinculo_criado": True}, headers=CAB)
        corpo = r.json()
        assert corpo["ok"] is False
        assert corpo["causa"] == "compromisso_mudou"
        assert "966835" in corpo["motivo"]
        assert chamadas["delete"] == []

    def test_DELETE_aceito_e_a_linha_FICA_nao_e_sucesso(self, cliente,
                                                        monkeypatch):
        """🚨 A prova é a releitura, nunca o retorno do DELETE."""
        chamadas = self._dubles(monkeypatch, antes=[self.NOSSA], apaga=False)
        r = cliente.post("/api/os/cancelar-agendamento", json={
            "numero_os": 90001, "agendamento_id": 944000,
            "vinculo_id": 1199999, "vinculo_criado": True}, headers=CAB)
        corpo = r.json()
        assert corpo["ok"] is False
        assert "continua na OS" in corpo["motivo"]
        assert len(chamadas["delete"]) == 1


class TestReagendarCriaAntesDeApagar:
    """🚨 A ORDEM É A REGRA, e é a única parte deste plano em que errar para um
    lado é recuperável e para o outro não.

    Apagando primeiro, a criação falhando deixa a OS com **zero** compromisso:
    o técnico perde a visita da agenda e ninguém percebe. Criando primeiro, a
    falha deixa **dois** — visível, corrigível, e a resposta diz qual não saiu.
    """

    ANTIGA = {"id": 1167019, "usuarioId": 14262, "nomeTecnico": "Franck",
              "agendamentoId": 966835}

    CORPO = {"numero_os": 90001, "inicio": "2026-11-25T09:00:00",
             "tecnico_id": 14262, "agendamento_id_antigo": 966835,
             "vinculo_id_antigo": 1167019, "vinculo_criado": True}

    def _dubles(self, monkeypatch, *, cria=True, apaga=True):
        estado = {"tecnico": [dict(self.ANTIGA)]}
        chamadas = {"delete": [], "agendar": 0, "vinculo": 0}

        async def postar(caminho, corpo):
            if caminho.endswith("SalvarTecnicoOrdemServico"):
                chamadas["vinculo"] += 1
                estado["tecnico"] = list(estado["tecnico"]) + [
                    {"id": 1177777, "usuarioId": corpo["tecnicoId"],
                     "nomeTecnico": "Franck", "agendamentoId": 0}]
                return {"data": {"osxTecId": 1177777}}
            chamadas["agendar"] += 1
            if not cria:
                raise HTTPException(status_code=502,
                                    detail="Harmonit: recusou (encenado)")
            estado["tecnico"] = [
                dict(t, agendamentoId=977000)
                if t.get("id") == corpo["ordemServicoxTecnicoId"] else t
                for t in estado["tecnico"]]
            return {"data": {}}

        async def ler(caminho, params=None):
            return {"data": {"id": 990001, "numeroOrdem": 90001,
                             "tecnico": list(estado["tecnico"])}}

        async def apagar(caminho, params=None):
            chamadas["delete"].append(params)
            if apaga:
                estado["tecnico"] = [t for t in estado["tecnico"]
                                     if t.get("id") != params["id"]]
            return {"data": {}}

        monkeypatch.setattr(os_ponte, "harmonit_post", postar)
        monkeypatch.setattr(os_ponte, "harmonit_get", ler)
        monkeypatch.setattr(os_ponte, "harmonit_delete", apagar)
        return chamadas

    def test_a_rota_exige_a_chave(self, cliente):
        assert cliente.post("/api/os/reagendar-tecnico",
                            json=self.CORPO).status_code == 422

    def test_cria_o_novo_e_SO_DEPOIS_apaga_o_antigo(self, cliente,
                                                    monkeypatch):
        chamadas = self._dubles(monkeypatch)
        r = cliente.post("/api/os/reagendar-tecnico", json=self.CORPO,
                         headers=CAB)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is True, corpo
        assert corpo["reagendou"] is True
        assert corpo["apagou_o_antigo"] is True
        assert corpo["agendamento_id"] == 977000
        assert corpo["agendamento_id_antigo"] == 966835
        # 🚨 Apagou a linha ANTIGA, não a nova.
        assert chamadas["delete"] == [{"osId": 990001, "id": 1167019,
                                       "agendaId": 966835}]

    def test_criacao_FALHANDO_nao_apaga_nada(self, cliente, monkeypatch):
        """🚨 O teste que guarda a ordem. Compromisso velho na agenda é ruim;
        nenhum compromisso é pior, e ninguém vê."""
        chamadas = self._dubles(monkeypatch, cria=False)
        r = cliente.post("/api/os/reagendar-tecnico", json=self.CORPO,
                         headers=CAB)
        corpo = r.json()
        assert corpo["ok"] is False
        assert corpo["reagendou"] is False
        assert corpo["apagou_o_antigo"] is False
        assert chamadas["delete"] == []

    def test_remocao_FALHANDO_deixa_DOIS_e_diz_qual(self, cliente,
                                                    monkeypatch):
        """⚠️ Nunca zero. E a frase tem de dizer qual não saiu, senão a OS
        fica com dois compromissos e ninguém sabe por quê."""
        chamadas = self._dubles(monkeypatch, apaga=False)
        r = cliente.post("/api/os/reagendar-tecnico", json=self.CORPO,
                         headers=CAB)
        corpo = r.json()
        assert corpo["reagendou"] is True
        assert corpo["apagou_o_antigo"] is False
        assert corpo["causa_do_antigo"] == "recusa_do_erp"
        assert "966835" in corpo["motivo"]
        assert "dois compromissos" in corpo["motivo"]
        assert len(chamadas["delete"]) == 1

    def test_linha_antiga_DE_OUTRO_cria_o_novo_e_NAO_apaga(self, cliente,
                                                           monkeypatch):
        """🔵 O caso misto que ele aceitou: a OS fica com dois, e a resposta
        diz qual não pudemos remover."""
        chamadas = self._dubles(monkeypatch)
        r = cliente.post("/api/os/reagendar-tecnico",
                         json=dict(self.CORPO, vinculo_criado=False),
                         headers=CAB)
        corpo = r.json()
        assert corpo["reagendou"] is True
        assert corpo["apagou_o_antigo"] is False
        assert corpo["causa_do_antigo"] == "vinculo_nao_e_nosso"
        assert chamadas["delete"] == []

    def test_se_o_novo_nasceu_na_MESMA_linha_nao_apaga(self, cliente,
                                                       monkeypatch):
        """🚨 Apagar levaria o compromisso que acabamos de criar — o DELETE
        leva os dois, medido na Velasco."""
        chamadas = self._dubles(monkeypatch)
        r = cliente.post("/api/os/reagendar-tecnico",
                         json=dict(self.CORPO, vinculo_id_antigo=1177777),
                         headers=CAB)
        corpo = r.json()
        assert corpo["reagendou"] is True
        if corpo.get("vinculo_id") == 1177777:
            assert corpo["apagou_o_antigo"] is False
            assert corpo["causa_do_antigo"] == "mesma_linha_do_novo"
            assert chamadas["delete"] == []

    def test_a_ordem_esta_NO_CODIGO_criar_antes_de_apagar(self):
        """⚠️ Trava por texto, e sei que é frágil — mas o que ela guarda é a
        única decisão deste arquivo que não se recupera depois: se alguém
        inverter a ordem, nenhum dublê pega, porque os dois caminhos
        "funcionam"."""
        import inspect
        fonte = inspect.getsource(os_ponte.reagendar_tecnico)
        assert fonte.index("agendar_tecnico(") < fonte.index("_apagar_o_vinculo(")
