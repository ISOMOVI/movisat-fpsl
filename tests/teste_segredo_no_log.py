"""O `code` do OAuth não pode ir para o log de acesso (2026-08-19).

🚨 POR QUE ESTE TESTE EXISTE. Medido em 18/08: o `code` do OAuth do Google ia
inteiro para o journal, 37 entradas. É a mesma classe do incidente de 12/08 no
MoviZap, onde o segredo do webhook do Evolution foi ao disco 2.527 vezes em
24 h — lá o segredo vive no CAMINHO, aqui na QUERY STRING.

⚠️ O risco aqui é menor e vale registrar por quê: o `code` é de uso único e
expira em ~10 min, então journal antigo não autentica ninguém. O que justifica
o filtro é o hábito, não o dano provável.

🚨 O FILTRO REESCREVE `record.args`, NÃO A MENSAGEM FORMATADA. O
`uvicorn.access` guarda os campos separados e só os junta na hora de escrever.
Testar a mensagem final passaria com o filtro errado — por isso as verificações
abaixo montam um `LogRecord` de verdade, com o mesmo formato do uvicorn, e
conferem `record.args`.

Roda na VPS: venv/bin/python tests/teste_segredo_no_log.py
Não faz rede, não toca banco.
"""
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import main  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


f = main.MascararSegredoDaQueryString()


def passar(caminho):
    """Roda o filtro num LogRecord no formato REAL do uvicorn.access."""
    record = logging.LogRecord(
        name="uvicorn.access", level=logging.INFO, pathname="", lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", caminho, "1.1", 302), exc_info=None)
    f.filter(record)
    return record.args[2]


# ── 1. o caso real ───────────────────────────────────────────────────────────
print("\n[1] o caso que aconteceu")
real = "/painel/api/auth/google/callback?code=4/0AVMBsJi-SEGREDO-REAL&state=abc123"
saida = passar(real)
checar("o code sumiu", True, "4/0AVMBsJi" not in saida)
checar("o state também", True, "abc123" not in saida)
checar("e a rota continua legível",
       "/painel/api/auth/google/callback?code=<mascarado>&state=<mascarado>", saida)

# ── 2. o que NÃO pode ser mascarado ──────────────────────────────────────────
print("\n[2] o resto do log não pode ser destruído")
checar("caminho sem query passa intacto",
       "/painel/api/me", passar("/painel/api/me"))
checar("parâmetro comum passa intacto",
       "/painel/api/os?limite=50", passar("/painel/api/os?limite=50"))
checar("mascara só o sensível, não o vizinho",
       "/x?limite=50&code=<mascarado>&pagina=2",
       passar("/x?limite=50&code=SEGREDO&pagina=2"))
# 🚨 `code` como parte de outro nome não pode casar por engano
checar("`barcode` não é `code`",
       "/x?barcode=123", passar("/x?barcode=123"))
# ⚠️ `?code` sem `=` não tem valor para esconder, e não pode virar lixo
checar("parâmetro sem valor passa intacto", "/x?code", passar("/x?code"))

# ── 3. o filtro está REGISTRADO, não só definido ─────────────────────────────
print("\n[3] registrado nos loggers que escrevem")
# 🚨 ESTA É A VERIFICAÇÃO QUE PEGA O ERRO MAIS PROVÁVEL: escrever a classe e
# esquecer o `addFilter`. Aí tudo acima passa e o segredo continua no disco.
for nome in ("uvicorn.access", "gunicorn.access"):
    tem = any(isinstance(x, main.MascararSegredoDaQueryString)
              for x in logging.getLogger(nome).filters)
    checar(f"{nome} tem o filtro", True, tem)

# ── 4. o outro logger que escreve a mesma linha ──────────────────────────────
print("\n[4] o nginx")
# ⚠️ O filtro NÃO alcança o access.log do nginx. Isso é fato registrado, não
# defeito — e o `docs/fpsl/11_Seguranca.md` tem de dizer.
doc = (RAIZ / "docs" / "fpsl" / "11_Seguranca.md").read_text(encoding="utf-8")
checar("a doc registra que o nginx fica de fora", True,
       "nginx" in doc.lower() and "mascarado" in doc.lower())

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for x in falhas:
        print("  FALHOU:", x)
    sys.exit(1)
