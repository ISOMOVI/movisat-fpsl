"""
Extração de campos do PDF do contrato/distrato -- baseado em regra, sem IA.

Reescrito em 2026-07-15 pra extração POR PERFIL, depois de auditar 7 documentos
reais (1 de cada tipo + variações) e confirmar que os 6 perfis têm formatos de
tabela genuinamente diferentes -- uma heurística única (a versão anterior,
validada só contra 1 Distrato simples) não cobre nenhum dos outros 5 tipos
corretamente.

Ainda sem IA -- tudo por regex/posição de tabela. Cliente sugerido e CNPJ
continuam heurística frágil, sempre tratar como pré-preenchido, nunca como
confirmação automática.
"""
import re
import unicodedata
import pdfplumber

from .. import placas

_TERMO_RE = re.compile(r"(?:Distrato|Termo|Contrato|Documento)\s*n[ºo°]?\s*[:.]?\s*(\d+)", re.IGNORECASE)
_PLACA_RE = re.compile(r"\b([A-Z]{3})[\s\-]?(\d[A-Z0-9]\d{2})\b")

# 🚨 A MESMA PLACA, MAS SEM ATRAVESSAR QUEBRA DE LINHA -- só para o fallback
# de texto corrido.
#
# Dentro de uma CÉLULA de tabela, `\s` casando com `\n` é o comportamento
# certo: `FIAT/STRADA - RFD\n0E02` é uma placa que quebrou dentro da célula.
#
# No TEXTO ACHATADO da página é o oposto. As colunas viram linhas
# intercaladas, e o número da coluna "DOCUMENTO REFERÊNCIA" cai ENTRE as duas
# metades da placa. Em 07/08 isso produziu `RFD 2447` e `FMS 3078` no termo
# 8800 -- placas que não existem na WESO -- no lugar de `RFD 0E02` e
# `FMS 3J88`. Sem erro e sem aviso.
#
# Placa inventada é pior que placa faltando: a que falta alguém percebe.
_PLACA_RE_MESMA_LINHA = re.compile(r"\b([A-Z]{3})[ \t\-]?(\d[A-Z0-9]\d{2})\b")

# Placa FANTASMA: 'FIAT/UNO 2019' casa no regex acima -- UNO sao 3 letras e
# 2019 tem o formato do padrao antigo (LLL NNNN). Estruturalmente E placa
# valida; so o CONTEXTO distingue. Nao ocorre nos 9 termos reais (la vem
# 'VW/SAVEIRO, CARGA CAMINHONETE 2026/2027'), mas basta um termo escrever o
# modelo em 3 letras seguido do ano: UNO, GOL, KA.
# Sinal: vir logo apos '/' (notacao MARCA/MODELO) E a parte numerica ser ano
# plausivel. Placa de verdade nao aparece precedida de barra.
_ANO_RE = re.compile(r"^(19|20)[0-9]{2}$")


def _eh_placa_fantasma(texto, m):
    """True quando o casamento e nome de modelo + ano, nao placa."""
    if not _ANO_RE.match(m.group(2)):
        return False
    return texto[:m.start()].rstrip().endswith("/")
_CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
_CPF_RE = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
_VALOR_RE = re.compile(r"R\$\s*([\d\.]+(?:,\d{2})?)")  # centavos opcionais -- "R$ 250" sem vírgula existe

# "da {RAZÃO SOCIAL}" -- só aparece no texto corrido de Rescisão/Transferência
# ("Eu Fulano, da EMPRESA LTDA, conforme..."). Cliente Novo/Aditivo/Substituição
# não têm esse texto -- usam _CABECALHO_TABELA_RE abaixo.
_CLIENTE_PROSA_RE = re.compile(
    r"\bda\s+([A-ZÀ-Ú][A-ZÀ-Ú0-9\s\.&\-]{4,90}?(?:LTDA|EIRELI|\bME\b|\bEPP\b|S\.?A\.?))\b"
)
_RESPONSAVEL_RE = re.compile(r"\bEu\s+([A-ZÀ-Úa-zà-ú][A-Za-zÀ-ú\s]{2,60}?),\s*da\b")

# Cabeçalho da página de item/veículo: "{RAZÃO SOCIAL}\nCNPJ: X | Contrato/
# Documento nº: Y" -- fonte MUITO mais confiável que regex em texto corrido,
# usada em Cliente Novo, Aditivo, Upgrade e Substituição (todas têm essa
# mesma página de tabela de item, só o texto de contrato ao redor muda).
_CABECALHO_TABELA_RE = re.compile(
    r"([A-ZÀ-Ú][A-ZÀ-Ú0-9\s\.,&\-]{3,90}?)\s*\n\s*CNPJ:\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})"
    r"\s*\|\s*(?:Contrato|Documento)\s*n[ºo°]?:?\s*(\d+)",
)

# Frases que indicam que um documento (tipicamente Rescisão) é na verdade o
# lado de origem de uma transferência de titularidade pra outro cliente --
# achado real auditando "termo errado.pdf" (Distrato 8787): título e forma são
# de Rescisão, mas o conteúdo é uma transferência disfarçada (R$0,00, veículo
# "passará a fazer parte" de outro contrato).
_TRANSFERENCIA_FRASES = [
    re.compile(r"passar[áa]\s+a\s+fazer\s+parte\s+do\s+contrato\s*n[ºo°]?\s*\d+", re.IGNORECASE),
    re.compile(r"outra\s+titularidade", re.IGNORECASE),
    re.compile(r"transferid[oa]\s+(?:do|para o?)\s+contrato\s*n[ºo°]?\s*\d+", re.IGNORECASE),
    # lado NOVO titular (formato Cliente Novo): nota "Transferência de
    # titularidade do contrato 3622 do cliente SWM..." na coluna Tipo do item.
    # "n" opcional -- essa nota vem "contrato 3622" (sem o "nº").
    re.compile(r"titularidade\s+do\s+contrato\s*n?[ºo°]?\s*\d+", re.IGNORECASE),
]

# Nº do contrato CRUZADO citado na frase de transferência -- o "outro lado" do
# termo (posterior pro antigo titular, anterior pro novo). Vai pra descrição da OS.
_TERMO_RELACIONADO_RE = re.compile(r"contrato\s*n?[ºo°]?\s*[:.]?\s*(\d+)", re.IGNORECASE)

# Marca, dentro da descrição livre de um veículo, que ele NÃO recebe bloqueio
# -- achado em cliente novo2.pdf: 28 veículos, só 11 "Bloqueio veicular"
# comprados, e a marcação de quem recebe está no texto do próprio veículo
# ("***...SEM BLOQUEIO***"), não é "os N primeiros da lista".
_SEM_BLOQUEIO_RE = re.compile(r"SEM\s+BLOQUEIO", re.IGNORECASE)


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(s.strip().upper().split())


_RD_RE = re.compile(r"\(\s*RD\s*\)", re.IGNORECASE)


