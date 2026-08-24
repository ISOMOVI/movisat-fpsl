"""O cache diário do Harmonit existe, é fresco e é o que a etapa 3 lê. 24/08.

🚨 POR QUE ISTO EXISTE. A lista de placas dos perfis SEM TERMO saía de uma
tabela que NADA atualizava -- nenhum cron, nenhum caminho no código. Ela andava
quando alguém lembrava de rodar um script à mão, e ninguém tinha como perceber
que ela tinha parado: lista velha e lista nova têm a mesma cara.

Medido em 24/08: Harmonit ao vivo 9.116 × espelho 9.114. Uma das duas ausentes,
`FWB 0E36`, tinha sido criada pelo PRÓPRIO painel três horas antes.

A regra da casa -- manutenção só em placa que já está na WESO há pelo menos um
dia -- só se sustenta se a base for refeita todo dia.

⚠️ ESTE TESTE FALA COM O DISCO, NÃO COM A REDE. Ele não roda o cron nem chama
o Harmonit: confere que o cache existe, que o carimbo dele não envelheceu, e
que o endpoint lê de lá. Se a máquina não tiver o cache (checkout novo), ele
diz isso e sai sem reprovar -- teste de infraestrutura ausente não é defeito de
código.

Roda na VPS: venv/bin/python tests/teste_cache_harmonit.py
"""
import pathlib
import sqlite3
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel.routers import operacoes_router as opr  # noqa: E402

ok, falhas = 0, []

# 🚨 O PISO É O MESMO DO SCRIPT. Se as duas divergirem, uma delas está errada e
# ninguém sabe qual.
MINIMO = 8000
# O cron roda 1x por dia; 48 h dá folga para uma falha isolada sem virar alarme
# falso -- e alarme falso treina a equipe a ignorar alarme.
IDADE_MAXIMA_H = 48


def checar(nome, cond, detalhe=""):
    global ok
    if cond:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


CACHE = opr.CACHE_HARMONIT
CRON = pathlib.Path("/home/claude/harmonit_cache/rodar.sh")

print("== o endpoint aponta para o cache, e não para a tabela parada ==")
# 🚨 MEDE A LIGAÇÃO: é a constante que o router REALMENTE usa, importada dele.
checar("o router tem a constante do cache",
       str(CACHE).endswith("harmonit_cache/harmonit.db"), str(CACHE))

if not CACHE.exists():
    print(f"\n⚠️  {CACHE} não existe nesta máquina — nada a conferir.")
    print("    (o cache é infraestrutura da VPS, criado pelo cron de 04:50)")
    print(f"\n== {ok} verificações OK, 0 falha(s) ==")
    raise SystemExit(0)

print()
print("== o cache está de pé e é fresco ==")
with sqlite3.connect(f"file:{CACHE}?mode=ro", uri=True) as c:
    total = c.execute("SELECT count(*) FROM veiculos").fetchone()[0]
    carimbo = c.execute(
        "SELECT valor FROM meta WHERE chave = 'atualizado_em'").fetchone()
    com_cliente = c.execute(
        "SELECT count(*) FROM veiculos WHERE cliente_id IS NOT NULL").fetchone()[0]
    sem_chave = c.execute(
        "SELECT count(*) FROM veiculos WHERE chave_placa IS NULL "
        "OR chave_placa = ''").fetchone()[0]

checar(f"tem {total} veículos, acima do piso de {MINIMO}", total >= MINIMO,
       "abaixo do piso é resposta ruim do Harmonit, não base que encolheu")
checar("tem carimbo de quando foi feito", bool(carimbo and carimbo[0]))
if carimbo and carimbo[0]:
    idade = datetime.now() - datetime.fromisoformat(carimbo[0])
    checar(f"e o carimbo é de {carimbo[0]} — menos de {IDADE_MAXIMA_H} h",
           idade < timedelta(hours=IDADE_MAXIMA_H),
           f"{idade} atrás. O cron das 04:50 parou?")
# 🚨 SEM `cliente_id` O CACHE NÃO SERVE PARA NADA AQUI: a pergunta que a etapa
# 3 faz é "quais veículos são deste cliente". É exatamente o que a WESO não
# responde -- lá são 0 de 1.955 -- e por isso a lista vem do Harmonit.
checar("os veículos têm cliente", com_cliente == total,
       f"{total - com_cliente} sem cliente_id")
# ⚠️ A PRIMEIRA VERSÃO DESTA TRAVA EXIGIA CHAVE EM TODOS, e reprovou -- mas o
# defeito era do DADO, não do cache: a base do Harmonit tem 2 veículos sem
# placa (um `FORD F 4000` num cliente real e um registro em branco). O espelho
# guarda os dois de propósito, porque espelho que edita a origem deixa de
# servir para conferir a origem. Quem os filtra é o endpoint.
checar(f"os {sem_chave} sem placa são poucos e conhecidos", sem_chave <= 5,
       f"{sem_chave} sem chave_placa -- se cresceu, a origem mudou")
with sqlite3.connect(f"file:{CACHE}?mode=ro", uri=True) as c:
    orfas = c.execute(
        "SELECT count(*) FROM veiculos WHERE chave_placa <> '' "
        "AND (placa IS NULL OR TRIM(placa) = '')").fetchone()[0]
checar("e nenhuma placa com chave sem texto", orfas == 0, str(orfas))

print()
print("== e a lista que a etapa 3 recebe não tem placa vazia ==")
# 🚨 MEDE O ENDPOINT, NÃO A TABELA. O cliente 87787 tem o `FORD F 4000` sem
# placa: sem o filtro, ele virava um `<option>` vazio, e escolher esse option
# levaria placa vazia para a gravação nos dois sistemas.
import asyncio  # noqa: E402

lista = asyncio.run(opr.placas_do_cliente(cliente_harmonit_id=87787, _=None))
placas = [v["placa"] for v in lista["veiculos"]]
checar("o cliente do veículo sem placa devolve lista", bool(placas), str(lista))
checar("e nenhuma entrada dela vem vazia",
       all(p and p.strip() for p in placas),
       f"{sum(1 for p in placas if not (p or '').strip())} vazias")
checar("a origem é o cache, não o espelho parado",
       lista.get("origem") == "cache", str(lista.get("origem")))
checar("e ela diz de quando é", bool(lista.get("atualizado_em")),
       str(lista.get("atualizado_em")))

print()
print("== o cron existe e é o caminho que o cron chama ==")
checar("o rodar.sh está no lugar", CRON.exists(), str(CRON))
if CRON.exists():
    checar("e é executável", CRON.stat().st_mode & 0o111 != 0)

print()
print(f"== {ok} verificações OK, {len(falhas)} falha(s) ==")
if falhas:
    for f in falhas:
        print("   -", f)
    sys.exit(1)
