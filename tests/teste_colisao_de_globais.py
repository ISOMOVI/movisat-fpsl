"""Nenhuma página redefine um nome que o `sidebar.js` declara. 2026-08-24.

🚨 POR QUE ISTO EXISTE. Ele inseriu uma opção no perfil da Erika e o MENU
LATERAL SUMIU. Não era o perfil: a tela de Usuários declarava a sua própria
`desenharAbas`, e o `sidebar.js` declara uma com o MESMO NOME. Os dois scripts
vivem no mesmo escopo global, e a declaração da página -- avaliada depois --
apagava a do arquivo compartilhado.

A partir daí `montarSidebar('usuarios')` chamava a função ERRADA: a da página,
que escreve na caixa de checkboxes do modal e não no `sidebarNav`, e que ainda
lê `ABAS` -- um `let` declarado ABAIXO da chamada, portanto em zona morta
temporal. `ReferenceError`, promessa rejeitada, e o `/painel/api/me` nunca
chegava a ser pedido.

🚨 E O SERVIDOR NÃO TINHA COMO SABER. No journal a página sai `200` e, sozinha
entre todas, SEM o `/painel/api/me` logo em seguida. Foi assim que se achou.

A colisão vale desde 19/08, quando o `sidebar.js` ganhou a `desenharAbas` do
cache (`52f47dd`); a da tela de Usuários existe desde 04/08. Cinco dias com a
sidebar de uma tela morta e placar verde o tempo todo -- nenhum teste olhava
a convivência entre os dois arquivos.

⚠️ A LISTA DE NOMES VEM DO `sidebar.js`, nunca escrita aqui. Escrever à mão
criaria a segunda verdade que este teste existe para impedir.

Roda na VPS: venv/bin/python tests/teste_colisao_de_globais.py
🚨 NÃO FAZ REDE. Lê os arquivos do `frontend/`.
"""
import io
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "frontend"

ok, achados = 0, []


def checar(nome, cond, detalhe=""):
    global ok
    if cond:
        ok += 1
        print(f"  OK   {nome}")
    else:
        achados.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


def sem_comentario(fonte: str) -> str:
    """🚨 COMENTÁRIO NÃO É CÓDIGO, e medir palavra em comentário é o `M7`.

    Estes arquivos EXPLICAM a colisão em comentário -- inclusive citando
    `function logout`. Varrer sem tirar os comentários acusaria justamente o
    texto que documenta a correção.
    """
    fonte = re.sub(r"/\*.*?\*/", " ", fonte, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", fonte, flags=re.M)


def globais(fonte: str) -> set:
    """Declarações de TOPO -- coluna zero. O que está indentado vive dentro de
    outra função e não disputa o escopo global."""
    fonte = sem_comentario(fonte)
    nomes = set(re.findall(r"^function\s+([A-Za-z_$][\w$]*)\s*\(", fonte, re.M))
    nomes |= set(re.findall(r"^(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=",
                            fonte, re.M))
    return nomes


sidebar = io.open(RAIZ / "sidebar.js", encoding="utf-8").read()
DO_SIDEBAR = globais(sidebar)

print("== o que o sidebar.js poe no escopo global ==")
checar("ele declara nomes de topo", bool(DO_SIDEBAR), "nao achei nenhum")
print(f"       {sorted(DO_SIDEBAR)}")
# Prende os dois que já custaram caro, para o dia em que alguém "simplificar"
# o extrator acima e ele passar a devolver conjunto vazio -- teste que não mede
# nada passa sempre.
checar("entre eles, `desenharAbas` e `logout`",
       {"desenharAbas", "logout"} <= DO_SIDEBAR, str(sorted(DO_SIDEBAR)))

print()
print("== nenhuma pagina redefine um deles ==")
paginas = sorted(p for p in RAIZ.glob("*.html"))
com_sidebar = []
for p in paginas:
    fonte = io.open(p, encoding="utf-8").read()
    if "sidebar.js" not in fonte:
        continue
    com_sidebar.append(p.name)
    # Só o que a PÁGINA escreve: os <script src> são arquivos à parte.
    inline = "\n".join(re.findall(r"<script>(.*?)</script>", fonte, re.S))
    colisao = globais(inline) & DO_SIDEBAR
    checar(f"{p.name:32} não redefine nada do sidebar.js",
           not colisao,
           f"redefine {sorted(colisao)} -- a declaracao da pagina apaga a de la, "
           f"e `montarSidebar` passa a chamar a funcao errada")

checar("e há páginas usando o sidebar.js para conferir",
       len(com_sidebar) >= 5, str(com_sidebar))

print()
print(f"== {ok} verificações OK, {len(achados)} falha(s) ==")
if achados:
    for a in achados:
        print("   -", a)
    sys.exit(1)