# Placa ainda nao definida no termo vem como "A DEFINIR". Formato decidido pelo
# usuario em 2026-07-29: a placa vira A_DEFINIR_<termo> (unica por termo, nao
# colide entre contratos) e o nome do veiculo no Harmonit / apelido na WESO
# vira TERMO:<termo>. Ja existe convencao de fato na base -- 'TERMO:8396'
# aparece 4x e 'TERMO 8222' tambem (ver docs/fpsl/21_Plano_Higiene_Placas.md).
_A_DEFINIR_RE = re.compile(r"^A[\s_]*DEFINIR", re.I)


def _aplicar_placeholder_termo(campos: dict) -> dict:
    """Troca 'A DEFINIR' pelo formato definitivo em TODAS as listas de veiculo
    do resultado, seja qual for o perfil.

    Aplicado no despachante (extrair_campos) e nao dentro de cada parser: sao
    tres parsers com nomes de variavel diferentes (`placas`, `veiculos`,
    `pares`), e colocar a chamada em um deles ja causou NameError em 29/07 --
    o py_compile passa e so o teste pega. Um lugar so, uma vez.

    Sem numero de termo, deixa como esta: inventar sufixo seria pior que
    manter o texto original.
    """
    termo = campos.get("termo")
    if not termo:
        return campos

    def _trocar(v: dict, chave: str) -> None:
        val = v.get(chave)
        if val and _A_DEFINIR_RE.match(str(val).strip()):
            v[chave] = f"A_DEFINIR_{termo}"
            v["apelido_sugerido"] = f"TERMO:{termo}"
            v["placa_convencional"] = False

    for lista in ("placas", "veiculos", "pares"):
        for v in campos.get(lista) or []:
            if not isinstance(v, dict):
                continue
            _trocar(v, "placa")
            _trocar(v, "placa_saida")
            _trocar(v, "placa_entrada")
    return campos


def _placa_formatada(contexto: str, m) -> str:
    """Placa normalizada, PRESERVANDO o marcador (RD) de REDUNDÂNCIA quando ele
    aparece coladinho à placa -- antes ('(RD) CUB 0764') ou depois ('CUB 0764
    (RD)'). O (RD) distingue um 2º equipamento legítimo no MESMO veículo de uma
    placa duplicada por erro: na WESO 'CUB 0764' e 'CUB 0764 (RD)' são dois
    registros (dois rastreadores), e cada um vira sua OS. Só conta o (RD) ENTRE
    PARÊNTESES numa janela colada ao match -- 'DRD 4189' tem RD nas letras da
    placa (não é redundância), e um (RD) distante no texto pertence a outra placa.
    `contexto` tem que ser a MESMA string em que `m` foi casado (offsets de m)."""
    placa = f"{m.group(1)} {m.group(2)}"
    ctx = contexto or ""
    janela = ctx[max(0, m.start() - 8):m.end() + 8]
    # padrão de 2026-07-27: marcador ANTES da placa. Antes daqui saía
    # 'CUB 0764 (RD)'; a base da WESO foi toda padronizada pra '(RD) CUB 0764',
    # e o de-para só casa se os dois lados falarem a mesma língua.
    return placas.montar(placa, tem_rd=bool(_RD_RE.search(janela)))


def _tem_header(header: list[str], *termos: str) -> bool:
    return any(any(t in h for t in termos) for h in header)


def _achar_linha_header(tabela: list, *termos: str, min_ocorrencias: int = 1) -> tuple[int, list[str]] | None:
    """Várias tabelas têm uma linha de título mesclada ANTES do cabeçalho de
    verdade (ex: 'SISTEMA: MOVISAT MANAGER 2.0' cobrindo a largura toda, ou
    'VEÍCULOS QUE SAIRÃO DO CONTRATO' na Substituição) -- não dá pra assumir
    que tabela[0] é sempre o cabeçalho real. Escaneia as primeiras linhas e
    usa a que tem mais colunas batendo nos termos buscados."""
    melhor: tuple[int, list[str], int] | None = None
    for idx, linha in enumerate(tabela[:4]):
        header = [_normalizar(str(c or "")) for c in linha]
        ocorrencias = sum(1 for h in header if any(t in h for t in termos))
        if ocorrencias >= min_ocorrencias and (melhor is None or ocorrencias > melhor[2]):
            melhor = (idx, header, ocorrencias)
    if melhor is None:
        return None
    return melhor[0], melhor[1]


def _achar_linha_header_com_todos(tabela: list, *grupos: str) -> tuple[int, list[str]] | None:
    """Variante que exige cada termo de `grupos` presente em ALGUMA coluna
    (E, não OU) -- usada pra tabela de rescisão, que precisa de PLACA e
    VEICULO como conceitos distintos na mesma linha, não só '2 ocorrências
    quaisquer' (isso deixava o achador pegar uma linha errada quando só
    'VEICULO' aparecia 2x em vez de PLACA+VEICULO 1x cada)."""
    for idx, linha in enumerate(tabela[:4]):
        header = [_normalizar(str(c or "")) for c in linha]
        if all(any(g in h for h in header) for g in grupos):
            return idx, header
    return None


def _ler_paginas(fonte) -> list[dict]:
    paginas = []
    with pdfplumber.open(fonte) as pdf:
        for pagina in pdf.pages:
            paginas.append({
                "texto": pagina.extract_text() or "",
                "tabelas": pagina.extract_tables() or [],
            })
    return paginas


def _detectar_transferencia(texto: str) -> str | None:
    for padrao in _TRANSFERENCIA_FRASES:
        m = padrao.search(texto)
        if m:
            inicio = max(0, m.start() - 40)
            fim = min(len(texto), m.end() + 40)
            return texto[inicio:fim].strip().replace("\n", " ")
    return None


def _termo_relacionado(texto: str) -> str | None:
    """Nº do contrato do OUTRO lado da transferência de titularidade, lido de
    dentro da frase de transferência detectada (pra não pegar um 'contrato'
    qualquer do texto). Ex.: antigo 8581 -> '8580' (posterior); novo 8580 ->
    '3622' (anterior). None quando não é transferência."""
    frase = _detectar_transferencia(texto)
    if not frase:
        return None
    m = _TERMO_RELACIONADO_RE.search(frase)
    return m.group(1) if m else None


def _extrair_cliente_cabecalho_tabela(texto: str) -> tuple[str | None, str | None, str | None]:
    """Retorna (nome, cnpj, termo) a partir do cabeçalho da página de item.
    Fonte mais confiável que regex em texto corrido -- usar sempre que a
    página tiver esse formato (Cliente Novo, Aditivo, Upgrade, Substituição)."""
    m = _CABECALHO_TABELA_RE.search(texto)
    if not m:
        return None, None, None
    nome = " ".join(m.group(1).split())  # razão social pode quebrar em 2 linhas no PDF
    return nome, m.group(2), m.group(3)


def _extrair_ficha_cadastral(tabelas: list) -> tuple[str | None, str | None]:
    """Página 1 do Cliente Novo tem uma 'Ficha Cadastral' com Razão Social e
    CNPJ em tabela chave-valor. Só usada como apoio pra busca de cliente na
    Etapa 2 -- nenhum outro dado dessa página entra na OS."""
    razao_social, cnpj = None, None
    for tabela in tabelas:
        for linha in tabela:
            for i, cel in enumerate(linha):
                rotulo = _normalizar(str(cel or ""))
                if rotulo == "RAZAO SOCIAL" and i + 1 < len(linha):
                    razao_social = " ".join(str(linha[i + 1] or "").split())  # célula pode quebrar em 2 linhas
                if rotulo == "CNPJ" and i + 1 < len(linha):
                    m = _CNPJ_RE.search(str(linha[i + 1] or ""))
                    if m:
                        cnpj = m.group(0)
    return razao_social, cnpj


