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

  5. **A prova de gravação é RELER**, nunca o código de retorno. Se a releitura
     não achar, a linha é `falhou` -- e não `criado`.

🚨 POR QUE ESTE TESTE RODA IN-PROCESS, E NÃO PELO HTTP (mudou em 19/08).

Até 18/08 ele batia no serviço por HTTP e se protegia de escrever ligando o
interruptor `placas_registro_ativo` em `false`: as chamadas voltavam
`simulado`. **O interruptor foi removido em 19/08** -- decisão do usuário, o
cadastro é rotina nativa e subir o termo grava. Sem ele, cada uma destas
chamadas criaria veículo de verdade na WESO e no Harmonit, e o do Harmonit
**não teria como ser apagado**: `/Veiculo/` não tem DELETE.

Então o teste passou a chamar `criar_uma` direto, com a WESO e o Harmonit
substituídos por dublês. Ganhou três coisas que a versão anterior não tinha:
não depende de placa viva em produção, roda em milissegundos em vez de
minutos, e consegue exercitar o caminho de **sucesso** -- que com o
interruptor era invisível, porque a escrita nunca acontecia.

⚠️ O que ele deixou de cobrir: a camada HTTP e a tranca de permissão. Isso é
de `teste_cadastro_placas.py` (401/403) e `teste_roteadores_painel.py`.

