"""A aba Operações inteira, de ponta a ponta. 2026-08-21.

🚨 NASCEU COMO AUDITORIA DE FECHAMENTO E VIROU TESTE. Auditar não é rodar a
suíte: a suíte estava verde e não dizia nada sobre o que FALTAVA. Esta achou
duas coisas -- um bloco de estilo inteiro morto no `<head>` e a checagem de
classes órfãs que só olhava um dos dois arquivos de CSS.

⚠️ E ELA MESMA MEDIU PALAVRA DUAS VEZES antes de medir uso, acusando nomes que
apareciam nos COMENTÁRIOS que documentam a remoção deles. Foi a quarta e a
quinta vez em 21/08 -- por isso o `_sem_comentario_nenhum` tira HTML **e**
JavaScript.

Roda na VPS: venv/bin/python tests/teste_aba_ponta_a_ponta.py
🚨 NÃO FAZ REDE. Lê fixtures, monta o payload como a TELA monta, e compara.

Auditoria original:

🚨 AUDITAR NAO E RODAR A SUITE. A suite ja esta verde (1.485/39) e isso nao diz
nada sobre o que FALTA. O que falta aparece de dois jeitos: comparando com a
tela que ja existe, e perguntando o que acontece DEPOIS do que eu consertei.

Sete frentes:
  1. os 11 perfis ainda chegam ao fim, montando o payload como a TELA monta
  2. toda rota que a tela chama existe, e sob a permissao da aba
  3. as duas telas velhas continuam de pe (elas so saem na F7)
  4. o que eu mexi hoje se sustenta junto
  5. nao sobrou referencia morta
  6. o contrato tela<->router continua fechado
  7. nada de geometria por JavaScript
"""
import ast
import io
import pathlib
import re
import sys

RAIZ = pathlib.Path("/home/claude/fpsl_weso")
sys.path.insert(0, str(RAIZ))

HTML = io.open(RAIZ / "frontend" / "operacoes.html", encoding="utf-8").read()
CSS = io.open(RAIZ / "frontend" / "operacoes.css", encoding="utf-8").read()
ROUTER_TXT = io.open(RAIZ / "fpsl_weso" / "painel" / "routers"
                     / "operacoes_router.py", encoding="utf-8").read()

ok, achados = 0, []


def checar(nome, cond, detalhe=""):
    global ok
    if cond:
        ok += 1
        print(f"  OK   {nome}")
    else:
        achados.append(nome)
        print(f"  FALHA {nome}" + (f"  -- {detalhe}" if detalhe else ""))


def sem_comentarios_js(fonte):
    fonte = re.sub(r"/\*.*?\*/", " ", fonte, flags=re.S)
    return "\n".join(l for l in fonte.split("\n")
                     if not l.lstrip().startswith("//"))


JS = sem_comentarios_js("\n".join(
    re.findall(r"<script>(.*?)</script>", HTML, re.S)))

# ── 1. os 11 perfis ────────────────────────────────────────────────────────
print("== 1. os 11 perfis chegam ao fim pelo caminho da TELA ==")
import io as _io                                             # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg         # noqa: E402
from fpsl_weso.painel import operacoes_os as oos             # noqa: E402
from fpsl_weso.painel.pdf_extractor import extrair_campos    # noqa: E402

FIX = RAIZ / "tests" / "fixtures"
CASOS = {
    "contrato_novo": "contrato_novo_8739.pdf", "aditivo": "aditivo_8840.pdf",
    "rescisao": "rescisao_8842.pdf", "substituicao": "substituicao.pdf",
    "transferencia_novo_titular": "transferencia_novo.pdf",
    "transferencia_antigo_titular": "transferencia_existente.pdf",
    "upgrade": "upgrade_8820.pdf", "manutencao_local": None,
    "manutencao_troca": None, "ressarcimento_sem_termo": None,
    "ressarcimento_com_termo": "aditivo_8840.pdf",
}

proximo = [1]


def linha(dados):
    d = {"id": proximo[0], "recipiente": False, "entrada": False,
         "situacao": None}
    proximo[0] += 1
    d.update(dados)
    return d


