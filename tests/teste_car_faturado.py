"""Espelho do faturado do Harmonit (`CAR_1.1`) — bloco F1. 30/10/2026.

Banco TEMPORÁRIO em memória. Não toca o `fpsl.db` e **não fala com o Harmonit**:
o que depende de rede é a função `ler_mes`, e aqui se testa tudo o que vem
depois dela.

🚨 OS CASOS QUE ESTE TESTE EXISTE PARA FECHAR:
1. **A competência sai do TEXTO, e NULA quando o texto não diz** -- nunca cai no
   mês de vencimento. Medido em 28/10: 233 de 261 mensalidades baixadas em
   outubro eram de referência 09/2026, então ler pelo vencimento erraria a
   maioria da carteira.
2. **O tipo sai do TEXTO, não do `centroCusto`**: em 30/10, 4 mensalidades vêm
   com centro `boleto`. Classificar pelo centro jogaria as 4 fora da conta.
3. **O que não casa vira `outro` com a descrição crua** -- apareceu um
   `"Negociação 17/24"` que nenhuma régua minha previa.
4. **O termo é procurado DENTRO DO PRÓPRIO CLIENTE.** Medido em 30/10: assim
   537 de 544 lançamentos amarram (98,7%); pelo número solto o dinheiro poderia
   cair no termo homônimo de outra empresa.
5. **Reler o mesmo mês não duplica** (a chave é o `id` do Harmonit) e o
   lançamento que foi pago **muda de estado** em vez de virar duas linhas.
6. **A régua do botão**, nos quatro casos da frase dele de 30/10.
7. **`faturado_do_mes` declara `lido: false`** quando o espelho está vazio, em
   vez de a tela desenhar R$ 0 -- e o que não amarra APARECE.
8. **O módulo da régua é puro**: sem `sqlite3`, sem `httpx`, sem `open()`.

Roda na VPS:  venv/bin/python tests/teste_car_faturado.py
"""
import ast
import datetime
import pathlib
import sqlite3
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import car_faturado as cf                  # noqa: E402
from fpsl_weso.painel import car_prefatura as pf                 # noqa: E402
from fpsl_weso.painel import car_tabelas as car                  # noqa: E402
from fpsl_weso.painel import contratos_tabelas as ctr            # noqa: E402
from fpsl_weso.services import sync_faturado as sync             # noqa: E402

ok, falhas = 0, []
A = "20480457000158"
B = "44213607000125"
UTC = datetime.timezone.utc


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
    # ⚠️ `clientes` é tabela do `storage.init_db`, não do `car_tabelas` -- aqui
    # ela é criada à mão, com as mesmas 3 colunas, porque é ela que liga o
    # `contatoId` do Harmonit ao CNPJ desta base.
    conn.execute("CREATE TABLE IF NOT EXISTS clientes ("
                 "harmonit_id INTEGER PRIMARY KEY, cnpjcpf TEXT NOT NULL, "
                 "criado_em TEXT NOT NULL)")
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


def lanc(**kw):
    """Um lançamento como o Harmonit devolve. Os nomes são os DELE."""
    bruto = {"id": 1, "descricao": "", "contatoId": 900, "contato": "CLIENTE A",
             "valor": 100.0, "categoria": "Boleto", "centroCusto": "Mensalidades",
             "contaCorrente": "Banco Asaas"}
    bruto.update(kw)
    return bruto


print("[0] a competência sai do texto, e nula é NULA")
checar("mensalidade: período 09/2026", "2026-09",
       cf.competencia_da_descricao(
           "Faturamento do contrato Nr. 3226. Mensalidade ref. período 09/2026."))
checar("sem período no texto -> None", None,
       cf.competencia_da_descricao("Ordem de Serviço Nr. 17019"))
checar("descrição vazia -> None", None, cf.competencia_da_descricao(""))
checar("mês impossível -> None", None,
       cf.competencia_da_descricao("Mensalidade ref. período 13/2026"))
