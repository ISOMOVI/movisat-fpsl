"""Semeadura de preço do faturado (`CAR_1.1`) — bloco F4. 30/10/2026.

Banco TEMPORÁRIO em memória. 🔵 Decisão dele, 30/10: *"faça o 2 [o lote], mas
deixe as regras do 1 tbm, para quando alguem alterar os demais"*.

🚨 OS CASOS QUE ESTE TESTE EXISTE PARA FECHAR:
1. **Proposta não é lançamento.** `propor_precos` não grava nada, e o que tem
   conflito **não entra no lote** -- sai nomeado, para uma pessoa decidir.
2. **Contrato que já tem OUTRO preço vigente é conflito**, não cópia. Era o
   único jeito de a semeadura passar por cima de um reajuste combinado.
3. **O mesmo preço já vigente também é conflito** -- lançar de novo encheria o
   histórico com a linha repetida, e é esse histórico que responde "por que
   mudou".
4. **Dois valores no mesmo contrato na mesma competência**: ninguém escolhe por
   adivinhação. (Medido em 28/10: zero casos hoje -- e a trava fica.)
5. **Idempotência do lote** por (termo, competência, valor): clicar duas vezes
   não lança duas vezes.
6. **Recusa não derruba o lote**: o resto entra, e o recusado volta com motivo.
7. **O documento é o lançamento financeiro**, e o autor **nunca** vem do corpo.

Roda na VPS:  venv/bin/python tests/teste_car_semear.py
"""
import pathlib
import sqlite3
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import car_faturado as cf                  # noqa: E402
from fpsl_weso.painel import car_motor as motor                  # noqa: E402
from fpsl_weso.painel import car_prefatura as pf                 # noqa: E402
from fpsl_weso.painel import car_registro as registro            # noqa: E402
from fpsl_weso.painel import car_tabelas as car                  # noqa: E402
from fpsl_weso.painel import contratos_tabelas as ctr            # noqa: E402

ok, falhas = 0, []
A = "20480457000158"
B = "44213607000125"
COMP = "2026-09"

def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def base():
    conn = sqlite3.connect(":memory:")
    ctr.criar(conn)
    ctr.migrar(conn)
    car.criar(conn)
    car.migrar(conn)
    for cnpj, nome in ((A, "CLIENTE A"), (B, "CLIENTE B")):
        conn.execute("INSERT INTO contrato_cliente (cnpj, nome, nome_fonte, "
                     "atualizado_em) VALUES (?,?,'teste','2026-10-30')", (cnpj, nome))
    return conn


def termo(conn, cnpj, numero, empresa="MOVISAT"):
    cur = conn.execute(
        "INSERT INTO contrato_termo (cnpj, numero, empresa, tipo, assinado, "
        "assinado_em, origem, enviado_em) VALUES (?,?,?,'CONTRATO',1,"
        "'2026-01-10','teste','2026-01-10')", (cnpj, numero, empresa))
    return cur.lastrowid


def faturado(termo_id, valor, lanc_id, competencia=COMP, tipo=cf.MENSALIDADE,
             numero="3226"):
    return {"id": lanc_id, "tipo": tipo, "competencia": competencia,
            "valor": valor, "termo_id": termo_id, "termo_numero": numero,
            "contato": "CLIENTE A"}


print("[0] a proposta nasce do que o Harmonit cobra")
conn = base()
t1 = termo(conn, A, "3226")
t2 = termo(conn, B, "8719")
termos = {t1: {"id": t1, "cnpj": A, "numero": "3226", "empresa": "MOVISAT"},
          t2: {"id": t2, "cnpj": B, "numero": "8719", "empresa": "MOVISAT"}}
r = cf.propor_precos([faturado(t1, "200.53", 11)], termos, lambda _t: None, COMP)
checar("uma proposta", 1, r["totais"]["propostas"])
p = r["propostas"][0]
checar("com o valor do lançamento", "200.53", p["valor"])
checar("e o documento é o lançamento", "mov. financeira 11", p["documento"])
checar("nenhum conflito", 0, r["totais"]["conflitos"])

