"""Carga dos PDFs assinados (`C7`) — a classificação e as guardas. 2026-10-14.

🚨 O DEFEITO QUE ESTE ARQUIVO EXISTE PARA IMPEDIR JÁ ACONTECEU, em produção, na
primeira passada da 2HM: o extrator devolveu a **linha descritiva inteira** no
lugar da placa, e a carga criou evento com ela **e anulou o identificador
correto** que estava na base. Foi revertido pelo livro-razão, e as linhas reais
que causaram o estrago estão aqui como fixture.

**Identificador inventado é pior que identificador faltando** (regra 13, a
família do `RFD 2447`): a cobrança passa a apontar para um veículo que não
existe. Quando a leitura vem descritiva, o documento inteiro vai para a fila --
decifrar a linha seria mexer no `pdf_extractor`, que é da aba Operações e é
intocável.

Roda na VPS:  venv/bin/python tests/teste_contratos_assinados.py
Sem I/O de banco nas partes de classificação; o resto em banco de memória.
"""
import pathlib
import sqlite3
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.painel import contratos_assinados as c7          # noqa: E402
from fpsl_weso.painel import contratos_eventos as motor         # noqa: E402
from fpsl_weso.painel import contratos_registro as reg          # noqa: E402
from fpsl_weso.painel import contratos_tabelas as tab           # noqa: E402

ok, falhas = 0, []
CNPJ = "26388566000126"


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


print("\n[1] As linhas REAIS que a carga aceitou por engano, e agora recusa")
# Medidas na 2HM, em 14/10, nos termos 2652, 2703 e 3520.
reais = [
    "Cod: 01-06 - Escavadeira Hidraulica- JohnDeere- 210G - Amarela- 1F9210GXKED520143 - 2014",
    "Escavadeira PC350, Komatsu, PC350 LC-8 B10217",
    "Cod: 05-01 - Trator de Esteiras - JohnDeere- 700J - Amarela- 1T0700JXEDD253286 - 2014",
    "1BZ310KXJEC000130 (ID: 007842126)",
    "Cod: 01-05 (ID: 205727026)",
]
for texto in reais:
    checar(f"recusa: {texto[:38]}...", True, bool(c7.identificador_suspeito(texto)))

print("\n[2] E continua aceitando identificador de verdade, inclusive os estranhos")
# Todos existem na base: placa comum, Mercosul, chassi de 17, e os códigos de
# frota que a auditoria mediu (eles NÃO são placa, mas são o identificador que o
# cliente usa, e o FPSL já os trata assim).
for texto in ("FJW0B75", "FJW 0B75", "B10217", "ASC100", "BW212D-40", "PC200-8",
              "1F9210GXKED520143", "9BD281A22MYV30872", "00D6NCCCK01011", "NEAA01436"):
    checar(f"aceita: {texto}", None, c7.identificador_suspeito(texto))

print("\n[3] Um identificador ruim reprova o documento INTEIRO")
# Metade boa não salva: se a leitura errou numa linha, não há razão para
# confiar nas outras para fins de CORREÇÃO.
bom = lido("2652", "rescisao", [ev(motor.RESCINDE, "1F9210GXKED520143")])
checar("leitura limpa passa", (True, None), c7.leitura_confiavel(bom))
ruim = lido("2652", "rescisao", [ev(motor.RESCINDE, "1F9210GXKED520143"),
                                 ev(motor.RESCINDE, reais[0])])
passou, motivo = c7.leitura_confiavel(ruim)
checar("leitura com uma linha descritiva reprova", False, passou)
checar("e o motivo diz o que veio no lugar", True, "no lugar da placa" in motivo)

