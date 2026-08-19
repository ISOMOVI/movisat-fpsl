"""Os três defeitos que a auditoria de 17/08 achou na tela de Cadastro de Placas.

🚨 POR QUE ESTE ARQUIVO EXISTE. Os três estavam no código com a suíte VERDE em
519 verificações. A suíte só reprova no que eu pensei em testar — e eu tinha
declarado o trabalho concluído com base nela. Cada checagem aqui é a prova de
que o defeito não volta, não a descrição dele.

  1. escape de HTML na tela (o `gerar_os.html` tem desde 15/07; esta nasceu sem)
  2. depois de criar, a linha diz CRIADA e o botão desabilita
  3. placa repetida na mesma lista não vira duas criações

Roda na VPS: venv/bin/python tests/teste_auditoria_placas.py
Lê a WESO (a prévia confere placa). Não escreve: o interruptor fica desligado.
"""
import asyncio
import pathlib
import re
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel.auth import criar_token  # noqa: E402

BASE = "http://127.0.0.1:8004"
CNPJ_VELASCO = "WQ0P6GLD000108"
RAIZ = pathlib.Path(__file__).resolve().parent.parent
TELA = RAIZ / "frontend" / "cadastro_placas.html"
ROTEADOR = RAIZ / "fpsl_weso" / "painel" / "routers" / "placas_router.py"

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


# ── 1. escape de HTML ───────────────────────────────────────────────────────
print("\n[1] a tela escapa o que joga no innerHTML")

html = TELA.read_text(encoding="utf-8")
checar("a função escapeHtml existe", True, "function escapeHtml(" in html)

# 🚨 O QUE SE MEDE É CADA CAMPO, não a contagem. Contar chamadas passaria com
# escape em quatro campos e o quinto cru -- que é exatamente como o defeito
# nasceu: a tela tinha escape nenhum, mas poderia ter tido escape parcial.
for campo in ("i.placa_digitada", "i.placa_gravada", "i.erro",
              "i.descricao_atual", "i.conferido_em"):
    padrao = re.compile(r"escapeHtml\(\s*" + re.escape(campo))
    checar(f"{campo} passa por escapeHtml", True, bool(padrao.search(html)))

# `i.descricao` é escapado dentro de um ternário; procura o par
checar("i.descricao passa por escapeHtml", True,
       bool(re.search(r"escapeHtml\(i\.descricao\)", html)))

# ⚠️ E o inverso: nenhum desses campos pode aparecer CRU dentro de `${...}`
for campo in ("placa_digitada", "placa_gravada", "descricao_atual"):
    cru = re.compile(r"\$\{\s*i\." + campo + r"\s*\}")
    checar(f"{campo} não aparece cru em template", False, bool(cru.search(html)))


# ── 2 e 3. o comportamento ──────────────────────────────────────────────────
async def main():
    admin = await storage.buscar_usuario_painel("admin")
    h = {"Authorization": "Bearer " + criar_token(admin["login"])}
    async with httpx.AsyncClient(base_url=BASE, timeout=90) as c:
        print("\n[2] placa repetida na lista não vira duas criações")
        # a mesma placa escrita de três jeitos: com espaço, sem, e minúscula
        r = await c.post("/painel/api/placas/previa", headers=h, json={
            "cnpjcpf": CNPJ_VELASCO,
            "itens": [{"placa": "QQQ1Q11"}, {"placa": "QQQ 1Q11"},
                      {"placa": "qqq1q11"}]})
        d = r.json()
        gravadas = [i["placa_gravada"] for i in d["itens"]]
        checar("as três viram a mesma grafia", 1, len(set(gravadas)))
        checar("só a primeira é 'criar'", 1, d["resumo"].get("criar", 0))
        checar("e as outras duas são 'duplicada'", 2,
               d["resumo"].get("duplicada", 0))
        checar("a duplicada aponta de qual linha veio", gravadas[0],
               d["itens"][1]["repetida_de"])

    print("\n[3] a tela não pode dizer 'vai ser criada' depois de criar")
    # 🚨 SÓ LEITURA DE CÓDIGO, e de propósito. Até 18/08 este bloco chamava
    # `/criar` com o interruptor desligado para observar `gravou = false`. O
    # interruptor saiu em 19/08 e a mesma chamada criaria a `QQQ 1Q11` na WESO
    # de verdade -- lixo permanente em produção a cada rodada da suíte.
    # A regra que importa é da TELA, e a tela se lê.
    checar("a tela deriva o rótulo de `gravou`", True,
           "i.gravou ? 'criada' : i.acao" in html)
    checar("e o badge 'criada' existe", True, "criada:" in html)
    # 🚨 o botão só continua habilitado se sobrou linha em `criar`
    checar("o botão depende de contagem.criar", True,
           "disabled = !(contagem.criar > 0)" in html)
    # a contrapartida no backend: `gravou` só vira true depois da releitura
    rota = ROTEADOR.read_text(encoding="utf-8")
    checar("o backend só marca gravou com releitura conferida", True,
           '"gravou": True,' in rota and "verificado_relendo" in rota)


asyncio.run(main())

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
