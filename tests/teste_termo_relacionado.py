"""O contrato do outro lado nas OS de titularidade -- 2026-09-23.

A aba Operações nunca mandou o `termo_relacionado`: as OS dos perfis 5 e 6
saíam sem o nº do contrato do outro lado, que a tela velha escrevia. Medido
no uso real: OS 16799 (antigo, termo 8850) e 16801 (novo, termo 8835) são as
duas pontas da MESMA transferência, e nenhuma cita a outra.

O que este teste prende:

  1. **A leitura do novo titular** reconhece "transferência de titularidade
     contrato nº N" (termo 8771 -> 2395). E NÃO "Já instalado através do
     contrato nº N" (8785): esse é o contrato novo ou aditivo que o novo
     titular usou para se vincular, não o outro lado (usuário, 23/09).
  2. **O antigo titular continua** lendo o que já lia (8787 -> 8785).
  3. **A OS leva o número** -- `descricao_titularidade`, nos dois perfis.
  4. **A tela**, dirigida com as respostas REAIS do router: mostra quando o
     termo traz, pede quando não traz, e o número chega ao payload.

Roda na VPS: venv/bin/python tests/teste_termo_relacionado.py
"""
import asyncio
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path("/home/claude/fpsl_weso")
sys.path.insert(0, str(RAIZ))

from fastapi import UploadFile                                     # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg               # noqa: E402
from fpsl_weso.painel import operacoes_extracao as extracao        # noqa: E402
from fpsl_weso.painel import operacoes_os as oos                   # noqa: E402
from fpsl_weso.painel.routers import operacoes_router as R         # noqa: E402

FIX = RAIZ / "tests" / "fixtures"
ok, achados = 0, []


def checar(nome, cond, detalhe=""):
    global ok
    if cond:
        ok += 1
        print(f"  OK   {nome}")
    else:
        achados.append(nome)
        print(f"  FALHA {nome}" + (f"  -- {detalhe}" if detalhe else ""))


def pdf(nome):
    return io.BytesIO((FIX / nome).read_bytes())


def extrair(nome, perfil):
    return asyncio.run(R.extrair(None, perfil=perfil, _=None,
                                 arquivo=UploadFile(file=pdf(nome), filename=nome)))


# ── 1. a leitura ─────────────────────────────────────────────────────────────
print("== 1. a leitura do novo titular ==")
checar("8771: 'transferência de titularidade contrato nº 2395' -> 2395",
       extracao.relacionado_novo_titular(pdf("transferencia_novo.pdf")) == "2395")
checar("8785: 'Já instalado através do contrato nº 2702' NÃO é o outro lado",
       extracao.relacionado_novo_titular(pdf("transferencia_existente.pdf")) is None)

novo = extrair("transferencia_novo.pdf", "transferencia_novo_titular")
checar("/extrair do novo titular devolve 2395", novo["termo_relacionado"] == "2395",
       novo["termo_relacionado"])
sem = extrair("transferencia_existente.pdf", "transferencia_novo_titular")
checar("/extrair do 8785 devolve vazio (a tela pede)", sem["termo_relacionado"] is None,
       sem["termo_relacionado"])
antigo = extrair("termo_errado.pdf", "transferencia_antigo_titular")
checar("/extrair do antigo titular continua 8785", antigo["termo_relacionado"] == "8785",
       antigo["termo_relacionado"])

# ── 2. quem pede ─────────────────────────────────────────────────────────────
print("\n== 2. só os perfis de titularidade pedem ==")
perfis = asyncio.run(R.listar_perfis(None))["perfis"]
pedem = sorted(p["id"] for p in perfis if p.get("pede_relacionado"))
checar("pedem: antigo e novo titular, e só eles",
       pedem == ["transferencia_antigo_titular", "transferencia_novo_titular"], pedem)

# ── 3. a OS ──────────────────────────────────────────────────────────────────
print("\n== 3. a OS leva o número, nas duas pontas ==")


def descricao(perfil, termo, rel):
    body = oos.MontarInput(perfil=perfil, cliente_id=1, termo=termo,
                           termo_relacionado=rel, produto_servico_id=6966,
                           placas=[oos.PlacaOS(placa="RFD 0E02", veiculo="X")])
    ops = oos.montar(body, cfg.PERFIS[perfil], [[]], [], [], {}, {}, {})
    return ops[0]["descricao"]


d = descricao("transferencia_antigo_titular", "8850", "8835")
checar("antigo 8850 cita o 8835", "TERMO 8850 | termo relacionado 8835 | placas:" in d, d)
d = descricao("transferencia_novo_titular", "8835", "8850")
checar("novo 8835 cita o 8850", "TERMO 8835 | termo relacionado 8850 | placas:" in d, d)
d = descricao("transferencia_antigo_titular", "8850", "")
checar("sem número, a OS sai como sempre saiu", "relacionado" not in d
       and d.startswith("TRANSFERENCIA TITULARIDADE (ANTIGO TITULAR): TERMO 8850 | placas:"), d)

# ── 4. a tela ────────────────────────────────────────────────────────────────
print("\n== 4. a tela, com as respostas reais do router ==")
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                 encoding="utf-8") as f:
    json.dump({"com": antigo, "sem": sem}, f, ensure_ascii=False)
try:
    saida = subprocess.run(
        ["node", str(RAIZ / "tests" / "exercitar_operacoes.js"),
         str(RAIZ / "frontend" / "operacoes.html")],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "EXTRAIR_REL": f.name})
finally:
    os.unlink(f.name)
t = json.loads(saida.stdout or "{}")
checar("o exercício rodou sem erro", not t.get("erros") and saida.returncode == 0,
       (t.get("erros") or [saida.stderr[-300:]])[0][:300])
checar("termo que traz: mostra o número", "Contrato do outro lado: <strong>8785</strong>"
       in (t.get("rel_com_resumo") or ""), (t.get("rel_com_resumo") or "")[-200:])
checar("termo que traz: não pede", t.get("rel_com_pede") == "none", t.get("rel_com_pede"))
checar("termo que traz: o número vai no payload", t.get("rel_com_payload") == "8785",
       t.get("rel_com_payload"))
checar("termo que não traz: pede", t.get("rel_sem_pede") == "block", t.get("rel_sem_pede"))
checar("em branco, vai vazio (a OS sai como hoje)", t.get("rel_sem_payload_vazio") == "",
       repr(t.get("rel_sem_payload_vazio")))
checar("digitado ' 88.35 ', vai 8835", t.get("rel_sem_payload_digitado") == "8835",
       t.get("rel_sem_payload_digitado"))
checar("perfil que não é de titularidade não pede", t.get("rel_aditivo_pede") == "none",
       t.get("rel_aditivo_pede"))

for a in achados:
    print("  FALHOU:", a)
print(f"\n{ok} OK, {len(achados)} falha(s)")
sys.exit(1 if achados else 0)