Roda na VPS: venv/bin/python tests/teste_criar_uma.py
NÃO faz rede e NÃO escreve em sistema externo. Grava só no `cadastro_placas_log`
local, num lote próprio que ele mesmo apaga no fim.
"""
import asyncio
import pathlib
import re
import sqlite3
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel.routers import placas_router  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ROUTER = RAIZ / "fpsl_weso" / "painel" / "routers" / "placas_router.py"

CNPJ = "WQ0P6GLD000108"
CLIENTE_HARMONIT = 998063
CLIENTE_WESO = 13562

# Nenhuma destas existe em lugar nenhum: quem responde é o dublê. Placa viva em
# produção como fixture foi o que quebrou este teste em 19/08.
JA_EXISTE = "TST 0Z11"
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
    with sqlite3.connect(storage.DB_PATH) as conn:
        conn.execute("DELETE FROM cadastro_placas_log WHERE lote = ?", (lote,))


# ── 1. a trava por construção, lendo o próprio código ────────────────────────
print("\n[1] o único endpoint de escrita do Harmonit")
codigo = ROUTER.read_text(encoding="utf-8")

# 🚨 O QUE SE MEDE É A LISTA DE ENDPOINTS DE ESCRITA REALMENTE CHAMADOS.
# Se alguém acrescentar o `Atualizar` numa chamada, ele aparece aqui e o teste
# reprova. Comentar sobre ele continua livre.
escritas_harmonit = set(re.findall(r'harmonit_post\(\s*"([^"]+)"', codigo))
checar("o único endpoint de escrita do Harmonit é o Incluir",
       {"/Veiculo/Incluir"}, escritas_harmonit)
checar("e manda id 0 explícito", True, '"id": 0' in codigo)

# 🚨 A TRAVA NOVA (19/08): o interruptor não pode voltar sem alguém decidir.
# ⚠️ MEDE USO, NÃO A PALAVRA. A docstring do router explica por que o
# interruptor existiu e saiu -- essa memória tem de poder ficar lá. O que não
# pode voltar é a LEITURA da chave e a ação `simulado` na escrita.
checar("ninguém lê a chave do interruptor", False,
       'get_config("placas_registro_ativo"' in codigo)
checar("não há rota de toggle", False, "/config/ativo" in codigo)
checar("nem a ação `simulado` na escrita", False, '"simulado", **comum' in codigo)


# ── os dublês ────────────────────────────────────────────────────────────────
class Espiao:
    """Guarda o que foi 'enviado' para cada sistema, sem enviar nada."""

    def __init__(self):
        self.harmonit, self.weso = [], []


def montar_dubles(espiao, *, existe_no_harmonit=None, existe_na_weso=None,
                  harmonit_erro=None, weso_erro=None, releitura_acha=True):
    """Substitui os cinco pontos de rede de `criar_uma`.

    `existe_*` recebe o texto gravado e devolve o registro, ou None.
    `releitura_acha=False` simula o caso mais traiçoeiro: a WESO responde sem
    erro e a placa NÃO aparece na releitura.
    """
    from fastapi import HTTPException

    async def achar_no_harmonit(texto, forcar=False):
        # Na conferência pós-gravação (`forcar=True`) o registro já existe.
        if forcar and espiao.harmonit:
            return {"id": 555001, "placa": texto, "cliente": "PASTELARIA VELASCO",
                    "clienteId": CLIENTE_HARMONIT}
        return (existe_no_harmonit or (lambda _t: None))(texto)

    async def harmonit_post(path, payload):
        if harmonit_erro:
            raise HTTPException(400, harmonit_erro)
        espiao.harmonit.append((path, payload))
        return {"data": {"id": 555001}}

    async def situacao_das_placas(textos):
        saida = {}
        for t in textos:
            achado = (existe_na_weso or (lambda _t: None))(t)
            saida[t] = ({"existe": True, "veiculo_id": achado["id"],
                         "descricao_atual": achado.get("descricao")}
                        if achado else {"existe": False})
        return saida

    async def weso_post(path, corpo, allow_409=False):
        if weso_erro:
            raise HTTPException(400, weso_erro)
        espiao.weso.append((path, corpo))
        return {}

    async def conferir_na_weso(texto):
        if not espiao.weso or not releitura_acha:
            return None
        return {"id": 777001, "placa": texto}

    return {
        "_achar_no_harmonit": achar_no_harmonit,
        "harmonit_post": harmonit_post,
        "_situacao_das_placas": situacao_das_placas,
        "weso_post": weso_post,
        "_conferir_na_weso": conferir_na_weso,
        "_espelho_aprende": lambda v: None,
    }


async def chamar(lote, *, dubles, **campos):
    padrao = dict(lote=lote, cnpjcpf=CNPJ, perfil="cliente_novo", termo="9999",
                  cliente_harmonit_id=CLIENTE_HARMONIT,
                  cliente_weso_id=CLIENTE_WESO)
    corpo = placas_router.CriarUmaInput(**{**padrao, **campos})
    originais = {n: getattr(placas_router, n) for n in dubles}
    for n, f in dubles.items():
        setattr(placas_router, n, f)
    try:
        return await placas_router.criar_uma(corpo, usuario={"login": "zz_teste"})
    finally:
        for n, f in originais.items():
            setattr(placas_router, n, f)


async def main():
    lote = "zzteste" + uuid.uuid4().hex[:5]
    try:
        print("\n[2] já existe nos dois → informa e NÃO cria")
        e = Espiao()
        d = await chamar(
            lote, placa=JA_EXISTE.replace(" ", ""), descricao="qualquer",
            dubles=montar_dubles(
                e,
                existe_no_harmonit=lambda t: {"id": 900001, "placa": t,
                                              "cliente": "PASTELARIA VELASCO",
                                              "clienteId": CLIENTE_HARMONIT},
                existe_na_weso=lambda t: {"id": 900002, "descricao": "X"}))
        # ⚠️ mandado SEM espaço; o dublê responde pelo texto GRAVADO, com espaço
        checar("o texto gravado ganhou o espaço", JA_EXISTE, d["placa_gravada"])
        checar("a WESO reconhece", "ja_existia", d["weso"]["acao"])
        checar("o Harmonit também", "ja_existia", d["harmonit"]["acao"])
        checar("e diz de quem é no Harmonit", True, bool(d["harmonit"].get("dono")))
        checar("nada foi enviado ao Harmonit", [], e.harmonit)
        checar("nada foi enviado à WESO", [], e.weso)

        print("\n[3] não existe → cria nos dois, na ordem certa")
        e = Espiao()
        d = await chamar(lote, placa=NAO_EXISTE, descricao="VEICULO DE TESTE",
                         dubles=montar_dubles(e))
        checar("Harmonit criado", "criado", d["harmonit"]["acao"])
        checar("WESO criada", "criado", d["weso"]["acao"])
        checar("e a WESO foi conferida relendo", True,
               d["weso"].get("verificado_relendo"))
        checar("o Harmonit recebeu 1 chamada", 1, len(e.harmonit))
        checar("e foi o Incluir", "/Veiculo/Incluir", e.harmonit[0][0])
        checar("com id 0 explícito", 0, e.harmonit[0][1]["id"])
        checar("e o clienteId do corpo", CLIENTE_HARMONIT,
               e.harmonit[0][1]["clienteId"])
        # 🚨 TRAVA 1: só o documento vai para a WESO, nunca os dados do cliente.
        checar("a WESO recebeu só o cnpjcpf do cliente", {"cnpjcpf": CNPJ},
               e.weso[0][1]["equipamento"]["cliente"])

        print("\n[4] a WESO responde sem erro e a placa não aparece na releitura")
        e = Espiao()
        d = await chamar(lote, placa=NAO_EXISTE, descricao="X",
                         dubles=montar_dubles(e, releitura_acha=False))
        # 🚨 ESTE É O CASO QUE O INTERRUPTOR NUNCA DEIXOU TESTAR. `200 OK` não é
        # prova; a prova é reler. Sem releitura achando, a linha é `falhou`.
        checar("não vira `criado`", "falhou", d["weso"]["acao"])
        checar("e o erro diz que a releitura não achou", True,
               "releitura" in (d["weso"]["erro"] or "").lower())

        print("\n[5] o Harmonit falha → PARA, nada vai para a WESO")
        e = Espiao()
        d = await chamar(lote, placa=NAO_EXISTE, descricao="X",
                         dubles=montar_dubles(e, harmonit_erro="500: caiu"))
        checar("Harmonit falhou", "falhou", d["harmonit"]["acao"])
        checar("WESO ignorada", "ignorado", d["weso"]["acao"])
        checar("com o motivo certo", True,
               "harmonit" in d["weso"]["motivo"].lower())
        checar("e a WESO não recebeu nada", [], e.weso)

        print("\n[6] recipiente NÃO vai ao Harmonit, mas vai à WESO")
        e = Espiao()
        d = await chamar(lote, placa=NAO_EXISTE, sufixo="-UPGRADE", termo="9999",
                         dubles=montar_dubles(e))
        checar("Harmonit ignora", "ignorado", d["harmonit"]["acao"])
        checar("com o motivo", True, "bancada" in d["harmonit"]["motivo"])
        checar("mas a WESO cria", "criado", d["weso"]["acao"])
        checar("e a descrição é derivada do termo", "TERMO 9999", d["descricao"])
        checar("o Harmonit não recebeu nada", [], e.harmonit)
        # o recipiente vai marcado como bancada
        checar("e a WESO recebeu o complemento de bancada",
               placas_router.TIPO_BANCADA,
               e.weso[0][1]["equipamento"]["complemento"]["tipoEqp"])

        print("\n[7] recipiente de upgrade sem termo é recusado nos DOIS")
        e = Espiao()
        d = await chamar(lote, placa=NAO_EXISTE, sufixo="-UPGRADE", termo=None,
                         dubles=montar_dubles(e))
        checar("Harmonit ignorado", "ignorado", d["harmonit"]["acao"])
        checar("WESO ignorada", "ignorado", d["weso"]["acao"])
        checar("e o motivo fala do termo", True,
               "termo" in (d["weso"]["erro"] or "").lower())
        checar("nada foi enviado", ([], []), (e.harmonit, e.weso))

        print("\n[8] sem cliente no Harmonit, a WESO segue sozinha")
        e = Espiao()
        d = await chamar(lote, placa=NAO_EXISTE, descricao="X",
                         cliente_harmonit_id=None, dubles=montar_dubles(e))
        checar("Harmonit ignorado", "ignorado", d["harmonit"]["acao"])
        checar("mas a WESO não para", "criado", d["weso"]["acao"])

        print("\n[9] tudo foi para o registro")
        linhas = await storage.listar_cadastro_placas(lote=lote,
                                                      incluir_simulado=True)
        # 7 tentativas × 2 sistemas.
        checar("duas linhas por tentativa", 14, len(linhas))
        checar("os dois sistemas aparecem", {"harmonit", "weso"},
               {l["sistema"] for l in linhas})
        # ⚠️ o caso [7] manda `termo: None` DE PROPÓSITO, para provar que
        # recipiente de upgrade sem termo é recusado. Exigir `{"9999"}` aqui
        # reprovaria justamente o cenário que o teste quer exercitar.
        checar("o termo viajou junto onde havia termo", {None, "9999"},
               {l["termo"] for l in linhas})
        # 🚨 nenhuma linha `simulado`: essa ação morreu com o interruptor.
        checar("nenhuma linha simulada", set(),
               {l["acao"] for l in linhas} & {"simulado"})
    finally:
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
