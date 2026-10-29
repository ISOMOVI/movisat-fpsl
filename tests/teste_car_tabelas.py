"""Tabelas das Contas a Receber (`CAR_1.1`) — etapa E2.

Roda em banco de MEMÓRIA: a DDL se prova sem o `fpsl.db` e sem asyncio.

🚨 O QUE ESTE TESTE EXISTE PARA FECHAR, e não é teoria:
1. **Idempotência.** O `init_db` roda a cada start do serviço. `criar()` e
   `migrar()` são chamados DUAS VEZES aqui -- se um dia alguém puser um `CREATE
   TABLE` sem `IF NOT EXISTS` ou um `ALTER` sem a guarda do `PRAGMA`, o serviço
   para de subir, e o sintoma aparece num restart qualquer, longe do commit.
2. **Anulação dobrada.** O índice único parcial é a única coisa que impede
   empilhar `ANULA` sobre `ANULA`. Na CTR isso foi achado em construção; aqui
   nasce travado.
3. **A CAR não altera a CTR.** `criar()` roda num banco que já tem as tabelas
   `contrato_*` e o teste prova que elas saem com as MESMAS colunas -- é a
   regra da casa ("regra que muda clona, infraestrutura reusa") medida, e não
   prometida.

Roda na VPS:  venv/bin/python tests/teste_car_tabelas.py
Não toca o banco real: tudo em `:memory:`.
"""
import pathlib
import sqlite3
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import car_tabelas as car                  # noqa: E402
from fpsl_weso.painel import contratos_tabelas as ctr            # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def colunas(conn, tabela):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def tabelas(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def indices(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}


ESPERADO = {
    "car_evento": {"id", "cnpj", "termo_id", "placa_chave", "acao", "valor_mensal",
                   "competencia", "motivo", "documento", "fonte", "por", "criado_em",
                   "corrige_evento_id"},
    "car_contrato": {"termo_id", "cnpj", "numero", "empresa", "situacao", "motivo",
                     "placas_ativas", "placas_com_valor", "placas_sem_valor",
                     "valor_mensal_total", "divergencia", "competencia", "calculado_em"},
    "car_leitura": {"id", "competencia", "cnpj", "gerada_em", "por", "clientes",
                    "placas", "sem_valor", "total", "assinatura"},
}


