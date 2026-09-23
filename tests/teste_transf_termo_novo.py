"""O termo novo de transferência -- perfil 12, 2026-09-23.

"TERMO DE TRANSF. DE TIT.: RESCISÃO", medido nos termos 8873 e 8880 (as duas
fixtures `transf_novo_*.pdf`). Spec: `docs/fpsl/28_Operacoes.md`, seção do
perfil 12.

O que este teste prende:

  1. **O leitor lê as três tabelas** -- titulares, placas, itens -- e o CNPJ
     do cliente é o do ANTIGO titular, pela tabela. O 8880 não tem a linha
     "CNPJ:" do cabeçalho, e é ele que prova que não se depende dela.
  2. **O problema existia**: pelo extrator compartilhado (perfil 6) o termo dá
     ZERO placas. Se um dia der, este teste avisa que o motivo do perfil mudou.
  3. **O reconhecimento não pega termo velho**: nenhuma das fixtures antigas é
     tomada pelo modelo novo -- senão o `/extrair` recusaria termo legítimo.
  4. **A montagem é por placa e por papel**: com novo contrato TRANSFERE (7474,
     nada flegado, sem financeira); sem, RESCINDE (a regra da `rescisao`, com
     rotina) e só gera financeira se houver cobrança.
  5. **A rota e a tela de Vínculos**, chamadas de verdade com o PDF.

Roda na VPS: venv/bin/python tests/teste_transf_termo_novo.py
Não faz rede: o vínculo e o de-para são lidos do banco local, só leitura.
"""
import asyncio
import io
import pathlib
import sys

RAIZ = pathlib.Path("/home/claude/fpsl_weso")
sys.path.insert(0, str(RAIZ))

from fastapi import HTTPException, UploadFile                      # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg               # noqa: E402
from fpsl_weso.painel import operacoes_extracao as extracao        # noqa: E402
from fpsl_weso.painel import operacoes_os as oos                   # noqa: E402
from fpsl_weso.painel.pdf_extractor import extrair_campos          # noqa: E402
from fpsl_weso.painel.routers import operacoes_router as R         # noqa: E402
from fpsl_weso.painel.routers import os_router as V                # noqa: E402

FIX = RAIZ / "tests" / "fixtures"
PERFIL = "transferencia_termo_novo"

ok, achados = 0, []


def checar(nome, cond, detalhe=""):
    global ok
    if cond:
        ok += 1
        print(f"  OK   {nome}")
    else:
        achados.append(nome)
        print(f"  FALHA {nome}" + (f"  -- {detalhe}" if detalhe else ""))


def pdf(nome):
    return io.BytesIO((FIX / nome).read_bytes())


def upload(nome):
    return UploadFile(file=pdf(nome), filename=nome)


# ── 1. o leitor ──────────────────────────────────────────────────────────────
print("== 1. o leitor lê as três tabelas ==")
a = extracao.ler_termo_transf_novo(pdf("transf_novo_8873.pdf"))
checar("8873: termo", a["termo"] == "8873", a["termo"])
checar("8873: CNPJ do cliente é o do ANTIGO titular",
       a["cnpj"] == "12.411.822/0001-44", a["cnpj"])
checar("8873: nome do antigo vem inteiro, sem quebra de linha",
       a["cliente_nome_sugerido"] ==
       "CAVAN ROCBRA E COMERCIO DE PRE MOLDADOS DE CONCRETO",
       a["cliente_nome_sugerido"])
checar("8873: novo titular",
       a["novo_titular"] == {"nome": "CAVAN PRE-MOLDADO S/A",
                             "cnpj": "33.039.181/0010-00"}, a["novo_titular"])
checar("8873: as 2 placas, com o novo contrato",
       [(p["placa"], p["novo_contrato"]) for p in a["placas"]]
       == [("DOR 8307", "8870"), ("ROI 9F62", "8870")], a["placas"])
checar("8873: o contrato atual é lido (e não vai para a OS)",
       [p["contrato_atual"] for p in a["placas"]] == ["2312", "2465"])
