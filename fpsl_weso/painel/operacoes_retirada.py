"""A REGRA DA OS QUE NÃO FLEGA COMODATO — uma só, para os dois caminhos.

🔵 17/11, DECISÃO DELE: *"nenhuma OS de retirada pode ter item de comodato
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
*"manutenção não flega nada"*, não um interruptor de comodato.

🚨 ESTE MÓDULO EXISTE PORQUE A GERAÇÃO NASCEU DUAS VEZES. A aba Operações
(`routers/operacoes_router.py`) e a tela Gerar OS (`routers/os_router.py`) têm
cada uma a SUA cópia de `resolver_vinculos` e `material_do_equipamento`. Foi
esse gêmeo que escondeu o defeito: a regra de 13/11 (rescisão sem comodato)
entrou só no caminho novo, e na tela velha o item do CONTRATO continuou saindo
flegado até hoje -- o `_resolver_vinculos` dela não recebe nem o perfil, então
não tinha como aplicar a regra. Copiar a regra pela terceira vez seria repetir
o erro, e por isso ela não mora em nenhum dos dois.

🚨 A CHAVE É O TIPO DA OS, NÃO O PERFIL. Os dois caminhos têm configs
diferentes (`operacoes_config` e `templates_config`), com perfis de nomes
próprios, mas a OS de retirada é o tipo 57 nos dois, e os dois montam o mesmo
dicionário: `{"tipo_id": ..., "materiais": [...]}`. O tipo é a única pergunta
que as duas sabem responder igual -- e é a pergunta que a decisão dele faz.

⚠️ QUEM CHAMA TEM DE CHAMAR DEPOIS DO CABEÇALHO. Nos dois caminhos o `tipo_id`
só é definitivo depois dele: na tela velha o operador pode trocar o Tipo pelo
NOME (`_resolver_cabecalho_por_nome`), e chamar antes olharia um tipo que ainda
vai mudar. A ordem tem trava no `teste_retirada_sem_comodato`.

⚠️ O QUE ESTA REGRA PODE FAZER, E SÓ: apagar a flag de comodato de material de
OS tipo 57. Não lê valor, não toca `cobrar`, não remove nem reordena item, não
cria nem apaga OS. A financeira da rescisão é tipo 2 (`TIPO_CONTRATO_ID`) nos
dois caminhos, e por isso nunca passa por aqui.

🚨 VALE NA MONTAGEM, e isso é obrigatório, não zelo: a prévia mostra o selo
"comodato" por material (`frontend/operacoes.html`) e a tela velha promete por
escrito que *"o dry-run mostra o mesmo"* que o real. Regra aplicada só na
gravação faria a tela afirmar um flag que o Harmonit não recebeu -- e tela que
mente é defeito.

⚠️ O PASSADO NÃO É CORRIGIDO, por decisão dele em 17/11: *"não devemos
corrigir, apenas evitar que nasçam novamente"*. As OS de rescisão já geradas
com a flag ficam como estão.

⚠️ A ROTINA NÃO PASSA POR AQUI, e foi medido: o único `comodato: True` dela
(`operacoes_rotina._anexar_equipamento`) só roda no caso `recipiente`, que é
instalação com placa de teste, e nunca numa rescisão.
"""
import logging

log = logging.getLogger(__name__)

# O Tipo "Retirada" do Harmonit. 🚨 MEDIDO, NÃO LEMBRADO: é o `tipo_id` do
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
    return op.get("tipo_id") in TIPOS_SEM_COMODATO


def aplicar(operacoes: list[dict]) -> list[dict]:
    """Apaga a flag de comodato dos materiais das OS que não podem flegá-la.

    Devolve a MESMA lista, com o `op` mutado no lugar: a prévia e a gravação
    leem a mesma lista, e devolver uma cópia deixaria uma das duas para trás.
    Os dicts de material são trocados por cópias, para não mexer em item que
    outra OS do mesmo termo esteja compartilhando.
    """
    for op in operacoes or []:
        if not sem_comodato(op):
            continue
        materiais = op.get("materiais") or []
        tinham = [m.get("descricao") for m in materiais if m.get("comodato")]
        if not tinham:
            continue
        op["materiais"] = [{**m, "comodato": False} if m.get("comodato") else m
                           for m in materiais]
        # ⚠️ O TIPO VEM DO `op`, NÃO DA CONSTANTE: com três tipos na regra,
        # imprimir 57 sempre faria o log mentir sobre qual OS foi tratada --
        # e este log é o que prova, depois, que a regra pegou.
        log.info("sem comodato: OS tipo %s saiu SEM comodato em %s",
                 op.get("tipo_id"), ", ".join(t or "?" for t in tinham))
    return operacoes
