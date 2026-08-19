"""O contrato entre `/painel/api/me` e o `sidebar.js` (2026-08-18).

🚨 POR QUE ESTE TESTE EXISTE. Em 17/08 `telas.do_usuario` passou a devolver
`codigo`/`titulo` no lugar de `id`/`nome`. O `sidebar.js` -- que TODA pagina do
painel carrega -- compara `a.id` com a permissao que a pagina declara e escreve
`a.nome` no link. Com `a.id` valendo `undefined`, nenhuma pagina se reconheceu,
todas se julgaram fora do perfil e redirecionaram para a primeira aba, que
redirecionava para si mesma: o painel piscava e ninguem entrava. As 677
verificacoes daquele dia passaram todas -- nenhuma olhava o consumidor.

A licao registrada era "tela nova se compara com a tela que ja existe". Esta e
a versao executavel dela: o teste LE O sidebar.js, extrai os campos que ele
consome e exige que `do_usuario` devolva cada um. Se alguem trocar o nome de um
campo dos dois lados, o teste acompanha sozinho; se trocar so de um lado,
reprova.

Roda na VPS: venv/bin/python tests/teste_contrato_sidebar.py
Nao toca em banco, nao faz rede.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso.painel import telas  # noqa: E402
from fpsl_weso.painel import abas as abas_painel  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SIDEBAR = RAIZ / "frontend" / "sidebar.js"
ok_total, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok_total
    if condicao:
        ok_total += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def campos_que_o_sidebar_usa() -> set:
    """Todo `a.<campo>` dentro do sidebar.js -- e o que ele espera receber."""
    fonte = SIDEBAR.read_text(encoding="utf-8")
    # so o corpo executavel: comentario cita campo sem depender dele
    sem_bloco = re.sub(r"/\*.*?\*/", "", fonte, flags=re.S)
    sem_linha = re.sub(r"//[^\n]*", "", sem_bloco)
    return set(re.findall(r"\ba\.([A-Za-z_][A-Za-z0-9_]*)", sem_linha))


print("\n[1] o sidebar.js e legivel e usa campos")
checar("sidebar.js existe", SIDEBAR.exists(), str(SIDEBAR))
usados = campos_que_o_sidebar_usa()
checar("extraiu ao menos 3 campos", len(usados) >= 3, str(sorted(usados)))
print(f"       campos consumidos: {sorted(usados)}")

print("\n[2] do_usuario entrega TODOS eles, para o owner")
owner = abas_painel.do_usuario({"owner": True, "abas": []})
checar("owner tem ao menos uma aba", len(owner) > 0)
for campo in sorted(usados):
    faltando = [a.get("codigo", "?") for a in owner if campo not in a]
    checar(f"toda aba tem `{campo}`", not faltando, f"faltou em {faltando}")
    vazios = [a.get("codigo", "?") for a in owner if a.get(campo) in (None, "")]
    checar(f"`{campo}` nunca vem vazio", not vazios, f"vazio em {vazios}")

print("\n[3] do_usuario entrega TODOS eles, para um operador comum")
operador = abas_painel.do_usuario({"owner": False, "abas": ["gerar_os", "vinculos"]})
checar("operador ve exatamente as 2 abas dele", len(operador) == 2,
       str([a.get("codigo") for a in operador]))
for campo in sorted(usados):
    checar(f"operador: toda aba tem `{campo}`",
           all(campo in a and a[campo] not in (None, "") for a in operador))

print("\n[4] o `id` e a PERMISSAO -- e o vocabulario que as paginas falam")
# 🚨 O MENU TEM DE SER SUBCONJUNTO DO ACESSO, sempre. Item no menu que a pessoa
# nao pode abrir e link que leva a 403; e o inverso (acesso sem menu) e
# legitimo -- e o caso das telas `no_menu`.
_menu = {a.get("id") for a in owner}
_acesso = set(abas_painel.permissoes_do_usuario({"owner": True, "abas": []}))
checar("o menu do owner cabe dentro do que ele pode acessar",
       _menu <= _acesso, f"sobrando no menu: {sorted(_menu - _acesso)}")
declarados = {}
for html in sorted((RAIZ / "frontend").glob("*.html")):
    m = re.search(r"montarSidebar\(\s*'([^']+)'", html.read_text(encoding="utf-8"))
    if m:
        declarados[html.name] = m.group(1)
checar("achou as paginas que montam sidebar", len(declarados) >= 8, str(len(declarados)))

# 🚨 A PERGUNTA E DE ACESSO, NAO DE MENU. Ate 19/08 as duas coincidiam, porque
# toda tela fora do menu dividia permissao com uma do menu (o Historico de
# Placas com o Cadastro) ou nao tinha permissao (as de demandas). A `OPR_1.1`
# quebrou a coincidencia: permissao propria e fora do menu.
#
# Medir pela lista do MENU aqui reprovaria uma pagina que funciona -- e, pior,
# esconderia o caso inverso: pagina que declara permissao que ninguem tem.
# `permissoes_do_usuario` responde exatamente "o que esta pessoa pode abrir".
vistas_do_owner = set(abas_painel.permissoes_do_usuario({"owner": True, "abas": []}))
for arquivo, declarado in sorted(declarados.items()):
    checar(f"{arquivo} declara `{declarado}`, que o owner recebe",
           declarado in vistas_do_owner,
           f"nao veio em /me: {sorted(vistas_do_owner)}")
    checar(f"{arquivo}: `{declarado}` e permissao conhecida",
           declarado in telas.PERMISSOES_VALIDAS)

print("\n[5] a pagina de destino do redirecionamento nao pode ser um beco")
primeira = owner[0] if owner else None
checar("existe primeira aba", primeira is not None)
if primeira:
    print(f"       primeira aba do owner: {primeira['rota']}")
    alvos = {d for d in declarados.values()}
    checar("a primeira aba se reconhece (senao e loop)",
           primeira.get("id") in alvos,
           f"id={primeira.get('id')!r} nao e declarado por nenhuma pagina")

print("\n[6] o sidebar.js nao redireciona para a propria URL")
fonte = SIDEBAR.read_text(encoding="utf-8")
checar("compara destino com o caminho atual antes de navegar",
       "!==" in fonte and "caminho" in fonte,
       "sem essa guarda, dado errado vira loop infinito")

print(f"\n{'='*46}\n{ok_total} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
