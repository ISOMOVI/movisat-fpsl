#!/usr/bin/env python3
"""Exporta as 3 categorias de termos de vinculo para JSON. SOMENTE LEITURA."""
import asyncio, sys, sqlite3, io, glob, unicodedata, json
sys.path.insert(0, "/home/claude/fpsl_weso")
from fpsl_weso.harmonit_client import harmonit_get, start_harmonit_client

BANCO = "/home/claude/fpsl_weso/data/fpsl.db"
SAIDA = "/home/claude/fpsl_weso/termos_vinculo.json"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(s.strip().upper().split())


def tokens(s):
    return {t for t in norm(s).replace("/", " ").replace("-", " ").split() if len(t) >= 4}


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
                "codigo": i.get("codigo") or "",
            }

    con = sqlite3.connect(BANCO)
    vincs = [dict(zip(
        ("nome_contrato", "harmonit_id", "harmonit_tipo", "harmonit_descricao",
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
                vistos.setdefault(norm(it.get("descricao")), set()).add(p.split("/")[-1])
        except Exception:
            pass
    vistos = {k: sorted(v) for k, v in vistos.items() if k}

    cadastrados = {v["nome_contrato"] for v in vincs}
    por_id = {}
    for v in vincs:
        if v["harmonit_id"]:
            por_id.setdefault(v["harmonit_id"], []).append(v)

    linhas = []

    # ── C1: duplicidade com vinculo ────────────────────────────────────────
    for hid, grupo in sorted(por_id.items(), key=lambda x: (-len(x[1]), x[0])):
        if len(grupo) < 2:
            continue
        cat = catalogo.get(hid, {})
        for v in sorted(grupo, key=lambda g: g["nome_contrato"]):
            linhas.append({
                "categoria": "1 - Duplicado (varios termos, mesmo item)",
                "termo": v["nome_contrato"],
                "situacao_termo": "Vinculado",
                "onde_apareceu": ", ".join(vistos.get(v["nome_contrato"], [])),
                "h_id": hid, "h_tipo": cat.get("tipo", v["harmonit_tipo"]),
                "h_codigo": cat.get("codigo", ""),
                "h_descricao": cat.get("descricao", v["harmonit_descricao"] or ""),
                "h_grupo": cat.get("grupo", ""), "h_situacao": cat.get("situacao", ""),
                "n_termos": len(grupo),
                "criado_em": (v["criado_em"] or "")[:10],
                "nas_duas": "sim" if v["nas_duas"] else "",
            })

    # ── C2: no catalogo, sem vinculo ───────────────────────────────────────
    usados = set(por_id.keys())
    for cid, cat in sorted(catalogo.items(), key=lambda x: (x[1]["grupo"], x[1]["descricao"])):
        if cid in usados:
            continue
        toks_cat = tokens(cat["descricao"])
        apareceu = []
        for texto, arquivos in vistos.items():
            if texto in cadastrados:
                continue
            tk = tokens(texto)
            if not tk:
                continue
            if texto in norm(cat["descricao"]) or norm(cat["descricao"]) in texto or tk <= toks_cat:
                apareceu.append(f"{texto} ({', '.join(arquivos)})")
        linhas.append({
            "categoria": "2 - No Harmonit, sem vinculo",
            "termo": "", "situacao_termo": "Sem vinculo",
            "onde_apareceu": " | ".join(apareceu),
            "h_id": cid, "h_tipo": cat["tipo"], "h_codigo": cat["codigo"],
            "h_descricao": cat["descricao"], "h_grupo": cat["grupo"],
            "h_situacao": cat["situacao"], "n_termos": 0, "criado_em": "", "nas_duas": "",
        })

    # ── C3: apareceu e nao tem item no Harmonit ────────────────────────────
    for v in vincs:
        if v["harmonit_id"]:
            continue
        nc = v["nome_contrato"]
        tk = tokens(nc)
        cands = []
        for cid, cat in catalogo.items():
            d = norm(cat["descricao"])
            if not d:
                continue
            if d == nc or d in nc or nc in d or (tk and tk <= tokens(cat["descricao"])):
                cands.append(f"{cid} [{cat['tipo']}/{cat['situacao']}] {cat['descricao']}")
        linhas.append({
            "categoria": "3 - Apareceu, sem item no Harmonit",
            "termo": nc,
            "situacao_termo": "Oculto" if v["oculto"] else "Sem destino",
            "onde_apareceu": ", ".join(vistos.get(nc, [])) or "cadastro manual",
            "h_id": "", "h_tipo": "", "h_codigo": "", "h_descricao": "",
            "h_grupo": "", "h_situacao": "",
            "n_termos": 0, "criado_em": (v["criado_em"] or "")[:10], "nas_duas": "",
            "candidatos": " | ".join(sorted(cands)[:3]),
        })

    for texto, arquivos in sorted(vistos.items()):
        if texto in cadastrados:
            continue
        tk = tokens(texto)
        cands = []
        for cid, cat in catalogo.items():
            d = norm(cat["descricao"])
            if not d:
                continue
            if d == texto or d in texto or texto in d or (tk and tk <= tokens(cat["descricao"])):
                cands.append(f"{cid} [{cat['tipo']}/{cat['situacao']}] {cat['descricao']}")
        linhas.append({
            "categoria": "3 - Apareceu, sem item no Harmonit",
            "termo": texto, "situacao_termo": "Pendente (nao cadastrado)",
            "onde_apareceu": ", ".join(arquivos),
            "h_id": "", "h_tipo": "", "h_codigo": "", "h_descricao": "",
            "h_grupo": "", "h_situacao": "",
            "n_termos": 0, "criado_em": "", "nas_duas": "",
            "candidatos": " | ".join(sorted(cands)[:3]),
        })

    resumo = {
        "medido_em": "2026-09-21",
        "vinculos_total": len(vincs),
        "vinculos_com_id": sum(1 for v in vincs if v["harmonit_id"]),
        "vinculos_ocultos": sum(1 for v in vincs if v["oculto"]),
        "catalogo_total": len(catalogo),
        "catalogo_ativos": sum(1 for c in catalogo.values() if c["situacao"] == "Ativo"),
        "pdfs_lidos": len(glob.glob("/home/claude/fpsl_weso/tests/fixtures/*.pdf")),
        "descricoes_nos_pdfs": len(vistos),
    }
    with open(SAIDA, "w", encoding="utf-8") as fh:
        json.dump({"resumo": resumo, "linhas": linhas}, fh, ensure_ascii=False, indent=1)
    print(json.dumps(resumo, ensure_ascii=False))
    print("linhas:", len(linhas))

asyncio.run(main())
