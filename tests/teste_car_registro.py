"""Registro das Contas a Receber (`CAR_1.1`) — etapa E6.

Banco TEMPORÁRIO em memória. Não toca o `fpsl.db`.

🚨 OS CASOS QUE ESTE TESTE EXISTE PARA FECHAR:
1. **Nada de `UPDATE`.** Dois `PRECO` geram duas linhas, e o vigente é o da
   competência -- é o que faz o histórico de reajuste existir de graça.
2. **`por` nunca vazio, `motivo` obrigatório onde a origem é gente.** Dinheiro
   sem autor é dinheiro sem responsável.
3. **Termo de OUTRO cliente é recusado.** O CNPJ vem da tela e o `termo_id` do
   clique; se discordarem, gravar lançaria preço no contrato de outro cliente e
   a conferência só pegaria meses depois.
4. **Anular duas vezes levanta `JaAnulado`**, e o anulado **aparece** no
   histórico, marcado -- esconder a correção transformaria histórico em versão
   final.
5. **O lote é idempotente** por (termo, competência, valor): dois cliques não
   lançam duas linhas.
6. **Um contrato recusado não derruba o lote.** Lote que morre no meio deixa
   metade da carteira precificada e ninguém sabe qual metade.
7. **`car_contrato` entra com TODOS os termos**, não só os com placa cobrável:
   ele pediu status "pelo contrato em si".

Roda na VPS:  venv/bin/python tests/teste_car_registro.py
"""
import pathlib
import sqlite3
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import car_motor as motor                  # noqa: E402
from fpsl_weso.painel import car_registro as rg                  # noqa: E402
from fpsl_weso.painel import car_tabelas as car                  # noqa: E402
from fpsl_weso.painel import contratos_tabelas as ctr            # noqa: E402

ok, falhas = 0, []
A = "20480457000158"
B = "44213607000125"


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def levanta(nome, excecao, fn, *a, **k):
    global ok
    try:
        fn(*a, **k)
    except excecao:
        ok += 1
        print(f"  OK   {nome}")
        return
    except Exception as e:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       levantou {type(e).__name__}: {e}")
        return
    falhas.append(nome)
    print(f"  FALHA {nome}\n       não levantou nada")


def termo(conn, cnpj, numero, empresa="MOVISAT", assinado=1, tipo="CONTRATO"):
    cur = conn.execute(
        "INSERT INTO contrato_termo (cnpj, numero, empresa, tipo, assinado, "
        "assinado_em, origem, enviado_em) VALUES (?,?,?,?,?,'2026-01-10','teste',"
        "'2026-01-10')", (cnpj, numero, empresa, tipo, assinado))
    return cur.lastrowid


def evento(conn, termo_id, placa, acao="ENTRA"):
    conn.execute(
        "INSERT INTO contrato_evento (termo_id, placa_chave, placa_texto, acao, "
        "fonte, criado_em) VALUES (?,?,?,?,'assinado','2026-01-10T00:00:00Z')",
        (termo_id, placa.replace(" ", ""), placa, acao))


def base():
    conn = sqlite3.connect(":memory:")
    ctr.criar(conn); ctr.migrar(conn); car.criar(conn); car.migrar(conn)
    for doc, nome in ((A, "CLIENTE A"), (B, "CLIENTE B")):
        conn.execute("INSERT INTO contrato_cliente (cnpj, nome, nome_fonte, "
                     "atualizado_em) VALUES (?,?,'teste','2026-10-28')", (doc, nome))
    return conn


