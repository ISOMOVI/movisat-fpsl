# -*- coding: utf-8 -*-
"""O que faz `pytest` rodar neste projeto — e o que ele deixa de fora.

🚨 DUAS COISAS, E AS DUAS VIERAM DE MEDIÇÃO EM 18/11.

**1. Os 64 scripts não são coletados.** Dos 81 arquivos `teste_*.py`, 64 não
têm nenhuma função de teste: são scripts, com tudo no topo do módulo
(`teste_trava_etapas.py` tem 191 chamadas soltas). O pytest importa o arquivo
para procurar testes, e o import **executa** o script -- foi assim que
`teste_roteadores_painel.py` derrubava a coleta inteira com um
`sqlite3.OperationalError: no such table`.

⚠️ A exclusão é por **AST, não por lista de nomes**. Lista fixa envelheceria no
primeiro script novo, e o arquivo de teste novo que caísse fora dela voltaria a
não rodar -- que é exatamente o defeito que isto conserta.

**2. Os testes `async` ganham o marcador do anyio.** São 55 em 9 arquivos, e
nunca rodaram: o `anyio` está no venv e o plugin de pytest dele está ativo, mas
sem marcador o pytest 9 recusa com *"async def functions are not natively
supported"*. 🔵 *"liga o async"* -- decisão dele, 18/11.

🚨 O marcador é posto aqui, e não nos 9 arquivos, por um motivo: marcar à mão
seria 9 arquivos editados hoje e o 10º esquecido amanhã.
"""
import ast
import inspect
import pathlib

import pytest

AQUI = pathlib.Path(__file__).resolve().parent


def _tem_funcao_de_teste(caminho: pathlib.Path) -> bool:
    """O arquivo tem alguma função de teste? ⚠️ Lê a fonte, não importa nada.

    🚨 Importar para descobrir é o próprio defeito: o import executa o script.
    """
    try:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- arquivo ilegível é problema dele, não daqui
        # ⚠️ Na dúvida, COLETA. Esconder um arquivo que não dá para ler faria o
        # pytest ficar verde por não olhar -- o oposto do que isto serve.
        return True
    funcoes = (ast.FunctionDef, ast.AsyncFunctionDef)
    for no in arvore.body:
        if isinstance(no, funcoes) and no.name.startswith("test"):
            return True
        if isinstance(no, ast.ClassDef):
            for membro in no.body:
                if isinstance(membro, funcoes) and membro.name.startswith("test"):
                    return True
    return False


collect_ignore = [
    str(c.relative_to(AQUI))
    for c in sorted((AQUI / "tests").glob("teste_*.py"))
    if not _tem_funcao_de_teste(c)
]


# 🚨 O BANCO DE PRODUÇÃO, CAPTURADO ANTES DE QUALQUER TESTE SER IMPORTADO.
# O `conftest.py` é o primeiro arquivo que o pytest importa, então aqui o
# `storage.DB_PATH` ainda é o de verdade.
from fpsl_weso import storage as _storage  # noqa: E402

BANCO_DE_PRODUCAO = _storage.DB_PATH


@pytest.fixture(autouse=True)
def _banco_do_modulo(request):
    """Cada módulo de teste roda com O SEU banco, e devolve o que achou.

    🚨 ISTO CONSERTA UM DEFEITO QUE SÓ APARECEU AO LIGAR A SUÍTE INTEIRA, em
    18/11. `teste_ponte_rotas_http.py` faz `storage.DB_PATH = DB` **no topo do
    módulo**, e o pytest importa todos os módulos na coleta, antes de rodar
    qualquer teste. Resultado: o último a atribuir ganhava o processo inteiro, e
    testes que esperavam o banco real morriam com

        sqlite3.OperationalError: no such table: painel_vinculos_itens

    🚨 E eram FALSOS: `teste_aquisicao_retirada.py` passa 4/4 rodando sozinho.
    Quatro testes reprovando por contaminação entre arquivos -- o tipo de
    vermelho que faz alguém desligar a suíte em vez de ler.

    ⚠️ A convenção é o módulo declarar `DB`. Quem não declara roda contra o
    banco de produção, que é o que esses arquivos sempre fizeram -- isto não
    muda o alvo de ninguém, só impede que um módulo decida pelos outros.
    """
    _storage.DB_PATH = getattr(request.module, "DB", None) or BANCO_DE_PRODUCAO
    yield
    # 🚨 VOLTA PARA PRODUÇÃO, NÃO PARA "O QUE ESTAVA ANTES". Guardar e devolver
    # o valor anterior parece mais cuidadoso e é pior: o valor anterior pode
    # ser justamente o banco temporário que outro módulo vazou na coleta, e aí
    # o estrago continua circulando. Medido em 18/11: com `antes`, a limpeza de
    # fim de módulo do `teste_operacoes_f5b` caía em
    # `sqlite3.OperationalError: no such table` -- ela rodava contra o banco
    # vazado e deixava o resíduo na produção.
    _storage.DB_PATH = BANCO_DE_PRODUCAO


@pytest.fixture
def anyio_backend():
    """O backend único. ⚠️ Sem isto o anyio roda cada teste async DUAS vezes
    (asyncio e trio), e o trio não está instalado."""
    return "asyncio"


def pytest_collection_modifyitems(items):
    """Põe o marcador do anyio em toda função async coletada."""
    for item in items:
        if inspect.iscoroutinefunction(getattr(item, "obj", None)):
            item.add_marker(pytest.mark.anyio)
