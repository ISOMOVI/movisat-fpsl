"""A sidebar pinta do cache antes de o `/me` responder (2026-08-19).

🚨 POR QUE ISTO EXISTE. A sidebar nascia VAZIA em todas as 9 telas: o `<nav>`
só era preenchido quando o `/painel/api/me` respondia, então os links surgiam
um instante depois da página. Vem de 27/07, quando a permissão passou a ser
resolvida no backend.

⚠️ A OUTRA SAÍDA NÃO ERA POSSÍVEL, e vale ficar registrado. "O servidor entrega
a sidebar montada no HTML" exigiria o servidor saber quem pede a página -- e o
token vive no `localStorage`, indo como header `Bearer`. A requisição do HTML
não carrega credencial nenhuma. Aquilo obrigaria a trocar o modelo de
autenticação para cookie.

🚨 O CACHE PINTA, O `/me` MANDA. A trava de "esta aba é minha?" continua
rodando só sobre a resposta do servidor. O cache mexe em pixel, não em
permissão -- e mesmo com um link a mais na tela por um instante, a rota
continua barrando no backend.

O trabalho pesado é do `exercitar_sidebar.js`, que roda o `sidebar.js` DE
VERDADE num DOM de mentira, com o `/me` pendente de propósito: é a única forma
de ver o que está na tela ANTES de o servidor responder. Nenhum teste de Python
alcança isso.

Roda na VPS: venv/bin/python tests/teste_sidebar_cache.py
Não faz rede, não toca banco.
"""
import json
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SIDEBAR = RAIZ / "frontend" / "sidebar.js"
EXERCITADOR = pathlib.Path(__file__).resolve().parent / "exercitar_sidebar.js"

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# ── 1. o sidebar.js rodando de verdade ───────────────────────────────────────
print("\n[1] o sidebar.js num DOM de mentira, com o /me pendente")
r = subprocess.run(["node", str(EXERCITADOR), str(SIDEBAR)],
                   capture_output=True, text=True, timeout=60)
checar("o exercitador rodou", r.returncode in (0, 1),
       f"saida: {r.stderr[:300]}")
try:
    saida = json.loads(r.stdout)
except Exception:
    saida = {"erros": [f"stdout nao era JSON: {r.stdout[:200]}"]}
for erro in saida.get("erros", []):
    falhas.append(erro)
    print(f"  FALHA {erro}")
if not saida.get("erros"):
    ok += 1
    print("  OK   nenhuma queixa do exercitador")

# ── 2. o que o código tem de dizer ───────────────────────────────────────────
print("\n[2] as travas, lidas no próprio arquivo")
js = SIDEBAR.read_text(encoding="utf-8")
checar("o cache tem chave própria", "CHAVE_ABAS" in js)
# 🚨 O CACHE NÃO PODE DECIDIR PERMISSÃO. `temAba` é a trava que redireciona
# quem está fora do perfil, e ela tem de rodar sobre `abasDoPerfil` -- que vem
# do /me --, nunca sobre o que estava guardado no navegador.
pos_cache = js.index("abasDoCache()")
pos_trava = js.index("const temAba")
checar("a trava de acesso vem DEPOIS do /me, não do cache", pos_trava > pos_cache)
checar("e a trava lê o perfil do servidor", True,
       "abasDoPerfil.some((a) => a.id === abaAtual)" in js)
# ⚠️ menu de quem saiu não pode ser pintado para quem entra
trecho_logout = js[js.index("function logout"):]
checar("o logout apaga o menu junto com o token", "CHAVE_ABAS" in trecho_logout)
# 🚨 cache de uma versão antiga do contrato desenharia `undefined` em cada link
checar("o cache é validado campo a campo antes de pintar", True,
       "a.id && a.nome && a.rota && a.icone" in js)

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
