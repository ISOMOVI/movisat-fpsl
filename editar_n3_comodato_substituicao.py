# -*- coding: utf-8 -*-
"""N3 — a Substituição (retirada E instalação) deixa de flegar comodato.

🔵 ELE, 23/11: *"No FPSL, as OS de substituição retirada e instalação, NÃO
DEVEM ter o flag de comodato"*.

🚨 ISTO ESTENDE A REGRA DE 17/11, NÃO CRIA UMA NOVA. Em 17/11 ele decidiu
*"nenhuma OS de retirada pode ter item de comodato flegado"* e delimitou no
mesmo dia: *"somente rescisão"*, *"Sub retirada não é só retirada"*. O
`operacoes_retirada` nasceu com `TIPO_OS_RETIRADA = 57` e o teste daquele dia
**prende de propósito** que o 73 da Substituição continuasse flegando. Hoje ele
mudou o alcance da própria regra -- então o que muda é a LISTA DE TIPOS, e os
dois caminhos de geração herdam a mudança sem copiar nada.

🚨 E É POR ISSO QUE A PROPOSTA DE CHAVE NOVA NO PERFIL (`sem_comodato`) FOI
DESCARTADA: ela colocaria a decisão no construtor do item, que existe DUAS
vezes (`operacoes_os.material_do_equipamento` e
`os_router._material_do_equipamento`) -- o gêmeo que o módulo de 17/11 existe
para evitar. A regra única já roda nos dois caminhos, depois do cabeçalho e
dentro da montagem que a prévia e a gravação dividem.

⚠️ E O CONSERTO "ÓBVIO" SEGUE ERRADO, por medição de 23/11: ligar `sem_flags`
no perfil `substituicao` zeraria `valor_unitario` (o ST310U sairia R$ 0,00
contra R$ 1.100,00 do contrato) e mataria a OS financeira. Esta regra **só
apaga a flag**: não lê valor, não toca `cobrar`, não remove item.

⚠️ O PASSADO NÃO É CORRIGIDO -- decisão dele em 17/11: *"não devemos corrigir,
apenas evitar que nasçam novamente"*. Vale igual para as OS de substituição já
geradas.
"""
import pathlib

ALVOS = {}


def abrir(rel):
    p = pathlib.Path(rel)
    bruto = p.read_bytes()
    ALVOS[rel] = {"p": p, "crlf": b"\r\n" in bruto,
                  "t": bruto.decode("utf-8").replace("\r\n", "\n")}
    return rel


def troca(rel, velho, novo, rotulo):
    d = ALVOS[rel]
    assert velho in d["t"], "NAO ACHOU (%s)" % rotulo
    assert d["t"].count(velho) == 1, "AMBIGUO %dx (%s)" % (
        d["t"].count(velho), rotulo)
    d["t"] = d["t"].replace(velho, novo, 1)
    print("  ok:", rotulo)


# ===========================================================================
# 1. A REGRA — de um tipo para três
# ===========================================================================
MOD = abrir("fpsl_weso/painel/operacoes_retirada.py")

troca(MOD,
      '''"""A REGRA DA OS DE RETIRADA — uma só, para os dois caminhos de geração.''',
      '''"""A REGRA DA OS QUE NÃO FLEGA COMODATO — uma só, para os dois caminhos.''',
      "1a. o titulo do modulo diz o que a regra e hoje")

troca(MOD,
      '''🔵 17/11, DECISÃO DELE: *"nenhuma OS de retirada pode ter item de comodato
flegado"*, delimitada por ele no mesmo dia em três frases: *"somente na de
retirada. Demais tipos não pode mexer"*, *"Sub retirada não é só retirada"* e
*"somente rescisão"*. Sobre o desenho: *"1 regra só para as duas, evitar lixo"*.''',
      '''🔵 17/11, DECISÃO DELE: *"nenhuma OS de retirada pode ter item de comodato
flegado"*, delimitada por ele no mesmo dia em três frases: *"somente na de
retirada. Demais tipos não pode mexer"*, *"Sub retirada não é só retirada"* e
*"somente rescisão"*. Sobre o desenho: *"1 regra só para as duas, evitar lixo"*.

🔵 23/11, ELE AMPLIOU O ALCANCE DA PRÓPRIA REGRA: *"No FPSL, as OS de
substituição retirada e instalação, NÃO DEVEM ter o flag de comodato"*. Então
os tipos **73** (Substituição Retirada) e **72** (Substituição Instalação)
entraram, e a delimitação de 17/11 que os deixava fora **deixou de valer** --
por decisão dele, não por releitura minha. O teste daquele dia prendia o 73
fora de propósito, e a trava foi invertida junto, citando esta frase.

🚨 ESTE É O LUGAR CERTO DA MUDANÇA, e a alternativa foi medida e descartada em
23/11: pôr uma chave `sem_comodato` no perfil faria a decisão morar no
construtor do item, que existe DUAS vezes
(`operacoes_os.material_do_equipamento` e
`os_router._material_do_equipamento`) -- exatamente o gêmeo que este módulo
existe para evitar. Aqui é uma linha e os dois caminhos herdam.

⚠️ E O CONSERTO "ÓBVIO" É ERRADO: ligar `sem_flags` no perfil `substituicao`
zeraria o `valor_unitario` (medido em 14/08: o ST310U sairia R$ 0,00 contra os
R$ 1.100,00 do contrato) e não geraria a OS financeira. `sem_flags` é a decisão
*"manutenção não flega nada"*, não um interruptor de comodato.''',
      "1b. a decisao de 23/11 fica registrada no modulo")