def _extrair_itens_tabela_padrao(tabela: list, header: list[str], primeira_linha_dado: int) -> list[dict]:
    """Tabela 'Descrição dos serviços e acessórios' (Cliente Novo/Aditivo/
    Upgrade) OU tabela 'Acessórios' (Rescisão) -- cabeçalhos diferentes,
    mesma forma de dado. Reconhece os dois."""
    idx_qtd = next((i for i, h in enumerate(header) if "QUANTIDADE" in h or h == "QTD"), None)
    idx_desc = next((i for i, h in enumerate(header) if any(t in h for t in ("ACESSORIO", "ITEM", "DESCRICAO"))), None)
    idx_valor = next((i for i, h in enumerate(header) if "VALOR" in h), None)
    idx_comodato = next((i for i, h in enumerate(header) if "COMODATO" in h or "AQUISICAO" in h or h == "TIPO"), None)
    idx_devolvido = next((i for i, h in enumerate(header) if "DEVOLV" in h), None)

    itens = []
    if idx_desc is None:
        return itens
    for linha in tabela[primeira_linha_dado:]:
        if idx_desc >= len(linha):
            continue
        descricao = str(linha[idx_desc] or "").replace("\n", " ").strip()
        if not descricao:
            continue
        valor_txt = str(linha[idx_valor] or "") if idx_valor is not None and idx_valor < len(linha) else ""
        m_valor = _VALOR_RE.search(valor_txt)
        itens.append({
            "descricao": descricao,
            "quantidade": str(linha[idx_qtd] or "").strip() if idx_qtd is not None and idx_qtd < len(linha) else None,
            "valor_unitario": m_valor.group(1) if m_valor else None,
            "comodato_ou_aquisicao": str(linha[idx_comodato] or "").replace("\n", " ").strip() if idx_comodato is not None and idx_comodato < len(linha) else None,
            "sera_devolvido": str(linha[idx_devolvido] or "").strip().upper() if idx_devolvido is not None and idx_devolvido < len(linha) else None,
        })
    return itens


# ── Perfil: Cliente Novo / Aditivo / Upgrade ──────────────────────────────────
# Mesma forma de página de item+veículo nos 3 -- só Cliente Novo tem Ficha
# Cadastral antes. Tabela de veículo é 1 coluna mesclada ("Veículo e Placa ou
# Chassis do veículo"), não 2 colunas separadas.

_ITENS_KEYS = ("ACESSORIO", "QUANTIDADE", "QTD", "VALOR", "CONDICAO",
               "COMODATO", "DEVOLV", "PAGAMENTO", "TOTAL", "TIPO")


def _eh_continuacao_tabela(tabela: list, n_cols: int, idxs_conteudo: list[int]) -> bool:
    """A tabela é a continuação de uma lista que quebrou de página?

    Quando a lista de veículos passa de uma página, a parte de baixo vem numa
    tabela SEM cabeçalho -- e o achador de header a ignora, sumindo com as
    placas seguintes sem erro nenhum. Reconhece por: mesmo nº de colunas da
    tabela original, NÃO parecer tabela de itens, e ter conteúdo em alguma das
    colunas de placa.

    Versão genérica da `_eh_continuacao_veiculo_rescisao`, que resolvia isso só
    na Rescisão desde 2026-07-23.
    """
    larguras = [len(r) for r in tabela if r]
    if not larguras or max(larguras) != n_cols:
        return False
    for linha in tabela[:2]:
        for cel in linha:
            if any(k in _normalizar(str(cel or "")) for k in _ITENS_KEYS):
                return False
    for linha in tabela:
        for idx in idxs_conteudo:
            if idx < len(linha) and str(linha[idx] or "").strip():
                return True
    return False


#  Um cabeçalho de coluna é um TÍTULO ("VEÍCULOS A MIGRAR", 17 caracteres),
#  não um parágrafo. No termo 8800 a coluna de descrição do plano começa com
#  "Após a migração os VEÍCULOS migrados passarão a operar..." -- e casava como
#  coluna de veículo, arrastando "PLANO PRÓ Troca de equipamento 2G para 4G"
#  para a lista de itens sem placa. O teto separa título de texto corrido.
_MAX_TITULO_COLUNA = 40


def _colunas_de_veiculo(header: list[str]) -> list[int]:
    """Índices das colunas cujo cabeçalho é REALMENTE um título de veículo.

    Se o teto descartar todas -- cabeçalho legitimamente longo --, devolve os
    candidatos originais: perder a coluna certa é pior que aceitar uma a mais.
    """
    candidatos = [i for i, h in enumerate(header) if "VEICULO" in h]
    curtos = [i for i in candidatos if len(_normalizar(str(header[i] or ""))) <= _MAX_TITULO_COLUNA]
    return curtos or candidatos


#  Só um RÓTULO EXPLÍCITO no documento autoriza tratar texto como
#  identificador de veículo. "SERIE 16994" e "Chassi:1BM6115J" dizem o que
#  são; texto solto não diz nada, e adivinhar a partir dele é como nasceu a
#  placa inventada `RFD 2447`.
_ROTULO_NAO_CONVENCIONAL = re.compile(
    r"\b(?:N[º°]?\s*)?(?:S[EÉ]RIE|CHASSIS?)\s*[:\-]?\s*(.+)$", re.IGNORECASE)


def _identificador_nao_convencional(celula: str) -> tuple[str | None, str, list[str]]:
    """(identificador, descrição do veículo, variantes) para máquina sem placa.

    🚨 AS VARIANTES EXISTEM PORQUE A WESO NÃO É COERENTE, e o termo tem que
    sair IDÊNTICO a ela. Medido no cache em 07/08:

        escavadeira -> WESO grava 'SERIE 16994'      (o rótulo FAZ parte)
        trator      -> WESO grava '1BM6115JJMD002601' (o rótulo NÃO faz parte)

    Adivinhar qual rótulo manter erraria metade dos casos, e erra em silêncio:
    placa que não casa não dá erro, só deixa de achar o veículo. Então aqui se
    emite as duas formas, e quem decide é a consulta à WESO -- que devolve a
    grafia oficial. Quem confronta com a WESO hoje é
    `painel.equipamentos._rastreador_id_por_placa` (o `placas_router`, que
    fazia essa conferência na tela, foi removido em 14/08).
    """
    texto = " ".join(str(celula or "").split())
    m = _ROTULO_NAO_CONVENCIONAL.search(texto)
    if not m:
        return None, "", []

    com_rotulo = " ".join(texto[m.start():].split()).strip(" -,;.")
    sem_rotulo = " ".join(m.group(1).split()).strip(" -,;.")
    if not re.search(r"[A-Za-z0-9]", sem_rotulo):
        return None, "", []

    veiculo = texto[:m.start()].strip(" -,;.*")
    variantes = []
    for v in (com_rotulo.upper(), sem_rotulo.upper()):
        if v and v not in variantes:
            variantes.append(v)
    # O primeiro é só o palpite inicial: a consulta à WESO troca pelo oficial.
    return variantes[0], " ".join(veiculo.split()), variantes


