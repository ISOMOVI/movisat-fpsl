"""A REGRA DA OS DE RETIRADA — uma só, para os dois caminhos de geração.

🔵 17/11, DECISÃO DELE: *"nenhuma OS de retirada pode ter item de comodato
flegado"*, delimitada por ele no mesmo dia em três frases: *"somente na de
retirada. Demais tipos não pode mexer"*, *"Sub retirada não é só retirada"* e
*"somente rescisão"*. Sobre o desenho: *"1 regra só para as duas, evitar lixo"*.

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
# perfil `rescisao` nos DOIS configs, e nenhum outro perfil usa 57 -- nem o
# `tipo_id_retirada` 73 da Substituição, que ele deixou FORA de propósito. A
# trava do teste prende isso, para que mudar um config não faça a regra deixar
# de pegar em silêncio.
TIPO_OS_RETIRADA = 57


def eh_retirada(op: dict) -> bool:
    """Esta OS é a de retirada?"""
    return op.get("tipo_id") == TIPO_OS_RETIRADA


def aplicar(operacoes: list[dict]) -> list[dict]:
    """Apaga a flag de comodato dos materiais de toda OS de retirada.

    Devolve a MESMA lista, com o `op` mutado no lugar: a prévia e a gravação
    leem a mesma lista, e devolver uma cópia deixaria uma das duas para trás.
    Os dicts de material são trocados por cópias, para não mexer em item que
    outra OS do mesmo termo esteja compartilhando.
    """
    for op in operacoes or []:
        if not eh_retirada(op):
            continue
        materiais = op.get("materiais") or []
        tinham = [m.get("descricao") for m in materiais if m.get("comodato")]
        if not tinham:
            continue
        op["materiais"] = [{**m, "comodato": False} if m.get("comodato") else m
                           for m in materiais]
        log.info("retirada: OS tipo %s saiu SEM comodato em %s",
                 TIPO_OS_RETIRADA, ", ".join(t or "?" for t in tinham))
    return operacoes