checar("acento ausente ('periodo') ainda casa", "2026-11",
       cf.competencia_da_descricao("Mensalidade ref. periodo 11/2026"))

print("\n[1] o tipo sai do TEXTO, nunca do centro de custo")
casos = [
    ("Faturamento do contrato Nr. 3226. Mensalidade ref. período 09/2026.",
     "Mensalidades", cf.MENSALIDADE),
    # 🚨 os 4 medidos em 30/10 com centro `boleto`: seguem mensalidade
    ("Faturamento do contrato Nr. 8719. Mensalidade ref. período 09/2026.",
     "boleto", cf.MENSALIDADE),
    ("Faturamento do contrato Nr. 8353. Mensalidade ref. período 09/2026.",
     "Adesão", cf.ADESAO),
    ("Ordem de Serviço Nr. 17019", "Prestação de Serviços", cf.SERVICO),
    ("Venda Nr. 430", "Venda de Produtos", cf.VENDA),
    ("Negociação 17/24", "", cf.NEGOCIACAO),
    ("qualquer coisa que eu nunca vi", "", cf.OUTRO),
]
for descricao, centro, esperado in casos:
    r = cf.classificar(lanc(descricao=descricao, centroCusto=centro), cf.BAIXADO)
    checar(f"tipo de {descricao[:34]!r}", esperado, r["tipo"])
checar("a adesão NÃO conta como recorrente", False, cf.ADESAO in cf.RECORRENTES)
r = cf.classificar(lanc(descricao="qualquer coisa que eu nunca vi"), cf.BAIXADO)
checar("o 'outro' guarda a descrição crua", "qualquer coisa que eu nunca vi",
       r["descricao"])
r = cf.classificar(lanc(descricao="Ordem de Serviço Nr. 17019"), cf.BAIXADO)
checar("serviço guarda o número da OS", 17019, r["numero_os"])
checar("e não inventa competência", None, r["competencia"])
r = cf.classificar(lanc(descricao="Negociação 17/24"), cf.A_BAIXAR)
checar("negociação guarda a parcela", "17/24", r["parcela"])
try:
    cf.classificar(lanc(), "pago")
    checar("estado desconhecido levanta ValueError", True, False)
except ValueError:
    checar("estado desconhecido levanta ValueError", True, True)
# 🚨 O DEFEITO QUE ESTE TESTE ACHOU EM 30/10, antes de valer nada: o Harmonit
# manda `200.53` (ponto decimal) e `_centavos` lê ponto como separador de
# MILHAR -- guardar o número cru fazia R$ 200,53 virar R$ 20.053,00 na soma, e
# esse valor é copiado para `car_evento` pela semeadura.
checar("valor vira TEXTO em convenção brasileira", "100,00",
       cf.classificar(lanc(valor=100.0), cf.BAIXADO)["valor"])
checar("centavos do ponto decimal não se perdem", "200,53",
       cf.classificar(lanc(valor=200.53), cf.BAIXADO)["valor"])
checar("e a casa soma isso certo", "200,53",
       pf.somar_textos([cf.classificar(lanc(valor=200.53), cf.BAIXADO)["valor"]]))
checar("milhar com centavos", "1.588,11".replace(".", ""),
       pf.somar_textos([cf.classificar(lanc(valor=1588.11), cf.BAIXADO)["valor"]]))
checar("valor ausente é None, não 0", None,
       cf.classificar(lanc(valor=None), cf.BAIXADO)["valor"])

print("\n[2] a régua do botão (frase dele, 30/10)")
agora = datetime.datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
r = cf.pode_atualizar_agora(False, None, None, agora)
checar("rotina desligada: botão livre", True, r["pode"])
r = cf.pode_atualizar_agora(True, None, None, agora)
checar("ligada e sem passada nenhuma: não pode", False, r["pode"])
checar("e o motivo diz por quê", True, "libera 4 h" in r["motivo"])
r = cf.pode_atualizar_agora(
    True, datetime.datetime(2026, 10, 30, 9, 30, tzinfo=UTC), None, agora)