checar("8873: o modelo do veículo vem numa linha",
       a["placas"][1]["veiculo"] == "FIAT/MOBI LIKE, 2022/2022, PRATA, FLEX",
       a["placas"][1]["veiculo"])
checar("8873: 3 itens, UM POR VEÍCULO (quantidade 2)",
       [(i["descricao"], i["quantidade"], i["comodato_ou_aquisicao"])
        for i in a["itens"]] ==
       [("Plano Smart", "2", "Contratado"), ("Rastreador 2G", "2", "Comodato"),
        ("Chip de Dados", "2", "Comodato")], a["itens"])
checar("8873: termo relacionado é o novo contrato",
       a["termo_relacionado"] == "8870")
checar("8873: nenhum aviso", a["avisos_extracao"] == [], a["avisos_extracao"])

b = extracao.ler_termo_transf_novo(pdf("transf_novo_8880.pdf"))
# 🚨 O 8880 NÃO TEM A LINHA "CNPJ:" DO CABEÇALHO, e antigo e novo têm o MESMO
# nome. É ele que prova que o CNPJ vem da coluna certa da tabela.
checar("8880: CNPJ do antigo (0010-00), não o do novo (0030-53)",
       b["cnpj"] == "33.039.181/0010-00", b["cnpj"])
checar("8880: novo titular é a outra filial",
       (b["novo_titular"] or {}).get("cnpj") == "33.039.181/0030-53")
checar("8880: 1 placa para o 8864",
       [(p["placa"], p["novo_contrato"]) for p in b["placas"]]
       == [("DOT 0C95", "8864")], b["placas"])
checar("8880: itens com quantidade 1",
       all(i["quantidade"] == "1" for i in b["itens"]) and len(b["itens"]) == 3)

# ── 2. o problema que o perfil resolve ───────────────────────────────────────
print("\n== 2. pelo extrator compartilhado o termo dá ZERO placas ==")
velho = extrair_campos(pdf("transf_novo_8873.pdf"), "transferencia_antigo_titular")
checar("perfil 6 no 8873 lê 0 placas (é por isso que o 12 existe)",
       not (velho.get("placas") or []), velho.get("placas"))

# ── 3. o reconhecimento ──────────────────────────────────────────────────────
print("\n== 3. o reconhecimento não pega termo velho ==")
checar("reconhece o 8873 e o 8880",
       extracao.eh_termo_transf_novo(pdf("transf_novo_8873.pdf"))
       and extracao.eh_termo_transf_novo(pdf("transf_novo_8880.pdf")))
falsos = [f.name for f in sorted(FIX.glob("*.pdf"))
          if not f.name.startswith("transf_novo_")
          and extracao.eh_termo_transf_novo(pdf(f.name))]
checar(f"nenhuma das {len(list(FIX.glob('*.pdf'))) - 2} fixtures antigas é "
       "tomada pelo modelo novo", not falsos, str(falsos))

# ── 3b. tabela desconhecida não some ─────────────────────────────────────────
_orig = extracao._ler_paginas


def _com_tabela_a_mais(fonte):
    pags = _orig(fonte)
    pags[0]["tabelas"].append([["ENCARGOS DA RESCISAO", "VALOR"],
                               ["Aviso previo", "R$ 100,00"]])
    return pags


extracao._ler_paginas = _com_tabela_a_mais
try:
    c = extracao.ler_termo_transf_novo(pdf("transf_novo_8873.pdf"))
finally:
    extracao._ler_paginas = _orig
checar("tabela que o leitor não conhece vira aviso (a cobrança pode estar nela)",
       any("não sei ler" in x for x in c["avisos_extracao"]),
       c["avisos_extracao"])

# ── 4. a montagem ────────────────────────────────────────────────────────────
print("\n== 4. uma OS por placa, cada uma com o seu papel ==")
p12 = cfg.PERFIS[PERFIL]
checar("o perfil tem o nome que ele deu",
       p12["label"] == "NOVO - Termo de transf. de tit.: Rescisão")