print("\n[4] O tipo do nome do arquivo -> perfil, com a cauda de grafias erradas")
for tipo, esperado in (("contrato", "contrato_novo"), ("aditivo", "aditivo"),
                       ("adtivo", "aditivo"), ("rescisao", "rescisao"),
                       ("resscisao", "rescisao"), ("distrato", "rescisao"),
                       ("substituicao", "substituicao"), ("subtituicao", "substituicao"),
                       ("ressarcimento", "ressarcimento_com_termo"),
                       ("upgrade", "upgrade"), ("dowgrade", "upgrade")):
    perfil, rota, _ = c7.perfil_do_nome(tipo)
    checar(f"'{tipo}' -> {esperado}", (esperado, "ler"), (perfil, rota))

print("\n[5] O que não lista veículo é 'documento só', e transferência é fila")
for tipo in ("acordo", "negociacao", "outros", "minuta", "party", "ivan"):
    _, rota, motivo = c7.perfil_do_nome(tipo)
    checar(f"'{tipo}' -> documento só", "doc_so", rota)
    checar(f"'{tipo}' diz por quê", True, bool(motivo))
_, rota, motivo = c7.perfil_do_nome("transferencia")
checar("transferência vai para a fila", "fila", rota)
checar("com o motivo do documento por titular", True, "titular" in motivo)

print("\n[6] Só 'assinado' entra — e a 2HM tem um 3520 cancelado ao lado do assinado")
checar("a lista branca tem um estado só", {"assinado"}, c7.ESTADOS_QUE_ENTRAM)
for estado in ("cancelado", "rascunho", "pendente", ""):
    checar(f"'{estado or 'vazio'}' não entra", False, estado in c7.ESTADOS_QUE_ENTRAM)
# ⚠️ Maiúscula e espaço sobrando ENTRAM, e isso é certo: o CSV da auditoria é
# texto digitado, e recusar por caixa seria perder documento bom por formatação.
checar("'ASSINADO ' (caixa/espaço) entra, porque o código normaliza", True,
       "ASSINADO ".strip().lower() in c7.ESTADOS_QUE_ENTRAM)

print("\n[7] Quando NÃO corrigir — cada recusa é um caso medido")
termo_troca = {"numero": "8872", "troca_registrada": "FAC 5H30 - cliente pediu alteracao"}
checar("termo com troca registrada não se corrige sozinho", False,
       c7.pode_corrigir(termo_troca, lido("8872", "aditivo", [ev(motor.ENTRA, "AAA1B23")]),
                        ["DVS2992"])[0])
checar("termo com 'a definir' também não", False,
       c7.pode_corrigir({"numero": "3085", "a_definir": True},
                        lido("3085", "aditivo", [ev(motor.ENTRA, "AAA1B23")]), ["SIF0C19"])[0])
checar("leitura sem placa nenhuma não corrige", False,
       c7.pode_corrigir({"numero": "1"}, lido("1", "aditivo", []), ["AAA1B23"])[0])
# O 2207 da 2HM é este caso: o assinado traz 3 placas e a lista do Harmonit, 16.
muitas = [f"PLACA{i:04d}" for i in range(13)]
pode, motivo = c7.pode_corrigir({"numero": "2207"},
                                lido("2207", "aditivo", [ev(motor.ENTRA, "B10217")] * 3), muitas)
checar("diferença maior que a metade não se corrige sozinha", False, pode)
checar("e o motivo traz os números", True, "13 de 16" in motivo)
pode, _ = c7.pode_corrigir({"numero": "2224"},
                           lido("2224", "aditivo", [ev(motor.ENTRA, "FJW0B75")]),
                           ["00D6NCCCK01011"])
checar("uma placa a mais, com documento legível: corrige", True, pode)

print("\n[8] O identificador CONTIDO na linha nova nunca é anulado")
# `9BD281A22MYV` × `9BD281A22MYV30872` é chassi cortado na quebra de linha. E o
# caso real de 14/10: o identificador bom estava DENTRO da linha descritiva.
checar("prefixo conta como mesma placa", True, c7._prefixo_de("9BD281A22MYV", "9BD281A22MYV30872"))
checar("contido no meio também", True,
       c7._prefixo_de("1F9210GXKED520143",
                      motor.chave("Cod: 01-06 - ... 1F9210GXKED520143 - 2014")))
