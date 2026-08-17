"""Entrada pelo Google no FPSL — as travas, sem falar com o Google.

🚨 O QUE ESTE TESTE PRENDE. Não dá para exercitar o handshake real numa suíte
(exige navegador e consentimento humano), então o que se testa é tudo o que
acontece ANTES e DEPOIS dele — que é onde moram as decisões de segurança:

  1. **Degradação sem credencial.** Sem `google_client_id` no .env, o painel
     tem de continuar 100% funcional por senha, e a tela nem mostrar o botão.
     Botão que não funciona rende chamado.

  2. **`state` assinado.** É o que prova que o retorno veio de um início nosso.
     Um `state` forjado, vencido ou de outro tipo tem de ser recusado.

  3. **Conta tem que existir.** A busca por google_sub/e-mail NUNCA cria.

  4. **`sub` antes de e-mail.** Quem trocou de endereço no Google continua
     sendo reencontrado pelo `sub` — casar só por e-mail perderia o vínculo
     em silêncio.

  5. **Trocar o e-mail zera o `google_sub`.** É assim que a conta passa de mão;
     sem isso a conta Google antiga continuaria entrando.

  6. **Só o domínio da casa.** No cadastro e na entrada.

Roda na VPS: venv/bin/python tests/teste_google_login.py
Não fala com o Google nem com a WESO.
"""
import asyncio
import pathlib
import sqlite3
import sys
import time

import httpx
from jose import jwt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.config import settings  # noqa: E402
from fpsl_weso.painel import auth, google_auth  # noqa: E402
from fpsl_weso.painel.auth import criar_token  # noqa: E402

BASE = "http://127.0.0.1:8004"
LOGIN_TESTE = "zz_teste_google"

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def limpar():
    with sqlite3.connect(storage.DB_PATH) as conn:
        conn.execute("DELETE FROM painel_usuarios WHERE login = ?", (LOGIN_TESTE,))


print("\n[1] o state — a trava que impede terceiro de disparar a troca")

s = google_auth._novo_state()
checar("o state que eu emito vale", True, google_auth._state_valido(s))
checar("lixo não vale", False, google_auth._state_valido("nao-e-um-jwt"))
checar("vazio não vale", False, google_auth._state_valido(""))

# 🚨 Assinado com OUTRO segredo: é o caso do atacante que monta o próprio JWT.
outro = jwt.encode({"tipo": google_auth.TIPO_STATE, "exp": int(time.time()) + 600},
                   "segredo-do-atacante", algorithm=auth.ALGORITHM)
checar("assinado com outro segredo não vale", False, google_auth._state_valido(outro))

# ⚠️ Assinado com o NOSSO segredo mas com outro `tipo`: é o token de sessão
# sendo reaproveitado como state. Sem conferir o tipo, ele passaria.
sessao = criar_token("admin")
checar("token de sessão não serve de state", False, google_auth._state_valido(sessao))

vencido = jwt.encode({"tipo": google_auth.TIPO_STATE, "exp": int(time.time()) - 10},
                     settings.painel_jwt_secret, algorithm=auth.ALGORITHM)
checar("state vencido não vale", False, google_auth._state_valido(vencido))


print("\n[2] degradação sem credencial — o painel não pode depender disto")
tinha = bool(settings.google_client_id)
checar("configurado() reflete o .env", tinha, google_auth.configurado())
if not tinha:
    print("       (sem credencial no .env: é o estado de hoje)")