def main():
    print("teste_car_tabelas — banco em :memory:")
    conn = sqlite3.connect(":memory:")

    # A CTR primeiro, porque é o cenário real: a CAR nasce num banco que já tem
    # as 8 tabelas de contrato.
    ctr.criar(conn)
    ctr.migrar(conn)
    ctr_antes = {t: colunas(conn, t) for t in ctr.TABELAS}

    print("\n[1] criar() faz as 3 tabelas, com as colunas da spec")
    car.criar(conn)
    feitas = car.migrar(conn)
    checar("TABELAS declara as 3", 3, len(car.TABELAS))
    for t in car.TABELAS:
        checar(f"{t} existe", True, t in tabelas(conn))
        checar(f"{t} tem exatamente as colunas da spec", ESPERADO[t], colunas(conn, t))
    checar("migrar() nasce sem nada a fazer", [], feitas)

    print("\n[2] os índices que a spec pede")
    idx = indices(conn)
    for nome in ("idx_car_evento_termo", "idx_car_evento_cnpj", "idx_car_evento_corrige",
                 "idx_car_contrato_cnpj", "idx_car_contrato_situacao",
                 "idx_car_leitura_comp"):
        checar(f"{nome} existe", True, nome in idx)

    print("\n[3] 🚨 rodar DUAS VEZES não quebra e não perde dado")
    conn.execute(
        "INSERT INTO car_evento (cnpj, termo_id, acao, valor_mensal, competencia, "
        "fonte, por, criado_em) VALUES "
        "('20480457000158', 1, 'PRECO', 'R$ 75,26', '2026-10', 'termo', 'admin', "
        "'2026-10-28T12:00:00Z')")
    car.criar(conn)
    car.migrar(conn)
    checar("a linha gravada sobreviveu ao segundo criar()", 1,
           conn.execute("SELECT count(*) FROM car_evento").fetchone()[0])
    for t in car.TABELAS:
        checar(f"{t} segue com as mesmas colunas depois da 2ª passada",
               ESPERADO[t], colunas(conn, t))

    print("\n[4] 🚨 o mesmo evento NÃO se anula duas vezes")
    anula = ("INSERT INTO car_evento (cnpj, termo_id, acao, competencia, fonte, por, "
             "criado_em, corrige_evento_id) VALUES "
             "('20480457000158', 1, 'ANULA', '2026-10', 'operador', 'admin', "
             "'2026-10-28T12:01:00Z', 1)")
    conn.execute(anula)
    checar("a primeira anulação entra", 1, conn.execute(
        "SELECT count(*) FROM car_evento WHERE acao='ANULA'").fetchone()[0])
    try:
        conn.execute(anula)
        checar("a segunda anulação do MESMO evento é recusada", True, False)
    except sqlite3.IntegrityError:
        checar("a segunda anulação do MESMO evento é recusada", True, True)
    # ⚠️ E o índice é PARCIAL: dois eventos comuns (sem corrigir ninguém)
    # convivem. Um índice único cheio barraria o segundo PRECO do mesmo termo.
    conn.execute(
        "INSERT INTO car_evento (cnpj, termo_id, acao, valor_mensal, competencia, "
        "fonte, por, criado_em) VALUES "
        "('20480457000158', 1, 'PRECO', 'R$ 80,00', '2026-11', 'operador', 'admin', "
        "'2026-10-28T12:02:00Z')")
    checar("dois eventos com corrige_evento_id NULO convivem", 2, conn.execute(
        "SELECT count(*) FROM car_evento WHERE corrige_evento_id IS NULL "
        "AND acao='PRECO'").fetchone()[0])

    print("\n[5] 🚨 a CAR não alterou NENHUMA tabela da CTR")
    for t in ctr.TABELAS:
        checar(f"{t} intacta", ctr_antes[t], colunas(conn, t))

    print("\n[6] o ESQUEMA gravado, não a prosa que o explica")
    # 🚨 A PRIMEIRA VERSÃO DESTE BLOCO DEU FALSO VERMELHO, e a lição vale mais
    # que o bloco: ela procurava a palavra "CHECK" no texto do módulo -- e o
    # módulo **explica por que não há CHECK**. Prosa casou com a busca. Agora o
    # que se mede é o que o SQLite guardou, com os comentários do DDL fora.
    import re
    for t in car.TABELAS:
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (t,)).fetchone()[0]
        limpo = re.sub(r"--[^\n]*", "", ddl).upper()
        # Sem CHECK, por decisão: o conjunto de ações vive em `car_motor`. Com
        # CHECK no SQLite, ação nova exigiria RECONSTRUIR a tabela -- foi o que
        # a CTR evitou quando a `ANULA` nasceu, em 14/10.
        checar(f"{t}: nenhum CHECK no esquema (o enum vive no motor)",
               False, "CHECK" in limpo)
        # Sem FOREIGN KEY, por simetria com as 8 tabelas da CTR, que também não
        # usam: o `termo_id` aponta `contrato_termo.id` e quem garante isso é o
        # registro, não o banco.
        checar(f"{t}: nenhuma FOREIGN KEY", False, "FOREIGN KEY" in limpo)

    print("\n[7] o módulo não escreve em tabela da CTR, e não tem UPDATE/DROP")
    # Mesma lição do bloco acima: compara-se o SQL que o módulo executa, obtido
    # da árvore sintática, e não o arquivo inteiro -- as docstrings falam de
    # `UPDATE` e de `contrato_evento` de propósito, para dizer o que NÃO se faz.
    import ast
    arvore = ast.parse((RAIZ / "fpsl_weso" / "painel" / "car_tabelas.py")
                       .read_text(encoding="utf-8"))
    docs = {id(arvore.body[0].value)} if (arvore.body and isinstance(
        arvore.body[0], ast.Expr) and isinstance(arvore.body[0].value, ast.Constant)) else set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if no.body and isinstance(no.body[0], ast.Expr) and \
                    isinstance(no.body[0].value, ast.Constant):
                docs.add(id(no.body[0].value))
    sql = "\n".join(
        no.value.upper() for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str)
        and id(no) not in docs)
    checar("o SQL do módulo não tem ALTER TABLE contrato_", False,
           "ALTER TABLE CONTRATO_" in sql)
    checar("o SQL do módulo não tem UPDATE", False, "UPDATE " in sql)
    checar("o SQL do módulo não tem DROP", False, "DROP " in sql)
    checar("e tem as 3 tabelas", 3, sql.count("CREATE TABLE IF NOT EXISTS"))

    conn.close()
    print("\n" + "=" * 52)
    print(f"{ok} verificações OK, {len(falhas)} falha(s)")
    for f in falhas:
        print(f"  FALHOU: {f}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