# ── o que vem depois do traco e a placa ─────────────────────────────────────

# Guarda medida nos 14 fixtures em 20/08. Nao e "conservadorismo": cada limite
# abaixo existe por causa de uma linha real que a medicao mostrou.
_POS_TRACO_MAX_TOKENS = 2      # 'RZL H405' tem 2; texto corrido tem 6+
_POS_TRACO_MIN_CHARS = 3       # abaixo disso é sobra de pontuação
_POS_TRACO_MAX_CHARS = 15      # cobre 'RZ.LH40.5' (9); chassi tem via própria

# 🚨 PONTUAÇÃO DE PLACA É BEM-VINDA, e é aqui que a placa estrangeira entra. A
# do termo 8846 é CHILENA -- 4 letras + 2 dígitos, escrita `RZ.LH40.5` -- e foi
# adaptada à força para o Mercosul por quem escreveu o termo. Exigir
# alfanumérico puro reprovaria a grafia original, que é restringir o FORMATO
# justamente onde a regra manda não restringir.
#
# ⚠️ Vírgula e parêntese ficam de fora porque são marca de fragmento de prosa,
# não de identificador de veículo.
_POS_TRACO_PONTUACAO = set(".-/")
_POS_TRACO_PROIBIDOS = set(",;()[]{}:\"'")


def _placa_pos_traco(celula: str) -> tuple[str | None, str]:
    """(identificador, descricao) quando o que vem depois do traco e a placa.

    🚨 REGRA DO USUARIO (20/08, termo 8846). A coluna se chama "Veiculo e Placa
    ou Chassis do veiculo": o que vem depois do `-` e o identificador, mesmo em
    formato nao convencional. O 8846 traz `NISSAN, 2022, DIESEL - RZL H405`, e
    `RZL H405` nao casa com nenhum padrao brasileiro -- nem o antigo
    (3 letras + 4 digitos) nem o Mercosul (3 letras + digito + letra + 2
    digitos). Existe na WESO com rastreador vinculado; e a placa daquele
    veiculo, e o painel recusava gerar a OS.

    ⚠️ RODA DEPOIS DO RECONHECIMENTO DE PLACA, NUNCA ANTES. Medido: 4 linhas
    dos fixtures tem placa E traco na descricao (`SEMI- REBOQUE`,
    `- (Veiculo transferido do contrato n 8665)`). Rodar antes roubaria a placa
    certa e poria lixo no lugar.

    🚨 E A GUARDA NAO E ZELO EXCESSIVO: sem ela, duas linhas de texto corrido
    que caem na tabela de veiculos do `transferencia_novo.pdf` virariam a placa
    `la tambem no contrato principal de`. Isso e o `RFD 2447` de novo -- dado
    plausivel apontando para lugar nenhum -- e a regra 13 existe para impedir.

    O que passa: no maximo 2 blocos, so letras e digitos ASCII, ao menos um
    digito, entre 5 e 12 caracteres. Texto corrido reprova pelo numero de
    blocos e pelo acento; sobra de pontuacao reprova pelo tamanho.
    """
    texto = " ".join(str(celula or "").split())

    # 🚨 O SEPARADOR É O TRAÇO COM ESPAÇO DOS DOIS LADOS, não qualquer traço.
    # Cortando no último traço, `VEICULO - AB-123-CD` devolvia `CD`: placa
    # estrangeira com hífen interno se parte no meio. O espaço é o que separa o
    # traço-separador do hífen que pertence ao texto:
    #
    #     `NISSAN, 2022, DIESEL - RZL H405`  separador, espaço dos dois lados
    #     `SR/FACCHINI SEMI- REBOQUE`        palavra quebrada, espaço só depois
    #     `AB-123-CD`                        hífen da própria placa, sem espaço
    if " - " not in texto:
        return None, ""

    cabeca, _, cauda = texto.rpartition(" - ")
    cauda = cauda.strip(" ,;*")
    # ⚠️ O ponto NÃO é removido da ponta: `RZ.LH40.5` termina em dígito, mas uma
    # placa chilena escrita `RZ.LH40.5.` perderia o formato. Só some ponto que
    # sobra sozinho no fim, depois de já haver conteúdo.
    while cauda.endswith(".") and cauda[:-1] and not cauda[:-1].endswith("."):
        if cauda[:-1][-1].isalnum():
            break
        cauda = cauda[:-1]
    if not cauda:
        return None, ""

    blocos = cauda.split()
    if len(blocos) > _POS_TRACO_MAX_TOKENS:
        return None, ""
    junto = "".join(blocos)
    if not (_POS_TRACO_MIN_CHARS <= len(junto) <= _POS_TRACO_MAX_CHARS):
        return None, ""
    # Só letras, dígitos e pontuação de placa. Vírgula e parêntese reprovam.
    if any(c in _POS_TRACO_PROIBIDOS for c in junto):
        return None, ""
    if not all(c.isalnum() or c in _POS_TRACO_PONTUACAO for c in junto):
        return None, ""
    # 🚨 O DÍGITO É O QUE REPROVA `também`. Identificador de veículo tem número;
    # palavra solta em português, não. Sem esta linha, a frase do
    # `transferencia_novo.pdf` volta a virar placa.
    if not any(c.isdigit() for c in junto):
        return None, ""
    if not any(c.isalpha() for c in junto):
        return None, ""

    return cauda.upper(), " ".join(cabeca.split()).strip(" -,;.*")


