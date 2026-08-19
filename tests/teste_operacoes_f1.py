"""A aba Operações (`OPR_1.1`) — fundação (F1), 2026-08-19.

A aba única que substitui Cadastro de Placas e Gerar OS. Escopo, as 14 regras e
as fases: `docs/fpsl/28_Operacoes.md`.

O que a F1 prende:

  1. **A independência.** Nada da aba nova importa `os_router` nem
     `placas_router`. Os dois vão ser desmontados na F7 -- um import daqui
     seria dependência num arquivo com data de validade, e o defeito só
     apareceria no dia da remoção.

  2. **Os 11 perfis existem e são coerentes.** Perfil sem termo não pode exigir
     termo; perfil com recipiente tem de ter sufixo; `etapa_placas` só aceita
     os três valores conhecidos.

  3. **A tela está registrada e trancada.** Código `OPR_1.1`, permissão
     `operacoes`, fora do menu. Rota sem token dá 401.

  4. **O contrato com a TELA.** O `operacoes.html` lê campos de
     `/painel/api/operacoes/perfis`; este teste LÊ O HTML e exige que a rota
     entregue cada um. É a lição de 18/08: naquele dia 677 verificações
     passaram com o painel derrubado porque nenhuma olhava o consumidor.

  5. **As duas telas velhas continuam intactas.** A aba nova nasce ao lado,
     não por cima.

Roda na VPS: venv/bin/python tests/teste_operacoes_f1.py
Fala HTTP com o serviço local para a tranca. Não escreve em lugar nenhum.
"""
import asyncio
import pathlib
import re
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import operacoes_config as cfg  # noqa: E402
from fpsl_weso.painel import telas  # noqa: E402
from fpsl_weso.painel.routers import operacoes_router  # noqa: E402

BASE = "http://127.0.0.1:8004"
RAIZ = pathlib.Path(__file__).resolve().parent.parent
TELA = RAIZ / "frontend" / "operacoes.html"
CSS = RAIZ / "frontend" / "operacoes.css"
ROUTER = RAIZ / "fpsl_weso" / "painel" / "routers" / "operacoes_router.py"
CONFIG = RAIZ / "fpsl_weso" / "painel" / "operacoes_config.py"

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# ── 1. independência ─────────────────────────────────────────────────────────
print("\n[1] a aba nova não depende do que vai ser apagado")
# 🚨 A VERIFICAÇÃO MAIS IMPORTANTE DA F1. Um import esquecido aqui só quebraria
# na F7, meses depois, quando os dois routers saírem.
CONDENADOS = ("os_router", "placas_router", "templates_config")
for arquivo in (ROUTER, CONFIG):
    fonte = arquivo.read_text(encoding="utf-8")
    # só as linhas de import -- citar o nome em comentário é livre e desejável
    imports = [l for l in fonte.splitlines()
               if re.match(r"\s*(from|import)\s", l)]
    for alvo in CONDENADOS:
        achou = any(alvo in l for l in imports)
        checar(f"{arquivo.name} não importa {alvo}", not achou,
               f"linhas: {[l for l in imports if alvo in l]}")

html = TELA.read_text(encoding="utf-8")
checar("a tela só chama rotas /painel/api/operacoes/",
       all(r.startswith("/painel/api/operacoes/")
           for r in re.findall(r"/painel/api/[a-z0-9/{}_-]+", html)),
       f"achei: {sorted(set(re.findall(r'/painel/api/[a-z0-9/{}_-]+', html)))}")
# ⚠️ MEDE OS <link>, NÃO A PALAVRA. O HTML cita `gerar_os.html` no comentário
# que explica de onde o CSS foi clonado, e essa memória tem de poder ficar lá.
folhas = re.findall(r'<link[^>]+href="([^"]+\.css)"', html)
checar("a tela usa o CSS próprio", "/painel/static/operacoes.css" in folhas,
       f"folhas: {folhas}")
checar("e nenhuma folha das telas que vão sair",
       not any("gerar_os" in f or "cadastro_placas" in f for f in folhas),
       f"folhas: {folhas}")

# ── 2. os 11 perfis ──────────────────────────────────────────────────────────
print("\n[2] os 11 perfis")
checar("são 11", len(cfg.PERFIS) == 11, f"são {len(cfg.PERFIS)}")
checar("8 com termo, 3 sem",
       (len(cfg.com_termo()), len(cfg.sem_termo())) == (8, 3),
       f"{len(cfg.com_termo())} / {len(cfg.sem_termo())}")
checar("2 com recipiente", len(cfg.com_recipiente()) == 2)

