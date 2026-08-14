"""Perfis de MANUTENÇÃO — sem termo, sem flags, com recipiente `-MANUT`.

🚨 MANUTENÇÃO NÃO NASCE DE DOCUMENTO. Os 7 perfis de contrato vêm de um PDF
assinado; estes dois vêm de um chamado. Não há termo, não há item de contrato e
não há OS financeira — o que existe é uma placa e um defeito.

O que este teste trava:
  1. os dois perfis existem e não flegam cobrar nem comodato em nada;
  2. a chave do recipiente tolera espaço em qualquer lugar, e SÓ ela;
  3. `MANUTENÇÃO` e `MANUTENCAO` casam (acento dobrado);
  4. recipiente ausente/ambíguo/divergente/sem série é DESCARTADO com aviso,
     e a OS sai com `NUMERO DE SERIE` e sem o equipamento nos materiais;
  5. o item marcado `nas_duas` vira cópia operacional sem flag e com valor 0;
  6. a série só é liberada com OS criada, série na descrição e material aceito.

Roda na VPS:  venv/bin/python tests/teste_manutencao.py
Só leitura — não toca Harmonit e não escreve na WESO.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import equipamentos, templates_config  # noqa: E402
from fpsl_weso.painel.routers import os_router  # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


class _Placa:
    def __init__(self, placa, veiculo=""):
        self.placa = placa
        self.veiculo = veiculo
        self.sem_bloqueio = False
        self.placa_entrada = None


class _Body:
    def __init__(self, placas, termo=""):
        self.placas = placas
        self.termo = termo


LOCAL = templates_config.PERFIS["manutencao_local"]
TROCA = templates_config.PERFIS["manutencao_troca"]

# ── 1. os perfis ─────────────────────────────────────────────────────────────
print("\n[1] os dois perfis")
checar("manutencao no local existe", "Manutenção no local", LOCAL["label"])
checar("manutencao com troca existe", "Manutenção com troca", TROCA["label"])
checar("nenhuma das duas exige termo", (True, True),
       (LOCAL["sem_termo"], TROCA["sem_termo"]))
checar("nenhuma das duas flega nada", (True, True),
       (LOCAL["sem_flags"], TROCA["sem_flags"]))
checar("nenhuma das duas gera financeira", (True, True),
       (LOCAL["sem_financeira"], TROCA["sem_financeira"]))
checar("1 OS por placa nas duas", (1, 1),
       (LOCAL["os_por_placa"], TROCA["os_por_placa"]))
# 🚨 o tipo vai por NOME: das 14 OS de manutencao que a casa abriu na mao, 7
# usam `tipo = 55`, que nao esta mais na lista do Harmonit.
checar("tipo vai por nome, nao so por id", "Solicitação de Cliente", TROCA["tipo_nome"])
checar("problema vai por nome", "MANUTENÇÃO", TROCA["problema_nome"])
checar("so a com troca usa recipiente", (None, "-MANUT"),
       (LOCAL.get("placa_teste_sufixo"), TROCA.get("placa_teste_sufixo")))
checar("no local le o modelo da propria placa", "placa", LOCAL["modelo_origem"])
checar("com troca le o modelo do recipiente", "placa_teste", TROCA["modelo_origem"])
checar("so a com troca libera serie", (None, True),
       (LOCAL.get("liberar_serie"), TROCA.get("liberar_serie")))
# 🚨 As 14 OS de manutencao abertas na mao terminam com `O.S: nnnnn`. Custa uma
# SEGUNDA chamada -- por isso NENHUM perfil de contrato faz, decisao de 14/07.
checar("as duas gravam o numero na descricao", (True, True),
       (LOCAL["numero_na_descricao"], TROCA["numero_na_descricao"]))
checar("nenhum perfil de contrato grava o numero", [],
       [k for k, p in templates_config.PERFIS.items()
        if p.get("numero_na_descricao") and not p.get("sem_termo")])

# ── 2. a chave do recipiente ─────────────────────────────────────────────────
# 🚨 O ESPACO PODE ESTAR EM QUALQUER LUGAR, mesmo com o apelido padronizado.
print("\n[2] chave do recipiente — espaço em qualquer lugar")
esperada = "GJN8689-MANUT"
for grafia in ("GJN8689", "GJN 8689", " GJN8689 ", "gjn 8689", "G J N 8 6 8 9"):
    checar(f"{grafia!r} vira a mesma chave", esperada,
           equipamentos.chave_recipiente(grafia, "-MANUT"))
# ⚠️ A TRAVA: a placa original inteira tem de bater. Digito a menos nao casa.
checar("placa truncada NAO gera a mesma chave", False,
       equipamentos.chave_recipiente("GJN868", "-MANUT") == esperada)
checar("placa vazia nao inventa chave", "",
       equipamentos.chave_recipiente("   ", "-MANUT"))
checar("chassi tambem serve de base", "HCCZTL80HNCJ51769-MANUT",
       equipamentos.chave_recipiente("HCCZTL80HNCJ51769", "-MANUT"))

# ── 3. o acento ──────────────────────────────────────────────────────────────
# 🚨 Os 5 recipientes da WESO estao gravados `MANUTENCAO`; o usuario padroniza
# escrevendo `MANUTENÇÃO`. Sem dobrar acento, TODA geracao morreria em 400.
print("\n[3] acento dobrado")
checar("MANUTENÇÃO == MANUTENCAO", True,
       os_router._norm_desc("MANUTENÇÃO") == os_router._norm_desc("MANUTENCAO"))
checar("minuscula acentuada tambem casa", True,
       os_router._norm_desc(" manutenção ") == os_router._norm_desc("MANUTENCAO"))
checar("nao casa com outra palavra", False,
       os_router._norm_desc("MANUTENCAO") == os_router._norm_desc("TERMO 8820"))

# ── 4. descarte do recipiente duvidoso ───────────────────────────────────────
# 🚨 SEM ENTRARA PLAUSIVEL, NAO INVENTA: descarta, avisa, e a OS sai com o
# marcador. Nenhum caso descarta em silencio.
print("\n[4] recipiente duvidoso é descartado, sempre com aviso")
body = _Body([_Placa("GJN 8689", "VW 24.280")])

bons, avisos = os_router._conferir_recipientes(body, TROCA, {})
checar("ausente: nenhum recipiente aproveitado", 0, len(bons))
checar("ausente: gerou 1 aviso", 1, len(avisos))
checar("ausente: o aviso diz o que vai sair", True,
       equipamentos.MARCADOR_SERIE_A_PREENCHER in avisos[0])

bons, avisos = os_router._conferir_recipientes(
    body, TROCA, {"GJN8689": {"ambiguo": ["GJN8689-MANUT", "GJN 8689-MANUT"]}})
checar("ambiguo: descartado", 0, len(bons))
checar("ambiguo: avisa que nao escolhe sozinho", True, "mbigu" in avisos[0])

bons, avisos = os_router._conferir_recipientes(
    body, TROCA, {"GJN8689": {"descricao": "TERMO 8820", "serie": "007560668"}})
checar("descricao de outra rodada: descartado", 0, len(bons))

bons, avisos = os_router._conferir_recipientes(
    body, TROCA, {"GJN8689": {"descricao": "MANUTENCAO", "serie": None}})
checar("sem serie: descartado", 0, len(bons))

bom = {"GJN8689": {"descricao": "MANUTENÇÃO", "serie": "007560668",
                   "modelo": "Suntech ST310", "veiculo_id": 88202,
                   "rastreador_id": 14036}}
bons, avisos = os_router._conferir_recipientes(body, TROCA, bom)
checar("recipiente certo passa (mesmo com acento)", 1, len(bons))
checar("recipiente certo nao gera aviso", 0, len(avisos))

# ── 5. o que sai na descrição e nos materiais ────────────────────────────────
print("\n[5] descrição e materiais")
checar("com recipiente, a serie que entra e a do recipiente", "007560668",
       os_router._serie_que_entra(TROCA, bons, "GJN 8689"))
# 🚨 marcador do ENTRARA e `NUMERO DE SERIE` (o tecnico preenche), nao
# `serie nao localizada` (que significa "nao sei o que esta la").
checar("sem recipiente, sai o marcador de preencher",
       equipamentos.MARCADOR_SERIE_A_PREENCHER,
       os_router._serie_que_entra(TROCA, {}, "GJN 8689"))
checar("no local nao tem 'entrara' nenhum", "",
       os_router._serie_que_entra(LOCAL, {}, "GJN 8689"))
checar("modelo do que entra vem do recipiente", "Suntech ST310",
       os_router._modelo_da_operacao(TROCA, "GJN 8689", [], bons))
checar("sem recipiente, modelo e o marcador", equipamentos.MARCADOR_MODELO,
       os_router._modelo_da_operacao(TROCA, "GJN 8689", [], {}))
# 🚨 sem modelo nao ha produto, entao o equipamento NAO entra nos materiais.
checar("sem recipiente nao entra material de equipamento", None,
       os_router._material_do_equipamento(TROCA, "GJN 8689", [], {}))

checar("o template do no local nao cita termo", False,
       "{termo}" in LOCAL["descricao_template"])
checar("o template da troca nao cita termo", False,
       "{termo}" in TROCA["descricao_template"])
checar("a troca diz SAIRÁ e ENTRARÁ", True,
       "SAIRÁ" in TROCA["descricao_template"] and "ENTRARÁ" in TROCA["descricao_template"])

# ── 6. o item que vai nas duas OS ────────────────────────────────────────────
# 🚨 Termo 8839 real: "Central 24 horas" vem CONTRATADO com R$ 10,00, cai em
# cobranca e some da OS que o tecnico le.
print("\n[6] item nas duas OS")
itens = [
    {"descricao": "CENTRAL 24 HORAS", "harmonit_id": 6976, "quantidade": 1,
     "valor_unitario": 10.0, "comodato": False, "cobrar": True, "nas_duas": True},
    {"descricao": "ADESAO", "harmonit_id": 21122, "quantidade": 1,
     "valor_unitario": 150.0, "comodato": False, "cobrar": True, "nas_duas": False},
    {"descricao": "RASTREADOR", "harmonit_id": 20314, "quantidade": 1,
     "valor_unitario": 1100.0, "comodato": True, "cobrar": False, "nas_duas": False},
]
copias = os_router._duplicar_nas_duas(itens, 1)
checar("so o item marcado e copiado", ["CENTRAL 24 HORAS"],
       [c["descricao"] for c in copias])
checar("a copia nao cobra e nao e comodato", (False, False),
       (copias[0]["cobrar"], copias[0]["comodato"]))
# 🚨 valor zero: o preco ja esta contado na financeira, e valor repetido nas
# duas OS vira soma dobrada no primeiro relatorio que alguem montar.
checar("a copia vai com valor zero", 0.0, copias[0]["valor_unitario"])
checar("o original continua cobrando", True, itens[0]["cobrar"])
checar("item comodato nao vira copia", 0,
       len(os_router._duplicar_nas_duas([itens[2]], 1)))

# ── 7. a liberação da série ──────────────────────────────────────────────────
# 🚨 SO DEPOIS DE TUDO CERTO. Falhou uma das tres provas, o recipiente fica.
print("\n[7] liberação da série — as três provas")


def _liberar(op, criada, recipientes=None):
    return asyncio.run(os_router._liberar_series(
        TROCA, [op], [criada], recipientes if recipientes is not None else bons))


op_bom = {"placa": "GJN 8689",
          "descricao": "MANUTENÇÃO COM TROCA: GJN 8689 | ENTRARÁ: 007560668",
          "materiais": [{"descricao": "ST310U", "_equipamento": True}]}
criada_boa = {"ok": True, "materiais_ok": ["ST310U"], "materiais_erro": []}

r = _liberar(op_bom, {"ok": False, "erro": "500"})
checar("OS que falhou nao libera", False, r[0]["ok"])
checar("e diz o motivo", True, "não foi criada" in r[0]["erro"])

op_sem_serie = {**op_bom,
                "descricao": f"MANUTENÇÃO COM TROCA: GJN 8689 | ENTRARÁ: "
                             f"{equipamentos.MARCADOR_SERIE_A_PREENCHER}"}
r = _liberar(op_sem_serie, criada_boa)
checar("descricao sem serie nao libera", False, r[0]["ok"])

r = _liberar({**op_bom, "materiais": []}, criada_boa)
checar("sem material de equipamento nao libera", False, r[0]["ok"])

r = _liberar(op_bom, {"ok": True, "materiais_ok": [], "materiais_erro": ["ST310U: 500"]})
checar("material recusado pelo Harmonit nao libera", False, r[0]["ok"])
checar("e devolve os numeros para corrigir na mao", 88202,
       r[0]["dados_para_correcao"]["veiculo_id"])

checar("perfil sem liberar_serie nao libera nada", [],
       asyncio.run(os_router._liberar_series(LOCAL, [op_bom], [criada_boa], bons)))
checar("sem recipiente nao ha o que liberar", [],
       asyncio.run(os_router._liberar_series(TROCA, [op_bom], [criada_boa], {})))

# ── 8. o item que vai nas duas chega em TODAS as placas ──────────────────────
# 🚨 DEFEITO REAL, achado auditando em 14/08. A copia passava pela alocacao
# normal, que distribui pela quantidade do CONTRATO: um termo que lista a
# Central como uma linha so fazia a copia chegar em UM veiculo, com os outros
# 99 sem nada e sem aviso. A regra do usuario e "em todos os veiculos".
print("\n[8] a cópia cobre a frota, não a quantidade do contrato")
from fpsl_weso.painel.routers.os_router import PlacaInput, _alocar_itens_por_placa  # noqa: E402


def _quantos_receberam(qtd_contrato, n_placas):
    itens = [{"descricao": "CENTRAL 24 HORAS", "harmonit_id": 6976,
              "quantidade": qtd_contrato, "valor_unitario": 10.0,
              "comodato": False, "cobrar": True, "nas_duas": True}]
    copias = os_router._duplicar_nas_duas(itens, n_placas)
    placas = [PlacaInput(placa=f"AAA{i:04d}", veiculo="") for i in range(n_placas)]
    alocacao, _ = _alocar_itens_por_placa(copias, placas)
    return sum(1 for lista in alocacao
               if any(m["descricao"] == "CENTRAL 24 HORAS" for m in lista))


checar("qtd do contrato = nº de placas", 100, _quantos_receberam(100, 100))
checar("qtd 1 para 100 placas chega nas 100", 100, _quantos_receberam(1, 100))
checar("qtd 5 para 100 placas chega nas 100", 100, _quantos_receberam(5, 100))
checar("1 placa continua sendo 1", 1, _quantos_receberam(1, 1))
# a cobranca na financeira NAO e mexida -- so a copia de referencia
checar("o original preserva a quantidade do contrato", 1,
       [{"descricao": "X", "quantidade": 1, "valor_unitario": 10.0,
         "comodato": False, "cobrar": True, "nas_duas": True}][0]["quantidade"])

# ── 9. nenhuma função chamada no JS pode estar faltando ──────────────────────
# 🚨 ESTA É A CLASSE DE ERRO QUE DERRUBOU A TELA. `extrair()` chamava
# `renderPlacas()` e `validarEtapa2()`, que nunca existiram: clicar em
# "Gerar OS" lançava ReferenceError e o fluxo parava antes de trocar de etapa.
# `node --check` não pega -- ele valida sintaxe, e a sintaxe estava correta.
print("\n[9] o JavaScript das telas não chama função inexistente")
import re  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
# Definidas fora do <script> da própria página (sidebar.js e afins).
EXTERNAS = {"montarSidebar"}
NATIVAS = {
    "if", "for", "while", "switch", "catch", "return", "typeof", "function",
    "await", "new", "else", "do", "try", "fetch", "parseInt", "parseFloat",
    "alert", "confirm", "setInterval", "clearInterval", "setTimeout",
    "clearTimeout", "encodeURIComponent", "decodeURIComponent", "isNaN",
    "String", "Number", "Boolean", "Array", "Object", "JSON", "Math", "Date",
    "Promise", "Set", "Map", "Error", "RegExp", "FormData", "URLSearchParams",
}


def _sem_texto(src):
    """Tira comentários e literais de string numa passada só.

    ⚠️ Regex não serve aqui: `//` mora dentro de string ('https://...') e aspa
    mora dentro de comentário. Tirar um antes do outro deixa lixo, e foi por
    isso que a primeira versão deste teste acusou 'oculto' e 'var' -- palavras
    de prosa dentro de `'...oculto (não vira material)...'` e de
    `'border:1px solid var(--border)'`. Teste com falso positivo é teste que
    alguém desliga.

    🚨 REGEX LITERAL TAMBÉM PRECISA SAIR. `escapeHtml` tem `.replace(/"/g, ...)`
    e `.replace(/'/g, ...)`: as aspas soltas dentro do regex abriam uma string
    que só fechava páginas depois, e a partir dali tudo saía trocado. Foi o que
    fez este teste acusar `var` em `color:var(--text2)`.
    """
    # Uma barra inicia regex quando vem depois de operador/abertura; depois de
    # identificador ou `)` ela é divisão. É a heurística padrão, e basta aqui.
    ANTES_DE_REGEX = "(,=:[!&|?{};+-*%~^\n"
    saida, i, n = [], 0, len(src)
    anterior = ""
    while i < n:
        c = src[i]
        if c in "'\"`":  # literal de string
            aspa, i = c, i + 1
            while i < n and src[i] != aspa:
                i += 2 if src[i] == "\\" else 1
            i += 1
            saida.append('""')
            anterior = '"'
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            fim = src.find("*/", i + 2)
            i = n if fim == -1 else fim + 2
        elif c == "/" and (anterior in ANTES_DE_REGEX or anterior == ""):
            i += 1
            while i < n and src[i] != "/":
                i += 2 if src[i] == "\\" else 1
            i += 1
            while i < n and src[i] in "gimsuy":  # flags
                i += 1
            saida.append(" ")
            anterior = "/"
        else:
            saida.append(c)
            if not c.isspace() or c == "\n":
                anterior = c
            i += 1
    return "".join(saida)


def _orfas(caminho):
    html = caminho.read_text(encoding="utf-8")
    src = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    definidas = set(re.findall(r"(?:async\s+)?function\s+(\w+)", src))
    definidas |= set(re.findall(r"(?:const|let|var)\s+(\w+)", src))
    limpo = _sem_texto(src)
    # só chamadas sem ponto antes: `f(` conta, `obj.f(` não
    chamadas = set(re.findall(r"(?<![.\w$])([a-z_][A-Za-z0-9_]*)\s*\(", limpo))
    return sorted(chamadas - definidas - EXTERNAS - NATIVAS)


for pagina in ("gerar_os.html", "vinculos.html"):
    checar(f"{pagina}: nenhuma chamada órfã", [], _orfas(RAIZ / "frontend" / pagina))

# O detector precisa PEGAR o defeito, não só passar quando está tudo certo.
_falso = "function a(){ b(); }"
checar("o detector acha chamada inexistente", True,
       "b" in re.findall(r"(?<![.\w$])([a-z_][A-Za-z0-9_]*)\s*\(", _sem_texto(_falso)))
checar("o detector ignora palavra dentro de string", "",
       _sem_texto("'oculto (nao vira material)'").strip().strip('"'))

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
