"""A escrita de endereço na OS e o segundo vínculo (21/10) — medindo a REGRA.

🚨 Este arquivo nasceu de uma auditoria: as duas coisas mais delicadas de
21/10 -- escrever a OS inteira para mudar só o endereço, e criar um segundo
vínculo OS×técnico para poder agendar -- foram provadas **ao vivo** na OS
16991 e **não tinham teste**. Prova ao vivo não se repete sozinha: uma
regressão passaria verde.

O que estes testes guardam:
  · 🚨 `solucaoTecnica` passa COMO ESTÁ: foi a escrita no-op que pegou o `or ""`
    trocando `null` por string vazia, e a comparação de depois acusou;
  · a `dataPrevisao` vira ISO, e formato desconhecido NÃO vira `None` em
    silêncio -- gravar sem ela apagaria a previsão da OS;
  · o CEP vai sem máscara, como a base guarda;
  · 🚨 `parceiro` NÃO é o cliente da escrita: quem manda é o `clienteId` que a
    rota recebe -- os nomes de leitura e de escrita não batem;
  · só os sete campos de endereço mudam; qualquer outra diferença é
    `fora_do_endereco`, por extenso;
  · 🚨 o segundo vínculo é o caminho do próprio Harmonit, e a prova de que
    nasceu é RELER a OS e achar um id que não existia -- nunca o retorno.

Estes testes não falam com o Harmonit nem com o banco.
"""
import asyncio
import sys

import pytest

sys.path.insert(0, "/home/claude/fpsl_weso")

from fastapi import HTTPException  # noqa: E402

from fpsl_weso.routers import os_ponte  # noqa: E402

# Uma OS como o Harmonit a devolve, reduzida ao que a escrita lê.
OS = {
    "id": 16991, "empresaId": 1, "numeroOrdem": 16991,
    "dataPrevisao": "21/10/2026 08:00:00", "localServico": 3, "tipo": 1784,
    "prioridade": 2, "situacaoId": 15694, "problema": 77, "produtoId": 9,
    "descricao": "trocar rastreador", "status": 1, "solucaoTecnica": None,
    "parceiro": 5555, "cep": "19013180", "endereco": "Rua Marcondes Salgado",
    "numero": "S/N", "bairro": "Centro", "cidade": "Presidente Prudente",
    "uf": "SP", "complemento": None, "tecnico": [{"id": 1143047}],
    "checkList": [], "materiais": [], "oficina": [],
}


class TestOCorpoDeEscrita:
    def test_so_o_endereco_muda_e_o_resto_vem_da_OS(self):
        corpo = os_ponte._corpo_de_escrita(OS, cliente_id=4321,
                                           novo={"numero": "26"})
        assert corpo["numero"] == "26"
        assert corpo["endereco"] == "Rua Marcondes Salgado"
        assert corpo["descricaoDetalhada"] == "trocar rastreador"
        assert corpo["tipoId"] == 1784

    def test_parceiro_NAO_e_o_cliente_da_escrita(self):
        """🚨 Os nomes de leitura e escrita não batem: `clienteId` é quem manda."""
        corpo = os_ponte._corpo_de_escrita(OS, cliente_id=4321, novo={})
        assert corpo["clienteId"] == 4321
        assert "parceiro" not in corpo

    def test_solucaoTecnica_nula_segue_NULA(self):
        """🚨 O `or ""` trocava `null` por `""` -- pego pelo ensaio a seco."""
        corpo = os_ponte._corpo_de_escrita(OS, cliente_id=1, novo={})
        assert corpo["solucaoTecnica"] is None

    def test_campo_nao_enviado_nao_apaga_o_que_a_OS_tem(self):
        """⚠️ `None` no pedido é "não mexe", não "apaga"."""
        corpo = os_ponte._corpo_de_escrita(
            OS, cliente_id=1, novo={"cep": None, "bairro": None})
        assert corpo["cep"] == "19013180"
        assert corpo["bairro"] == "Centro"

    def test_valores_de_retencao_nulos_viram_zero(self):
        corpo = os_ponte._corpo_de_escrita(OS, cliente_id=1, novo={})
        assert corpo["valorRetAlimentacao"] == 0
        assert corpo["vendedorId"] == 0


class TestOCep:
    def test_mascara_sai(self):
        assert os_ponte._so_digitos_cep("19013-180") == "19013180"

    def test_nulo_segue_nulo_e_vazio_vira_nulo(self):
        assert os_ponte._so_digitos_cep(None) is None
        assert os_ponte._so_digitos_cep("   ") is None


