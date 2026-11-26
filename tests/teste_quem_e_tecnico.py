# -*- coding: utf-8 -*-
r"""A TERCEIRA CAMADA DE "QUEM NAO E TECNICO" -- 25/11.

🔵 Ele: *"bruna, vanessa e karla nao sao tecnicos"* e *"segue a regra de quem e
ou nao tecnico"*.

📏 MEDIDO ANTES DE ESCREVER, e e o que define a regra: **190 dos 191** tecnicos
nao excluidos tem e-mail `@movisat.com.br`, porque o Harmonit usa
`telefone@movisat.com.br` como e-mail sintetico. O dominio NAO separa nada. O
que separa e a parte ANTES do @: **numero e o telefone do tecnico de campo,
nome e gente da casa**.

Hoje a regra separa exatamente os tres que ele nomeou:
  · Karla Alves (9617)   karla.alves@movisat.com.br
  · Vanessa Guimaraes (7148)  vanessa@movisat.com.br
  · Bruna Souza (10909)  bruna@movisat.com.br

🚨 E ELA NAO PODE PEGAR MAIS NINGUEM. O unico e-mail fora do dominio e
`checklistpreenchidosoficial@gmail.com` ("Teste tecnico"): parte local
alfabetica, mas de OUTRO dominio -- a regra vale **so no dominio da empresa**,
senao ela julgaria o cadastro de terceiros por um padrao que e nosso.

⚠️ As duas camadas que ja existiam (estar em `ObterUsuarios`, ter e-mail de
usuario do painel) continuam valendo e nao sao tocadas: as tres escaparam das
duas, e e por isso que a terceira existe.
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.services import sync_tecnicos as st  # noqa: E402

DOMINIO = "@movisat.com.br"


def teste_nome_no_dominio_da_empresa_NAO_e_tecnico():
    """Os tres que ele nomeou, pelo e-mail real que esta no cadastro."""
    for email in ("karla.alves@movisat.com.br",
                  "vanessa@movisat.com.br",
                  "bruna@movisat.com.br"):
        assert st.e_da_casa(email) is True, email


def teste_telefone_no_dominio_CONTINUA_tecnico():
    """📏 187 dos 191 sao assim. Se a regra pegasse um destes, ela apagaria
    tecnico de verdade -- e a OS dele viraria card sem tecnico."""
    for email in ("997394026@movisat.com.br",   # Franck, 14262
                  "974140416@movisat.com.br",   # Tecnico Movisat, 14493
                  "84656845@movisat.com.br",    # E&T, 14059 (8 digitos)
                  "99059387@movisat.com.br"):   # Naldo Eletricista, 14203
        assert st.e_da_casa(email) is False, email


def teste_FORA_do_dominio_a_regra_nao_opina():
    """🚨 `checklistpreenchidosoficial@gmail.com` e alfabetico e NAO e da casa:
    julgar cadastro de terceiro por um padrao nosso seria inventar regra."""
    for email in ("checklistpreenchidosoficial@gmail.com",
                  "joao@oficinaparceira.com.br",
                  "123456789@gmail.com"):
        assert st.e_da_casa(email) is False, email


def teste_email_vazio_ou_torto_nao_vira_exclusao():
    """⚠️ Sem e-mail nao se sabe, e "nao sei" nao pode virar "nao e tecnico":
    isso tiraria do pagamento quem o cadastro apenas nao preencheu."""
    for email in (None, "", "   ", "semarroba", "@movisat.com.br",
                  "nome@", "nome@@movisat.com.br"):
        assert st.e_da_casa(email) is False, repr(email)


def teste_a_caixa_e_o_espaco_nao_enganam():
    """⚠️ `grep -i` sempre: o C maiusculo ja custou tres textos nesta casa."""
    assert st.e_da_casa("  KARLA.ALVES@MOVISAT.COM.BR  ") is True
    assert st.e_da_casa(" 997394026@MoviSat.Com.Br ") is False


def teste_ponto_e_underline_no_nome_contam_como_nome():
    """`karla.alves` tem ponto; `maria_souza` tem underline. Nenhum e digito,
    e os dois sao gente da casa."""
    assert st.e_da_casa("karla.alves@movisat.com.br") is True
    assert st.e_da_casa("maria_souza@movisat.com.br") is True
    # ⚠️ Mas telefone com separador segue sendo telefone.
    assert st.e_da_casa("99739-4026@movisat.com.br") is False
    assert st.e_da_casa("+5518997394026@movisat.com.br") is False