checar("o perfil 6 continua existindo", "transferencia_antigo_titular" in cfg.PERFIS)

RESOLVIDOS = [
    {"descricao": "Rastreador 2G", "harmonit_id": 20314, "quantidade": 2,
     "valor_unitario": 0.0, "comodato": True, "cobrar": False},
    {"descricao": "Chip de Dados", "harmonit_id": 16016, "quantidade": 2,
     "valor_unitario": 0.0, "comodato": True, "cobrar": False},
]


def corpo(placas):
    return oos.MontarInput(perfil=PERFIL, cliente_id=262495, termo="8873",
                           produto_servico_id=6966, placas=placas)


def montar(body, resolvidos):
    return oos.montar(body, p12, [[] for _ in body.placas], [], resolvidos,
                      {}, {}, {})


so_transf = corpo([oos.PlacaOS(placa="DOR 8307", veiculo="VW KOMBI", novo_contrato="8870"),
                   oos.PlacaOS(placa="ROI 9F62", veiculo="FIAT MOBI", novo_contrato="8870")])
ops = montar(so_transf, RESOLVIDOS)
checar("só transferência: 2 placas = 2 OS, e NENHUMA financeira",
       len(ops) == 2 and not any(o.get("eh_financeira") for o in ops),
       [o.get("rotulo") for o in ops])
checar("as duas com o problema 7474 e o tipo Contrato",
       all(o["problema_id"] == 7474 and o["tipo_id"] == cfg.TIPO_CONTRATO_ID
           for o in ops))
checar("uma OS por placa, cada uma com a sua",
       [o["placa"] for o in ops] == ["DOR 8307", "ROI 9F62"])
mats = [m for o in ops for m in o["materiais"]]
checar("nenhum material flegado (regra de 29/07 do antigo titular)",
       not any(m.get("comodato") or m.get("cobrar") for m in mats),
       [(m["descricao"], m.get("comodato"), m.get("cobrar")) for m in mats
        if m.get("comodato") or m.get("cobrar")])
checar("cada placa leva o chip UMA vez (não os 2 do termo numa só)",
       all(sum(1 for m in o["materiais"] if m["descricao"] == "Chip de Dados") == 1
           for o in ops))
checar("a descrição leva o novo contrato",
       all("NOVO CONTRATO 8870" in o["descricao"] and "TERMO 8873" in o["descricao"]
           for o in ops), ops[0]["descricao"])
checar("o contrato atual NÃO vai para a OS",
       not any("2312" in o["descricao"] or "2465" in o["descricao"] for o in ops))
checar("a transferência não entra na rotina", not any(o.get("caso_rotina") for o in ops))

hibrido = corpo([oos.PlacaOS(placa="DOR 8307", veiculo="VW KOMBI", novo_contrato="8870"),
                 oos.PlacaOS(placa="ROI 9F62", veiculo="FIAT MOBI", novo_contrato=None)])
ops = montar(hibrido, RESOLVIDOS)
resc = cfg.PERFIS["rescisao"]
r = ops[1]
checar("híbrido: a placa SEM novo contrato vira rescisão (tipo e problema dela)",
       r["tipo_id"] == resc["tipo_id"] and r["problema_id"] == resc["problema_id"],
       (r["tipo_id"], r["problema_id"]))
checar("híbrido: a rescisão usa o texto da rescisão",
       r["descricao"].startswith("Retirada: ROI 9F62"), r["descricao"])
checar("híbrido: a rescisão flega o comodato, como o perfil rescisao",
       any(m.get("comodato") for m in r["materiais"]))
checar("híbrido: só a rescisão entra na rotina de devolução",
       r.get("caso_rotina") == "rescisao" and not ops[0].get("caso_rotina"))
checar("híbrido sem cobrança: sem financeira",
       len(ops) == 2 and not any(o.get("eh_financeira") for o in ops))

com_cobranca = RESOLVIDOS + [{"descricao": "AVISO PREVIO", "harmonit_id": 1,
                              "quantidade": 2, "valor_unitario": 100.0,
                              "comodato": False, "cobrar": True}]