class TestAPrevisao:
    def test_data_com_hora_vira_iso(self):
        assert os_ponte._previsao_iso("21/10/2026 08:00:00") == \
            "2026-10-21T08:00:00"

    def test_so_data_tambem(self):
        assert os_ponte._previsao_iso("21/10/2026") == "2026-10-21T00:00:00"

    def test_iso_que_chega_iso_segue(self):
        assert os_ponte._previsao_iso("2026-10-21T08:00:00") == \
            "2026-10-21T08:00:00"

    def test_vazio_e_None(self):
        assert os_ponte._previsao_iso(None) is None
        assert os_ponte._previsao_iso("") is None

    def test_formato_desconhecido_NAO_vira_None_em_silencio(self):
        """🚨 Gravar sem a previsão apagaria o prazo que a aba Operações usa."""
        with pytest.raises(HTTPException) as e:
            os_ponte._previsao_iso("outubro de 2026")
        assert e.value.status_code == 500
        assert "previsao" in e.value.detail.lower()


class TestAsDiferencas:
    def test_escrita_que_nao_mudou_nada_da_dicionario_vazio(self):
        assert os_ponte._diferencas(OS, dict(OS)) == {}

    def test_mudanca_de_endereco_aparece_com_antes_e_depois(self):
        depois = dict(OS, numero="26")
        mudou = os_ponte._diferencas(OS, depois)
        assert mudou == {"numero": {"antes": "S/N", "depois": "26"}}

    def test_campo_FORA_do_endereco_tambem_aparece(self):
        """🚨 É isto que permite dizer `fora_do_endereco` por extenso."""
        mudou = os_ponte._diferencas(OS, dict(OS, solucaoTecnica=""))
        assert "solucaoTecnica" in mudou
        assert mudou["solucaoTecnica"] == {"antes": None, "depois": ""}

    def test_lista_e_comparada_por_TAMANHO_e_diz_isso(self):
        mudou = os_ponte._diferencas(OS, dict(OS, checkList=[{"a": 1}]))
        assert mudou["checkList"] == {"antes": "0 itens", "depois": "1 itens"}

    def test_lista_igual_em_tamanho_nao_acusa(self):
        """⚠️ O limite é conhecido: conteúdo de item não é comparado."""
        assert "oficina" not in os_ponte._diferencas(
            OS, dict(OS, oficina=[]))


class TestOSegundoVinculo:
    """🚨 `TecnicoJaAgendado` é do VÍNCULO, não do técnico (medido em 21/10:
    `usuarioId 14316` tem a mesma OS 16921 duas vezes). O caminho é criar
    outra linha `ordemServicoxTecnico` e agendar nela."""

    def _cena(self, monkeypatch, os_depois, erro_no_post=None):
        posts = []

        async def post_falso(rota, corpo):
            posts.append((rota, corpo))
            if erro_no_post:
                raise erro_no_post
            return {"osxTecId": 999999}

        async def get_falso(rota, params=None):
            return {"data": [os_depois]}

        monkeypatch.setattr(os_ponte, "harmonit_post", post_falso)
        monkeypatch.setattr(os_ponte, "harmonit_get", get_falso)
        return posts

    def test_nasce_um_vinculo_e_e_ele_que_volta(self, monkeypatch):
        depois = dict(OS, tecnico=[{"id": 1143047}, {"id": 1143048,
                                                     "usuarioId": 7493}])
        posts = self._cena(monkeypatch, depois)
        novo, motivo = asyncio.run(
            os_ponte._segundo_vinculo(OS, {"usuarioId": 7493}))
        assert motivo == ""
        # 🚨 O id vem de RELER a OS, não do retorno do POST (que diz 999999).
        assert novo["id"] == 1143048

    def test_o_corpo_nao_tira_a_responsabilidade_de_ninguem(self, monkeypatch):
        depois = dict(OS, tecnico=[{"id": 1143047}, {"id": 1143048}])
        posts = self._cena(monkeypatch, depois)
        asyncio.run(os_ponte._segundo_vinculo(OS, {"usuarioId": 7493}))
        rota, corpo = posts[0]
        assert rota.endswith("SalvarTecnicoOrdemServico")
        assert corpo["tecnicoResponsavelPelaOS"] is False
        assert corpo["tecnicoId"] == 7493
        assert corpo["osId"] == 16991

    def test_se_a_OS_relida_nao_tem_vinculo_novo_RECUSA(self, monkeypatch):
        """⚠️ Nada nasceu: dizer que nasceu seria agendar no vínculo velho."""
        self._cena(monkeypatch, dict(OS))      # a mesma lista de antes
        novo, motivo = asyncio.run(
            os_ponte._segundo_vinculo(OS, {"usuarioId": 7493}))
        assert novo is None
        assert motivo
