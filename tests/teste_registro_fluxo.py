"""O registro da aba acompanha o fluxo. 2026-08-21.

🚨 POR QUE ESTE ARQUIVO EXISTE. `guardar_cliente` foi escrito na F3 e NUNCA foi
chamado por ninguém: `grep` no projeto inteiro devolvia só a definição. O efeito
era invisível na tela e total no registro -- toda rodada ficava com
`cliente_harmonit_id` nulo, `cliente_weso_id` nulo e `etapa = 1` para sempre.

Os dois lotes reais de 21/08 provam: gravados em `etapa 1`, cliente nulo, zero
passos -- e o operador tinha chegado à etapa 4 e pedido a prévia. O Histórico de
Operações (`HST_4.1`) lê essas colunas, então ele mostrava toda rodada como se
tivesse morrido no começo.

⚠️ AQUI SE MEDE USO, NÃO PALAVRA. Três travas escritas em 19/08 reprovaram
código correto porque procuravam um nome que aparecia num comentário. As duas
verificações que não conseguem chamar a rota (a de placa e a de OS exigiriam
dublê dos dois sistemas externos) usam a ÁRVORE SINTÁTICA e procuram uma
CHAMADA de função dentro do corpo certo -- `reg.marcar_etapa(...)` num
comentário não conta.

Roda na VPS: venv/bin/python tests/teste_registro_fluxo.py
🚨 NÃO FAZ REDE. Usa o SQLite do painel com um lote de teste, e limpa no fim.
"""
import ast
import asyncio
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso import storage                                    # noqa: E402
from fpsl_weso.painel import operacoes_registro as reg           # noqa: E402
from fpsl_weso.painel.routers import operacoes_router as rt      # noqa: E402

ROUTER_PY = RAIZ / "fpsl_weso" / "painel" / "routers" / "operacoes_router.py"

ok, falhas = 0, []
criados = []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


def limpar():
    reg._criar()
    with storage._connect() as c:
        for lote in criados:
            c.execute("DELETE FROM operacoes_passo WHERE lote = ?", (lote,))
            c.execute("DELETE FROM operacoes_lote  WHERE lote = ?", (lote,))


def chamadas_em(nome_da_funcao):
    """Nomes de função chamados dentro de `nome_da_funcao`, pela AST.

    Mede USO. `reg.marcar_etapa` escrito num comentário ou numa docstring não
    aparece aqui -- e é essa a diferença entre trava e adivinhação.
    """
    arvore = ast.parse(ROUTER_PY.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and no.name == nome_da_funcao:
            achados = set()
            for filho in ast.walk(no):
                if isinstance(filho, ast.Call):
                    achados.add(ast.unparse(filho.func))
            return achados
    return set()


async def principal():
    print("== a rota /lote grava o cliente que a etapa 2 resolveu ==")
    corpo = rt.LoteInput(perfil="aditivo", termo="8800",
                         documento="32020313000106",
                         cliente_harmonit_id=998063, cliente_weso_id=13624)
    saida = await rt.abrir_lote(corpo, usuario={"login": "teste-registro"})
    lote = saida["lote"]
    criados.append(lote)

    cab = await reg.ler_lote(lote)
    checar("o lote nasce com o id do Harmonit",
           cab["cliente_harmonit_id"] == 998063, str(cab))
    checar("o lote nasce com o id da WESO",
           cab["cliente_weso_id"] == 13624, str(cab))
    checar("🚨 a etapa sai de 1 -- era o defeito de 21/08",
           cab["etapa"] == 2, f"etapa = {cab['etapa']}")

    print()
    print("== marcar_etapa anda para a frente e NUNCA para trás ==")
    await reg.marcar_etapa(lote, 3)
    checar("a etapa 3 é anotada", (await reg.ler_lote(lote))["etapa"] == 3)
    await reg.marcar_etapa(lote, 2)
    checar("voltar para conferir a etapa 2 não desfaz a 3",
           (await reg.ler_lote(lote))["etapa"] == 3,
           "o registro é do que ACONTECEU, não de onde a tela está aberta")

    print()
    print("== encerrar fecha a rodada ==")
    cab = await reg.ler_lote(lote)
    checar("antes de gerar OS, a rodada está aberta", cab["encerrado_em"] is None)
    await reg.encerrar(lote)
    cab = await reg.ler_lote(lote)
    checar("encerrado_em passa a existir", bool(cab["encerrado_em"]))
    checar("e a etapa vai para 4", cab["etapa"] == 4)
    marca = cab["encerrado_em"]
    await reg.encerrar(lote)
    checar("encerrar de novo não reescreve a hora do fim",
           (await reg.ler_lote(lote))["encerrado_em"] == marca)

    print()
    print("== lote sem cliente informado continua funcionando ==")
    # A rota tem de aceitar o caso em que a etapa 2 não resolveu ninguém --
    # senão perfil sem termo, que ainda não tem cliente, quebraria ao abrir.
    corpo2 = rt.LoteInput(perfil="manutencao_troca")
    lote2 = (await rt.abrir_lote(corpo2, usuario={"login": "teste-registro"}))["lote"]
    criados.append(lote2)
    cab2 = await reg.ler_lote(lote2)
    checar("abre sem cliente, sem estourar", cab2 is not None)
    checar("e os ids ficam nulos, não zero",
           cab2["cliente_harmonit_id"] is None and cab2["cliente_weso_id"] is None)

    print()
    print("== as outras duas pontas do fluxo, medidas na árvore sintática ==")
    na_placa = chamadas_em("criar_uma_placa")
    checar("gravar placa marca a etapa 3",
           "reg.marcar_etapa" in na_placa,
           f"chamadas encontradas: {sorted(na_placa)}")
    na_os = chamadas_em("gerar_os")
    checar("gerar as OS encerra o lote",
           "reg.encerrar" in na_os,
           f"chamadas encontradas: {sorted(na_os)}")
    na_lote = chamadas_em("abrir_lote")
    checar("abrir o lote guarda o cliente",
           "reg.guardar_cliente" in na_lote,
           f"chamadas encontradas: {sorted(na_lote)}")


try:
    asyncio.run(principal())
finally:
    limpar()

print()
print(f"== {ok} verificações OK, {len(falhas)} falha(s) ==")
if falhas:
    for f in falhas:
        print(f"   - {f}")
    sys.exit(1)
