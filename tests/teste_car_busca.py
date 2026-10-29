"""Busca das Contas a Receber (`CAR_1.1`) — etapa E5.

Banco TEMPORÁRIO em memória + um cache da WESO de mentira, em arquivo temporário.
Não toca o `fpsl.db` nem o cache real.

🚨 OS CASOS QUE ESTE TESTE EXISTE PARA FECHAR:
1. **`"2hm"` e `"2"` NÃO devolvem a base inteira.** Já aconteceu na CTR:
   extrair dígito de texto virava `"2"`, que casa com quase todo CNPJ.
2. **CNPJ alfanumérico É achado.** `WQ0P6GLD000108` tem letra e, pela regra
   "letra procura nome", cairia na busca por nome e nunca apareceria -- é
   exatamente o que acontece na Gestão de Contratos hoje.
3. **Número de termo repetido devolve OS DOIS**, dizendo quantos e de quais
   empresas. Escolher um calado esconderia o documento errado.
4. **A busca por ID em uso diz a IDADE do cache**, e cache ausente **não
   derruba a busca** -- devolve o motivo.
5. **`achou_por` sempre diz o degrau.** Sem isso o operador não distingue "não
   existe" de "procurei no campo errado".

Roda na VPS:  venv/bin/python tests/teste_car_busca.py
"""
import pathlib
import sqlite3
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import car_busca as b                      # noqa: E402
from fpsl_weso.painel import car_tabelas as car                  # noqa: E402
from fpsl_weso.painel import contratos_tabelas as ctr            # noqa: E402

ok, falhas = 0, []
A = "20480457000158"        # 2HM — o CNPJ que começa com "2"
B = "44213607000125"
ALFA = "WQ0P6GLD000108"     # CNPJ alfanumérico real, já na base do Harmonit


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
    ctr.criar(conn); ctr.migrar(conn); car.criar(conn); car.migrar(conn)
    for doc, nome in ((A, "2HM TRANSPORTES LTDA"), (B, "ZAGO COMERCIO LTDA"),
                      (ALFA, "VELASCO LEITE PASTELARIA ME")):
        conn.execute("INSERT INTO contrato_cliente (cnpj, nome, nome_fonte, "
                     "atualizado_em) VALUES (?,?,'teste','2026-10-28')", (doc, nome))
    conn.execute("INSERT INTO contrato_termo (cnpj, numero, empresa, tipo, "
                 "assinado, origem, enviado_em) VALUES (?, '2207', 'MOVISAT', "
                 "'CONTRATO', 1, 'teste', '2026-01-10')", (A,))
    conn.execute("INSERT INTO contrato_termo (cnpj, numero, empresa, tipo, "
                 "assinado, origem, enviado_em) VALUES (?, '2207', 'INSTITUTO', "
                 "'CONTRATO', 1, 'teste', '2026-01-10')", (A,))
    conn.execute("INSERT INTO contrato_termo (cnpj, numero, empresa, tipo, "
                 "assinado, origem, enviado_em) VALUES (?, '8838', 'MOVISAT', "
                 "'CONTRATO', 1, 'teste', '2026-01-10')", (B,))
    for doc, chave, texto in ((A, "ABC1D23", "ABC1D23"),
                              (B, "BUW8H32", "BUW8732")):
        conn.execute(
            "INSERT INTO contrato_placa (cnpj, placa_chave, placa_texto, situacao, "
            "base, termo_vigente, calculado_em) VALUES (?,?,?,'ATIVA','assinado',"
            "'2207','2026-10-28')", (doc, chave, texto))
    return conn


