"""A aba de Cadastro de Placas, ponta a ponta pelas rotas HTTP.

🚨 O QUE ESTE TESTE PRENDE, e por que cada coisa importa:

  1. **A tranca.** Sem token -> 401; com token sem a aba -> 403. A aba `placas`
     de julho morreu justamente por não ter isto: as rotas dela exigiam
     `gerar_os`, então a permissão era de mentira (ver `cf16837`).

  2. **A grafia gravada.** `placas.formatar` põe espaço na placa convencional e
     deixa o recipiente intacto -- a placa real e o recipiente dela ficam com
     grafias DIFERENTES na WESO. Se isso mudar sem querer, a geração de OS
     deixa de achar o recipiente.

  3. **A descrição do recipiente é DERIVADA, nunca digitada.** `-MANUT` ->
     `MANUTENCAO`, `-UPGRADE` -> `TERMO {n}`. É contrato com o gerador de OS:
     descrição errada = recipiente não reconhecido = OS sem série, em silêncio.

  4. **Upgrade sem termo é RECUSADO.** Sem o número não dá para montar
     `TERMO {n}`, e gravar uma descrição incompleta é pior que não gravar.

  5. **A simulação não escreve.** Com `placas_registro_ativo=false`, `/criar`
     devolve o que faria e não chama a WESO.

Roda na VPS: venv/bin/python tests/teste_cadastro_placas.py
⚠️ Fala com a WESO em LEITURA (a prévia confere placa). Não escreve: o teste
força o interruptor desligado e o restaura no fim.
"""
import asyncio
import pathlib
import sqlite3
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel.auth import criar_token  # noqa: E402
from fpsl_weso.painel.routers import placas_router  # noqa: E402

BASE = "http://127.0.0.1:8004"
LOGIN_TESTE = "zz_teste_placas"
SENHA = "senha-de-teste-123"
CNPJ_VELASCO = "WQ0P6GLD000108"

ok, falhas = 0, []


def limpar_usuario():
    with sqlite3.connect(storage.DB_PATH) as conn:
        conn.execute("DELETE FROM painel_usuarios WHERE login = ?", (LOGIN_TESTE,))


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


# ── 1. as regras puras, sem rede ─────────────────────────────────────────────
print("\n[1] grafia e descrição — as duas coisas que o gerador de OS confere")

Item = placas_router.ItemPlaca

checar("placa convencional ganha espaço", "TST 0A11",
       placas_router._texto_gravado(Item(placa="TST0A11")))
checar("recipiente fica intacto", "TST0A11-MANUT",
       placas_router._texto_gravado(Item(placa="TST0A11", sufixo="-MANUT")))
# 🚨 o recipiente sai da placa COM espaço também -- é o caso real do termo
checar("recipiente de placa com espaço não leva o espaço", "OOM4131-UPGRADE",
       placas_router._texto_gravado(Item(placa="OOM 4131", sufixo="-UPGRADE")))

checar("-MANUT vira MANUTENCAO", ("MANUTENCAO", None),
       placas_router._descricao_final(Item(placa="X", sufixo="-MANUT")))
checar("-UPGRADE vira TERMO n", ("TERMO 8820", None),
       placas_router._descricao_final(Item(placa="X", sufixo="-UPGRADE", termo="8820")))

# ⚠️ ESTA É A TRAVA 4. Sem termo a descrição sairia "TERMO " e o gerador não
# reconheceria o recipiente -- falha silenciosa, que é o que este projeto mais
# apanha. Recusar é o comportamento certo.
desc, err = placas_router._descricao_final(Item(placa="X", sufixo="-UPGRADE"))
checar("upgrade sem termo é recusado", None, desc)
checar("e diz o porquê", True, "termo" in (err or "").lower())

desc, err = placas_router._descricao_final(Item(placa="X", sufixo="-INVENTADO"))
checar("sufixo desconhecido é recusado", None, desc)

checar("placa sem sufixo usa a descrição digitada", ("Caminhão 1", None),
       placas_router._descricao_final(Item(placa="X", descricao="Caminhão 1")))


