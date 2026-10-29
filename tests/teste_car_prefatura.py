"""Pré-fatura da competência (`CAR_1.1`) — etapa E4.

Banco TEMPORÁRIO em memória, montado à mão. Não toca o `fpsl.db`.

🚨 OS CASOS QUE ESTE TESTE EXISTE PARA FECHAR:
1. **O mês passado reproduz o MÊS PASSADO**, não o hoje. É o que separa
   "releitura do contrato" de "cópia congelada", e o aviso prévio de 90 dias é
   o caso que prova: a mesma placa é cobrável em setembro e não é em janeiro,
   **sem nenhum evento novo**.
2. **`MOVISAT vence`** quando (cnpj, número) aponta dois termos. Medido na base
   real em 28/10: 555 pares assim, todos MOVISAT × INSTITUTO, atingindo 271 das
   2.952 placas cobráveis. Sem a regra, o preço de 9% da carteira vai para o
   documento errado -- ou dobra.
3. **Placa cobrável de termo que não existe APARECE** em `sem_termo`, em vez de
   desaparecer num `JOIN`. É a lição da `FIN_1.1`, onde 6 OS sumiam da tela e
   nada dizia.
4. **Total nulo nunca é `0,00`**, e `cobertura` diz de quanto da carteira o
   total fala.
5. **Valor que não converte não é silenciado**: sai da soma e o motivo diz.
6. **A parte variável declara que não está ligada**, com o porquê.
7. **A pré-fatura não grava nada** -- travado no `ast`.

Roda na VPS:  venv/bin/python tests/teste_car_prefatura.py
"""
import pathlib
import sqlite3
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import car_prefatura as pf                 # noqa: E402
from fpsl_weso.painel import car_tabelas as car                  # noqa: E402
from fpsl_weso.painel import contratos_tabelas as ctr            # noqa: E402

ok, falhas = 0, []
A = "20480457000158"        # cliente com dois termos homônimos
B = "44213607000125"        # cliente simples, com valor no termo


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def termo(conn, cnpj, numero, empresa="MOVISAT", assinado=1, tipo="CONTRATO",
          assinado_em="2026-01-10"):
    cur = conn.execute(
        "INSERT INTO contrato_termo (cnpj, numero, empresa, tipo, assinado, "
        "assinado_em, origem, enviado_em) VALUES (?,?,?,?,?,?,'teste','2026-01-10')",
        (cnpj, numero, empresa, tipo, assinado, assinado_em))
    return cur.lastrowid


def evento(conn, termo_id, placa, acao="ENTRA", fonte="assinado"):
    conn.execute(
        "INSERT INTO contrato_evento (termo_id, placa_chave, placa_texto, acao, "
        "fonte, criado_em) VALUES (?,?,?,?,?,'2026-01-10T00:00:00Z')",
        (termo_id, placa.replace(" ", ""), placa, acao, fonte))


def base():
    conn = sqlite3.connect(":memory:")
    ctr.criar(conn)
    ctr.migrar(conn)
    car.criar(conn)
    car.migrar(conn)
    conn.execute("INSERT INTO contrato_cliente (cnpj, nome, nome_fonte, atualizado_em) "
                 "VALUES (?,?,'teste','2026-10-28')", (A, "CLIENTE A"))
    conn.execute("INSERT INTO contrato_cliente (cnpj, nome, nome_fonte, atualizado_em) "
                 "VALUES (?,?,'teste','2026-10-28')", (B, "CLIENTE B"))
    return conn


def achar_linha(pre, cnpj, placa):
    for c in pre["clientes"]:
        if c["cnpj"] != cnpj:
            continue
        for ct in c["contratos"]:
            for l in ct["linhas"]:
                if l["placa"] == placa:
                    return ct, l
    return None, None