def cache_falso(serie="356354872124749", chave="ABC1D23",
                atualizado="2026-10-28T04:15:32"):
    caminho = tempfile.mktemp(suffix=".db")
    c = sqlite3.connect(caminho)
    c.execute("CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT)")
    c.execute("CREATE TABLE rastreadores (id INTEGER PRIMARY KEY, numero_serie TEXT)")
    c.execute("CREATE TABLE veiculos (id INTEGER PRIMARY KEY, placa TEXT, "
              "chave_placa TEXT, rastreador_id INTEGER)")
    c.execute("INSERT INTO meta VALUES ('atualizado_em', ?)", (atualizado,))
    c.execute("INSERT INTO rastreadores VALUES (1, ?)", (serie,))
    c.execute("INSERT INTO veiculos VALUES (10, ?, ?, 1)", (chave, chave))
    c.commit(); c.close()
    return caminho


def main():
    print("teste_car_busca — banco em :memory: + cache da WESO de mentira")
    conn = base()
    cache = cache_falso()

    print("\n[1] 🚨 a armadilha do \"2hm\" e do \"2\"")
    r = b.resolver(conn, "2hm", cache)
    checar("\"2hm\" acha por NOME", "nome", r["achou_por"])
    checar("e só o 2HM", [A], r["cnpjs"])
    r = b.resolver(conn, "2", cache)
    checar("\"2\" sozinho não acha nada", None, r["achou_por"])
    checar("e diz que é curto demais", True, "2 caracteres" in r["como"])
    r = b.resolver(conn, "22", cache)
    checar("\"22\" (2 dígitos) não devolve a base inteira", [], r["cnpjs"])
    r = b.resolver(conn, "204", cache)
    checar("🚨 \"204\" (3 dígitos) NÃO acha por CNPJ — o piso é 6", None,
           r["achou_por"])
    r = b.resolver(conn, "204804", cache)
    checar("\"204804\" (6 dígitos) acha por CNPJ", "cnpj", r["achou_por"])
    checar("e só o cliente certo", [A], r["cnpjs"])

    print("\n[1b] 🚨 número de termo vence pedaço de CNPJ (o EXATO ganha)")
    # `2048` é pedaço do CNPJ do cliente A **e** número de um termo. Medido na
    # base real em 28/10: buscar o termo `1000` devolvia "CNPJ contendo 1000"
    # com 67 clientes, porque o parcial rodava antes do exato.
    conn.execute("INSERT INTO contrato_termo (cnpj, numero, empresa, tipo, "
                 "assinado, origem, enviado_em) VALUES (?, '2048', 'MOVISAT', "
                 "'CONTRATO', 1, 'teste', '2026-01-10')", (B,))
    r = b.resolver(conn, "2048", cache)
    checar("acha por CONTRATO, não por CNPJ", "contrato", r["achou_por"])
    checar("e é o termo do cliente B", [B], r["cnpjs"])
    checar("o `como` diz que é número de termo", True,
           "número de termo 2048" in r["como"])

    print("\n[2] 🚨 CNPJ alfanumérico é achado — o que a CTR não faz hoje")
    checar("a forma é reconhecida", True, b.parece_documento(ALFA))
    checar("com pontuação também", True, b.parece_documento("WQ.0P6.GLD/0001-08"))
    checar("em caixa baixa também", True, b.parece_documento("wq0p6gld000108"))
    checar("CPF de 11 dígitos é documento", True, b.parece_documento("12345678901"))
    checar("CNPJ comum é documento", True, b.parece_documento(A))
    checar("🚨 letra nas 2 últimas NÃO é documento", False,
           b.parece_documento("WQ0P6GLD0001AB"))
    checar("13 posições não é documento", False, b.parece_documento("1234567890123"))
    checar("\"2hm\" não é documento", False, b.parece_documento("2hm"))
    r = b.resolver(conn, ALFA, cache)
    checar("e a busca acha por DOCUMENTO", "documento", r["achou_por"])
    checar("devolvendo o cliente", [ALFA], r["cnpjs"])
    r = b.resolver(conn, "WQ.0P6.GLD/0001-08", cache)
    checar("mascarado acha igual", [ALFA], r["cnpjs"])
    r = b.resolver(conn, "WQ0P6GLD000199", cache)
    checar("documento que não existe diz isso", None, r["achou_por"])
    checar("e não finge que procurou nome", True, "não está nesta base" in r["como"])

    print("\n[3] placa: compara pela chave, mostra o texto")
    r = b.resolver(conn, "BUW8732", cache)
    checar("acha por placa", "placa", r["achou_por"])
    checar("do cliente certo", [B], r["cnpjs"])
    checar("e mostra a placa como o termo escreveu", "BUW8732",
           r["placas"][0]["placa"])

    print("\n[4] 🚨 número de termo repetido devolve OS DOIS")
    r = b.resolver(conn, "2207", cache)
    checar("acha por contrato", "contrato", r["achou_por"])
    checar("com os dois termos", 2, len(r["termos"]))
    checar("e o `como` diz quantos", True, "2 termos com este número" in r["como"])
    checar("nomeando as empresas", True,
           "INSTITUTO" in r["como"] and "MOVISAT" in r["como"])
    r = b.resolver(conn, "8838", cache)
    checar("número único devolve um", 1, len(r["termos"]))
    checar("e o `como` não fala de dois", False, "termos com este" in r["como"])

    print("\n[5] 🚨 ID em uso: acha, e diz a idade do cache")
    r = b.resolver(conn, "356354872124749", cache)
    checar("acha por ID em uso", "id_em_uso", r["achou_por"])
    checar("do cliente da placa", [A], r["cnpjs"])
    checar("a idade do cache vem na resposta", True, r["cache"]["horas"] is not None)
    checar("e a data também", "2026-10-28T04:15:32", r["cache"]["atualizado_em"])
    checar("sem erro", None, r["cache"]["erro"])
    r = b.resolver(conn, "35635487", cache)
    checar("pedaço da série também acha", "id_em_uso", r["achou_por"])

    print("\n[6] cache ausente NÃO derruba a busca")
    r = b.resolver(conn, "356354872124749", "/tmp/nao_existe_este_cache.db")
    checar("não levanta, devolve vazio", None, r["achou_por"])
    checar("com o motivo em cache.erro", True, bool(r["cache"]["erro"]))
    checar("e o nome por CNPJ continua funcionando", "nome",
           b.resolver(conn, "zago", "/tmp/nao_existe.db")["achou_por"])

    print("\n[7] cache VELHO ainda procura, e diz a idade")
    velho = cache_falso(atualizado="2026-09-01T04:15:32")
    r = b.resolver(conn, "356354872124749", velho)
    checar("acha mesmo com cache de mês passado", "id_em_uso", r["achou_por"])
    checar("e a idade passa de 48 h", True, r["cache"]["horas"] > 48)

    print("\n[8] rastreador que existe mas cuja placa não está em contrato")
    orfao = cache_falso(serie="999999999999999", chave="ZZZ9Z99")
    r = b.resolver(conn, "999999999999999", orfao)
    checar("não acha cliente", None, r["achou_por"])
    checar("mas o `como` explica que a série existe na WESO", True,
           "está na WESO" in r["como"])

    print("\n[9] nada achado diz onde procurou")
    r = b.resolver(conn, "xxxxyyyy", cache)
    checar("achou_por nulo", None, r["achou_por"])
    checar("e o `como` lista os degraus", True,
           all(p in r["como"] for p in ("nome", "CNPJ", "placa", "termo", "série")))

    print("\n[10] todo retorno tem o mesmo formato")
    for q in ("2hm", "2", ALFA, "BUW8732", "2207", "356354872124749", "xxxxyyyy"):
        r = b.resolver(conn, q, cache)
        faltando = {"achou_por", "como", "q", "cnpjs", "termos", "placas",
                    "cache"} - set(r)
        checar(f"{q!r} devolve as 7 chaves", set(), faltando)

    for p in (cache, velho, orfao):
        pathlib.Path(p).unlink(missing_ok=True)
    conn.close()
    print("\n" + "=" * 52)
    print(f"{ok} verificações OK, {len(falhas)} falha(s)")
    for f in falhas:
        print(f"  FALHOU: {f}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