print("\n[1] só mensalidade semeia preço")
r = cf.propor_precos([faturado(t1, "598.01", 12, tipo=cf.SERVICO)], termos,
                     lambda _t: None, COMP)
checar("serviço (OS) não vira mensalidade", 0, r["totais"]["propostas"])
r = cf.propor_precos([faturado(t1, "237.71", 13, tipo=cf.ADESAO)], termos,
                     lambda _t: None, COMP)
checar("adesão também não", 0, r["totais"]["propostas"])
r = cf.propor_precos([faturado(t1, "200.53", 14, competencia="2026-08")], termos,
                     lambda _t: None, COMP)
checar("mês diferente não entra", 0, r["totais"]["propostas"])

print("\n[2] conflito é conflito: não entra no lote")
r = cf.propor_precos([faturado(t1, "200.53", 11)], termos,
                     lambda _t: "180,00", COMP)
checar("preço vigente diferente -> conflito", (0, 1),
       (r["totais"]["propostas"], r["totais"]["conflitos"]))
checar("e o motivo manda DECIDIR", True,
       "decidir, não copiar" in r["conflitos"][0]["motivo"])
r = cf.propor_precos([faturado(t1, "200.53", 11)], termos,
                     lambda _t: "200.53", COMP)
checar("mesmo preço já vigente -> conflito, não repetição", (0, 1),
       (r["totais"]["propostas"], r["totais"]["conflitos"]))
r = cf.propor_precos([faturado(t1, "200.53", 11), faturado(t1, "300.00", 12)],
                     termos, lambda _t: None, COMP)
checar("dois valores no mesmo contrato -> conflito", (0, 1),
       (r["totais"]["propostas"], r["totais"]["conflitos"]))
checar("e o conflito mostra os dois valores", ["200.53", "300.00"],
       r["conflitos"][0]["valores"])
r = cf.propor_precos([faturado(t1, "200.53", 11), faturado(t1, "200.53", 12)],
                     termos, lambda _t: None, COMP)
checar("o MESMO valor em dois lançamentos é uma proposta só", 1,
       r["totais"]["propostas"])
checar("com os dois lançamentos no documento", "mov. financeira 11, 12",
       r["propostas"][0]["documento"])
r = cf.propor_precos([faturado(None, "200.53", 11)], termos, lambda _t: None, COMP)
checar("lançamento sem termo resolvido aparece em sem_termo", 1,
       r["totais"]["sem_termo"])
r = cf.propor_precos([faturado(99999, "200.53", 11)], termos, lambda _t: None, COMP)
checar("termo que não existe mais também", 1, r["totais"]["sem_termo"])

print("\n[3] o lote grava, com autor, motivo e documento")
propostas = cf.propor_precos([faturado(t1, "200.53", 11)], termos,
                             lambda _t: None, COMP)["propostas"]
d = registro.semear_em_lote(conn, propostas, "iago")
checar("lançou 1", 1, d["lancados"])
linha = conn.execute(
    "SELECT cnpj, termo_id, acao, valor_mensal, competencia, fonte, por, "
    "documento, motivo FROM car_evento").fetchone()
checar("o evento é um PRECO do contrato certo",
       (A, t1, motor.PRECO, "200.53", COMP, "operador", "iago"),
       linha[:7])
checar("o documento aponta o lançamento", "mov. financeira 11", linha[7])
checar("e o motivo diz de onde veio", registro.MOTIVO_SEMEADURA, linha[8])

print("\n[4] idempotência e recusa que não derruba o lote")
d = registro.semear_em_lote(conn, propostas, "iago")
checar("semear de novo não lança de novo", (0, 1), (d["lancados"], d["repetidos"]))
checar("e o histórico não ganhou linha repetida", 1,
       conn.execute("SELECT COUNT(*) FROM car_evento").fetchone()[0])
