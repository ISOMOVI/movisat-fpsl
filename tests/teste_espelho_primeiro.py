"""Espelho primeiro, rede só quando ele não acha — e nunca na releitura. 24/08.

🚨 O QUE ISTO PRENDE, E POR QUE IMPORTA. `_existe_no_harmonit` baixava a base
INTEIRA do Harmonit (9.118 registros, ~1,9 s) **duas vezes por placa**: uma
antes de gravar, outra para reler. Num lote de 11 placas de manutenção -- em
que todas as placas JÁ existem -- eram 11 leituras completas, ~21 s, para
descobrir 11 vezes o que o cache diário já sabia.

O desenho aprovado tem três camadas:

  1. o espelho responde primeiro;
  2. rede só quando o espelho NÃO acha (pode ter nascido depois das 04:50);
  3. **a releitura depois de gravar continua sempre ao vivo.**

⚠️ A CAMADA 3 É A QUE NÃO PODE CAIR, e é a mais fácil de quebrar sem querer:
basta alguém trocar `_no_harmonit_ao_vivo` por `_existe_no_harmonit` numa
refatoração. O espelho é das 04:50 -- ele diria "não está lá" para TODA placa
recém-criada, e a rodada inteira sairia como falha. Por isso o teste mede a
LIGAÇÃO: com a rede desligada, a releitura tem de estourar, não responder.

🚨 NÃO FAZ REDE: o `harmonit_get` é substituído por um dublê que conta chamadas.

Roda na VPS: venv/bin/python tests/teste_espelho_primeiro.py
"""
import asyncio
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel.routers import operacoes_router as opr  # noqa: E402

ok, falhas = 0, []


def checar(nome, cond, detalhe=""):
    global ok
    if cond:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# ── dublês ──────────────────────────────────────────────────────────────────
CHAMADAS = []


async def _harmonit_de_mentira(rota, *a, **k):
    CHAMADAS.append(rota)
    return [{"id": 777, "placa": "NOVA 1A11", "veiculo": "recem-nascida",
             "clienteId": 42, "cliente": "CLIENTE NOVO"}]


def espelho_de_mentira(caminho):
    c = sqlite3.connect(caminho)
    c.execute("CREATE TABLE veiculos (id INTEGER, placa TEXT, chave_placa TEXT,"
              " veiculo TEXT, cliente_id INTEGER, cliente TEXT)")
    c.execute("INSERT INTO veiculos VALUES (?,?,?,?,?,?)",
              (108711, "TST 0E55", "TST0E55", "FIAT UNO", 998063, "VELASCO"))
    c.execute("CREATE TABLE meta (chave TEXT, valor TEXT)")
    c.commit()
    c.close()


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        caminho = pathlib.Path(tmp) / "harmonit.db"
        espelho_de_mentira(caminho)
        opr.CACHE_HARMONIT = caminho
        opr.harmonit_get = _harmonit_de_mentira

        print("== camada 1: o espelho responde, e a rede fica quieta ==")
        CHAMADAS.clear()
        r = await opr._existe_no_harmonit("TST 0E55")
        checar("acha a placa que está no espelho", bool(r), str(r))
        checar("e NÃO foi à rede", CHAMADAS == [], str(CHAMADAS))
        # 🚨 O FORMATO. O cache grava `cliente_id`; quem chama lê `clienteId`.
        # Sem a tradução o dono sairia nulo na tela e nada acusaria.
        checar("devolve o id do veículo", r and r.get("id") == 108711, str(r))
        checar("e o dono no formato da resposta ao vivo (`clienteId`)",
               r and r.get("clienteId") == 998063, str(r))
        checar("com o nome do cliente junto",
               r and r.get("cliente") == "VELASCO", str(r))

        print()
        print("== e a placa com espaço/caixa diferente casa igual ==")
        CHAMADAS.clear()
        r2 = await opr._existe_no_harmonit("tst0e55")
        checar("mesma placa, outra grafia, mesmo resultado",
               r2 and r2.get("id") == 108711, str(r2))
        checar("e continua sem rede", CHAMADAS == [], str(CHAMADAS))

        print()
        print("== camada 2: o que o espelho NÃO acha vai ao vivo ==")
        CHAMADAS.clear()
        r3 = await opr._existe_no_harmonit("NOVA 1A11")
        checar("achou pela rede", r3 and r3.get("id") == 777, str(r3))
        checar("e foi à rede UMA vez", len(CHAMADAS) == 1, str(CHAMADAS))

        print()
        print("== camada 3: a releitura NUNCA passa pelo espelho ==")
        # 🚨 A PROVA É A LIGAÇÃO, NÃO O NOME. Ponho no espelho justamente a
        # placa que a rede diz existir: se a releitura consultasse o espelho,
        # ela responderia sem chamar a rede -- e o contador denuncia.
        with sqlite3.connect(caminho) as c:
            c.execute("INSERT INTO veiculos VALUES (?,?,?,?,?,?)",
                      (777, "NOVA 1A11", "NOVA1A11", "recem", 42, "CLIENTE NOVO"))
        CHAMADAS.clear()
        r4 = await opr._no_harmonit_ao_vivo("NOVA 1A11")
        checar("a releitura devolve a placa", bool(r4), str(r4))
        checar("e foi à rede mesmo com ela NO espelho",
               len(CHAMADAS) == 1,
               "se não foi, alguém trocou a releitura pela versão com espelho")

        print()
        print("== sem espelho, tudo cai na rede — e nada quebra ==")
        opr.CACHE_HARMONIT = pathlib.Path(tmp) / "nao_existe.db"
        CHAMADAS.clear()
        r5 = await opr._existe_no_harmonit("NOVA 1A11")
        checar("continua respondendo", bool(r5), str(r5))
        checar("indo à rede", len(CHAMADAS) == 1, str(CHAMADAS))

    print()
    print(f"== {ok} verificações OK, {len(falhas)} falha(s) ==")
    return 1 if falhas else 0


if __name__ == "__main__":
    codigo = asyncio.run(main())
    if codigo:
        for f in falhas:
            print("   -", f)
    sys.exit(codigo)