def _processar_linhas_placa(linhas: list, idx_placa_cols: list[int], placas: list[dict],
                            sem_placa: list[dict] | None = None) -> None:
    """Extrai placa+veículo das linhas de uma tabela de veículos.

    Separado de `_extrair_item_veiculo` pra poder ser reusado na continuação de
    página (P5) -- o mesmo motivo pelo qual a Rescisão tem
    `_processar_linhas_veiculo_rescisao`.

    🚨 `sem_placa` recebe a linha que TEM conteúdo de veículo e NÃO tem placa
    reconhecida -- máquina identificada por chassi ou número de série. Antes
    esses sumiam calados, e a tela mostrava "9 veículos" num termo de 11 sem
    nada indicar os 2 que faltavam. Item que o sistema não entende precisa
    APARECER: quem decide o que fazer com ele é gente.
    """
    for linha in linhas:
        for idx in idx_placa_cols:
            if idx >= len(linha):
                continue
            celula = str(linha[idx] or "").replace("\n", " ").strip()
            achou_nesta = False
            for m in _PLACA_RE.finditer(celula):
                if _eh_placa_fantasma(celula, m):
                    continue
                achou_nesta = True
                veiculo = (celula[:m.start()] + celula[m.end():])
                veiculo = _SEM_BLOQUEIO_RE.sub("", veiculo).strip(" -*")
                placas.append({
                    "placa": _placa_formatada(celula, m),
                    "veiculo": " ".join(veiculo.split()),
                    "sem_bloqueio": bool(_SEM_BLOQUEIO_RE.search(celula)),
                    "nota_transferencia": _detectar_transferencia(celula),
                })

            if achou_nesta or len(celula) <= 3:
                continue

            # 🚨 MÁQUINA IDENTIFICADA POR SÉRIE OU CHASSI É VEÍCULO DO TERMO,
            # e ENTRA na geração -- mesma regra que a Rescisão já aplicava:
            # "não é mais 'sem placa': é placa fora do padrão convencional.
            # Serve para destacar na revisão, nunca para excluir da geração."
            #
            # No termo 8800 são 2 de 11: uma mini escavadeira (SÉRIE 16994) e
            # um trator (Chassi 1BM6115J JMD002601). Deixá-los de fora fazia a
            # tela dizer "9 veículos" num termo de 11.
            identificador, veiculo, variantes = _identificador_nao_convencional(celula)
            if identificador:
                placas.append({
                    "placa": identificador,
                    "veiculo": veiculo,
                    "sem_bloqueio": bool(_SEM_BLOQUEIO_RE.search(celula)),
                    "nota_transferencia": _detectar_transferencia(celula),
                    # ⚠️ Falso aqui faz a tela destacar para conferência visual:
                    # errar a leitura de um nº de série é mais fácil que errar
                    # uma placa Mercosul.
                    "placa_convencional": False,
                    # Formas alternativas para a consulta à WESO adotar a
                    # grafia oficial -- ver `_identificador_nao_convencional`.
                    "placa_variantes": variantes,
                })
                continue

            # 🆕 O QUE VEM DEPOIS DO TRAÇO É A PLACA (decisão do usuário,
            # 20/08). A coluna se chama "Veículo e Placa ou Chassis do
            # veículo", e o identificador vem ali -- inclusive fora do padrão
            # brasileiro, como o `RZL H405` do termo 8846, que existe na WESO
            # com rastreador vinculado e mesmo assim travava a geração.
            #
            # ⚠️ Vem DEPOIS do reconhecimento normal e do rótulo de
            # série/chassi, de propósito: só decide o que sobrou.
            identificador, veiculo = _placa_pos_traco(celula)
            if identificador:
                placas.append({
                    "placa": identificador,
                    "veiculo": veiculo,
                    "sem_bloqueio": bool(_SEM_BLOQUEIO_RE.search(celula)),
                    "nota_transferencia": _detectar_transferencia(celula),
                    # Destaca na tela para conferência visual, como já se faz
                    # com série e chassi -- não muda o tratamento.
                    "placa_convencional": False,
                })
                continue

            # ⚠️ Sobrou conteúdo que não é placa nem traz rótulo de série/chassi.
            # NÃO se inventa identificador a partir de texto solto -- foi
            # exatamente assim que `RFD 2447` nasceu. Vai para revisão humana.
            if sem_placa is not None:
                sem_placa.append({
                    "texto": " ".join(celula.split()),
                    "motivo": "nao reconhecida",
                })


def _extrair_item_veiculo(paginas: list[dict], tem_ficha_cadastral: bool) -> dict:
    texto_completo = "\n".join(p["texto"] for p in paginas)
    itens: list[dict] = []
    placas: list[dict] = []
    sem_placa: list[dict] = []
    layout_placa: tuple[int, list[int]] | None = None   # (n_cols, idx das colunas de placa)

    for pagina in paginas:
        for tabela in pagina["tabelas"]:
            if not tabela:
                continue

            achado = _achar_linha_header(tabela, "PLACA", "VEICULO")
            if achado:
                idx_h, header = achado
                # 🚨 A COLUNA DE VEÍCULO SOZINHA JÁ BASTA -- corrigido em 07/08.
                #
                # Antes exigia `PLACA` no cabeçalho, ou `VEICULO` E `CHASSIS`
                # juntos. O termo 8800 (upgrade 4G) chama a coluna de
                # "VEÍCULOS A MIGRAR" e não tem coluna CHASSIS -- então a
                # tabela, que estava PERFEITA, era descartada, e a extração
                # caía no fallback por texto corrido.
                #
                # E o fallback inventou placa: no texto achatado, a coluna
                # "DOCUMENTO REFERÊNCIA" fica ENTRE as duas metades de uma
                # placa que quebrou de linha, e o `\s` do regex atravessava a
                # quebra. Saíram `RFD 2447` e `FMS 3078` -- que não existem na
                # WESO -- no lugar de `RFD 0E02` e `FMS 3J88`, que existem.
                # Nenhum erro, nenhum aviso: placa inventada é pior que placa
                # faltando.
                #
                # Aceitar `VEICULO` sozinho é seguro porque a extração é POR
                # CÉLULA: coluna de outro assunto simplesmente não casa com o
                # regex, e a `\b` das duas pontas já rejeita `SERIE 16994` e
                # `Chassi:...JMD002601` (verificado célula a célula).
                if _tem_header(header, "PLACA") or _tem_header(header, "VEICULO"):
                    idx_placa_cols = [i for i, h in enumerate(header) if "PLACA" in h] or \
                                      _colunas_de_veiculo(header)
                    layout_placa = (len(header), idx_placa_cols)
                    _processar_linhas_placa(tabela[idx_h + 1:], idx_placa_cols, placas,
                                            sem_placa)
                    continue

            # P5 (2026-07-27): continuação da tabela de placas numa página
            # seguinte, SEM cabeçalho. Antes isso existia só na Rescisão -- nos
            # outros perfis a lista simplesmente parava na quebra de página, em
            # silêncio (mesmo bug do termo 8788, que lia 12 de 26).
            if layout_placa and _eh_continuacao_tabela(tabela, layout_placa[0], layout_placa[1]):
                _processar_linhas_placa(tabela, layout_placa[1], placas, sem_placa)
                continue

            achado = _achar_linha_header(tabela, "ACESSORIO", "ITEM", "DESCRICAO")
            if achado:
                idx_h, header = achado
                if _tem_header(header, "ACESSORIO", "ITEM", "DESCRICAO") and not _tem_header(header, "CONDICAO"):
                    itens.extend(_extrair_itens_tabela_padrao(tabela, header, idx_h + 1))

    # Fallback: alguns documentos (ex: aditivo enxuto sem cabeçalho de tabela
    # de veículo reconhecível) têm a placa só como texto solto na página, sem
    # tabela estruturada -- procura no texto perto de "TOTAL MENSAL POR
    # VEÍCULO" (fim da tabela de item, início da lista de veículos).
    if not placas:
        idx_marca = texto_completo.upper().find("TOTAL MENSAL POR VEICULO")
        if idx_marca == -1:
            idx_marca = 0
        trecho = texto_completo[idx_marca:]
        for m in _PLACA_RE_MESMA_LINHA.finditer(trecho):
            if _eh_placa_fantasma(trecho, m):
                continue
            linha_ini = trecho.rfind("\n", 0, m.start()) + 1
            linha_fim = trecho.find("\n", m.end())
            linha_fim = len(trecho) if linha_fim == -1 else linha_fim
            linha = trecho[linha_ini:linha_fim]
            veiculo = (linha[:m.start() - linha_ini] + linha[m.end() - linha_ini:]).strip(" -*#0123456789")
            placas.append({
                "placa": _placa_formatada(trecho, m),
                "veiculo": " ".join(veiculo.split()),
                "sem_bloqueio": bool(_SEM_BLOQUEIO_RE.search(linha)),
                "nota_transferencia": _detectar_transferencia(linha),
            })

    nome_cabecalho, cnpj_cabecalho, termo_cabecalho = _extrair_cliente_cabecalho_tabela(texto_completo)

    nome_ficha, cnpj_ficha = None, None
    if tem_ficha_cadastral and paginas:
        nome_ficha, cnpj_ficha = _extrair_ficha_cadastral(paginas[0]["tabelas"])

    termo_match = _TERMO_RE.search(texto_completo)

    # A nota de transferência de titularidade do NOVO titular vive na coluna Tipo
    # de um item (ex.: "Adesão e Instalação" -> "* Transferência de titularidade
    # do contrato 3622..."), que nem sempre entra no extract_text da página. Junta
    # os textos de Tipo dos itens pra detecção não depender só do texto corrido.
    texto_transf = texto_completo + "\n" + "\n".join((i.get("comodato_ou_aquisicao") or "") for i in itens)

    return {
        "termo": termo_cabecalho or (termo_match.group(1) if termo_match else None),
        "cliente_nome_sugerido": nome_ficha or nome_cabecalho,
        "cnpj": cnpj_ficha or cnpj_cabecalho,
        "cpf": None,
        "placas": placas,
        # 🚨 Veículo que o PDF traz sem placa (chassi, número de série). Vai
        # para a tela em vez de sumir: no termo 8800 eram 2 de 11, e a
        # diferença entre "9 veículos" e "11 veículos, 2 sem placa" é quem
        # percebe que falta alguma coisa.
        "veiculos_sem_placa": sem_placa,
        "itens": itens,
        "alerta_transferencia": _detectar_transferencia(texto_transf),
        "termo_relacionado": _termo_relacionado(texto_transf),
        "texto_bruto": texto_completo[:3000],
    }


