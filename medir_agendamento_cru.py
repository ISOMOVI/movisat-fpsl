# -*- coding: utf-8 -*-
"""N2.1 — LE o `agendamentoOS` CRU do Harmonit e mostra a janela gravada.

🔵 ELE, 23/11: *"os agendamentos feitos por aqui no Movizap, continuam não
sendo escritos nas OS, precisamos de um definitivo para isso!"*

🚨 A PERGUNTA QUE ESTE SCRIPT RESPONDE, E SO ELA: a DATA foi escrita? A medicao
de 23/11 mostrou que o compromisso EXISTE (`tem_agendamento = True`, o
`agendamento_id` bate com o que gravamos, o `usuario_id` e o tecnico de
verdade), mas o resumo da ficha devolve so `usuario_id`, `nome`,
`agendamento_id` e `vinculos` -- **sem `start`/`end`**. Sem a data, o `ok` da
escrita nao prova nada: e a mesma licao do A10 (*"o `ok` so diz que o POST nao
deu erro"*) aplicada ao agendamento.

🚨 E HA UMA SEGUNDA PISTA NA MESMA LEITURA: em 23/11 o compromisso da 17143
voltou com `nome: null`. Quem olha a agenda do Harmonit pode estar vendo um
compromisso **sem tecnico identificado** -- e concluindo, com razao do ponto de
vista de quem olha, que *"nao foi escrito"*. Este script imprime o nome cru de
tres lugares (o vinculo, o compromisso e o cadastro) para separar as duas
coisas.

⚠️ SO LEITURA. Nenhuma rota de escrita e chamada: so
`/OrdemServico/ObterOrdemServicoPorNumero`. Nao escreve no banco, nao toca o
MoviZap, nao cria nem apaga nada.

Uso:  ./venv/bin/python medir_agendamento_cru.py 17143
      ./venv/bin/python medir_agendamento_cru.py 17143 17139 17137
      ./venv/bin/python medir_agendamento_cru.py --json 17143
"""
import asyncio
import json
import sys

sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso.harmonit_client import (  # noqa: E402
    harmonit_get, start_harmonit_client, stop_harmonit_client)


def _dados(r):
    return r.get("data") if isinstance(r, dict) and "data" in r else r


def _uma(r):
    """A OS, venha ela como dict, como lista de uma ou embrulhada em `data`.

    🚨 `list` x `dict` do Harmonit e armadilha catalogada da casa: a mesma
    rota devolve os dois formatos dependendo do endpoint.
    """
    d = _dados(r)
    if isinstance(d, list):
        return d[0] if d else {}
    return d or {}


async def ler(numero_os: int) -> dict:
    os_dict = _uma(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": numero_os}))
    linhas = []
    for t in os_dict.get("tecnico") or []:
        # 🚨 O `agendamentoOS` E O ALVO: e aqui que `start`/`end` moram, e e
        # isto que o resumo da ficha nao devolve. Imprime-se CRU, com as
        # chaves como o ERP as nomeia, para ninguem traduzir no caminho.
        linhas.append({
            "vinculo_id": t.get("id"),
            "usuarioId": t.get("usuarioId"),
            "nome_no_vinculo": t.get("nomeTecnico"),
            "email": t.get("email"),
            "agendamentoId": t.get("agendamentoId"),
            "agendamentoOS": t.get("agendamentoOS"),
        })
    return {"numero_os": numero_os, "os_id": os_dict.get("id"),
            "situacao_id": os_dict.get("situacaoId"),
            "tem_agendamento": bool(os_dict.get("agendamentoId")
                                    or any(l["agendamentoId"] for l in linhas)),
            "tecnicos": linhas}


def mostrar(r: dict) -> None:
    print("\n" + "=" * 70)
    print("OS %s  (osId interno %s, situacao %s)"
          % (r["numero_os"], r["os_id"], r["situacao_id"]))
    if not r["tecnicos"]:
        print("  🔴 NENHUMA LINHA DE TECNICO nesta OS -- nao ha compromisso")
        return
    for l in r["tecnicos"]:
        print("  linha %s | usuarioId %s | nome no vinculo: %r"
              % (l["vinculo_id"], l["usuarioId"], l["nome_no_vinculo"]))
        print("     agendamentoId: %s" % l["agendamentoId"])
        ag = l["agendamentoOS"]
        if ag is None:
            # 🚨 ISTO E A RESPOSTA RUIM, e tem nome: compromisso sem janela.
            print("     🔴 agendamentoOS AUSENTE (None) -- a linha tem id de "
                  "compromisso e NENHUMA janela: a data nao esta la")
            continue
        if not isinstance(ag, dict):
            print("     ⚠️ agendamentoOS veio como %s: %r"
                  % (type(ag).__name__, ag))
            continue
        # As chaves do ERP, como ele as nomeia. ⚠️ Nao se adivinha nome: o que
        # nao existir sai como AUSENTE, e isso ja e a medicao.
        for chave in ("id", "inicioCompromisso", "fimCompromisso", "start",
                      "end", "statusCompromisso", "motivoCancelamento",
                      "usuarioId", "nome", "clienteId", "ordemServicoId"):
            if chave in ag:
                print("     %-20s %r" % (chave, ag[chave]))
        sobra = [k for k in ag if k not in (
            "id", "inicioCompromisso", "fimCompromisso", "start", "end",
            "statusCompromisso", "motivoCancelamento", "usuarioId", "nome",
            "clienteId", "ordemServicoId")]
        if sobra:
            print("     outras chaves: %s" % ", ".join(sorted(sobra)))


async def main(argv: list[str]) -> int:
    so_json = "--json" in argv
    numeros = [int(a) for a in argv if a.isdigit()]
    if not numeros:
        print(__doc__)
        return 2
    await start_harmonit_client()
    try:
        saida = [await ler(n) for n in numeros]
    finally:
        await stop_harmonit_client()
    if so_json:
        print(json.dumps(saida, ensure_ascii=False, indent=2, default=str))
    else:
        for r in saida:
            mostrar(r)
        print("\n" + "=" * 70)
        print("⚠️ LEITURA APENAS. Nada foi escrito em lugar nenhum.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