ops = montar(hibrido, com_cobranca)
fin = [o for o in ops if o.get("eh_financeira")]
checar("híbrido COM cobrança: uma financeira", len(fin) == 1, len(fin))
checar("a financeira é só da placa que rescinde",
       fin and "ROI 9F62" in fin[0]["descricao"]
       and "DOR 8307" not in fin[0]["descricao"], fin and fin[0]["descricao"])
checar("a cobrança não vai para a OS de transferência",
       not any(m["descricao"] == "AVISO PREVIO" for m in ops[0]["materiais"]))
checar("só transferência COM cobrança no termo: continua sem financeira",
       not any(o.get("eh_financeira") for o in montar(so_transf, com_cobranca)))
checar("sem pedido de motivo de cobrança zero (seria aviso falso)",
       oos.aviso_cobranca_sem_motivo(so_transf, p12, RESOLVIDOS) == [])


# ── 5. as rotas, chamadas de verdade ─────────────────────────────────────────
print("\n== 5. a rota, a lista de perfis e a tela de Vínculos ==")


async def rotas():
    d = await R.extrair(None, perfil=PERFIL, arquivo=upload("transf_novo_8873.pdf"))
    checar("/extrair: documento é o CNPJ do antigo, sem pontuação",
           d["documento"] == "12411822000144", d["documento"])
    checar("/extrair: as placas levam o novo contrato até a tela",
           [i.get("novo_contrato") for i in d["itens"]] == ["8870", "8870"],
           d["itens"])
    checar("/extrair: devolve o novo titular e o termo relacionado",
           (d["novo_titular"] or {}).get("cnpj") == "33.039.181/0010-00"
           and d["termo_relacionado"] == "8870")
    checar("/extrair: os 3 itens do contrato", len(d["itens_contrato"]) == 3)

    try:
        await R.extrair(None, perfil="transferencia_antigo_titular",
                        arquivo=upload("transf_novo_8873.pdf"))
        checar("perfil 6 com o termo novo é recusado", False, "não recusou")
    except HTTPException as e:
        checar("perfil 6 com o termo novo é recusado, e diz qual escolher",
               e.status_code == 400 and p12["label"] in e.detail, e.detail)
    try:
        await R.extrair(None, perfil=PERFIL, arquivo=upload("rescisao_8842.pdf"))
        checar("termo velho no perfil 12 é recusado", False, "não recusou")
    except HTTPException as e:
        checar("termo velho no perfil 12 é recusado", e.status_code == 400)

    velho = await R.extrair(None, perfil="transferencia_antigo_titular",
                            arquivo=upload("transferencia_existente.pdf"))
    checar("o perfil 6 continua lendo o termo velho",
           velho["resumo"]["veiculos"] >= 1 and "novo_contrato" not in velho["itens"][0])

    ids = [p["id"] for p in (await R.listar_perfis(None))["perfis"]]
    checar("/perfis oferece os 12", len(ids) == 12 and PERFIL in ids, ids)
    cfg.PERFIS["transferencia_antigo_titular"]["ativo"] = False
    try:
        ids = [p["id"] for p in (await R.listar_perfis(None))["perfis"]]
    finally:
        del cfg.PERFIS["transferencia_antigo_titular"]["ativo"]
    checar("`ativo: False` tira da escolha e só isso",
           "transferencia_antigo_titular" not in ids and len(ids) == 11
           and "transferencia_antigo_titular" in cfg.PERFIS)

    # A tela de Vínculos escolhe perfil numa lista das telas VELHAS; o termo
    # novo é reconhecido pelo documento, qualquer que seja o escolhido.
    v = await V.extrair_preview(perfil="rescisao",
                                arquivo=upload("transf_novo_8880.pdf"))
    checar("Vínculos lê os 3 itens do termo novo, com o vínculo de cada um",
           [i["descricao"] for i in v["itens"]]
           == ["Plano Smart", "Rastreador 2G", "Chip de Dados"]
           and all("vinculo" in i for i in v["itens"]), v["itens"])

    # 🚨 A PENDÊNCIA DA ROTINA vem da OS, não do perfil. `esp.registrar` é
    # trocado por um dublê: o de verdade grava no banco.
    registrados = []

    async def _duble(**kw):
        registrados.append(kw)
        return len(registrados)

    original = R.esp.registrar
    R.esp.registrar = _duble
    try:
        ops = montar(hibrido, RESOLVIDOS)
        pre = {"perfil": p12, "ctx": {"recipientes": {}}}
        await R._gravar_pendencias(hibrido, pre, ops,
                                   [{"ok": True, "os_id": 1, "numero_ordem": 1},
                                    {"ok": True, "os_id": 2, "numero_ordem": 2}])
    finally:
        R.esp.registrar = original
    checar("rotina: só a placa que rescinde vira pendência de devolução",
           [(x["placa"], x["caso"]) for x in registrados] == [("ROI 9F62", "rescisao")],
           registrados)