# ── Perfil: Substituição ──────────────────────────────────────────────────────
# Tabela pareada: 2 colunas "Placa" lado a lado (sai / entra), no mesmo termo.
# Gera 2 OS (retirada + instalação) com veículos DIFERENTES -- não confundir
# com Transferência, que são 2 OS com o MESMO veículo em clientes diferentes.

def _itens_acessorios_substituicao(celula) -> list[str]:
    """Quebra a célula 'Acessórios / Serviços' da Substituição em descrições de
    item. Formato diferente dos outros perfis: bullets '▶' (um por acessório),
    cada um podendo quebrar em 2 linhas no PDF ('▶ Bloqueio\\nVeicular'), e SEM
    coluna Tipo/Valor. Por isso o item sai só com a descrição -- em Substituição
    nunca é comodato nem cobrado (decisão do usuário 2026-07-23), o que
    _resolver_vinculos já traduz em comodato=False/cobrar=False quando não há
    Tipo nem valor."""
    txt = str(celula or "").replace("\n", " ")
    nomes = []
    for parte in re.split(r"[▶►•]", txt):  # ▶ ► •
        nome = " ".join(parte.split()).strip(" -*")
        if nome:
            nomes.append(nome)
    return nomes


def _placa_ou_texto(celula) -> str | None:
    """Placa normalizada quando casa com o padrão; senão o texto literal em
    maiúsculas. Existe pro veículo de ENTRADA da Substituição, que quando o
    substituto ainda não foi escolhido vem como 'A DEFINIR' -- decisão do
    usuário (2026-07-23): 'A DEFINIR' é placa válida e vai pra descrição como
    está, não pode zerar o par. Devolve None só pra célula vazia."""
    txt = str(celula or "").replace("\n", " ").strip()
    if not txt:
        return None
    m = _PLACA_RE.search(txt)
    if m:
        return _placa_formatada(txt, m)
    return " ".join(txt.upper().split())


def _extrair_substituicao(paginas: list[dict]) -> dict:
    texto_completo = "\n".join(p["texto"] for p in paginas)
    pares: list[dict] = []
    taxa_mesmo_local, taxa_local_diferente = None, None

    m = re.search(r"mesmo local e hor[áa]rio:\s*R\$\s*([\d,\.]+)", texto_completo, re.IGNORECASE)
    if m:
        taxa_mesmo_local = m.group(1)
    m = re.search(r"locais? e/?ou hor[áa]rios? diferentes?:\s*R\$\s*([\d,\.]+)", texto_completo, re.IGNORECASE)
    if m:
        taxa_local_diferente = m.group(1)

    for pagina in paginas:
        for tabela in pagina["tabelas"]:
            if not tabela:
                continue
            achado = _achar_linha_header(tabela, "PLACA", min_ocorrencias=2)
            if not achado:
                continue  # não é a tabela pareada -- ex: tabela normal com só 1 "placa"
            idx_h, header = achado
            idx_placa_cols = [i for i, h in enumerate(header) if "PLACA" in h]
            idx_saida, idx_entrada = idx_placa_cols[0], idx_placa_cols[1]
            idx_veic_saida = next((i for i in range(idx_saida) if "VEICULO" in header[i]), None)
            idx_veic_entrada = next((i for i in range(idx_saida + 1, idx_entrada) if "VEICULO" in header[i]), None)
            idx_acess_entrada = next((i for i in range(idx_entrada, len(header)) if "ACESSORIO" in header[i] or "SERVICO" in header[i]), None)

            for linha in tabela[idx_h + 1:]:
                if idx_entrada >= len(linha):
                    continue
                placa_saida = _placa_ou_texto(linha[idx_saida])
                placa_entrada = _placa_ou_texto(linha[idx_entrada])
                if not placa_saida or not placa_entrada:
                    continue
                pares.append({
                    "placa_saida": placa_saida,
                    "veiculo_saida": str(linha[idx_veic_saida] or "").replace("\n", " ").strip() if idx_veic_saida is not None else "",
                    "placa_entrada": placa_entrada,
                    "veiculo_entrada": str(linha[idx_veic_entrada] or "").replace("\n", " ").strip() if idx_veic_entrada is not None else "",
                    "acessorios_entrada": str(linha[idx_acess_entrada] or "").replace("\n", " ").strip() if idx_acess_entrada is not None and idx_acess_entrada < len(linha) else "",
                })

    nome_cabecalho, cnpj_cabecalho, termo_cabecalho = _extrair_cliente_cabecalho_tabela(texto_completo)
    termo_match = _TERMO_RE.search(texto_completo)

    # Acessórios da coluna de ENTRADA viram itens de OS (a instalação é que
    # recebe o equipamento no veículo novo). Sem Tipo nem valor -> comodato e
    # cobrar saem False lá no _resolver_vinculos, como pedido. Agregados por
    # descrição: a quantidade é quantos pares recebem aquele acessório, pra
    # _alocar_itens_por_placa espalhar 1 por placa de instalação.
    # Ressalva: se pares diferentes tiverem acessórios diferentes, o modelo de
    # lista global + quantidade pode desalinhar a alocação (aloca por ordem);
    # os termos reais vistos têm o mesmo pacote em todos os pares.
    contagem: dict[str, int] = {}
    for par in pares:
        for nome in _itens_acessorios_substituicao(par.get("acessorios_entrada")):
            contagem[nome] = contagem.get(nome, 0) + 1
    itens_acessorios = [
        {"descricao": nome, "quantidade": str(qtd), "valor_unitario": None,
         "comodato_ou_aquisicao": None, "sera_devolvido": None}
        for nome, qtd in contagem.items()
    ]

    return {
        "termo": termo_cabecalho or (termo_match.group(1) if termo_match else None),
        "cliente_nome_sugerido": nome_cabecalho,
        "cnpj": cnpj_cabecalho,
        "cpf": None,
        "pares": pares,
        "itens": itens_acessorios,
        "taxa_mesmo_local": taxa_mesmo_local,
        "taxa_local_diferente": taxa_local_diferente,
        "alerta_transferencia": None,
        "texto_bruto": texto_completo[:3000],
    }