for nome, p in cfg.PERFIS.items():
    checar(f"{nome}: tem label e etapa_placas",
           bool(p.get("label")) and p.get("etapa_placas") in cfg.ETAPA_PLACAS,
           f"etapa_placas={p.get('etapa_placas')!r}")

# 🚨 COERÊNCIA, não só presença. Estas são as combinações que não podem existir.
for nome, p in cfg.PERFIS.items():
    if p.get("placa_teste_sufixo"):
        checar(f"{nome}: recipiente é só WESO", bool(p.get("recipiente_so_weso")))
        checar(f"{nome}: recipiente tem descrição para conferir",
               bool(p.get("placa_teste_descricao")))
    if p.get("sem_termo"):
        checar(f"{nome}: sem termo não usa template de termo",
               "{termo}" not in (p.get("descricao_template") or ""))
    if p.get("hibrida"):
        # a híbrida NOVA é cobrança+oficina; não pode ter comodato junto
        checar(f"{nome}: híbrida não flega comodato", not p.get("sem_flags"))

checar("os dois renomes entraram",
       cfg.PERFIS["contrato_novo"]["label"] == "Contrato novo ou teste de tecnologia"
       and cfg.PERFIS["aditivo"]["label"] == "Aditivo ou teste upgrade")
checar("os dois ressarcimentos são agregados e híbridos",
       all(cfg.PERFIS[n].get("agregada") and cfg.PERFIS[n].get("hibrida")
           for n in ("ressarcimento_sem_termo", "ressarcimento_com_termo")))
# 🚨 PENDENTE DE PROPÓSITO: dois serviços do Harmonit têm o nome idêntico
# ("SUBSTITUIÇÃO DIA, HORÁRIO OU LOCAL DIFERENTE - CLIENTE", ids 6967 e 54845).
# Escolher um no chute sairia com o serviço errado sem nada acusar.
checar("o serviço de local diferente segue pendente, falhando alto",
       cfg.SUBSTITUICAO_LOCAL_DIFERENTE_ID is None)
checar("mas o valor já está fixado",
       cfg.SUBSTITUICAO_LOCAL_DIFERENTE_VALOR == 299.90)
checar("rescisão mantém a financeira embutida (decisão de 29/07)",
       cfg.PERFIS["rescisao"].get("financeira_embutida") is True)

# ── 3. registro e tranca ─────────────────────────────────────────────────────
print("\n[3] a tela está registrada e trancada")
t = telas.por_codigo("OPR_1.1")
checar("código OPR_1.1 existe", t is not None)
checar("permissão própria", t["permissao"] == "operacoes")
checar("rota própria", t["rota"] == "/painel/operacoes")
checar("fora do menu", bool(t.get("no_menu")))
checar("está ativa (fase 1)", t in telas.ativas())


async def http():
    async with httpx.AsyncClient(base_url=BASE, timeout=20) as c:
        r = await c.get("/painel/operacoes")
        checar("a página responde 200", r.status_code == 200, f"HTTP {r.status_code}")
        r = await c.get("/painel/api/operacoes/perfis")
        checar("a rota sem token dá 401", r.status_code == 401, f"HTTP {r.status_code}")
        r = await c.get("/painel/static/operacoes.css")
        checar("o CSS próprio é servido", r.status_code == 200, f"HTTP {r.status_code}")
        # ── 5. as duas velhas continuam de pé ────────────────────────────────
        print("\n[5] as duas telas velhas continuam intactas")
        for rota in ("/painel/cadastro-placas", "/painel/gerar-os"):
            r = await c.get(rota)
            checar(f"{rota} continua 200", r.status_code == 200, f"HTTP {r.status_code}")


# ── 4. contrato com a tela ───────────────────────────────────────────────────
print("\n[4] contrato entre a rota de perfis e o HTML que a consome")
# lê o HTML e extrai os campos que ele usa de cada perfil
campos_no_html = set(re.findall(r"\bp\.([a-z_]+)\b", html))
campos_no_html |= set(re.findall(r"\bx\.([a-z_]+)\b", html))
entregues = set(operacoes_router.listar_perfis.__doc__ and [] or [])
amostra = asyncio.run(operacoes_router.listar_perfis(_=None))["perfis"][0]
entregues = set(amostra)
faltando = campos_no_html - entregues
checar("a rota entrega todo campo que a tela lê", not faltando,
       f"faltam: {sorted(faltando)} | entregues: {sorted(entregues)}")
checar("a tela lê pelo menos um campo", bool(campos_no_html))

asyncio.run(http())

print()
print("=" * 56)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
