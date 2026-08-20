"""Aba Operações — F6: `HST_4.1`, Histórico de Operações. 2026-08-20.

🚨 O NOME NÃO É "REGISTRO", E ISSO É O PRIMEIRO QUE ESTE ARQUIVO PRENDE. Já
existe `CFG_9.1 Registro de telas` **no menu**, e `operacoes_registro.py` é o
registro de lote e passos da própria aba. Chamar a F6 de "Registro" seria a
terceira coisa com o mesmo nome, e a primeira é um item que a pessoa vê.
`HST_4.1` entra na família que já existe: Histórico de OS, Histórico de Placas.

O que mais este arquivo prende:

  1. **`HST_3.1` continua QUEIMADO.** Era a tela de Aderência, apagada em 19/08
     porque a premissa era minha. Código aposentado não se reaproveita.

  2. **A tela mostra `desistiu` em destaque.** É a razão de ela existir:
     `desistiu` significa que a rotina tentou até o teto e parou — há
     equipamento parado num estado que ninguém pediu. Sem a tela, é linha morta
     numa tabela que ninguém abre.

  3. **O contrato com quem consome.** Todo campo que a tela lê de `/historico`
     é entregue, e toda rota que ela chama existe e aceita `operacoes`. É a
     lição de 18/08 — e em 20/08 ela pegou dois defeitos ao ligar a etapa 4.

  4. **`listar_lotes` não é N+1.** Uma consulta só; ler o cabeçalho e depois
     pedir o resumo de cada lote seria 101 idas ao banco para desenhar 100
     linhas.

Roda na VPS: venv/bin/python tests/teste_operacoes_f6.py
🚨 NÃO FAZ REDE.
"""
import asyncio
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import operacoes_registro as reg  # noqa: E402
from fpsl_weso.painel import telas  # noqa: E402

TELA = RAIZ / "frontend" / "operacoes_historico.html"
ROUTER = RAIZ / "fpsl_weso" / "painel" / "routers" / "operacoes_router.py"
MAIN = RAIZ / "main.py"

ok, falhas = 0, []
tela = TELA.read_text(encoding="utf-8")
router = ROUTER.read_text(encoding="utf-8")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# ── 1. o registro e o nome ──────────────────────────────────────────────────

def teste_registro():
    print("\n1. A tela está registrada, e o nome não colide")
    t = telas.por_codigo("HST_4.1")
    checar("HST_4.1 existe", t is not None)
    if not t:
        return
    checar("título é 'Histórico de Operações'",
           t["titulo"] == "Histórico de Operações", t["titulo"])
    checar("rota própria", t["rota"] == "/painel/operacoes-historico", t["rota"])
    checar("mesma permissão da aba principal", t["permissao"] == "operacoes",
           str(t["permissao"]))
    checar("está no menu", not t.get("no_menu"))
    checar("está ativa", t in telas.ativas())

    # 🚨 A COLISÃO QUE O NOME EVITA.
    titulos = [x["titulo"] for x in telas.TELAS]
    checar("'Registro de telas' continua existindo e é OUTRA tela",
           "Registro de telas" in titulos)
    checar("nenhum título se repete",
           len(titulos) == len(set(titulos)),
           str([x for x in titulos if titulos.count(x) > 1]))

    codigos = [x["codigo"] for x in telas.TELAS]
    checar("HST_3.1 continua QUEIMADO — não foi reaproveitado",
           "HST_3.1" not in codigos, str(codigos))
    checar("nenhum código se repete", len(codigos) == len(set(codigos)))


def teste_pagina():
    print("\n2. A página é servida")
    m = MAIN.read_text(encoding="utf-8")
    checar("main.py serve a rota", "/painel/operacoes-historico" in m)
    checar("e aponta para o arquivo certo",
           "operacoes_historico.html" in m)
    checar("o arquivo existe", TELA.exists())


# ── 3. o contrato com a tela ────────────────────────────────────────────────

