"""Aba Operações — etapas 1 e 2 (F2): documento e cliente. 2026-08-19.

  1. **A leitura do termo é local e não cruza cliente.** Na tela velha o mesmo
     endpoint lia o PDF e batia nos dois sistemas -- e é a consulta que oscila
     (6s a timeout de 30s). Quando ela demorava, a leitura do PDF, que é
     instantânea, demorava junto. Aqui são duas rotas.

  2. **11 de 11.** O termo 8800 tem 11 veículos e o extrator já leu 9,
     inventando `RFD 2447` para uma linha de texto solto. O que não é
     reconhecido vai para `sem_placa` e APARECE -- nunca vira identificador.

  3. **Perfil sem termo recusa PDF.** Oferecer o campo seria oferecer um
     caminho que não existe.

  4. **O cliente cruza por DOCUMENTO, nunca por nome**, e a resposta traz os
     dois nomes: o mesmo CNPJ é `Velasco Leite Pastelaria ME` no Harmonit e
     `PASTELARIA VELASCO LTDA` na WESO.

  5. **Falha fechado nas três situações**: sem Harmonit não cria nada; falta na
     WESO oferece criar; nos dois, só exibe.

  6. **O contrato com a tela**: o `operacoes.html` lê campos das respostas;
     este teste LÊ O HTML e exige que as rotas entreguem cada um.

Roda na VPS: venv/bin/python tests/teste_operacoes_f2.py
🚨 NÃO ESCREVE EM SISTEMA EXTERNO. A rota que cria cliente na WESO é exercitada
com dublês, in-process -- nunca pela rede. Em 17/08 a própria suíte criou 6
veículos permanentes no Harmonit; não se repete.
"""
import asyncio
import io
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi import HTTPException, UploadFile  # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg  # noqa: E402
from fpsl_weso.painel.routers import operacoes_router as opr  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TELA = RAIZ / "frontend" / "operacoes.html"
FIXTURES = RAIZ / "tests" / "fixtures"

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


def subir(caminho: pathlib.Path) -> UploadFile:
    return UploadFile(filename=caminho.name, file=io.BytesIO(caminho.read_bytes()))


# ── 1. leitura dos termos fixture ────────────────────────────────────────────
print("\n[1] leitura do termo")
pdfs = sorted(FIXTURES.glob("*.pdf"))
checar("há termos fixture para ler", bool(pdfs), f"em {FIXTURES}")

leituras = {}
for pdf in pdfs:
    # os fixtures são de contrato; `contrato_novo` lê todos
    try:
        d = asyncio.run(opr.extrair(perfil="contrato_novo", arquivo=subir(pdf), _=None))
    except HTTPException as exc:
        checar(f"{pdf.name}: leu", False, f"{exc.status_code}: {exc.detail}")
        continue
    leituras[pdf.name] = d
    r = d["resumo"]
    print(f"       {pdf.name}: termo {d['termo']} · {r['veiculos']} veículo(s)"
          f" · {r['nao_lidos']} não lido(s) · doc {d['documento']}")
    checar(f"{pdf.name}: devolveu itens", r["veiculos"] > 0)
    checar(f"{pdf.name}: trouxe o termo", bool(d["termo"]))
    # 🚨 NADA INVENTADO: toda linha tem placa vinda do documento, e o que não
    # foi reconhecido está em `sem_placa`, não numa placa fabricada.
    checar(f"{pdf.name}: nenhuma placa vazia",
           all(i["placa"] for i in d["itens"]))

# ── 2. o termo 8800, que já perdeu 2 de 11 ───────────────────────────────────
print("\n[2] o termo 8800 — 11 de 11")
oito_mil = next((d for n, d in leituras.items() if "8800" in n), None)
if oito_mil:
    total = oito_mil["resumo"]["veiculos"] + oito_mil["resumo"]["nao_lidos"]
    checar("11 linhas de veículo, lidas ou reportadas", total == 11,
           f"{oito_mil['resumo']['veiculos']} lidas + "
           f"{oito_mil['resumo']['nao_lidos']} reportadas = {total}")
    # a placa que o extrator inventou em 07/08 não pode reaparecer
    placas = {i["placa_gravada"] for i in oito_mil["itens"]}
    checar("a placa inventada `RFD 2447` não está lá", "RFD 2447" not in placas)
else:
    print("       (fixture do 8800 não encontrada — pulando)")

# ── 3. perfil sem termo recusa PDF ───────────────────────────────────────────
print("\n[3] perfil sem termo recusa documento")
for nome in cfg.sem_termo():
    try:
        asyncio.run(opr.extrair(perfil=nome, arquivo=subir(pdfs[0]), _=None))
        checar(f"{nome} recusa PDF", False, "aceitou")
    except HTTPException as exc:
        checar(f"{nome} recusa PDF", exc.status_code == 400)
try:
    asyncio.run(opr.extrair(perfil="nao_existe", arquivo=subir(pdfs[0]), _=None))
    checar("perfil inexistente é recusado", False, "aceitou")
except HTTPException as exc:
    checar("perfil inexistente é recusado", exc.status_code == 400)

# ── 4 e 5. o cliente, com dublês ─────────────────────────────────────────────
print("\n[4] as três situações do cliente")
VELASCO_H = {"id": 998063, "nome": "Velasco Leite Pastelaria ME"}
VELASCO_W = {"id": 13562, "razaoSocial": "PASTELARIA VELASCO LTDA",
             "situacao": "Adimplente"}


