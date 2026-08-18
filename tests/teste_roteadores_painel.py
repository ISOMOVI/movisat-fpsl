"""Contrato de acesso dos roteadores do painel — os 8 que faltavam.

🚨 POR QUE ESTE ARQUIVO EXISTE. Até 2026-08-14 os roteadores web do painel
tinham ZERO teste. A trava de acesso é declarativa (`requer_aba(...)` no
decorador), e trava declarativa é fácil de esquecer numa rota nova: ninguém
percebe, porque a rota simplesmente funciona — para todo mundo.

O que este teste garante, rota por rota:
  1. sem token          -> 401
  2. token sem a aba    -> 403
  3. token do owner     -> nem 401 nem 403

⚠️ NÃO EXERCITA ROTA DE ESCRITA. `clientes/criar` grava na WESO; `os-scan/varrer`
varre o Harmonit inteiro. Dessas só se testa a tranca — abrir a porta para ver
se abre estragaria dado real. As de leitura são chamadas de verdade e têm o
formato conferido.

(`placas/criar` saiu em 14/08 com a tela de placas; `oficina/resync` em 17/08
com o fluxo de oficina.)

Roda na VPS: venv/bin/python tests/teste_roteadores_painel.py
Cria um usuário de teste com abas restritas e o apaga no fim.
"""
import asyncio
import pathlib
import sqlite3
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel.abas import ABAS  # noqa: E402
from fpsl_weso.painel.auth import criar_token  # noqa: E402

BASE = "http://127.0.0.1:8004"
LOGIN_TESTE = "zz_teste_roteadores"
SENHA = "senha-de-teste-123"
ok, falhas = 0, []