# ── Perfil: Rescisão / Transferência (lado de origem) ─────────────────────────
# Uma linha da tabela pode agrupar VÁRIOS veículos (texto numerado "1. ... 2.
# ..." numa célula só, todos com o mesmo "documento referência"). Usa findall,
# não search -- a versão anterior perdia todo veículo além do primeiro numa
# célula agrupada.

_LINHA_NUMERADA_RE = re.compile(r"^\s*\d+\.\s*")


def _dividir_linhas_numeradas(celula: str) -> list[str]:
    """Cada '1. ...' inicia um item novo; uma linha SEM prefixo numerado é
    continuação do item anterior (descrição de veículo que quebrou em 2
    linhas no PDF, ex: '1. VW/17.210...\nBRANCA, DIESEL' é 1 veículo só, não
    2 -- bug real da 1ª versão, juntava tudo separado e desalinhava com a
    coluna de placa)."""
    linhas = [l.strip() for l in celula.split("\n") if l.strip()]
    if not linhas:
        return []
    if not any(_LINHA_NUMERADA_RE.match(l) for l in linhas):
        return [" ".join(linhas)]
    itens: list[str] = []
    atual: str | None = None
    for l in linhas:
        if _LINHA_NUMERADA_RE.match(l):
            if atual is not None:
                itens.append(atual)
            atual = _LINHA_NUMERADA_RE.sub("", l)
        else:
            atual = f"{atual} {l}" if atual else l
    if atual is not None:
        itens.append(atual)
    return itens


_ITENS_KEYS_RESCISAO = ("ACESSORIO", "QUANTIDADE", "QTD", "DESCRICAO", "VALOR", "CONDICAO", "COMODATO", "DEVOLV", "PAGAMENTO", "TOTAL")


def _processar_linhas_veiculo_rescisao(linhas: list, idx_veic: int, idx_placa: int, idx_ref, veiculos: list[dict]) -> None:
    """Processa as linhas de dado da tabela de veículos (uma célula pode agrupar
    vários veículos numerados). Usado tanto na tabela COM cabeçalho quanto nas
    continuações SEM cabeçalho em páginas seguintes."""
    for linha in linhas:
        if idx_placa >= len(linha):
            continue
        ref = str(linha[idx_ref] or "").strip() if idx_ref is not None and idx_ref < len(linha) else None
        veic_linhas = _dividir_linhas_numeradas(str(linha[idx_veic] or ""))
        placa_linhas = _dividir_linhas_numeradas(str(linha[idx_placa] or ""))
        n = max(len(veic_linhas), len(placa_linhas))
        for i in range(n):
            veic_txt = veic_linhas[i] if i < len(veic_linhas) else ""
            placa_txt = placa_linhas[i] if i < len(placa_linhas) else ""
            m = _PLACA_RE.search(placa_txt)
            # O que está na coluna PLACA é a placa, mesmo quando não tem o
            # formato convencional (decisão do usuário, 2026-07-29; coerente
            # com PADRÃO DE PLACA de 27/07: "chassi como vier, não
            # normalizar"). Perfuratriz identificada por 'DZCACCDBBAHB' ou
            # 'LS ABG' tem rastreador e entra na OS como qualquer outra.
            # Antes isto virava placa=None e a linha sumia da lista `placas`,
            # fazendo o painel acusar falsa divergência: no termo 8788 chegavam
            # 18 placas para distribuir 23 rastreadores. Confirmado na WESO em
            # 29/07: as 23 do 8788 existem lá, 22 idênticas byte a byte.
            bruto = " ".join(placa_txt.split())
            # ...mas traço, hífen ou célula em branco NÃO são identificador.
            # Existe versão do mesmo termo 8788 em que a coluna PLACA das
            # máquinas traz '-' em vez do nº de série (fixture de regressão);
            # sem esta guarda, '-' viraria placa e entraria na OS. Exige ao
            # menos um caractere alfanumérico.
            if not re.search(r"[A-Za-z0-9]", bruto):
                bruto = ""
            veiculos.append({
                "veiculo": veic_txt,
                "placa": _placa_formatada(placa_txt, m) if m else (bruto or None),
                "documento_referencia": ref,
                # não é mais "sem placa": é placa fora do padrão convencional.
                # Serve para destacar na revisão, nunca para excluir da geração.
                "placa_convencional": m is not None,
            })


def _eh_continuacao_veiculo_rescisao(tabela: list, n_cols: int, idx_veic: int, idx_placa: int) -> bool:
    """Quando a rescisão tem mais veículos do que cabe numa página, a lista
    quebra pra página seguinte numa tabela SEM cabeçalho -- que o achador de
    header ignora, sumindo com metade das placas (bug real, termo 8788: 26
    veículos, só 12 extraídos). Reconhece a continuação por: mesmo nº de colunas
    da tabela de veículos, NÃO é tabela de itens (QUANTIDADE/ACESSORIO/VALOR/...)
    e ter conteúdo de veículo/placa em alguma linha."""
    larguras = [len(r) for r in tabela if r]
    if not larguras or max(larguras) != n_cols:
        return False
    for linha in tabela[:2]:
        for cel in linha:
            if any(k in _normalizar(str(cel or "")) for k in _ITENS_KEYS_RESCISAO):
                return False
    for linha in tabela:
        if idx_veic < len(linha) and str(linha[idx_veic] or "").strip():
            return True
        if idx_placa < len(linha) and str(linha[idx_placa] or "").strip():
            return True
    return False


def _valor_ativo(celula) -> str | None:
    """Último valor monetário da célula. Trata valor RISCADO + valor real: a
    taxa de retirada às vezes vem 'R$ 299,00 R$ 0,00*' (o 299 riscado no PDF, o
    0,00 vigente) -- o extract_text traz o riscado primeiro, então o valor ATIVO
    é o ÚLTIMO."""
    achados = _VALOR_RE.findall(str(celula or ""))
    return achados[-1] if achados else None


