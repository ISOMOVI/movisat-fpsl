"""Leituras do termo que SÓ a aba Operações faz. 2026-08-26.

🚨 EXISTE PARA NÃO TOCAR O `pdf_extractor`. Aquele arquivo é lido por TRÊS
telas -- a aba Operações, a tela velha de Gerar OS e o Cadastro de Placas -- e
o pedido do usuário foi explícito: o ajuste é só da aba nova. Regra que muda
entre as telas se clona; infraestrutura sem regra se reusa. Daqui de dentro o
`pdf_extractor` só é LIDO (`_ler_paginas`, `_valor_ativo`), nunca alterado.

O que se lê aqui hoje: a TAXA DE MIGRAÇÃO do termo de Upgrade.

⚠️ POR QUE ELA NÃO CABIA NO EXTRATOR GENÉRICO. O layout do Upgrade não tem
tabela de itens -- tem uma linha por veículo com as colunas `VEÍCULOS A
MIGRAR`, `DOCUMENTO REFERÊNCIA`, `TAXA DE MIGRAÇÃO` e `NOVO VALOR MENSAL`. Sem
coluna de tipo, sem `COMODATO`. Por isso `itens` sempre voltou vazio e TODA OS
financeira de upgrade saiu `SEM CUSTO`: 8820, 8834, 8844 e 8827.

🚨 O VALOR VEM DO TOTAL, E O TOTAL VEM RISCADO EM 2 DOS 3 TERMOS REAIS:

    8827   R$ 200,00 (Boleto a vista)                       -> cobra 200,00
    8820   R$ 100,00 / R$ 0,00*  "Negociação especial"      -> não cobra
    8800   R$ 2.200,00 - R$ 0,00 "Condição especial ..."    -> não cobra

Ler o primeiro valor da célula cobraria R$ 100,00 e R$ 2.200,00 que os termos
CANCELARAM. É a mesma armadilha da taxa de retirada da rescisão, e o remédio é
o mesmo: `_valor_ativo` pega o ÚLTIMO valor, e encargo zerado não vira item.

⚠️ NENHUM ID FIXO EM CÓDIGO AQUI. O item sai com a DESCRIÇÃO e é o vínculo de
`painel_vinculos_itens` que diz qual serviço do Harmonit ele é -- igual a todo
item de termo. Sem vínculo ele vira PENDENTE e bloqueia a geração, que é
falha visível; id fixo apodreceria em silêncio, como o `tipo = 55`.
"""
import re
import unicodedata

from .pdf_extractor import _ler_paginas, _valor_ativo

# O rótulo, como fica depois de tirar acento, espaço e a duplicação de letras.
ROTULO_TOTAL_MIGRACAO = "TOTALDAMIGRACAO"
DESCRICAO_TAXA_MIGRACAO = "TAXA DE MIGRAÇÃO"

_VALOR_NA_CELULA = re.compile(r"\d")