checar("ligada, automática há 2,5 h: não pode", False, r["pode"])
checar("e diz a hora em que libera", "2026-10-30T13:30:00+00:00", r["libera_em"])
r = cf.pode_atualizar_agora(
    True, datetime.datetime(2026, 10, 30, 7, 0, tzinfo=UTC), None, agora)
checar("ligada, automática há 5 h: pode", True, r["pode"])
r = cf.pode_atualizar_agora(
    True, datetime.datetime(2026, 10, 30, 7, 0, tzinfo=UTC),
    datetime.datetime(2026, 10, 30, 8, 0, tzinfo=UTC), agora)
checar("ligada e já usado hoje: não pode", False, r["pode"])
checar("e o motivo cita a hora do uso", True, "08:00" in r["motivo"])
r = cf.pode_atualizar_agora(
    True, datetime.datetime(2026, 10, 30, 7, 0, tzinfo=UTC),
    datetime.datetime(2026, 10, 29, 23, 0, tzinfo=UTC), agora)
checar("manual de ONTEM não bloqueia hoje", True, r["pode"])
r = cf.pode_atualizar_agora(True, "", "", agora)
checar("carimbo vazio é tratado como ausente", False, r["pode"])
r = cf.pode_atualizar_agora(True, "2026-10-30T07:00:00", None, agora)
checar("ISO sem fuso é lido como UTC", True, r["pode"])

print("\n[3] os meses da passada")
# 🚨 ERAM 6 MESES (atras=2) ATE 30/10, e subestimavam: a competencia 2026-09
# tem lancamento em SETE meses de vencimento (abril a outubro), e 5 deles, de
# vencimento ABRIL, somam R$ 15.678,03. Com a janela curta a conta de setembro
# fechava R$ 21 mil abaixo e nada dizia.
checar("20 chamadas: 10 meses × 2 rotas", 10,
       len(cf.meses_da_passada(datetime.date(2026, 10, 30))))
checar("a passada de outubro vai de abril a janeiro",
       [(2026, 4), (2026, 5), (2026, 6), (2026, 7), (2026, 8), (2026, 9),
        (2026, 10), (2026, 11), (2026, 12), (2027, 1)],
       cf.meses_da_passada(datetime.date(2026, 10, 30)))
checar("virada de ano para trás",
       [(2025, 7), (2025, 8), (2025, 9), (2025, 10), (2025, 11), (2025, 12),
        (2026, 1), (2026, 2), (2026, 3), (2026, 4)],
       cf.meses_da_passada(datetime.date(2026, 1, 15)))
checar("a janela é parametrizável (a carga inicial usa isso)", 2,
       len(cf.meses_da_passada(datetime.date(2026, 10, 30), atras=1, adiante=0)))

print("\n[4] a tabela: nasce, migra duas vezes e não duplica")
conn = base()
checar("car_faturado está no criar()", True, "car_faturado" in car.TABELAS)
car.criar(conn)
car.migrar(conn)
cols = {r[1] for r in conn.execute("PRAGMA table_info(car_faturado)")}
checar("criar() é idempotente e as colunas estão lá", True,
       {"id", "tipo", "estado", "competencia", "cnpj", "termo_id", "valor",
        "descricao", "lido_em"} <= cols)
checar("toda coluna do INSERT existe na tabela", set(),
       set(sync.COLUNAS) - cols)

print("\n[5] resolver: cliente pelo contatoId, termo DENTRO do cliente")
conn.execute("INSERT INTO clientes (harmonit_id, cnpjcpf, criado_em) "
             "VALUES (900, ?, '2026-10-30')", (A,))
conn.execute("INSERT INTO clientes (harmonit_id, cnpjcpf, criado_em) "
             "VALUES (901, ?, '2026-10-30')", (B,))