def _extrair_encargos_rescisao(tabela: list, header: list[str], primeira_linha: int) -> list[dict]:
    """Tabela de ENCARGOS da Rescisão (DESCRIÇÃO + CONDIÇÃO DE PAGAMENTO): aviso
    prévio, taxa de retirada, multa... É o que GERA O FINANCEIRO -- a tabela de
    acessórios é toda comodato (volta), o custo mora aqui. Até E4 (2026-07-24)
    era pulada de propósito. Valor = TOTAL GERAL (valor ativo da célula); qtd=1
    porque o TOTAL GERAL já é o total do termo. Só emite encargo com valor > 0
    (taxa zerada / 'R$ 0,00*' não é cobrança real). `comodato_ou_aquisicao` fica
    None -> _resolver_vinculos resolve cobrar = valor>0 -> vai pra financeira."""
    idx_desc = next((i for i, h in enumerate(header) if "DESCRICAO" in h), None)
    idx_total = next((i for i, h in enumerate(header) if "TOTAL" in h and "GERAL" in h), None)
    if idx_total is None:
        idx_total = next((i for i, h in enumerate(header) if "TOTAL" in h), None)
    itens: list[dict] = []
    if idx_desc is None or idx_total is None:
        return itens
    for linha in tabela[primeira_linha:]:
        if idx_desc >= len(linha) or idx_total >= len(linha):
            continue
        descricao = str(linha[idx_desc] or "").replace("\n", " ").strip()
        valor = _valor_ativo(linha[idx_total])
        if not descricao or not valor:
            continue
        try:
            if float(valor.replace(".", "").replace(",", ".")) <= 0:
                continue  # encargo zerado (ex.: taxa de retirada assumida pelo cliente)
        except ValueError:
            continue
        itens.append({
            "descricao": descricao,
            "quantidade": "1",
            "valor_unitario": valor,
            "comodato_ou_aquisicao": None,
            "sera_devolvido": None,
        })
    return itens


def _extrair_rescisao(paginas: list[dict]) -> dict:
    texto_completo = "\n".join(p["texto"] for p in paginas)
    veiculos: list[dict] = []
    itens: list[dict] = []
    valor_total_rescisao = None
    layout_veiculo: tuple[int, int, int, int | None] | None = None  # (n_cols, idx_veic, idx_placa, idx_ref)

    for pagina in paginas:
        for tabela in pagina["tabelas"]:
            if not tabela:
                continue

            achado = _achar_linha_header_com_todos(tabela, "PLACA", "VEICULO")
            if achado:
                idx_h, header = achado
                idx_veic = next(i for i, h in enumerate(header) if "VEICULO" in h)
                idx_placa = next(i for i, h in enumerate(header) if "PLACA" in h)
                idx_ref = next((i for i, h in enumerate(header) if "REFERENCIA" in h or "DOCUMENTO" in h), None)
                layout_veiculo = (len(header), idx_veic, idx_placa, idx_ref)
                _processar_linhas_veiculo_rescisao(tabela[idx_h + 1:], idx_veic, idx_placa, idx_ref, veiculos)
                continue

            # Continuação da tabela de veículos numa página seguinte (sem cabeçalho).
            if layout_veiculo and _eh_continuacao_veiculo_rescisao(tabela, layout_veiculo[0], layout_veiculo[1], layout_veiculo[2]):
                _, idx_veic, idx_placa, idx_ref = layout_veiculo
                _processar_linhas_veiculo_rescisao(tabela, idx_veic, idx_placa, idx_ref, veiculos)
                continue

            achado = _achar_linha_header(tabela, "ACESSORIO", "ITEM")
            if achado:
                idx_h, header = achado
                if not _tem_header(header, "CONDICAO"):
                    itens.extend(_extrair_itens_tabela_padrao(tabela, header, idx_h + 1))
                    continue

            # E4 (2026-07-24): tabela de ENCARGOS -> financeiro. Cabeçalho DESCRIÇÃO
            # + CONDIÇÃO DE PAGAMENTO (ou TOTAL GERAL). Antes pulada de propósito.
            achado_enc = _achar_linha_header(tabela, "DESCRICAO")
            if achado_enc:
                idx_h, header = achado_enc
                if _tem_header(header, "CONDICAO") or _tem_header(header, "PAGAMENTO") or (_tem_header(header, "TOTAL") and _tem_header(header, "GERAL")):
                    itens.extend(_extrair_encargos_rescisao(tabela, header, idx_h + 1))

    m = re.search(r"VALOR TOTAL DA RESCIS[ÃA]O\s*R\$\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
    if m:
        valor_total_rescisao = m.group(1)

    cliente_match = _CLIENTE_PROSA_RE.search(texto_completo)
    responsavel_match = _RESPONSAVEL_RE.search(texto_completo)
    cnpj_match = _CNPJ_RE.search(texto_completo)  # geralmente None -- rescisão não mostra CNPJ, esperado
    termo_match = _TERMO_RE.search(texto_completo)

    return {
        "termo": termo_match.group(1) if termo_match else None,
        "cliente_nome_sugerido": cliente_match.group(1).strip() if cliente_match else None,
        "responsavel_nome": responsavel_match.group(1).strip() if responsavel_match else None,
        "cnpj": cnpj_match.group(0) if cnpj_match else None,
        "cpf": None,
        "veiculos": veiculos,
        # Só fica de fora linha sem NADA na coluna PLACA (célula vazia de
        # tabela desalinhada). Placa não-convencional entra — ver comentário
        # em _processar_linhas_veiculo.
        "placas": [v for v in veiculos if v["placa"]],
        "itens": itens,
        "valor_total_rescisao": valor_total_rescisao,
        "alerta_transferencia": _detectar_transferencia(texto_completo),
        "termo_relacionado": _termo_relacionado(texto_completo),
        "texto_bruto": texto_completo[:3000],
    }


# ── Dispatch ───────────────────────────────────────────────────────────────────

def extrair_campos(fonte, perfil: str = "") -> dict:
    """`fonte` pode ser um caminho de arquivo ou um objeto tipo arquivo (BytesIO).
    `perfil` decide qual layout de tabela esperar -- ver PERFIS em
    templates_config.py pras chaves válidas. Perfil desconhecido/vazio cai no
    parser genérico de item+veículo (mais próximo do comportamento antigo)."""
    paginas = _ler_paginas(fonte)

    if perfil == "substituicao":
        return _aplicar_placeholder_termo(_extrair_substituicao(paginas))
    # Antigo titular (E5): documento é formato Rescisão/Distrato (o veículo sai do
    # contrato do antigo dono). Novo titular é formato Cliente Novo -> cai embaixo.
    if perfil in ("rescisao", "transferencia_antigo_titular"):
        return _aplicar_placeholder_termo(_extrair_rescisao(paginas))
    # Achado 2026-07-16 (docs reais "transferencia de cliente que ja/nao
    # existe.pdf"): o lado de destino de uma Transferência de titularidade é
    # sempre formato Cliente Novo/Aditivo (coluna única "Veículo e Placa"),
    # NUNCA Rescisão -- roteava errado antes e perdia nome do cliente, itens
    # (tabela "Descrição" não batia com o cabeçalho procurado por Rescisão) e
    # metade das placas em tabelas de 2 colunas lado a lado (Rescisão só
    # capturava a 1ª coluna via `next()`; este parser itera todas). O lado de
    # origem continua sendo submetido separadamente como perfil "rescisao".
    return _aplicar_placeholder_termo(
        _extrair_item_veiculo(paginas, tem_ficha_cadastral=(perfil in ("cliente_novo", "transferencia_novo_titular")))
    )