troca(MOD,
      '''# O Tipo "Retirada" do Harmonit. 🚨 MEDIDO, NÃO LEMBRADO: é o `tipo_id` do
# perfil `rescisao` nos DOIS configs, e nenhum outro perfil usa 57 -- nem o
# `tipo_id_retirada` 73 da Substituição, que ele deixou FORA de propósito. A
# trava do teste prende isso, para que mudar um config não faça a regra deixar
# de pegar em silêncio.
TIPO_OS_RETIRADA = 57


def eh_retirada(op: dict) -> bool:
    """Esta OS é a de retirada?"""
    return op.get("tipo_id") == TIPO_OS_RETIRADA''',
      '''# O Tipo "Retirada" do Harmonit. 🚨 MEDIDO, NÃO LEMBRADO: é o `tipo_id` do
# perfil `rescisao` nos DOIS configs, e nenhum outro perfil usa 57. A trava do
# teste prende isso, para que mudar um config não faça a regra deixar de pegar
# em silêncio.
TIPO_OS_RETIRADA = 57

# 🔵 23/11, DELE: a Substituição entrou. Os dois tipos vêm do perfil
# `substituicao`, e estão nos DOIS configs com os mesmos números --
# `tipo_id_retirada = 73` e `tipo_id_instalacao = 72`.
# ⚠️ NÃO são "retirada" no sentido de 17/11 (*"Sub retirada não é só
# retirada"*, dele): a Substituição retira E instala no mesmo termo. O que
# mudou é que agora nenhuma das duas pontas flega comodato.
TIPO_OS_SUB_RETIRADA = 73
TIPO_OS_SUB_INSTALACAO = 72

# 🚨 A LISTA É A REGRA. Acrescentar tipo aqui é a única mudança necessária para
# ampliar o alcance -- os dois routers chamam `aplicar` e não conhecem número
# nenhum. É isso que impede a regra de nascer uma terceira vez.
TIPOS_SEM_COMODATO = frozenset({
    TIPO_OS_RETIRADA, TIPO_OS_SUB_RETIRADA, TIPO_OS_SUB_INSTALACAO,
})


def sem_comodato(op: dict) -> bool:
    """Esta OS é de um tipo que não pode flegar comodato?"""
    return op.get("tipo_id") in TIPOS_SEM_COMODATO''',
      "1c. os tres tipos, e a pergunta deixa de ser so sobre retirada")

troca(MOD,
      '''def aplicar(operacoes: list[dict]) -> list[dict]:
    """Apaga a flag de comodato dos materiais de toda OS de retirada.''',
      '''def aplicar(operacoes: list[dict]) -> list[dict]:
    """Apaga a flag de comodato dos materiais das OS que não podem flegá-la.''',
      "1d. a docstring do aplicar")

troca(MOD,
      '''        if not eh_retirada(op):''',
      '''        if not sem_comodato(op):''',
      "1e. o laco usa a pergunta nova")

troca(MOD,
      '''        log.info("retirada: OS tipo %s saiu SEM comodato em %s",
                 TIPO_OS_RETIRADA, ", ".join(t or "?" for t in tinham))''',
      '''        # ⚠️ O TIPO VEM DO `op`, NÃO DA CONSTANTE: com três tipos na regra,
        # imprimir 57 sempre faria o log mentir sobre qual OS foi tratada --
        # e este log é o que prova, depois, que a regra pegou.
        log.info("sem comodato: OS tipo %s saiu SEM comodato em %s",
                 op.get("tipo_id"), ", ".join(t or "?" for t in tinham))''',
      "1f. o log diz o tipo de verdade")


# ===========================================================================
# 2. A TRAVA DE 17/11 — invertida no ponto que prendia o 73 fora
# ===========================================================================
TS = abrir("tests/teste_retirada_sem_comodato.py")

