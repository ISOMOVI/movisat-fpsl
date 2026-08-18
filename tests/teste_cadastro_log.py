"""O registro do cadastro de placas — passo 1 do cadastro por termo.

🚨 POR QUE ELE VEM ANTES DA ESCRITA. O cadastro grava em DOIS sistemas externos
e o resultado é invisível: veículo errado some no meio de 9.107 no Harmonit e
1.962 na WESO. Sem registro, auditar exigiria comparar as bases inteiras. E,
durante o desenvolvimento, é com ele que a própria escrita será verificada —
mesmo raciocínio do expurgo da oficina, onde os testes vieram antes da remoção.

O que este arquivo prende:
  1. uma linha por (placa, sistema) — a mesma placa produz DUAS tentativas, e
     elas podem terminar diferente;
  2. o `lote` amarra a rodada, senão o histórico é lista solta;
  3. ação desconhecida não derruba a gravação — registro que se recusa a gravar
     perde justamente o caso inesperado, que é o que interessa;
  4. simulação é registrada mas fica FORA do padrão da listagem;
  5. o corte é pelo lado certo (mais recentes), não pelo mais antigo.

Roda na VPS: venv/bin/python tests/teste_cadastro_log.py
Não fala com Harmonit nem WESO. Grava e apaga o próprio lote.
"""
import asyncio
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def limpar(*lotes):
    # ⚠️ A tabela nasce na PRIMEIRA gravação (init preguiçoso), e a limpeza roda
    # antes dela. Sem este init, o teste morre em `no such table` na máquina
    # onde a tabela ainda não existe -- que é justamente a primeira.
    storage._init_cadastro_placas_log()
    with sqlite3.connect(storage.DB_PATH) as conn:
        for lote in lotes:
            conn.execute("DELETE FROM cadastro_placas_log WHERE lote = ?", (lote,))


async def main():
    lote_a = "zzteste_" + storage.novo_lote()
    lote_b = "zzteste_" + storage.novo_lote()
    limpar(lote_a, lote_b)

    try:
        print("\n[1] o lote identifica a rodada, e o id volta")
        checar("dois lotes são diferentes", True, lote_a != lote_b)

        rid = await storage.registrar_cadastro_placa(
            lote_a, "harmonit", "criado", termo="8800", perfil="upgrade",
            cnpjcpf="WQ0P6GLD000108", cliente_harmonit_id=998063,
            placa_digitada="TST0Z99", placa_gravada="TST 0Z99",
            descricao="VEICULO DE TESTE", id_externo=111111, usuario="admin")
        checar("gravou e devolveu um id", True, isinstance(rid, int) and rid > 0)

        print("\n[2] a MESMA placa em dois sistemas = duas linhas")
        # 🚨 É o caso que mais importa: criada no Harmonit e recusada na WESO
        # deixa os dois fora de sincronia, e é isso que o registro tem de contar.
        await storage.registrar_cadastro_placa(
            lote_a, "weso", "falhou", termo="8800", perfil="upgrade",
            placa_digitada="TST0Z99", placa_gravada="TST 0Z99",
            erro="a WESO recusou: 502")

        linhas = await storage.listar_cadastro_placas(lote=lote_a)
        checar("duas linhas para uma placa", 2, len(linhas))
        checar("uma por sistema", {"harmonit", "weso"},
               {l["sistema"] for l in linhas})
        porsis = {l["sistema"]: l for l in linhas}
        checar("o Harmonit criou", "criado", porsis["harmonit"]["acao"])
        checar("e guardou o id de lá", 111111, porsis["harmonit"]["id_externo"])
        checar("a WESO falhou", "falhou", porsis["weso"]["acao"])
        checar("com o motivo", True, "502" in (porsis["weso"]["erro"] or ""))

        print("\n[3] ação desconhecida GRAVA, não derruba")
        # ⚠️ Registro que se recusa a gravar perde o caso inesperado -- que é
        # exatamente o que se quer descobrir depois.
        await storage.registrar_cadastro_placa(
            lote_b, "weso", "explodiu_de_um_jeito_novo",
            placa_gravada="TST 0Y88", erro="original")
        l = (await storage.listar_cadastro_placas(lote=lote_b))[0]
        checar("virou 'desconhecido'", "desconhecido", l["acao"])
        checar("preservando o valor original no erro", True,
               "explodiu_de_um_jeito_novo" in (l["erro"] or ""))
        checar("e o erro original não se perdeu", True,
               "original" in (l["erro"] or ""))

        print("\n[4] simulação fica FORA da listagem padrão")
        await storage.registrar_cadastro_placa(
            lote_b, "weso", "simulado", placa_gravada="TST 0X77")
        sem = await storage.listar_cadastro_placas(lote=lote_b)
        com = await storage.listar_cadastro_placas(lote=lote_b, incluir_simulado=True)
        checar("padrão não traz simulado", 1, len(sem))
        checar("mas ela está gravada", 2, len(com))

        print("\n[5] o resumo por lote — o que a tela mostra primeiro")
        lotes = {x["lote"]: x for x in await storage.listar_lotes_cadastro()}
        checar("o lote A aparece", True, lote_a in lotes)
        a = lotes[lote_a]
        checar("conta 1 placa distinta, não 2 linhas", 1, a["placas"])
        checar("1 criado", 1, a["criados"])
        checar("1 falha", 1, a["falhas"])
        checar("e leva o termo junto", "8800", a["termo"])

        print("\n[6] o corte é pelo lado certo")
        # 🚨 `ORDER BY id ASC LIMIT n` devolveria as MAIS ANTIGAS, e ninguém
        # percebe enquanto a tabela é pequena.
        for i in range(3):
            await storage.registrar_cadastro_placa(
                lote_a, "weso", "criado", placa_gravada=f"TST 0W{i}{i}")
        recentes = await storage.listar_cadastro_placas(limite=2, lote=lote_a)
        checar("limite respeitado", 2, len(recentes))
        checar("e traz as mais RECENTES", ["TST 0W22", "TST 0W11"],
               [r["placa_gravada"] for r in recentes])
    finally:
        limpar(lote_a, lote_b)
        checar("o lote de teste foi removido", 0,
               len(await storage.listar_cadastro_placas(lote=lote_a,
                                                        incluir_simulado=True)))


asyncio.run(main())

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
