"""P5 — continuação de página na tabela de placas (2026-07-27).

O bug: quando a lista de veículos passa de uma página, a parte de baixo vem numa
tabela SEM cabeçalho. O achador de header a ignora e as placas seguintes somem
SEM ERRO NENHUM. Foi assim que a rescisão 8788 lia 12 de 26.

Corrigido em 23/07 só no parser de Rescisão. Estendido aos demais em 27/07.

Os 9 termos reais não têm esse caso fora da Rescisão -- por isso aqui os dados
são sintéticos: é a única forma de provar que a correção pega.

Roda: venv/bin/python tests/teste_continuacao_pagina.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import pdf_extractor as px  # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


# ⚠️ os textos de veículo abaixo evitam de propósito o padrão "XXX 9999"
# (3 letras + 4 dígitos): 'UNO 2019' e 'GOL 2020' CASAM com o regex de placa
# antiga e viram placa fantasma. Isso é um bug latente do extrator, anotado em
# 2026-07-27 -- não é o que este teste cobre.
# página 1: tabela COM cabeçalho, 2 colunas
PAG1 = [["Nº", "Veiculo Placa"],
        ["1", "VOLKSWAGEN GOLF BRANCO ABC1234"],
        ["2", "FIAT PALIO PRATA DEF5678"]]
# página 2: continuação, MESMO nº de colunas, SEM cabeçalho
PAG2 = [["3", "CHEVROLET ONIX PRETO GHI9012"],
        ["4", "FORD FIESTA AZUL JKL3456"]]
# tabela de ITENS: mesmo nº de colunas, mas é outra coisa -- não pode ser lida como placa
ITENS = [["Acessorio", "Quantidade"],
         ["Bloqueio veicular", "2"]]

print("[1] reconhecimento da continuação")
checar("continuação de placas é reconhecida", True,
       px._eh_continuacao_tabela(PAG2, 2, [1]))
checar("tabela de ITENS não é confundida", False,
       px._eh_continuacao_tabela(ITENS, 2, [1]))
checar("nº de colunas diferente não casa", False,
       px._eh_continuacao_tabela([["a", "b", "c"]], 2, [1]))
checar("tabela vazia não casa", False, px._eh_continuacao_tabela([], 2, [1]))

print("\n[2] extração das linhas")
placas = []
px._processar_linhas_placa(PAG1[1:], [1], placas)
checar("página 1 rende 2 placas", 2, len(placas))
px._processar_linhas_placa(PAG2, [1], placas)
checar("com a continuação vira 4", 4, len(placas))
checar("placas na ordem", ["ABC 1234", "DEF 5678", "GHI 9012", "JKL 3456"],
       [p["placa"] for p in placas])
checar("veículo veio junto", "VOLKSWAGEN GOLF BRANCO", placas[0]["veiculo"])

print("\n[3] ponta a ponta pelo extrator (simulando 2 páginas)")
paginas = [{"texto": "TERMO 9999", "tabelas": [PAG1]},
           {"texto": "", "tabelas": [PAG2]}]
r = px._extrair_item_veiculo(paginas, tem_ficha_cadastral=False)
checar("extrator captura as 4 placas (era 2 antes do P5)", 4, len(r.get("placas") or []))
checar("a 4a placa é a da pagina 2", "JKL 3456", (r["placas"][3] or {}).get("placa"))

print("\n[4] guarda: itens na 2a pagina NÃO viram placa")
paginas2 = [{"texto": "TERMO 9999", "tabelas": [PAG1]},
            {"texto": "", "tabelas": [ITENS]}]
r2 = px._extrair_item_veiculo(paginas2, tem_ficha_cadastral=False)
checar("continua com 2 placas", 2, len(r2.get("placas") or []))

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
