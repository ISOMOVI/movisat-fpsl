# -*- coding: utf-8 -*-
"""Prova de ponta a ponta do Bloco A: cria UMA OS de análise e APAGA.

🔵 Autorizado por ele em 29/10: *"criar uma e apagar"*.

🚨 POR QUE ISTO EXISTE, se a suíte já está verde: o retorno do
`SalvarOrdemServico` **na criação** não está documentado pelo Harmonit -- a doc
documenta o da rota BÁSICA. A suíte prova que a rota trata todos os retornos
plausíveis; só a escrita real diz qual deles acontece. Sem isto, quem
descobriria seria o primeiro chamado de cliente.

🚨 ELE APAGA NO FIM, E DIZ EM VOZ ALTA SE NÃO CONSEGUIR. OS de teste que fica
em ERP de produção é sujeira que ninguém reconhece seis meses depois. O número
é impresso ANTES da remoção, para que exista rastro mesmo se o delete falhar.

⚠️ O NÚMERO DA OS É CONSUMIDO DE QUALQUER FORMA: remover a OS não devolve o
número à sequência. É o custo desta prova, e é uma vez.

Uso:  ./venv/bin/python provar_criacao_os.py 998063   (a Velasco, a UNICA)
      ./venv/bin/python provar_criacao_os.py <clienteId> --nao-apagar
"""
import asyncio
import json
import sys

sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso.harmonit_client import (  # noqa: E402
    harmonit_delete, harmonit_get, start_harmonit_client, stop_harmonit_client)
from fpsl_weso.routers import os_ponte  # noqa: E402

DESCRICAO = ("ZZ TESTE API - APAGAR. Prova de ponta a ponta do Bloco A "
             "(pipeline da operacao, 29/10). Esta OS foi aberta por script e "
             "deve ser removida em seguida.")


# 🚨 A SANDBOX E A VELASCO, E SO ELA -- regra dele, 29/10: *"nao pode usar
# outro CNPJ alem da VELASCO para teste, pois os tickets nascem e tem ligacoes.
# OS com outros clientes podem ser mal interpretadas pela OP"*.
#
# ⚠️ ISTO E UMA TRAVA, NAO UM AVISO, porque eu ja errei: a OS 17056 foi criada
# no cliente 68546 (DCBM) em 29/10 para provar a criacao. Foi apagada no mesmo
# minuto, mas entre a criacao e o delete ela existiu na fila que a Operacao le
# -- e ninguem ali sabia que era teste.
CLIENTE_SANDBOX = 998063   # Velasco Leite Pastelaria ME
NOME_SANDBOX = "Velasco Leite Pastelaria ME"


def conferir_sandbox(cliente_id: int) -> None:
    """Recusa qualquer cliente que nao seja a sandbox. Ver o bloco acima."""
    if cliente_id != CLIENTE_SANDBOX:
        raise SystemExit(
            f"*** RECUSADO: cliente {cliente_id}.\n"
            f"*** A sandbox e a {NOME_SANDBOX} ({CLIENTE_SANDBOX}), e so ela.\n"
            f"*** Regra dele: OS nascida em cliente de verdade entra na fila\n"
            f"*** que a Operacao le, e ninguem ali sabe que e teste.")


def _dados(r):
    d = r.get("data") if isinstance(r, dict) and "data" in r else r
    if isinstance(d, list):
        d = d[0] if d else None
    return d


async def main(cliente_id: int, apagar: bool) -> int:
    # 🚨 ANTES DE QUALQUER CHAMADA AO ERP.
    conferir_sandbox(cliente_id)
    await start_harmonit_client()
    try:
        entrada = os_ponte.CriarOS(
            cliente_id=cliente_id,
            # 🔵 Origem "link": o chamado do formulario publico. 1782.
            tipo_id=1782,
            problema_id=12760,      # ANALISE OPERACIONAL
            situacao_id=38,         # Novo Solicitacao 1a
            prioridade_id=382,      # Normal
            produto_servico_id=670990,   # ABERTURA DE OS, R$ 0,01
            descricao=DESCRICAO,
        )

        print("=== 1. ENSAIO A SECO (nada e escrito)")
        seco = await os_ponte.criar_os(entrada.model_copy(
            update={"conferir": True}))
        print(json.dumps(seco["corpo"], ensure_ascii=False, indent=2))

        print()
        print("=== 2. A ESCRITA DE VERDADE")
        r = await os_ponte.criar_os(entrada)
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))

        numero = r.get("numero_os")
        os_id = r.get("os_id")
        if not numero:
            print()
            print("*** SEM NUMERO. Ver o motivo acima -- PODE haver OS criada "
                  "no ERP sem registro. NAO rodar de novo sem conferir a mao.")
            return 1

        print()
        print(f"=== 3. A OS {numero} (osId {os_id}) EXISTE. RELENDO DO ERP")
        lida = _dados(await harmonit_get(
            "/OrdemServico/ObterOrdemServicoPorNumero",
            params={"numeroOs": numero})) or {}
        for campo in ("id", "numeroOrdem", "tipo", "problema", "situacaoId",
                      "prioridade", "parceiro", "produtoId", "status",
                      "statusStr", "dataPrevisao", "descricao"):
            print(f"   {campo:16} {lida.get(campo)!r}")

        if not apagar:
            print()
            print(f"*** A OS {numero} FICOU NO ERP, por pedido. "
                  f"Apagar: DELETE /OrdemServico/RemoverOrdemServico?osId={os_id}")
            return 0

        print()
        print(f"=== 4. APAGANDO A OS {numero} (osId {os_id})")
        try:
            await harmonit_delete("/OrdemServico/RemoverOrdemServico",
                                  params={"osId": os_id})
        except Exception as e:  # noqa: BLE001
            print(f"*** O DELETE FALHOU: {type(e).__name__}: {e}")
            print(f"*** A OS {numero} (osId {os_id}) FICOU NO ERP e tem de ser "
                  f"apagada a mao. O nome dela comeca com 'ZZ TESTE API'.")
            return 1

        # A prova de que apagou e RELER, nunca o retorno do delete.
        print("=== 5. CONFERINDO QUE SUMIU (a prova e reler)")
        try:
            depois = _dados(await harmonit_get(
                "/OrdemServico/ObterOrdemServicoPorNumero",
                params={"numeroOs": numero}))
            if depois:
                print(f"*** A OS {numero} AINDA RESPONDE a leitura: "
                      f"{ {k: depois.get(k) for k in ('id', 'situacaoId', 'statusStr')} }")
                print("*** Conferir a mao -- pode ser exclusao logica.")
            else:
                print(f"    a OS {numero} nao responde mais. Apagada.")
        except Exception as e:  # noqa: BLE001
            print(f"    a leitura da OS {numero} recusou ({type(e).__name__}) "
                  f"-- e o esperado para OS removida.")
        return 0
    finally:
        await stop_harmonit_client()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(asyncio.run(main(int(sys.argv[1]),
                              "--nao-apagar" not in sys.argv)))
