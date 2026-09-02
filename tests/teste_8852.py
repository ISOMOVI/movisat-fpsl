"""Aditivo 8852 — `A DEFINIR` sozinho na célula. 2026-09-02.

Documento real: `tests/fixtures/aditivo_8852.pdf`, Condomínio Vinhas da Vista
Alegre. A tabela de veículos tem três linhas, e a terceira é **só o texto
`A DEFINIR`** — sem veículo e sem traço.

O que este arquivo PRENDE:

  1. **As três linhas viram placa.** Antes, a terceira caía em
     `veiculos_sem_placa` com motivo "nao reconhecida" e sumia da tela: o
     contrato tem 3 equipamentos e o painel mostrava 2 veículos.

  2. **O formato é o decidido em 29/07:** placa `A_DEFINIR_<termo>`, nome do
     veículo `TERMO:<termo>`, `placa_convencional = false`.

  3. **As duas placas de verdade continuam intactas**, com a descrição do
     veículo inteira.

🚨 POR QUE PASSOU DESPERCEBIDO. Havia duas correções necessárias, e a primeira
escondia a segunda: `_placa_pos_traco` exige o ` - ` para agir, e a linha do
8852 não tem traço nenhum. Corrigir só o caminho do traço deixava este caso de
fora — foi o que aconteceu na primeira tentativa, ao vivo, com o usuário
esperando.

Roda na VPS: venv/bin/python tests/teste_8852.py

🚨 NÃO FAZ REDE.
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
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


campos = ex.extrair_campos(str(RAIZ / "tests/fixtures/aditivo_8852.pdf"), "aditivo")
placas = campos.get("placas") or []

print("1. O documento inteiro")
checar("o termo é o 8852", campos.get("termo") == "8852", campos.get("termo"))
checar("o cliente saiu do cabeçalho",
       campos.get("cliente_nome_sugerido") == "CONDOMINIO VINHAS DA VISTA ALEGRE",
       campos.get("cliente_nome_sugerido"))
checar("AS TRÊS LINHAS VIRARAM PLACA", len(placas) == 3,
       "vieram %d: %s" % (len(placas), [p.get("placa") for p in placas]))
checar("e NADA sobrou para revisão humana",
       not campos.get("veiculos_sem_placa"), campos.get("veiculos_sem_placa"))
checar("o contrato tem 3 equipamentos, e agora 3 veículos",
       len(placas) == 3)

print()
print("2. As duas placas de verdade, intactas")
for i, esperada in ((0, "FWF 6C16"), (1, "GHL 0A32")):
    p = placas[i] if i < len(placas) else {}
    checar("linha %d é %s" % (i + 1, esperada), p.get("placa") == esperada,
           repr(p.get("placa")))
    checar("   com a descrição do veículo inteira",
           "HONDA/CG 160 CARGO" in (p.get("veiculo") or ""), repr(p.get("veiculo")))

print()
print("3. A terceira, no formato decidido em 29/07")
p = placas[2] if len(placas) > 2 else {}
checar("placa vira A_DEFINIR_8852", p.get("placa") == "A_DEFINIR_8852",
       repr(p.get("placa")))
checar("nome do veículo vira TERMO:8852", p.get("veiculo") == "TERMO:8852",
       repr(p.get("veiculo")))
checar("apelido sugerido é TERMO:8852",
       p.get("apelido_sugerido") == "TERMO:8852", repr(p.get("apelido_sugerido")))
checar("marcada como placa não convencional",
       p.get("placa_convencional") is False, repr(p.get("placa_convencional")))

print()
print("4. Os itens do contrato não mudaram")
itens = campos.get("itens") or []
checar("dez itens lidos", len(itens) == 10, len(itens))
checar("o rastreador está entre eles",
       any("rastreador" in (i.get("descricao") or "").lower() for i in itens))

print()
print("%d ok, %d falha(s)" % (ok, len(falhas)))
if falhas:
    for f in falhas:
        print("  -", f)
    sys.exit(1)
