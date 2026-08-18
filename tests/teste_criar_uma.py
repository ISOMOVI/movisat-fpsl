"""Escrever uma placa nos dois sistemas — passos 4 e 5.

🚨 AS REGRAS QUE ESTE ARQUIVO PRENDE, e o estrago que cada uma evita:

  1. **Só `/Veiculo/Incluir`, com `id: 0`.** O `PUT /Veiculo/Atualizar` tem os
     MESMOS campos e, sem `id`, CRIA em vez de atualizar. Foi ele que fez 88
     veículos por engano em 27/07 e quebrou 93 vínculos, que continuam
     quebrados. O teste exige que ele não exista no arquivo -- a trava é por
     construção, não por cuidado.

  2. **Harmonit antes da WESO, e falha do primeiro PARA.** Na ordem inversa
     sobraria veículo na WESO sem par -- o estrago espelhado do de 27/07.

  3. **Recipiente não vai ao Harmonit.** Ele é bancada do setor de
     configuração, não veículo do cliente.

  4. **Já existe → informa, não cria** (regra do usuário, 17/08), comparando
     SEM espaço: a WESO grava com espaço e a consulta é igualdade exata. Foi
     assim que a TTX 0H91 do termo 8788 sumiu em julho.

  5. **Simulação não escreve.** E é registrada, para responder depois "por que
     o operador achou que ia funcionar?".

Roda na VPS: venv/bin/python tests/teste_criar_uma.py
Lê os dois sistemas. NÃO escreve: força o interruptor desligado e restaura.
"""
import asyncio
import pathlib
import re
import sqlite3
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel.auth import criar_token  # noqa: E402

BASE = "http://127.0.0.1:8004"
RAIZ = pathlib.Path(__file__).resolve().parent.parent
ROUTER = RAIZ / "fpsl_weso" / "painel" / "routers" / "placas_router.py"

CNPJ = "WQ0P6GLD000108"
CLIENTE_HARMONIT = 998063
CLIENTE_WESO = 13562
JA_EXISTE = "TST 0G77"          # criada em 17/08, existe nos DOIS
NAO_EXISTE = "TST9Z00"

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def limpar(lote):
    storage._init_cadastro_placas_log()
    with sqlite3.connect(storage.DB_PATH) as conn:
        conn.execute("DELETE FROM cadastro_placas_log WHERE lote = ?", (lote,))


# ── 1. a trava por construção ───────────────────────────────────────────────
print("\n[1] o Atualizar do Harmonit não existe neste arquivo")
codigo = ROUTER.read_text(encoding="utf-8")
checar("usa /Veiculo/Incluir", True, "/Veiculo/Incluir" in codigo)

# ⚠️ DUAS VERSÕES ANTERIORES DESTA CHECAGEM FALHARAM, e as duas por medir texto
# em vez de comportamento: a primeira procurava a string no arquivo inteiro e
# reprovava por causa do COMENTÁRIO que explica o cuidado; a segunda filtrava
# linhas `#` e ainda pegava a DOCSTRING. Teste que reprova a documentação do
# próprio cuidado é teste ruim.
#
# 🚨 O QUE SE MEDE AGORA É A LISTA DE ENDPOINTS DE ESCRITA REALMENTE CHAMADOS.
# Se alguém acrescentar o `Atualizar` numa chamada, ele aparece aqui e o teste
# reprova. Comentar sobre ele continua livre.
escritas_harmonit = set(re.findall(r'harmonit_post\(\s*"([^"]+)"', codigo))
checar("o único endpoint de escrita do Harmonit é o Incluir",
       {"/Veiculo/Incluir"}, escritas_harmonit)
checar("e manda id 0 explícito", True, '"id": 0' in codigo)


