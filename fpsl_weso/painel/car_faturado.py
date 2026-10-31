"""Espelho do faturado do Harmonit (`CAR_1.1`, bloco **F1**). 2026-10-30.

Spec: `docs/fpsl/32_Contas_a_Receber.md`. Controle da frente:
`C:\\Users\\Lenovo\\Desktop\\CAR_1.1_Financeiro_FPSL.md`.

🚨 MÓDULO PURO, SEM I/O -- no molde do `car_motor.py`. Quem fala com o Harmonit
é `services/sync_faturado.py`; quem fala com o banco é o router. Aqui só mora a
régua, e é por isso que ela é testável sem rede e sem banco.

🚨 POR QUE ESTE MÓDULO EXISTE: a Movisat já fatura pelo Harmonit (medido em
30/10: 297 lançamentos de vencimento 10/2026) e a CAR não lia **nada** disso --
a tela afirmava uma carteira de R$ 0 com a operação inteira rodando do lado.

🚨 A API FINANCEIRA NÃO DÁ PLACA, e isso é limite dela, não escolha nossa.
Medido ao vivo em 30/10, nos 12 campos do lançamento
(`id · pagamento · descricao · contatoId · contato · valor · categoria(Id) ·
centroCusto(Id) · contaCorrente(Id)`): **zero** das 297 descrições traz placa, e
o `swagger.json` **não tem nenhuma rota de contrato** (`/Contrato*`,
`/Mensalidade*`, `/Parcela*`). A placa só existe do nosso lado: `contrato_placa`
mais o cache da WESO. Quem quiser "as placas que estão sendo cobradas" chega lá
pelo CONTRATO, nunca pelo financeiro.

🚨 A COMPETÊNCIA SAI DO TEXTO, NÃO DO VENCIMENTO. `anoVencimento/mesVencimento`
é eixo de vencimento; a referência está escrita na descrição
(*"Mensalidade ref. período 09/2026"*). Medido em 28/10: das 261 mensalidades
baixadas em outubro, **233 eram de referência 09/2026**. Ler pelo vencimento
mostraria o mês errado para a maioria da carteira. ⚠️ E a **v2** da rota, que
traria `competencia` como campo pronto, **recusa esta empresa** (*"Este método
não atende a sua empresa, por favor tente novamente em /v1"*, conferido em
30/10) -- não há atalho.

🚨 O TIPO SAI DO TEXTO, E O `centroCusto` FICA DO LADO COMO VEIO. Medido em
30/10: **4 mensalidades** chegam com `centroCusto` = `boleto` e **1** com
`Adesão`, embora a descrição diga *"Faturamento do contrato Nr. X. Mensalidade
ref. período MM/AAAA"*. Classificar pelo centro de custo jogaria essas 5 fora da
mensalidade. O centro de custo continua gravado, cru, porque é ele que a tela
usa para separar o recorrente do avulso.

⚠️ O QUE NÃO CASA VIRA `outro`, COM A DESCRIÇÃO CRUA PRESERVADA. Supor
significado para texto que nunca vi é o erro que o `M15` cobra -- e já apareceu
um `"Negociação 17/24"` (parcelamento) que nenhuma régua minha previa.
"""
import re
from datetime import datetime, timedelta, timezone

# ── Os cinco tipos. Enum no CÓDIGO, não em CHECK (ver `car_tabelas`). ────────
MENSALIDADE = "mensalidade"
SERVICO = "servico"
VENDA = "venda"
ADESAO = "adesao"
NEGOCIACAO = "negociacao"
OUTRO = "outro"
TIPOS = frozenset({MENSALIDADE, SERVICO, VENDA, ADESAO, NEGOCIACAO, OUTRO})

# 🟡 DECISÃO MINHA, REVERSÍVEL EM UMA LINHA: a adesão é lançada como
# "Faturamento do contrato ... Mensalidade ref. período", mas é cobrança de UMA
# vez -- então ela tem tipo próprio e conta no AVULSO, não na mensalidade do mês.
# Somá-la à mensalidade inflaria a receita recorrente de um contrato novo.
RECORRENTES = frozenset({MENSALIDADE})

# Estados do lançamento. São as duas rotas do Harmonit, não invenção nossa.
A_BAIXAR = "a_baixar"
BAIXADO = "baixado"
ESTADOS = frozenset({A_BAIXAR, BAIXADO})

# ── O que a descrição amarra ─────────────────────────────────────────────────
RE_CONTRATO = re.compile(r"contrato\s+n[ro]?\.?\s*(\d+)", re.I)
RE_COMPETENCIA = re.compile(r"per[ií]odo\s+(\d{2})/(\d{4})")
RE_OS = re.compile(r"ordem\s+de\s+servi[çc]o\s+n[ro]?\.?\s*(\d+)", re.I)
RE_VENDA = re.compile(r"venda\s+n[ro]?\.?\s*(\d+)", re.I)
RE_NEGOCIACAO = re.compile(r"negocia[çc][ãa]o\s+(\d+)\s*/\s*(\d+)", re.I)
RE_MENSALIDADE = re.compile(r"mensalidade", re.I)

