"""A barra de status do rodape, e a ordem do menu (2026-08-18).

Prende o que foi pedido em 18/08:
  - toda pagina do painel carrega a barra, e ANTES do sidebar.js (o
    interceptador de `fetch` precisa existir antes da primeira chamada da
    pagina, senao a barra nasce sem `req`);
  - o servidor devolve `X-Request-Id` -- sem ele o campo `req` fica vazio e a
    barra vira enfeite;
  - o token carrega `iat`, que e como a barra mede a sessao;
  - `/painel/api/me` diz o CODIGO de cada rota, inclusive das telas fora do
    menu, senao a barra nao sabe em que tela a pessoa esta;
  - `Historico de Placas` aparece no menu logo abaixo de `Historico de OS`,
    com o codigo CAD_1.2 intacto.

Roda na VPS: venv/bin/python tests/teste_barra_status.py
"""
import asyncio
import glob
import os
import pathlib
import sys

import httpx
from jose import jwt   # o painel usa python-jose, nao pyjwt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso.painel import telas  # noqa: E402
from fpsl_weso.painel import abas as abas_painel  # noqa: E402
from fpsl_weso.painel.auth import criar_token  # noqa: E402
from fpsl_weso import storage  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8004"
ok_total, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok_total
    if condicao:
        ok_total += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


async def main():
    print("\n[1] o arquivo da barra existe e nao escreve HTML cru")
    barra = RAIZ / "frontend" / "barra_status.js"
    checar("barra_status.js existe", barra.exists())
    fonte = barra.read_text(encoding="utf-8")
    checar("intercepta fetch", "window.fetch =" in fonte)
    checar("le o X-Request-Id", "X-Request-Id" in fonte)
    checar("escapa o que escreve", "function esc(" in fonte)
    # login e titulo vem do servidor: tudo que entra em innerHTML passa por esc
    cru = [ln.strip() for ln in fonte.splitlines()
           if "estado." in ln and "+ estado." in ln and "esc(" not in ln]
    checar("nenhum `estado.x` vai cru para o HTML", not cru, str(cru[:2]))

    print("\n[2] toda pagina do painel carrega a barra, e antes do sidebar")
    paginas = 0
    for arq in sorted(glob.glob(str(RAIZ / "frontend" / "*.html"))):
        html = pathlib.Path(arq).read_text(encoding="utf-8")
        if "sidebar.js" not in html:
            continue                    # login, demandas e planilha nao tem menu
        paginas += 1
        nome = os.path.basename(arq)
        tem = "barra_status.js" in html
        checar(f"{nome} carrega a barra", tem)
        if tem:
            checar(f"{nome}: barra ANTES do sidebar",
                   html.index("barra_status.js") < html.index("sidebar.js"))
    checar("achou as 9 paginas do painel", paginas == 9, f"achou {paginas}")

    print("\n[3] o servidor devolve o req id")
    u = await storage.buscar_usuario_painel("admin")
    tok = criar_token(u["login"])
    h = {"Authorization": "Bearer " + tok}
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.get("/painel/api/me", headers=h)
        me = r.json()
        rid = r.headers.get("X-Request-Id", "")
        checar("me responde 200", r.status_code == 200)
        checar("X-Request-Id vem preenchido", len(rid) >= 4, repr(rid))
        r2 = await c.get("/painel/api/me", headers=h)
        checar("cada requisicao tem id proprio",
               r2.headers.get("X-Request-Id") != rid)
        r3 = await c.get("/painel/nao-existe-mesmo")
        checar("ate o 404 tem id", len(r3.headers.get("X-Request-Id", "")) >= 4)

    print("\n[4] o token diz quando a sessao comecou")
    corpo = jwt.get_unverified_claims(tok)
    checar("token tem `iat`", "iat" in corpo, str(sorted(corpo)))
    checar("`iat` e anterior ao `exp`", corpo.get("iat", 0) < corpo.get("exp", 0))

    print("\n[5] /me diz o codigo de cada rota")
    codigos = me.get("codigos") or {}
    checar("veio o mapa de codigos", bool(codigos), str(list(codigos)[:3]))
    for t in telas.ativas():
        if t["permissao"] is None:
            # telas de demandas: publicas por token, fora do painel, sem barra
            checar(f"{t['codigo']} FICA FORA do mapa", t["rota"] not in codigos)
            continue
        checar(f"{t['codigo']} esta no mapa", t["rota"] in codigos)
    fora = "/painel/cadastro-placas/historico"
    checar("tela FORA do menu tambem esta no mapa (a barra precisa dela)",
           fora in codigos, "sem isso a barra mostra travessao no historico")
    if fora in codigos:
        checar("e com o codigo certo", codigos[fora]["codigo"] == "CAD_1.2",
               str(codigos.get(fora)))

    print("\n[6] Historico de Placas: no menu, abaixo de Historico de OS")
    menu = abas_painel.do_usuario({"owner": True, "abas": []})
    rotulos = [a["nome"] for a in menu]
    checar("aparece no menu", "Histórico de Placas" in rotulos, str(rotulos))
    if "Histórico de Placas" in rotulos and "Histórico de OS" in rotulos:
        checar("logo ABAIXO de Historico de OS",
               rotulos.index("Histórico de Placas") == rotulos.index("Histórico de OS") + 1,
               str(rotulos))
    cad12 = [t for t in telas.TELAS if t["codigo"] == "CAD_1.2"]
    checar("CAD_1.2 continua existindo com o codigo intacto", len(cad12) == 1)
    if cad12:
        checar("e deixou de ser fora-do-menu", not cad12[0].get("no_menu"))
        checar("permissao intacta: nao exigiu migrar conta nenhuma",
               cad12[0]["permissao"] == "cadastro_placas")
    checar("quem so tem cadastro_placas ve as duas telas",
           len(abas_painel.do_usuario({"owner": False, "abas": ["cadastro_placas"]})) == 2)

    print("\n[7] a barra desenha de verdade, num DOM de mentira")
    # 🚨 O QUE FALTOU EM 17/08. As 677 verificacoes eram todas de backend; nada
    # exercitava o que o navegador executa. Aqui o proprio barra_status.js roda
    # e o HTML que ele produz e conferido.
    exercicio = await asyncio.create_subprocess_exec(
        "node", str(RAIZ / "tests" / "exercitar_barra.js"),
        str(RAIZ / "frontend" / "barra_status.js"),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    saida, _ = await exercicio.communicate()
    checar("a barra roda sem estourar e desenha o esperado",
           exercicio.returncode == 0,
           saida.decode("utf-8", "replace").strip()[:400])

    print("\n[8] a barra nao cobre o botao Sair")
    css = (RAIZ / "frontend" / "barra_status.js").read_text(encoding="utf-8")
    checar("devolve altura para a sidebar",
           "calc(100vh - 30px)" in css and ".sidebar {" in css,
           "sem isso a barra fixa fica por cima do botao Sair")
    uma = (RAIZ / "frontend" / "os_historico.html").read_text(encoding="utf-8")
    checar("a pagina realmente usa sidebar de 100vh (a razao do ajuste)",
           "height:100vh" in uma.replace(" ", ""))

    print(f"\n{'='*46}\n{ok_total} passaram, {len(falhas)} falharam")
    for f in falhas:
        print("  -", f)
    sys.exit(1 if falhas else 0)


asyncio.run(main())
