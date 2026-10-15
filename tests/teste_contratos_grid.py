"""Grid da Gestão de Contratos (`CTR_1.2`) — etapa G3. 2026-10-14.

O que este teste existe para impedir:

🚨 **GRID QUE DISCORDA DA FICHA.** A listagem lê o cache `contrato_placa` em
agregações; a ficha recalcula pelos eventos. Se as duas divergirem, a tela
mostra um número no grid e outro ao abrir o cliente -- e aí nenhum dos dois é
confiável. Então o teste usa a FICHA COMO ORÁCULO: para cada cliente, o grid
tem de dar o mesmo que ela.

🚨 **TERMO DOBRADO PELO PRÓPRIO CONSERTO.** A carga gravou os termos sem hash
de PDF, e `gravar()` só deduplica por hash. O modo anexar é o que impede que
subir o assinado crie um segundo termo com os eventos repetidos. Aqui isso é
medido por contagem antes/depois.

🚨 **CHAVE NORMALIZADA APARECENDO NA TELA.** `BUW8732` normaliza para
`BUW8H32`, placa que não existe. O grid compara por chave e mostra o texto.

Roda na VPS:  venv/bin/python tests/teste_contratos_grid.py
Banco em memória -- não toca banco real, Harmonit, WESO nem Clicksign.
"""
import pathlib
import sqlite3
import sys
from datetime import date

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.painel import contratos_eventos as motor          # noqa: E402
from fpsl_weso.painel import contratos_grid as grid              # noqa: E402
from fpsl_weso.painel import contratos_registro as reg           # noqa: E402
from fpsl_weso.painel import contratos_tabelas as tab            # noqa: E402

ok, falhas = 0, []
HOJE = date(2026, 10, 14)
DOIS_HM = "26388566000126"
OUTRO = "52048662000135"


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


def banco():
    c = sqlite3.connect(":memory:")
    tab.criar(c)
    tab.migrar(c)
    return c


def ev(acao, placa, fonte=motor.ASSINADO):
    return {"acao": acao, "placa": placa, "fonte": fonte}


def lido(numero, perfil, eventos, **kw):
    return dict(numero=numero, perfil=perfil, eventos=eventos, a_definir=False, **kw)


