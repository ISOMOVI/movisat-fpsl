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
        # 10 desde 20/08: a aba Operações saiu de `no_menu` por decisão do
        # usuário. O número fica explícito de propósito -- tela nova no menu
        # tem de passar por aqui e ser deliberada.
        # 12 desde 29/09: FIN_1.1 (Conferência de Fechamento) nasceu no menu.
        # 9 desde 02/10: o expurgo F7 tirou CAD_1.1, OSG_1.1 e CAD_1.2 do menu.
        # 🚨 10 DESDE 06/10, E A TRAVA PEGOU TARDE: a FIN_2.1 (Fechamento dos
        # Técnicos) nasceu no menu e este número não foi atualizado -- a suíte
        # ficou vermelha de 06/10 a 13/10 (exit=1) sem ninguém olhar.
        # 11 desde 13/10: CTR_1.1 (Gestão de Contratos).
        # 12 desde 28/10: CAR_1.1 (Contas a Receber).
        checar("owner enxerga as 12 telas do menu",
               len(me.get("abas", [])) == 12, str(len(me.get("abas", []))))
        checar("e Operações é uma delas",
               any(a.get("id") == "operacoes" for a in me.get("abas", [])),
               str([a.get("id") for a in me.get("abas", [])]))

        r = await c.get("/painel/api/usuarios/abas", headers=h_owner)
        catalogo = r.json()
        ids = [a["id"] for a in catalogo]
        # 6 desde a F1 (19/08), quando a permissao `operacoes` nasceu.
        # 7 desde 29/09: `financeiro` (FIN_1.1, Conferência de Fechamento).
        # 5 desde 02/10: o expurgo F7 tirou `gerar_os` e `cadastro_placas`.
        # ⚠️ CONTINUA 5 COM A CTR_1.1 (13/10), e é de propósito: `contratos`
        # nasceu em `PERMISSOES_SO_OWNER` por decisão dele ("somente eu, como
        # padrão owner inicial"), e permissão de owner não é concedível.
        # 23/10: 5 -> 7. Decisao dele: "todas devem permitir que eu escolha
        # o que ela ve". `contratos` e `config` sairam de PERMISSOES_SO_OWNER.
        # 28/10: 7 -> 8. A CAR_1.1 (Contas a Receber) nasce com permissao
        # PROPRIA, `contas_receber`, e nao reusando `financeiro`: a aba cancela
        # cobranca e preco em lote, e quem tem `financeiro` confere OS. Nascer
        # concedivel NAO concede nada a ninguem -- so faz a permissao APARECER
        # no modal de perfil, desligada, para ele ligar em quem quiser.
        checar("catalogo tem 8 abas concediveis", len(catalogo) == 8, str(ids))
        checar("contas_receber e concedivel, e NAO e a `financeiro`",
               "contas_receber" in ids, str(ids))
        checar("contratos E concedivel (23/10, era so-owner desde 13/10)",
               "contratos" in ids, str(ids))
        checar("operacoes e concedivel", "operacoes" in ids, str(ids))
        checar("gerar_os NAO e mais concedivel (expurgo F7)", "gerar_os" not in ids, str(ids))
        checar("cadastro_placas NAO e mais concedivel (expurgo F7)",
               "cadastro_placas" not in ids, str(ids))
        # a aba `placas` saiu do catalogo em 14/08 -- ver abas.py
        checar("placas NAO e mais concedivel", "placas" not in ids, str(ids))
        # e `oficinas` em 17/08, com o fluxo inteiro
        checar("oficinas NAO e mais concedivel", "oficinas" not in ids, str(ids))
        checar("usuarios NAO e concedivel", "usuarios" not in ids)
        checar("config E concedivel (23/10, era so-owner desde 27/07)",
               "config" in ids, str(ids))
        # A trava que faltava: `usuarios` fica fora porque NENHUMA ROTA o
        # exige -- o router inteiro usa `get_owner_painel`. Conceder daria
        # tela no menu com 403 em toda chamada (a porta trancada da `placas`).
        raiz = pathlib.Path(__file__).resolve().parent.parent
        rotas = (raiz / "fpsl_weso" / "painel" / "routers")
        fonte = "\n".join(f.read_text(encoding="utf-8")
                          for f in rotas.glob("*.py") if ".bak" not in f.name)
        checar("e nenhuma rota exige 'usuarios' (por isso fica fora)",
               'requer_aba("usuarios")' not in fonte)

        # ⚠️ A COBAIA E `vinculos`, E ISSO NAO E DETALHE. Ate 17/08 este teste
        # usava a aba `oficinas` -- o assunto dele sempre foi PERMISSAO, e a
        # oficina era so o exemplo que estava a mao. Com o fluxo de oficina
        # saindo do painel, um teste sobre permissao morreria junto com ele.
        # Trocada por `vinculos`, que e concedivel e tem rota propria.
        print("\n[2] cria operador so com 'vinculos'")
        await c.request("DELETE", "/painel/api/usuarios/0", headers=h_owner)  # no-op, so aquece
        # 23/10: `config` passou a ser concedivel, entao nao e mais descartado.
        # Quem testa o descarte agora e `usuarios`, o unico so-owner que restou.
        r = await c.post("/painel/api/usuarios", headers=h_owner,
                         json={"login": LOGIN_TESTE, "senha": "senha-de-teste-123",
                               "abas": ["vinculos", "usuarios", "inventada"]})
        checar("criou operador", r.status_code == 200, r.text[:120])

        op = await storage.buscar_usuario_painel(LOGIN_TESTE)
        checar("'usuarios' (so-owner) e 'inventada' descartados no cadastro",
               op["abas"] == ["vinculos"], str(op["abas"]))
        h_op = {"Authorization": "Bearer " + criar_token(LOGIN_TESTE)}

        print("\n[3] operador: so a aba dele")
        r = await c.get("/painel/api/me", headers=h_op)
        checar("sidebar do operador tem 1 aba", len(r.json().get("abas", [])) == 1)

        r = await c.get("/painel/api/vinculos", headers=h_op)
        checar("aba concedida responde 200", r.status_code == 200, str(r.status_code))

        # 🚨 NENHUMA DESTAS PODE ACEITAR `vinculos`. Cada uma exige uma aba única
        # e diferente: checkpoint -> os_historico, harmonit/resumo ->
        # harmonit_historico, conferencia-fechamento -> financeiro.
        # (prioridades/problemas saíram no expurgo F7 -- eram de `gerar_os`.)
        for rota in ["/painel/api/os-scan/checkpoint", "/painel/api/harmonit/resumo",
                     "/painel/api/conferencia-fechamento"]:
            r = await c.get(rota, headers=h_op)
            checar(f"403 em {rota}", r.status_code == 403, str(r.status_code))

        r = await c.get("/painel/api/usuarios", headers=h_op)
        checar("operador nao lista usuarios (403)", r.status_code == 403, str(r.status_code))
        r = await c.post("/painel/api/usuarios", headers=h_op,
                         json={"login": "zz_invasor", "senha": "12345678", "abas": []})
        checar("operador nao cria usuario (403)", r.status_code == 403, str(r.status_code))

        print("\n[4] owner mexe no perfil do operador")
        # ⚠️ O perfil novo TEM DE TIRAR `vinculos`, senao o 403 seguinte nao
        # prova nada. A cobaia era `gerar_os`, aposentada no expurgo F7 -- trocada
        # por `os_historico`, que é concedível e diferente de `vinculos`.
        r = await c.patch(f"/painel/api/usuarios/{op['id']}", headers=h_owner,
                          json={"abas": ["os_historico"]})
        checar("owner troca o perfil", r.status_code == 200, r.text[:120])
        op2 = await storage.buscar_usuario_painel(LOGIN_TESTE)
        checar("perfil novo gravado", op2["abas"] == ["os_historico"], str(op2["abas"]))
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
