"""Gravação e ficha da Gestão de Contratos — etapa C3.

Roda o núcleo em banco de MEMÓRIA: as regras se provam sem o `fpsl.db` e sem
asyncio. O que o router faz por cima (upload, CNPJ do formulário, 409 de PDF
repetido) está no `teste_contratos_router`.

🚨 O CASO QUE ESTE TESTE EXISTE PARA FECHAR é a Maxi Confort 8872: o motor
sozinho deixava 11 placas onde a auditoria conferiu 10, porque a anotação da
troca diz quem ENTRA e nunca quem SAI. A saída vem CONFIRMADA por gente, fica
gravada como evento com a autoria, e só então a conta fecha.

Roda na VPS:  venv/bin/python tests/teste_contratos_registro.py
Não toca o banco real: tudo em `:memory:`.
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

HOJE = date(2026, 10, 13)
MAXI = "20480457000158"
ZAGO = "44213607000125"
ok, falhas = 0, []


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
    return c


def ev(acao, placa, fonte=motor.ASSINADO):
    return {"acao": acao, "placa": placa, "fonte": fonte}


def lido(numero, perfil, eventos, **kw):
    return dict(numero=numero, perfil=perfil, eventos=eventos, a_definir=False, **kw)


print("\n[1] Maxi Confort 8872 — a troca fecha quando a saida e confirmada")
c = banco()
assinadas = ("CYR2B15", "DVS2992", "DVT3D81", "EJV7D20", "FLT0F07",
             "FTO3F51", "GEE7E85", "GFZ0726", "GYQ4J53", "HGO9D77")
termo_id = reg.gravar(
    c, MAXI, lido("8872", "contrato_novo", [ev(motor.ENTRA, p) for p in assinadas]),
    assinado=True, assinado_em="2026-09-15", origem="upload", enviado_por="iago",
    hash_arquivo="hash-do-assinado-8872",
    eventos_do_harmonit=[ev(motor.ENTRA, "FAC5H30", motor.HARMONIT)],
    troca_registrada="FAC 5H30 - Cliente pediu alteracao da placa em 30/09/2026 via Movizap",
    saida_confirmada=["DVS2992"])
f = reg.ficha(c, MAXI, HOJE)
checar("gravou o termo", 1, termo_id)
checar("o contrato sustenta 10 placas, igual a WESO", 10, len(f["sustentadas"]))
checar("FAC5H30 entrou", True, "FAC5H30" in f["sustentadas"])
checar("DVS2992 saiu", False, "DVS2992" in f["sustentadas"])
porplaca = {p["placa"]: p for p in f["placas"]}
checar("e a situacao dela e SUBSTITUIDA", "SUBSTITUIDA", porplaca["DVS2992"]["situacao"])
# 🚨 A ficha tem de dizer QUEM decidiu a saida: foi gente, não documento.
checar("a ficha registra a autoria da saida", True, "iago" in (porplaca["DVS2992"]["obs"] or ""))
checar("e a placa que entrou diz que veio da troca", True,
       "troca registrada" in (porplaca["FAC5H30"]["obs"] or ""))
# ⚠️ A observacao da troca é SÓ de quem veio pela troca. A primeira versao
# marcava todas as placas do termo, inclusive as assinadas -- a ficha mentia
# sobre a origem delas.
checar("placa do documento assinado NAO ganha obs de troca", None, porplaca["CYR2B15"]["obs"])

print("\n[2] mesmo PDF duas vezes nao dobra evento")
try:
    reg.gravar(c, MAXI, lido("8872", "contrato_novo", [ev(motor.ENTRA, "XXX1234")]),
               assinado=True, assinado_em="2026-09-15", origem="upload",
               enviado_por="iago", hash_arquivo="hash-do-assinado-8872")
    checar("segunda gravacao recusada", "TermoJaGravado", "aceitou")
except reg.TermoJaGravado as e:
    checar("segunda gravacao recusada", True, e.termo_id == 1 and e.numero == "8872")
checar("continua com 1 termo", 1, c.execute("SELECT COUNT(*) FROM contrato_termo").fetchone()[0])
checar("e as placas nao dobraram", 10, len(reg.ficha(c, MAXI, HOJE)["sustentadas"]))

print("\n[3] Zago — oito termos, dois cancelados, 4 placas no fim")
c = banco()
zago = [
    ("3285", "contrato_novo", True, "2024-02-14", [ev(motor.ENTRA, p) for p in ("ETR2C29", "DDU9873", "DPC9F69")]),
    ("3394", "aditivo", True, "2024-05-07", [ev(motor.ENTRA, "RVF5G49")]),
    ("3566", "substituicao", True, "2024-09-26", [ev(motor.SAI, "DDU9873"), ev(motor.ENTRA, "FFW4925")]),
    ("8011", "substituicao", True, "2025-04-14", [ev(motor.SAI, "ETR2C29"), ev(motor.ENTRA, "NWO4C95")]),
    ("8590", "rescisao", False, None, [ev(motor.RESCINDE, "FFW4925"), ev(motor.RESCINDE, "RVF5G49")]),
    ("8838", "substituicao", True, "2026-09-11",
     [ev(motor.SAI, "RVF5G49"), ev(motor.SAI, "FFW4925"), ev(motor.ENTRA, "FUX7B86"), ev(motor.ENTRA, "BRX9I89")]),
    ("8853", "ressarcimento_com_termo", False, None, [ev(motor.RESCINDE, "RVF5G49")]),
]
for numero, perfil, assinado, quando, eventos in zago:
    reg.gravar(c, ZAGO, lido(numero, perfil, eventos), assinado=assinado, assinado_em=quando,
               origem="carga", enviado_por="carga", hash_arquivo=f"h-{numero}")
f = reg.ficha(c, ZAGO, HOJE)
checar("4 placas sustentadas", ["BRX9I89", "DPC9F69", "FUX7B86", "NWO4C95"], f["sustentadas"])
checar("os 2 termos sem assinatura aparecem na ficha", ["8590", "8853"], sorted(f["sem_assinatura"]))
checar("a linha do tempo vem ordenada pelo numero",
       ["3285", "3394", "3566", "8011", "8590", "8838", "8853"], [t["numero"] for t in f["termos"]])
checar("e cada termo leva seus eventos", 4, len([t for t in f["termos"] if t["numero"] == "8838"][0]["eventos"]))

print("\n[4] recalcular e idempotente, e o evento manda")
antes = reg.ficha(c, ZAGO, HOJE)["sustentadas"]
reg.recalcular(c, ZAGO, HOJE)
reg.recalcular(c, ZAGO, HOJE)
checar("rodar duas vezes nao muda nada", antes, reg.ficha(c, ZAGO, HOJE)["sustentadas"])
# As 8 placas que passaram pelo histórico da Zago: 4 sustentadas hoje e 4 que
# saíram por substituição (DDU9873, ETR2C29, RVF5G49, FFW4925).
checar("o cache tem uma linha por placa do historico, sem duplicar", 8,
       c.execute("SELECT COUNT(*) FROM contrato_placa WHERE cnpj = ?", (ZAGO,)).fetchone()[0])
checar("e as 4 que nao estao sustentadas sairam por substituicao", 4,
       c.execute("SELECT COUNT(*) FROM contrato_placa WHERE cnpj = ? AND situacao = 'SUBSTITUIDA'",
                 (ZAGO,)).fetchone()[0])
# 🚨 `contrato_placa` e CACHE, nunca fonte: sujar o cache e recalcular restaura.
c.execute("UPDATE contrato_placa SET situacao='RESCINDIDA' WHERE cnpj=? AND placa_texto='DPC9F69'", (ZAGO,))
checar("cache sujo e desfeito pelo recalculo", True, "DPC9F69" in reg.ficha(c, ZAGO, HOJE)["sustentadas"])

print("\n[5] o aviso previo vence pelo CALENDARIO, sem evento novo")
# ⚠️ Nada acontece no banco quando o prazo passa -- por isso a ficha recalcula
# na hora em vez de confiar no cache.
c = banco()
reg.gravar(c, "11111111111111", lido("9000", "contrato_novo", [ev(motor.ENTRA, "AAA1B34")]),
           assinado=True, assinado_em="2026-01-01", origem="carga", enviado_por="t", hash_arquivo="h-9000")
reg.gravar(c, "11111111111111", lido("9001", "rescisao", [ev(motor.RESCINDE, "AAA1B34")]),
           assinado=True, assinado_em="2026-07-16", origem="carga", enviado_por="t", hash_arquivo="h-9001")
checar("em 13/10 ainda esta no aviso previo (89 dias)",
       "EM_AVISO_PREVIO", reg.ficha(c, "11111111111111", date(2026, 10, 13))["placas"][0]["situacao"])
checar("em 15/10 ja venceu, sem nenhum evento novo",
       "RESCINDIDA", reg.ficha(c, "11111111111111", date(2026, 10, 15))["placas"][0]["situacao"])

print("\n[6] evento nao se atualiza, se acrescenta")
fonte = (RAIZ / "fpsl_weso" / "painel" / "contratos_registro.py").read_text(encoding="utf-8")
checar("nenhum UPDATE em contrato_evento", False, "UPDATE contrato_evento" in fonte)
checar("nenhum DELETE em contrato_evento", False, "DELETE FROM contrato_evento" in fonte)
# O unico DELETE e o do cache derivado, e ele e recriado no mesmo passo.
checar("o cache derivado e o unico apagado", 1, fonte.count("DELETE FROM"))
checar("e nada e escrito no Harmonit/WESO/Clicksign", False,
       any(s in fonte for s in ("harmonit_get", "harmonit_post", "weso_get", "weso_post", "clicksign")))

print("\n[7] termo marcado 'a revisar' aparece na ficha")
c = banco()
reg.gravar(c, "22222222222222", lido("9100", "contrato_novo", [ev(motor.ENTRA, "BBB1C34")]),
           assinado=True, assinado_em="2026-05-01", origem="carga", enviado_por="t",
           hash_arquivo="h-9100", revisar_motivo="troca registrada sem confirmacao de qual placa sai")
f = reg.ficha(c, "22222222222222", HOJE)
checar("a ficha lista o que precisa de revisao", 1, len(f["a_revisar"]))
checar("com o motivo", True, "sem confirmacao" in f["a_revisar"][0]["motivo"])

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f_ in falhas:
    print("  -", f_)
sys.exit(1 if falhas else 0)