def main():
    print("teste_car_registro — banco em :memory:")
    conn = base()
    t1 = termo(conn, A, "1001"); evento(conn, t1, "ABC1D23")
    t2 = termo(conn, B, "2002"); evento(conn, t2, "XYZ9W88")
    t_nao = termo(conn, B, "2003", assinado=0); evento(conn, t_nao, "QQQ1R11")

    print("\n[1] 🚨 preço: insere, não atualiza — e o histórico nasce de graça")
    e1 = rg.lancar_preco(conn, A, t1, "R$ 75,26", "2026-10", "admin",
                         motivo="valor do termo, conferido à mão")
    e2 = rg.lancar_preco(conn, A, t1, "R$ 90,00", "2026-11", "admin",
                         motivo="reajuste anual")
    checar("duas linhas em car_evento", 2, conn.execute(
        "SELECT count(*) FROM car_evento WHERE acao='PRECO'").fetchone()[0])
    checar("em outubro vale o primeiro", "R$ 75,26", motor.preco_vigente(
        list(rg.pf.eventos_por_termo(conn)[t1]), "2026-10")["valor_mensal"])
    checar("em novembro vale o segundo", "R$ 90,00", motor.preco_vigente(
        list(rg.pf.eventos_por_termo(conn)[t1]), "2026-11")["valor_mensal"])
    h = rg.historico_de_preco(conn, t1)
    checar("o histórico traz os dois", 2, len(h))
    checar("e nenhum está anulado", [False, False], [x["anulado"] for x in h])
    checar("o autor ficou gravado", "admin", conn.execute(
        "SELECT por FROM car_evento WHERE id=?", (e1,)).fetchone()[0])

    print("\n[2] 🚨 o que se recusa a gravar")
    levanta("preço sem valor", rg.DadoInvalido, rg.lancar_preco,
            conn, A, t1, "", "2026-10", "admin", motivo="x")
    levanta("preço à mão sem motivo", rg.DadoInvalido, rg.lancar_preco,
            conn, A, t1, "R$ 10,00", "2026-10", "admin")
    levanta("sem quem lançou", rg.DadoInvalido, rg.lancar_preco,
            conn, A, t1, "R$ 10,00", "2026-10", "   ", motivo="x")
    levanta("competência inválida", motor.CompetenciaInvalida, rg.lancar_preco,
            conn, A, t1, "R$ 10,00", "2026-13", "admin", motivo="x")
    levanta("termo que não existe", rg.TermoNaoExiste, rg.lancar_preco,
            conn, A, 99999, "R$ 10,00", "2026-10", "admin", motivo="x")
    levanta("🚨 termo de OUTRO cliente", rg.TermoNaoExiste, rg.lancar_preco,
            conn, A, t2, "R$ 10,00", "2026-10", "admin", motivo="x")
    levanta("cancelar sem motivo", rg.DadoInvalido, rg.cancelar,
            conn, A, t1, "2026-10", "admin", "")
    levanta("exceção sem motivo", rg.DadoInvalido, rg.excecao,
            conn, A, t1, "2026-10", "admin", "")
    checar("e nada disso gravou linha nova", 2, conn.execute(
        "SELECT count(*) FROM car_evento WHERE acao='PRECO'").fetchone()[0])
    # 🚨 Do termo, o documento é o motivo -- e aí motivo não é exigido.
    e3 = rg.lancar_preco(conn, B, t2, "R$ 50,00", "2026-10", "admin",
                         fonte="termo", documento="sha256:abc")
    checar("preço vindo do termo não exige motivo", True, e3 > 0)
    checar("e a fonte fica gravada", "termo", conn.execute(
        "SELECT fonte FROM car_evento WHERE id=?", (e3,)).fetchone()[0])

    print("\n[3] 🚨 anular: uma vez só, e o anulado APARECE no histórico")
    a1 = rg.anular(conn, e2, "admin", "reajuste lançado no contrato errado")
    checar("a anulação entrou", True, a1 > 0)
    levanta("anular de novo levanta JaAnulado", rg.JaAnulado, rg.anular,
            conn, e2, "admin", "de novo")
    levanta("anular sem motivo", rg.DadoInvalido, rg.anular, conn, e1, "admin", "")
    levanta("anular evento que não existe", rg.DadoInvalido, rg.anular,
            conn, 99999, "admin", "x")
    h = rg.historico_de_preco(conn, t1)
    checar("o histórico segue com os dois", 2, len(h))
    checar("e marca qual está anulado", [False, True],
           [x["anulado"] for x in h])
    checar("em novembro o preço volta a ser o de outubro", "R$ 75,26",
           motor.preco_vigente(list(rg.pf.eventos_por_termo(conn)[t1]),
                               "2026-11")["valor_mensal"])

    print("\n[4] cancelar e renovar")
    rg.cancelar(conn, A, t1, "2026-12", "admin", "cliente encerrou o contrato")
    ev = rg.pf.eventos_por_termo(conn)[t1]
    checar("o cancelamento vale em dezembro", "2026-12",
           motor.cancelamento_vigente(ev, "2026-12")["competencia"])
    checar("e não vale em novembro", None,
           motor.cancelamento_vigente(ev, "2026-11"))
    rg.renovar(conn, A, t1, "2027-01", "admin", documento="sha256:def")
    checar("a renovação vale em janeiro", "2027-01", motor.renovacao_vigente(
        rg.pf.eventos_por_termo(conn)[t1], "2027-01")["competencia"])

    print("\n[5] 🚨 lote: idempotente, e um recusado não derruba os outros")
    conn2 = base()
    ta = termo(conn2, A, "10"); evento(conn2, ta, "AAA1A11")
    tb = termo(conn2, B, "20"); evento(conn2, tb, "BBB2B22")
    r = rg.lancar_preco_em_lote(conn2, [(A, ta), (B, tb)], "R$ 100,00",
                                "2026-10", "admin", "carga inicial de preço")
    checar("lançou os dois", 2, r["lancados"])
    checar("nenhum repetido", 0, r["repetidos"])
    checar("nenhum recusado", [], r["recusados"])
    r2 = rg.lancar_preco_em_lote(conn2, [(A, ta), (B, tb)], "R$ 100,00",
                                 "2026-10", "admin", "carga inicial de preço")
    checar("🚨 rodar de novo não lança nada", 0, r2["lancados"])
    checar("e conta os dois como repetidos", 2, r2["repetidos"])
    checar("o banco segue com dois PRECO", 2, conn2.execute(
        "SELECT count(*) FROM car_evento WHERE acao='PRECO'").fetchone()[0])
    # valor diferente é fato novo, e entra
    r3 = rg.lancar_preco_em_lote(conn2, [(A, ta)], "R$ 110,00", "2026-10",
                                 "admin", "correção do valor")
    checar("valor diferente entra", 1, r3["lancados"])
    # 🚨 um alvo inválido no meio
    r4 = rg.lancar_preco_em_lote(conn2, [(A, ta), (A, 99999), (B, tb)],
                                 "R$ 120,00", "2026-11", "admin", "reajuste")
    checar("os válidos entraram", 2, r4["lancados"])
    checar("e o inválido voltou nomeado", 1, len(r4["recusados"]))
    checar("com o motivo escrito", True, bool(r4["recusados"][0]["motivo"]))
    levanta("lote sem motivo", rg.DadoInvalido, rg.lancar_preco_em_lote,
            conn2, [(A, ta)], "R$ 1,00", "2026-10", "admin", "")
    levanta("lote sem valor", rg.DadoInvalido, rg.lancar_preco_em_lote,
            conn2, [(A, ta)], "", "2026-10", "admin", "motivo")

    print("\n[6] a fila de trabalho do lote vem da pré-fatura")
    conn3 = base()
    tg = termo(conn3, A, "30")
    for p in ("GGG1G11", "GGG2G22", "GGG3G33"):
        evento(conn3, tg, p)
    tp = termo(conn3, B, "40"); evento(conn3, tp, "PPP1P11")
    fila = rg.contratos_sem_valor(conn3, "2026-10")
    checar("os dois contratos estão na fila", 2, len(fila))
    checar("🚨 o de 3 placas vem primeiro", 3, fila[0]["sem_valor"])
    rg.lancar_preco_em_lote(conn3, [(A, tg)], "R$ 70,00", "2026-10", "admin",
                            "carga")
    fila = rg.contratos_sem_valor(conn3, "2026-10")
    checar("depois do lote, ele sai da fila", 1, len(fila))
    checar("e sobra o de 1 placa", "PPP1P11" and 1, fila[0]["sem_valor"])

    print("\n[7] 🚨 car_contrato: TODOS os termos, com situação e motivo")
    r = rg.recalcular_todos(conn3, "2026-10")
    checar("os 2 termos entraram", 2, r["termos"])
    checar("os dois ativos", 2, r["ativos"])
    linha = conn3.execute(
        "SELECT situacao, motivo, placas_ativas, placas_com_valor, "
        "placas_sem_valor, valor_mensal_total FROM car_contrato WHERE termo_id=?",
        (tg,)).fetchone()
    checar("situação ATIVO", "ATIVO", linha[0])
    checar("com motivo", True, "sustentadas" in linha[1])
    checar("3 placas", 3, linha[2])
    checar("3 com valor", 3, linha[3])
    checar("0 sem valor", 0, linha[4])
    checar("e o total somou as 3", "210,00", linha[5])
    sem = conn3.execute("SELECT valor_mensal_total, placas_sem_valor FROM "
                        "car_contrato WHERE termo_id=?", (tp,)).fetchone()
    checar("🚨 contrato sem valor tem total NULO, não '0,00'", None, sem[0])
    checar("e conta a placa sem valor", 1, sem[1])
    # idempotência: apaga e insere
    r = rg.recalcular_todos(conn3, "2026-10")
    checar("recalcular de novo não duplica", 2, conn3.execute(
        "SELECT count(*) FROM car_contrato").fetchone()[0])

    print("\n[8] termo não assinado: INATIVO, e a placa cobrável é DIVERGÊNCIA")
    r = rg.recalcular_todos(conn, "2026-10")
    linha = conn.execute("SELECT situacao, motivo, divergencia FROM car_contrato "
                         "WHERE termo_id=?", (t_nao,)).fetchone()
    checar("situação INATIVO", "INATIVO", linha[0])
    checar("motivo é a assinatura", "termo não assinado", linha[1])
    checar("🚨 e a divergência está escrita", True,
           "sem assinatura" in (linha[2] or ""))
    checar("o recalculo contou a divergência", True, r["divergencias"] >= 1)

    print("\n[9] 🚨 o módulo não ATUALIZA car_evento — medido no ast")
    import ast
    arvore = ast.parse((RAIZ / "fpsl_weso" / "painel" / "car_registro.py")
                       .read_text(encoding="utf-8"))
    docs = set()
    for no in [arvore] + [n for n in ast.walk(arvore)
                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                            ast.ClassDef))]:
        if no.body and isinstance(no.body[0], ast.Expr) and \
                isinstance(no.body[0].value, ast.Constant):
            docs.add(id(no.body[0].value))
    sql = "\n".join(n.value.upper() for n in ast.walk(arvore)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docs)
    checar("nenhum UPDATE car_evento", False, "UPDATE CAR_EVENTO" in sql)
    checar("nenhum UPDATE em nada", False, "UPDATE " in sql)
    checar("nenhum DELETE em car_evento", False, "DELETE FROM CAR_EVENTO" in sql)
    checar("o único DELETE é o da derivada car_contrato", 1,
           sql.count("DELETE FROM CAR_CONTRATO"))
    checar("nada de ALTER nem DROP", False, "ALTER " in sql or "DROP " in sql)

    conn.close(); conn2.close(); conn3.close()
    print("\n" + "=" * 52)
    print(f"{ok} verificações OK, {len(falhas)} falha(s)")
    for f in falhas:
        print(f"  FALHOU: {f}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