# Quantas horas o botão espera depois da passada automática, com a rotina
# ligada. 🔵 Regra dele, 30/10: *"o botão esmaece ou só pode ser usado mais 1 vez
# no dia 4hrs após a automática, quando ligada"*.
ESPERA_APOS_AUTOMATICA_H = 4
MANUAIS_POR_DIA = 1


def _texto(v) -> str:
    return str(v or "").strip()


def competencia_da_descricao(descricao) -> str | None:
    """`"... ref. período 09/2026."` -> `"2026-09"`. `None` quando o texto não diz.

    🚨 `None` NUNCA CAI NO MÊS DE VENCIMENTO. "Não sei de que mês é" e "é do mês
    do boleto" são afirmações diferentes, e a segunda estaria errada em 233 de
    261 casos medidos. Lançamento sem competência aparece na tela como tal.
    """
    m = RE_COMPETENCIA.search(_texto(descricao))
    if not m:
        return None
    mes, ano = m.group(1), m.group(2)
    if not ("01" <= mes <= "12"):
        return None
    return f"{ano}-{mes}"


def valor_texto(v) -> str | None:
    """O valor do Harmonit no formato de dinheiro DESTA CASA: `"200,53"`.

    🚨 ISTO É CONSERTO DE UM DEFEITO REAL, achado por teste em 30/10 antes de
    valer qualquer coisa: o Harmonit manda `200.53` (número JSON, ponto
    decimal), e todo dinheiro daqui é TEXTO em convenção brasileira --
    `car_prefatura._centavos` lê o ponto como **separador de milhar**. Guardar
    `"200.53"` fazia a soma virar **R$ 20.053,00**, cem vezes mais, em silêncio.

    E o formato importa duas vezes: o valor do espelho é **copiado** para
    `car_evento.valor_mensal` pela semeadura (F4). Entrar torto aqui poria o
    número torto no livro-razão do dinheiro, onde ele é imutável.

    Texto já vem do termo em convenção brasileira e passa intacto.
    """
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return f"{v:.2f}".replace(".", ",")
    return _texto(v) or None


def _numero(regex, descricao) -> str | None:
    m = regex.search(_texto(descricao))
    return m.group(1) if m else None


def classificar(lancamento: dict, estado: str) -> dict:
    """Um lançamento do Harmonit -> a linha de `car_faturado`, sem cnpj nem termo.

    Puro: o que depende do banco (`cnpj` pelo `contatoId`, `termo_id` pelo
    número) é resolvido por quem tem a conexão. Aqui só se lê o que o próprio
    lançamento diz.

    `estado` é `a_baixar` ou `baixado` -- vem da rota que trouxe o lançamento,
    não do corpo dele (as duas rotas devolvem campos diferentes: a de baixados
    traz `pagamento`, a de abertos traz `vencimento` e `valorFinal`).
    """
    if estado not in ESTADOS:
        raise ValueError(f"estado desconhecido: {estado!r}")

    descricao = _texto(lancamento.get("descricao"))
    centro = _texto(lancamento.get("centroCusto"))
    comp = competencia_da_descricao(descricao)
    numero_contrato = _numero(RE_CONTRATO, descricao)
    numero_os = _numero(RE_OS, descricao)
    numero_venda = _numero(RE_VENDA, descricao)
    parcela = None
    neg = RE_NEGOCIACAO.search(descricao)
    if neg:
        parcela = f"{neg.group(1)}/{neg.group(2)}"

    if numero_contrato and RE_MENSALIDADE.search(descricao):
        # O centro de custo só decide entre mensalidade e adesão -- as duas são
        # faturamento do contrato, e a diferença é recorrer ou não.
        tipo = ADESAO if centro.lower().startswith("ades") else MENSALIDADE
    elif numero_os:
        tipo = SERVICO
    elif numero_venda:
        tipo = VENDA
    elif parcela:
        tipo = NEGOCIACAO
    else:
        tipo = OUTRO

    return {
        "id": lancamento.get("id"),
        "tipo": tipo,
        "estado": estado,
        "competencia": comp,
        "vencimento": _texto(lancamento.get("vencimento")) or None,
        "pagamento": _texto(lancamento.get("pagamento")) or None,
        # 🚨 TEXT em convenção BRASILEIRA, pela mesma razão de `contrato_item` e
        # de `car_evento` -- e pela armadilha do ponto decimal, que `valor_texto`
        # explica. A conversão para número acontece num lugar só, na hora de
        # somar, e erro de conversão é DITO, não silenciado.
        "valor": valor_texto(lancamento.get("valor")),
        "valor_final": valor_texto(lancamento.get("valorFinal")),
        "contato_id": lancamento.get("contatoId"),
        "contato": _texto(lancamento.get("contato")) or None,
        "termo_numero": numero_contrato,
        "numero_os": int(numero_os) if numero_os else None,
        "numero_venda": numero_venda,
        "parcela": parcela,
        "centro_custo": centro or None,
        "categoria": _texto(lancamento.get("categoria")) or None,
        "conta_corrente": _texto(lancamento.get("contaCorrente")) or None,
        "nosso_numero": _texto(lancamento.get("nossoNumero")) or None,
        # A descrição CRUA fica sempre. É ela que permite reclassificar depois
        # sem reler o Harmonit -- e é a única prova do que o texto dizia.
        "descricao": descricao or None,
    }


