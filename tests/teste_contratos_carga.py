"""Carga histórica da Gestão de Contratos — etapa C5.

Roda em banco de MEMÓRIA, sobre um JSONL de mentira com os clientes reais da
auditoria. O que esta suíte existe para impedir:

🚨 RODAR A CARGA DUAS VEZES NÃO PODE DOBRAR EVENTO. A carga não guarda PDF,
então o `UNIQUE(hash)` não protege — a chave é `(cnpj, numero, empresa)`.
Evento dobrado dobra placa no contrato, e seriam 12.114 eventos.

🚨 O MOTOR TEM DE CONTINUAR MANDANDO. A carga grava o que a auditoria apurou,
inclusive termo SEM assinatura; é o motor que aplica "vale o assinado". Se a
carga filtrasse, a JLM perderia as 5 placas que o contrato assinado sustenta.

Roda na VPS:  venv/bin/python tests/teste_contratos_carga.py
"""
import json
import pathlib
import sqlite3
import sys
import tempfile
from datetime import date

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import contratos_carga as carga        # noqa: E402
from fpsl_weso.painel import contratos_registro as reg       # noqa: E402
from fpsl_weso.painel import contratos_tabelas as tab        # noqa: E402

HOJE = date(2026, 10, 13)
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


def ev(acao, placa):
    return {"acao": acao, "placa": placa, "fonte": "assinado"}


# A JLM como a auditoria a exportou: 13 termos (os do Instituto repetem o
# número), o distrato 6026 CANCELADO e o upgrade 7235 sem registro.
JLM = {
    "cnpj": "62702410000131", "cliente": "JLM MATERIAIS PARA CONSTRUCAO LTDA",
    "termos": [
        {"numero": "5029", "empresa": "INSTITUTO", "tipo": "CONTRATO", "assinado": True,
         "assinado_em": "2021-06-28", "revisar_motivo": None,
         "eventos": [ev("ENTRA", p) for p in ("CPJ7279", "BKW9955", "BWO9236", "FIV9399", "DZH2E13", "DVT0268")]},
        {"numero": "5029", "empresa": "MOVISAT", "tipo": "CONTRATO", "assinado": True,
         "assinado_em": "2021-06-28", "revisar_motivo": None,
         "eventos": [ev("ENTRA", p) for p in ("CPJ7279", "BKW9955", "BWO9236", "FIV9399", "DZH2E13", "DVT0268")]},
        {"numero": "6026", "empresa": "MOVISAT", "tipo": "RESCISAO", "assinado": False,
         "assinado_em": None, "revisar_motivo": None,
         "eventos": [ev("RESCINDE", p) for p in ("CPJ7279", "BKW9955", "BWO9236", "FIV9399", "DZH2E13", "DVT0268")]},
        {"numero": "7172", "empresa": "MOVISAT", "tipo": "ADITIVO", "assinado": True,
         "assinado_em": "2024-11-11", "revisar_motivo": None, "eventos": [ev("ENTRA", "FIV9399")]},
        {"numero": "8564", "empresa": "MOVISAT", "tipo": "RESCISAO_FINAL", "assinado": True,
         "assinado_em": "2026-07-16", "revisar_motivo": None, "eventos": [ev("RESCINDE", "FIV9399")]},
        # SEM_ARQUIVO: entra sem evento e MARCADO, porque a lacuna tem de ser visível.
        {"numero": "9999", "empresa": "MOVISAT", "tipo": "SEM_ARQUIVO", "assinado": False,
         "assinado_em": None, "revisar_motivo": "contrato no índice do Harmonit sem PDF", "eventos": []},
    ],
}
ZAGO = {
    "cnpj": "44213607000125", "cliente": "ZAGO COMERCIO E SERVICOS DE REBOQUE LTDA",
    "termos": [
        {"numero": "3285", "empresa": "MOVISAT", "tipo": "CONTRATO", "assinado": True,
         "assinado_em": "2024-02-14", "revisar_motivo": None,
         "eventos": [ev("ENTRA", p) for p in ("ETR2C29", "DDU9873", "DPC9F69")]},
        {"numero": "8838", "empresa": "MOVISAT", "tipo": "SUBSTITUICAO", "assinado": True,
         "assinado_em": "2026-09-11", "revisar_motivo": None,
         "eventos": [ev("SAI", "ETR2C29"), ev("ENTRA", "FUX7B86")]},
    ],
}


def jsonl(clientes):
    f = pathlib.Path(tempfile.mkdtemp(prefix="carga_ctr_")) / "carga.jsonl"
    f.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in clientes) + "\n", encoding="utf-8")
    return str(f)


def banco():
    c = sqlite3.connect(":memory:")
    tab.criar(c)
    return c


