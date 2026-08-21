"""O acabamento visual da aba Operações. 2026-08-21.

🚨 NASCEU COMO AUDITORIA E VIROU TESTE. Ele mandou "faça conforme metodologia,
avançando e depois audite" -- e a auditoria achou duas coisas que eu não tinha
visto: o cabeçalho de seção não era alcançável por `Tab`, e quatro espaços
fora da escala. Auditoria que acha e some deixa o achado voltar; por isso ela
fica aqui, rodando com a suíte.

⚠️ E ELA MESMA TEVE UM FALSO POSITIVO, corrigido: o filtro que separava a
sidebar olhava linha a linha, e a regra dela ocupa duas -- a continuação caía
no balde da aba e acusava um `20px` que não é dela. **Achado falso é pior que
achado nenhum: ensina a ignorar a auditoria.**

⚠️ A SIDEBAR FICA DE FORA DE PROPÓSITO. Ela é o padrão visual COMPARTILHADO
pelos quatro painéis, e ele mandou polir SÓ a aba Operações. Auditoria que
cobra o que a decisão dele proíbe é trava que reprova o certo.

Roda na VPS: venv/bin/python tests/teste_acabamento.py
🚨 NÃO FAZ REDE. Lê o CSS e o HTML das duas telas.
"""
import io
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "frontend"
css = io.open(RAIZ / "operacoes.css", encoding="utf-8").read()
html = io.open(RAIZ / "operacoes.html", encoding="utf-8").read()
velha_css = io.open(RAIZ / "gerar_os.html", encoding="utf-8").read()

ok, achados = 0, []


def checar(nome, cond, detalhe=""):
    global ok
    if cond:
        ok += 1
        print(f"  OK   {nome}")
    else:
        achados.append(nome)
        print(f"  FALHA {nome}" + (f"  -- {detalhe}" if detalhe else ""))


print("== 1. o foco visivel alcanca tudo que se navega? ==")
# Botao, campo, select e o cabecalho de secao (que e clicavel).
checar("existe :focus-visible", ":focus-visible" in css)
# 🚨 O CABECALHO DE SECAO E CLICAVEL E NAO E BOTAO: um `div` com onclick nao
# entra na ordem de tabulacao. Quem navega por teclado nao alcanca a secao.
checar("o cabeçalho de seção é alcançável por Tab",
       html.count('class="secao-cab"') == html.count('tabindex="0"'),
       "<header onclick> sem tabindex: o teclado nao chega nele")
# 🚨 QUEM RECEBE FOCO PRECISA RESPONDER A ENTER E ESPACO. E o contrato que um
# elemento clicavel assume quando nao e <button> -- dar tabindex e nao tratar a
# tecla poe o foco num lugar que nao faz nada, que e pior que nao ter foco.
checar("e responde a Enter e Espaco",
       "teclaNaSecao" in html and "'Enter'" in html)
checar("com role de botao, para o leitor de tela",
       html.count('role="button"') == html.count('class="secao-cab"'))

print()
print("== 2. o que muda geometria vem por CSS, nunca por JS? ==")
# Licao de 18/08: regra que chega depois nao corrige o desenho, REMONTA.
js = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
js_limpo = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
proibidos = [p for p in ("padding", "margin", "width:", "height:", "position:")
             if f".style.{p}" in js_limpo or f"style.{p}" in js_limpo]
checar("o JS não mexe em geometria", not proibidos, str(proibidos))
checar("nenhum <style> injetado por JS", "<style" not in js_limpo)

print()
print("== 3. o acabamento cobre os tres pesos de botao? ==")
for classe in ("btn-primary", "btn-ghost", "btn-perigo"):
    checar(f"{classe} tem hover", f".{classe}:hover" in css)
checar("o clique afunda (:active)", ":active" in css)
checar("e o afundar NÃO vale para desabilitado",
       ":active:not(:disabled)" in css)

print()
print("== 4. campo somente-leitura nao finge ser editavel ==")
# O cliente e o servico se ESCOLHEM -- se parecerem editaveis, alguem digita.
checar("readonly tem aparência própria", "input[readonly]" in css)
n_readonly = len(re.findall(r"readonly", html))
checar(f"e há {n_readonly} campos readonly na tela", n_readonly >= 2)

print()
print("== 5. a escala de espaco e usada, ou os avulsos voltaram? ==")
# ⚠️ A SIDEBAR FICA DE FORA, e nao e descuido: ela e o padrao visual
# COMPARTILHADO pelos quatro paineis. Ele mandou polir SO a aba Operacoes --
# mexer la mudaria MoviZap, MoviServer e Painel rapido de tabela. Auditoria que
# cobra o que a decisao dele proibe ensina a ignorar a auditoria.
def separar_sidebar(fonte):
    """Divide o CSS em (aba, sidebar), por BLOCO e não por linha.

    🚨 FILTRO LINHA A LINHA ERRA NA CONTINUAÇÃO. A regra `.sidebar { ... }`
    ocupa duas linhas, e a segunda não tem a palavra `.sidebar` -- então ela
    caía no balde da aba e a auditoria acusava um `20px` que é da sidebar.
    Achado falso é pior que achado nenhum: ensina a ignorar a auditoria.
    """
    aba, side, dentro = [], [], False
    for l in fonte.split(chr(10)):
        if not dentro and ".sidebar" in l:
            dentro = True
        (side if dentro else aba).append(l)
        if dentro and "}" in l:
            dentro = False
    return chr(10).join(aba), chr(10).join(side)


so_da_aba, so_sidebar_bloco = separar_sidebar(css)
avulsos = re.findall(r"(?:margin|padding|gap)[^;:]*:\s*([0-9]+)px", so_da_aba)
fora = sorted({int(v) for v in avulsos} - {0, 1, 2, 4, 6, 8, 10, 12, 16, 24, 32})
checar("nenhum espaço da ABA fora da escala", not fora, f"px avulsos: {fora}")
n_sidebar = len(re.findall(r"(?:margin|padding|gap)[^;:]*:\s*[0-9]+px",
                           so_sidebar_bloco))
print(f"       (a sidebar tem {n_sidebar} espaços próprios — compartilhada, fora do escopo)")

print()
print("== 6. comparacao com a tela velha ==")
# A regra de 17/08: tela nova se compara com a que ja existe.
checar("a nova tem foco visível e a velha não",
       ":focus-visible" in css and ":focus-visible" not in velha_css)
checar("a nova tem transição e a velha não",
       "transition" in css and velha_css.count("transition") == 0)

print()
print("== 7. o que eu acabei de mexer quebrou algo do que ja funcionava? ==")
checar("as seções continuam com regra própria", ".secao-cab" in css)
checar("a moldura da prévia continua", ".previa-moldura" in css)
checar("os quatro badges continuam",
       all(f".badge-{c}" in css for c in ("blue", "green", "red", "ambar")))
checar("a barra de retomada continua", ".retomar" in css)

print()
print(f"== {ok} verificações OK, {len(achados)} falha(s) ==")
if achados:
    for a in achados:
        print("   -", a)
    sys.exit(1)
