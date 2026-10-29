# -*- coding: utf-8 -*-
"""Põe o catálogo "Situação de OS" do Harmonit nas 17 que ele definiu, na ORDEM dele.

🔵 Pedido dele, 29/10: *"eis as situações que precisamos manter"* + *"as
situações já estão na Ordem"*.

🔵 E as duas decisões que ele confirmou quando eu perguntei (não supus):
  · a **677** "Envio dos Equipamentos" (4 OS reais) é *"Enviar por
    correio/transportadora"*; *"Entrega de materiais prontos"* nasce NOVA;
  · a **15694** "Serviço Realizado" (19 OS) **pode ser renomeada** para
    *"Atendimento finalizado"* -- 🚨 e ela é a PORTA do Painel Financeiro do
    FPSL (`SITUACAO_SERVICO_REALIZADO`, a rotina de conferência dispara nela).
    O **id não muda**, então o FPSL continua funcionando; o que muda é o nome
    que a operação lê.

🚨 RENOMEAR É SEGURO, CRIAR É SEGURO, EXCLUIR NÃO ENTRA AQUI. A OS guarda o
`situacaoId` (número), nunca o nome -- então renomear não mexe em OS nenhuma.
Este script **não exclui** situação: as que ficam fora das 17 continuam no
Harmonit e só deixam de ser coluna no painel. Excluir uma situação com OS
pendurada deixaria OS apontando para id que não existe, e isso ninguém pediu.

🚨 A PROVA É RELER O CATÁLOGO, nunca o retorno do POST. ⚠️ E `take` explícito:
sem ele o Harmonit devolve só 10 (medido em 29/10).

Uso:  ./venv/bin/python ajustar_situacoes_os.py            # só mostra o plano
      ./venv/bin/python ajustar_situacoes_os.py --aplicar   # grava
"""
import asyncio
import sys

sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso.harmonit_client import (  # noqa: E402
    harmonit_get, harmonit_post, start_harmonit_client, stop_harmonit_client)

EMPRESA_ID = 98

# A ORDEM É A DELE, e ela passa a ser a ordem das colunas do painel.
# `id` None = criar nova.
AS_DEZESSETE = [
    (38,    "Novo Solicitação 1ª"),
    (None,  "Pendente de ação da Movisat"),
    (251,   "Configurar equipamentos e Sistemas"),
    (None,  "Entrega de materiais prontos"),
    (677,   "Enviar por correio/transportadora"),
    (15747, "Aguardando recebimento via correio/transportadora"),
    (15797, "Rescisão Aguardando Aviso Prévio"),
    (890,   "Agendar serviço"),
    (None,  "Confirmação agendamento"),
    (1316,  "Serviço Agendado"),
    (15696, "Aguardando devolução de equipamento"),
    (None,  "Analise de Equipamentos Retornados"),
    (15694, "Atendimento finalizado"),
    (None,  "Não atendido"),
    (15746, "Financeiro"),
    (15695, "Pós venda"),
    (None,  "Contratual"),
]


def _dados(r):
    return r.get("data") if isinstance(r, dict) and "data" in r else r


async def catalogo() -> dict:
    r = await harmonit_get("/SituacaoOrdemServico/ObterSituacoesOS",
                           params={"take": 200, "skip": 0})
    d = _dados(r) or []
    if isinstance(d, dict):
        d = d.get("items") or d.get("lista") or []
    return {x["id"]: (x.get("descricao") or "").strip()
            for x in d if isinstance(x, dict)}


async def main(aplicar: bool):
    await start_harmonit_client()
    try:
        antes = await catalogo()
        print(f"[1] catalogo hoje: {len(antes)} situacoes")

        plano = []
        for sid, nome in AS_DEZESSETE:
            if sid is None:
                plano.append(("CRIAR ", None, nome, None))
            elif antes.get(sid) == nome:
                plano.append(("IGUAL ", sid, nome, antes.get(sid)))
            else:
                plano.append(("RENOME", sid, nome, antes.get(sid)))

        print("\n[2] plano, na ORDEM dele:")
        for i, (acao, sid, nome, velho) in enumerate(plano, start=1):
            de = f"  (era {velho!r})" if acao == "RENOME" else ""
            print(f"   {i:>2}. {acao} {str(sid or '-'):>6}  {nome}{de}")

        fora = {sid: n for sid, n in antes.items()
                if sid not in {s for s, _ in AS_DEZESSETE if s}}
        print(f"\n[3] ficam FORA das 17 (nao sao excluidas, so saem do painel): "
              f"{fora or 'nenhuma'}")

        if not aplicar:
            print("\n[4] ENSAIO A SECO -- nada foi gravado. Use --aplicar.")
            return

        print("\n[4] gravando")
        for acao, sid, nome, _velho in plano:
            if acao == "IGUAL":
                continue
            corpo = {"id": sid or 0, "empresaId": EMPRESA_ID, "descricao": nome}
            try:
                r = await harmonit_post(
                    "/SituacaoOrdemServico/CadastrarOuAtualizar", corpo)
                novo = _dados(r) or {}
                print(f"    {acao} -> id {novo.get('id')}  {nome}")
            except Exception as e:  # noqa: BLE001
                print(f"    🚨 FALHOU {acao} {nome!r}: {type(e).__name__}: {e}")

        # 🚨 A prova e RELER.
        depois = await catalogo()
        print(f"\n[5] catalogo agora: {len(depois)} situacoes")
        esperadas = {}
        for sid, nome in AS_DEZESSETE:
            achados = [i for i, n in depois.items() if n == nome]
            if not achados:
                print(f"    🚨 NAO ACHEI {nome!r} na releitura")
                continue
            esperadas[achados[0]] = nome
        print("\n[6] a tupla para o `movizap/paineis.py`, na ordem dele:")
        for sid, nome in AS_DEZESSETE:
            achados = [i for i, n in depois.items() if n == nome]
            print(f'    ({achados[0] if achados else "?"}, "{nome}"),')
    finally:
        await stop_harmonit_client()


if __name__ == "__main__":
    asyncio.run(main("--aplicar" in sys.argv[1:]))
