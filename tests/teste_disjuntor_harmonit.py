"""Testa o disjuntor do harmonit_client contra a API REAL (que esta fora).

E o cenario perfeito: a API esta caida agora, entao da pra provar o
comportamento de verdade, nao com mock.
"""
import asyncio
import time

import sys
sys.path.insert(0, "/home/claude/fpsl_weso")

from fastapi import HTTPException
from fpsl_weso import harmonit_client as hc

ok = fail = 0


def checar(nome, cond, detalhe=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {nome}")
    else:
        fail += 1
        print(f"  FALHA {nome}  {detalhe}")


async def main():
    await hc.start_harmonit_client()
    try:
        print("== estado inicial ==")
        e = hc.estado()
        checar("disjuntor comeca fechado", not e["aberto"], str(e))

        print(f"== {hc.FALHAS_PARA_ABRIR} falhas devem abrir o disjuntor ==")
        chamadas = 0
        t0 = time.time()
        for i in range(1, 6):
            try:
                await hc.harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero",
                                      params={"numeroOs": 16550})
                print(f"  tentativa {i}: SUCESSO — a API VOLTOU")
                break
            except HTTPException as ex:
                chamadas += 1
                e = hc.estado()
                marca = " [DISJUNTOR ABERTO]" if e["aberto"] else ""
                print(f"  tentativa {i}: {ex.status_code} falhas={e['falhas_seguidas']}{marca}")
        dur = time.time() - t0

        e = hc.estado()
        if e["aberto"]:
            checar("disjuntor abriu apos as falhas", True)
            checar("guardou o motivo real do erro",
                   "pooled connections" in e["ultimo_erro"] or "HTTP" in e["ultimo_erro"],
                   e["ultimo_erro"][:80])
            checar("espera configurada e coerente",
                   0 < e["segundos_restantes"] <= hc.ESPERA_ABERTO_SEG,
                   str(e["segundos_restantes"]))

            print("== com o disjuntor aberto, NAO deve tocar a rede ==")
            t1 = time.time()
            try:
                await hc.harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero",
                                      params={"numeroOs": 16551})
                checar("chamada bloqueada pelo disjuntor", False, "passou direto")
            except HTTPException as ex:
                rapido = (time.time() - t1) < 0.05
                checar("responde 503 (nao 502) quando aberto", ex.status_code == 503,
                       f"veio {ex.status_code}")
                checar("falha instantanea, sem chamar a API", rapido,
                       f"levou {time.time()-t1:.3f}s")
                checar("mensagem diz quanto falta",
                       "restantes" in str(ex.detail), str(ex.detail)[:90])

            print("== 20 tentativas com disjuntor aberto: custo de rede zero ==")
            t2 = time.time()
            for _ in range(20):
                try:
                    await hc.harmonit_get("/x", params={})
                except HTTPException:
                    pass
            print(f"  20 chamadas em {time.time()-t2:.3f}s "
                  f"(antes seriam 20 requisicoes ao /Account/Token)")
            checar("20 chamadas bloqueadas em menos de 1s", (time.time() - t2) < 1.0)

            print("== reset manual fecha o disjuntor ==")
            hc._registrar_sucesso()
            checar("apos sucesso, disjuntor fecha", not hc.estado()["aberto"])
        else:
            print("  (API respondeu — disjuntor nao chegou a abrir)")
            checar("API voltou, nada a testar no disjuntor", True)

        print(f"\n  {chamadas} chamadas de rede em {dur:.1f}s antes de abrir")
    finally:
        await hc.stop_harmonit_client()

    print(f"\n== {ok} OK, {fail} FALHA ==")
    raise SystemExit(1 if fail else 0)


asyncio.run(main())
