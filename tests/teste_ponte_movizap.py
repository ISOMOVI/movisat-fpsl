"""A ponte com o MoviZap: leitura de OS e a trava do técnico (21/10).

🔵 Decisão dele, 21/10: *"a validação será pelo e-mail do técnico... assim,
mesmo que nomeiem errado, ele vai trazer no orçamento o nome do cadastro
harmonit"*.

🚨 O QUE A MEDIÇÃO MOSTROU, e que derruba o casamento por nome: o e-mail do
técnico no Harmonit **é o telefone dele** (`Franck` →
`997394026@movisat.com.br`, contato `+5519997394026`), e isso vale em **186
dos 200** cadastros — os 14 que fogem são contas internas (`comercial@`,
`parceiros@`, pessoas da casa), não técnicos de campo. Dos 179 contatos de
técnico do MoviZap que casam por telefone, **21 têm nome diferente** do
Harmonit, e quase todos os nomes do MoviZap carregam sufixo de cidade
(`Franck | Campinas - SP`): casar por nome recusaria praticamente todos.

Estes testes não falam com o Harmonit nem com o banco — medem a regra.
"""
import sys

sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso.routers import os_ponte  # noqa: E402


class TestAChaveDoTelefone:
    def test_sao_os_9_ultimos_digitos(self):
        """Nove porque é o número sem DDI nem DDD: comparar o e164 inteiro
        erraria em todo técnico cujo DDD o Harmonit não guardou."""
        assert os_ponte._chave_do_telefone("+5519997394026") == "997394026"
        assert os_ponte._chave_do_telefone("19 99739-4026") == "997394026"
        assert os_ponte._chave_do_telefone("997394026") == "997394026"

    def test_telefone_curto_nao_vira_chave(self):
        assert os_ponte._chave_do_telefone("4026") == ""
        assert os_ponte._chave_do_telefone(None) == ""
        assert os_ponte._chave_do_telefone("") == ""


class TestOEmailDoTecnico:
    def test_so_vale_e_mail_NUMERICO(self):
        assert os_ponte._email_do_tecnico(
            {"email": "997394026@movisat.com.br"}) == "997394026"

    def test_conta_interna_nao_casa_por_acidente(self):
        assert os_ponte._email_do_tecnico({"email": "iago@movisat.com.br"}) == ""
        assert os_ponte._email_do_tecnico(
            {"email": "comercial@movisat.com.br"}) == ""

    def test_sem_email_nao_quebra(self):
        assert os_ponte._email_do_tecnico({}) == ""
        assert os_ponte._email_do_tecnico({"email": None}) == ""
        assert os_ponte._email_do_tecnico({"email": "semarroba"}) == ""


class TestEscolherOTecnico:
    IAGO = {"id": 1, "nomeTecnico": "Iago Santos do Ó Souza",
            "email": "iago@movisat.com.br"}
    FRANCK = {"id": 2, "nomeTecnico": "Franck",
              "email": "997394026@movisat.com.br"}

    def test_casa_o_tecnico_certo_pelo_telefone(self):
        achado, motivo = os_ponte._escolher_vinculo(
            [self.IAGO, self.FRANCK], "+5519997394026", "Franck | Campinas - SP")
        assert achado["id"] == 2
        assert motivo == ""

    def test_nome_divergente_NAO_atrapalha(self):
        """É o caso que ele descreveu: *"mesmo que nomeiem errado"*."""
        tecnicos = [{"id": 7, "nomeTecnico": "Jose da Silva",
                     "email": "988887777@movisat.com.br"}]
        achado, _ = os_ponte._escolher_vinculo(
            tecnicos, "+5511988887777", "Ze | Sao Paulo - SP")
        assert achado["id"] == 7

    def test_o_NOME_nao_casa_nada(self):
        """Mandar o nome certo e o telefone errado continua recusando."""
        achado, _ = os_ponte._escolher_vinculo(
            [self.FRANCK], "+5518998116168", "Franck")
        assert achado is None

    def test_telefone_fora_da_OS_e_recusado_COM_a_lista(self):
        achado, motivo = os_ponte._escolher_vinculo(
            [self.IAGO, self.FRANCK], "+5518998116168")
        assert achado is None
        # A recusa diz o telefone procurado E quem a OS tem -- sem isso o
        # operador não sabe o que corrigir.
        assert "998116168" in motivo
        assert "997394026@movisat.com.br" in motivo

    def test_tecnico_JA_AGENDADO_e_recusado_dizendo_qual(self):
        ocupado = dict(self.FRANCK, agendamentoId=944780)
        achado, motivo = os_ponte._escolher_vinculo([ocupado], "+5519997394026")
        assert achado is None
        assert "944780" in motivo

    def test_sem_telefone_so_aceita_quando_ha_UM_livre(self):
        """🚨 Nunca escolhe no escuro."""
        achado, _ = os_ponte._escolher_vinculo([self.FRANCK], None)
        assert achado["id"] == 2

    def test_sem_telefone_e_com_dois_livres_recusa(self):
        achado, motivo = os_ponte._escolher_vinculo(
            [self.IAGO, self.FRANCK], None)
        assert achado is None
        assert "nao tem telefone" in motivo

    def test_todos_ocupados_recusa(self):
        ocupados = [dict(self.IAGO, agendamentoId=1),
                    dict(self.FRANCK, agendamentoId=2)]
        achado, motivo = os_ponte._escolher_vinculo(ocupados, None)
        assert achado is None
        assert "ja tem compromisso" in motivo


