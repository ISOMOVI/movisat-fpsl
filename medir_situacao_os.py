# -*- coding: utf-8 -*-
"""Mede se da para MUDAR a situacao de uma OS existente no Harmonit. NAO LIGA NADA.

Pedido dele (29/10): *"veja se conseguimos mudar a situacao da OS via API no
harmonit, pegue a que usamos de teste"*.

O que se sabia antes deste script:
  - `situacaoId` E ACEITO NA CRIACAO -- o FPSL manda na geracao de OS do termo
    e a financeira releu `situacaoId=15746` (docs/fpsl/14_Painel_OS.md, E1-E5);
  - NAO HA rota de "alterar situacao": a unica escrita de OS e
    `POST /OrdemServico/SalvarOrdemServico`, que grava a OS INTEIRA;
  - mudar a situacao de uma OS JA EXISTENTE nunca foi medido.

🚨 RODA SO NA OS 16991, a sandbox da Pastelaria Velasco (cliente 998063), a
mesma que ele liberou para o teste do endereco e do AgendarTecnico.

🚨 O CORPO DA ESCRITA NAO E REESCRITO AQUI: importa o
`os_ponte._corpo_de_escrita`, que e o caminho provado (remapeia os nomes de
leitura para os de escrita), e troca SO o `situacaoId`. Duas montagens do mesmo
corpo seriam duas verdades.

Uso:
  ./venv/bin/python medir_situacao_os.py                 le e ensaia a seco
  ./venv/bin/python medir_situacao_os.py --gravar 890     grava a situacao 890
  ./venv/bin/python medir_situacao_os.py --restaurar      volta a original
"""
import asyncio
import json
import sys

sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso.harmonit_client import (  # noqa: E402
    harmonit_get, harmonit_post, start_harmonit_client, stop_harmonit_client)
from fpsl_weso.routers.os_ponte import (  # noqa: E402
    _corpo_de_escrita, _diferencas, _ESCALARES_DA_OS, _LISTAS_DA_OS)

OS_NUMERO = 16991
CLIENTE_ID = 998063
# Onde a situacao original fica guardada entre as duas rodadas -- sem isto o
# "--restaurar" dependeria da minha memoria.
MARCO = "/home/claude/fpsl_weso/caches/situacao_16991_original.json"


def _dados(r):
    return r.get("data") if isinstance(r, dict) and "data" in r else r


async def ler() -> dict:
    r = await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero",
                           params={"numeroOs": OS_NUMERO})
    d = _dados(r)
    if isinstance(d, list):
        d = d[0] if d else {}
    return d or {}


async def catalogo() -> list:
    r = await harmonit_get("/SituacaoOrdemServico/ObterSituacoesOS")
    d = _dados(r) or []
    if isinstance(d, dict):
        d = d.get("items") or d.get("lista") or []
    return d


def _retrato(d: dict) -> dict:
    r = {c: d.get(c) for c in _ESCALARES_DA_OS}
    for c in _LISTAS_DA_OS:
        r[c] = f"{len(d.get(c) or [])} itens"
    return r


async def main(alvo: int | None, restaurar: bool):
    await start_harmonit_client()
    try:
        antes = await ler()
        if not antes:
            print("NAO LI A OS %s -- parei." % OS_NUMERO)
            return
        atual = antes.get("situacaoId")
        print("[1] OS %s lida. situacaoId=%r  statusStr=%r  problema=%r"
              % (OS_NUMERO, atual, antes.get("statusStr"), antes.get("problema")))

        cat = await catalogo()
        print("[2] catalogo de situacoes: %d" % len(cat))
        for s in cat:
            if isinstance(s, dict):
                print("      %s  %s" % (s.get("id"), s.get("descricao") or s.get("nome")))

        if restaurar:
            try:
                with open(MARCO, encoding="utf-8") as f:
                    alvo = json.load(f)["situacao_original"]
            except Exception as e:
                print("[!] nao achei o marco (%s): %s" % (MARCO, e))
                return
            print("[3] RESTAURAR: voltando a situacao original %r" % alvo)

        if alvo is None:
            print("[3] ENSAIO A SECO -- nada sera escrito.")
            corpo = _corpo_de_escrita(antes, CLIENTE_ID, {})
            print(json.dumps(corpo, ensure_ascii=False, indent=2, default=str))
            return

        if not restaurar:
            with open(MARCO, "w", encoding="utf-8") as f:
                json.dump({"os": OS_NUMERO, "situacao_original": atual}, f)
            print("[3] situacao original %r guardada em %s" % (atual, MARCO))

        corpo = _corpo_de_escrita(antes, CLIENTE_ID, {})
        corpo["situacaoId"] = alvo
        print("[4] POST SalvarOrdemServico com situacaoId=%r" % alvo)
        try:
            resp = await harmonit_post("/OrdemServico/SalvarOrdemServico", corpo)
            print("    resposta: %s" % json.dumps(resp, ensure_ascii=False, default=str)[:400])
        except Exception as e:
            print("    RECUSOU: %s: %s" % (type(e).__name__, e))
            return

        depois = await ler()
        print("[5] releitura: situacaoId=%r" % depois.get("situacaoId"))
        mudou = _diferencas(antes, depois)
        print("[6] o que mudou de verdade na OS:")
        print(json.dumps(mudou, ensure_ascii=False, indent=2, default=str))
        fora = {k: v for k, v in mudou.items() if k != "situacaoId"}
        if fora:
            print("🚨 MUDOU ALGO FORA DA SITUACAO: %s" % list(fora))
        if depois.get("situacaoId") != alvo:
            print("🚨 A SITUACAO NAO GRAVOU: pedi %r, a OS tem %r"
                  % (alvo, depois.get("situacaoId")))
        else:
            print("OK: a situacao gravou e a releitura confirma.")
    finally:
        await stop_harmonit_client()


if __name__ == "__main__":
    args = sys.argv[1:]
    restaurar = "--restaurar" in args
    alvo = None
    if "--gravar" in args:
        alvo = int(args[args.index("--gravar") + 1])
    asyncio.run(main(alvo, restaurar))
