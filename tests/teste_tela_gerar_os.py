"""A tela de Gerar OS, exercitada de verdade — sem navegador.

🚨 POR QUE ESTE ARQUIVO EXISTE. Em 14/08 a extração de termo parou de funcionar
para TODOS os 7 perfis de contrato, e nada acusou: nem log, nem `py_compile`,
nem `node --check`, nem o detector de chamada órfã. O erro era de TIPO de
argumento — `progresso()` recebendo string depois de passar a esperar lista — e
estourava FORA do `try`, então a tela não dava alerta, não mostrava mensagem e
não liberava o botão. Simplesmente não fazia nada. Quem descobriu foi o usuário,
clicando.

Aqui o script da página roda inteiro num DOM de mentira, com `fetch` devolvendo
o JSON REAL da extração. Se `extrair()` estourar em qualquer ponto, reprova.

⚠️ ISTO NÃO SUBSTITUI ABRIR NO NAVEGADOR. Não há layout, não há CSS, não há
evento de clique de verdade. O que ele garante é que o CAMINHO do código
aguenta a resposta real do backend — que é exatamente o que faltava.

Roda na VPS: venv/bin/python tests/teste_tela_gerar_os.py
Não toca Harmonit nem WESO: a extração é local, o resto é mock.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso.painel import pdf_extractor  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
HTML = RAIZ / "frontend" / "gerar_os.html"
HARNESS = RAIZ / "tests" / "exercitar_tela.js"
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def exercitar(html, resposta, perfil):
    """Devolve o dicionário que o harness imprime, ou None se o node faltar."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(resposta, f, ensure_ascii=False)
        caminho = f.name
    try:
        r = subprocess.run(["node", str(HARNESS), str(html), caminho, perfil],
                           capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return None
    finally:
        pathlib.Path(caminho).unlink(missing_ok=True)
    if not r.stdout.strip():
        return {"erros": [f"harness sem saída: {r.stderr[:200]}"]}
    return json.loads(r.stdout)


def extrair(fixture, perfil):
    with open(RAIZ / "tests" / "fixtures" / fixture, "rb") as f:
        return pdf_extractor.extrair_campos(f, perfil)


# ── 1. rescisão 8842 — o termo que o usuário testou ──────────────────────────
# ⚠️ Documento REAL, de 1 placa só. Foi com ele que o defeito apareceu.
print("\n[1] rescisão 8842 — o caso que quebrou")
dados = extrair("rescisao_8842.pdf", "rescisao")
checar("o extrator lê o termo", "8842", dados.get("termo"))
checar("e a única placa do documento", 1, len(dados.get("veiculos") or []))

r_resc = exercitar(HTML, dados, "rescisao")
if r_resc is None:
    print("  (node ausente -- exercício da tela pulado)")
else:
    checar("a tela atravessa a extração sem estourar", [], r_resc.get("erros"))
    checar("o termo chega ao campo da Etapa 2", "8842", r_resc.get("termo_na_tela"))
    checar("chamou o endpoint de extração", True, r_resc.get("chamou_extrair"))
    checar("a mensagem de sucesso apareceu", True,
           "Extraído: Termo 8842" in (r_resc.get("mensagem") or ""))
    checar("a tabela de itens foi montada", True, r_resc.get("itens_html"))
    checar("o botão voltou a ficar clicável", True, r_resc.get("botao_liberado"))
    checar("e nenhum alerta de erro subiu", [], r_resc.get("alertas"))

# ── 2. manutenção — o caminho sem termo ──────────────────────────────────────
print("\n[2] manutenção — sem anexo, vai direto para a Etapa 2")
r_manut = exercitar(HTML, {}, "manutencao_troca")
if r_manut is not None:
    checar("a tela atravessa o caminho sem termo", [], r_manut.get("erros"))
    checar("não chama o endpoint de extração", False, r_manut.get("chamou_extrair"))
    checar("e não alerta nada", [], r_manut.get("alertas"))

# ── 3. o exercício precisa PEGAR o defeito ───────────────────────────────────
# 🚨 Teste que só passa quando está tudo certo não prova nada. Este reproduz o
# defeito real injetando de volta as DUAS metades: a chamada com string e a
# ausência da conversão defensiva.
print("\n[3] o exercício reprova a versão quebrada")
if r_resc is not None:
    # ⚠️ O ARQUIVO ESTÁ EM CRLF (veio por scp do Windows). Substituir usando
    # só `\n` não casa com nada e a injeção falha em silêncio -- o teste
    # passaria dizendo que a versão quebrada "não reprova", quando na verdade
    # ele nem chegou a quebrá-la. Normaliza antes.
    texto = HTML.read_text(encoding="utf-8").replace("\r\n", "\n")
    quebrado = (texto
                .replace("  if (typeof etapas === 'string') etapas = [etapas];\n", "")
                .replace("""    progresso(['Lendo o documento', 'Extraindo placas e itens',
               'Conferindo os vínculos']);""",
                         "  progresso('Lendo o documento...');"))
    # a injeção precisa ter MUDADO alguma coisa, senão não há defeito nenhum
    checar("a injeção do defeito realmente alterou o arquivo", True,
           quebrado != texto)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as f:
        f.write(quebrado)
        caminho = f.name
    try:
        rq = exercitar(pathlib.Path(caminho), dados, "rescisao")
        # ⚠️ O QUE SE MEDE É O QUE O USUÁRIO SENTE: a extração não conclui.
        # Não dá para exigir exceção vazando, porque depende de a chamada
        # estar dentro ou fora do `try` -- no defeito original estava FORA e
        # a tela ficava muda; com ela dentro, vira mensagem de erro. Nos dois
        # casos o termo não chega ao campo, e é isso que importa.
        checar("com o defeito, o termo NÃO chega à Etapa 2", True,
               rq.get("termo_na_tela") != "8842")
        checar("e a versão no ar chega", "8842", r_resc.get("termo_na_tela"))
    finally:
        pathlib.Path(caminho).unlink(missing_ok=True)

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