troca(TS,
      '''"""Nenhuma OS de retirada sai com item de comodato flegado — 17/11.''',
      '''"""Nenhuma OS de retirada nem de Substituição sai com comodato — 17 e 23/11.''',
      "2a. o titulo do teste")

troca(TS,
      '''  1. **A trava do tipo:** 57 é o `tipo_id` do perfil `rescisao` nos DOIS
     configs, nenhum outro perfil usa 57, e o 73 da Substituição Retirada
     fica de fora. Mudar um config faria a regra deixar de pegar em silêncio;
     aqui ela reprova antes.''',
      '''  1. **A trava do tipo:** 57 é o `tipo_id` do perfil `rescisao` nos DOIS
     configs e nenhum outro perfil usa 57; **73 e 72 são a Substituição nos
     dois configs**. Mudar um config faria a regra deixar de pegar em
     silêncio; aqui ela reprova antes.
     🔵 **23/11, ELE AMPLIOU:** *"as OS de substituição retirada e instalação,
     NÃO DEVEM ter o flag de comodato"*. A delimitação de 17/11 (*"somente
     rescisão"*) deixou de valer **por decisão dele**, e os pontos 1 e 6 deste
     arquivo foram invertidos junto -- um teste que continuasse prendendo o 73
     flegado estaria prendendo a decisão antiga.''',
      "2b. o ponto 1 do cabecalho")

troca(TS,
      '''  6. **Os outros tipos não se movem:** Substituição Retirada (73), contrato
     (76), upgrade (77), manutenção (1783) e a financeira (2) saem idênticos.''',
      '''  6. **Os outros tipos não se movem:** contrato (76), upgrade (77),
     manutenção (1783) e a financeira (2) saem idênticos. **A Substituição
     (73 e 72) agora se move**, e sai com o VALOR DE PÉ -- é o par que o
     conserto errado (`sem_flags`) quebraria, e por isso as duas coisas são
     cobradas na mesma trava.''',
      "2c. o ponto 6 do cabecalho")

troca(TS,
      '''        # 🔵 DELE: *"Sub retirada não é só retirada"* -- o 73 fica fora.
        subs = [k for k, v in perfis.items()
                if v.get("tipo_id_retirada") == ret.TIPO_OS_RETIRADA]
        checar(f"config {nome}: nenhum tipo_id_retirada é 57 (o 73 fica fora)",
               subs == [], str(subs))''',
      '''        # 🔵 23/11, DELE: a Substituição ENTROU na regra. 🚨 Os números
        # vêm do config, não da memória: se alguém trocar o tipo da
        # Substituição num dos dois configs, a regra deixaria de pegar em
        # silêncio -- e é isto que reprova antes.
        sub = perfis["substituicao"]
        checar(f"config {nome}: Sub retirada é 73 e está na regra",
               sub["tipo_id_retirada"] == ret.TIPO_OS_SUB_RETIRADA
               and sub["tipo_id_retirada"] in ret.TIPOS_SEM_COMODATO,
               str(sub.get("tipo_id_retirada")))
        checar(f"config {nome}: Sub instalação é 72 e está na regra",
               sub["tipo_id_instalacao"] == ret.TIPO_OS_SUB_INSTALACAO
               and sub["tipo_id_instalacao"] in ret.TIPOS_SEM_COMODATO,
               str(sub.get("tipo_id_instalacao")))
        # ⚠️ E a regra não cresceu além do que ele pediu: três tipos, e só.
        checar(f"config {nome}: a regra tem exatamente 3 tipos",
               ret.TIPOS_SEM_COMODATO == {57, 73, 72},
               str(sorted(ret.TIPOS_SEM_COMODATO)))''',
      "2d. a trava do tipo passa a cobrar o 73 e o 72 DENTRO da regra")

troca(TS,
      '''    # 🔵 DELE: *"Demais tipos não pode mexer"*. 73 = Substituição Retirada.
    outros = {"Substituição Retirada": 73, "contrato": 76, "upgrade": 77,
              "manutenção": 1783, "financeira": cfg.TIPO_CONTRATO_ID}''',
      '''    # 🔵 DELE: *"Demais tipos não pode mexer"*. ⚠️ O 73 SAIU desta lista em
    # 23/11, quando ele ampliou a regra -- ver a seção 8.
    outros = {"contrato": 76, "upgrade": 77,
              "manutenção": 1783, "financeira": cfg.TIPO_CONTRATO_ID}''',
      "2e. o 73 sai da lista dos que nao se movem")