def rotas_do_router() -> dict:
    saida = {}
    for bloco in router.split("@router.")[1:]:
        m = re.match(r'\w+\("([^"]+)"', bloco)
        if not m:
            continue
        corpo = bloco[:bloco.find("\n\n\n")] if "\n\n\n" in bloco else bloco
        nomes = set()
        for grupo in re.findall(r'requer_aba\(([^)]*)\)', corpo):
            nomes |= set(re.findall(r'"([^"]+)"', grupo))
        saida["/painel/api/operacoes" + m.group(1)] = nomes
    return saida


def teste_contrato():
    print("\n3. Toda rota que a tela chama existe e aceita `operacoes`")
    do_router = rotas_do_router()
    chamadas = {m.group(1).rstrip("/") for m in
                re.finditer(r"'(/painel/api/operacoes[^'?+]*)", tela)}
    for caminho in sorted(chamadas):
        existe = caminho in do_router
        checar(f"{caminho} existe", existe, "a tela tomaria 404")
        if existe:
            checar(f"{caminho} aceita `operacoes`",
                   "operacoes" in do_router[caminho],
                   f"exige {do_router[caminho]}")

    i = router.find("async def historico(")
    trecho = router[i:i + 900] if i >= 0 else ""
    entregues = set(re.findall(r'"([a-z_]+)":', trecho))
    for campo in ("lotes", "pendentes", "resumo_pendencias", "teto_tentativas"):
        checar(f"/historico entrega `{campo}`", campo in entregues,
               str(sorted(entregues)))
        checar(f"e a tela usa `{campo}`",
               f"d.{campo}" in tela or f"dados.{campo}" in tela)


# ── 4. `desistiu` grita ─────────────────────────────────────────────────────

def teste_desistiu():
    print("\n4. `desistiu` aparece em destaque — é a razão da tela existir")
    checar("a tela trata o estado `desistiu`", "desistiu" in tela)
    checar("com classe de erro, não de aviso comum", "msg-erro" in tela)
    checar("e diz quantas vezes a rotina tentou", "teto_tentativas" in tela)
    # ⚠️ `ignorado` NÃO é erro: descartar de propósito é comportamento certo, e
    # pintar de vermelho ensinaria a equipe a ignorar o vermelho.
    checar("`ignorado` NÃO é pintado de vermelho",
           "ignorado: 'badge-blue'" in tela or 'ignorado: "badge-blue"' in tela,
           "descartar de propósito não é falhar")


# ── 5. nada cru no template ─────────────────────────────────────────────────

def teste_escape():
    print("\n5. Dado externo não entra cru")
    n = len(re.findall(r"escapeHtml\(", tela))
    checar(f"a tela usa escapeHtml ({n} vezes)", n >= 15, str(n))
    for campo in ("p.ultimo_erro", "p.placa", "l.perfil", "l.termo",
                  "p.erro || p.descricao"):
        checar(f"`{campo}` passa por escapeHtml", f"escapeHtml({campo}" in tela)


# ── 6. a listagem não é N+1 ─────────────────────────────────────────────────

def teste_listagem():
    print("\n6. `listar_lotes` responde, e numa consulta só")
    lotes = asyncio.run(reg.listar_lotes())
    checar("listar_lotes responde sem erro", isinstance(lotes, list))
    fonte = (RAIZ / "fpsl_weso" / "painel"
             / "operacoes_registro.py").read_text(encoding="utf-8")
    i = fonte.find("async def listar_lotes")
    corpo = fonte[i:i + 2000]
    checar("uma única chamada a execute()",
           corpo.count("conn.execute(") == 1,
           f"{corpo.count('conn.execute(')} chamadas — N+1")
    checar("o resumo sai do próprio SQL",
           "SELECT COUNT(*)" in corpo)
    checar("ordena pelo carimbo, porque não há `id` na tabela",
           "ORDER BY l.criado_em" in corpo)


def main():
    for t in (teste_registro, teste_pagina, teste_contrato, teste_desistiu,
              teste_escape, teste_listagem):
        t()
    print(f"\n{'=' * 62}")
    print(f"{ok} verificações OK, {len(falhas)} falhas")
    if falhas:
        for f in falhas:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
