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
        # 🚨 A UNIDADE MUDOU EM 17/08: eram ABAS (permissões), agora são TELAS
        # (códigos do registro). Uma permissão pode ter mais de uma tela --
        # `cadastro_placas` tem CAD_1.1 e CAD_1.2 --, e o menu mostra tela.
        #
        # 9 = as 7 antigas + CFG_9.1 (o registro se mostrando) + CAD_1.2, que
        # em 18/08 saiu de `no_menu` e virou "Histórico de Placas", item próprio
        # logo abaixo do Histórico de OS -- a pedido seu. O número é fixo de
        # propósito: tela que aparece no menu sem ninguém pedir é defeito.
        checar("owner enxerga as 9 telas", len(me.get("abas", [])) == 9, str(len(me.get("abas", []))))

        r = await c.get("/painel/api/usuarios/abas", headers=h_owner)
        catalogo = r.json()
        ids = [a["id"] for a in catalogo]
        # 6 desde a F1 (19/08), quando a permissao `operacoes` nasceu.
        checar("catalogo tem 6 abas concediveis", len(catalogo) == 6, str(ids))
        checar("operacoes e concedivel", "operacoes" in ids, str(ids))
        checar("cadastro_placas e concedivel", "cadastro_placas" in ids, str(ids))
        # a aba `placas` saiu do catalogo em 14/08 -- ver abas.py
        checar("placas NAO e mais concedivel", "placas" not in ids, str(ids))
        # e `oficinas` em 17/08, com o fluxo inteiro
        checar("oficinas NAO e mais concedivel", "oficinas" not in ids, str(ids))
        checar("usuarios NAO e concedivel", "usuarios" not in ids)
        checar("config NAO e concedivel (so owner)", "config" not in ids, str(ids))

        # ⚠️ A COBAIA E `vinculos`, E ISSO NAO E DETALHE. Ate 17/08 este teste
        # usava a aba `oficinas` -- o assunto dele sempre foi PERMISSAO, e a
        # oficina era so o exemplo que estava a mao. Com o fluxo de oficina
        # saindo do painel, um teste sobre permissao morreria junto com ele.
        # Trocada por `vinculos`, que e concedivel e tem rota propria.
        print("\n[2] cria operador so com 'vinculos'")
        await c.request("DELETE", "/painel/api/usuarios/0", headers=h_owner)  # no-op, so aquece
        r = await c.post("/painel/api/usuarios", headers=h_owner,
                         json={"login": LOGIN_TESTE, "senha": "senha-de-teste-123",
                               "abas": ["vinculos", "usuarios", "config"]})
        checar("criou operador", r.status_code == 200, r.text[:120])

        op = await storage.buscar_usuario_painel(LOGIN_TESTE)
        checar("'usuarios' e 'config' descartados no cadastro",
               op["abas"] == ["vinculos"], str(op["abas"]))
        h_op = {"Authorization": "Bearer " + criar_token(LOGIN_TESTE)}

        print("\n[3] operador: so a aba dele")
        r = await c.get("/painel/api/me", headers=h_op)
        checar("sidebar do operador tem 1 aba", len(r.json().get("abas", [])) == 1)

        r = await c.get("/painel/api/vinculos", headers=h_op)
        checar("aba concedida responde 200", r.status_code == 200, str(r.status_code))

        # 🚨 NENHUMA DESTAS PODE ACEITAR `vinculos`. `/painel/api/perfis` parece
        # candidata e NAO SERVE: ela e `requer_aba("gerar_os", "vinculos")` --
        # basta UMA das duas, entao responderia 200 e o teste passaria a provar
        # o contrario do que diz. As quatro abaixo exigem aba unica e diferente:
        # prioridades e problemas -> gerar_os, checkpoint -> os_historico,
        # harmonit/resumo -> harmonit_historico.
        for rota in ["/painel/api/prioridades", "/painel/api/problemas",
                     "/painel/api/os-scan/checkpoint", "/painel/api/harmonit/resumo"]:
            r = await c.get(rota, headers=h_op)
            checar(f"403 em {rota}", r.status_code == 403, str(r.status_code))

        r = await c.get("/painel/api/usuarios", headers=h_op)
        checar("operador nao lista usuarios (403)", r.status_code == 403, str(r.status_code))
        r = await c.post("/painel/api/usuarios", headers=h_op,
                         json={"login": "zz_invasor", "senha": "12345678", "abas": []})
        checar("operador nao cria usuario (403)", r.status_code == 403, str(r.status_code))

        print("\n[4] owner mexe no perfil do operador")
        # ⚠️ O perfil novo TEM DE TIRAR `vinculos`, senao o 403 seguinte nao
        # prova nada -- era o que aconteceria trocando por ["gerar_os",
        # "vinculos"], que foi o que este teste fazia enquanto a cobaia era
        # outra aba.
        r = await c.patch(f"/painel/api/usuarios/{op['id']}", headers=h_owner,
                          json={"abas": ["gerar_os"]})
        checar("owner troca o perfil", r.status_code == 200, r.text[:120])
        op2 = await storage.buscar_usuario_painel(LOGIN_TESTE)
        checar("perfil novo gravado", op2["abas"] == ["gerar_os"], str(op2["abas"]))
        r = await c.get("/painel/api/vinculos", headers=h_op)
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


# 🚨 SAI COM O CODIGO CERTO. Ate 20/08 este arquivo imprimia FALHA e
# terminava em 0, entao quem media pelo exit code via verde -- e foi
# assim que a contagem de abas ficou errada desde 19/08 sem ninguem ver.
asyncio.run(main())
sys.exit(1 if falhas else 0)
