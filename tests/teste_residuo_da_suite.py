# -*- coding: utf-8 -*-
"""A suíte não deixa lixo no banco de produção — e isto é teste, não confiança.

🚨 NASCEU DE UM DANO MEDIDO EM 18/11, na primeira vez que a suíte inteira do
FPSL rodou. Comparando o banco com a cópia tirada antes:

    ANTES   os_historico=675  operacoes_espera=132
    DEPOIS  os_historico=675  operacoes_espera=133

A linha a mais era de teste, e estava assim:

    id=2815  lote=TESTE-F5B  numero_os=990001  placa=AAA 0A00
    estado=esperando  ultimo_erro='erro inesperado: estourei de proposito'

⚠️ E `estado='esperando'` é exatamente o que `operacoes_espera.pendentes()`
seleciona. A fila de retentativa **de verdade** iria pegar essa linha e tentar
processar uma OS que não existe, gastando chamadas num ERP que esgota o pool
todo dia. Lixo de teste em tabela de fila não é sujeira: é trabalho falso que
alguém vai executar.

🚨 POR QUE UM TESTE E NÃO UMA LIMPEZA AUTOMÁTICA no `conftest`. Apagar o
resíduo em silêncio faria a suíte ficar verde **por limpar**, e o arquivo que
vaza continuaria vazando sem ninguém saber. Aqui o vazamento aparece com nome,
e quem conserta é quem escreveu o arquivo que vazou.

⚠️ Roda depois dos `teste_operacoes_*` porque o pytest coleta em ordem
alfabética e `r` vem depois de `o`. Frágil como toda ordem implícita -- mas o
pior caso é acusar resíduo de uma rodada anterior, que também é verdade.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso import storage  # noqa: E402

# OS de verdade vão até 17 mil; 99xxxx é a faixa que os testes usam.
PRIMEIRA_OS_FALSA = 990000


def test_nenhuma_fila_de_operacao_com_marca_de_teste():
    """🚨 O defeito exato de 18/11: linha `TESTE-*` em `esperando`."""
    with storage._connect() as conn:
        sobrou = conn.execute(
            "SELECT id, lote, numero_os, estado FROM operacoes_espera "
            " WHERE lote LIKE 'TESTE%' OR numero_os >= ?",
            (PRIMEIRA_OS_FALSA,)).fetchall()
    assert not sobrou, (
        f"a suite deixou {len(sobrou)} linha(s) de teste em `operacoes_espera`: "
        f"{sobrou}. ⚠️ `pendentes()` seleciona `estado='esperando'`, entao a "
        f"fila de retentativa real vai tentar processar OS que nao existem. "
        f"Quem criou essas linhas tem de apaga-las no proprio arquivo.")


def test_nenhuma_OS_falsa_no_cache():
    """O cache de OS é o que o card do painel lê: OS 99xxxx viraria card."""
    with storage._connect() as conn:
        sobrou = conn.execute(
            "SELECT numero_os FROM os_historico WHERE numero_os >= ?",
            (PRIMEIRA_OS_FALSA,)).fetchall()
    assert not sobrou, (
        f"a suite deixou {len(sobrou)} OS de teste na `os_historico`: "
        f"{[r[0] for r in sobrou]}. Elas apareceriam como card no painel.")


def test_o_banco_deste_teste_e_o_DE_PRODUCAO():
    """⚠️ Guarda do próprio guarda: se um módulo vazar `storage.DB_PATH` para
    um banco temporário, estes dois testes passariam por olhar o lugar errado —
    e foi um vazamento desse tipo que derrubou 4 testes em 18/11."""
    import conftest
    assert storage.DB_PATH == conftest.BANCO_DE_PRODUCAO, (
        f"este teste esta olhando {storage.DB_PATH}, nao o banco de producao "
        f"({conftest.BANCO_DE_PRODUCAO}) -- nao da para afirmar nada sobre "
        f"residuo olhando outro banco")
