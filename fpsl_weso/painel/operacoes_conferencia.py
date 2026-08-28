"""Conferência da leitura do termo — o termo diz quantos veículos tem.

🚨 O QUE ESTE MÓDULO RESOLVE. Ele mandou o termo 8687 acusando "placa não
reconhecida". A placa estava certa (`FBI 8A36`, e existe na WESO e no Harmonit):
o que entrou na lista de veículos foi a LINHA DO TOTAL, porque nesse layout ela
mora dentro da tabela de veículos, na coluna dos veículos. O extrator não acha
que o total é uma placa -- ele acha que aquela linha é um veículo, e nela não
encontra placa nenhuma. Dentro da regra dele, está sendo honesto.

🚨 POR QUE NÃO SE CLASSIFICA A LINHA. Tentei duas regras antes desta e as duas
eram remendo:

  - `X....X` (só a 1ª e a última coluna preenchidas): acerta 2 de 87 linhas com
    0 falsos positivos, mas é GEOMETRIA. Quebra no dia em que o rodapé tiver
    uma coluna a mais, ou o total mudar de lugar.
  - "linha de veículo preenche outras colunas": MORREU no teste. Os dois totais
    preenchem uma outra coluna (o valor), e há veículo legítimo em
    `cliente_novo.pdf` preenchendo exatamente uma também.

⚠️ E o layout MUDA entre gerações do mesmo perfil -- foi isso que produziu o
erro, não uma regressão de código:

    8820 e 8800 .... total em tabela PRÓPRIA de 2 colunas   -> nunca poluiu
    8827 e 8687 .... total é a ÚLTIMA LINHA da tabela        -> polui

🚨 A SOLUÇÃO É ARITMÉTICA, E O DOCUMENTO A CARREGA. Todo termo de upgrade diz
quantos veículos tem, não num campo "quantidade", mas na taxa:

    8820:    R$ 100,00 ÷ R$  50,00 =  2   -> 2 placas lidas
    8827:    R$ 200,00 ÷ R$ 200,00 =  1   -> 1
    8800:  R$ 2.200,00 ÷ R$ 200,00 = 11   -> 11
    8687:    R$ 200,00 ÷ R$ 200,00 =  1   -> 1

Conferir contra o declarado não olha forma de linha, não depende de o rótulo
vir duplicado, nem de o total estar na última linha, nem do número de colunas.
Se o gerador do termo mudar de layout outra vez, a conta continua valendo.

E ganha o que nenhuma das outras tinha: **detecta veículo que SUMIU**, não só
linha que sobrou. Hoje, se uma placa deixasse de ser lida, ninguém saberia.

⚠️ SÓ DA ABA OPERAÇÕES, por decisão dele em 28/08: *"não deve ter vínculo com
as outras duas, não importa se geraria diferente, precisa funcionar nesta nova
tela"*. O `pdf_extractor` não muda -- Gerar OS, Vínculos e Cadastro de placas
seguem exatamente como estão, e a divergência entre telas é de propósito.
"""
import logging
import re

from .pdf_extractor import _ler_paginas, _normalizar
from .operacoes_extracao import _eh_rotulo_do_total, desdobrar

log = logging.getLogger(__name__)

_VALOR = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

# Cabeçalho da coluna que traz a taxa por veículo, sem acento.
_COLUNA_TAXA = "TAXADEMIGRACAO"


