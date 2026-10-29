# -*- coding: utf-8 -*-
"""A criação de OS na ponte — Bloco A do pipeline da operação (29/10).

🔵 Decisão D4 dele: *"todo chamado de suporte abrirá uma OS"*.

🚨 NADA AQUI FALA COM O HARMONIT. A escrita é trocada por dublê: teste que
cria OS em ERP de produção deixa sujeira que fica, e o `RemoverOrdemServico`
não desfaz o número consumido.

O que esta suíte trava, e por quê cada coisa doeu:

  · 🚨 **`id: 0` e `numeroOrdem: 0`** — é o que manda CRIAR. Um id de verdade
    ali atualizaria a OS de outra pessoa;
  · 🚨 **`status: 2`** e não o `1` do exemplo da doc — medido: `2` é "Nova" em
    302 OS do cache, e a 17050, aberta por eles em 29/10, nasceu com `2`;
  · 🚨 **a prova é a RELEITURA, nunca o retorno da escrita** — régua da frente
    inteira;
  · 🚨 **resposta sem número não é "falhou"** — é *"pode haver OS criada e não
    sabemos qual"*, e dizer "falhou" faria quem chama tentar de novo e criar a
    segunda;
  · **o ensaio a seco não escreve** — foi assim que o corpo foi provado antes
    de existir a primeira OS de verdade.
"""
import asyncio
import sys

import pytest

sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso.routers import os_ponte  # noqa: E402

# 🚨 O CLIENTE DOS TESTES E A VELASCO (998063), E SO ELA. Regra dele, 29/10:
# *"nao pode usar outro CNPJ alem da VELASCO para teste, pois os tickets nascem
# e tem ligacoes. OS com outros clientes podem ser mal interpretadas pela OP"*.
#
# ⚠️ Aqui o id vive em DUBLE e nenhuma escrita chega ao ERP -- mas e de um teste
# que se copia o numero para um script que escreve, e foi exatamente o que eu
# fiz em 29/10: a OS 17056 nasceu na DCBM porque o numero dela estava a mao.
CLIENTE_SANDBOX = 998063



def _entrada(**troca):
    base = dict(cliente_id=998063, tipo_id=1782, problema_id=12760,
                situacao_id=38, prioridade_id=382,
                descricao="chamado de teste", produto_servico_id=670990)
    base.update(troca)
    return os_ponte.CriarOS(**base)


# ============================================================================
# O corpo da escrita
# ============================================================================
def teste_id_zero_e_o_que_manda_criar():
    """🚨 `id: 0` cria; id de verdade ATUALIZA a OS daquele id."""
    corpo = os_ponte._corpo_de_criacao(_entrada())
    assert corpo["id"] == 0
    assert corpo["numeroOrdem"] == 0


def teste_o_corpo_leva_os_ids_que_ele_decidiu():
    corpo = os_ponte._corpo_de_criacao(_entrada())
    assert corpo["situacaoId"] == 38
    assert corpo["prioridadeId"] == 382
    assert corpo["problemaId"] == 12760
    assert corpo["tipoId"] == 1782
    assert corpo["produtoServicoId"] == 670990
    assert corpo["clienteId"] == 998063


def teste_status_e_dois_porque_o_dado_diz_isso():
    """🚨 A doc do Harmonit mostra `1` no exemplo. O dado real diz `2` = Nova,
    em 302 OS do cache e na 17050 que eles abriram em 29/10."""
    assert os_ponte.STATUS_NOVA == 2
    assert os_ponte._corpo_de_criacao(_entrada())["status"] == 2


def teste_o_endereco_nasce_vazio():
    """⚠️ Chamado de análise não tem endereço de serviço, e inventar um seria
    pior que não ter. Quem agenda preenche pela rota `/endereco`."""
    corpo = os_ponte._corpo_de_criacao(_entrada())
    for campo in os_ponte.CAMPOS_DO_ENDERECO:
        assert corpo[campo] is None


