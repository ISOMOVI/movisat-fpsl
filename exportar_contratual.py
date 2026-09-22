#!/usr/bin/env python3
"""Exporta o vocabulario completo de vinculos para a planilha contratual.
SOMENTE LEITURA - nao grava nada no banco nem no Harmonit."""
import asyncio, sys, sqlite3, io, glob, unicodedata, json
sys.path.insert(0, "/home/claude/fpsl_weso")
from fpsl_weso.harmonit_client import harmonit_get, start_harmonit_client

BANCO = "/home/claude/fpsl_weso/data/fpsl.db"
SAIDA = "/home/claude/fpsl_weso/termos_contratual.json"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(s.strip().upper().split())


async def puxar(rota):
    todos, skip = [], 0
    while True:
        r = await harmonit_get(rota, params={"skip": skip, "take": 100})
        it = (r.get("data") if isinstance(r, dict) else r) or []
        todos.extend(it)
        if len(it) < 100 or skip > 5000:
            break
        skip += 100
    return todos


async def main():
    await start_harmonit_client()
    catalogo = {}
    for rota, tp in (("/Produto/ObterProdutos", "produto"), ("/Produto/ObterServicos", "servico")):
        for i in await puxar(rota):
            catalogo[i["id"]] = {
                "id": i["id"], "tipo": tp, "descricao": (i.get("descricao") or "").strip(),
                "grupo": (i.get("grupo") or "").strip(), "situacao": i.get("situacaoStr") or "",
            }

    con = sqlite3.connect(BANCO)
    vincs = [dict(zip(("nome_contrato", "harmonit_id", "harmonit_tipo", "harmonit_descricao",
                       "oculto", "nas_duas", "criado_em"), r))
             for r in con.execute(
                 "SELECT nome_contrato, harmonit_id, harmonit_tipo, harmonit_descricao, "
                 "oculto, nas_duas, criado_em FROM painel_vinculos_itens ORDER BY nome_contrato")]
    con.close()

    # textos vistos nos PDFs de termo
    from fpsl_weso.painel.pdf_extractor import extrair_campos
    vistos = {}
    for p in sorted(glob.glob("/home/claude/fpsl_weso/tests/fixtures/*.pdf")):
        try:
            with open(p, "rb") as fh:
                campos = extrair_campos(io.BytesIO(fh.read()), "")
            for it in campos.get("itens", []):
                d = norm(it.get("descricao"))
                if d:
                    vistos.setdefault(d, set()).add(p.split("/")[-1])
        except Exception:
            pass
    vistos = {k: sorted(v) for k, v in vistos.items()}

    # grupos por item do Harmonit (TODOS, inclusive os de 1 termo so)
    por_id = {}
    for v in vincs:
        if v["harmonit_id"]:
            por_id.setdefault(v["harmonit_id"], []).append(v)

    vocabulario = []
    for hid, g in por_id.items():
        cat = catalogo.get(hid, {})
        vocabulario.append({
            "h_id": hid,
            "h_tipo": cat.get("tipo", g[0]["harmonit_tipo"] or ""),
            "h_descricao": cat.get("descricao", g[0]["harmonit_descricao"] or ""),
            "h_grupo": cat.get("grupo", ""),
            "h_situacao": cat.get("situacao", ""),
            "termos": sorted([v["nome_contrato"] for v in g]),
            "nas_duas": any(v["nas_duas"] for v in g),
            "usado_em": sorted({a for t in g for a in vistos.get(t["nome_contrato"], [])}),
        })
    vocabulario.sort(key=lambda x: x["h_descricao"])

    ocultos = [{"termo": v["nome_contrato"], "criado_em": (v["criado_em"] or "")[:10],
                "usado_em": vistos.get(v["nome_contrato"], [])}
               for v in vincs if not v["harmonit_id"]]

    cadastrados = {v["nome_contrato"] for v in vincs}
    pendentes = [{"termo": k, "usado_em": v} for k, v in sorted(vistos.items())
                 if k not in cadastrados]

    # catalogo inteiro, para a aba de decisoes achar equivalentes
    with open(SAIDA, "w", encoding="utf-8") as fh:
        json.dump({
            "medido_em": "2026-09-21",
            "vocabulario": vocabulario,
            "ocultos": ocultos,
            "pendentes": pendentes,
            "catalogo": list(catalogo.values()),
            "totais": {"vinculos": len(vincs), "itens_harmonit_usados": len(por_id),
                       "catalogo": len(catalogo), "pdfs": len(glob.glob(
                           "/home/claude/fpsl_weso/tests/fixtures/*.pdf"))},
        }, fh, ensure_ascii=False, indent=1)
    print("vocabulario:", len(vocabulario), "| ocultos:", len(ocultos),
          "| pendentes:", len(pendentes), "| catalogo:", len(catalogo))

asyncio.run(main())