# ── 2. a tranca ──────────────────────────────────────────────────────────────
async def main():
    admin = await storage.buscar_usuario_painel("admin")
    h_owner = {"Authorization": "Bearer " + criar_token(admin["login"])}

    # ⚠️ NÃO EXISTE ROTA DELETE DE USUÁRIO -- o router tem GET, POST e PATCH.
    # A limpeza é por SQL, como `teste_perfis.py` já fazia. Tentar pela rota
    # devolve 405 e o teste "passaria" deixando lixo no banco.
    limpar_usuario()
    # usuário sem nenhuma aba, criado pela ROTA (exercita o cadastro junto)
    async with httpx.AsyncClient(base_url=BASE, timeout=20) as c0:
        await c0.post("/painel/api/usuarios", headers=h_owner,
                      json={"login": LOGIN_TESTE, "senha": SENHA, "abas": []})
    magro = await storage.buscar_usuario_painel(LOGIN_TESTE)
    h_magro = {"Authorization": "Bearer " + criar_token(magro["login"])}

    corpo = {"cnpjcpf": CNPJ_VELASCO, "itens": [{"placa": "TST0A11"}]}

    print("\n[2] a tranca — foi a falta dela que matou a aba de julho")
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        for rota in ("/painel/api/placas/previa", "/painel/api/placas/criar"):
            r = await c.post(rota, json=corpo)
            checar(f"401 sem token em {rota}", 401, r.status_code)
            r = await c.post(rota, json=corpo, headers=h_magro)
            checar(f"403 sem a aba em {rota}", 403, r.status_code)

        # ⚠️ o toggle é de `config`, que é somente_owner -- não da aba nova
        r = await c.get("/painel/api/placas/config/ativo", headers=h_magro)
        checar("403 no toggle sem a aba config", 403, r.status_code)

        print("\n[3] prévia — lê a WESO e NÃO escreve")
        anterior = await storage.get_config("placas_registro_ativo", "false")
        await storage.set_config("placas_registro_ativo", "false")
        try:
            r = await c.post("/painel/api/placas/previa", headers=h_owner, json={
                "cnpjcpf": CNPJ_VELASCO,
                "itens": [
                    {"placa": "TST0A11"},
                    {"placa": "TST0A11", "sufixo": "-MANUT"},
                    {"placa": "ZZZ9Z99"},
                ]})
            checar("prévia responde 200", 200, r.status_code)
            d = r.json()
            checar("achou a Velasco na WESO", True, d["cliente"]["existe_na_weso"])
            checar("e é o cliente 13562", 13562, d["cliente"]["id"])
            checar("a escrita está desligada", False, d["escrita_ativa"])

            porplaca = {i["placa_gravada"]: i for i in d["itens"]}
            # as duas primeiras EXISTEM: foram criadas na medição de 17/08
            checar("TST 0A11 já existe", "ja_existe",
                   porplaca["TST 0A11"]["acao"])
            checar("TST0A11-MANUT já existe", "ja_existe",
                   porplaca["TST0A11-MANUT"]["acao"])
            checar("e a placa inventada seria criada", "criar",
                   porplaca["ZZZ 9Z99"]["acao"])

            print("\n[4] criar com a escrita desligada NÃO grava")
            r = await c.post("/painel/api/placas/criar", headers=h_owner, json={
                "cnpjcpf": CNPJ_VELASCO,
                "itens": [{"placa": "ZZZ9Z99"}]})
            checar("criar responde 200", 200, r.status_code)
            d = r.json()
            checar("nada foi gravado", 0, d["criadas"])
            checar("e a linha veio marcada como simulada", True,
                   d["itens"][0].get("simulado"))
            # 🚨 A PROVA: reler. Se a placa apareceu, a simulação mentiu.
            #
            # ⚠️ A releitura vai pela ROTA, não por `buscar_veiculo` direto:
            # o cliente HTTP da WESO é inicializado no `lifespan` do app, e
            # neste processo ele não existe (`_client` é None). Chamar a função
            # daqui estoura em AttributeError -- que foi o que aconteceu na
            # primeira versão deste teste. Pela rota, quem consulta é o serviço,
            # que é exatamente o caminho que o operador exercita.
            r = await c.post("/painel/api/placas/previa", headers=h_owner, json={
                "cnpjcpf": CNPJ_VELASCO, "itens": [{"placa": "ZZZ9Z99"}]})
            checar("a placa continua NÃO existindo depois da simulação", "criar",
                   r.json()["itens"][0]["acao"])
        finally:
            await storage.set_config("placas_registro_ativo", anterior)

    limpar_usuario()
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