def _sem_acento(txt: str) -> str:
    t = unicodedata.normalize("NFKD", str(txt or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def desdobrar(celula) -> str | None:
    """Texto de célula em que CADA LETRA está duplicada, ou None.

    🚨 O RÓTULO DO TOTAL VEM `TTOOTTAALL DDAA MMIIGGRRAAÇÇÃÃOO`. É negrito
    sobreposto no PDF, e acontece nos três termos de upgrade.

    ⚠️ SÓ DESDOBRA QUANDO A CÉLULA INTEIRA TEM O PADRÃO, e o resultado NUNCA é
    gravado em campo nenhum -- serve só para comparar rótulo. Varri as 15
    fixtures: o mesmo padrão aparece em `Franquia mensal: R$ 0,00` de quatro
    termos de contrato novo e transferência, que hoje são lidos certo. Aplicar
    o desdobramento no texto que vira dado estragaria esses.
    """
    s = re.sub(r"\s+", "", str(celula or ""))
    if len(s) >= 4 and len(s) % 2 == 0 and s[0::2] == s[1::2]:
        return s[0::2]
    return None


def _eh_rotulo_do_total(celula) -> bool:
    dobrado = desdobrar(celula)
    if dobrado is None:
        return False
    return _sem_acento(dobrado) == ROTULO_TOTAL_MIGRACAO


def _valor_da_linha(linha: list, idx_rotulo: int) -> str | None:
    """O valor ATIVO da linha do total, procurando da direita para a esquerda.

    ⚠️ A POSIÇÃO MUDA ENTRE OS TERMOS: no 8827 o total está na última linha da
    tabela de veículos, com o valor na 6ª coluna; no 8820 e no 8800 está numa
    tabela própria de 2 colunas. Procurar por posição fixa acertaria um e
    perderia os outros.
    """
    for i in range(len(linha) - 1, -1, -1):
        if i == idx_rotulo:
            continue
        celula = linha[i]
        if not celula or not _VALOR_NA_CELULA.search(str(celula)):
            continue
        valor = _valor_ativo(celula)
        if valor:
            return valor
    return None


def taxa_de_migracao(fonte) -> tuple[dict | None, list[str]]:
    """(item, avisos). O item já sai no formato de `itens_contrato`.

    `comodato_ou_aquisicao` fica None de propósito: `resolver_vinculos` traduz
    isso em comodato=False e cobrar = valor>0, que é o caminho de todo encargo.
    """
    avisos: list[str] = []
    for pagina in _ler_paginas(fonte):
        for tabela in pagina["tabelas"]:
            for linha in tabela or []:
                idx = next((i for i, c in enumerate(linha)
                            if _eh_rotulo_do_total(c)), None)
                if idx is None:
                    continue
                valor = _valor_da_linha(linha, idx)
                if not valor:
                    avisos.append(
                        "O termo tem a linha TOTAL DA MIGRAÇÃO mas não consegui "
                        "ler o valor dela — a taxa de migração NÃO entrou na OS "
                        "financeira. Confira o documento antes de gerar.")
                    return None, avisos
                try:
                    numero = float(valor.replace(".", "").replace(",", "."))
                except ValueError:
                    avisos.append(
                        f"O TOTAL DA MIGRAÇÃO do termo veio como {valor!r}, que "
                        "não é um valor que eu saiba ler — a taxa NÃO entrou na "
                        "OS financeira.")
                    return None, avisos
                if numero <= 0:
                    # 🚨 NÃO É ERRO, É O TERMO. Taxa riscada (8820, 8800) é
                    # cortesia concedida: não vira cobrança e não vira aviso,
                    # porque aviso falso treina a equipe a ignorar aviso.
                    return None, avisos
                return {"descricao": DESCRICAO_TAXA_MIGRACAO,
                        "quantidade": "1",
                        "valor_unitario": valor,
                        "comodato_ou_aquisicao": None,
                        "sera_devolvido": None}, avisos
    # Sem a linha do total não se inventa nada: nem item, nem soma das linhas
    # por veículo. O usuário decidiu em 26/08 que o valor é o TOTAL do termo,
    # "está escrito" -- somar por conta seria adivinhar.
    return None, avisos


def itens_extras(fonte, perfil: str) -> tuple[list[dict], list[str]]:
    """Itens que só esta aba lê, por perfil. Hoje: a taxa de migração."""
    if perfil != "upgrade":
        return [], []
    item, avisos = taxa_de_migracao(fonte)
    return ([item] if item else []), avisos


# ── O termo novo de transferência (23/09) ────────────────────────────────────
#
# "TERMO DE TRANSF. DE TIT.: RESCISÃO", medido nos termos 8873 e 8880. O
# layout não tem NADA em comum com a Rescisão, que era por onde o antigo
# titular passava: são três tabelas de cabeçalho fixo --
#
#     DE - ANTIGO TITULAR | CNPJ ANTIGO TITULAR | PARA - NOVO TITULAR | CNPJ NOVO TITULAR
#     Placa | Modelo | Contrato ATUAL | NOVO CONTRATO
#     Equipamentos e Acessórios | Tipo | Ação
#
# 🚨 LIDO PELO PERFIL ANTIGO, ESTE TERMO DÁ ZERO PLACAS (medido nos dois). A
# etapa 3 trava e ninguém entende por quê -- por isso existe
# `eh_termo_transf_novo`, que o `/extrair` usa para recusar o perfil errado
# com o nome do certo.
#
# 🚨 O CLIENTE É O ANTIGO TITULAR, PELO CNPJ DA TABELA. O extrator genérico pega
# o PRIMEIRO CNPJ do texto: no 8873 era o do cabeçalho, no 8880 (que não tem a
# linha do cabeçalho) foi o da tabela -- certo nos dois por sorte da ordem. E
# nunca pelo nome: o 8873 diz "CAVAN ROCBRA E COMERCIO DE PRE MOLDADOS DE
# CONCRETO" e o Harmonit tem "CAVAN ROCBRA INDUSTRIA E COMERCIO ... S/A".
#
# 🚨 O TERMO NÃO TEM COLUNA DE QUANTIDADE. A tabela de itens é "o que
# acompanha OS veículos", então cada item vale UM POR VEÍCULO. Sem dizer isso,
# o item sai com quantidade 1 e a alocação o põe só na PRIMEIRA placa -- as
# outras ficariam sem ele, calado.
#
# ⚠️ PLACA SEM NOVO CONTRATO É RESCISÃO (decisão do usuário, 23/09): o modelo
# é "meio híbrido", mistura placa que transfere e placa que rescinde. Nenhum
# termo real com rescisão chegou ainda -- quando chegar, ele vira fixture.

_CAB_TITULARES = ("ANTIGO TITULAR", "NOVO TITULAR")
_CAB_PLACAS = ("PLACA", "CONTRATO ATUAL", "NOVO CONTRATO")
_CAB_ITENS = ("EQUIPAMENTOS", "TIPO", "ACAO")
_DISTRATO_RE = re.compile(r"Distrato\s*n\S?\s*(\d+)", re.IGNORECASE)
_TITULO_RE = re.compile(r"TERMO\s+DE\s+TRANSF\.?\s+DE\s+TIT", re.IGNORECASE)
_CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
_CONTRATO_NA_FRASE_RE = re.compile(
    r"transferid[oa]s?\s+para\s+o\s+contrato\s*n\S?\s*(\d+)", re.IGNORECASE)
_NUMERO_RE = re.compile(r"\d+")


def _cel(c) -> str:
    """Célula como uma linha só: o PDF quebra nome e modelo em várias."""
    return " ".join(str(c or "").split())


def _cabecalho(linha) -> str:
    return " | ".join(_sem_acento(_cel(c)) for c in (linha or []))


def _tem(cab: str, marcas: tuple) -> bool:
    return all(m in cab for m in marcas)


def _indice(linha, marca: str) -> int | None:
    return next((i for i, c in enumerate(linha or [])
                 if marca in _sem_acento(_cel(c))), None)


def eh_termo_transf_novo(fonte) -> bool:
    """O documento é o termo novo de transferência? Pelo TÍTULO e pela tabela
    de placas -- os dois juntos, para um texto solto não bastar."""
    paginas = _ler_paginas(fonte)
    if not paginas or not _TITULO_RE.search(paginas[0]["texto"] or ""):
        return False
    return any(_tem(_cabecalho(t[0]), _CAB_PLACAS)
               for p in paginas for t in p["tabelas"] if t)


def ler_termo_transf_novo(fonte) -> dict:
    """Os campos do termo novo, no MESMO formato que `extrair_campos` devolve
    -- é o que deixa o `/extrair` e a tela de Vínculos usarem sem caminho
    próprio. O que é só deste termo vem em chaves novas (`novo_titular`,
    `novo_contrato` por placa), que os outros perfis nunca leem."""
    paginas = _ler_paginas(fonte)
    texto = "\n".join(p["texto"] for p in paginas)
    avisos: list[str] = []
    titulares: dict | None = None
    placas: list[dict] = []
    sem_placa: list[str] = []
    itens_brutos: list[dict] = []

    for pagina in paginas:
        for tabela in pagina["tabelas"]:
            if not tabela:
                continue
            cab = _cabecalho(tabela[0])
            corpo = [l for l in tabela[1:] if any(_cel(c) for c in l)]
            if _tem(cab, _CAB_TITULARES) and corpo:
                l = corpo[0]
                titulares = {"antigo_nome": _cel(l[0]) if len(l) > 0 else "",
                             "antigo_cnpj": _cel(l[1]) if len(l) > 1 else "",
                             "novo_nome": _cel(l[2]) if len(l) > 2 else "",
                             "novo_cnpj": _cel(l[3]) if len(l) > 3 else ""}
            elif _tem(cab, _CAB_PLACAS):
                ip, im = _indice(tabela[0], "PLACA"), _indice(tabela[0], "MODELO")
                ia = _indice(tabela[0], "CONTRATO ATUAL")
                inovo = _indice(tabela[0], "NOVO CONTRATO")
                for l in corpo:
                    placa = _cel(l[ip]) if ip is not None and ip < len(l) else ""
                    modelo = _cel(l[im]) if im is not None and im < len(l) else ""
                    if not placa:
                        # 🚨 APARECE, NÃO SOME (regra 13): linha de veículo sem
                        # placa vai para a lista que a tela mostra.
                        sem_placa.append(modelo or " ".join(_cel(c) for c in l))
                        continue
                    novo = _NUMERO_RE.search(_cel(l[inovo])) if inovo is not None and inovo < len(l) else None
                    atual = _cel(l[ia]) if ia is not None and ia < len(l) else ""
                    placas.append({"veiculo": modelo, "placa": placa,
                                   "contrato_atual": atual or None,
                                   "novo_contrato": novo.group(0) if novo else None})
            elif _tem(cab, _CAB_ITENS):
                it = _indice(tabela[0], "TIPO")
                ia = _indice(tabela[0], "ACAO")
                for l in corpo:
                    desc = _cel(l[0])
                    if not desc:
                        continue
                    itens_brutos.append({
                        "descricao": desc,
                        "tipo": _cel(l[it]) if it is not None and it < len(l) else "",
                        "acao": _cel(l[ia]) if ia is not None and ia < len(l) else ""})
            else:
                # 🚨 TABELA QUE EU NÃO CONHEÇO NÃO SOME. É por aqui que a
                # cobrança da rescisão vai chegar -- o modelo ainda não mostrou
                # como -- e ler "nada" dela seria a financeira saindo vazia.
                avisos.append(
                    "O termo tem uma tabela que eu não sei ler (começa com "
                    f"\"{_cel(tabela[0][0])[:40]}\"). Se ela tem cobrança, a "
                    "cobrança NÃO entrou na OS. Confira o documento antes de gerar.")

    if titulares is None:
        avisos.append("Não achei a tabela dos titulares (antigo e novo). Sem ela "
                      "o CNPJ do cliente não foi lido.")
    if not placas and not sem_placa:
        avisos.append("Não achei a tabela de placas (Placa | Modelo | Contrato "
                      "ATUAL | NOVO CONTRATO).")

    # ⚠️ O NOVO CONTRATO TEM DE SER UM SÓ, e bater com a frase do rodapé. Se
    # divergir, avisa -- não escolhe um.
    novos = sorted({p["novo_contrato"] for p in placas if p["novo_contrato"]})
    frase = _CONTRATO_NA_FRASE_RE.search(" ".join(texto.split()))
    if len(novos) > 1:
        avisos.append("As placas apontam para contratos novos DIFERENTES: "
                      + ", ".join(novos) + ". Confira o termo.")
    if frase and novos and frase.group(1) not in novos:
        avisos.append(f"A tabela diz novo contrato {', '.join(novos)} e o texto "
                      f"do termo diz {frase.group(1)}. Confira antes de gerar.")
    termo_relacionado = novos[0] if len(novos) == 1 else (
        frase.group(1) if frase else None)

    n = max(len(placas), 1)
    itens = [{"descricao": i["descricao"],
              # um por veículo -- ver o cabeçalho desta seção
              "quantidade": str(n),
              "valor_unitario": None,
              "comodato_ou_aquisicao": i["tipo"] or None,
              "sera_devolvido": None,
              "acao": i["acao"] or None}
             for i in itens_brutos]

    m = _DISTRATO_RE.search(texto)
    t = titulares or {}
    return {
        "termo": m.group(1) if m else None,
        "cliente_nome_sugerido": t.get("antigo_nome") or None,
        "responsavel_nome": None,
        "cnpj": t.get("antigo_cnpj") if _CNPJ_RE.fullmatch(t.get("antigo_cnpj") or "") else None,
        "cpf": None,
        "novo_titular": ({"nome": t.get("novo_nome") or None,
                          "cnpj": t.get("novo_cnpj") or None} if titulares else None),
        "placas": placas,
        "veiculos": [p["placa"] for p in placas],
        "veiculos_sem_placa": sem_placa,
        "itens": itens,
        "termo_relacionado": termo_relacionado,
        "avisos_extracao": avisos,
    }
