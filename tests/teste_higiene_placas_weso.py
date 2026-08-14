"""Etapa 4 do docs/fpsl/21_Plano_Higiene_Placas.md — impede a reincidencia.

Em 2026-07-29 a base da WESO tinha 110 de 1.962 placas com espaco nas pontas,
espaco duplo ou minuscula. `/Veiculos/Consultar?placa=` compara por igualdade
EXATA, entao esses registros ficavam INVISIVEIS para consulta por placa --
devolvia lista vazia em vez de erro. Falha silenciosa: o sistema concluia
"placa nao existe" para veiculo que existia (foi assim que a TTX 0H91 do termo
8788 sumiu).

Os 110 foram normalizados no mesmo dia. Este teste existe porque JA tinha
acontecido antes: o projeto tem `corrigir_placas_espaco.py` de 27/07, o que
prova que a base ja fora limpa uma vez e sujou de novo. A WESO tambem recebe
cadastro por fora do FPSL, entao sem uma trava automatica isso volta.

TESTE DE INTEGRACAO: bate na WESO de verdade (~2,3s para 1.962 registros).
Somente LEITURA -- nao escreve nada.

Roda: venv/bin/python tests/teste_higiene_placas_weso.py
"""
import asyncio
import pathlib
import re
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import placas                                        # noqa: E402
from fpsl_weso.client import start_client, stop_client, weso_get    # noqa: E402
from fpsl_weso.weso_lookup import buscar_veiculo                    # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
    else:
        falhas.append(f"{nome}: esperado {esperado!r}, obtido {obtido!r}")


# Colisoes conhecidas, deixadas de proposito: aparar o espaco de duas placas
# que colidem transformaria duplicata escondida em conflito ativo. Saem junto
# da decisao 3 do usuario (duplicadas sem RD). Se a lista mudar, o teste avisa.
COLISOES_ACEITAS = {"MVEL1"}


# 🚨 A REGRA DE MINUSCULA SO VALE PARA OS NOSSOS PADROES (decisao do usuario,
# 2026-08-14). A base tem identificadores que nao sao placa e nunca vao ser --
# `Movel 1`, `TAG identificacao` -- e cobrar caixa alta neles e cobrar uma
# regra que nao existe. Reprovar por causa deles treinava a ignorar a suite.
#
# ⚠️ O ESPACO CONTINUA VALENDO PARA TODOS. Espaco e sempre defeito: foi ele que
# tornou `' TTX 0H91'` invisivel para `/Veiculos/Consultar?placa=` no termo
# 8788, que e o motivo desta suite existir (doc 21, 29/07). Minuscula e
# convencao; espaco e falha silenciosa.
# 🚨 A REGRA DE PLACA MORA EM `fpsl_weso/placas.py`, E SO LA. `eh_convencional`
# ja trata o marcador `(RD)` em qualquer posicao e ja sabe que `RDM`/`RDQ`/`RDS`
# sao prefixos legitimos, nao redundancia. Escrever um regex proprio aqui
# criaria uma segunda definicao de "o que e placa" -- e as duas divergiriam.
# Medido em 14/08: um regex proprio deixava 47 placas `(RD) EDF 5724` fora do
# escopo, ou seja, sem a protecao que esta suite existe para dar.
PADROES_EXTRAS = (
    re.compile(r"^CHASSI:\s*[A-Z0-9]{17}$", re.I),           # chassi rotulado
    re.compile(r"^.+\s*-\s*(UPGRADE|MANUT)$", re.I),         # recipiente
)


def e_padrao_nosso(placa: str) -> bool:
    """A grafia deste registro e cobrada pela nossa regra?

    Sao tres padroes: placa convencional (com ou sem `(RD)`), chassi rotulado e
    placa-recipiente. Identificador que nao e nenhum dos tres -- `Movel 1`,
    `TAG identificacao`, `OBD 4G - 17`, `ISCA DE CARGA` -- nao e placa e nunca
    vai ser: cobrar caixa alta neles seria cobrar regra que nao existe
    (decisao do usuario, 2026-08-14).
    """
    p = " ".join(str(placa or "").split())
    if not p:
        return False
    if placas.eh_convencional(p):
        return True
    return any(rx.match(p) for rx in PADROES_EXTRAS)


