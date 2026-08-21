"""A tela da aba Operações contra o router que a serve. 2026-08-20.

🚨 CONTRATO DE JSON SE TESTA PELO LADO DE QUEM CONSOME. Em 17/08 o
`do_usuario` passou a devolver `codigo`/`titulo` no lugar de `id`/`nome` e
**derrubou o painel inteiro** — as 677 verificações daquele dia passaram todas,
porque nenhuma olhava o consumidor.

Ao ligar a etapa 4 em 20/08, dois defeitos apareceram que só este tipo de teste
pega, e os dois só apareceriam ao USAR a tela:

  1. **As três rotas de apoio exigiam `gerar_os`.** Quem tem só `operacoes`
     tomaria 403 em serviços, prioridades e problemas.
  2. **O `/extrair` não devolvia os itens do CONTRATO.** O campo `itens` dele
     são os VEÍCULOS — colisão de nome. Sem os itens do contrato não há
     vínculo, sem vínculo não há material, e a OS sairia só com o serviço do
     cabeçalho e o ENTREGA OS: **completa na aparência e vazia no conteúdo**.

Roda na VPS: venv/bin/python tests/teste_tela_operacoes.py
🚨 NÃO FAZ REDE. Lê o fonte da tela e o fonte do router.
"""
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TELA = RAIZ / "frontend" / "operacoes.html"
ROUTER = RAIZ / "fpsl_weso" / "painel" / "routers" / "operacoes_router.py"

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


tela = TELA.read_text(encoding="utf-8")
router = ROUTER.read_text(encoding="utf-8")


def rotas_do_router() -> dict:
    """{caminho: {abas que a rota aceita}} lido do FONTE.

    Ler o fonte e não a aplicação é de propósito: o teste tem de reprovar
    mesmo que alguém quebre o import.
    """
    saida = {}
    for bloco in router.split("@router.")[1:]:
        m = re.match(r'\w+\("([^"]+)"', bloco)
        if not m:
            continue
        caminho = "/painel/api/operacoes" + m.group(1)
        corpo = bloco[:bloco.find("\n\n\n")] if "\n\n\n" in bloco else bloco
        abas = set(re.findall(r'requer_aba\(([^)]*)\)', corpo))
        nomes = set()
        for grupo in abas:
            nomes |= set(re.findall(r'"([^"]+)"', grupo))
        saida[caminho] = nomes
    return saida


def rotas_da_tela() -> set:
    """Todo `/painel/api/operacoes/...` que a tela chama."""
    achados = set()
    for m in re.finditer(r"'(/painel/api/operacoes[^'?]*)", tela):
        achados.add(m.group(1))
    # A rota com parâmetro é montada por concatenação; normaliza.
    return {c.rstrip("/") for c in achados}


# ── 1. as rotas que a tela chama existem ────────────────────────────────────

def teste_rotas_existem():
    print("\n1. Toda rota que a tela chama existe no router")
    do_router = rotas_do_router()
    for caminho in sorted(rotas_da_tela()):
        checar(f"{caminho}", caminho in do_router,
               "não existe no router — a tela tomaria 404")


# ── 2. e aceitam a permissão da aba ─────────────────────────────────────────

def teste_permissao():
    print("\n2. E todas aceitam a permissão `operacoes`")
    # 🚨 ESTE É O TESTE QUE TERIA PEGADO O 403. As rotas equivalentes no
    # `os_router` exigem `gerar_os`; quem tem só `operacoes` não passaria, e
    # isso só apareceria clicando.
    do_router = rotas_do_router()
    for caminho in sorted(rotas_da_tela()):
        abas = do_router.get(caminho)
        if abas is None:
            continue
        checar(f"{caminho} aceita `operacoes`", "operacoes" in abas,
               f"exige {abas or 'nenhuma aba declarada'}")


# ── 3. o contrato do /extrair ───────────────────────────────────────────────

def campos_do_retorno(nome_funcao: str) -> set:
    """As chaves literais do `return {...}` de uma função do router."""
    i = router.find(f"async def {nome_funcao}(")
    if i < 0:
        return set()
    trecho = router[i:]
    j = trecho.find("\n    return {")
    if j < 0:
        return set()
    corpo = trecho[j:j + 3000]
    fim = corpo.find("\n    }")
    return set(re.findall(r'^\s*"([a-z_]+)":', corpo[:fim if fim > 0 else None],
                          re.M))