class TestOVinculoGravadoManda:
    """🔵 21/10: quando o MoviZap já tem o vínculo, ele casa por IDENTIDADE.

    🚨 O `usuarioId` de cada técnico da OS **é o `tecnico_id` do cadastro** —
    medido: Iago 7493 e Franck 14262, iguais dos dois lados. É isso que faz o
    vínculo MANUAL funcionar, inclusive a exceção dele (6168 → Iago), que por
    telefone jamais casaria.
    """

    IAGO = {"id": 1, "usuarioId": 7493, "nomeTecnico": "Iago Santos do Ó Souza",
            "email": "iago@movisat.com.br"}
    FRANCK = {"id": 2, "usuarioId": 14262, "nomeTecnico": "Franck",
              "email": "997394026@movisat.com.br"}

    def test_o_tecnico_id_vinculado_ganha_do_telefone(self):
        achado, _ = os_ponte._escolher_vinculo(
            [self.IAGO, self.FRANCK],
            telefone="+5519997394026",   # este telefone é do Franck...
            tecnico_id=7493)             # ...e o vínculo diz Iago.
        assert achado["usuarioId"] == 7493

    def test_a_excecao_dele_funciona_SO_pelo_vinculo(self):
        """Pelo telefone, o 6168 não acharia ninguém."""
        sem_vinculo, motivo = os_ponte._escolher_vinculo(
            [self.IAGO, self.FRANCK], telefone="+5518998116168")
        assert sem_vinculo is None

        com_vinculo, _ = os_ponte._escolher_vinculo(
            [self.IAGO, self.FRANCK], telefone="+5518998116168",
            tecnico_id=7493)
        assert com_vinculo["usuarioId"] == 7493

    def test_vinculado_mas_fora_desta_OS_e_recusado_COM_a_lista(self):
        achado, motivo = os_ponte._escolher_vinculo(
            [self.FRANCK], telefone=None, tecnico_id=7493)
        assert achado is None
        assert "7493" in motivo
        assert "Franck" in motivo

    def test_vinculado_e_JA_AGENDADO_diz_qual(self):
        ocupado = dict(self.IAGO, agendamentoId=930447)
        achado, motivo = os_ponte._escolher_vinculo(
            [ocupado], telefone=None, tecnico_id=7493)
        assert achado is None
        assert "930447" in motivo


class TestORecorteDasOS:
    def test_em_aberto_inclui_status_NULO(self):
        """⚠️ Nulo não é finalizado: 37 das 572 OS da base estão assim, e em
        SQL nulo não é diferente de nada -- `status_str <> 'Finalizado'`
        sozinho sumiria com elas em silêncio."""
        assert "status_str IS NULL" in os_ponte._EM_ABERTO

    def test_a_data_e_remontada_por_SUBSTR(self):
        """🚨 `data_previsao` é texto `dd/mm/aaaa`: `date()` devolve zero."""
        assert "substr(data_previsao, 7, 4)" in os_ponte._PREVISAO_ISO
        assert "date(" not in os_ponte._PREVISAO_ISO

    def test_placa_sai_do_oficinas_json_sem_repetir(self):
        bruto = ('[{"veiculoPlaca": "FZU5D16", "veiculoNome": "FIORINO"},'
                 ' {"veiculoPlaca": "FZU5D16", "veiculoNome": "FIORINO"},'
                 ' {"veiculoPlaca": "ABC1D23", "veiculoNome": "GOL"}]')
        assert [v["placa"] for v in os_ponte._placas(bruto)] == ["FZU5D16", "ABC1D23"]

    def test_oficina_ilegivel_nao_derruba_a_consulta(self):
        """Dado do Harmonit, varrido por rotina: lista vazia, não exceção."""
        assert os_ponte._placas("isto nao e json") == []
        assert os_ponte._placas(None) == []
        assert os_ponte._placas('{"nao": "e lista"}') == []