def teste_a_previsao_nasce_preenchida():
    """🚨 Medido em 29/10: `dataPrevisao` É a data de criação da OS (12 de 12).
    Nula apagaria o campo pelo qual a aba Operações mede prazo -- 100%
    preenchido nas 572 OS da base."""
    corpo = os_ponte._corpo_de_criacao(_entrada())
    assert corpo["dataPrevisaoEntrega"]
    assert "T" in corpo["dataPrevisaoEntrega"]


def teste_o_corpo_tem_as_chaves_que_a_doc_do_harmonit_lista():
    """⚠️ `SalvarOrdemServico` é "a OS inteira": chave que falta se perde."""
    corpo = os_ponte._corpo_de_criacao(_entrada())
    for chave in ("id", "empresaId", "numeroOrdem", "dataPrevisaoEntrega",
                  "localServicoId", "tipoId", "prioridadeId", "situacaoId",
                  "problemaId", "produtoServicoId", "clienteId",
                  "descricaoDetalhada", "status", "solucaoTecnica",
                  "valorRetAlimentacao", "valorRetProdutosLimpeza",
                  "valorRetValeTransporte", "vendedorId"):
        assert chave in corpo, chave


def teste_a_empresa_e_o_local_sao_os_da_casa():
    """Lidos da OS 17050 em 29/10, e iguais aos da 16991 de 21/10."""
    assert os_ponte.EMPRESA_PADRAO == 98
    assert os_ponte.LOCAL_SERVICO_PADRAO == 1


def teste_produto_nulo_vira_zero_nao_nulo():
    """⚠️ O campo é inteiro do outro lado; nulo num inteiro é recusa."""
    corpo = os_ponte._corpo_de_criacao(_entrada(produto_servico_id=None))
    assert corpo["produtoServicoId"] == 0


# ============================================================================
# A entrada recusa o que não pode faltar
# ============================================================================
def teste_nada_de_catalogo_tem_padrao_na_entrada():
    """🚨 DE PROPÓSITO: um padrão aqui faria a ponte decidir regra de negócio
    que é do MoviZap -- o `tipoId` vem da ORIGEM do chamado, e a origem este
    lado não conhece."""
    from pydantic import ValidationError
    for falta in ("cliente_id", "tipo_id", "problema_id", "situacao_id",
                  "prioridade_id", "descricao"):
        base = dict(cliente_id=1, tipo_id=1, problema_id=1, situacao_id=1,
                    prioridade_id=1, descricao="x")
        base.pop(falta)
        with pytest.raises(ValidationError):
            os_ponte.CriarOS(**base)


def teste_descricao_vazia_e_recusada():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _entrada(descricao="")


# ============================================================================
# O número que a resposta traz
# ============================================================================
@pytest.mark.parametrize("resposta, esperado", [
    ({"data": {"numeroOrdem": 17101, "ordemServicoId": 927100}},
     (17101, 927100)),
    ({"numeroOrdem": 17101, "id": 927100}, (17101, 927100)),
    ({"data": [{"numeroOs": "17101", "osId": "927100"}]}, (17101, 927100)),
    # 🚨 Os casos que NÃO dão número -- cada um já foi um jeito de a resposta
    # vir e não pode virar `KeyError` numa rota que acabou de gravar no ERP.
    ({"data": {}}, (None, None)),
    ({"data": None}, (None, None)),
    ({"data": []}, (None, None)),
    ({"data": {"numeroOrdem": None}}, (None, None)),
    ({"data": {"numeroOrdem": "nao e numero"}}, (None, None)),
    ("uma string", (None, None)),
])
def teste_o_numero_sai_de_qualquer_forma_plausivel(resposta, esperado):
    """⚠️ A doc documenta o retorno da rota BÁSICA, não o da completa. Então
    se procura por todos os nomes plausíveis, e não achar é caso tratado."""
    assert os_ponte._numero_da_resposta(resposta) == esperado