async def main():
    admin = await storage.buscar_usuario_painel("admin")
    h_owner = {"Authorization": "Bearer " + criar_token(admin["login"])}

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.get("/painel/api/auth/google/disponivel")
        checar("a rota /disponivel é pública e diz a verdade", tinha,
               r.json()["disponivel"])
        if not tinha:
            r = await c.get("/painel/api/auth/google/inicio")
            checar("iniciar sem credencial dá 503, não 500", 503, r.status_code)

        # 🚨 O callback NUNCA pode devolver 500 -- é rota pública, e qualquer
        # um chega nela com o que quiser.
        r = await c.get("/painel/api/auth/google/callback",
                        params={"error": "access_denied"},
                        follow_redirects=False)
        checar("callback com erro redireciona", 302, r.status_code)
        checar("e leva o motivo no FRAGMENTO, não na query", True,
               "#erro=" in r.headers.get("location", ""))

        r = await c.get("/painel/api/auth/google/callback",
                        params={"code": "inventado", "state": "invalido"},
                        follow_redirects=False)
        checar("state inválido não vira 500", 302, r.status_code)
        checar("e a pessoa volta ao login com o motivo", True,
               r.headers.get("location", "").startswith("/painel#erro="))

        print("\n[3] a conta tem que existir — a busca NUNCA cria")
        antes = await storage.contar_usuarios_painel()
        achado = await storage.buscar_usuario_painel_por_google(
            "sub-que-nao-existe", "ninguem@movisat.com.br")
        checar("e-mail desconhecido não acha ninguém", None, achado)
        checar("e não criou conta nenhuma", antes,
               await storage.contar_usuarios_painel())

        print("\n[4] o vínculo — e-mail acha, sub tem prioridade")
        limpar()
        r = await c.post("/painel/api/usuarios", headers=h_owner, json={
            "login": LOGIN_TESTE, "senha": "senha-de-teste-123",
            "abas": ["vinculos"], "email": "zzteste@movisat.com.br"})
        checar("criou usuário com e-mail de vínculo", 200, r.status_code)

        u = await storage.buscar_usuario_painel_por_google(None, "zzteste@movisat.com.br")
        checar("acha pelo e-mail na primeira entrada", LOGIN_TESTE,
               (u or {}).get("login"))
        checar("e ainda não tem sub", None, (u or {}).get("google_sub"))

        await storage.gravar_google_sub(u["id"], "sub-111")
        u2 = await storage.buscar_usuario_painel_por_google("sub-111", "outro@movisat.com.br")
        # 🚨 ESTE É O PONTO DO `google_sub`: o e-mail mudou no Google e a conta
        # continua sendo encontrada. Casando só por e-mail, o vínculo sumiria.
        checar("acha pelo sub mesmo com outro e-mail", LOGIN_TESTE,
               (u2 or {}).get("login"))

        print("\n[5] trocar o e-mail zera o sub — é assim que a conta passa de mão")
        await storage.definir_email_painel(u["id"], "novo@movisat.com.br")
        u3 = await storage.buscar_usuario_painel_por_google(None, "novo@movisat.com.br")
        checar("o e-mail novo acha", LOGIN_TESTE, (u3 or {}).get("login"))
        checar("e o sub foi zerado", None, (u3 or {}).get("google_sub"))
        checar("o sub antigo não acha mais ninguém", None,
               await storage.buscar_usuario_painel_por_google("sub-111", ""))

        print("\n[6] só o domínio da casa")
        r = await c.patch(f"/painel/api/usuarios/{u['id']}", headers=h_owner,
                          json={"email": "fulano@gmail.com"})
        checar("e-mail de fora é recusado no cadastro", 400, r.status_code)
        # ⚠️ e o que estava lá não pode ter sido apagado pela tentativa
        u4 = await storage.buscar_usuario_painel_por_id(u["id"])
        checar("e o e-mail anterior continua", "novo@movisat.com.br", u4.get("email"))

        print("\n[7] os três de produção têm vínculo")
        todos = {x["login"].lower(): x for x in await storage.listar_usuarios_painel()}
        for login, esperado in (("admin", "iago@movisat.com.br"),
                                ("erika", "erika@movisat.com.br"),
                                ("caio", "caio@movisat.com.br")):
            checar(f"{login} tem e-mail de vínculo", esperado,
                   (todos.get(login) or {}).get("email"))

        limpar()
        checar("usuário de teste removido", None,
               await storage.buscar_usuario_painel(LOGIN_TESTE))


asyncio.run(main())

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
