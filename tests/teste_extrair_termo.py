"""Ler o termo e cruzar o cliente — passo 2 do cadastro por termo.

Exercita a rota com TRÊS TERMOS REAIS, e os números vêm de medição, não de
expectativa: foram lidos em 17/08 antes de existir código nenhum.

  8739 (contrato novo)  4 veículos, TODOS por chassi, nenhum com placa
  8840 (aditivo)        1 placa convencional
  8800 (upgrade)        11 veículos: placas, um número de SÉRIE, um chassi
                        grudado com espaço no meio, e uma linha SEM descrição

🚨 O 8800 É O TERMO EM QUE O EXTRATOR INVENTAVA A PLACA `RFD 2447`, corrigido
em 07/08. Exigir 11 de 11 aqui é o que impede a regressão voltar.

Roda na VPS: venv/bin/python tests/teste_extrair_termo.py
Lê Harmonit e WESO (cruzamento do cliente). NÃO ESCREVE NADA.
"""
import asyncio
import pathlib
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel.auth import criar_token  # noqa: E402

BASE = "http://127.0.0.1:8004"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


async def extrair(c, h, fixture, perfil):
    with open(FIXTURES / fixture, "rb") as f:
        r = await c.post(f"/painel/api/placas/extrair?perfil={perfil}",
                         headers=h, files={"arquivo": (fixture, f.read(),
                                                       "application/pdf")})
    return r


async def main():
    admin = await storage.buscar_usuario_painel("admin")
    h = {"Authorization": "Bearer " + criar_token(admin["login"])}

    async with httpx.AsyncClient(base_url=BASE, timeout=180) as c:
        print("\n[1] 8739 — contrato novo, TODOS por chassi")
        r = await extrair(c, h, "contrato_novo_8739.pdf", "cliente_novo")
        checar("respondeu 200", 200, r.status_code)
        d = r.json()
        checar("leu o termo", "8739", d["termo"])
        checar("4 veículos", 4, len(d["itens"]))
        # 🚨 nenhum é convencional -- é o caso que NENHUMA fixture antiga tinha
        checar("nenhum é placa convencional", 0,
               sum(1 for i in d["itens"] if i["convencional"]))
        checar("todos começam com CHASSI:", 4,
               sum(1 for i in d["itens"] if i["placa"].startswith("CHASSI:")))
        # ⚠️ chassi passa INALTERADO pela formatação
        checar("o chassi não é mutilado pela normalização", True,
               all(i["placa"] == i["placa_gravada"] for i in d["itens"]))
        checar("perfil sem recipiente", None, d["recipiente_sufixo"])
        checar("todos têm descrição", 0,
               sum(1 for i in d["itens"] if i["sem_descricao"]))

        print("\n[2] 8840 — aditivo, uma placa convencional")
        r = await extrair(c, h, "aditivo_8840.pdf", "aditivo")
        d = r.json()
        checar("leu o termo", "8840", d["termo"])
        checar("1 veículo", 1, len(d["itens"]))
        checar("é convencional", True, d["itens"][0]["convencional"])
        checar("a placa é a do documento", "TQD 2E45", d["itens"][0]["placa"])

        print("\n[3] 8800 — upgrade, o termo mais difícil")
        r = await extrair(c, h, "upgrade_4g_8800.pdf", "upgrade")
        d = r.json()
        checar("leu o termo", "8800", d["termo"])
        # 🚨 ONZE. Antes de 07/08 lia 9 e inventava a `RFD 2447`.
        checar("11 de 11 veículos", 11, len(d["itens"]))
        placas = [i["placa"] for i in d["itens"]]
        checar("não inventa a RFD 2447", False, "RFD 2447" in placas)
        checar("achou o número de série", True, "SERIE 16994" in placas)
        checar("achou o chassi grudado, com espaço no meio", True,
               "CHASSI:1BM6115J JMD002601" in placas)
        checar("2 não convencionais", 2,
               sum(1 for i in d["itens"] if not i["convencional"]))
        # ⚠️ a `FKX 9E34` vem SEM descrição no documento -- a tela exige que o
        # operador preencha, e é por este sinal que ela sabe qual destacar
        checar("uma linha sem descrição", 1,
               sum(1 for i in d["itens"] if i["sem_descricao"]))
        checar("e é a FKX 9E34", "FKX 9E34",
               next(i["placa"] for i in d["itens"] if i["sem_descricao"]))
        checar("o perfil traz recipiente -UPGRADE", "-UPGRADE",
               d["recipiente_sufixo"])

        print("\n[4] o cruzamento do cliente")
        # 🚨 POR CNPJ, NUNCA POR NOME. Os dois sistemas guardam nomes
        # diferentes para o mesmo documento.
        cli = d["cliente"]
        checar("traz o nome do termo", True, bool(cli["nome_no_termo"]))
        checar("e o documento só com alfanuméricos", True,
               cli is not None and d["documento"].isalnum())
        checar("achou o cliente no Harmonit", True, bool(cli["harmonit_id"]))
        checar("e na WESO", True, bool(cli["weso_id"]))

        print("\n[5] o que a rota RECUSA")
        r = await extrair(c, h, "upgrade_4g_8820.pdf" if False else
                          "upgrade_8820.pdf", "manutencao_troca")
        checar("perfil sem termo é recusado", 400, r.status_code)
        checar("e diz o motivo", True, "digitado" in r.text.lower())

        r = await extrair(c, h, "upgrade_8820.pdf", "perfil_que_nao_existe")
        checar("perfil desconhecido é recusado", 400, r.status_code)

        print("\n[6] a tranca da aba")
        r = await c.post("/painel/api/placas/extrair?perfil=upgrade",
                         files={"arquivo": ("x.pdf", b"%PDF-", "application/pdf")})
        checar("sem token dá 401", 401, r.status_code)


asyncio.run(main())

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