checar("placas diferentes da mesma frota NAO se confundem", False,
       c7._prefixo_de("DTX7581", "DTX7583"))

print("\n[9] Desempate entre Instituto e Movisat: só com prova")
c = banco()
# 555 pares (cnpj, numero) existem nas duas empresas.
reg.gravar(c, CNPJ, lido("5029", "contrato_novo", [ev(motor.ENTRA, "AAA1B23")], empresa="MOVISAT"),
           assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
reg.gravar(c, CNPJ, lido("5029", "contrato_novo", [ev(motor.ENTRA, "CCC3D45")], empresa="INSTITUTO"),
           assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
termo_id, motivo = c7.escolher_termo(c, CNPJ, "5029", {"assinado_em": None, "enviado_em": None}, None)
checar("sem prova, vai para a fila", None, termo_id)
checar("dizendo que há dois e quais empresas", True,
       "2 termos 5029" in motivo and "INSTITUTO" in motivo)
# Prova 3: a placa do documento aparece em um candidato só.
doc = lido("5029", "contrato_novo", [ev(motor.ENTRA, "CCC3D45")])
termo_id, motivo = c7.escolher_termo(c, CNPJ, "5029", {"assinado_em": None, "enviado_em": None}, doc)
checar("a placa do documento desempata", "INSTITUTO",
       c.execute("SELECT empresa FROM contrato_termo WHERE id = ?", (termo_id,)).fetchone()[0])

print("\n[10] Número que não existe no cliente, e segundo documento do mesmo termo")
c = banco()
tid = reg.gravar(c, CNPJ, lido("765", "contrato_novo", [ev(motor.ENTRA, "AAA1B23")]),
                 assinado=True, assinado_em="2019-11-26", origem="upload",
                 enviado_por="iago", hash_arquivo="h-765")
termo_id, motivo = c7.escolher_termo(c, CNPJ, "765", {}, None)
checar("termo que já tem PDF não recebe outro automático", None, termo_id)
checar("e o motivo diz que é segundo documento", True, "segundo" in motivo)
termo_id, motivo = c7.escolher_termo(c, CNPJ, "9999", {}, None)
checar("número inexistente vai para a fila", None, termo_id)
checar("dizendo que o documento só está na Clicksign", True, "só na Clicksign" in motivo)

print("\n[11] O livro-razão dá retomada")
c = banco()
reg_fake = {"cnpj": CNPJ, "arquivo": "x.pdf", "estado": "assinado", "numero": "2224",
            "chave_clicksign": "abc"}
c7.anotar(c, "sha-1", reg_fake, "anexado", termo_id=1, lote="t")
checar("o que foi anexado fica marcado", "anexado", c7.ja_processado(c, "sha-1"))
checar("e o que nunca passou não tem marca", None, c7.ja_processado(c, "sha-2"))
c7.anotar(c, "sha-1", reg_fake, "fila", motivo="mudou de ideia", lote="t")
checar("a linha é atualizada, nao duplicada", 1,
       c.execute("SELECT COUNT(*) FROM contrato_carga_pdf WHERE sha256='sha-1'").fetchone()[0])

print("\n[12] O valor: a regra ampliada (decisao dele, 14/10)")
from fpsl_weso.painel import contratos_leitura as L
# O item REAL do termo da 2HM, que a regra estreita nao reconhecia.
real = [{"descricao": "PACOTE FULL MANAGER - Mensal", "quantidade": "16", "valor_unitario": "75,26"}]
placas = [ev(motor.ENTRA, f"PLACA{i:03d}") for i in range(16)]
v = L.valor_das_placas(real, placas)
checar("PACOTE FULL MANAGER passou a ser reconhecido", 1, len(v["itens"]))
checar("e Qtd=16 para 16 placas da valor a todas", 16, len(v["por_placa"]))
checar("com o preco unitario do documento", "75,26", v["por_placa"]["PLACA000"])
checar("nenhuma placa fica sem valor", [], v["sem_valor"])
# Qtd que NAO bate nao vira rateio: o numero sairia de nos, nao do documento.
v = L.valor_das_placas([{"descricao": "MENSALIDADE", "quantidade": "3", "valor_unitario": "99,90"}],
                       [ev(motor.ENTRA, "AAA1B23"), ev(motor.ENTRA, "CCC3D45")])
checar("Qtd diferente do numero de placas NAO rateia", {}, v["por_placa"])
checar("e a tela sabe quantas ficaram sem valor", 2, len(v["sem_valor"]))

# 🚨 OS ITENS REAIS DO TERMO 2224 DA 2HM. A regra ampliada pegou DOIS itens --
# a mensalidade (75,26) e a VENDA do equipamento (999,90) -- e com dois
# candidatos nenhuma placa recebia valor. Sem a exclusao do que se paga uma vez
# so, a cobranca poderia sair com o preco do aparelho: 13x o valor certo.
itens_2hm = [{"descricao": "Equipamento rastreador telemetria avancada", "quantidade": "01",
              "valor_unitario": "999,90"},
             {"descricao": "Adesao", "quantidade": "01", "valor_unitario": "199,90"},
             {"descricao": "PACOTE FULL MANAGER", "quantidade": "01", "valor_unitario": "75,26"}]
v = L.valor_das_placas(itens_2hm, [ev(motor.ENTRA, "FJW 0B75")])
checar("so a mensalidade conta como mensal", ["PACOTE FULL MANAGER"],
       [i["descricao"] for i in v["itens"]])
checar("e a placa recebe 75,26, nao 999,90", {"FJW 0B75": "75,26"}, v["por_placa"])
# O 2207: os mesmos itens com qtd 16, mas o documento deu 3 placas. Nao se
# atribui valor quando a quantidade nao bate -- e a tela diz quantas ficaram.
v = L.valor_das_placas([dict(i, quantidade="16") for i in itens_2hm],
                       [ev(motor.ENTRA, f"P{i}") for i in range(3)])
checar("qtd 16 com 3 placas lidas: ninguem recebe valor", {}, v["por_placa"])
checar("e as 3 ficam listadas como sem valor", 3, len(v["sem_valor"]))

print("\n[13] O valor chega ao contrato_item, que a carga deixou vazio")
c = banco()
tid = reg.gravar(c, CNPJ, lido("2207", "aditivo",
                               [ev(motor.ENTRA, "AAA1B23"), ev(motor.ENTRA, "CCC3D45")]),
                 assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
checar("a carga deixou o item sem valor", [(None,), (None,)],
       c.execute("SELECT valor_mensal FROM contrato_item WHERE termo_id = ?", (tid,)).fetchall())
r = reg.preencher_valores(c, tid, CNPJ, {"AAA1B23": "75,26", "CCC3D45": "75,26"})
checar("os dois itens ganharam valor", 2, len(r["preenchidos"]))
checar("e o banco confirma", [("75,26",), ("75,26",)],
       c.execute("SELECT valor_mensal FROM contrato_item WHERE termo_id = ?", (tid,)).fetchall())
# Valor ja gravado nao se sobrescreve: quem o pos sabia de algo que nao sabemos.
r = reg.preencher_valores(c, tid, CNPJ, {"AAA1B23": "999,99"})
checar("valor existente NAO e sobrescrito", ["AAA1B23"], r["ja_tinha"])
checar("o banco manteve o primeiro", "75,26",
       c.execute("SELECT valor_mensal FROM contrato_item WHERE termo_id = ? AND placa_texto = 'AAA1B23'",
                 (tid,)).fetchone()[0])

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f_ in falhas:
    print("  -", f_)
sys.exit(1 if falhas else 0)