# ============================================================================
# A rota
# ============================================================================
def teste_o_ensaio_a_seco_nao_escreve(monkeypatch):
    """🚨 Com `conferir: true` a rota monta tudo e NÃO grava."""
    def nao_devia_ser_chamado(*a, **k):
        raise AssertionError("o ensaio a seco escreveu no Harmonit")

    monkeypatch.setattr(os_ponte, "harmonit_post", nao_devia_ser_chamado)
    r = asyncio.run(os_ponte.criar_os(_entrada(conferir=True)))
    assert r["ok"] is True
    assert r["conferido_sem_gravar"] is True
    assert r["corpo"]["id"] == 0


def teste_a_prova_e_a_releitura(monkeypatch):
    """🚨 A régua da frente: o retorno da escrita não é prova. Aqui a escrita
    devolve o número e a RELEITURA é quem confirma os campos."""
    escrito = {}

    async def postar(caminho, corpo):
        escrito.update(corpo)
        return {"data": {"numeroOrdem": 17101, "ordemServicoId": 927100}}

    async def ler(caminho, params=None):
        return {"data": {"id": 927100, "numeroOrdem": 17101, "tipo": 1782,
                         "problema": 12760, "situacaoId": 38,
                         "prioridade": 382, "parceiro": 998063}}

    monkeypatch.setattr(os_ponte, "harmonit_post", postar)
    monkeypatch.setattr(os_ponte, "harmonit_get", ler)

    r = asyncio.run(os_ponte.criar_os(_entrada()))
    assert r["ok"] is True
    assert r["criada"] is True
    assert r["numero_os"] == 17101
    assert r["divergencias"] is None
    assert escrito["id"] == 0


def teste_a_releitura_acusa_divergencia(monkeypatch):
    """🚨 OS que nasceu diferente do pedido: `ok` falso, número guardado (senão
    fica órfã no ERP) e a divergência DITA por extenso."""
    async def postar(caminho, corpo):
        return {"data": {"numeroOrdem": 17101}}

    async def ler(caminho, params=None):
        # A situação nasceu 0 em vez de 38 -- caso real: 129 OS do cache
        # estão com situação 0.
        return {"data": {"id": 927100, "tipo": 1782, "problema": 12760,
                         "situacaoId": 0, "prioridade": 382,
                         "parceiro": 998063}}

    monkeypatch.setattr(os_ponte, "harmonit_post", postar)
    monkeypatch.setattr(os_ponte, "harmonit_get", ler)

    r = asyncio.run(os_ponte.criar_os(_entrada()))
    assert r["ok"] is False
    assert r["criada"] is True
    assert r["numero_os"] == 17101
    assert r["divergencias"]["situacaoId"] == {"pedido": 38, "gravado": 0}


def teste_resposta_sem_numero_nao_e_falhou(monkeypatch):
    """🚨 O PIOR CASO, e o que não se pode mascarar: pode haver OS criada e nós
    não sabermos qual. `criada: None`, e a mensagem manda NÃO tentar de novo."""
    async def postar(caminho, corpo):
        return {"data": {}}

    monkeypatch.setattr(os_ponte, "harmonit_post", postar)
    r = asyncio.run(os_ponte.criar_os(_entrada()))
    assert r["ok"] is False
    assert r["criada"] is None
    assert r["numero_os"] is None
    assert "nascem duas" in r["motivo"]


def teste_a_releitura_que_nao_acha_a_os_guarda_o_numero(monkeypatch):
    """⚠️ Criada e não relida: o número é devolvido de qualquer forma, porque
    OS criada sem registro deste lado é OS órfã no ERP."""
    async def postar(caminho, corpo):
        return {"data": {"numeroOrdem": 17101}}

    async def ler(caminho, params=None):
        return {"data": None}

    monkeypatch.setattr(os_ponte, "harmonit_post", postar)
    monkeypatch.setattr(os_ponte, "harmonit_get", ler)

    r = asyncio.run(os_ponte.criar_os(_entrada()))
    assert r["ok"] is False
    assert r["criada"] is True
    assert r["numero_os"] == 17101


