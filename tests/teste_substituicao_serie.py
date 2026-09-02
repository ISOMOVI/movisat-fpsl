"""Substituição: a série da INSTALAÇÃO é a do equipamento RETIRADO. 2026-09-02.

O que este arquivo PRENDE, e que reprova se alguém desfizer:

  1. **A instalação leva a série da placa que SAI.** Decisão do usuário em
     02/09: *"a OS de instalação sempre terá o mesmo ID que a da correspondente
     da retirada"*. O equipamento é O MESMO e só muda de veículo; quando a OS é
     gerada ele ainda está vinculado ao veículo antigo, então ler da placa de
     entrada devolve vazio.

  2. **O modelo acompanha a série.** Série de uma placa com modelo de outra
     produz `007933914 (modelo nao localizado)` -- o defeito que o comentário
     antigo tentava evitar lendo tudo da placa ERRADA.

  3. **Placa e veículo continuam vindo da ENTRADA.** Quem recebe é o veículo
     novo; só o equipamento vem do antigo. Trocar isso mandaria o técnico ao
     veículo errado.

🚨 CUSTOU UMA CORREÇÃO À MÃO. Termo 8867 (WGM), OS 16829/16830 em 02/09: a
instalação saiu com `série não localizada` e a Erika preencheu manualmente.
Nenhum teste cobria essa descrição -- por isso este arquivo existe.

Roda na VPS: venv/bin/python tests/teste_substituicao_serie.py

🚨 NÃO FAZ REDE. Toda leitura de WESO e Harmonit entra por dublê.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import teste_operacoes_f4 as base  # noqa: E402
from fpsl_weso.painel import operacoes_os as oos  # noqa: E402

ok, falhas = 0, []


def checar(nome, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print("  ok   %s" % nome)
    else:
        falhas.append(nome)
        print("  FALHA %s %s" % (nome, extra))


async def principal():
    base.instalar_dubles(modelo_na_weso="Suntech ST4315U")

    # O caso real do termo 8867: o equipamento esta na placa que SAI. A placa
    # que ENTRA nasceu agora e nao tem nada -- e por isso vai receber.
    seriais = {oos.eqp.chave("SYA 8C88"): "0840133573"}

    body = base.corpo(
        "substituicao",
        [base.placa("SYA 8C88", veic="JEEP/COMPASS, 2023/2024, BRANCO, FLEX",
                    placa_entrada="UVS 8I88", veiculo_entrada="BYD SEALION 7")],
        [base.item("RASTREADOR", "1", "480,00", "COMODATO")],
        valor_substituicao=299.90,
    )
    ops, _r, _p, _d = await base.montar(body, seriais=seriais)
    operacionais = [o for o in ops if not o.get("eh_financeira")]
    ret = [o for o in operacionais if o["rotulo"] == "Retirada"][0]
    inst = [o for o in operacionais if o["rotulo"] == "Instalação"][0]

    print("  retirada  :", ret["descricao"])
    print("  instalação:", inst["descricao"])

    checar("a retirada leva a série do equipamento",
           "0840133573" in ret["descricao"], ret["descricao"])
    checar("A INSTALAÇÃO LEVA A MESMA SÉRIE DA RETIRADA",
           "0840133573" in inst["descricao"], inst["descricao"])
    checar("e NÃO sai o marcador de série não localizada",
           oos.eqp.MARCADOR_NAO_LOCALIZADO not in inst["descricao"],
           inst["descricao"])
    checar("o modelo acompanha a série",
           "Suntech ST4315U" in inst["descricao"], inst["descricao"])
    checar("a placa da instalação é a que ENTRA",
           inst["placa"] == "UVS 8I88", inst["placa"])
    checar("o veículo da instalação é o que ENTRA",
           inst["veiculo"] == "BYD SEALION 7", inst["veiculo"])
    checar("a placa da retirada é a que SAI",
           ret["placa"] == "SYA 8C88", ret["placa"])
    checar("as duas OS carregam os mesmos materiais",
           ret.get("materiais") == inst.get("materiais"))

    # ── sem conseguir ler a placa que sai, o marcador é honesto ──────────────
    #
    # 🚨 "não localizada" significa NÃO CONSEGUI LER, e é diferente de "a
    # preencher". Se a WESO não devolver o equipamento do veículo antigo, a
    # instalação tem de dizer isso -- e não inventar.
    ops2, _r, _p, _d = await base.montar(body, seriais={})
    inst2 = [o for o in ops2 if o.get("rotulo") == "Instalação"][0]
    checar("sem leitura da placa que sai, a instalação assume o marcador",
           oos.eqp.MARCADOR_NAO_LOCALIZADO in inst2["descricao"],
           inst2["descricao"])


asyncio.run(principal())
print()
print("%d ok, %d falha(s)" % (ok, len(falhas)))
if falhas:
    for f in falhas:
        print("  -", f)
    sys.exit(1)