def limpar_usuario():
    with sqlite3.connect(storage.DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM painel_usuarios WHERE login = ?", (LOGIN_TESTE,))


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


# (método, rota, aba exigida, corpo, escreve?)
# 🚨 `escreve=True` significa: NUNCA chamar autorizado. Só a tranca.
ROTAS = [
    ("GET",  "/painel/api/perfis",              "gerar_os",           None, False),
    ("GET",  "/painel/api/prioridades",         "gerar_os",           None, False),
    ("GET",  "/painel/api/problemas",           "gerar_os",           None, False),
    ("GET",  "/painel/api/vinculos",            "vinculos",           None, False),
    ("GET",  "/painel/api/produtos/buscar?q=ST310", "vinculos",       None, False),
    ("GET",  "/painel/api/servicos/buscar?q=MANUT",  "gerar_os",      None, False),
    ("GET",  "/painel/api/clientes/buscar?q=VELASCO", "gerar_os",     None, False),
    ("POST", "/painel/api/clientes/previa",     "gerar_os",           {"cnpj": "00000000000000"}, True),
    ("POST", "/painel/api/clientes/criar",      "gerar_os",           {}, True),
    ("GET",  "/painel/api/harmonit/resumo",     "harmonit_historico", None, False),
    ("GET",  "/painel/api/harmonit/chamadas",   "harmonit_historico", None, False),
    # Cadastro de Placas (17/08). ⚠️ `previa` NÃO escreve -- entra no laço [3]
    # como leitura, e sem corpo válido ela para no 422 antes de tocar a WESO,
    # que é o que se quer aqui: o assunto desta tabela é a TRANCA, não o fluxo.
    # O fluxo tem teste próprio em `teste_cadastro_placas.py`.
    ("POST", "/painel/api/placas/previa",       "cadastro_placas",    None, False),
    ("POST", "/painel/api/placas/criar",        "cadastro_placas",    None, True),
    ("GET",  "/painel/api/placas/config/ativo", "config",             None, False),
    ("PUT",  "/painel/api/placas/config/ativo", "config",             {"ativo": False}, True),
    # As 4 rotas de `/painel/api/oficina/*` sairam em 17/08, junto com o fluxo
    # de sincronizacao de oficina: tabela `oficinas_processadas` com ZERO linhas
    # em toda a vida, ZERO chamadas no journal e o interruptor
    # `oficina_registro_ativo` em `false` desde 16/07. O Historico de OS
    # (`/painel/api/os-scan/*`, logo abaixo) NAO tem relacao e fica.
    ("GET",  "/painel/api/os-scan/historico",   "os_historico",       None, False),
    ("GET",  "/painel/api/os-scan/checkpoint",  "os_historico",       None, False),
    ("POST", "/painel/api/os-scan/varrer",      "os_historico",       None, True),
    ("POST", "/painel/api/os-scan/resync",      "os_historico",       None, True),
    ("PUT",  "/painel/api/os-scan/checkpoint",  "os_historico",       {"numero": 16000}, True),
    ("GET",  "/painel/api/usuarios",            "usuarios",           None, False),
    ("GET",  "/painel/api/usuarios/abas",       "usuarios",           None, False),
]


async def chamar(c, metodo, rota, corpo, headers):
    if metodo == "GET":
        return await c.get(rota, headers=headers)
    if metodo == "PUT":
        return await c.put(rota, json=corpo or {}, headers=headers)
    return await c.post(rota, json=corpo or {}, headers=headers)


async def main():
    admin = await storage.buscar_usuario_painel("admin")
    h_owner = {"Authorization": "Bearer " + criar_token(admin["login"])}

    # Usuário de teste SEM aba nenhuma: é o que prova o 403. Um usuário com
    # todas as abas provaria só que o token funciona.
    # ⚠️ Criado pela ROTA, não por SQL: assim a criação de usuário também fica
    # exercitada, e a senha passa pelo mesmo hash da produção.
    limpar_usuario()
    async with httpx.AsyncClient(base_url=BASE, timeout=20) as c0:
        r = await c0.post("/painel/api/usuarios", headers=h_owner,
                          json={"login": LOGIN_TESTE, "senha": SENHA, "abas": []})
        if r.status_code != 200:
            print(f"  nao consegui criar o usuario de teste: {r.status_code} {r.text[:120]}")
            sys.exit(1)
    magro = await storage.buscar_usuario_painel(LOGIN_TESTE)
    h_magro = {"Authorization": "Bearer " + criar_token(magro["login"])}

    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
            print("\n[1] sem token nenhum -> 401 em TODA rota protegida")
            for metodo, rota, _aba, corpo, _esc in ROTAS:
                r = await chamar(c, metodo, rota, corpo, {})
                checar(f"401 {metodo} {rota.split('?')[0]}", 401, r.status_code)

            print("\n[2] token sem a aba -> 403")
            for metodo, rota, _aba, corpo, _esc in ROTAS:
                r = await chamar(c, metodo, rota, corpo, h_magro)
                checar(f"403 {metodo} {rota.split('?')[0]}", 403, r.status_code)

            print("\n[3] token do owner passa da tranca (só rotas de leitura)")
            for metodo, rota, _aba, corpo, escreve in ROTAS:
                if escreve:
                    continue
                r = await chamar(c, metodo, rota, corpo, h_owner)
                checar(f"owner entra em {metodo} {rota.split('?')[0]}", True,
                       r.status_code not in (401, 403))

            print("\n[4] formato do que as rotas de leitura devolvem")
            r = await c.get("/painel/api/perfis", headers=h_owner)
            perfis = r.json()
            checar("perfis: 9 no total", 9, len(perfis))
            checar("perfis: manutenção marcada como sem termo", True,
                   perfis["manutencao_troca"]["sem_termo"])
            r = await c.get("/painel/api/problemas", headers=h_owner)
            checar("problemas: MANUTENÇÃO está na lista", True,
                   any(p["descricao"] == "MANUTENÇÃO"
                       for p in r.json().get("problemas", [])))
            r = await c.get("/painel/api/os-scan/checkpoint", headers=h_owner)
            checar("checkpoint devolve dict", True, isinstance(r.json(), dict))
            # o toggle `oficina/config/ativo` saiu em 17/08 com o fluxo de oficina

            print("\n[5] login")
            r = await c.post("/painel/api/login",
                             json={"login": LOGIN_TESTE, "senha": "senha_errada"})
            checar("senha errada não entra", True, r.status_code >= 400)
            checar("e não diz se o login existe", False,
                   "existe" in r.text.lower() or "não encontrado" in r.text.lower())
            r = await c.post("/painel/api/login",
                             json={"login": LOGIN_TESTE, "senha": SENHA})
            checar("senha certa entra", 200, r.status_code)
            # ⚠️ O campo chama `access_token`, não `token` -- quem escrever
            # cliente novo contra esta rota precisa saber disso.
            checar("e devolve access_token", True, bool(r.json().get("access_token")))
            # 🚨 CAIXA NÃO IMPORTA. Em 07/08 o dono ficou de fora com a senha
            # certa porque a busca era `WHERE login = ?`, sensível a maiúscula.
            r = await c.post("/painel/api/login",
                             json={"login": LOGIN_TESTE.upper(),
                                   "senha": SENHA})
            checar("login em CAIXA ALTA entra igual", 200, r.status_code)

            print("\n[6] /me reflete as abas do usuário")
            r = await c.get("/painel/api/me", headers=h_magro)
            checar("me responde 200 para usuário magro", 200, r.status_code)
            checar("usuário sem aba enxerga zero abas", 0, len(r.json().get("abas") or []))
            checar("e não é owner", False, r.json().get("owner") is True)
            r = await c.get("/painel/api/me", headers=h_owner)
            # ⚠️ NÃO SE COMPARA MAIS COM `len(ABAS)`. Desde 17/08 o menu devolve
            # TELAS (códigos) e `ABAS` são PERMISSÕES -- são unidades diferentes,
            # e uma permissão pode ter mais de uma tela. Comparar as duas passou
            # a ser comparar laranja com maçã.
            from fpsl_weso.painel import telas as _telas
            _no_menu = [t for t in _telas.ativas()
                        if not t.get("no_menu") and t["permissao"] is not None]
            checar("owner enxerga todas as telas do menu", len(_no_menu),
                   len(r.json().get("abas") or []))

            print("\n[7] toda aba concedível é exigida por alguma rota")
            # 🚨 ABA QUE NINGUÉM EXIGE É PERMISSÃO QUE NÃO PROTEGE NADA.
            #
            # ⚠️ HOUVE UMA ÓRFÃ ATÉ 14/08: a aba "placas", que aparecia no
            # catálogo e na barra lateral mas que rota nenhuma exigia -- o
            # placas_router sempre pediu "gerar_os". Quem recebia só "Placas"
            # via a aba e não conseguia usar; quem tinha "Gerar OS" criava
            # placa na WESO sem ter recebido "Placas". Foi REMOVIDA a pedido do
            # usuário: "não tem motivo para existir, nunca pedi ela". Em 14/08, com nova
            # autorização, a TELA e o `placas_router` também foram apagados --
            # por isso não há mais rota de `placas` nesta lista.
            #
            # O conjunto abaixo ficou vazio de propósito: se voltar a ter
            # alguma coisa, é porque nasceu permissão que não protege nada.
            exigidas = {aba for _m, _r, aba, _c, _e in ROTAS}
            concediveis = {a["id"] for a in ABAS if not a.get("somente_owner")}
            checar("nenhuma aba concedível ficou sem rota que a exija",
                   set(), concediveis - exigidas)
    finally:
        limpar_usuario()
        # 🚨 A prova de que apagou é RELER, não o retorno do DELETE.
        sobrou = await storage.buscar_usuario_painel(LOGIN_TESTE)
        checar("usuário de teste foi removido", None, sobrou)


asyncio.run(main())

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
