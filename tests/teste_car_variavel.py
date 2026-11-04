"""A parte variável do contas a receber (`CAR_1.1`, bloco G2). 2026-11-03.

🚨 MÓDULO PURO, TESTE PURO: sem banco e sem rede. Os casos vêm todos de dado
MEDIDO em 03/11 na produção -- as 3 OS da fila (16846, 16896, 16899), a OS sem
cliente nesta base, e as já faturadas que o Harmonit lançou.

Roda na VPS:  venv/bin/python tests/teste_car_variavel.py
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.painel import car_variavel as cv                      # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n[1] o valor do Harmonit entra em convenção BRASILEIRA")
# 🚨 O DEFEITO DE DINHEIRO DE 30/10, travado aqui também: o item da OS traz
# `valorTotal` como float (`120.0`), e `_centavos` lê ponto como separador de
# MILHAR. Guardar "120.0" faria R$ 120,00 virar R$ 12.000,00 na soma.
checar("float vira texto com virgula", "120,00", cv.valor_texto(120.0))
checar("centavos do Harmonit atravessam", "200,53", cv.valor_texto(200.53))
checar("texto brasileiro passa intacto", "1.234,56", cv.valor_texto("1.234,56"))
checar("vazio e None, nao '0,00'", None, cv.valor_texto(None))
checar("string vazia tambem", None, cv.valor_texto(""))
# ⚠️ `True` é `int` em Python, e `True * 1.0` daria "1,00": booleano não é
# dinheiro, e deixar passar poria R$ 1,00 numa fatura por causa de um `true`.
checar("booleano nao e dinheiro", None, cv.valor_texto(True))
checar("zero e zero, e isso e um valor", "0,00", cv.valor_texto(0))

print("\n[2] a competência sai da data de PREVISÃO, e nula não vira o mês de hoje")
checar("16/09/2026 14:45:00", "2026-09",
       cv.competencia_da_os("16/09/2026 14:45:00"))
checar("08/09/2026 09:41:00", "2026-09",
       cv.competencia_da_os("08/09/2026 09:41:00"))
checar("so a data, sem hora", "2026-01", cv.competencia_da_os("31/01/2026"))
# 🚨 `None` NUNCA VIRA O MÊS CORRENTE: OS sem data não pertence a competência
# nenhuma, e chutar o mês de hoje a faria aparecer numa fatura por acidente.
checar("data vazia e None", None, cv.competencia_da_os(None))
checar("texto que nao e data e None", None, cv.competencia_da_os("sem data"))
checar("mes 13 e recusado", None, cv.competencia_da_os("01/13/2026"))
checar("formato ISO nao e o do Harmonit", None,
       cv.competencia_da_os("2026-09-16"))

print("\n[3] `cobrar` é o que decide o item -- e o de valor zero FICA, marcado")
itens = cv.itens_a_cobrar([
    {"descricao": "INSTALAÇÃO", "cobrar": True, "valor": 120.0, "valorTotal": 120.0},
    {"descricao": "PAGAMENTO DE TÉCNICO", "cobrar": False, "valor": 80.0,
     "valorTotal": 80.0},
    {"descricao": "ENTREGA OS", "cobrar": True, "valor": 0.0, "valorTotal": 0.0},
])
checar("so os `cobrar` entram", 2, len(itens))
checar("e o de maior valor vem primeiro", "INSTALAÇÃO", itens[0]["descricao"])
# 🚨 PAGAMENTO DE TÉCNICO é o item que prova que `cobrar` é COBRAR DO CLIENTE,
# não pagar o técnico: medido em 30/10, ele vem `cobrar = false` em 70 de 71.
checar("pagamento de tecnico NAO entra", False,
       any(i["descricao"] == "PAGAMENTO DE TÉCNICO" for i in itens))
checar("o de valor zero continua na lista", True,
       any(i["descricao"] == "ENTREGA OS" for i in itens))
checar("e nao muda a soma", "120,00",
       cv.somar_textos([i["valor_total"] for i in itens]))
checar("lista vazia da lista vazia", [], cv.itens_a_cobrar([]))
checar("None da lista vazia", [], cv.itens_a_cobrar(None))
# Item que não é dicionário (JSON torto) não derruba a leitura.
checar("item torto e ignorado, nao explode", 0,
       len(cv.itens_a_cobrar(["nao sou item", 42, None])))

print("\n[4] somar: nulo nunca vira zero")
checar("soma dois", "240,00", cv.somar_textos(["120,00", "120,00"]))
checar("nada somavel e None", None, cv.somar_textos([None, None]))
checar("lista vazia e None", None, cv.somar_textos([]))
checar("zero explicito soma zero", "0,00", cv.somar_textos(["0,00"]))
# 🚨 ACIMA DE MIL, A CASA NÃO PÕE SEPARADOR DE MILHAR -- medido aqui, não
# suposto: `car_prefatura.somar_textos` devolve "1080,00" pela mesma fórmula,
# desde 28/10. Meu teste esperava "1.080,00" e estava errado; a saída é que é a
# convenção, e as duas somas da casa têm de concordar. 🟡 Se a leitura na tela
# incomodar, trocar é UMA linha nos dois módulos -- e é decisão dele, porque
# muda o número em todas as telas do dinheiro.
checar("acima de mil, sem separador (como o car_prefatura)", "1080,00",
       cv.somar_textos(["180,00", "300,00", "600,00"]))

print("\n[5] a classificação: a ORDEM DOS CORTES é a régua dele")
base = {"numero_os": 16896, "os_id": 846000, "situacao_id": 15746,
        "status_str": "Finalizado", "cliente_id": 886302,
        "cnpj": "07098192000160", "cliente": "zz MOTO HELP",
        "data_previsao": "16/09/2026 14:45:00",
        "materiais": [{"descricao": "INSTALAÇÃO", "cobrar": True,
                       "valor": 120.0, "valorTotal": 120.0}]}

d = cv.classificar(dict(base))
checar("finalizada, com item a cobrar, nao faturada: A GERAR", cv.A_GERAR, d["estado"])
checar("total", "120,00", d["total"])
checar("competencia da previsao", "2026-09", d["competencia"])
checar("cliente conhecido", True, d["cliente_conhecido"])
checar("todo estado tem causa escrita", True, bool(d["porque"]))

# 🚨 JÁ FATURADA GANHA DE TUDO -- inclusive de "finalizada e com item". O risco
# de dois boletos é o maior da virada, e por isso ele é o primeiro corte.
d = cv.classificar(dict(base), faturadas={16896})
checar("ja faturada no Harmonit sai da fila", cv.JA_FATURADA, d["estado"])
checar("mas o total continua visivel", "120,00", d["total"])

d = cv.classificar({**base, "status_str": "Iniciada"})
checar("nao finalizada sai da fila", cv.NAO_FINALIZADA, d["estado"])

d = cv.classificar({**base, "materiais": [
    {"descricao": "PAGAMENTO DE TÉCNICO", "cobrar": False, "valorTotal": 80.0}]})
checar("sem item a cobrar sai da fila", cv.SEM_ITEM_A_COBRAR, d["estado"])
checar("e o total e None, nao 0,00", None, d["total"])

# A OS 16846 real: três itens a cobrar, R$ 1.080,00, e o cliente 1036572 que
# NÃO está em `clientes`. Ela não é escondida -- é o caso do bloco G5.
d = cv.classificar({**base, "numero_os": 16846, "cliente_id": 1036572,
                    "cnpj": None, "cliente": None,
                    "data_previsao": "08/09/2026 09:41:00",
                    "materiais": [
                        {"descricao": "CARTAO RFID", "cobrar": True, "valorTotal": 180.0},
                        {"descricao": "ADESÃO", "cobrar": True, "valorTotal": 300.0},
                        {"descricao": "INSTALAÇÃO", "cobrar": True, "valorTotal": 600.0}]})
checar("a 16846 esta a gerar", cv.A_GERAR, d["estado"])
checar("com R$ 1080,00", "1080,00", d["total"])
checar("mas o cliente NAO e conhecido", False, d["cliente_conhecido"])

print("\n[6] a fila: agrupa por CLIENTE, e o sem cliente não entra na soma")
linhas = [
    base,
    {**base, "numero_os": 16899, "data_previsao": "16/09/2026 15:38:00"},
    {**base, "numero_os": 16846, "cliente_id": 1036572, "cnpj": None,
     "cliente": None, "data_previsao": "08/09/2026 09:41:00",
     "materiais": [{"descricao": "INSTALAÇÃO", "cobrar": True, "valorTotal": 1080.0}]},
    # Já faturada: fica de fora, com motivo.
    {**base, "numero_os": 16500},
    # De outra competência: não é "fora", é outro mês.
    {**base, "numero_os": 17000, "data_previsao": "02/10/2026 10:00:00"},
]
f = cv.fila(linhas, "2026-09", faturadas={16500})
checar("3 OS a gerar na competencia", 3, f["totais"]["os_a_gerar"])
checar("1 cliente com documento", 1, f["totais"]["clientes"])
# 🚨 R$ 240,00 e não R$ 1.320,00: o dinheiro da OS sem cliente existe, mas não
# pode virar documento. Somar junto inflaria o lote em R$ 1.080,00.
checar("o total do que VIRA documento", "240,00", f["totais"]["total"])
checar("e o sem cliente aparece à parte", "1080,00", f["totais"]["sem_cliente"])
checar("1 OS sem cliente", 1, f["totais"]["os_sem_cliente"])
checar("a ja faturada ficou fora", 1, len(f["fora"]))
checar("com o estado que a barrou", cv.JA_FATURADA, f["fora"][0]["estado"])
checar("a de outra competencia NAO e 'fora'", False,
       any(o["numero_os"] == 17000 for o in f["fora"]))
checar("a regra fica declarada na resposta", 15746, f["regra"]["situacao_id"])
checar("e o limite da data tambem", True, "PREVIS" in f["regra"]["data"].upper())

f = cv.fila(linhas, None, faturadas={16500})
checar("sem competencia, traz os dois meses", 4, f["totais"]["os_a_gerar"])

f = cv.fila([], "2026-09")
checar("fila vazia nao explode", 0, f["totais"]["os_a_gerar"])
checar("e o total e None, nao 0,00", None, f["totais"]["total"])

print("\n[7] a trava do módulo puro: nada de I/O aqui dentro")
# 🚨 A MESMA TRAVA DO `car_motor` e do `car_faturado`: se um `import sqlite3` ou
# um `harmonit_get` entrar aqui, a régua deixa de ser testável sem banco -- e é
# testável sem banco que faz este arquivo existir.
fonte = (RAIZ / "fpsl_weso" / "painel" / "car_variavel.py").read_text("utf-8")
for proibido in ("import sqlite3", "harmonit_get", "storage", "conn.execute",
                 "json.loads", "open("):
    checar(f"o fonte nao tem `{proibido}`", False, proibido in fonte)

print(f"\n{'='*60}\n{ok} OK, {len(falhas)} falhas")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