asyncio.run(rotas())

# ── 6. a TELA, dirigida com a resposta real ──────────────────────────────────
# 🚨 PLACAR VERDE NÃO PROVA QUE A TELA DESENHA (M9). O `exercitar_operacoes.js`
# roda o script da página num DOM de mentira; aqui o `/extrair` dele devolve o
# JSON que o router REAL acabou de produzir para o 8873.
print("\n== 6. a tela, com a resposta real do router ==")
import json        # noqa: E402
import os          # noqa: E402
import subprocess  # noqa: E402
import tempfile    # noqa: E402

real = asyncio.run(R.extrair(None, perfil=PERFIL,
                             arquivo=upload("transf_novo_8873.pdf")))
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                 encoding="utf-8") as f:
    json.dump(real, f, ensure_ascii=False)
try:
    saida = subprocess.run(
        ["node", str(RAIZ / "tests" / "exercitar_operacoes.js"),
         str(RAIZ / "frontend" / "operacoes.html")],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "EXTRAIR_REAL": f.name})
finally:
    os.unlink(f.name)
t = json.loads(saida.stdout or "{}")
checar("o exercício rodou sem erro", not t.get("erros") and saida.returncode == 0,
       (t.get("erros") or [saida.stderr[-300:]])[0][:300])
resumo = t.get("t12_resumo") or ""
checar("etapa 1 mostra de quem para quem",
       "CAVAN ROCBRA E COMERCIO" in resumo and "CAVAN PRE-MOLDADO S/A" in resumo,
       resumo[:300])
checar("etapa 1 conta as placas: 2 transferem para o 8870, 0 rescindem",
       "<strong>2</strong> placa(s) transferem" in resumo and "8870" in resumo
       and "<strong>0</strong> rescindem" in resumo, resumo[-200:])
checar("etapa 1 sem aviso vermelho (o termo foi lido inteiro)",
       "msg-erro" not in (t.get("t12_nao_lidos") or "")
       and "msg-erro" not in (t.get("t12_msg_etapa1") or ""),
       (t.get("t12_nao_lidos") or "") + (t.get("t12_msg_etapa1") or ""))
checar("chegou à etapa 3", t.get("t12_etapa") == 3, t.get("t12_etapa"))
checar("o novo contrato atravessa a etapa 3",
       t.get("t12_linhas") == [["DOR 8307", "8870"], ["ROI 9F62", "8870"]],
       t.get("t12_linhas"))
checar("e chega ao payload da OS, com o perfil 12",
       t.get("t12_payload") == [["DOR 8307", "8870"], ["ROI 9F62", "8870"]]
       and t.get("t12_perfil") == PERFIL, (t.get("t12_payload"), t.get("t12_perfil")))
checar("os itens vão com quantidade 2 (um por veículo)",
       t.get("t12_itens") == [["Plano Smart", "2"], ["Rastreador 2G", "2"],
                               ["Chip de Dados", "2"]], t.get("t12_itens"))

for a in achados:
    print("  FALHOU:", a)
print(f"\n{ok} OK, {len(achados)} falha(s)")
sys.exit(1 if achados else 0)