def sem_comentarios(fonte):
    """O fonte da tela sem comentário, para medir USO e não palavra.

    🚨 SEM ISTO O TESTE MEDE A PALAVRA. Um comentário que EXPLICA por que
    `extraido.<algo>` não deve existir fazia o teste exigir que o router
    entregasse esse campo -- exatamente o erro de 19/08, quando três travas
    reprovaram código correto por acharem um nome dentro de comentário.

    ⚠️ Tira comentário de bloco e linha que COMEÇA com `//`. Nada além disso:
    `//` no meio de uma linha costuma ser `https://`, e um regex esperto aqui
    apagaria código de verdade -- e teste que apaga código aprova o que não
    existe.
    """
    fonte = re.sub(r"/\*.*?\*/", " ", fonte, flags=re.S)
    return "\n".join(l for l in fonte.split("\n")
                     if not l.lstrip().startswith("//"))


def teste_contrato_extrair():
    print("\n3. Todo campo que a tela lê de `/extrair` é entregue")
    entregues = campos_do_retorno("extrair")
    lidos = set(re.findall(r"extraido\.([a-z_]+)", sem_comentarios(tela)))
    checar("o router declara campos no retorno do /extrair",
           len(entregues) > 5, str(entregues))
    for campo in sorted(lidos):
        checar(f"/extrair entrega `{campo}`", campo in entregues,
               f"a tela lê `extraido.{campo}` e o router não devolve. "
               f"Entrega: {sorted(entregues)}")

    # 🚨 A COLISÃO DE NOME QUE CUSTOU O DEFEITO: `itens` são os VEÍCULOS.
    checar("`itens_contrato` existe e é separado de `itens`",
           "itens_contrato" in entregues and "itens" in entregues,
           str(sorted(entregues)))
    checar("a tela lê os itens do CONTRATO, não os veículos, para os vínculos",
           "extraido.itens_contrato" in tela or "itens_contrato" in tela)


# ── 4. o contrato da prévia ─────────────────────────────────────────────────

def teste_contrato_previa():
    print("\n4. Todo campo que a tela lê da prévia é entregue")
    entregues = campos_do_retorno("previa_os")
    checar("o router declara campos no retorno da prévia",
           len(entregues) > 4, str(entregues))
    for campo in ("operacoes", "placas", "avisos", "pendentes", "pode_gerar"):
        checar(f"a prévia entrega `{campo}`", campo in entregues,
               str(sorted(entregues)))
        checar(f"e a tela usa `{campo}`", f"d.{campo}" in tela or
               f"previa.{campo}" in tela)


# ── 5. nada de dado externo entra cru no HTML ───────────────────────────────

def teste_escape():
    print("\n5. Dado externo não entra cru no template")
    # A tela velha de Gerar OS tem 26 `escapeHtml`; a de placas nasceu sem e
    # foi corrigida. Aqui a exigência é a mesma.
    n = len(re.findall(r"escapeHtml\(", tela))
    checar(f"a tela usa escapeHtml ({n} vezes)", n >= 20, str(n))
    checar("a função escapeHtml existe", "function escapeHtml" in tela)

    # Campos que vêm de sistema externo e são desenhados na etapa 4.
    for campo in ("op.descricao", "op.rotulo", "m.descricao", "p.placa",
                  "p.recado", "r.placa", "r.rotulo"):
        checar(f"`{campo}` passa por escapeHtml",
               f"escapeHtml({campo}" in tela,
               "aparece cru no template")


# ── 6. a etapa 4 não ficou órfã ─────────────────────────────────────────────

def teste_etapa4_ligada():
    print("\n6. A etapa 4 está ligada, não é mais esqueleto")
    checar("o esqueleto 'Entra na F4' sumiu", "Entra na <strong>F4</strong>" not in tela)
    checar("há botão de conferir", "conferirOS()" in tela)
    checar("há botão de gerar", "gerarOS()" in tela)
    checar("a gravação exige confirmação explícita", "corpoOS(true)" in tela)
    checar("a prévia NÃO confirma", "corpoOS(false)" in tela)
    # 🚨 A mesma montagem serve prévia e gravação; se cada uma montasse o seu
    # corpo, poderiam divergir sem ninguém ver.
    checar("prévia e gravação usam a MESMA função de corpo",
           len(re.findall(r"function corpoOS\(", tela)) == 1)
    checar("o botão de gerar nasce desabilitado", 'id="btnGerar"' in tela
           and "disabled" in tela)


def main():
    for t in (teste_rotas_existem, teste_permissao, teste_contrato_extrair,
              teste_contrato_previa, teste_escape, teste_etapa4_ligada):
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