async def main():
    await start_client()
    try:
        r = await weso_get("/Veiculos/Consultar", {})
        base = (r.get("veiculos") if isinstance(r, dict) else r) or []
        print(f"[1] base da WESO: {len(base)} veiculos")
        checar("base nao veio vazia", True, len(base) > 100)

        def sujas(teste, so_padroes_nossos=False):
            fora = []
            for v in base:
                p = str(v.get("placa") or "")
                if not p or not teste(p):
                    continue
                if placas.normalizar(p) in COLISOES_ACEITAS:
                    continue
                if so_padroes_nossos and not e_padrao_nosso(p):
                    continue
                fora.append((v.get("id"), p))
            return fora

        print("\n[2] higiene da grafia")
        for rotulo, teste, so_nossos in (
            ("espaco a esquerda", lambda p: p != p.lstrip(), False),
            ("espaco a direita",  lambda p: p != p.rstrip(), False),
            ("espaco duplo",      lambda p: "  " in p,       False),
            # minuscula so nos nossos padroes -- ver PADROES_NOSSOS acima
            ("letra minuscula",   lambda p: p != p.upper(),  True),
        ):
            fora = sujas(teste, so_nossos)
            checar(rotulo, 0, len(fora))
            if fora:
                for vid, p in fora[:8]:
                    print(f"       id={vid} {p!r}")

        fora_do_escopo = [v.get("placa") for v in base
                          if v.get("placa") and not e_padrao_nosso(str(v["placa"]))]
        print(f"       ({len(fora_do_escopo)} identificadores fora dos nossos "
              f"padroes, nao cobrados aqui)")

        print("\n[2b] o filtro de padrao reconhece o que tem de reconhecer")
        for p, esperado in (("ABC 1234", True), ("ABC1D23", True),
                            ("abc 1234", True),
                            # 🚨 redundancia: continua sendo placa nossa
                            ("(RD) EDF 5724", True), ("EDF 5724 (RD)", True),
                            ("CHASSI: HCCZTL80HNCJ51769", True),
                            ("GJN8689-MANUT", True), ("OOM4131-UPGRADE", True),
                            ("Movel 1", False), ("TAG identificacao", False),
                            ("OBD 4G - 17", False), ("ISCA DE CARGA", False),
                            ("COD: 04-01", False), ("", False)):
            checar(f"padrao nosso? {p!r}", esperado, e_padrao_nosso(p))

        print("\n[3] colisao nova (placa normalizada repetida)")
        grupos = defaultdict(list)
        for v in base:
            k = placas.normalizar(v.get("placa"))
            if k:
                grupos[k].append(v.get("id"))
        novas = {k: ids for k, ids in grupos.items()
                 if len(ids) > 1 and k not in COLISOES_ACEITAS}
        # As 3 duplicatas sem RD (decisao 3) e os placeholders de termo ja
        # existiam em 29/07 -- o teste falha so se APARECER colisao nova.
        # GFI3G42/SVS6J23/EBU1968: duplicatas sem RD, decisao 3 do usuario.
        # TERMO8396: placeholder de placa a definir, 4 registros.
        # OBD2 e OBD3: identificador nao-convencional reusado. O OBD3 e um
        #   caso especial -- na WESO sao 'OBD 3' e 'OBD 3*', DIFERENTES; quem
        #   os funde e a nossa placas.normalizar(), que descarta o '*'. Como
        #   weso_lookup usa essa mesma chave, a ambiguidade e REAL do nosso
        #   lado: buscar 'OBD 3' pode devolver qualquer um dos dois. Fica
        #   catalogado, nao silenciado.
        conhecidas = {"GFI3G42", "SVS6J23", "EBU1968", "TERMO8396", "OBD2", "OBD3"}
        inesperadas = {k: v for k, v in novas.items() if k not in conhecidas}
        checar("nenhuma colisao NOVA", {}, inesperadas)
        print(f"       colisoes conhecidas: {len(novas) - len(inesperadas)} | novas: {len(inesperadas)}")

        print("\n[4] leitura tolerante (etapa 2) continua funcionando")
        alvo = next((v for v in base
                     if placas.eh_convencional(v.get("placa")) and v.get("id")), None)
        if not alvo:
            falhas.append("nao achei placa convencional para testar a busca")
        else:
            limpa = str(alvo["placa"]).strip()
            for variante, rotulo in (
                (limpa,                    "grafia limpa"),
                (f"  {limpa}  ",           "com espaco nas pontas"),
                (limpa.lower(),            "minuscula"),
                (limpa.replace(" ", ""),   "sem espaco"),
            ):
                achado = await buscar_veiculo(variante)
                checar(f"acha {rotulo}", alvo["id"], achado.get("id") if achado else None)

        print("\n[5] placa inexistente devolve None, nao explode")
        checar("inexistente -> None", None, await buscar_veiculo("ZZZ 9Z99"))
    finally:
        await stop_client()


asyncio.run(main())

print("\n" + "=" * 52)
if falhas:
    print(f"{ok} passaram, {len(falhas)} FALHARAM")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print(f"{ok} passaram, 0 falharam")
