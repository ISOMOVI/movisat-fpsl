"""A ação `ANULA` do motor de contratos (`C7`). 2026-10-14.

🚨 POR QUE ELA EXISTE. A carga de 13/10 gravou a lista de placas do **Harmonit**
-- e o PDF do Harmonit é editado DEPOIS de assinado. Em 412 termos essa lista
difere do documento assinado, e é isso que faz a ficha dar 2.979 placas
sustentadas contra 2.811 da planilha. Quando a releitura do assinado mostra que
uma placa não está lá, o evento que a fez entrar está errado.

🚨 E NÃO HAVIA ATALHO HONESTO:
  · `SAI` deixaria a placa SUBSTITUIDA — inventa uma saída que não houve;
  · `RESCINDE` deixaria RESCINDIDA — inventa uma rescisão que não houve;
  · `UPDATE` no evento violaria a imutabilidade, que é o que faz "por que esta
    placa está ativa?" ter documento como resposta.
A verdade é outra: a placa **nunca esteve no contrato**. Então entra um evento
novo que aponta para o errado, e o errado continua visível.

Roda na VPS:  venv/bin/python tests/teste_contratos_anula.py
Banco em memória — não toca banco real, Harmonit, WESO nem Clicksign.
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


print("\n[1] ANULA tira a placa do contrato SEM dizer que ela saiu")
c = banco()
# A carga trouxe 3 placas da lista do Harmonit; o assinado só tem duas.
tid = reg.gravar(c, CNPJ, lido("2224", "aditivo",
                              [ev(motor.ENTRA, "FJW0B75"), ev(motor.ENTRA, "AAA1B23"),
                               ev(motor.ENTRA, "00D6NCCCK01011")]),
                 assinado=True, assinado_em="2021-08-03", origem="carga", enviado_por="carga")
f = reg.ficha(c, CNPJ, HOJE)
checar("antes, o contrato sustenta as 3", 3, len(f["sustentadas"]))

alvo = c.execute("""SELECT id FROM contrato_evento
                     WHERE termo_id = ? AND placa_texto = '00D6NCCCK01011'""", (tid,)).fetchone()[0]
r = reg.anular_evento(c, alvo, "c7-releitura",
                      "C7: constava na lista do Harmonit; o assinado nao traz esta placa")
f = reg.ficha(c, CNPJ, HOJE)
checar("depois, sustenta 2", 2, len(f["sustentadas"]))
checar("e a placa anulada nao esta entre elas", False, "00D6NCCCK01011" in f["sustentadas"])
# 🚨 A diferença que importa: ela não está RESCINDIDA nem SUBSTITUIDA. Ela
# simplesmente não faz parte do contrato -- porque nunca fez.
situacoes = {p.get("placa"): p["situacao"] for p in f["placas"]}
checar("a placa NAO virou rescindida nem substituida", None, situacoes.get("00D6NCCCK01011"))
checar("as outras duas continuam ativas",
       [motor.ATIVA, motor.ATIVA], [situacoes["AAA1B23"], situacoes["FJW0B75"]])

print("\n[2] O evento errado CONTINUA na base, apontado por quem o anulou")
checar("nada foi apagado: 3 entradas + 1 anulacao", 4,
       c.execute("SELECT COUNT(*) FROM contrato_evento WHERE termo_id = ?", (tid,)).fetchone()[0])
checar("a anulacao aponta para o evento errado", alvo,
       c.execute("SELECT corrige_evento_id FROM contrato_evento WHERE id = ?",
                 (r["anulacao_id"],)).fetchone()[0])
checar("com a autoria no texto", True, "c7-releitura" in c.execute(
    "SELECT obs FROM contrato_evento WHERE id = ?", (r["anulacao_id"],)).fetchone()[0])
checar("e a ficha explica a correcao", 1, len(f["correcoes"]))
checar("dizendo qual placa", "00D6NCCCK01011", f["correcoes"][0]["placa"])

print("\n[3] Anular duas vezes nao empilha correcao")
try:
    reg.anular_evento(c, alvo, "c7-releitura", "de novo")
    checar("a segunda anulacao foi recusada", True, False)
except reg.JaAnulado:
    checar("a segunda anulacao foi recusada", True, True)
checar("e nenhum evento novo entrou", 4,
       c.execute("SELECT COUNT(*) FROM contrato_evento WHERE termo_id = ?", (tid,)).fetchone()[0])
try:
    reg.anular_evento(c, r["anulacao_id"], "x", "anular a anulacao")
    checar("anular uma anulacao foi recusado", True, False)
except ValueError:
    checar("anular uma anulacao foi recusado", True, True)

print("\n[4] A anulacao vale nas DUAS passadas do motor")
# Passada 2 é a do termo SEM assinatura. Se o filtro valesse só na primeira, a
# placa anulada voltaria por ali -- e a correção não corrigiria nada.
c = banco()
tid = reg.gravar(c, CNPJ, lido("1993", "aditivo", [ev(motor.ENTRA, "B10217")]),
                 assinado=False, assinado_em=None, origem="carga", enviado_por="carga")
f = reg.ficha(c, CNPJ, HOJE)
checar("a placa entra pela passada do nao assinado", "nao assinado",
       f["placas"][0]["base"])
alvo = c.execute("SELECT id FROM contrato_evento WHERE termo_id = ?", (tid,)).fetchone()[0]
reg.anular_evento(c, alvo, "c7", "o assinado nao traz esta placa")
f = reg.ficha(c, CNPJ, HOJE)
checar("anulada, ela nao volta pela passada 2", 0, len(f["placas"]))

print("\n[5] A anulacao independe da ORDEM dos termos")
# O evento anulado pode estar num termo que vem ANTES na ordem; o motor varre
# todas as anulações antes de aplicar qualquer coisa.
c = banco()
t1 = reg.gravar(c, CNPJ, lido("255", "contrato_novo", [ev(motor.ENTRA, "ASC100")]),
                assinado=True, assinado_em="2020-01-01", origem="carga", enviado_por="carga")
reg.gravar(c, CNPJ, lido("8904", "rescisao", [ev(motor.RESCINDE, "BW212D-40")]),
           assinado=True, assinado_em="2026-09-29", origem="carga", enviado_por="carga")
alvo = c.execute("SELECT id FROM contrato_evento WHERE termo_id = ?", (t1,)).fetchone()[0]
reg.anular_evento(c, alvo, "c7", "o assinado nao traz esta placa")
f = reg.ficha(c, CNPJ, HOJE)
checar("a placa do termo 255 saiu do contrato", False, "ASC100" in f["sustentadas"])
checar("e o resto da historia continua", True, any(p.get("placa") == "BW212D-40" for p in f["placas"]))

print("\n[6] O motor nao quebra com ANULA, e o cache acompanha a ficha")
c = banco()
tid = reg.gravar(c, CNPJ, lido("3465", "contrato_novo",
                               [ev(motor.ENTRA, "AAA1B23"), ev(motor.ENTRA, "CCC3D45")]),
                 assinado=True, assinado_em="2024-07-02", origem="carga", enviado_por="carga")
alvo = c.execute("SELECT id FROM contrato_evento WHERE placa_texto = 'CCC3D45'").fetchone()[0]
reg.anular_evento(c, alvo, "c7", "o assinado nao traz esta placa")
# 🚨 `recalcular_todos` usa o OUTRO leitor de termos (`termos_de_todos`). Se só
# um dos dois passasse o `id`, a ficha e o grid discordariam -- e o grid lê o
# cache. Este é o teste que prende os dois juntos.
reg.recalcular_todos(c, HOJE)
cache = {p: s for p, s in c.execute(
    "SELECT placa_texto, situacao FROM contrato_placa WHERE cnpj = ?", (CNPJ,))}
f = reg.ficha(c, CNPJ, HOJE)
checar("o cache tem so a placa que o assinado confirma", {"AAA1B23": motor.ATIVA}, cache)
checar("e a ficha diz o mesmo", ["AAA1B23"], f["sustentadas"])

print("\n[7] ANULA entrou na lista de acoes, e o motor nao o aplica como estado")
checar("ANULA e acao valida", True, motor.ANULA in motor.ACOES)
# Chamar `_aplicar` com ANULA é no-op: quem trata é `situacao_das_placas`. Se
# fosse exceção, um evento de correção derrubaria a ficha inteira do cliente.
estado = {}
motor._aplicar({"numero": "1"}, {"acao": motor.ANULA, "placa": "AAA1B23"},
               "AAA1B23", estado, motor.ASSINADO, HOJE)
checar("aplicar ANULA nao mexe no estado nem levanta", {}, estado)

print("\n[8] A tabela aceita rodar criar+migrar duas vezes")
c = banco()
checar("migrar nao repete a coluna", [], tab.migrar(c))
cols = [r[1] for r in c.execute("PRAGMA table_info(contrato_evento)")]
checar("corrige_evento_id aparece uma vez", 1, cols.count("corrige_evento_id"))
checar("e o livro-razao da carga existe", 1, len(
    c.execute("SELECT name FROM sqlite_master WHERE name = 'contrato_carga_pdf'").fetchall()))

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f_ in falhas:
    print("  -", f_)
sys.exit(1 if falhas else 0)