def teste_recusa_do_harmonit_nao_estoura(monkeypatch):
    """Recusa é resposta, não falha de ponte -- como nas outras escritas."""
    from fastapi import HTTPException

    async def postar(caminho, corpo):
        raise HTTPException(status_code=502, detail="Harmonit: cliente invalido")

    monkeypatch.setattr(os_ponte, "harmonit_post", postar)
    r = asyncio.run(os_ponte.criar_os(_entrada()))
    assert r["ok"] is False
    assert r["criada"] is False
    assert "cliente invalido" in r["motivo"]

# ============================================================================
# BLOCO B — as OS por situação, desde a data matriz
# ============================================================================
def teste_data_torta_e_recusada():
    """🚨 `desde` torto faria o SQL comparar texto com texto e devolver
    qualquer coisa. Recusa com 422, e a mensagem mostra o valor."""
    from fastapi import HTTPException
    for torta in ("24/10/2026", "2026-13-01", "ontem", ""):
        with pytest.raises(HTTPException) as e:
            asyncio.run(os_ponte.os_por_situacao(desde=torta))
        assert e.value.status_code == 422


def teste_o_corte_usa_substr_e_nao_date():
    """🚨 `data_previsao` É TEXTO `dd/mm/aaaa`, e `date()` devolve ZERO LINHA
    nesse formato -- custou um plano inteiro em 19/10. O corte tem de usar o
    `_PREVISAO_ISO`, que recorta a string."""
    assert "substr(data_previsao, 7, 4)" in os_ponte._PREVISAO_ISO
    assert "date(" not in os_ponte._PREVISAO_ISO


def teste_as_dezessete_situacoes_batem_com_as_do_movizap():
    """🚨 ESTA LISTA É CÓPIA, e a fonte é o `movizap/paineis.py`. A trava
    existe para a cópia não apodrecer calada: se divergirem, `tem_coluna` fica
    errado deste lado."""
    assert len(os_ponte._SITUACOES_DO_PAINEL) == 17
    ids = [sid for sid, _ in os_ponte._SITUACOES_DO_PAINEL]
    assert len(set(ids)) == 17
    # A primeira é a que toda OS de chamado recebe.
    assert ids[0] == 38
    # 🚨 A 15694 é a PORTA DO PAINEL FINANCEIRO DO FPSL -- o id não pode
    # mudar, só o nome.
    assert 15694 in ids


@pytest.mark.parametrize("bruto, esperado", [
    (None, []),
    ("", []),
    ("nao e json", []),
    ('{"nao": "e lista"}', []),
    ("[]", []),
    ('[{"semUsuarioId": 1}]', []),
])
def teste_tecnicos_ilegivel_nao_derruba(bruto, esperado):
    """⚠️ Dado do Harmonit, varrido por rotina: ilegível devolve vazio e
    registra, nunca estoura a consulta do painel inteiro."""
    assert os_ponte._tecnicos_da_os(bruto) == esperado


def teste_o_segundo_vinculo_aparece_como_vinculo_nao_como_tecnico():
    """🚨 O MESMO TÉCNICO DUAS VEZES É O DESENHO DO HARMONIT: o segundo vínculo
    é o caminho para reagendar (`TecnicoJaAgendado` é do VÍNCULO, não do
    técnico, medido em 21/10). Deduplicar escondendo isso faria desaparecer a
    razão pela qual o reagendamento funciona."""
    dois = ('[{"usuarioId": 14316, "nome": "Iago"},'
            ' {"usuarioId": 14316, "nome": "Iago", "agendamentoId": 945220}]')
    saida = os_ponte._tecnicos_da_os(dois)
    assert len(saida) == 1
    assert saida[0]["vinculos"] == 2
    # ⚠️ O vínculo COM agendamento ganha: o compromisso está em apenas um.
    assert saida[0]["agendamento_id"] == 945220
