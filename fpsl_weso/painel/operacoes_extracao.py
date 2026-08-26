"""Leituras do termo que SÓ a aba Operações faz. 2026-08-26.

🚨 EXISTE PARA NÃO TOCAR O `pdf_extractor`. Aquele arquivo é lido por TRÊS
telas -- a aba Operações, a tela velha de Gerar OS e o Cadastro de Placas -- e
o pedido do usuário foi explícito: o ajuste é só da aba nova. Regra que muda
entre as telas se clona; infraestrutura sem regra se reusa. Daqui de dentro o
`pdf_extractor` só é LIDO (`_ler_paginas`, `_valor_ativo`), nunca alterado.

O que se lê aqui hoje: a TAXA DE MIGRAÇÃO do termo de Upgrade.

⚠️ POR QUE ELA NÃO CABIA NO EXTRATOR GENÉRICO. O layout do Upgrade não tem
tabela de itens -- tem uma linha por veículo com as colunas `VEÍCULOS A
MIGRAR`, `DOCUMENTO REFERÊNCIA`, `TAXA DE MIGRAÇÃO` e `NOVO VALOR MENSAL`. Sem
coluna de tipo, sem `COMODATO`. Por isso `itens` sempre voltou vazio e TODA OS
financeira de upgrade saiu `SEM CUSTO`: 8820, 8834, 8844 e 8827.

🚨 O VALOR VEM DO TOTAL, E O TOTAL VEM RISCADO EM 2 DOS 3 TERMOS REAIS:

    8827   R$ 200,00 (Boleto a vista)                       -> cobra 200,00
    8820   R$ 100,00 / R$ 0,00*  "Negociação especial"      -> não cobra
    8800   R$ 2.200,00 - R$ 0,00 "Condição especial ..."    -> não cobra

Ler o primeiro valor da célula cobraria R$ 100,00 e R$ 2.200,00 que os termos
CANCELARAM. É a mesma armadilha da taxa de retirada da rescisão, e o remédio é
o mesmo: `_valor_ativo` pega o ÚLTIMO valor, e encargo zerado não vira item.

⚠️ NENHUM ID FIXO EM CÓDIGO AQUI. O item sai com a DESCRIÇÃO e é o vínculo de
`painel_vinculos_itens` que diz qual serviço do Harmonit ele é -- igual a todo
item de termo. Sem vínculo ele vira PENDENTE e bloqueia a geração, que é
falha visível; id fixo apodreceria em silêncio, como o `tipo = 55`.
"""
import re
import unicodedata

from .pdf_extractor import _ler_paginas, _valor_ativo

# O rótulo, como fica depois de tirar acento, espaço e a duplicação de letras.
ROTULO_TOTAL_MIGRACAO = "TOTALDAMIGRACAO"
DESCRICAO_TAXA_MIGRACAO = "TAXA DE MIGRAÇÃO"

_VALOR_NA_CELULA = re.compile(r"\d")


def _sem_acento(txt: str) -> str:
    t = unicodedata.normalize("NFKD", str(txt or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def desdobrar(celula) -> str | None:
    """Texto de célula em que CADA LETRA está duplicada, ou None.

    🚨 O RÓTULO DO TOTAL VEM `TTOOTTAALL DDAA MMIIGGRRAAÇÇÃÃOO`. É negrito
    sobreposto no PDF, e acontece nos três termos de upgrade.

    ⚠️ SÓ DESDOBRA QUANDO A CÉLULA INTEIRA TEM O PADRÃO, e o resultado NUNCA é
    gravado em campo nenhum -- serve só para comparar rótulo. Varri as 15
    fixtures: o mesmo padrão aparece em `Franquia mensal: R$ 0,00` de quatro
    termos de contrato novo e transferência, que hoje são lidos certo. Aplicar
    o desdobramento no texto que vira dado estragaria esses.
    """
    s = re.sub(r"\s+", "", str(celula or ""))
    if len(s) >= 4 and len(s) % 2 == 0 and s[0::2] == s[1::2]:
        return s[0::2]
    return None


def _eh_rotulo_do_total(celula) -> bool:
    dobrado = desdobrar(celula)
    if dobrado is None:
        return False
    return _sem_acento(dobrado) == ROTULO_TOTAL_MIGRACAO


def _valor_da_linha(linha: list, idx_rotulo: int) -> str | None:
    """O valor ATIVO da linha do total, procurando da direita para a esquerda.

    ⚠️ A POSIÇÃO MUDA ENTRE OS TERMOS: no 8827 o total está na última linha da
    tabela de veículos, com o valor na 6ª coluna; no 8820 e no 8800 está numa
    tabela própria de 2 colunas. Procurar por posição fixa acertaria um e
    perderia os outros.
    """
    for i in range(len(linha) - 1, -1, -1):
        if i == idx_rotulo:
            continue
        celula = linha[i]
        if not celula or not _VALOR_NA_CELULA.search(str(celula)):
            continue
        valor = _valor_ativo(celula)
        if valor:
            return valor
    return None


def taxa_de_migracao(fonte) -> tuple[dict | None, list[str]]:
    """(item, avisos). O item já sai no formato de `itens_contrato`.

    `comodato_ou_aquisicao` fica None de propósito: `resolver_vinculos` traduz
    isso em comodato=False e cobrar = valor>0, que é o caminho de todo encargo.
    """
    avisos: list[str] = []
    for pagina in _ler_paginas(fonte):
        for tabela in pagina["tabelas"]:
            for linha in tabela or []:
                idx = next((i for i, c in enumerate(linha)
                            if _eh_rotulo_do_total(c)), None)
                if idx is None:
                    continue
                valor = _valor_da_linha(linha, idx)
                if not valor:
                    avisos.append(
                        "O termo tem a linha TOTAL DA MIGRAÇÃO mas não consegui "
                        "ler o valor dela — a taxa de migração NÃO entrou na OS "
                        "financeira. Confira o documento antes de gerar.")
                    return None, avisos
                try:
                    numero = float(valor.replace(".", "").replace(",", "."))
                except ValueError:
                    avisos.append(
                        f"O TOTAL DA MIGRAÇÃO do termo veio como {valor!r}, que "
                        "não é um valor que eu saiba ler — a taxa NÃO entrou na "
                        "OS financeira.")
                    return None, avisos
                if numero <= 0:
                    # 🚨 NÃO É ERRO, É O TERMO. Taxa riscada (8820, 8800) é
                    # cortesia concedida: não vira cobrança e não vira aviso,
                    # porque aviso falso treina a equipe a ignorar aviso.
                    return None, avisos
                return {"descricao": DESCRICAO_TAXA_MIGRACAO,
                        "quantidade": "1",
                        "valor_unitario": valor,
                        "comodato_ou_aquisicao": None,
                        "sera_devolvido": None}, avisos
    # Sem a linha do total não se inventa nada: nem item, nem soma das linhas
    # por veículo. O usuário decidiu em 26/08 que o valor é o TOTAL do termo,
    # "está escrito" -- somar por conta seria adivinhar.
    return None, avisos


def itens_extras(fonte, perfil: str) -> tuple[list[dict], list[str]]:
    """Itens que só esta aba lê, por perfil. Hoje: a taxa de migração."""
    if perfil != "upgrade":
        return [], []
    item, avisos = taxa_de_migracao(fonte)
    return ([item] if item else []), avisos