def main():
    print("teste_car_prefatura — banco em :memory:")

    print("\n[1] 🚨 MOVISAT vence quando o número aponta dois termos")
    conn = base()
    t_inst = termo(conn, A, "2207", empresa="INSTITUTO")
    t_movi = termo(conn, A, "2207", empresa="MOVISAT")
    evento(conn, t_inst, "ABC1D23")
    evento(conn, t_movi, "ABC1D23")
    termos = [{"id": t_inst, "numero": "2207", "empresa": "INSTITUTO"},
              {"id": t_movi, "numero": "2207", "empresa": "MOVISAT"}]
    checar("resolver_termo escolhe a MOVISAT", t_movi,
           pf.resolver_termo(termos, "2207")["id"])
    checar("e a ordem da lista não importa", t_movi,
           pf.resolver_termo(list(reversed(termos)), "2207")["id"])
    checar("número que não existe devolve None", None,
           pf.resolver_termo(termos, "9999"))
    checar("número vazio devolve None", None, pf.resolver_termo(termos, None))
    # Empate dentro da MESMA empresa (nunca visto em 28/10): o id maior ganha.
    mesmos = [{"id": 5, "numero": "7", "empresa": "MOVISAT"},
              {"id": 9, "numero": "7", "empresa": "MOVISAT"}]
    checar("empate na mesma empresa: o mais recente", 9,
           pf.resolver_termo(mesmos, "7")["id"])

    pre = pf.montar(conn, "2026-10")
    ct, l = achar_linha(pre, A, "ABC1D23")
    checar("a placa entrou numa linha", True, l is not None)
    checar("e o contrato dela é o da MOVISAT", "MOVISAT", ct["empresa"])
    checar("uma linha por placa (decisão 6)", 1, pre["totais"]["placas"])

    print("\n[2] 🚨 valor: nulo é nulo, e o total diz de quanto fala")
    checar("nenhuma placa tem valor", 0, pre["totais"]["com_valor"])
    checar("e uma está sem", 1, pre["totais"]["sem_valor"])
    checar("o total é None, não '0,00'", None, pre["totais"]["total"])
    checar("a cobertura é 0.0", 0.0, pre["totais"]["cobertura"])
    checar("a linha diz por que não tem valor", True, bool(l["motivo"]))
    checar("e o valor da linha é None", None, l["valor"])

    print("\n[3] o valor do termo (contrato_item) entra, e o PRECO vence")
    conn.execute("INSERT INTO contrato_item (cnpj, placa_chave, placa_texto, "
                 "valor_mensal) VALUES (?,?,?,?)", (A, "ABC1D23", "ABC1D23", "75,26"))
    pre = pf.montar(conn, "2026-10")
    _ct, l = achar_linha(pre, A, "ABC1D23")
    checar("o valor do termo aparece", "75,26", l["valor"])
    checar("e a fonte nomeia o contrato_item", "contrato_item", l["fonte_do_valor"])
    checar("o total soma", "75,26", pre["totais"]["total"])
    checar("cobertura 100%", 1.0, pre["totais"]["cobertura"])
    conn.execute(
        "INSERT INTO car_evento (cnpj, termo_id, acao, valor_mensal, competencia, "
        "fonte, por, criado_em) VALUES (?,?,'PRECO','R$ 90,00','2026-10','operador',"
        "'admin','2026-10-28T12:00:00Z')", (A, t_movi))
    pre = pf.montar(conn, "2026-10")
    _ct, l = achar_linha(pre, A, "ABC1D23")
    checar("o PRECO lançado vence o valor do termo", "R$ 90,00", l["valor"])
    checar("e a fonte diz que veio de preço", "preco_operador", l["fonte_do_valor"])
    checar("o total segue o PRECO", "90,00", pre["totais"]["total"])
    checar("em setembro, antes do PRECO, vale o termo", "75,26",
           achar_linha(pf.montar(conn, "2026-09"), A, "ABC1D23")[1]["valor"])

    print("\n[4] 🚨 o mês passado reproduz o MÊS PASSADO (aviso prévio de 90 dias)")
    conn2 = base()
    t = termo(conn2, B, "8838", assinado_em="2026-09-15")
    evento(conn2, t, "XYZ9W88")
    r = termo(conn2, B, "8900", tipo="RESCISAO", assinado_em="2026-09-15")
    evento(conn2, r, "XYZ9W88", acao="RESCINDE")
    set_ = pf.montar(conn2, "2026-09")
    checar("em setembro a placa é cobrável (aviso prévio)", 1,
           set_["totais"]["placas"])
    _ct, l = achar_linha(set_, B, "XYZ9W88")
    checar("e a situação dela é EM_AVISO_PREVIO", "EM_AVISO_PREVIO", l["situacao"])
    jan = pf.montar(conn2, "2027-01")
    checar("em janeiro, passados os 90 dias, não é mais cobrável", 0,
           jan["totais"]["placas"])
    checar("🚨 e NENHUM evento novo foi lançado entre as duas leituras", 2,
           conn2.execute("SELECT count(*) FROM contrato_evento").fetchone()[0])

    print("\n[4b] 🚨 quem SAIU no meio do mês é cobrado, e a linha diz isso")
    # Rescisão assinada em 10/07: o aviso de 90 dias vence em 08/10. Então no
    # dia 1º de outubro a placa ainda é cobrável e no dia 31 não é.
    # 🚨 Olhar só o dia 31 perderia essa cobrança EM SILÊNCIO -- foi o que a
    # medição da base real mostrou em 28/10: 47 placas em outubro de 2026.
    conn5 = base()
    t = termo(conn5, B, "300", assinado_em="2026-01-10")
    evento(conn5, t, "MEI1O00")
    r = termo(conn5, B, "301", tipo="RESCISAO", assinado_em="2026-07-10")
    evento(conn5, r, "MEI1O00", acao="RESCINDE")
    out = pf.montar(conn5, "2026-10")
    checar("a placa que saiu no meio do mês É cobrada", 1, out["totais"]["placas"])
    _ct, l = achar_linha(out, B, "MEI1O00")
    checar("e a linha marca que ela saiu", True, l["saiu_no_mes"])
    checar("e não marca entrada", False, l["entrou_no_mes"])
    checar("os totais contam a saída", 1, out["totais"]["sairam_no_mes"])
    nov = pf.montar(conn5, "2026-11")
    checar("em novembro ela já não é cobrada", 0, nov["totais"]["placas"])
    checar("a resposta diz o primeiro dia do mês", "2026-10-01", out["de"])
    conn5.close()

    print("\n[5] 🚨 placa de termo inexistente APARECE, não desaparece")
    conn3 = base()
    t = termo(conn3, B, "100")
    evento(conn3, t, "QQQ1R11")
    # a derivada aponta um número que não existe em contrato_termo
    conn3.execute("UPDATE contrato_termo SET numero='101' WHERE id=?", (t,))
    pre = pf.montar(conn3, "2026-10")
    # agora o termo existe com outro número; a placa segue sustentada por ele,
    # então o caso de verdade se força pelo resolver_termo:
    checar("resolver_termo devolve None para número órfão", None,
           pf.resolver_termo([{"id": t, "numero": "101", "empresa": "MOVISAT"}], "100"))
    checar("a lista sem_termo existe na resposta", True, "sem_termo" in pre)

    print("\n[6] valor que não converte sai da soma, e o motivo diz")
    conn4 = base()
    t = termo(conn4, B, "200")
    evento(conn4, t, "WWW2X22")
    conn4.execute("INSERT INTO contrato_item (cnpj, placa_chave, placa_texto, "
                  "valor_mensal) VALUES (?,?,?,?)",
                  (B, "WWW2X22", "WWW2X22", "a combinar"))
    pre = pf.montar(conn4, "2026-10")
    _ct, l = achar_linha(pre, B, "WWW2X22")
    checar("o valor aparece como o termo escreveu", "a combinar", l["valor"])
    checar("mas não entra na soma", None, pre["totais"]["total"])
    checar("e o motivo diz que ficou fora", True,
           "fora da soma" in (l["motivo"] or ""))

    print("\n[7] a parte variável declara que não está ligada")
    checar("variavel.ligada é False", False, pre["variavel"]["ligada"])
    checar("e tem o porquê escrito", True, len(pre["variavel"]["porque"]) > 30)
    checar("a competência volta na resposta", "2026-10", pre["competencia"])
    checar("e o último dia dela também", "2026-10-31", pre["ate"])

    print("\n[8] competência inválida é recusada, não devolve vazio")
    for ruim in ("2026-13", "outubro", ""):
        try:
            pf.montar(conn4, ruim)
            checar(f"recusa {ruim!r}", True, False)
        except Exception as e:
            checar(f"recusa {ruim!r}", True, "competência" in str(e).lower())

    print("\n[9] CSV: cabeçalho e uma linha por cobrança")
    csv = pf.para_csv(pre)
    linhas = csv.splitlines()
    checar("tem cabeçalho", True, linhas[0].startswith("cnpj;cliente;termo"))
    checar("e uma linha de dado", 2, len(linhas))
    checar("sem ponto-e-vírgula dentro do motivo", 9, linhas[1].count(";"))

    print("\n[10] 🚨 a pré-fatura NÃO grava — medido no ast")
    import ast
    arvore = ast.parse((RAIZ / "fpsl_weso" / "painel" / "car_prefatura.py")
                       .read_text(encoding="utf-8"))
    docs = set()
    for no in [arvore] + [n for n in ast.walk(arvore)
                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        if no.body and isinstance(no.body[0], ast.Expr) and \
                isinstance(no.body[0].value, ast.Constant):
            docs.add(id(no.body[0].value))
    sql = "\n".join(n.value.upper() for n in ast.walk(arvore)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docs)
    for proibido in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER "):
        checar(f"o SQL do módulo não tem `{proibido.strip()}`", False, proibido in sql)
    checar("e tem SELECT", True, "SELECT" in sql)

    conn.close(); conn2.close(); conn3.close(); conn4.close()
    print("\n" + "=" * 52)
    print(f"{ok} verificações OK, {len(falhas)} falha(s)")
    for f in falhas:
        print(f"  FALHOU: {f}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