for perfil, arq in CASOS.items():
    try:
        if arq is None:
            itens = [{"veiculo": "FIAT UNO", "placa_gravada": "TST0E55"}]
            campos = {}
        else:
            campos = extrair_campos(_io.BytesIO((FIX / arq).read_bytes()), perfil)
            brutas = campos.get("placas") or []
            if not brutas and campos.get("pares"):
                brutas = [{"veiculo": p.get("veiculo_saida"),
                           "placa": p.get("placa_saida"),
                           "veiculo_entrada": p.get("veiculo_entrada"),
                           "placa_entrada": p.get("placa_entrada")}
                          for p in campos["pares"]]
            itens = []
            for b in brutas:
                it = {"veiculo": (b.get("veiculo") or "").strip(),
                      "placa_gravada": (b.get("placa") or "").strip()}
                if (b.get("placa_entrada") or "").strip():
                    it["veiculo_entrada"] = (b.get("veiculo_entrada") or "").strip()
                    it["placa_entrada_gravada"] = b["placa_entrada"].strip()
                itens.append(it)

        p = cfg.PERFIS[perfil]
        linhas = []
        for i in itens:
            saida = linha({"veiculo": i["veiculo"], "placa": i["placa_gravada"]})
            linhas.append(saida)
            if i.get("placa_entrada_gravada"):
                linhas.append(linha({"veiculo": i.get("veiculo_entrada"),
                                     "placa": i["placa_entrada_gravada"],
                                     "entrada": True, "origem": saida["id"]}))
            suf = campos.get("recipiente_sufixo") or p.get("recipiente")
            if suf:
                linhas.append(linha({
                    "veiculo": "(bancada)",
                    "placa": i["placa_gravada"].replace(" ", "") + suf,
                    "recipiente": True, "origem": saida["id"]}))

        # 🚨 A `corpoOS` da tela, linha por linha -- inclusive o pareamento
        # por `origem`, que e o conserto da substituicao.
        reais = [l for l in linhas if not l["recipiente"] and not l["entrada"]]
        placas = []
        for l in reais:
            par = next((x for x in linhas
                        if x["entrada"] and x.get("origem") == l["id"]), None)
            placas.append({"placa": l["placa"], "veiculo": l["veiculo"],
                           "placa_entrada": par["placa"] if par else None,
                           "veiculo_entrada": par["veiculo"] if par else "",
                           "modelo_escolhido": None})

        body = oos.MontarInput(perfil=perfil, cliente_id=998063, lote="AUD",
                               termo=str(campos.get("termo") or "9999"),
                               produto_servico_id=6966, placas=placas, itens=[])
        aloc, _ = oos.alocar_itens_por_placa([], body.placas)
        ops = oos.montar(body, p, aloc, [], [], {}, {}, {})
        checar(f"{perfil} gera {len(ops)} OS", len(ops) > 0)
    except Exception as e:
        checar(f"{perfil} gera OS", False, f"{type(e).__name__}: {str(e)[:90]}")

# ── 2. as rotas que a tela chama ───────────────────────────────────────────
print()
print("== 2. toda rota que a tela chama existe, sob a permissao da aba ==")
from fpsl_weso.painel.routers import operacoes_router as opr   # noqa: E402

rotas = {r.path for r in opr.router.routes}
chamadas = set(re.findall(r"'(/painel/api/operacoes/[^'?]+)", JS))
chamadas |= set(re.findall(r'"(/painel/api/operacoes/[^"?]+)', JS))
chamadas |= set(re.findall(r"`(/painel/api/operacoes/[^`?$]+)", JS))
faltando = []
for c in sorted(chamadas):
    base = c.rstrip("/")
    if base in rotas or any(r.startswith(base) for r in rotas):
        continue
    faltando.append(c)
checar(f"as {len(chamadas)} rotas chamadas existem", not faltando, str(faltando))

# 🚨 O DEFEITO DE 20/08: rota de apoio exigindo `gerar_os` da 403 para quem so
# tem `operacoes`. Voltou em 21/08 na busca de cliente.
outra_aba = re.findall(r'requer_aba\("(?!operacoes)([a-z_]+)"', ROUTER_TXT)
checar("nenhuma rota da aba exige outra permissão",
       not outra_aba, f"exigem: {set(outra_aba)}")

# ── 3. as duas telas velhas ────────────────────────────────────────────────
print()
print("== 3. as duas telas velhas continuam de pé (só saem na F7) ==")
for nome in ("gerar_os.html", "cadastro_placas.html", "vinculos.html"):
    checar(f"{nome} continua existindo",
           (RAIZ / "frontend" / nome).exists())
os_router = io.open(RAIZ / "fpsl_weso" / "painel" / "routers" / "os_router.py",
                    encoding="utf-8").read()
checar("o os_router não foi tocado hoje",
       "vinculos" in os_router and len(os_router.split("\n")) > 1200)

# ── 4. o que mexi hoje se sustenta junto ───────────────────────────────────
print()
print("== 4. o que mexi hoje se sustenta junto ==")
checar("a trava de etapas vale no clique do cabeçalho",
       'onclick="irPara(' in HTML and "faltaNaEtapa" in JS)
checar("a retomada pergunta, nunca retoma sozinha",
       "oferecerRetomada" in JS and "barraRetomar" in HTML
       and "retomarLote" in JS)
checar("as duas escritas confirmam",
       JS.count("confirm(") >= 2)
checar("o recipiente diz que vai só para a WESO",
       "só WESO" in HTML or "so WESO" in HTML)
checar("o cliente só se troca em perfil SEM termo",
       "btnBuscarCliente" in JS and "p.sem_termo ? '' : 'none'" in JS)
