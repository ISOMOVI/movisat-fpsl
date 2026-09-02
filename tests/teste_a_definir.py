"""`A DEFINIR` na coluna única do Aditivo. 2026-09-02.

O que este arquivo PRENDE, e que reprova se alguém desfizer:

  1. **`A DEFINIR` é identificador válido**, mesmo sem dígito. Ele é sentinela,
     não texto livre, e por isso passa antes das guardas de `_placa_pos_traco`.

  2. **A guarda do dígito continua de pé para o resto.** Ela é o que impede
     texto corrido de virar placa — o defeito do `RFD 2447`, dado plausível
     apontando para lugar nenhum. Tirá-la para resolver o `A DEFINIR` teria
     custado isso.

  3. **A grafia é normalizada.** `A definir`, `A-DEFINIR`, `A_DEFINIR` e
     `À DEFINIR` chegam iguais na etapa seguinte, que troca pelo formato
     definitivo `A_DEFINIR_<termo>` com apelido `TERMO:<termo>`.

  4. **Sem número de termo, nada é inventado** — o texto original fica.

🚨 CUSTOU UM TERMO AO VIVO. Aditivo 8852, em 02/09: dos três veículos, os dois
com placa entraram e o terceiro sumiu da extração. A troca pelo formato
definitivo já existia desde 29/07 e nunca era alcançada, porque roda DEPOIS do
reconhecimento — e o reconhecimento reprovava por falta de dígito.

Roda na VPS: venv/bin/python tests/teste_a_definir.py

🚨 NÃO FAZ REDE.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import pdf_extractor as ex  # noqa: E402

ok, falhas = 0, []


def checar(nome, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print("  ok    %s" % nome)
    else:
        falhas.append(nome)
        print("  FALHA %s %s" % (nome, extra))


print("1. A linha do Aditivo com placa a definir")
for linha in (
    "HONDA/CG 160 CARGO, 2021/2021, BRANCA, FLEX - A DEFINIR",
    "FIAT/TORO 2024 - A definir",
    "VOLVO FH 540 - A_DEFINIR",
    "SCANIA/P 340 - A-DEFINIR",
    "MERCEDES/ACTROS - À DEFINIR",
):
    ident, desc = ex._placa_pos_traco(linha)
    checar("vira identificador: %s" % linha[-24:],
           ident == "A DEFINIR", repr(ident))
    checar("   e a descrição do veículo sobra inteira", bool(desc), repr(desc))

print()
print("2. A guarda do dígito continua reprovando texto corrido")
for linha in (
    "coluna de texto que caiu na tabela - la tambem no contrato principal de",
    "SR/FACCHINI SEMI- REBOQUE",
):
    ident, _ = ex._placa_pos_traco(linha)
    checar("NÃO vira placa: %s" % linha[:34], ident is None, repr(ident))

print()
print("3. O que tem placa de verdade continua passando")
for linha, esperado in (
    ("NISSAN, 2022, DIESEL - RZL H405", "RZL H405"),
    ("HONDA/CG 160 - FWF 6C16", "FWF 6C16"),
):
    ident, _ = ex._placa_pos_traco(linha)
    checar("%s -> %s" % (linha[-12:], esperado), ident == esperado, repr(ident))

print()
print("4. A troca pelo formato definitivo, com o termo")
campos = {"termo": "8852", "placas": [
    {"placa": "A DEFINIR"}, {"placa": "A definir"}, {"placa": "À DEFINIR"},
    {"placa": "A-DEFINIR"}, {"placa": "FWF 6C16"},
]}
saida = ex._aplicar_placeholder_termo(campos)
for i in range(4):
    p = saida["placas"][i]
    checar("grafia %d vira A_DEFINIR_8852" % (i + 1),
           p["placa"] == "A_DEFINIR_8852", repr(p["placa"]))
    checar("   com apelido TERMO:8852",
           p.get("apelido_sugerido") == "TERMO:8852", repr(p.get("apelido_sugerido")))
    checar("   e marcada como placa não convencional",
           p.get("placa_convencional") is False, repr(p.get("placa_convencional")))
checar("a placa de verdade não é tocada",
       saida["placas"][4]["placa"] == "FWF 6C16", repr(saida["placas"][4]))

print()
print("5. Sem número de termo, nada é inventado")
sem = ex._aplicar_placeholder_termo({"placas": [{"placa": "A DEFINIR"}]})
checar("mantém o texto original", sem["placas"][0]["placa"] == "A DEFINIR",
       repr(sem["placas"][0]))

print()
print("%d ok, %d falha(s)" % (ok, len(falhas)))
if falhas:
    for f in falhas:
        print("  -", f)
    sys.exit(1)
