"""A WESO desempata, placa por placa (frente `D`). 2026-10-14.

🚨 AS DUAS REGRAS SÃO DELE, E SÃO OPOSTAS ENTRE SI DE PROPÓSITO:
  · *"placas sem assinatura mas placa ativa, placa vence, pois se existe na weso
    foi feita, o erro é não ter assinatura"* -- a placa EM USO nunca perde o
    contrato; o que falta é assinatura, e isso é achado.
  · *"pode ser que N placas foram rescindidas mas nao assinadas, se tiverem fora
    da Weso, é recisão mesmo"* -- a placa que já SAIU fecha, mesmo sem documento
    assinado.

O que este arquivo impede: que a segunda regra morda a primeira. Uma placa que
está na WESO não pode fechar por nenhum caminho desta frente -- e é essa a
asserção que vale mais aqui.

⚠️ O motor continua SEM I/O: ele não consulta a WESO. Quem consulta é
`contratos_aderencia`, que insere o evento com `fonte="weso"` e a data do cache
no `obs`. Por isso este teste roda em banco de memória, sem rede.

Roda na VPS:  venv/bin/python tests/teste_contratos_aderencia.py
"""
import pathlib
import sqlite3
import sys
from datetime import date

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.painel import contratos_eventos as motor          # noqa: E402
from fpsl_weso.painel import contratos_registro as reg           # noqa: E402
from fpsl_weso.painel import contratos_tabelas as tab            # noqa: E402

ok, falhas = 0, []
HOJE = date(2026, 10, 14)
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


print("\n[1] A regra que fecha: rescisao SEM assinatura + placa fora da WESO")
# O contrato ativa a placa por termo assinado; a rescisao nao foi assinada.
# Hoje, sem a fonte `weso`, a rescisao nao conta e a placa fica ATIVA.
termos = [
    lido("255", "contrato_novo", [ev(motor.ENTRA, "AAA1B23")],
         assinado=True, assinado_em="2020-01-01"),
    lido("8904", "rescisao", [ev(motor.RESCINDE, "AAA1B23")],
         assinado=False, assinado_em=None),
]
s = motor.situacao_das_placas(termos, HOJE)
checar("sem a prova do uso, a placa segue ativa", motor.ATIVA, s["AAA1B23"]["situacao"])

# Com a prova do uso (a placa nao esta mais na WESO), ela fecha.
termos[1]["eventos"].append(ev(motor.RESCINDE, "AAA1B23", motor.WESO))
s = motor.situacao_das_placas(termos, HOJE)
checar("com a prova do uso, e rescisao mesmo", motor.RESCINDIDA, s["AAA1B23"]["situacao"])
checar("e a base diz que o lastro e o uso, nao a assinatura",
       "rescisao confirmada pelo uso (fora da WESO)", s["AAA1B23"]["base"])

print("\n[2] A regra que PROTEGE: placa em uso nao fecha, mesmo sem assinatura")
# 🚨 Esta e a asserção mais importante do arquivo: a frente D nao pode tirar do
# contrato a placa que esta rodando. Quem esta na WESO nao recebe evento `weso`
# nenhum -- e, se receber por engano, o teste abaixo denuncia.
termos = [
    lido("1993", "aditivo", [ev(motor.ENTRA, "B10217")], assinado=False, assinado_em=None),
]
s = motor.situacao_das_placas(termos, HOJE)
checar("placa sem assinatura, mas sustentada, fica ativa", motor.ATIVA, s["B10217"]["situacao"])
checar("e a tela diz que nao ha assinatura", "nao assinado", s["B10217"]["base"])

print("\n[3] A fonte `weso` vale onde nenhuma outra valeria")
checar("evento `weso` conta mesmo em termo sem assinatura", True,
       motor._vale_assinado({"numero": "8904", "assinado": False},
                            {"acao": motor.RESCINDE, "fonte": motor.WESO}))
checar("e `harmonit` em termo sem assinatura continua NAO valendo", False,
       motor._vale_assinado({"numero": "8904", "assinado": False},
                            {"acao": motor.ENTRA, "fonte": motor.HARMONIT}))
checar("nem `assinado` em termo sem assinatura", False,
       motor._vale_assinado({"numero": "8904", "assinado": False},
                            {"acao": motor.ENTRA, "fonte": motor.ASSINADO}))

print("\n[4] A prova entra como EVENTO, apontando a rescisao que ela confirma")
c = banco()
t255 = reg.gravar(c, CNPJ, lido("255", "contrato_novo", [ev(motor.ENTRA, "AAA1B23")]),
                  assinado=True, assinado_em="2020-01-01", origem="carga", enviado_por="carga")