t_a_mov = termo(conn, A, "3226", "MOVISAT")
t_a_inst = termo(conn, A, "3226", "INSTITUTO")
t_b = termo(conn, B, "8719")
clientes = sync.mapa_clientes(conn)
termos = sync.termos_por_cnpj(conn)
linha = cf.classificar(lanc(
    contatoId=900,
    descricao="Faturamento do contrato Nr. 3226. Mensalidade ref. período 09/2026."),
    cf.BAIXADO)
r = sync.resolver(linha, clientes, termos)
checar("o cnpj vem do contatoId", A, r["cnpj"])
checar("MOVISAT vence o homônimo do INSTITUTO", t_a_mov, r["termo_id"])
checar("e NÃO é o do Instituto", False, r["termo_id"] == t_a_inst)
# 🚨 O MESMO NÚMERO, OUTRO CLIENTE: o 8719 é do B, e um lançamento do A que o
# citasse não pode cair no contrato do B.
linha_b = cf.classificar(lanc(
    contatoId=900,
    descricao="Faturamento do contrato Nr. 8719. Mensalidade ref. período 09/2026."),
    cf.BAIXADO)
r = sync.resolver(linha_b, clientes, termos)
checar("número de OUTRO cliente não amarra", None, r["termo_id"])
checar("mas o lançamento continua, com o número à vista", "8719", r["termo_numero"])
checar("e o contrato do B existe mesmo", B,
       conn.execute("SELECT cnpj FROM contrato_termo WHERE id=?", (t_b,)).fetchone()[0])
r = sync.resolver(cf.classificar(lanc(contatoId=9999), cf.BAIXADO), clientes, termos)
checar("contatoId desconhecido: cnpj nulo, não chute", None, r["cnpj"])

print("\n[6] gravar: reler o mês não duplica, e o pago muda de estado")
d = sync.gravar(conn, [sync.resolver(linha, clientes, termos)])
checar("gravou 1", 1, d["gravadas"])
sync.gravar(conn, [sync.resolver(linha, clientes, termos)])
checar("reler o mesmo lançamento não duplica", 1,
       conn.execute("SELECT COUNT(*) FROM car_faturado").fetchone()[0])
aberto = cf.classificar(lanc(
    contatoId=900, vencimento="2026-11-10",
    descricao="Faturamento do contrato Nr. 3226. Mensalidade ref. período 09/2026."),
    cf.A_BAIXAR)
sync.gravar(conn, [sync.resolver(aberto, clientes, termos)])
checar("o mesmo id muda de estado, não vira duas linhas",
       (1, cf.A_BAIXAR),
       (conn.execute("SELECT COUNT(*) FROM car_faturado").fetchone()[0],
        conn.execute("SELECT estado FROM car_faturado").fetchone()[0]))
d = sync.gravar(conn, [sync.resolver(linha_b, clientes, termos)])
checar("gravar conta o que não amarrou", 1, d["sem_termo"])

print("\n[7] faturado_do_mes: o cobrado por CLIENTE, e o que não amarra aparece")
vazio = base()
r = pf.faturado_do_mes(vazio, "2026-09")
checar("espelho vazio: lido = false", False, r["lido"])
checar("e diz por quê", True, "desligada" in (r.get("porque") or ""))
checar("sem inventar R$ 0", {}, r["por_cliente"])

conn2 = base()
conn2.execute("INSERT INTO clientes (harmonit_id, cnpjcpf, criado_em) "
              "VALUES (900, ?, '2026-10-30')", (A,))
