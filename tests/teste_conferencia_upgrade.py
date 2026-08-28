"""Conferência da leitura do termo — aba Operações (2026-08-28).

🚨 O DEFEITO QUE ISTO DEFENDE. Ele mandou o termo 8687 acusando "placa não
reconhecida". A placa estava certa (`FBI 8A36`, e existe na WESO e no
Harmonit); o que caiu na lista de veículos foi a LINHA DO TOTAL, que nesse
layout mora dentro da tabela de veículos, na coluna dos veículos. O extrator
não acha que o total é uma placa -- ele acha que aquela linha é um veículo, e
nela não encontra placa. Dentro da regra dele, está sendo honesto.

🚨 A REGRA NÃO OLHA A LINHA, OLHA A CONTA. Todo termo de upgrade declara
quantos veículos tem, na aritmética da taxa:

    8820:    R$ 100,00 ÷ R$  50,00 =  2
    8827:    R$ 200,00 ÷ R$ 200,00 =  1
    8800:  R$ 2.200,00 ÷ R$ 200,00 = 11
    8687:    R$ 200,00 ÷ R$ 200,00 =  1

⚠️ DUAS REGRAS QUE EU TENTEI ANTES E QUE NÃO ESTÃO AQUI, para não voltarem:
descartar por geometria (`X....X`) acerta 2 de 87 linhas com zero falsos
positivos, mas é FORMA -- quebra quando o rodapé ganhar uma coluna; e "linha
de veículo preenche outras colunas" morreu no teste, porque os dois totais
preenchem uma e há veículo legítimo que também preenche uma só.

⚠️ SÓ DA ABA OPERAÇÕES, por decisão dele: o `pdf_extractor` não muda, e as
outras duas telas seguem lendo como sempre leram.

Roda na VPS:  venv/bin/python tests/teste_conferencia_upgrade.py
Só leitura — não toca Harmonit, não escreve na WESO.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import operacoes_conferencia as oc  # noqa: E402
from fpsl_weso.painel.pdf_extractor import extrair_campos  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


# (arquivo, quantos o termo declara, quantas placas se lê)
UPGRADES = [
    ("upgrade_8820.pdf", 2, 2),
    ("upgrade_8827.pdf", 1, 1),
    ("upgrade_4g_8800.pdf", 11, 11),
]

print("== o termo declara quantos veículos tem ==")
for nome, declarado, lidos in UPGRADES:
    quantos, _como = oc.quantidade_declarada(str(FIXTURES / nome))
    checar(f"{nome} declara {declarado}", declarado, quantos)

print()
print("== a leitura fecha com o declarado ==")
for nome, declarado, lidos in UPGRADES:
    campos = extrair_campos(str(FIXTURES / nome), "upgrade")
    checar(f"{nome} lê {lidos} placa(s)", lidos, len(campos["placas"]))

print()
print("== o rodapé sai quando a conta fecha ==")
# 🚨 O CASO DELE: o 8827 tem o mesmo layout do 8687 -- total dentro da tabela.
_alvo = str(FIXTURES / "upgrade_8827.pdf")
_campos = extrair_campos(_alvo, "upgrade")
checar("antes: o rodapé entra na leitura", 1, len(_campos["veiculos_sem_placa"]))
_r = oc.conferir(_alvo, _campos)
checar("a conferência aconteceu", True, _r["conferido"])
checar("declarado x lido", (1, 1), (_r["declarado"], _r["lidos"]))
checar("depois: o rodapé saiu", [], _campos["veiculos_sem_placa"])
checar("descartar é silencioso, mas CONTADO", 1, len(_r["descartadas"]))

print()
print("== a conferência NUNCA mexe nas placas ==")
for nome, _declarado, lidos in UPGRADES:
    campos = extrair_campos(str(FIXTURES / nome), "upgrade")
    oc.conferir(str(FIXTURES / nome), campos)
    checar(f"{nome} mantém {lidos} placa(s)", lidos, len(campos["placas"]))

print()
print("== quando FALTA veículo, a sobra vira candidata ==")
# 🚨 O CAMINHO PERIGOSO, e o que separa esta regra de um filtro burro: a linha
# que sobrou pode SER o veículo que falta. Um filtro a apagaria.
_alvo = str(FIXTURES / "upgrade_4g_8800.pdf")
_campos = extrair_campos(_alvo, "upgrade")
_campos["placas"] = _campos["placas"][:-2]          # simula perder 2 na leitura
_campos["veiculos_sem_placa"] = [{"texto": "linha que eu nao soube ler",
                                  "motivo": "nao reconhecida"}]
_r = oc.conferir(_alvo, _campos)
checar("declarado x lido", (11, 9), (_r["declarado"], _r["lidos"]))
checar("a sobra NÃO some quando falta veículo", 1,
       len(_campos["veiculos_sem_placa"]))
checar("e o aviso diz o número", True, "declara 11" in (_r["aviso"] or ""))

print()
print("== termo sem a aritmética: a conferência se cala ==")
_alvo = str(FIXTURES / "transferencia_novo.pdf")
_campos = extrair_campos(_alvo, "transferencia")
_antes = len(_campos.get("veiculos_sem_placa") or [])
_r = oc.conferir(_alvo, _campos)
checar("não conferiu", False, _r["conferido"])
checar("e não estragou nada", _antes, len(_campos["veiculos_sem_placa"]))

print()
print("== valor bruto x valor ativo ==")
# 🚨 A mesma célula lida dos dois jeitos, e os dois estão certos: a financeira
# quer o ÚLTIMO (cobrança cancelada), a contagem quer o PRIMEIRO. Reusar o
# `_valor_ativo` aqui daria divisão por zero nos quatro termos, com placar verde.
checar("taxa riscada: pega o primeiro", 200.0, oc.valor_bruto("R$ 200,00\nR$ 0,00*"))
checar("total riscado: pega o primeiro", 2200.0,
       oc.valor_bruto("R$ 2.200,00 - R$ 0,00*"))
checar("sem valor devolve None", None, oc.valor_bruto("sem valor"))

print()
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