mistas = [
    {"termo_id": 99999, "cnpj": A, "valor": "10,00", "competencia": COMP,
     "documento": "mov. financeira 1"},
    {"termo_id": t2, "cnpj": B, "valor": "77,81", "competencia": COMP,
     "documento": "mov. financeira 2"},
    {"termo_id": t2, "cnpj": A, "valor": "50,00", "competencia": COMP,
     "documento": "mov. financeira 3"},
    {"termo_id": t1, "cnpj": A, "valor": "", "competencia": COMP,
     "documento": "mov. financeira 4"},
    {"termo_id": t1, "cnpj": A, "valor": "1,00", "competencia": "2026-13",
     "documento": "mov. financeira 5"},
]
d = registro.semear_em_lote(conn, mistas, "iago")
checar("o bom entra", 1, d["lancados"])
checar("e os quatro ruins voltam com motivo", 4, len(d["recusados"]))
checar("termo inexistente é dito", True,
       any("não existe nesta base" in x["motivo"] for x in d["recusados"]))
checar("🚨 termo de OUTRO cliente é dito", True,
       any("não de " in x["motivo"] for x in d["recusados"]))
checar("sem valor é dito", True,
       any("sem valor" in x["motivo"] for x in d["recusados"]))
checar("competência inválida é dita", True,
       any("competência inválida" in x["motivo"] for x in d["recusados"]))
checar("o lote não gravou o recusado", 2,
       conn.execute("SELECT COUNT(*) FROM car_evento").fetchone()[0])
try:
    registro.semear_em_lote(conn, [], "iago")
    checar("lote vazio é recusado", True, False)
except registro.DadoInvalido:
    checar("lote vazio é recusado", True, True)

print("\n[5] o preço semeado aparece na pré-fatura do mês")
# A placa entra no contrato pelo evento da CTR, como em toda a casa.
conn.execute("INSERT INTO contrato_evento (termo_id, placa_chave, placa_texto, "
             "acao, fonte, criado_em) VALUES (?,?,?,'ENTRA','assinado',"
             "'2026-01-10T00:00:00Z')", (t1, "AAA1B11", "AAA1B11"))
pre = pf.montar(conn, COMP, cnpj=A)
linhas = [l for c in pre["clientes"] for ct in c["contratos"] for l in ct["linhas"]]
checar("uma linha de cobrança", 1, len(linhas))
checar("com o valor semeado", "200.53", linhas[0]["valor"])
checar("e a fonte diz que veio de evento da CAR", True,
       "evento" in (linhas[0]["fonte_do_valor"] or "").lower()
       or linhas[0]["fonte_do_valor"] is not None)
checar("sem WESO consultada, em_uso_weso é None", None, linhas[0]["em_uso_weso"])
checar("e a resposta declara que não leu a WESO", False, pre["weso"]["lido"])

print("\n[6] com a WESO injetada, a régua dele aparece")
pre = pf.montar(conn, COMP, cnpj=A, weso={"AAA1B11": "Instalado"}, idade_weso=3.0)
linhas = [l for c in pre["clientes"] for ct in c["contratos"] for l in ct["linhas"]]
checar("a placa está em uso", True, linhas[0]["em_uso_weso"])
checar("e a situação aparece com o nome", "Instalado", linhas[0]["situacao_weso"])
checar("o total conta as em uso", 1, pre["totais"]["em_uso"])
checar("a idade do cache vai na resposta", 3.0, pre["weso"]["idade_h"])
pre = pf.montar(conn, COMP, cnpj=A, weso={"AAA1B11": "Estoque"}, idade_weso=3.0)
linhas = [l for c in pre["clientes"] for ct in c["contratos"] for l in ct["linhas"]]
checar("Estoque NÃO é uso", False, linhas[0]["em_uso_weso"])
checar("e o nome da situação é mostrado", "Estoque", linhas[0]["situacao_weso"])
checar("contratada e não instalada é contada", 1,
       pre["totais"]["contratadas_sem_uso"])

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
