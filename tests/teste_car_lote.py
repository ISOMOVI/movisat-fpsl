"""O lote de contas a receber (`CAR_1.1`, blocos G1 · G4 · G5). 2026-11-03.

🚨 MÓDULO PURO, TESTE PURO. A pré-fatura e a fila variável entram como dicionário
já montado -- é o que permite provar o encaixe das duas unidades (contrato e OS)
sem banco, sem WESO e sem Harmonit.

🚨 OS CASOS SÃO OS CLIENTES REAIS DE 30/10, com os números medidos: a XOMV
(fatura no contrato 306 e usa 71 placas no 8802 -- a amarração), a MOTO HELP
(bate: 8711 fatura e sustenta) e a OS 16846, cujo cliente não está nesta base.

Roda na VPS:  venv/bin/python tests/teste_car_lote.py
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.painel import car_lote as cl                          # noqa: E402
from fpsl_weso.painel import car_variavel as cv                      # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


def contrato(termo_id, numero, placas, valor=None, cobrado=None, em_uso=None):
    """Um contrato da pré-fatura, no formato que `car_prefatura.montar` devolve."""
    return {
        "termo_id": termo_id, "numero": numero, "empresa": "MOVISAT",
        "assinado": True, "situacao": "ATIVO", "motivo": "", "divergencia": None,
        "placas": placas, "com_valor": placas if valor else 0,
        "sem_valor": 0 if valor else placas,
        "em_uso": em_uso, "contratadas_sem_uso": None,
        "faturado": {"mensalidade": cobrado} if cobrado else {},
        "linhas": [{"placa": f"ZZZ{i}", "valor": valor,
                    "fonte_do_valor": "faturado do Harmonit" if valor else None,
                    "motivo": None, "em_uso_weso": True, "situacao_weso": "Instalado"}
                   for i in range(placas)],
    }


def cliente(cnpj, nome, contratos, faturado=None, em_uso_sem_faturar=False):
    return {"cnpj": cnpj, "nome": nome, "contratos": contratos,
            "placas": sum(c["placas"] for c in contratos),
            "com_valor": 0, "sem_valor": 0, "em_uso": None,
            "contratadas_sem_uso": None,
            "em_uso_sem_faturar": em_uso_sem_faturar,
            "faturado": faturado or {}}


# ─────────────────────────────────────────────────────────────────────────────
print("\n[1] a descrição é a DO HARMONIT, e o espelho tem de reconhecê-la")
# 🚨 Não é estilo: é esta frase que o `car_faturado.RE_CONTRATO` e o
# `RE_COMPETENCIA` sabem ler. Gerar outro texto faria o próprio lançamento da
# CAR cair em "não amarrado" na passada seguinte do espelho.
from fpsl_weso.painel import car_faturado as cf                      # noqa: E402

desc = cl.descricao_mensalidade("8711", "2026-09")
checar("a frase da mensalidade",
       "Faturamento do contrato Nr. 8711. Mensalidade ref. período 09/2026.", desc)
checar("o espelho acha o contrato nela", "8711",
       cf.RE_CONTRATO.search(desc).group(1))
checar("e acha a competencia", "2026-09", cf.competencia_da_descricao(desc))
checar("o espelho a classifica como mensalidade", cf.MENSALIDADE,
       cf.classificar({"descricao": desc, "centroCusto": cl.CENTRO_MENSALIDADE},
                      cf.A_BAIXAR)["tipo"])

serv = cl.descricao_servico(16896)
checar("a frase do servico", "Ordem de Serviço Nr. 16896", serv)
checar("o espelho acha a OS nela", 16896,
       cf.classificar({"descricao": serv, "centroCusto": cl.CENTRO_SERVICO},
                      cf.A_BAIXAR)["numero_os"])
checar("e a classifica como servico", cf.SERVICO,
       cf.classificar({"descricao": serv, "centroCusto": cl.CENTRO_SERVICO},
                      cf.A_BAIXAR)["tipo"])

print("\n[2] o centro de custo e a categoria são os MEDIDOS, não inventados")
checar("mensalidade", "Mensalidades", cl.CENTRO_MENSALIDADE)
checar("categoria da mensalidade", "Boleto", cl.CATEGORIA_MENSALIDADE)
checar("servico", "Prestação de Serviços", cl.CENTRO_SERVICO)
checar("categoria do servico", "Serviços", cl.CATEGORIA_SERVICO)

print("\n[3] a competência por extenso")
checar("2026-09", "setembro de 2026", cl.competencia_por_extenso("2026-09"))
checar("2026-01", "janeiro de 2026", cl.competencia_por_extenso("2026-01"))
checar("texto torto volta como veio", "lixo", cl.competencia_por_extenso("lixo"))

# ─────────────────────────────────────────────────────────────────────────────
print("\n[4] UM DOCUMENTO POR CLIENTE, com fixo e variável SEPARADOS")
pre = {
    "competencia": "2026-09",
    "clientes": [
        # MOTO HELP: o 8711 fatura E sustenta as placas -- o caso que bate.
        cliente("07098192000160", "zz MOTO HELP",
                [contrato(8711, "8711", 3, valor="1.841,03", cobrado="5.523,10",
                          em_uso=2)],
                faturado={"mensalidade": "5.523,10", "avulso": None,
                          "recebido": "5.523,10", "em_aberto": None,
                          "lancamentos": 1}),
        # XOMV: o Harmonit fatura no 306, que NÃO sustenta placa -- a amarração.
        cliente("18522913000133", "zz XOMV",
                [contrato(8802, "8802", 2)],
                faturado={"mensalidade": "9.609,65", "avulso": None,
                          "recebido": None, "em_aberto": "9.609,65",
                          "lancamentos": 1}),
    ],
    "sem_termo": [],
    "totais": {"clientes": 2, "placas": 5, "sem_valor": 2, "com_valor": 3},
    # 🚨 As LINHAS do espelho vivem aqui, em `faturado.por_cliente` -- é delas
    # que sai a amarração. O `faturado` resumido do cliente traz só as somas,
    # e foi por isso que a primeira versão desta régua não achava nada.
    "faturado": {"lido": True, "por_cliente": {
        "07098192000160": {"linhas": [{"termo_id": 8711, "tipo": "mensalidade",
                                       "valor": "5.523,10"}]},
        # O 306 fatura e não está entre os contratos com placa (8802): a
        # amarração, com nome e sobrenome.
        "18522913000133": {"linhas": [{"termo_id": 306, "tipo": "mensalidade",
                                       "valor": "9.609,65"}]},
    }},
    "weso": {"lido": True},
}
var = cv.fila([
    {"numero_os": 16896, "os_id": 1, "situacao_id": 15746,
     "status_str": "Finalizado", "cliente_id": 886302,
     "cnpj": "07098192000160", "cliente": "zz MOTO HELP",
     "data_previsao": "16/09/2026 14:45:00",
     "materiais": [{"descricao": "INSTALAÇÃO", "cobrar": True, "valorTotal": 120.0}]},
    {"numero_os": 16846, "os_id": 2, "situacao_id": 15746,
     "status_str": "Finalizado", "cliente_id": 1036572, "cnpj": None,
     "cliente": None, "data_previsao": "08/09/2026 09:41:00",
     "materiais": [{"descricao": "INSTALAÇÃO", "cobrar": True, "valorTotal": 1080.0}]},
], "2026-09")

lote = cl.montar(pre, var, vencimento="2026-11-10")
porcnpj = {d["cnpj"]: d for d in lote["documentos"]}
checar("2 documentos", 2, len(lote["documentos"]))
checar("competencia por extenso no lote", "setembro de 2026",
       lote["competencia_extenso"])

mh = porcnpj["07098192000160"]
# 🚨 FIXO E VARIÁVEL NUNCA SOMADOS NUMA COLUNA SÓ, e o total é a soma dos dois.
# ⚠️ "5523,09" e nao "5.523,09": a casa nao poe separador de milhar (medido no
# `car_prefatura.somar_textos`, e a tela fala a mesma convencao).
checar("fixo da MOTO HELP (3 placas x 1.841,03)", "5523,09", mh["fixo"])
checar("variavel da MOTO HELP", "120,00", mh["variavel"])
checar("total", "5643,09", mh["total"])
checar("o mesmo total em centavos, para a tela somar", 564309, mh["total_centavos"])
checar("e o que o Harmonit cobra hoje, ao lado", "5.523,10", mh["cobrado_hoje"])
checar("MOTO HELP sem pendencia", cl.SEM_PENDENCIA, mh["situacao"])
checar("e geravel", True, mh["geravel"])

xomv = porcnpj["18522913000133"]
# 🚨 O NÚMERO QUE A TELA EXISTE PARA MOSTRAR: o contrato que fatura (306) não
# está entre os que sustentam placa (8802). Em 71 de 263 clientes, medido.
checar("XOMV acusa amarracao", cl.AMARRACAO, xomv["situacao"])
checar("e tambem acusa falta de preco", True, cl.SEM_PRECO in xomv["pendencias"])
# 🚨 A ORDEM É MEDIDA, NÃO ESTÉTICA: `SEM_PRECO` é o último da gravidade porque
# hoje ele vale para quase toda a carteira (`car_evento` = 0 linhas em 03/11).
# No topo, ele faria as 276 linhas mostrarem o mesmo selo e o achado da
# amarração (71 de 263 clientes) desapareceria.
checar("a amarracao e o selo mostrado", cl.AMARRACAO, xomv["pendencias"][0])
checar("e o sem preco fica atras dela", cl.SEM_PRECO, xomv["pendencias"][1])
# 🚨 FIXO NULO, NÃO R$ 0,00: a XOMV não tem preço lançado na CAR. Desenhar
# R$ 0,00 afirmaria que ela não cobra nada, com R$ 9.609,65 faturados do lado.
checar("fixo nulo", None, xomv["fixo"])
checar("e em centavos tambem nulo", None, xomv["fixo_centavos"])
checar("logo nao e geravel", False, xomv["geravel"])

print("\n[5] as linhas de lançamento, no formato do Harmonit")
linhas = lote["lancamentos"]
checar("2 linhas (a mensalidade e a OS da MOTO HELP)", 2, len(linhas))
mensal = [l for l in linhas if l["tipo"] == "mensalidade"][0]
checar("descricao da mensalidade",
       "Faturamento do contrato Nr. 8711. Mensalidade ref. período 09/2026.",
       mensal["descricao"])
checar("centro de custo", "Mensalidades", mensal["centro_custo"])
checar("vencimento escolhido pelo operador", "2026-11-10", mensal["vencimento"])
servico = [l for l in linhas if l["tipo"] == "servico"][0]
checar("descricao do servico", "Ordem de Serviço Nr. 16896", servico["descricao"])
checar("centro de custo do servico", "Prestação de Serviços", servico["centro_custo"])
checar("valor do servico", "120,00", servico["valor"])
# 🚨 A XOMV NÃO GERA LINHA: sem preço na CAR, não há o que lançar. Gerar com o
# valor do espelho faria a CAR repetir o Harmonit em vez de substituí-lo.
checar("nenhuma linha da XOMV", 0,
       len([l for l in linhas if l["cnpj"] == "18522913000133"]))

print("\n[6] totais e o cobrado de hoje, lado a lado")
t = lote["totais"]
checar("fixo gerado", "5523,09", t["fixo"])
checar("variavel gerado", "120,00", t["variavel"])
checar("total gerado", "5643,09", t["total"])
checar("2 linhas", 2, t["lancamentos"])
checar("1 documento a gerar", 1, t["a_gerar"])
# O outro lado da virada, sempre visível: o risco é dois boletos.
checar("cobrado hoje nos dois clientes", "15132,75", t["cobrado_hoje"])
# 🚨 DOIS CONTADORES, E A DIFERENÇA É O QUE A TELA MOSTRA: a XOMV tem
# amarração E falta de preço, logo conta nos dois; a MOTO HELP não tem nenhuma.
checar("1 cliente com pendencia", 1, t["com_pendencia"])
checar("1 com ACHADO (amarracao)", 1, t["com_achado"])
checar("1 sem preco na CAR", 1, t["sem_preco"])

print("\n[7] 'ficaram fora' é TABELA, com motivo e onde resolver")
fora = {f["motivo"]: f for f in lote["fora"]}
checar("a amarracao aparece", True, cl.AMARRACAO in fora)
checar("a falta de preco aparece", True, cl.SEM_PRECO in fora)
checar("a OS sem cliente aparece", True, "OS sem cliente nesta base" in fora)
checar("com o valor que ela nao pode gerar", "1080,00",
       fora["OS sem cliente nesta base"]["valor"])
for motivo, f in fora.items():
    checar(f"`{motivo}` diz onde resolver", True, bool(f["onde"]))

print("\n[8] a seleção do operador manda, e o lote inteiro é o padrão")
so_xomv = cl.montar(pre, var, vencimento="2026-11-10",
                    apenas=["18522913000133"])
checar("selecionando so a XOMV, nenhuma linha sai", 0,
       len(so_xomv["lancamentos"]))
checar("mas os 2 documentos continuam na tela", 2, len(so_xomv["documentos"]))
so_mh = cl.montar(pre, var, vencimento="2026-11-10",
                  apenas=["07098192000160"])
checar("selecionando a MOTO HELP, as 2 linhas saem", 2, len(so_mh["lancamentos"]))
vazio = cl.montar(pre, var, vencimento="2026-11-10", apenas=[])
checar("selecao vazia nao gera linha", 0, len(vazio["lancamentos"]))
checar("e o total do que seria gerado e None, nao 0,00", None,
       vazio["totais"]["total"])

print("\n[9] cliente que SÓ tem variável entra no lote")
# ⚠️ Se o lote fosse montado sobre a pré-fatura sozinha, este cliente não
# existiria -- e é cobrança real. O encaixe das duas unidades é o que o traz.
pre_vazia = {"competencia": "2026-09", "clientes": [], "sem_termo": [],
             "totais": {"clientes": 0, "placas": 0, "sem_valor": 0},
             "faturado": {"lido": False}, "weso": {"lido": False}}
so_var = cl.montar(pre_vazia, var, vencimento="2026-11-10")
checar("1 documento, so de OS", 1, len(so_var["documentos"]))
checar("com o valor da OS", "120,00", so_var["documentos"][0]["variavel"])
checar("fixo nulo", None, so_var["documentos"][0]["fixo"])
checar("e 1 linha de servico", 1, len(so_var["lancamentos"]))
# 🚨 E SEM CONTRATO NENHUM, ele NÃO acusa "sem preço": não há placa cobrável a
# precificar. Acusar ali mandaria o operador lançar preço em contrato que não
# existe -- afirmar além do dado é o erro que esta frente já cometeu duas vezes.
checar("nao acusa falta de preco sem contrato", False,
       cl.SEM_PRECO in so_var["documentos"][0]["pendencias"])

print("\n[9-B] contrato CANCELADO não gera linha — e continua visível")
# 🚨 A `situacao` INATIVO junta TRÊS coisas (termo sem assinatura, cancelado,
# sem placa ativa) e só UMA proíbe cobrar. Por isso o lote lê o booleano
# `cancelado`, vindo da pré-fatura, e não o texto do motivo.
cancelado = contrato(9001, "9001", 2, valor="100,00")
cancelado["cancelado"] = True
cancelado["motivo"] = "cobrança cancelada em 2026-09"
vivo = contrato(9002, "9002", 1, valor="50,00")
pre_cancel = {"competencia": "2026-09", "sem_termo": [],
              "clientes": [cliente("12345678000199", "zz Cliente",
                                   [cancelado, vivo])],
              "totais": {"clientes": 1, "placas": 3, "sem_valor": 0},
              "faturado": {"lido": True}, "weso": {"lido": True}}
lc = cl.montar(pre_cancel, cv.fila([], "2026-09"), vencimento="2026-11-10")
doc = lc["documentos"][0]
# 🚨 R$ 50,00, não R$ 250,00: o cancelado sai da SOMA, não só da linha.
checar("o fixo soma so o contrato vivo", "50,00", doc["fixo"])
checar("1 contrato cancelado contado", 1, doc["contratos_cancelados"])
checar("os dois contratos continuam na tabela", 2, len(doc["fixo_linhas"]))
checar("1 linha de lancamento, a do vivo", 1, len(lc["lancamentos"]))
checar("e e a do 9002", "9002", lc["lancamentos"][0]["numero_contrato"])
checar("o cancelado aparece em 'ficaram fora'", True,
       any("cancelada" in f["motivo"] for f in lc["fora"]))
# ⚠️ E o termo SEM ASSINATURA segue cobrável: é o caso da MOTO HELP, que o
# Harmonit fatura hoje. Confundir os dois tiraria a maior parte da carteira.
sem_ass = contrato(9004, "9004", 1, valor="33,00")
sem_ass["assinado"] = False
sem_ass["situacao"] = "INATIVO"
sem_ass["motivo"] = "termo não assinado"
pre_sa = {**pre_cancel,
          "clientes": [cliente("12345678000199", "zz Cliente", [sem_ass])]}
lsa = cl.montar(pre_sa, cv.fila([], "2026-09"), vencimento="2026-11-10")
checar("sem assinatura CONTINUA gerando linha", 1, len(lsa["lancamentos"]))
checar("com o valor lancado", "33,00", lsa["documentos"][0]["fixo"])

print("\n[10] o lote DECLARA o que não faz (`M12` como estado)")
lim = lote["limites"]
checar("nao emite boleto", False, lim["emite_boleto"])
checar("nao escreve no Harmonit", False, lim["escreve_no_harmonit"])
checar("e diz que o Harmonit continua faturando", True,
       lim["harmonit_continua_faturando"])
checar("com o risco escrito", True, "dois boletos" in lim["risco"])

print("\n[11] o CSV: uma linha por lançamento")
csv = cl.para_csv(lote)
linhas_csv = csv.split("\n")
checar("cabecalho", True, linhas_csv[0].startswith("cnpj;cliente;tipo;contrato"))
checar("1 cabecalho + 2 linhas", 3, len(linhas_csv))
# ⚠️ `;` dentro da descrição quebraria a coluna; ele é trocado por vírgula.
checar("nenhuma linha tem coluna a mais", True,
       all(l.count(";") == linhas_csv[0].count(";") for l in linhas_csv))

print("\n[12] a trava do módulo puro")
fonte = (RAIZ / "fpsl_weso" / "painel" / "car_lote.py").read_text("utf-8")
for proibido in ("import sqlite3", "harmonit_get", "conn.execute", "storage",
                 "open("):
    checar(f"o fonte nao tem `{proibido}`", False, proibido in fonte)
# 🚨 E o lote NÃO ESCREVE: ele é a conferência antes do fechamento, e o
# fechamento é rota própria, com autor. Gerar na leitura faria recarregar a
# página lançar dinheiro.
for proibido in ("INSERT", "UPDATE", "DELETE"):
    checar(f"nem `{proibido}`", False, proibido in fonte)

print(f"\n{'='*60}\n{ok} OK, {len(falhas)} falhas")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