# ── A régua do botão de atualizar ────────────────────────────────────────────
def _quando(v) -> datetime | None:
    """ISO em UTC (ou `datetime`) -> `datetime` com fuso. Ilegível é `None`."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def pode_atualizar_agora(ativa: bool, ultima_automatica, ultima_manual,
                         agora=None) -> dict:
    """Se o botão "atualizar agora" pode rodar, e **por que não** quando não pode.

    🔵 REGRA DELE, 30/10, ao pé da letra: *"nasce desligada mas tbm pode ser
    feita pelo botão, até que decidam deixar ligada, aí o botão esmaece ou só
    pode ser usado mais 1 vez no dia 4hrs após a automática, quando ligada"*.

    Devolve `{"pode", "motivo", "libera_em"}`. 🚨 O MOTIVO É PARA A TELA, não
    para o log: botão esmaecido que não diz por quê é botão que mente (`M12`), e
    `libera_em` é o que deixa a tela escrever a hora em vez de "tente mais
    tarde".

    ⚠️ O dia é o dia em **UTC**, como todo carimbo desta casa. O limite real que
    a régua dele define é o das 4 h; o "1 por dia" só impede a segunda rodada à
    mão depois que a janela abriu.
    """
    agora = _quando(agora) or datetime.now(timezone.utc)
    auto = _quando(ultima_automatica)
    manual = _quando(ultima_manual)

    if not ativa:
        return {"pode": True, "motivo": "", "libera_em": None}

    if manual is not None and manual.date() == agora.date():
        return {"pode": False, "libera_em": None,
                "motivo": ("com a rotina ligada o botão vale uma vez por dia, e "
                           f"já foi usado hoje às {manual:%H:%M} UTC")}

    if auto is None:
        return {"pode": False, "libera_em": None,
                "motivo": ("a rotina está ligada e ainda não registrou passada "
                           "nenhuma; o botão libera 4 h depois da primeira")}

    libera = auto + timedelta(hours=ESPERA_APOS_AUTOMATICA_H)
    if agora < libera:
        return {"pode": False, "libera_em": libera.isoformat(),
                "motivo": (f"a passada automática foi às {auto:%H:%M} UTC; com a "
                           f"rotina ligada o botão libera às {libera:%H:%M} UTC")}

    return {"pode": True, "motivo": "", "libera_em": None}


# ── Meses a varrer ───────────────────────────────────────────────────────────
def meses_da_passada(hoje, atras: int = 6, adiante: int = 3) -> list:
    """Os `(ano, mês)` de VENCIMENTO que a rotina varre numa passada.

    🚨 NÃO BASTA O MÊS CORRENTE, e o motivo é medido: a competência vive no
    texto e o parcelado **antecipa** o vencimento -- em outubro de 2026 havia
    lançamento de referência 11/2026 a 09/2027 já criado. Varrer só o mês de
    hoje deixaria a competência do mês passado incompleta (233 de 261
    mensalidades de outubro eram de setembro) e perderia a previsão de receita
    que o Harmonit já tem lançada.

    🚨 E `atras` ERA 2, O QUE SUBESTIMAVA A RECEITA EM SILÊNCIO. Medido ao vivo
    em 30/10: a competência **2026-09** tem lançamento em **sete** meses de
    vencimento (04 a 10/2026) -- **282 lançamentos, R$ 185.234,14**, dos quais
    **5 de vencimento ABRIL** somam R$ 15.678,03. Com `atras=2` a conta de
    setembro fechava em R$ 163.666,05, e nada na tela diria que faltava.
    ⚠️ Por isso o espelho grava `venc_ano_mes` em cada linha e a pré-fatura
    **declara de quantos meses de vencimento aquela competência foi lida**:
    cobertura que não se vê é cobertura em que ninguém confia.

    São 2 chamadas por mês, então a passada de 10 meses custa **20 `GET`**
    (medido: ~49 s para 12, ~1,5 min para 20).
    """
    saida = []
    for passo in range(-atras, adiante + 1):
        m = hoje.month + passo
        ano = hoje.year + (m - 1) // 12
        mes = (m - 1) % 12 + 1
        saida.append((ano, mes))
    return saida


# ── A semeadura de preço (bloco F4) ──────────────────────────────────────────
def propor_precos(faturado: list, termos_por_id: dict, preco_vigente_de,
                  competencia: str) -> dict:
    """O que o Harmonit cobra, virado em proposta de `PRECO` -- sem gravar nada.

    🔵 DECISÃO DELE, 28/10 e 30/10: semear o preço do faturado **com ele como
    autor**, em lote, *"mas deixe as regras do 1 tbm, para quando alguem alterar
    os demais"* -- ou seja, o lote para o que não tem preço e o "adotar" por
    linha para o que mudar depois. A alternativa era digitar 1.189 contratos à
    mão.

    Entradas, todas já lidas por quem tem a conexão:
      `faturado`            linhas de `car_faturado` da competência
      `termos_por_id`       `{termo_id: termo}` (cnpj, numero, empresa)
      `preco_vigente_de`    `termo_id -> valor vigente (str) ou None`

    🚨 O CONTRATO VEM DO `termo_id` QUE O ESPELHO JÁ RESOLVEU, não de uma
    segunda busca por número. A amarração foi feita uma vez, em
    `sync_faturado.resolver`, **dentro do próprio cliente** (medido em 30/10:
    537 de 544, 98,7%). Reprocurar aqui pelo número solto poderia achar o termo
    homônimo de OUTRA empresa -- e é dinheiro.

    🚨 PROPOSTA NÃO É LANÇAMENTO, e a separação é o ponto: o que tem conflito
    sai em `conflitos` e **não entra no lote**, para uma pessoa olhar linha por
    linha. Três conflitos possíveis, e os três já apareceram ou podem aparecer:
    valor diferente do que já está vigente · dois valores no mesmo contrato na
    mesma competência · contrato que esta base não conhece.
    """
    por_termo: dict = {}
    sem_termo = []
    for linha in faturado:
        if linha.get("tipo") not in RECORRENTES:
            continue
        if (linha.get("competencia") or "") != competencia:
            continue
        valor = _texto(linha.get("valor"))
        if not valor:
            continue
        numero = _texto(linha.get("termo_numero"))
        tid = linha.get("termo_id")
        termo = termos_por_id.get(tid) if tid else None
        if termo is None:
            sem_termo.append({
                "lancamento_id": linha.get("id"), "termo_numero": numero or None,
                "contato": linha.get("contato"), "valor": valor,
                "motivo": ("o contrato deste lançamento não existe nesta base "
                           "para este cliente" if numero else
                           "o lançamento não diz número de contrato")})
            continue
        por_termo.setdefault(tid, {"termo": termo, "valores": {}})
        por_termo[tid]["valores"].setdefault(valor, []).append(linha.get("id"))

    propostas, conflitos = [], []
    for termo_id, bloco in por_termo.items():
        termo = bloco["termo"]
        valores = bloco["valores"]
        vigente = preco_vigente_de(termo_id)
        base = {"termo_id": termo_id, "cnpj": termo.get("cnpj"),
                "numero": termo.get("numero"), "empresa": termo.get("empresa"),
                "competencia": competencia, "preco_vigente": vigente}
        if len(valores) > 1:
            conflitos.append({**base, "valores": sorted(valores),
                              "motivo": ("o Harmonit tem mais de um valor neste "
                                         "contrato nesta competência")})
            continue
        valor, ids = next(iter(valores.items()))
        vistos = sorted(i for i in ids if i)
        # 🚨 O documento é o LANÇAMENTO, e é ele que responde "de onde veio este
        # preço?" meses depois. Sem isso a semeadura seria um número sem origem.
        proposta = {**base, "valor": valor, "lancamentos": vistos,
                    "documento": "mov. financeira " +
                                 ", ".join(str(i) for i in vistos)}
        if vigente is None:
            propostas.append(proposta)
        elif _texto(vigente) == valor:
            proposta["motivo"] = "este contrato já tem exatamente este preço vigente"
            conflitos.append(proposta)
        else:
            proposta["motivo"] = (f"já existe preço vigente {vigente!r}, diferente "
                                  f"do faturado {valor!r} -- decidir, não copiar")
            conflitos.append(proposta)

    propostas.sort(key=lambda p: (p["cnpj"] or "", p["numero"] or ""))
    return {
        "competencia": competencia,
        "propostas": propostas,
        "conflitos": conflitos,
        "sem_termo": sem_termo,
        "totais": {"propostas": len(propostas), "conflitos": len(conflitos),
                   "sem_termo": len(sem_termo)},
    }