print("\n[1] a carga grava os 2 clientes e marca a lacuna")
c = banco()
arq = jsonl([JLM, ZAGO])
r = carga.importar(c, arq)
checar("2 clientes", 2, r["clientes"])
checar("8 termos", 8, r["termos"])
checar("nenhum pulado na 1a vez", 0, r["pulados"])
checar("1 marcado a revisar (o SEM_ARQUIVO)", 1, r["a_revisar"])
checar("nenhum erro", 0, r["erros"])

print("\n[2] o MOTOR continua mandando — o distrato cancelado nao apaga nada")
f = reg.ficha(c, "62702410000131", HOJE)
# 🚨 Se a carga tivesse filtrado o termo sem assinatura, ou se tivesse deixado
# ele decidir, estas 5 placas desapareceriam do contrato.
checar("as 5 placas do contrato 5029 seguem sustentadas", 5,
       len([p for p in f["sustentadas"] if p != "FIV9399"]))
checar("FIV9399 em aviso previo (8564 assinado ha 89 dias)", "EM_AVISO_PREVIO",
       {p["placa"]: p for p in f["placas"]}["FIV9399"]["situacao"])
checar("o termo sem PDF aparece na lista de revisao", 1, len(f["a_revisar"]))
checar("com o motivo", True, "sem PDF" in f["a_revisar"][0]["motivo"])

print("\n[3] rodar a carga DE NOVO nao dobra nada")
antes_ev = c.execute("SELECT COUNT(*) FROM contrato_evento").fetchone()[0]
antes_sust = reg.ficha(c, "62702410000131", HOJE)["sustentadas"]
r2 = carga.importar(c, arq)
checar("nenhum termo novo", 0, r2["termos"])
checar("todos os 8 pulados", 8, r2["pulados"])
checar("eventos nao dobraram", antes_ev, c.execute("SELECT COUNT(*) FROM contrato_evento").fetchone()[0])
checar("e as placas sustentadas sao as mesmas", antes_sust,
       reg.ficha(c, "62702410000131", HOJE)["sustentadas"])

print("\n[4] o Instituto e a Movisat sao termos DISTINTOS, mesmo com o numero igual")
# O número do termo repete na migração; a chave é (cnpj, numero, empresa).
checar("os dois 5029 entraram", 2,
       c.execute("SELECT COUNT(*) FROM contrato_termo WHERE cnpj=? AND numero='5029'",
                 ("62702410000131",)).fetchone()[0])
checar("um de cada empresa", [("INSTITUTO",), ("MOVISAT",)],
       sorted(c.execute("SELECT empresa FROM contrato_termo WHERE cnpj=? AND numero='5029'",
                        ("62702410000131",)).fetchall()))

print("\n[5] a carga nao se disfarca de upload")
checar("origem e sempre 'carga'", [("carga",)],
       c.execute("SELECT DISTINCT origem FROM contrato_termo").fetchall())
checar("e nao guarda PDF", [(None,)],
       c.execute("SELECT DISTINCT arquivo FROM contrato_termo").fetchall())
checar("nem hash", [(None,)], c.execute("SELECT DISTINCT hash FROM contrato_termo").fetchall())

print("\n[6] Zago: a substituicao da carga tira e poe")
# ⚠️ FIXTURE REDUZIDO, de propósito: só 2 dos 8 termos da Zago. Então a
# DDU9873 CONTINUA sustentada aqui -- quem a tira é a substituição 3566, que
# não está neste recorte. A Zago inteira (4 placas no fim) está travada no
# `teste_contratos_registro`.
f = reg.ficha(c, "44213607000125", HOJE)
checar("3 sustentadas no recorte", ["DDU9873", "DPC9F69", "FUX7B86"], f["sustentadas"])
checar("ETR2C29 saiu por substituicao", "SUBSTITUIDA",
       {p["placa"]: p for p in f["placas"]}["ETR2C29"]["situacao"])

print("\n[7] linha quebrada no arquivo nao derruba a carga")
ruim = pathlib.Path(tempfile.mkdtemp(prefix="carga_ruim_")) / "c.jsonl"
ruim.write_text(json.dumps(ZAGO, ensure_ascii=False) + "\n{isso nao e json}\n"
                + json.dumps({"cliente": "sem cnpj", "termos": []}, ensure_ascii=False) + "\n",
                encoding="utf-8")
c2 = banco()
r3 = carga.importar(c2, str(ruim))
checar("gravou o cliente bom", 1, r3["clientes"])
checar("e contou 2 erros (json invalido + sem cnpj)", 2, r3["erros"])

print("\n[8] limite de clientes, para provar em pedaco antes do lote")
c3 = banco()
r4 = carga.importar(c3, arq, limite_clientes=1)
checar("so 1 cliente entrou", 1, r4["clientes"])
checar("e o outro nao esta no banco", 0,
       c3.execute("SELECT COUNT(*) FROM contrato_termo WHERE cnpj=?", ("44213607000125",)).fetchone()[0])

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f_ in falhas:
    print("  -", f_)
sys.exit(1 if falhas else 0)