print("\n[1] A 2HM como ela esta na base: 4 ativas, nenhuma assinada")
c = banco()
# Os quatro identificadores reais da 2HM, todos sustentados por termo SEM
# assinatura -- e a auditoria diz que estao so no Harmonit, nao instalados.
reg.gravar(c, DOIS_HM, lido("255", "contrato_novo",
                            [ev(motor.ENTRA, "ASC100"), ev(motor.ENTRA, "BW212D-40")]),
           assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
reg.gravar(c, DOIS_HM, lido("1993", "aditivo", [ev(motor.ENTRA, "B10217")]),
           assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
reg.gravar(c, DOIS_HM, lido("2207", "aditivo", [ev(motor.ENTRA, "B32635")]),
           assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
reg.gravar(c, DOIS_HM, lido("2704", "contrato_novo", []),
           assinado=False, assinado_em=None, origem="carga", enviado_por="carga",
           revisar_motivo="contrato no indice do Harmonit sem PDF")
reg.gravar(c, OUTRO, lido("3185", "contrato_novo", [ev(motor.ENTRA, "SPD5H90")]),
           assinado=True, assinado_em="2023-12-01", origem="carga", enviado_por="carga")
reg.recalcular(c, DOIS_HM, HOJE)
reg.recalcular(c, OUTRO, HOJE)
reg.definir_nome(c, DOIS_HM, "2HM EMPREENDIMENTOS E PARTICIPACOES LTDA", "carga", "carga")
reg.definir_nome(c, OUTRO, "2B SOLUCOES HIDRAULICAS LTDA", "carga", "carga")

r = grid.listar(c, recalcular_se_velho=False)
linha = [i for i in r["itens"] if i["cnpj"] == DOIS_HM][0]
checar("as duas linhas aparecem", 2, len(r["itens"]))
checar("a 2HM tem nome na tela", "2HM EMPREENDIMENTOS E PARTICIPACOES LTDA", linha["nome"])
checar("4 placas ativas", 4, linha["ativas"])
checar("as 4 sem assinatura", 4, linha["so_nao_assinado"])
checar("1 termo a revisar", 1, linha["a_revisar"])
checar("4 termos sem assinatura", 4, linha["sem_assinatura"])
checar("o estado nomeia o risco", grid.ATIVA_SEM_ASSINATURA, linha["estado"])
checar("o outro cliente esta em dia", grid.EM_DIA,
       [i for i in r["itens"] if i["cnpj"] == OUTRO][0]["estado"])

print("\n[2] A FICHA e o oraculo: grid e ficha nao podem discordar")
for cnpj in (DOIS_HM, OUTRO):
    f = reg.ficha(c, cnpj, HOJE)
    g = [i for i in grid.listar(c, recalcular_se_velho=False)["itens"] if i["cnpj"] == cnpj][0]
    ativas = sum(1 for p in f["placas"] if p["situacao"] == motor.ATIVA)
    aviso = sum(1 for p in f["placas"] if p["situacao"] == motor.EM_AVISO_PREVIO)
    checar(f"{cnpj}: ativas iguais a ficha", ativas, g["ativas"])
    checar(f"{cnpj}: aviso previo igual a ficha", aviso, g["aviso"])
    checar(f"{cnpj}: sem assinatura igual a ficha", len(f["sem_assinatura"]), g["sem_assinatura"])
    checar(f"{cnpj}: a revisar igual a ficha", len(f["a_revisar"]), g["a_revisar"])
soma = c.execute("SELECT COUNT(*) FROM contrato_placa WHERE situacao IN (?,?)",
                 (motor.ATIVA, motor.EM_AVISO_PREVIO)).fetchone()[0]
r = grid.listar(c, recalcular_se_velho=False)
checar("a soma do grid bate com o cache", soma,
       r["contagens"]["placas_ativas"] + r["contagens"]["placas_em_aviso"])

print("\n[3] A busca: letra procura nome, numero procura CNPJ, e placa tambem acha")
checar("'2hm' acha so a 2HM", [DOIS_HM],
       [i["cnpj"] for i in grid.listar(c, q="2hm", recalcular_se_velho=False)["itens"]])
checar("'263' acha pelo CNPJ", [DOIS_HM],
       [i["cnpj"] for i in grid.listar(c, q="263", recalcular_se_velho=False)["itens"]])
# 🚨 Era aqui que a busca mentia: "2hm" tem o digito 2, que casa com quase todo
# CNPJ -- a tela devolvia a base inteira e parecia que o filtro nao funcionava.
checar("letra NAO cai na busca por digito", 1,
       len(grid.listar(c, q="2hm", recalcular_se_velho=False)["itens"]))
achou = grid.listar(c, q="ASC100", recalcular_se_velho=False)
checar("placa acha o cliente", [DOIS_HM], [i["cnpj"] for i in achou["itens"]])
checar("e a tela sabe que achou pela placa", [DOIS_HM], achou["achou_por_placa"])
checar("filtro por estado", [DOIS_HM],
       [i["cnpj"] for i in grid.listar(c, estado=grid.ATIVA_SEM_ASSINATURA,
                                       recalcular_se_velho=False)["itens"]])

print("\n[4] As acoes vem do backend, com o motivo quando nao cabem")
acoes = {a["id"]: a for a in [i for i in grid.listar(c, recalcular_se_velho=False)["itens"]
                              if i["cnpj"] == OUTRO][0]["acoes"]}
checar("subir termo sempre cabe", True, acoes["subir_termo"]["ativa"])
checar("sem termo a revisar, a acao vem desligada", False, acoes["revisar"]["ativa"])
checar("e com o motivo escrito", True, bool(acoes["revisar"]["motivo"]))
checar("sem achado, a acao vem desligada", False, acoes["achados"]["ativa"])
# O que a aba ainda nao faz nao aparece -- nem como botao desligado.
checar("nao existe acao de gerar termo", False, "gerar_termo" in acoes)
checar("nem de enviar para assinatura", False, "assinar" in acoes)

print("\n[5] Anexar o assinado NAO duplica o termo (o defeito da carga)")
c = banco()
tid = reg.gravar(c, DOIS_HM, lido("2649", "rescisao", [ev(motor.RESCINDE, "DHKCECA0AB0005657")]),
                 assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
antes_termos = c.execute("SELECT COUNT(*) FROM contrato_termo").fetchone()[0]
antes_eventos = c.execute("SELECT COUNT(*) FROM contrato_evento").fetchone()[0]
cands = reg.candidatos_para_anexar(c, DOIS_HM, "2649")
checar("o termo da carga e candidato a receber o PDF", 1, len(cands))
r = reg.anexar_assinado(c, tid, DOIS_HM,
                        lido("2649", "rescisao", [ev(motor.RESCINDE, "DHKCECA0AB0005657")]),
                        assinado_em="2022-06-15", enviado_por="iago",
                        hash_arquivo="hash-2649", arquivo="2649.pdf")
checar("nenhum termo novo foi criado", antes_termos,
       c.execute("SELECT COUNT(*) FROM contrato_termo").fetchone()[0])
checar("nenhum evento repetido", antes_eventos,
       c.execute("SELECT COUNT(*) FROM contrato_evento").fetchone()[0])
checar("o termo passou a assinado", 1,
       c.execute("SELECT assinado FROM contrato_termo WHERE id=?", (tid,)).fetchone()[0])
checar("com a data do documento", "2022-06-15",
       c.execute("SELECT assinado_em FROM contrato_termo WHERE id=?", (tid,)).fetchone()[0])
checar("e saiu da lista de sem assinatura", 0, len(reg.ficha(c, DOIS_HM, HOJE)["sem_assinatura"]))
checar("o diff nao inventou evento", [], r["eventos_novos"])
checar("ja nao e mais candidato", 0, len(reg.candidatos_para_anexar(c, DOIS_HM, "2649")))

print("\n[6] O mesmo PDF duas vezes nao passa, e o cliente errado tambem nao")
try:
    reg.anexar_assinado(c, tid, DOIS_HM, lido("2649", "rescisao", []),
                        assinado_em=None, enviado_por="iago",
                        hash_arquivo="hash-2649", arquivo="2649.pdf")
    checar("o segundo envio foi recusado", True, False)
except reg.TermoJaGravado:
    checar("o segundo envio foi recusado", True, True)
try:
    reg.anexar_assinado(c, tid, "99999999999999", lido("2649", "rescisao", []),
                        assinado_em=None, enviado_por="iago",
                        hash_arquivo="outro-hash", arquivo="x.pdf")
    checar("anexar no CNPJ errado foi recusado", True, False)
except ValueError as e:
    checar("anexar no CNPJ errado foi recusado", True, "não do" in str(e))

print("\n[7] O que o assinado NAO confirma vira revisao, e nada e apagado")
c = banco()
# A carga trouxe 3 placas (lista do Harmonit); o assinado so confirma 2.
tid = reg.gravar(c, DOIS_HM, lido("3465", "contrato_novo",
                                  [ev(motor.ENTRA, "AAA1B23"), ev(motor.ENTRA, "CCC3D45"),
                                   ev(motor.ENTRA, "EEE5F67")]),
                 assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
r = reg.anexar_assinado(c, tid, DOIS_HM,
                        lido("3465", "contrato_novo",
                             [ev(motor.ENTRA, "AAA1B23"), ev(motor.ENTRA, "CCC3D45")]),
                        assinado_em="2024-07-02", enviado_por="iago",
                        hash_arquivo="hash-3465", arquivo="3465.pdf")
checar("o termo ficou marcado a revisar", True, r["a_revisar"])
checar("dizendo qual placa o assinado nao confirma", ["EEE5F67"], r["nao_confirmados"])
checar("e o evento da carga continua la", 3,
       c.execute("SELECT COUNT(*) FROM contrato_evento WHERE termo_id=?", (tid,)).fetchone()[0])
checar("a placa segue sustentada, nao desaparece", True,
       "EEE5F67" in reg.ficha(c, DOIS_HM, HOJE)["sustentadas"])

print("\n[8] Confirmar quem SAI: so inserção, e so onde ha troca registrada")
c = banco()
tid = reg.gravar(c, DOIS_HM, lido("8872", "contrato_novo",
                                  [ev(motor.ENTRA, "DVS2992"), ev(motor.ENTRA, "FAC5H30")]),
                 assinado=True, assinado_em="2026-09-15", origem="upload", enviado_por="iago",
                 hash_arquivo="h-8872",
                 troca_registrada="FAC 5H30 - Cliente pediu alteracao da placa",
                 revisar_motivo="troca registrada no Harmonit sem confirmação de qual placa sai")
antes = c.execute("SELECT COUNT(*) FROM contrato_evento WHERE termo_id=?", (tid,)).fetchone()[0]
r = reg.confirmar_saida(c, tid, "DVS2992", "iago")
checar("a saida entrou como evento novo", antes + 1,
       c.execute("SELECT COUNT(*) FROM contrato_evento WHERE termo_id=?", (tid,)).fetchone()[0])
checar("com a autoria gravada", True, "iago" in c.execute(
    "SELECT obs FROM contrato_evento WHERE termo_id=? AND acao=?",
    (tid, motor.SAI)).fetchone()[0])
checar("o termo saiu de 'a revisar'", 0,
       c.execute("SELECT revisar FROM contrato_termo WHERE id=?", (tid,)).fetchone()[0])
checar("e o motivo NAO foi apagado", True, "confirmação de qual placa sai" in c.execute(
    "SELECT revisar_motivo FROM contrato_termo WHERE id=?", (tid,)).fetchone()[0])
checar("o resolvido ficou escrito", True, "[resolvido" in c.execute(
    "SELECT revisar_motivo FROM contrato_termo WHERE id=?", (tid,)).fetchone()[0])
checar("so FAC5H30 continua sustentada", ["FAC5H30"], reg.ficha(c, DOIS_HM, HOJE)["sustentadas"])
try:
    reg.confirmar_saida(c, tid, "DVS2992", "iago")
    checar("confirmar duas vezes foi recusado", True, False)
except ValueError:
    checar("confirmar duas vezes foi recusado", True, True)
try:
    reg.confirmar_saida(c, tid, "ZZZ9Z99", "iago")
    checar("placa de fora do termo foi recusada", True, False)
except ValueError:
    checar("placa de fora do termo foi recusada", True, True)
tid2 = reg.gravar(c, OUTRO, lido("9000", "contrato_novo", [ev(motor.ENTRA, "GGG1H23")]),
                  assinado=True, assinado_em="2026-01-01", origem="upload",
                  enviado_por="iago", hash_arquivo="h-9000")
try:
    reg.confirmar_saida(c, tid2, "GGG1H23", "iago")
    checar("termo sem troca registrada nao aceita saida", True, False)
except ValueError:
    checar("termo sem troca registrada nao aceita saida", True, True)

print("\n[9] Revisado registra quem olhou e nao apaga o motivo")
c = banco()
tid = reg.gravar(c, DOIS_HM, lido("2704", "contrato_novo", []),
                 assinado=False, assinado_em=None, origem="carga", enviado_por="carga",
                 revisar_motivo="contrato no indice do Harmonit sem PDF")
r = reg.marcar_revisado(c, tid, "iago", "conferido com o cliente, nao existe PDF")
checar("estava marcado", True, r["estava_marcado"])
checar("o flag baixou", 0, c.execute("SELECT revisar FROM contrato_termo WHERE id=?",
                                     (tid,)).fetchone()[0])
checar("o motivo continua escrito", True, "sem PDF" in c.execute(
    "SELECT revisar_motivo FROM contrato_termo WHERE id=?", (tid,)).fetchone()[0])
checar("e ficou quem olhou", ("iago",), c.execute(
    "SELECT por FROM contrato_revisao WHERE termo_id=?", (tid,)).fetchone())

print("\n[10] O nome: a carga nao desfaz a correcao a mao")
c = banco()
reg.definir_nome(c, DOIS_HM, "M_ D_ G_ COMERCIO", "carga", "carga")
reg.definir_nome(c, DOIS_HM, "MDG Comercio de Pecas", "iago")
checar("a correcao a mao vale", "MDG Comercio de Pecas", reg.nome_do_cliente(c, DOIS_HM)["nome"])
checar("e fica marcada como manual", "manual", reg.nome_do_cliente(c, DOIS_HM)["nome_fonte"])
reg.definir_nome(c, DOIS_HM, "M_ D_ G_ COMERCIO", "carga", "carga")
checar("rodar a carga de novo nao desfaz", "MDG Comercio de Pecas",
       reg.nome_do_cliente(c, DOIS_HM)["nome"])
checar("cliente sem nome nao mente", None, reg.nome_do_cliente(c, "11111111111111")["nome"])

print("\n[11] A chave normalizada nunca chega a tela")
c = banco()
# `BUW8732` normaliza para `BUW8H32`, placa que nao existe -- a familia do RFD 2447.
reg.gravar(c, DOIS_HM, lido("7777", "contrato_novo", [ev(motor.ENTRA, "BUW8732")]),
           assinado=True, assinado_em="2026-02-02", origem="upload", enviado_por="iago",
           hash_arquivo="h-7777")
reg.recalcular(c, DOIS_HM, HOJE)
achou = grid.clientes_por_placa(c, "BUW8732")
checar("acha a placa", 1, len(achou))
checar("e mostra o texto do termo, nao a chave", "BUW8732", achou[0]["placa"])
r = grid.listar(c, q="BUW8732", recalcular_se_velho=False)
checar("a busca pela placa acha o cliente", [DOIS_HM], [i["cnpj"] for i in r["itens"]])

print("\n[12] O cache velho e refeito, porque o aviso previo vence pelo calendario")
c = banco()
reg.gravar(c, DOIS_HM, lido("8904", "rescisao", [ev(motor.RESCINDE, "FJW0B75")]),
           assinado=True, assinado_em="2026-07-01", origem="upload", enviado_por="iago",
           hash_arquivo="h-8904")
reg.recalcular(c, DOIS_HM, HOJE)
c.execute("UPDATE contrato_placa SET calculado_em = '2026-01-01T00:00:00'")
checar("o cache e reconhecido como velho", True, bool(grid._cache_velho(c)))
r = grid.listar(c)
checar("a listagem refez o calculo", 1, (r["recalculado"] or {}).get("clientes"))
checar("e agora o cache esta em dia", None, grid._cache_velho(c))

print("\n[13] A listagem nao chama a ficha, e o modulo nao grava fonte nenhuma")
fonte = (RAIZ / "fpsl_weso" / "painel" / "contratos_grid.py").read_text(encoding="utf-8")
# 🚨 Chamar a ficha por cliente foi o caminho natural e errado: 731 recalculos
# para desenhar a primeira tela.
checar("nao chama ficha()", False, "registro.ficha(" in fonte)
# O módulo LÊ `contrato_evento` (a guarda de cache vazio), e isso é esperado;
# o que não pode existir aqui é escrita.
checar("nao tem nenhuma escrita em SQL", False,
       any(s in fonte.upper() for s in ("INSERT INTO", "UPDATE ", "DELETE FROM")))
checar("e nada de Harmonit/WESO/Clicksign", False,
       any(s in fonte.lower() for s in ("harmonit_get", "harmonit_post", "weso_get", "clicksign_")))

print("\n[14] D4 - a aderencia por cliente, com a margem +-1 dele")
# Funcao pura: nao depende do cache nem de banco.
checar("3 sustentadas e 3 em uso -> bate", grid.ADERENTE,
       grid.aderencia_da_linha({"ativas": 3, "aviso": 0, "em_uso": 3}))
checar("4 sustentadas e 3 em uso -> ainda bate (margem 1)", grid.ADERENTE,
       grid.aderencia_da_linha({"ativas": 4, "aviso": 0, "em_uso": 3}))
checar("5 sustentadas e 3 em uso -> contrato maior", grid.CONTRATO_MAIOR,
       grid.aderencia_da_linha({"ativas": 5, "aviso": 0, "em_uso": 3}))
checar("o aviso previo conta como sustentada", grid.CONTRATO_MAIOR,
       grid.aderencia_da_linha({"ativas": 3, "aviso": 2, "em_uso": 3}))
# 🚨 SEM CACHE NAO SE INVENTA ZERO: `em_uso` nulo e "nao sei", nao "nada em uso".
checar("sem dado da WESO nao vira 'contrato maior'", grid.SEM_DADO,
       grid.aderencia_da_linha({"ativas": 9, "aviso": 0, "em_uso": None}))
# 🚨 Cliente SEM placa sustentada nao e "sem dado da WESO": culpar a fonte
# errada manda procurar defeito onde nao ha. Eram 252 clientes rotulados assim.
checar("cliente sem placa sustentada tem rotulo proprio", grid.SEM_SUSTENTADA,
       grid.aderencia_da_linha({"ativas": 0, "aviso": 0, "em_uso": 0}))
checar("e nao culpa o cache", grid.SEM_SUSTENTADA,
       grid.aderencia_da_linha({"ativas": 0, "aviso": 0, "em_uso": None}))
checar("e cada aderencia tem explicacao em portugues", 5, len(grid.ADERENCIAS))
checar("a margem e 1, como ele definiu", 1, grid.MARGEM_ADERENCIA)

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f_ in falhas:
    print("  -", f_)
sys.exit(1 if falhas else 0)
