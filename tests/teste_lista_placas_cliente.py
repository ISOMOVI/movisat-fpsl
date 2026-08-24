"""A lista de placas do cliente sai em ordem alfabética e sem sujeira. 24/08.

🚨 POR QUE ISTO EXISTE. Ele pediu a lista "em ordem alfabética" e a consulta
JÁ tinha `ORDER BY placa` -- o que enganaria qualquer um que fosse conferir
lendo o código. O defeito estava no DADO, não na cláusula:

  - a base do Harmonit tem placa com ESPAÇO À ESQUERDA (`' 280574'`,
    `' AHQ 7266'`), e espaço ordena antes de qualquer letra;
  - 902 das 9.114 placas não têm espaço nenhum (`AAA1234`), então elas se
    intercalam com as que têm (`AAA 1234`).

O resultado na tela era uma lista que parecia embaralhada, com a consulta
"certa". É `fonte não é comportamento` de novo, agora do lado do dado.

Este teste monta uma base de mentira com os DOIS defeitos e confere a saída.
🚨 NÃO FAZ REDE e não toca no banco de produção: usa um sqlite temporário.

Roda na VPS: venv/bin/python tests/teste_lista_placas_cliente.py
"""
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

ok, falhas = 0, []


def checar(nome, cond, detalhe=""):
    global ok
    if cond:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# A mesma consulta do `placas_do_cliente`. ⚠️ Copiada de propósito: o objetivo é
# provar a REGRA de ordenação, e um teste que importasse o router precisaria do
# banco de produção -- que é justamente o que nenhum teste pode tocar.
SQL = ("SELECT TRIM(placa), veiculo FROM harmonit_veiculos "
       "WHERE clienteId = ? "
       "ORDER BY UPPER(REPLACE(TRIM(placa), ' ', ''))")

# Os dois defeitos reais, medidos na base em 24/08.
AMOSTRA = [
    (1, " DUC 8819", "MERCEDES BENZ 2423", 7),
    (2, "aaa1234", "minuscula sem espaco", 7),
    (3, " AHQ 7266", "Ford 1622", 7),
    (4, "BEZ1138", "Microonibus VW Comil", 7),
    (5, " 280574", "TM 2200R 4x4", 7),
    (6, "AAA 1235", "com espaco", 7),
    (7, "ZZZ 0000", "de outro cliente", 99),
]

with tempfile.TemporaryDirectory() as tmp:
    caminho = pathlib.Path(tmp) / "t.db"
    conn = sqlite3.connect(caminho)
    conn.execute("CREATE TABLE harmonit_veiculos "
                 "(id INTEGER, placa TEXT, veiculo TEXT, clienteId INTEGER)")
    conn.executemany("INSERT INTO harmonit_veiculos VALUES (?,?,?,?)", AMOSTRA)
    conn.commit()
    saida = [p for p, _ in conn.execute(SQL, (7,))]
    conn.close()

print("== a lista sai do jeito que a pessoa espera ler ==")
# ⚠️ `aaa1234` VEM ANTES de `AAA 1235`, e isso está certo: normalizadas elas
# são AAA1234 e AAA1235. Escrevi a expectativa ao contrário na primeira versão
# e a trava reprovou código correto -- é o `M7` outra vez, e desta vez a
# medição salvou a lista, não o teste.
esperado = ["280574", "aaa1234", "AAA 1235", "AHQ 7266", "BEZ1138", "DUC 8819"]
checar("ordem alfabética pela placa normalizada",
       saida == esperado, f"veio {saida}")
# 🚨 ESTES DOIS SÃO O DEFEITO, e sem eles o teste passaria com a consulta velha.
checar("a que tinha espaço à esquerda NÃO vai para o topo",
       saida[0] != " 280574" and saida.index("AAA 1235") < saida.index("AHQ 7266"),
       str(saida))
checar("com e sem espaço ficam juntas, não em blocos separados",
       saida.index("aaa1234") + 1 == saida.index("AAA 1235"),
       "aaa1234 e AAA 1235 são vizinhas quando se ignora espaço e caixa")
checar("nenhuma placa sai com espaço nas pontas",
       all(p == p.strip() for p in saida), str(saida))
checar("o filtro por cliente continua valendo",
       "ZZZ 0000" not in saida and len(saida) == 6, str(saida))

# ⚠️ O CONTROLE. Sem isto o teste não prova que a ordenação NOVA é diferente da
# velha -- e trava que passaria com o código antigo não protege nada.
with tempfile.TemporaryDirectory() as tmp:
    caminho = pathlib.Path(tmp) / "t.db"
    conn = sqlite3.connect(caminho)
    conn.execute("CREATE TABLE harmonit_veiculos "
                 "(id INTEGER, placa TEXT, veiculo TEXT, clienteId INTEGER)")
    conn.executemany("INSERT INTO harmonit_veiculos VALUES (?,?,?,?)", AMOSTRA)
    conn.commit()
    velha = [p for p, _ in conn.execute(
        "SELECT placa, veiculo FROM harmonit_veiculos "
        "WHERE clienteId = ? ORDER BY placa", (7,))]
    conn.close()

print()
print("== e a consulta antiga REPROVARIA ==")
checar("a ordem velha era diferente da nova",
       velha != saida, f"velha {velha}")
checar("e ela punha as de espaço à esquerda no topo",
       velha[0].startswith(" "), str(velha))

print()
print(f"== {ok} verificações OK, {len(falhas)} falha(s) ==")
if falhas:
    for f in falhas:
        print("   -", f)
    sys.exit(1)