def _numero(texto) -> float | None:
    if not texto:
        return None
    try:
        return float(str(texto).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def valor_bruto(celula) -> float | None:
    """O PRIMEIRO valor monetário da célula — o oposto do `_valor_ativo`.

    🚨 A MESMA CÉLULA É LIDA DOS DOIS JEITOS, E OS DOIS ESTÃO CERTOS. A taxa vem
    riscada nos quatro termos (`R$ 200,00` + `R$ 0,00*`):

        para a FINANCEIRA -> `_valor_ativo` pega o ÚLTIMO (0,00), porque a
          cobrança foi cancelada. Regra existente, correta, intocada.
        para a CONTAGEM   -> tem de pegar o PRIMEIRO. `0 ÷ 0` não conta nada.

    ⚠️ Reusar `_valor_ativo` aqui -- que era o caminho óbvio -- daria divisão
    por zero nos QUATRO termos, e a conferência ficaria morta com placar verde.
    """
    achados = _VALOR.findall(str(celula or ""))
    return _numero(achados[0]) if achados else None


def _indice_coluna_taxa(header: list) -> int | None:
    """Onde fica a coluna da taxa por veiculo.

    ⚠️ COMPARA SEM ESPACO DOS DOIS LADOS. `_normalizar` tira o acento e junta a
    quebra de linha, mas MANTEM o espaco: o cabecalho de duas linhas vira
    `TAXA DE MIGRACAO`. Eu tinha copiado o estilo da constante do total
    (`TOTALDAMIGRACAO`), que e comparada contra texto ja colapsado pelo
    `desdobrar` -- e a coluna nunca casava, deixando a conferencia muda nos
    quatro termos com placar verde.
    """
    for i, h in enumerate(header):
        if _COLUNA_TAXA in _normalizar(str(h or "")).replace(" ", ""):
            return i
    return None


def quantidade_declarada(fonte) -> tuple[int | None, str]:
    """(quantos veículos o termo declara, como foi apurado).

    Devolve (None, motivo) quando o termo não declara -- e aí a conferência
    simplesmente não acontece, sem inventar nada.
    """
    unitario = None
    total = None
    for pagina in _ler_paginas(fonte):
        for tabela in pagina["tabelas"] or []:
            if not tabela:
                continue
            idx_taxa = _indice_coluna_taxa(tabela[0])
            if idx_taxa is not None:
                for linha in tabela[1:]:
                    if idx_taxa >= len(linha):
                        continue
                    v = valor_bruto(linha[idx_taxa])
                    # ⚠️ O unitário é o MESMO em todas as linhas nos quatro
                    # termos. Pega-se o primeiro que aparecer; se um dia
                    # divergir, a conta não fecha e a conferência se cala --
                    # que é o comportamento seguro.
                    if v and v > 0:
                        unitario = v
                        break
            # O total: seja última linha da tabela de veículos (8827, 8687),
            # seja tabela própria de 2 colunas (8820, 8800).
            for linha in tabela:
                idx = next((i for i, c in enumerate(linha)
                            if _eh_rotulo_do_total(c)), None)
                if idx is None:
                    continue
                for c in linha[idx + 1:]:
                    v = valor_bruto(c)
                    if v and v > 0:
                        total = v
                        break

    if unitario is None or total is None:
        return None, "o termo não traz taxa por veículo e total para conferir"
    if unitario <= 0:
        return None, "a taxa por veículo veio zerada"

    bruto = total / unitario
    quantos = round(bruto)
    # ⚠️ Só vale se a divisão for EXATA. Sobra de centavo quer dizer que eu
    # entendi errado uma das duas pontas -- e aí é melhor não conferir do que
    # conferir com número errado.
    if quantos < 1 or abs(bruto - quantos) > 0.01:
        return None, (f"total {total:.2f} ÷ unitário {unitario:.2f} não dá "
                      f"número inteiro de veículos")
    return quantos, f"total {total:.2f} ÷ unitário {unitario:.2f}"


def conferir(fonte, campos: dict) -> dict:
    """Confere a leitura contra o que o termo declara e limpa o que sobrou.

    Devolve um relatório e MEXE em `campos["veiculos_sem_placa"]` só quando a
    conta fecha.

    🚨 DESCARTAR É SILENCIOSO NA TELA, MAS CONTADO NA RESPOSTA. Trocar aviso
    ruidoso por sumiço calado seria voltar ao defeito que o `RFD 2447` deixou
    registrado neste código: placa inventada é pior que placa faltando, e placa
    apagada em silêncio é da mesma família.
    """
    lidos = len(campos.get("placas") or [])
    sobra = list(campos.get("veiculos_sem_placa") or [])
    declarado, como = quantidade_declarada(fonte)

    relatorio = {
        "declarado": declarado,
        "lidos": lidos,
        "como": como,
        "descartadas": [],
        "conferido": False,
        "aviso": None,
    }

    if declarado is None:
        return relatorio

    relatorio["conferido"] = True

    if lidos == declarado:
        # A leitura fecha com o termo: o que sobrou NÃO é veículo.
        relatorio["descartadas"] = sobra
        campos["veiculos_sem_placa"] = []
        if sobra:
            log.info("conferencia: %s veiculo(s) conforme o termo; %s linha(s) "
                     "descartada(s) como rodape", declarado, len(sobra))
        return relatorio

    if lidos < declarado:
        # 🚨 FALTA VEÍCULO. A sobra deixa de ser ruído e passa a ser candidata:
        # é exatamente para isto que a revisão humana existe.
        relatorio["aviso"] = (
            f"O termo declara {declarado} veículo(s) e eu li {lidos}. "
            f"Confira as linhas abaixo antes de gerar.")
        return relatorio

    relatorio["aviso"] = (
        f"Li {lidos} veículo(s) e o termo declara {declarado}. "
        f"Alguma linha foi contada duas vezes — confira antes de gerar.")
    return relatorio
