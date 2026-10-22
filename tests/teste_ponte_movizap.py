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

    def test_tecnico_JA_AGENDADO_e_ACEITO(self):
        """🔵 21/10, segunda decisao dele: *"a barreira de agendamento do
        tecnico nao deve existir, no harmonit ja foi liberada tbm"*.

        🚨 ESTE TESTE AFIRMAVA O CONTRARIO ATE 21/10, e a troca e deliberada:
        a barreira era DAQUI, e foi ela que derrubou o teste dele das 15:11.
        Quem decide agora e o Harmonit, e a recusa dele chega por extenso.
        """
        ocupado = dict(self.FRANCK, agendamentoId=944780)
        achado, motivo = os_ponte._escolher_vinculo([ocupado], "+5519997394026")
        assert achado["id"] == 2
        assert motivo == ""

    def test_prefere_o_vinculo_SEM_compromisso_quando_ha_os_dois(self):
        """⚠️ Criar onde nao ha e mais barato que mexer onde ha -- mas e
        preferencia, nao recusa."""
        tecnicos = [dict(self.FRANCK, id=2, agendamentoId=944780),
                    dict(self.FRANCK, id=3)]
        achado, _ = os_ponte._escolher_vinculo(tecnicos, "+5519997394026")
        assert achado["id"] == 3

    def test_sem_telefone_so_aceita_quando_a_OS_TEM_UM_TECNICO(self):
        """🚨 Nunca escolhe no escuro -- esta guarda NAO caiu."""
        achado, _ = os_ponte._escolher_vinculo([self.FRANCK], None)
        assert achado["id"] == 2

    def test_sem_telefone_e_com_dois_tecnicos_recusa(self):
        achado, motivo = os_ponte._escolher_vinculo(
            [self.IAGO, self.FRANCK], None)
        assert achado is None
        assert "nao tem telefone" in motivo

    def test_dois_tecnicos_JA_AGENDADOS_recusa_por_AMBIGUIDADE_e_nao_por_ocupacao(self):
        """🚨 A conta e sobre TODOS os tecnicos, nao so os livres.

        Contar so os livres faria a OS de tres tecnicos, dois ja agendados,
        escolher o terceiro sozinha e em silencio -- a barreira cairia junto
        com a guarda de ambiguidade, e so a barreira devia cair.
        """
        ocupados = [dict(self.IAGO, agendamentoId=1),
                    dict(self.FRANCK, agendamentoId=2)]
        achado, motivo = os_ponte._escolher_vinculo(ocupados, None)
        assert achado is None
        assert "nao tem telefone nem vinculo" in motivo
        assert "ja tem compromisso" not in motivo


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

    def test_vinculado_e_JA_AGENDADO_e_ACEITO(self):
        """🔵 A barreira caiu em 21/10 (ver `TestEscolherOTecnico`). Este e
        o caso exato do teste dele das 15:11: o 6168 esta vinculado ao Iago,
        que ja tinha o compromisso 930447 na OS 16991."""
        ocupado = dict(self.IAGO, agendamentoId=930447)
        achado, motivo = os_ponte._escolher_vinculo(
            [ocupado], telefone=None, tecnico_id=7493)
        assert achado["usuarioId"] == 7493
        assert motivo == ""


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


class TestODicionarioDeTiposDeOS:
    """🆕 21/10, ponta 1 do plano: o nome do tipo, para o cabeçalho da mensagem.

    🚨 O NOME NÃO EXISTE PARA TODA OS, e isto é o ponto: a lista do Harmonit
    tem **5 tipos**, que cobrem **374 das 547** OS não excluídas. As outras
    **173** estão em nove ids fora da lista (57, 76, 73, 72, 55, 77, 75, 576,
    814) -- tipos removidos ou renomeados lá. O `os_router` já registrava o
    caso do 55 desde 14/08: *"id fixo em código apodrece em silêncio"*.
    """

    def test_a_lista_crua_do_harmonit_e_aceita(self):
        """⚠️ Medido em 21/10: esta rota devolve LISTA, sem embrulho `data`."""
        from fpsl_weso.services import sync_tipos_os
        bruto = [{"id": 2, "codigo": 2, "descricao": "Contrato"}]
        assert sync_tipos_os._lista(bruto) == bruto

    def test_o_embrulho_data_tambem_e_aceito(self):
        """Outras rotas do Harmonit embrulham: tratar os dois custa 3 linhas e
        evita a rotina parar de achar tipo no dia em que padronizarem."""
        from fpsl_weso.services import sync_tipos_os
        assert sync_tipos_os._lista({"data": [{"id": 2, "descricao": "C"}]}) \
            == [{"id": 2, "descricao": "C"}]
        assert sync_tipos_os._lista(None) == []
        assert sync_tipos_os._lista("isto nao e lista") == []

    def test_base_sem_a_tabela_nao_derruba_a_consulta(self):
        """⚠️ Base antiga: sem dicionário, nenhum nome -- e nenhuma exceção.

        A ponte lê o dicionário no meio de montar a resposta das OS; estourar
        ali faria a tela dizer "não deu para consultar as OS deste cliente"
        por causa de um rótulo que é enfeite do cabeçalho.
        """
        import sqlite3

        from fpsl_weso import storage
        with sqlite3.connect(":memory:") as vazia:
            assert storage.nomes_dos_tipos_os(vazia) == {}

    def test_o_dicionario_devolve_ausencia_para_tipo_fora_da_lista(self):
        """🚨 A regra inteira da ponta 1: tipo sem nome -> `None`, e quem monta
        a mensagem OMITE o segmento. Imprimir o número não diz nada ao cliente,
        e inventar rótulo é tela que mente."""
        import sqlite3

        from fpsl_weso import storage
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE TABLE tipos_os (tipo_id INTEGER PRIMARY KEY,"
                         " nome TEXT NOT NULL, codigo INTEGER,"
                         " atualizado_em TEXT NOT NULL)")
            conn.execute("INSERT INTO tipos_os VALUES (2, 'Contrato', 2, 'x')")
            d = storage.nomes_dos_tipos_os(conn)
        assert d.get(2) == "Contrato"
        # 55 é o tipo morto que o FPSL já conhecia; 57 e 76 são os dois mais
        # numerosos entre os nove de fora (81 e 39 OS em 21/10).
        assert d.get(55) is None and d.get(57) is None and d.get(76) is None
