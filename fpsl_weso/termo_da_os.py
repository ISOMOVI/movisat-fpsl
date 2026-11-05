# -*- coding: utf-8 -*-
r"""O TERMO de uma OS — extraído do texto da `descricao`.

🚨 **NÃO EXISTE COLUNA `termo` NA OS DO HARMONIT.** Medido em 05/11: o termo só
aparece **dentro do texto** da `descricao`, e em mais de um formato. Esta é a
única fonte, e por isso a extração é um módulo com teste próprio em vez de uma
linha dentro da varredura.

📏 **A MEDIÇÃO QUE DESENHOU A EXPRESSÃO** (200 OS lidas ao vivo em 05/11):
173 com termo · 27 sem · **0 descrições com mais de um termo distinto** ·
**0 descrições com a palavra TERMO sem número ao lado**. Os formatos vistos:

    FINANCEIRO — TERMO 8937 | placas: DMD 0324, ...
    Retirada: BUS 0168 | ... | TERMO 8937 | O.S: 17081
    SUBSTITUIÇÃO INSTALAÇÃO: A_DEFINIR_2_8927 | TERMO:8927 | ... | TERMO 8927
    RESSARCIMENTO: TERMO 8924 | placas: TKZ 6A06 | O.S: 17025

⚠️ **OS SEM TERMO É NORMAL, NÃO É FALHA.** As 27 da amostra são venda, compra
de cartão RFID, entrega de chaveiro e manutenção — nenhuma nasce de termo.
Quem mostra o dado escreve só o número da OS; inventar *"sem termo"* no card
seria ruído em 1 de cada 7.

🚨 **O NÚMERO É EXIGIDO.** A expressão pede dígitos depois de `TERMO`, não
`\S+`: sem isso, `TERMO DE ADESÃO` viraria o "termo" chamado *DE*. Nenhuma das
200 descrições tinha a palavra solta, mas a guarda custa nada e a descrição é
texto livre digitado por gente.
"""
import re

# `TERMO 8937`, `TERMO: 8937`, `TERMO:8927` — com ou sem dois-pontos, com ou
# sem espaço, em qualquer caixa (a régua da casa: varredura de rótulo ignora
# caixa).
_RE_TERMO = re.compile(r"\bTERMO\s*:?\s*(\d{1,10})\b", re.IGNORECASE)


def termo_da_descricao(descricao: str | None) -> str | None:
    """O número do termo escrito na descrição da OS, ou `None`.

    Devolve **texto**, não inteiro: é um identificador que se mostra e se
    procura, não um número com que se faz conta. E texto é o que a busca do
    painel compara.

    🚨 **MAIS DE UM TERMO DISTINTO NA MESMA DESCRIÇÃO DEVOLVE `None`**, e é de
    propósito: nenhuma das 200 medidas tinha dois, então o caso é desconhecido
    — e escolher o primeiro calado poria no card um termo que pode ser o
    errado. Nulo diz "não sei", que é a verdade.
    """
    achados = _RE_TERMO.findall(descricao or "")
    if not achados:
        return None
    # ⚠️ `TERMO:8927 ... TERMO 8927` é o MESMO termo escrito duas vezes — isso
    # existe e não é ambiguidade. O que desiste é termo DIFERENTE.
    distintos = {a.lstrip("0") or "0" for a in achados}
    if len(distintos) > 1:
        return None
    return distintos.pop()
