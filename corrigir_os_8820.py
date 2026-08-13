"""Acrescenta o material do equipamento nas OS 16742 e 16743 (termo 8820).

ESCREVE NO HARMONIT (producao). Autorizado pelo usuario em 2026-08-13.

Por que existe: essas duas OS foram geradas ANTES de o equipamento passar a
entrar como material -- sairam so com o servico do cabecalho e o ENTREGA OS.
O ajuste vale para as proximas; estas duas ficam para tras se ninguem corrigir.

Disciplina dos irmaos (`normalizar_espacos_placas.py`):
  - nada sem --aplicar
  - --somente <osId> faz UMA, para validar antes da outra
  - le o estado ANTES, escreve, RE-LE e confirma
  - aborta se ja existir o material (nao duplica)
  - o Harmonit MENTE no codigo de retorno: a prova e reler
"""
import argparse
import asyncio

from fpsl_weso.harmonit_client import (harmonit_get, harmonit_post,
                                       start_harmonit_client, stop_harmonit_client)
from fpsl_weso.painel import equipamentos
from fpsl_weso import storage

# (osId, numero, placa) -- o modelo vem da WESO, nao esta fixo aqui
ALVOS = [(862942, 16742, "OOM 3895"), (862943, 16743, "OOM 4131")]
SUFIXO = "-UPGRADE"


async def ler(osid):
    return await harmonit_get("/OrdemServico/ObterOrdemServico", params={"osId": osid})


def materiais_de(d):
    return [(m.get("idProduto"), m.get("descricao")) for m in (d.get("materiais") or [])]


async def corpo(aplicar, somente):
    for osid, numero, placa in ALVOS:
        if somente and osid != somente:
            continue
        print("=" * 74)
        print(f"OS {numero} (id {osid}) — {placa}")

        # o que a WESO diz que ENTRA nesta placa
        recipiente = equipamentos.placa_teste(placa, SUFIXO)
        modelo = equipamentos.modelo_da_placa(recipiente)
        prod = storage.produto_do_modelo(modelo) if modelo else None
        print(f"  recipiente : {recipiente}")
        print(f"  modelo     : {modelo!r}")
        if not prod:
            print("  SEM PRODUTO no de-para -- nada a fazer aqui.")
            continue
        print(f"  produto    : {prod['harmonit_id']} {prod['descricao']}  R$ {prod['valor']:.2f}")

        antes = await ler(osid)
        mats = materiais_de(antes)
        print(f"  materiais ANTES ({len(mats)}): {[m[1] for m in mats]}")
        if any(pid == prod["harmonit_id"] for pid, _ in mats):
            print("  JA TEM esse produto -- pulando (nao duplico).")
            continue

        if not aplicar:
            print("  (dry-run, nada enviado)\n")
            continue

        r = await harmonit_post("/OrdemServico/SalvarMaterialOrdemServico", {
            "id": 0, "empresaId": 98, "osId": osid,
            "produtoId": prod["harmonit_id"], "quantidade": 1,
            "valor": prod["valor"], "cobrar": False, "comodato": True,
        })
        print(f"  POST -> {str(r)[:120]}")

        depois = await ler(osid)
        mats2 = materiais_de(depois)
        print(f"  materiais DEPOIS ({len(mats2)}): {[m[1] for m in mats2]}")
        if not any(pid == prod["harmonit_id"] for pid, _ in mats2):
            print("  !! FALHOU: o material nao aparece na releitura. PARANDO.")
            return
        if depois.get("descricao") != antes.get("descricao"):
            print("  !! ATENCAO: a descricao mudou. PARANDO.")
            return
        print("  OK confirmado por releitura (descricao intacta)\n")

    print("fim.")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--somente", type=int)
    args = ap.parse_args()
    await start_harmonit_client()
    try:
        await corpo(args.aplicar, args.somente)
    finally:
        await stop_harmonit_client()


asyncio.run(main())