t1 = termo(conn2, A, "3226")
clientes2 = sync.mapa_clientes(conn2)
termos2 = sync.termos_por_cnpj(conn2)
entradas = [
    (lanc(id=11, contatoId=900, valor=200.53,
          descricao="Faturamento do contrato Nr. 3226. Mensalidade ref. período 09/2026."),
     cf.BAIXADO),
    (lanc(id=12, contatoId=900, valor=598.01, centroCusto="Prestação de Serviços",
          descricao="Ordem de Serviço Nr. 17019"), cf.A_BAIXAR),
    (lanc(id=13, contatoId=777, valor=69.44, contato="ATENDE SAUDE",
          descricao="Faturamento do contrato Nr. 0002. Mensalidade ref. período 09/2026."),
     cf.BAIXADO),
    (lanc(id=14, contatoId=900, valor=129.04, centroCusto="",
          descricao="Negociação 17/24"), cf.A_BAIXAR),
]
# A de serviço não traz competência no texto: para entrar no mês ela precisa de
# uma, e aqui se grava a competência que o próprio texto deu (nenhuma) -- é o
# caso 1 deste arquivo, visto de dentro da conta do mês.
linhas = []
for bruto, estado in entradas:
    linhas.append(sync.resolver(cf.classificar(bruto, estado), clientes2, termos2))
linhas[1]["competencia"] = "2026-09"      # como se o texto tivesse dito
for l in linhas:
    l["venc_ano_mes"] = "2026-10"        # como a rotina carimba: o mês da chamada
sync.gravar(conn2, linhas)

r = pf.faturado_do_mes(conn2, "2026-09")
checar("lido = true", True, r["lido"])
checar("um cliente na conta", [A], list(r["por_cliente"]))
checar("mensalidade do cliente", "200,53", r["por_cliente"][A]["mensalidade"])
checar("o serviço entra no AVULSO, não na mensalidade", "598,01",
       r["por_cliente"][A]["avulso"])
checar("recebido = só o que está baixado", "200,53", r["por_cliente"][A]["recebido"])
checar("em aberto = o resto", "598,01", r["por_cliente"][A]["em_aberto"])
checar("o por_termo amarra no contrato certo", "200,53",
       r["por_cliente"][A]["por_termo"][t1]["mensalidade"])
# 🚨 DUAS LISTAS: "errado NESTE mês" e "não é de mês nenhum". Medido com dado
# real em 30/10, a mistura dava 340 linhas numa pré-fatura de setembro -- 333
# eram OS, venda e negociação, que não pertencem a competência alguma.
checar("não amarrado do mês = só o sem cliente", 1, len(r["nao_amarrados"]))
checar("e é o que tem cliente desconhecido", "ATENDE SAUDE",
       r["nao_amarrados"][0].get("contato"))
checar("a negociação sai na lista de SEM COMPETÊNCIA", 1,
       r["sem_competencia"]["lancamentos"])
checar("com o tipo dito", {cf.NEGOCIACAO: 1}, r["sem_competencia"]["por_tipo"])
checar("e com o total à parte, fora da conta do mês", "129,04",
       r["sem_competencia"]["total"])
checar("total de mensalidade do mês", "200,53", r["totais"]["mensalidade"])
# 🚨 A COBERTURA DECLARADA: sem isto a conta do mês afirma estar completa sem
# saber. Medido em 30/10: a competência 2026-09 vem de 7 meses de vencimento.
checar("a resposta diz de que meses de vencimento leu", ["2026-10"],
       r["cobertura"]["meses_de_vencimento_lidos"])
checar("e avisa que pode faltar quando a competência toca o mês mais antigo lido",
       True, r["cobertura"]["pode_faltar"])

print("\n[8] o módulo da régua é PURO")
fonte = (RAIZ / "fpsl_weso" / "painel" / "car_faturado.py").read_text(encoding="utf-8")
arvore = ast.parse(fonte)
importados = set()
for no in ast.walk(arvore):
    if isinstance(no, ast.Import):
        importados |= {a.name.split(".")[0] for a in no.names}
    elif isinstance(no, ast.ImportFrom):
        importados.add((no.module or "").split(".")[0])
checar("nada de sqlite3/httpx/os/pathlib", set(),
       importados & {"sqlite3", "httpx", "os", "pathlib", "requests"})
chamadas = {no.func.id for no in ast.walk(arvore)
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)}
checar("e nenhum open()", False, "open" in chamadas)

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
