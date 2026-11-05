# -*- coding: utf-8 -*-
r"""Preenche o `termo` das OS que já estão no cache — uma vez, à mão.

🚨 **POR QUE ESTE SCRIPT EXISTE:** a coluna `termo` entrou em 05/11 e a
varredura só a preenche quando **relê** a OS. O `resync` relê uma janela
recente, então as OS antigas ficariam sem termo por tempo indefinido — e o
card diria "não tem termo" sobre OS que têm.

⚠️ **É DERIVAÇÃO, não dado do ERP.** O termo é extraído do texto da
`descricao` por `fpsl_weso/termo_da_os.py`, e a extração está medida lá.

🚨 **POR PADRÃO SÓ RELATA.** Nada é gravado sem `--aplicar`, e `--um` faz
exatamente uma OS — a régua desta casa: validar 1 antes do lote.

🚨 **NÃO SOBRESCREVE.** Só toca linha com `termo IS NULL`. Rodar duas vezes
não muda nada na segunda, e a segunda rodada **diz** "a preencher: 0".

⚠️ **UMA LEITURA DO HARMONIT POR OS.** São ~600 OS no cache. Não é de graça, e
é por isso que roda à mão e uma vez só.

Uso:
    venv/bin/python scripts/termo_das_os.py            # só relata
    venv/bin/python scripts/termo_das_os.py --um       # grava 1
    venv/bin/python scripts/termo_das_os.py --aplicar  # grava o lote
"""
import argparse
import asyncio
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso import storage                                    # noqa: E402
from fpsl_weso.harmonit_client import (harmonit_get,             # noqa: E402
                                       start_harmonit_client,
                                       stop_harmonit_client)
from fpsl_weso.termo_da_os import termo_da_descricao             # noqa: E402


def _uma(resposta):
    d = (resposta.get("data") if (isinstance(resposta, dict) and resposta.get("data"))
         else resposta)
    return d[0] if isinstance(d, list) else d


def _a_preencher() -> list:
    """As OS do cache ainda sem termo. ⚠️ Excluída não entra: OS que sumiu do
    ERP não se relê, e a leitura só devolveria 'não encontrada'."""
    with storage._connect() as conn:
        return [r[0] for r in conn.execute(
            "SELECT numero_os FROM os_historico "
            " WHERE coalesce(excluida, 0) = 0 AND termo IS NULL "
            " ORDER BY numero_os DESC").fetchall()]


def _gravar(numero_os: int, termo: str) -> None:
    """Grava SÓ o termo, e só se continuar nulo.

    🚨 UPDATE direto e estreito em vez de `salvar_os_historico`: o save grava a
    OS inteira, e este script não tem (nem quer ter) os outros 16 campos na
    mão. Mexer só na coluna que é o assunto é o que torna a rodada reversível
    de cabeça.
    """
    with storage._connect() as conn:
        conn.execute(
            "UPDATE os_historico SET termo = ? "
            " WHERE numero_os = ? AND termo IS NULL", (termo, numero_os))


async def rodar(aplicar: bool, quantas: int | None) -> None:
    await start_harmonit_client()
    try:
        numeros = _a_preencher()
        print(f"OS no cache a preencher: {len(numeros)}")
        if quantas is not None:
            numeros = numeros[:quantas]
            print(f"nesta rodada: {len(numeros)}")
        com = sem = erro = 0
        for n in numeros:
            try:
                d = _uma(await harmonit_get(
                    "/OrdemServico/ObterOrdemServicoPorNumero",
                    params={"numeroOs": n}))
            except Exception as exc:                 # noqa: BLE001
                erro += 1
                print(f"  OS {n}: nao deu para ler ({type(exc).__name__})")
                continue
            termo = termo_da_descricao((d or {}).get("descricao"))
            if not termo:
                sem += 1
                continue
            com += 1
            if aplicar:
                _gravar(n, termo)
                print(f"  OS {n}: termo {termo} GRAVADO")
            else:
                print(f"  OS {n}: termo {termo} (so relato, nada gravado)")
        print(f"\ncom termo: {com} | sem termo: {sem} | nao lidas: {erro}")
        if not aplicar:
            print("NADA FOI GRAVADO. Use --um para uma, --aplicar para o lote.")
    finally:
        await stop_harmonit_client()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aplicar", action="store_true",
                   help="grava o lote inteiro")
    p.add_argument("--um", action="store_true",
                   help="grava exatamente UMA OS — valide antes do lote")
    a = p.parse_args()
    asyncio.run(rodar(aplicar=a.aplicar or a.um,
                      quantas=1 if a.um else None))


if __name__ == "__main__":
    main()
