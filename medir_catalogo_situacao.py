# -*- coding: utf-8 -*-
"""Mede se os ITENS do catalogo "Situacao de OS" podem ser criados, RENOMEADOS
e excluidos pela API do Harmonit. NAO TOCA EM NENHUMA SITUACAO EM USO.

Pergunta dele (29/10): *"veja se o campo dos itens de cadastro da 'Situacao de
OS' podem ser alterados, por exemplo 'Aguardando chegada do fornecedor' ->
'Entrega de materiais'"*.

🚨 POR QUE NAO MEDE NA 15747: renomear um item do catalogo muda o ERP para
todo mundo, e a 15747 esta em 4 OS reais. Entao o teste cria um item
descartavel, renomeia ESSE, confere, e apaga. O que se aprende e o mesmo; o
que nao se arrisca e o vocabulario de producao.

⚠️ SE O DELETE FALHAR, sobra um item com nome auto-explicativo no catalogo
("ZZ TESTE API - APAGAR") e o script diz isso em voz alta -- melhor um nome
obvio do que um item mudo.

Uso:  ./venv/bin/python medir_catalogo_situacao.py           so le o catalogo
      ./venv/bin/python medir_catalogo_situacao.py --medir   cria, renomeia, apaga
"""
import asyncio
import json
import sys

sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso.harmonit_client import (  # noqa: E402
    harmonit_delete, harmonit_get, harmonit_post, start_harmonit_client,
    stop_harmonit_client)

EMPRESA_ID = 98          # a nossa, lida da propria OS 16991
NOME_1 = "ZZ TESTE API - APAGAR"
NOME_2 = "ZZ TESTE API - RENOMEADO"


def _dados(r):
    return r.get("data") if isinstance(r, dict) and "data" in r else r


async def catalogo() -> list:
    # 🚨 `take` EXPLICITO: sem ele o Harmonit devolve 10 e esconde o 11o
    # (medido em 29/10 -- a 15797 ficava de fora).
    r = await harmonit_get("/SituacaoOrdemServico/ObterSituacoesOS",
                           params={"take": 200, "skip": 0})
    d = _dados(r) or []
    if isinstance(d, dict):
        d = d.get("items") or d.get("lista") or []
    return [x for x in d if isinstance(x, dict)]


async def por_id(sid: int):
    try:
        r = await harmonit_get("/SituacaoOrdemServico/ObterSituacaoOS",
                               params={"situacaoOsId": sid})
        return _dados(r)
    except Exception as e:
        return {"_erro": f"{type(e).__name__}: {e}"}


async def main(medir: bool):
    await start_harmonit_client()
    novo_id = None
    try:
        antes = await catalogo()
        print("[1] catalogo com %d itens:" % len(antes))
        for s in antes:
            print("      %-7s %s" % (s.get("id"), s.get("descricao")))
        if not medir:
            print("\n[2] so leitura -- nada foi criado nem alterado.")
            return

        print("\n[2] CRIAR item descartavel (id: 0)")
        try:
            r = await harmonit_post(
                "/SituacaoOrdemServico/CadastrarOuAtualizar",
                {"id": 0, "empresaId": EMPRESA_ID, "descricao": NOME_1})
            print("    resposta: %s" % json.dumps(_dados(r), ensure_ascii=False, default=str)[:300])
        except Exception as e:
            print("    RECUSOU CRIAR: %s: %s" % (type(e).__name__, e))
            return

        depois = await catalogo()
        achados = [s for s in depois if s.get("descricao") == NOME_1]
        if not achados:
            print("    🚨 nao achei o item no catalogo depois de criar -- parei.")
            return
        novo_id = achados[0]["id"]
        print("    criado: id=%s  (catalogo foi de %d para %d itens)"
              % (novo_id, len(antes), len(depois)))

        print("\n[3] RENOMEAR esse mesmo id (o que a pergunta dele quer saber)")
        try:
            r = await harmonit_post(
                "/SituacaoOrdemServico/CadastrarOuAtualizar",
                {"id": novo_id, "empresaId": EMPRESA_ID, "descricao": NOME_2})
            print("    resposta: %s" % json.dumps(_dados(r), ensure_ascii=False, default=str)[:300])
        except Exception as e:
            print("    RECUSOU RENOMEAR: %s: %s" % (type(e).__name__, e))

        # 🚨 A prova e RELER, nunca o retorno do POST.
        lido = await por_id(novo_id)
        print("    releitura por id: %s" % json.dumps(lido, ensure_ascii=False, default=str)[:200])
        cat3 = await catalogo()
        ainda = [s for s in cat3 if s.get("id") == novo_id]
        print("    no catalogo: %s" % (ainda[0].get("descricao") if ainda else "SUMIU"))
        print("    renomeou? %s   criou item novo em vez de renomear? %s"
              % (bool(ainda and ainda[0].get("descricao") == NOME_2),
                 len(cat3) != len(depois)))

        print("\n[4] APAGAR o item de teste")
        try:
            r = await harmonit_delete("/SituacaoOrdemServico/Excluir",
                                      params={"situacaoOsId": novo_id})
            print("    resposta: %s" % json.dumps(_dados(r), ensure_ascii=False, default=str)[:200])
        except Exception as e:
            print("    RECUSOU APAGAR: %s: %s" % (type(e).__name__, e))

        fim = await catalogo()
        sobrou = [s for s in fim if s.get("id") == novo_id]
        print("\n[5] catalogo final: %d itens (comecou com %d)" % (len(fim), len(antes)))
        if sobrou:
            print("    🚨 SOBROU O ITEM DE TESTE id=%s %r -- apagar a mao no ERP."
                  % (novo_id, sobrou[0].get("descricao")))
        else:
            print("    limpo: o item de teste nao esta mais la.")
        iniciais = {s.get("id"): s.get("descricao") for s in antes}
        finais = {s.get("id"): s.get("descricao") for s in fim}
        mexidos = {k: (v, finais.get(k)) for k, v in iniciais.items()
                   if finais.get(k) != v}
        print("    itens pre-existentes alterados: %s" % (mexidos or "NENHUM"))
    finally:
        await stop_harmonit_client()


if __name__ == "__main__":
    asyncio.run(main("--medir" in sys.argv[1:]))
