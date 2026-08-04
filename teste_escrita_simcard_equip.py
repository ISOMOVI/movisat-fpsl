"""Testes de ESCRITA na WESO — SIM Card e Rastreador. (2026-07-27)

Responde as perguntas do usuario:
  1. desativar ICCID?          -> JA RESPONDIDO: situacao='Cancelado' OCULTA o chip
                                   da listagem (registro continua existindo). Reversivel.
  2. desvincular chip do equipamento?
  3. cadastrar equipamento?
  4. inativar equipamento?

Dados de teste autorizados: chip 8955170220424545007 / equip 007559809 (id 49175).

CUIDADO aprendido na 1a rodada: depois de mexer na situacao, a consulta filtrada
pode voltar VAZIA -- o registro nao sumiu, foi ocultado. Nunca assumir que vazio
= apagado, e nunca deixar o script abortar antes de reverter.
"""
import argparse
import asyncio
import json

import httpx

from fpsl_weso.config import settings

TIMEOUT = 180
ICCID = "8955170220424545007"
SERIAL = "007559809"
SERIAL_NOVO = "FPSLTESTE0001"


async def post(c, path, body):
    r = await c.post(path, params={"key": settings.weso_api_key}, json=body)
    ct = r.headers.get("content-type", "")
    print(f"    POST {path} {json.dumps(body, ensure_ascii=False)[:110]}")
    print(f"      -> HTTP {r.status_code} [{'JSON' if 'json' in ct else 'HTML'}] "
          f"{r.text[:200].replace(chr(10), ' ')}")
    return r


async def ver_equip(c, serial=SERIAL):
    r = await c.get("/Rastreadores/Consultar",
                    params={"key": settings.weso_api_key, "numeroSerie": serial})
    try:
        lst = (r.json().get("Data", r.json())).get("rastreadores") or []
    except Exception:
        return None
    return lst[0] if lst else None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()
    print(f"== {'APLICANDO' if args.aplicar else 'DRY-RUN'} ==\n")

    async with httpx.AsyncClient(base_url=settings.weso_base_url, timeout=TIMEOUT) as c:
        eq0 = await ver_equip(c)
        if not eq0:
            print("!! equipamento de teste nao encontrado, abortando")
            return
        print(f"estado inicial equip: {json.dumps(eq0, ensure_ascii=False)[:240]}\n")
        simcard_original = eq0.get("simcard") or {}
        situacao_original = eq0.get("situacao")

        if not args.aplicar:
            print("faria: desvincular chip (3 formas) / cadastrar equip / inativar equip")
            return

        # ── 2. desvincular chip do equipamento ────────────────────────────────
        print("=" * 70)
        print("2. DESVINCULAR o chip do equipamento")
        print("=" * 70)
        ok2, forma_ok = False, None
        for rotulo, corpo in [
            ("simCard: null", {"id": eq0["id"], "simCard": None}),
            ("simCard.id: 0", {"id": eq0["id"], "simCard": {"id": 0}}),
            ("simCard.iccId vazio", {"id": eq0["id"], "simCard": {"iccId": ""}}),
        ]:
            print(f"  -- forma: {rotulo}")
            await post(c, "/Rastreadores/Atualizar", corpo)
            d = await ver_equip(c)
            atual = d.get("simcard") if d else "(consulta vazia)"
            print(f"    conferido: simcard={atual}")
            if d and not d.get("simcard"):
                ok2, forma_ok = True, rotulo
                break
        print(f"    >> DESVINCULAR: {'FUNCIONA via ' + forma_ok if ok2 else 'NAO FUNCIONA'}")
        if ok2 and simcard_original.get("id"):
            print("  -- revinculando")
            await post(c, "/Rastreadores/Atualizar",
                       {"id": eq0["id"], "simCard": {"id": simcard_original["id"]}})
            d = await ver_equip(c)
            print(f"    revinculado: simcard={d.get('simcard') if d else '(vazio)'}")
        print()

        # ── 3. cadastrar equipamento ──────────────────────────────────────────
        print("=" * 70)
        print(f"3. CADASTRAR equipamento novo ({SERIAL_NOVO})")
        print("=" * 70)
        ja = await ver_equip(c, SERIAL_NOVO)
        if ja:
            print(f"    ja existe: id={ja.get('id')} -- pulando")
            novo = ja
        else:
            await post(c, "/Rastreadores/Cadastro",
                       {"numeroSerie": SERIAL_NOVO,
                        "modelo": {"descricao": "Suntech ST310"},
                        "tipo": {"descricao": "Veiculo"}})
            novo = await ver_equip(c, SERIAL_NOVO)
            print(f"    conferido: {json.dumps(novo, ensure_ascii=False)[:240] if novo else 'NAO ENCONTRADO'}")
            print(f"    >> CADASTRAR EQUIP: {'FUNCIONA' if novo else 'NAO FUNCIONA'}")
        print()

        # ── 4. inativar equipamento ───────────────────────────────────────────
        print("=" * 70)
        print("4. INATIVAR equipamento — quais valores de situacao pegam?")
        print("=" * 70)
        alvo = novo or eq0
        print(f"    alvo: id={alvo['id']} serial={alvo['numeroSerie']} "
              f"situacao inicial={alvo.get('situacao')!r}")
        for valor in ["Cancelado", "Inativo", "Estoque"]:
            await post(c, "/Rastreadores/Atualizar",
                       {"id": alvo["id"], "situacao": {"descricao": valor}})
            d = await ver_equip(c, alvo["numeroSerie"])
            if d is None:
                print(f"    apos {valor!r}: SUMIU da consulta (ocultado, igual ao chip)")
            else:
                print(f"    apos {valor!r}: situacao={d.get('situacao')!r}")
        print()

        # ── garantir que o equip principal voltou ao estado original ──────────
        fim = await ver_equip(c)
        print("=" * 70)
        print(f"equip principal ao final: situacao={fim.get('situacao') if fim else '(vazio)'!r} "
              f"(era {situacao_original!r}) simcard={fim.get('simcard') if fim else None}")


asyncio.run(main())