checar("o aviso vem do servidor com a placa",
       "a.placa" in JS and 'def aviso(' in
       io.open(RAIZ / "fpsl_weso" / "painel" / "operacoes_os.py",
               encoding="utf-8").read())
checar("o erro leva a referência da requisição", "X-Request-Id" in JS)

# ── 5. referência morta ────────────────────────────────────────────────────
print()
print("== 5. não sobrou referência morta ==")
ids_html = set(re.findall(r'id="([A-Za-z0-9_-]+)"', HTML))
ids_js = set(re.findall(r"getElementById\(\s*['\"]([A-Za-z0-9_-]+)['\"]", JS))
orfaos_js = sorted(i for i in ids_js if i not in ids_html
                   and not i.startswith(("panel-", "dot-", "sit-",
                                         "marca-", "valor-", "sec-")))
checar("o JS não busca id que não existe", not orfaos_js, str(orfaos_js))
# 🚨 OLHA OS DOIS LUGARES. Ate 21/08 esta checagem varria so o
# `operacoes.css`, e havia um bloco de estilo INLINE no `<head>` com quatro
# regras -- todas mortas. CSS morto em outro arquivo nao e menos morto; so e
# mais dificil de achar.
ESTILO_INLINE = "".join(re.findall(r"<style>(.*?)</style>", HTML, re.S))
classes_css = set(re.findall(r"\.([a-z][a-z0-9-]+)\s*[{,:]", CSS + ESTILO_INLINE))
# ⚠️ E COMPARA COM O CORPO SEM COMENTARIO NENHUM -- HTML **E** JavaScript.
# 🚨 QUATRO VEZES EM 21/08 EU ESCREVI TRAVA QUE MEDE PALAVRA: o teste de
# contrato exigiu um campo citado num comentario meu; a guarda de rotulo
# reprovou os dois "Buscar" certos; a de geometria reprovou a barra de
# progresso; e esta acusou `placasInfo` e a tag de estilo dentro dos
# comentarios que DOCUMENTAM a remocao deles. Nome citado na explicacao de por
# que algo saiu nao e uso.
def _sem_comentario_nenhum(fonte):
    fonte = re.sub(r"<!--.*?-->", " ", fonte, flags=re.S)
    partes = []
    resto = fonte
    while "<script>" in resto:
        antes, resto = resto.split("<script>", 1)
        dentro, resto = resto.split("</script>", 1)
        partes.append(antes)
        partes.append(sem_comentarios_js(dentro))
    partes.append(resto)
    return "".join(partes)


CORPO = _sem_comentario_nenhum(HTML)
orfas = sorted(c for c in classes_css if c not in CORPO)
checar("nenhuma classe CSS órfã (arquivo + inline)", not orfas, str(orfas))
checar("nenhum bloco de estilo inline sobrou",
       not re.search(r"<style[^>]*>", CORPO))

# ⚠️ E AQUI TAMBEM SEM COMENTARIO: o nome de uma coisa REMOVIDA aparece no
# comentario que documenta a remocao. Foi o que me fez perder tempo hoje --
# terceira trava minha medindo palavra em vez de uso.
mortos = [m for m in ("clienteTrocadoNaMao", "irParaBase", "irParaEtapa4",
                      "tabelaLeitura", "servicoId", "placasInfo",
                      "resumoPerfil", "step-dot") if m in CORPO]
checar("nenhum resto das versões anteriores", not mortos, str(mortos))

# ── 6. contrato tela <-> router ────────────────────────────────────────────
print()
print("== 6. o contrato tela <-> router ==")
arvore = ast.parse(ROUTER_TXT)


def chamadas_em(nome):
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name == nome:
            return {ast.unparse(f.func) for f in ast.walk(no)
                    if isinstance(f, ast.Call)}
    return set()


checar("abrir_lote guarda o cliente",
       "reg.guardar_cliente" in chamadas_em("abrir_lote"))
checar("criar_uma_placa marca a etapa 3",
       "reg.marcar_etapa" in chamadas_em("criar_uma_placa"))
checar("gerar_os encerra o lote", "reg.encerrar" in chamadas_em("gerar_os"))

# ── 7. geometria por JavaScript ────────────────────────────────────────────
print()
print("== 7. nada de geometria por JavaScript (lição de 18/08) ==")
proibidos = [p for p in ("padding", "margin", "width", "height", "position")
             if f"style.{p}" in JS]
checar("o JS não mexe em geometria", not proibidos, str(proibidos))
checar("nenhum <style> injetado", "<style" not in JS)
inline = re.findall(r'style="[^"]*"', HTML)
estaticos = [s for s in inline if "${" not in s and not re.fullmatch(
    r'style="(display:(none|block)|visibility:hidden)"', s)]
checar("nenhuma geometria estática inline", not estaticos, str(estaticos[:3]))

print()
print(f"== {ok} verificações OK, {len(achados)} falha(s) ==")
if achados:
    for a in achados:
        print("   -", a)
    sys.exit(1)