t8904 = reg.gravar(c, CNPJ, lido("8904", "rescisao", [ev(motor.RESCINDE, "AAA1B23")]),
                   assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
checar("antes, o contrato sustenta a placa", ["AAA1B23"], reg.ficha(c, CNPJ, HOJE)["sustentadas"])
antes = c.execute("SELECT COUNT(*) FROM contrato_evento").fetchone()[0]
rescisao_id = c.execute(
    "SELECT id FROM contrato_evento WHERE termo_id = ? AND acao = ?",
    (t8904, motor.RESCINDE)).fetchone()[0]
c.execute(
    """INSERT INTO contrato_evento
       (termo_id, placa_chave, placa_texto, acao, fonte, obs, corrige_evento_id, criado_em)
       VALUES (?,?,?,?,?,?,?,?)""",
    (t8904, "AAA1B23", "AAA1B23", motor.RESCINDE, motor.WESO,
     "D: fora da WESO no cache de 2026-10-14", rescisao_id, reg._agora()))
reg.recalcular(c, CNPJ, HOJE)
f = reg.ficha(c, CNPJ, HOJE)
checar("depois, a placa fechou", [], f["sustentadas"])
checar("nada foi apagado: so acrescentado", antes + 1,
       c.execute("SELECT COUNT(*) FROM contrato_evento").fetchone()[0])
checar("e o evento novo aponta a rescisao que ele confirma", rescisao_id,
       c.execute("SELECT corrige_evento_id FROM contrato_evento WHERE fonte = ?",
                 (motor.WESO,)).fetchone()[0])
checar("a data do cache fica escrita", True, "cache de 2026-10-14" in c.execute(
    "SELECT obs FROM contrato_evento WHERE fonte = ?", (motor.WESO,)).fetchone()[0])
# ⚠️ A ficha mostra a correcao: a rescisao nao assinada continua visivel, com
# quem a confirmou ao lado.
checar("a ficha explica a confirmacao", 1, len(f["correcoes"]))

print("\n[6] A classificacao: as duas regras, em banco de memoria")
from fpsl_weso.painel import contratos_aderencia as ader
c = banco()
# tres placas: uma em uso, uma fora com rescisao, uma fora sem rescisao
# 🚨 O ENTRA e ASSINADO e a rescisao NAO -- e esse o caso real das 549 placas:
# com os dois sem assinatura, a rescisao ja fecharia a placa na passada 2 e ela
# nem apareceria como sustentada.
reg.gravar(c, CNPJ, lido("255", "contrato_novo",
                         [ev(motor.ENTRA, "EMUSO01"), ev(motor.ENTRA, "FORA001"),
                          ev(motor.ENTRA, "FORA002")]),
           assinado=True, assinado_em="2020-01-01", origem="carga", enviado_por="carga")
# uma placa EM USO cujo unico lastro e termo sem assinatura
reg.gravar(c, CNPJ, lido("1993", "aditivo", [ev(motor.ENTRA, "EMUSO02")]),
           assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
reg.gravar(c, CNPJ, lido("8904", "rescisao", [ev(motor.RESCINDE, "FORA001")]),
           assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
reg.recalcular(c, CNPJ, HOJE)
weso = {"EMUSO01": "ATIVO", "EMUSO02": "ATIVO"}   # as duas primeiras estao na WESO
linhas = {x["placa"]: x for x in ader.classificar(c, weso)}
checar("a placa em uso: destino 'em uso'", ader.EM_USO, linhas["EMUSO01"]["destino"])
checar("a em uso COM assinatura nao e cobrada de assinatura", False,
       linhas["EMUSO01"]["falta_assinar"])
checar("a em uso SEM assinatura e marcada (achado, nao demissao)", True,
       linhas["EMUSO02"]["falta_assinar"])
checar("fora da WESO com rescisao: fecha", ader.FECHA, linhas["FORA001"]["destino"])
checar("apontando a rescisao que confirma", True, bool(linhas["FORA001"]["confirma_evento"]))
checar("e dizendo que ela NAO era assinada", False, linhas["FORA001"]["rescisao_assinada"])
checar("fora da WESO sem rescisao: nada a fechar", ader.SEM_RESCISAO,
       linhas["FORA002"]["destino"])

print("\n[7] A coorte de aderencia, com a margem +-1 dele")
por = ader.aderencia_por_cliente(list(linhas.values()))
checar("4 sustentadas, 2 em uso -> diferenca 2", 2, por[CNPJ]["diferenca"])
checar("acima da margem: contrato maior que o uso", "contrato maior que o uso",
       por[CNPJ]["coorte"])
uma = [x for x in linhas.values() if x["placa"] == "EMUSO01"]
checar("so a em uso -> aderente", "aderente",
       ader.aderencia_por_cliente(uma)[CNPJ]["coorte"])

print("\n[8] Confirmar pelo uso fecha a placa, e NAO toca em quem esta na WESO")
antes = c.execute("SELECT COUNT(*) FROM contrato_evento").fetchone()[0]
ader.confirmar_saida_pelo_uso(c, linhas["FORA001"], "2026-10-14", "teste")
reg.recalcular(c, CNPJ, HOJE)
f = reg.ficha(c, CNPJ, HOJE)
checar("um evento novo, nenhum apagado", antes + 1,
       c.execute("SELECT COUNT(*) FROM contrato_evento").fetchone()[0])
checar("a placa fora da WESO fechou", False, "FORA001" in f["sustentadas"])
# A ASSERCAO QUE MAIS IMPORTA: a placa em uso continua sustentada.
checar("a placa EM USO continua sustentada", True, "EMUSO01" in f["sustentadas"])
checar("e a sem rescisao tambem", True, "FORA002" in f["sustentadas"])
checar("a ficha explica a confirmacao", True,
       any("fora da WESO" in (x["motivo"] or "") for x in f["correcoes"]))
linhas2 = {x["placa"]: x for x in ader.classificar(c, weso)}
checar("a placa ja confirmada nao volta para a fila", True,
       "FORA001" not in linhas2 or linhas2["FORA001"].get("ja_confirmada") is True)

print("\n[9] As duas imprecisoes que a primeira rodada real mostrou")
c = banco()
# (a) placa reativada por termo POSTERIOR a rescisao: nao e saida, e espera de
# instalacao. Medido: 5 das 32 primeiras confirmacoes.
reg.gravar(c, CNPJ, lido("700", "contrato_novo", [ev(motor.ENTRA, "VOLTOU1")]),
           assinado=True, assinado_em="2019-01-01", origem="carga", enviado_por="carga")
reg.gravar(c, CNPJ, lido("8098", "rescisao", [ev(motor.RESCINDE, "VOLTOU1")]),
           assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
reg.gravar(c, CNPJ, lido("8708", "aditivo", [ev(motor.ENTRA, "VOLTOU1")]),
           assinado=True, assinado_em="2026-01-01", origem="carga", enviado_por="carga")
reg.recalcular(c, CNPJ, HOJE)
linhas = {x["placa"]: x for x in ader.classificar(c, {})}
checar("placa reativada por termo posterior NAO fecha", ader.SEM_RESCISAO,
       linhas["VOLTOU1"]["destino"])
# (b) placa que ja esta em aviso previo: a rescisao ja vale, o prazo corre so.
# Medido: 12 das 32 primeiras confirmacoes nao mudaram nada.
c2 = banco()
reg.gravar(c2, CNPJ, lido("255", "contrato_novo", [ev(motor.ENTRA, "AVISO01")]),
           assinado=True, assinado_em="2020-01-01", origem="carga", enviado_por="carga")
reg.gravar(c2, CNPJ, lido("9000", "rescisao", [ev(motor.RESCINDE, "AVISO01")]),
           assinado=True, assinado_em="2026-09-20", origem="carga", enviado_por="carga")
reg.recalcular(c2, CNPJ, HOJE)
linhas = {x["placa"]: x for x in ader.classificar(c2, {})}
checar("a placa esta em aviso previo", motor.EM_AVISO_PREVIO, linhas["AVISO01"]["situacao"])
checar("e nao recebe confirmacao: o prazo corre sozinho", ader.SEM_RESCISAO,
       linhas["AVISO01"]["destino"])
checar("com o motivo escrito", True, "calendário" in (linhas["AVISO01"].get("motivo") or ""))

print("\n[5] O motor NAO consulta a WESO -- e nao pode passar a consultar")
fonte = (RAIZ / "fpsl_weso" / "painel" / "contratos_eventos.py").read_text(encoding="utf-8")
for proibido in ("import sqlite3", "import httpx", "weso_cache", "weso_get", "open("):
    checar(f"o motor nao tem {proibido!r}", False, proibido in fonte)

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f_ in falhas:
    print("  -", f_)
sys.exit(1 if falhas else 0)