def com_dubles(harmonit, weso, escrita=None):
    """Substitui os três pontos de rede. `escrita` guarda o que foi enviado."""
    async def _h(doc):
        return harmonit

    estado = {"criado": False}

    async def _w(doc):
        # depois de criar, a releitura passa a achar
        return weso if weso or not estado["criado"] else None

    async def _w_apos(doc):
        return weso if weso else (VELASCO_W if estado["criado"] else None)

    async def _post(path, corpo, allow_409=False):
        if escrita is not None:
            escrita.append((path, corpo))
        estado["criado"] = True
        return {}

    return {"_no_harmonit": _h, "_na_weso": _w_apos, "weso_post": _post}


def rodar(fn, dubles, **kw):
    originais = {n: getattr(opr, n) for n in dubles}
    for n, f in dubles.items():
        setattr(opr, n, f)
    try:
        return asyncio.run(fn(**kw, _=None))
    finally:
        for n, f in originais.items():
            setattr(opr, n, f)


d = rodar(opr.conferir_cliente, com_dubles(VELASCO_H, VELASCO_W),
          documento="WQ0P6GLD000108")
checar("nos dois: situação ok", d["situacao"] == "ok", d["situacao"])
checar("traz o nome do Harmonit", d["harmonit"]["nome"] == VELASCO_H["nome"])
# 🚨 OS DOIS NOMES. Mostrar um só faz parecer que achou o cliente errado.
checar("e o nome da WESO, que é diferente",
       d["weso"]["nome"] == VELASCO_W["razaoSocial"]
       and d["weso"]["nome"] != d["harmonit"]["nome"])

d = rodar(opr.conferir_cliente, com_dubles(VELASCO_H, None),
          documento="WQ0P6GLD000108")
checar("só no Harmonit: falta_na_weso", d["situacao"] == "falta_na_weso", d["situacao"])
checar("e o recado fala em criar", "criad" in d["recado"].lower())

d = rodar(opr.conferir_cliente, com_dubles(None, None), documento="00000000000000")
checar("em nenhum: sem_harmonit", d["situacao"] == "sem_harmonit", d["situacao"])
checar("e o recado diz que o painel não cria no Harmonit",
       "não cria cliente no harmonit" in d["recado"].lower())

print("\n[5] criar na WESO — falha fechado")
enviado = []
d = rodar(opr.criar_cliente_na_weso, com_dubles(VELASCO_H, None, enviado),
          body=opr.CriarClienteInput(documento="WQ0P6GLD000108"))
checar("criou e conferiu relendo",
       d["acao"] == "criado" and d.get("verificado_relendo"), str(d))
# 🚨 OS DADOS VÊM DO HARMONIT, nunca digitados
checar("mandou o nome do Harmonit, não outro",
       enviado and enviado[0][1]["razaoSocial"] == VELASCO_H["nome"], str(enviado))
checar("e o documento sem pontuação",
       enviado and enviado[0][1]["cnpjcpf"] == "WQ0P6GLD000108")

try:
    rodar(opr.criar_cliente_na_weso, com_dubles(None, None),
          body=opr.CriarClienteInput(documento="00000000000000"))
    checar("sem Harmonit não cria na WESO", False, "criou")
except HTTPException as exc:
    checar("sem Harmonit não cria na WESO", exc.status_code == 422)

d = rodar(opr.criar_cliente_na_weso, com_dubles(VELASCO_H, VELASCO_W),
          body=opr.CriarClienteInput(documento="WQ0P6GLD000108"))
checar("já existindo, informa e não recria", d["acao"] == "ja_existia", str(d))

# 🚨 A PROVA É RELER. Dublê que "grava" mas a releitura não acha -> 502.
async def _acha_harmonit(doc):
    return VELASCO_H


async def _nunca_acha(doc):
    return None


async def _post_mudo(path, corpo, allow_409=False):
    return {}


try:
    rodar(opr.criar_cliente_na_weso,
          {"_no_harmonit": _acha_harmonit, "_na_weso": _nunca_acha,
           "weso_post": _post_mudo},
          body=opr.CriarClienteInput(documento="WQ0P6GLD000108"))
    checar("gravou sem aparecer na releitura vira erro", False, "passou")
except HTTPException as exc:
    checar("gravou sem aparecer na releitura vira erro", exc.status_code == 502,
           f"HTTP {exc.status_code}")

# ── 6. contrato com a tela ───────────────────────────────────────────────────
print("\n[6] contrato com o operacoes.html")
html = TELA.read_text(encoding="utf-8")
for campo in ("resumo", "itens", "sem_placa", "termo", "documento",
              "nome_no_termo", "recipiente_sufixo"):
    checar(f"a tela lê `{campo}` e a extração entrega",
           (f"d.{campo}" in html or f"extraido.{campo}" in html)
           <= (campo in (leituras and list(leituras.values())[0] or {})))
for campo in ("situacao", "recado", "harmonit", "weso"):
    checar(f"a tela lê `{campo}` e o cliente entrega", f"d.{campo}" in html)
checar("a tela só chama rotas da própria aba",
       all(r.startswith("/painel/api/operacoes/")
           for r in re.findall(r"/painel/api/[a-z0-9/{}_-]+", html)))

print()
print("=" * 56)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