# ===========================================================================
# 3. A SEÇÃO 8 — a Substituição, com o valor de pé (o par que importa)
# ===========================================================================
troca(TS,
      '''# ── 7. a ordem da chamada, no fonte ──────────────────────────────────────────''',
      '''# ── 8. a Substituição: sem comodato E com o valor de pé ──────────────────────

def teste_substituicao_sem_comodato_com_valor():
    """🔵 23/11, DELE: *"as OS de substituição retirada e instalação, NÃO DEVEM
    ter o flag de comodato"*.

    🚨 AS DUAS COISAS NA MESMA TRAVA, de propósito: é o par que o conserto
    errado quebraria. Ligar `sem_flags` no perfil `substituicao` apagaria o
    comodato **e** zeraria o `valor_unitario` (medido em 14/08: o ST310U
    sairia R$ 0,00 contra os R$ 1.100,00 do contrato) **e** não geraria a OS
    financeira. Cobrar só o comodato deixaria a porta aberta para esse
    conserto passar verde.

    ⚠️ O item é montado pelo CONSTRUTOR DE VERDADE
    (`operacoes_os.material_do_equipamento`), não escrito à mão: é ele que
    herda o valor do rastreador que está saindo, e é essa herança que precisa
    sobreviver.
    """
    print("\\n8. Substituição (73 e 72): sem comodato, com o valor de pé")
    perfil = cfg.PERFIS["substituicao"]
    checar("o perfil NÃO tem sem_flags (senão o valor zeraria)",
           not perfil.get("sem_flags"), str(perfil.get("sem_flags")))

    # O de-para sem valor patrimonial (os 2G) devolve 0.0, e aí o valor TEM de
    # vir do item que está saindo -- a herança de 14/08.
    saindo = [{"descricao": "RASTREADOR ST310U", "harmonit_id": 20314,
               "quantidade": 1, "valor_unitario": 1100.0, "comodato": True}]
    guardado_modelo = oos.modelo_da_operacao
    guardado_produto = oos.storage.produto_do_modelo
    try:
        oos.modelo_da_operacao = (
            lambda perfil, placa, materiais, recipientes=None, dados=None:
            "ST310U")
        oos.storage.produto_do_modelo = lambda modelo: {
            "harmonit_id": 20314, "descricao": "RASTREADOR ST310U",
            "valor": None}
        item = oos.material_do_equipamento(perfil, PLACAS[0], saindo)
    finally:
        oos.modelo_da_operacao = guardado_modelo
        oos.storage.produto_do_modelo = guardado_produto

    checar("o construtor herda o valor do item que sai",
           item and item["valor_unitario"] == 1100.0, str(item))
    # 🚨 ANTES DA REGRA O ITEM VEM FLEGADO, e é isso que faz a trava provar
    # algo: teste que não reprova no código de antes não prova nada.
    checar("o construtor ainda flega comodato (a regra é quem apaga)",
           item and item["comodato"] is True, str(item))

    for nome, tipo in (("Sub retirada", ret.TIPO_OS_SUB_RETIRADA),
                       ("Sub instalação", ret.TIPO_OS_SUB_INSTALACAO)):
        op = {"tipo_id": tipo, "materiais": [dict(item)]}
        ret.aplicar([op])
        m = op["materiais"][0]
        checar(f"{nome} ({tipo}): sai SEM comodato",
               m["comodato"] is False, str(m))
        checar(f"{nome} ({tipo}): o valor patrimonial FICA DE PÉ",
               m["valor_unitario"] == 1100.0, str(m))

    # ⚠️ E a financeira da Substituição é EMBUTIDA (`financeira_embutida`), com
    # `cobrar = True` e sem comodato -- a regra não a alcança, e o valor dela
    # não muda. Se mudasse, o conserto estaria matando a cobrança do serviço.
    checar("a financeira embutida segue com valor e cobrança",
           perfil.get("financeira_servico_valor") == 299.9
           and perfil.get("financeira_servico_cobrar") is True,
           str(perfil.get("financeira_servico_valor")))


# ── 7. a ordem da chamada, no fonte ──────────────────────────────────────────''',
      "3. a secao 8, com o par comodato x valor")


troca(TS,
      """    teste_nao_toca_o_resto()
    teste_ordem_no_fonte()""",
      """    teste_nao_toca_o_resto()
    teste_substituicao_sem_comodato_com_valor()
    teste_ordem_no_fonte()""",
      "4. a secao 8 entra no runner (senao seria trava que nunca roda)")


for rel, d in ALVOS.items():
    saida = d["t"].replace("\n", "\r\n") if d["crlf"] else d["t"]
    d["p"].write_bytes(saida.encode("utf-8"))
    print("gravado:", rel, len(saida), "bytes")