async def main():
    admin = await storage.buscar_usuario_painel("admin")
    h = {"Authorization": "Bearer " + criar_token(admin["login"])}
    anterior = await storage.get_config("placas_registro_ativo", "false")
    await storage.set_config("placas_registro_ativo", "false")

    async with httpx.AsyncClient(base_url=BASE, timeout=300) as c:
        lote = (await c.post("/painel/api/placas/lote", headers=h)).json()["lote"]
        base = {"lote": lote, "cnpjcpf": CNPJ, "perfil": "cliente_novo",
                "termo": "9999", "cliente_harmonit_id": CLIENTE_HARMONIT,
                "cliente_weso_id": CLIENTE_WESO}
        try:
            print("\n[2] o lote nasce único")
            outro = (await c.post("/painel/api/placas/lote", headers=h)).json()["lote"]
            checar("dois lotes diferentes", True, lote != outro)

            print("\n[3] já existe → informa e NÃO cria, ignorando espaço")
            # ⚠️ mandado SEM espaço; está gravado COM espaço nos dois sistemas
            r = await c.post("/painel/api/placas/criar-uma", headers=h,
                             json={**base, "placa": JA_EXISTE.replace(" ", ""),
                                   "descricao": "qualquer"})
            d = r.json()
            checar("a WESO reconhece", "ja_existia", d["weso"]["acao"])
            checar("o Harmonit também", "ja_existia", d["harmonit"]["acao"])
            checar("e diz de quem é no Harmonit", True,
                   bool(d["harmonit"].get("dono")))

            print("\n[4] simulação não escreve")
            r = await c.post("/painel/api/placas/criar-uma", headers=h,
                             json={**base, "placa": NAO_EXISTE,
                                   "descricao": "VEICULO DE TESTE"})
            d = r.json()
            checar("Harmonit simulado", "simulado", d["harmonit"]["acao"])
            checar("WESO simulada", "simulado", d["weso"]["acao"])
            # 🚨 A PROVA: consulta independente. Se a placa apareceu, mentiu.
            r = await c.post("/painel/api/placas/previa", headers=h,
                             json={"cnpjcpf": CNPJ, "itens": [{"placa": NAO_EXISTE}]})
            checar("e a placa continua não existindo", "criar",
                   r.json()["itens"][0]["acao"])

            print("\n[5] recipiente NÃO vai ao Harmonit")
            r = await c.post("/painel/api/placas/criar-uma", headers=h,
                             json={**base, "placa": NAO_EXISTE,
                                   "sufixo": "-UPGRADE", "termo": "9999"})
            d = r.json()
            checar("Harmonit ignora", "ignorado", d["harmonit"]["acao"])
            checar("com o motivo", True, "bancada" in d["harmonit"]["motivo"])
            checar("mas a WESO trata", "simulado", d["weso"]["acao"])
            checar("e a descrição é derivada do termo", "TERMO 9999", d["descricao"])

            print("\n[6] recipiente de upgrade sem termo é recusado nos DOIS")
            r = await c.post("/painel/api/placas/criar-uma", headers=h,
                             json={**base, "placa": NAO_EXISTE, "sufixo": "-UPGRADE",
                                   "termo": None})
            d = r.json()
            checar("Harmonit ignorado", "ignorado", d["harmonit"]["acao"])
            checar("WESO ignorada", "ignorado", d["weso"]["acao"])
            checar("e o motivo fala do termo", True,
                   "termo" in (d["weso"]["erro"] or "").lower())

            print("\n[7] sem cliente no Harmonit, a WESO segue sozinha")
            r = await c.post("/painel/api/placas/criar-uma", headers=h,
                             json={**base, "placa": NAO_EXISTE,
                                   "descricao": "X", "cliente_harmonit_id": None})
            d = r.json()
            checar("Harmonit ignorado", "ignorado", d["harmonit"]["acao"])
            checar("mas a WESO não para", "simulado", d["weso"]["acao"])

            print("\n[8] tudo foi para o registro")
            linhas = await storage.listar_cadastro_placas(lote=lote,
                                                          incluir_simulado=True)
            # 5 tentativas × 2 sistemas. (Contei 12 na primeira versão e o
            # teste reprovou -- a aritmética era minha, o código estava certo.)
            checar("duas linhas por tentativa", 10, len(linhas))
            checar("os dois sistemas aparecem", {"harmonit", "weso"},
                   {l["sistema"] for l in linhas})
            # ⚠️ o caso [6] manda `termo: None` DE PROPÓSITO, para provar que
            # recipiente de upgrade sem termo é recusado. Exigir `{"9999"}` aqui
            # reprovaria justamente o cenário que o teste quer exercitar.
            checar("o termo viajou junto onde havia termo", {None, "9999"},
                   {l["termo"] for l in linhas})
        finally:
            await storage.set_config("placas_registro_ativo", anterior)
            limpar(lote)
            checar("o lote de teste foi removido", 0,
                   len(await storage.listar_cadastro_placas(lote=lote,
                                                            incluir_simulado=True)))


asyncio.run(main())

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
