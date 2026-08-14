"""Teste end-to-end do perfil de acesso por aba (2026-07-27).

Gera o token internamente (nunca passa senha por linha de comando) e exercita:
owner enxerga tudo, operador só as abas marcadas, aba não marcada dá 403,
e a conta owner é intocável pela rota de gestão.

Roda na VPS: venv/bin/python tests/teste_perfis.py
Remove o usuário de teste ao final.

⚠️ Mudou de lugar em 2026-08-14: estava solto na raiz, junto com dois
exploratórios que escreviam na WESO (esses foram apagados). Este ficou porque
a trava que ele exercita -- acesso por aba -- está em uso real nos 9
roteadores. Ao mudar de pasta precisou do sys.path, como os outros de tests/.
"""
import asyncio
import pathlib
import sqlite3
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso.painel.auth import criar_token  # noqa: E402
from fpsl_weso import storage  # noqa: E402

BASE = "http://127.0.0.1:8004"
LOGIN_TESTE = "zz_teste_perfil"
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
    admin = await storage.buscar_usuario_painel("admin")
    h_owner = {"Authorization": "Bearer " + criar_token(admin["login"])}

    async with httpx.AsyncClient(base_url=BASE, timeout=20) as c:
        print("\n[1] owner")
        r = await c.get("/painel/api/me", headers=h_owner)
        me = r.json()
        checar("me responde 200", r.status_code == 200, r.text[:120])
        checar("owner=True", me.get("owner") is True)
        # 🚨 NUMERO TRAVADO DE PROPOSITO: aba nova sem pensar em permissao faz
        # o teste avisar. Eram 8 ate 14/08, quando a aba "placas" saiu -- ela
        # nao era exigida por rota nenhuma, entao nao protegia nada.
        checar("owner enxerga as 7 abas", len(me.get("abas", [])) == 7, str(len(me.get("abas", []))))

        r = await c.get("/painel/api/usuarios/abas", headers=h_owner)
        catalogo = r.json()
        ids = [a["id"] for a in catalogo]
        checar("catalogo tem 5 abas concediveis", len(catalogo) == 5, str(ids))
        # a aba `placas` saiu do catalogo em 14/08 -- ver abas.py
        checar("placas NAO e mais concedivel", "placas" not in ids, str(ids))
        checar("usuarios NAO e concedivel", "usuarios" not in ids)
        checar("config NAO e concedivel (so owner)", "config" not in ids, str(ids))

        print("\n[2] cria operador so com 'oficinas'")
        await c.request("DELETE", "/painel/api/usuarios/0", headers=h_owner)  # no-op, so aquece
        r = await c.post("/painel/api/usuarios", headers=h_owner,
                         json={"login": LOGIN_TESTE, "senha": "senha-de-teste-123",
                               "abas": ["oficinas", "usuarios", "config"]})
        checar("criou operador", r.status_code == 200, r.text[:120])

        op = await storage.buscar_usuario_painel(LOGIN_TESTE)
        checar("'usuarios' e 'config' descartados no cadastro",
               op["abas"] == ["oficinas"], str(op["abas"]))
        h_op = {"Authorization": "Bearer " + criar_token(LOGIN_TESTE)}

        print("\n[3] operador: so a aba dele")
        r = await c.get("/painel/api/me", headers=h_op)
        checar("sidebar do operador tem 1 aba", len(r.json().get("abas", [])) == 1)

        r = await c.get("/painel/api/oficina/historico", headers=h_op)
        checar("aba concedida responde 200", r.status_code == 200, str(r.status_code))

        for rota in ["/painel/api/vinculos", "/painel/api/prioridades",
                     "/painel/api/os-scan/checkpoint", "/painel/api/oficina/config/ativo"]:
            r = await c.get(rota, headers=h_op)
            checar(f"403 em {rota}", r.status_code == 403, str(r.status_code))

        r = await c.get("/painel/api/usuarios", headers=h_op)
        checar("operador nao lista usuarios (403)", r.status_code == 403, str(r.status_code))
        r = await c.post("/painel/api/usuarios", headers=h_op,
                         json={"login": "zz_invasor", "senha": "12345678", "abas": []})
        checar("operador nao cria usuario (403)", r.status_code == 403, str(r.status_code))

        print("\n[4] owner mexe no perfil do operador")
        r = await c.patch(f"/painel/api/usuarios/{op['id']}", headers=h_owner,
                          json={"abas": ["gerar_os", "vinculos"]})
        checar("owner troca o perfil", r.status_code == 200, r.text[:120])
        op2 = await storage.buscar_usuario_painel(LOGIN_TESTE)
        checar("perfil novo gravado", op2["abas"] == ["gerar_os", "vinculos"], str(op2["abas"]))
        r = await c.get("/painel/api/oficina/historico", headers=h_op)
        checar("aba removida virou 403", r.status_code == 403, str(r.status_code))

        print("\n[5] owner e intocavel")
        r = await c.patch(f"/painel/api/usuarios/{admin['id']}", headers=h_owner,
                          json={"ativo": False})
        checar("nao desativa o owner", r.status_code == 400, str(r.status_code))
        ainda = await storage.buscar_usuario_painel("admin")
        checar("owner segue ativo", ainda["ativo"] is True)

    with sqlite3.connect(storage.DB_PATH) as conn:
        conn.execute("DELETE FROM painel_usuarios WHERE login = ?", (LOGIN_TESTE,))
    print(f"\n{'='*46}\n{ok_total} passaram, {len(falhas)} falharam")
    if falhas:
        for f in falhas:
            print("  -", f)


asyncio.run(main())
