"""O lote de contas a receber (`CAR_1.1`, blocos **G1 · G4 · G5**). 2026-11-03.

Spec: `docs/fpsl/32_Contas_a_Receber.md`. Controle da frente:
`C:\\Users\\Lenovo\\Desktop\\CAR_1.1_Financeiro_FPSL.md`, §V6. Mockup aprovado
por ele em 30/10: `https://claude.ai/artifact/RnvbtMzgCE44mgfqQsvKDt`.

🚨 MÓDULO PURO, SEM I/O. Recebe a pré-fatura (`car_prefatura.montar`) e a fila
variável (`car_variavel.fila`) já montadas e devolve o lote. Quem lê banco é o
router.

🚨 UM DOCUMENTO POR CLIENTE, COM LINHAS POR CONTRATO E POR OS. É o encaixe das
duas unidades, e nenhuma das duas é escolha de estilo: o boleto sai do CLIENTE
(decisão dele de 28/10 -- *"a unidade da cobrança é o cliente"*), e o Harmonit
lança por CONTRATO (mensalidade) e por OS (serviço). A linha nasce no formato
dele para que a substituição não precise reinventar a conta.

🚨 FIXO E VARIÁVEL NUNCA SOMADOS NUMA COLUNA SÓ (decisão de desenho 2 do §V6-B):
o fixo vem do contrato e se repete todo mês; o variável vem de OS e não se
repete. Uma coluna só esconderia qual dos dois mudou quando o total muda.

🚨 O VALOR DO FIXO É O DA CAR, NÃO O DO HARMONIT -- e é por isso que o lote de
hoje é quase vazio. `car_evento` tinha **0 linhas** em 03/11: ninguém clicou em
"Adotar as 274 propostas". Usar o valor do espelho como se fosse nosso faria a
CAR *repetir* o Harmonit em vez de substituí-lo, e o número pareceria pronto. O
documento então mostra os dois lados -- **a CAR** e **cobrado hoje** -- e o
cliente sem preço na CAR cai em "ficaram fora" com o caminho para resolver.

🚨 "FICARAM FORA" É TABELA, NÃO AVISO (decisão de desenho 5, e a regra de estilo
dele de 30/10: *"não precisa dos comentarios na tela. atrapalha o
profissionalismo"*): motivo · quantos clientes · onde resolver.
"""
from . import car_variavel as cv

# ── O formato de lançamento do Harmonit, lido do dado, não inventado. ───────
# Medido em 03/11 nas 3.070 linhas de `car_faturado`: mensalidade sai como
# `Mensalidades`/`Boleto` em 2.640 de 2.726, e serviço como
# `Prestação de Serviços`/`Serviços` em 280 de 282. São esses os pares que o
# lote escreve; o resto da base é ruído de digitação do Harmonit (`boleto`,
# `boletos`, `(vários)`), que não se propaga daqui.
CENTRO_MENSALIDADE = "Mensalidades"
CATEGORIA_MENSALIDADE = "Boleto"
CENTRO_SERVICO = "Prestação de Serviços"
CATEGORIA_SERVICO = "Serviços"

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

# ── As pendências de um documento, da mais grave para a menos. ──────────────
# 🚨 A ORDEM É A DA AÇÃO, não a do alfabeto: um cliente pode ter três
# pendências ao mesmo tempo (a XOMV tem), e o selo mostra UMA. Mostrar a menos
# grave mandaria o operador resolver a coisa errada primeiro.
SEM_CLIENTE = "sem cliente nesta base"
SEM_PRECO = "sem preço lançado na CAR"
AMARRACAO = "conferir amarração"
USA_SEM_FATURAR = "usa na WESO e não é faturado"
SEM_PENDENCIA = "sem pendência"

# 🚨 A ORDEM MEDIDA, E ELA IMPORTA: `SEM_PRECO` vem POR ÚLTIMO porque hoje ele
# vale para quase toda a carteira -- `car_evento` tinha 0 linhas em 03/11, logo
# 276 clientes estão sem preço na CAR. Pô-lo no topo faria todas as linhas
# mostrarem o mesmo selo, e o achado que a tela existe para expor (a amarração,
# 71 de 263 clientes) desapareceria no meio.
GRAVIDADE = (SEM_CLIENTE, USA_SEM_FATURAR, AMARRACAO, SEM_PRECO)

ONDE_RESOLVER = {
    SEM_CLIENTE: "Cadastro de clientes (o contatoId do Harmonit não está em `clientes`)",
    SEM_PRECO: "Lançar preço — ou adotar a proposta da semeadura",
    AMARRACAO: "Gestão de Contratos (CTR_1.1): o contrato que fatura não sustenta as placas",
    USA_SEM_FATURAR: "Lançar preço: há placa em uso na WESO e nenhuma mensalidade no mês",
}


def competencia_por_extenso(competencia: str) -> str:
    """`"2026-09"` -> `"setembro de 2026"`. O texto do cabeçalho do lote."""
    ano, _, mes = (competencia or "").partition("-")
    if not (mes.isdigit() and "01" <= mes <= "12"):
        return competencia or ""
    return f"{MESES[int(mes) - 1]} de {ano}"


def descricao_mensalidade(numero_contrato, competencia: str) -> str:
    """A descrição que o Harmonit usa para mensalidade, ao pé da letra.

    🚨 COPIADA DO DADO, NÃO ESCRITA DE NOVO: é esta frase que a leitura do
    espelho (`car_faturado.RE_CONTRATO` e `RE_COMPETENCIA`) sabe reconhecer. Se
    o lote gerasse outro texto, o espelho da passada seguinte não acharia nem o
    contrato nem o período, e o próprio lançamento da CAR cairia em
    "não amarrado".
    """
    ano, _, mes = (competencia or "").partition("-")
    return (f"Faturamento do contrato Nr. {numero_contrato}. "
            f"Mensalidade ref. período {mes}/{ano}.")


def descricao_servico(numero_os) -> str:
    """`"Ordem de Serviço Nr. 16896"` -- o texto que o `RE_OS` reconhece."""
    return f"Ordem de Serviço Nr. {numero_os}"


def _fat(bloco) -> dict:
    return bloco if isinstance(bloco, dict) else {}


def _pendencias(cliente: dict, fixo: str | None, detalhe: dict) -> list:
    """As pendências do documento, medidas -- nenhuma suposta.

    🚨 A amarração (`AMARRACAO`) é o número que a tela existe para mostrar
    (§V6-C): em 71 de 263 clientes faturados (27%) o contrato que o Harmonit
    fatura **não sustenta placa nenhuma**. A régua aqui é exatamente essa: há
    termo faturado no espelho que **não** está entre os contratos que sustentam
    placa cobrável deste cliente.

    ⚠️ Lançamento faturado SEM `termo_id` resolvido não vira amarração: ele não
    aponta contrato nenhum, e acusar amarração ali seria afirmar além do dado.
    """
    pend = []
    com_placa = {c["termo_id"] for c in cliente.get("contratos") or []}
    # 🚨 Termos faturados que NÃO aparecem entre os contratos com placa
    # cobrável. A pré-fatura só lista contrato COM placa no mês, então um termo
    # faturado ausente dela é, por definição, termo que não sustenta placa --
    # a XOMV fatura no 306 e usa 71 placas no 8802.
    # ⚠️ `detalhe` é o bloco do cliente em `faturado.por_cliente`, que é o
    # ÚNICO lugar com as linhas do espelho: o `faturado` resumido do cliente
    # traz só as somas.
    orfaos = [l for l in _fat(detalhe).get("linhas") or []
              if l.get("termo_id") and l["termo_id"] not in com_placa
              and l.get("tipo") == "mensalidade"]
    if orfaos and com_placa:
        pend.append(AMARRACAO)
    if fixo is None and com_placa:
        pend.append(SEM_PRECO)
    if cliente.get("em_uso_sem_faturar"):
        pend.append(USA_SEM_FATURAR)
    # ⚠️ `SEM_CLIENTE` NÃO É PENDÊNCIA DE DOCUMENTO, e por isso não entra aqui:
    # sem cliente não existe documento nenhum a que pendurá-la. Ela vive na
    # tabela "ficaram fora", alimentada pelos totais da fila variável.
    return sorted(set(pend), key=lambda p: GRAVIDADE.index(p))


def _documento_do_cliente(cliente: dict, variavel: dict | None,
                          competencia: str, detalhe: dict | None = None) -> dict:
    fat = _fat(cliente.get("faturado"))
    fixo_linhas = []
    for ct in cliente.get("contratos") or []:
        valor = cv.somar_textos([l.get("valor") for l in ct.get("linhas") or []])
        fat_termo = _fat(ct.get("faturado"))
        fixo_linhas.append({
            "termo_id": ct.get("termo_id"),
            "numero": ct.get("numero"),
            "empresa": ct.get("empresa"),
            "assinado": ct.get("assinado"),
            "situacao": ct.get("situacao"),
            "placas": ct.get("placas"),
            "em_uso": ct.get("em_uso"),
            "com_valor": ct.get("com_valor"),
            "sem_valor": ct.get("sem_valor"),
            # 🚨 OS DOIS LADOS, LADO A LADO: o que a CAR afirma e o que o
            # Harmonit cobra hoje. Uma coluna só faria a tela parecer pronta.
            "valor": valor,
            "cobrado_hoje": fat_termo.get("mensalidade"),
            # Da onde veio o valor da CAR -- "do termo" e "do operador" não são
            # a mesma afirmação, e a semeadura (F4) é a terceira.
            "fonte_do_valor": next(
                (l.get("fonte_do_valor") for l in ct.get("linhas") or []
                 if l.get("valor")), None),
            "divergencia": ct.get("divergencia"),
            # 🚨 CANCELADO NÃO GERA LINHA, e por isso o campo é booleano vindo
            # da pré-fatura: a `situacao` INATIVO junta termo sem assinatura,
            # cancelado e sem placa ativa, e só o cancelamento proíbe cobrar.
            # Termo sem assinatura segue cobrável -- é o caso da MOTO HELP, que
            # o Harmonit fatura hoje.
            "cancelado": bool(ct.get("cancelado")),
            "situacao_motivo": ct.get("motivo"),
        })
    fixo_linhas.sort(key=lambda c: (-(cv._centavos(c["valor"]) or 0),
                                    c["numero"] or ""))
    # 🚨 O FIXO SOMA SÓ O QUE PODE SER COBRADO. Contrato cancelado continua na
    # tabela, visível e com o motivo -- mas fora da soma e fora das linhas.
    # Somá-lo faria o total prometer dinheiro que o cancelamento já tirou.
    fixo = cv.somar_textos([c["valor"] for c in fixo_linhas
                            if not c["cancelado"]])
    cancelados = [c for c in fixo_linhas if c["cancelado"] and c["valor"]]

    var = variavel or {}
    var_linhas = var.get("os") or []
    variavel_total = var.get("total")

    pend = _pendencias(cliente, fixo, detalhe or {})
    return {
        "cnpj": cliente.get("cnpj"),
        "nome": cliente.get("nome"),
        "contratos": len(fixo_linhas),
        "placas": cliente.get("placas"),
        "em_uso": cliente.get("em_uso"),
        "fixo": fixo,
        "fixo_linhas": fixo_linhas,
        "variavel": variavel_total,
        "variavel_linhas": var_linhas,
        "total": cv.somar_textos([fixo, variavel_total]),
        # 🚨 O MESMO VALOR EM CENTAVOS, PARA A TELA SOMAR A SELEÇÃO SEM
        # REIMPLEMENTAR A CONVERSÃO. A régua de ler "R$ 1.234,56" fica num lugar
        # só, aqui no servidor -- foi conversão de dinheiro em dois lugares que
        # fez R$ 200,53 virar R$ 20.053,00 em 30/10. Somar inteiro não é
        # converter: a tela apenas adiciona e formata.
        # ⚠️ `None` continua `None`: nulo não vira 0 nem na ponte.
        "fixo_centavos": cv._centavos(fixo),
        "variavel_centavos": cv._centavos(variavel_total),
        "total_centavos": cv._centavos(cv.somar_textos([fixo, variavel_total])),
        # O que o Harmonit cobra do cliente nesta competência, para a virada:
        # enquanto os dois rodam, o risco é dois boletos (bloco G6).
        "cobrado_hoje": fat.get("mensalidade"),
        "avulso_hoje": fat.get("avulso"),
        "recebido_hoje": fat.get("recebido"),
        # Contrato cancelado COM preço lançado: não entra na conta, e aparece.
        "contratos_cancelados": len(cancelados),
        "pendencias": pend,
        "situacao": pend[0] if pend else SEM_PENDENCIA,
        # 🚨 GERÁVEL é diferente de SEM PENDÊNCIA: um cliente com amarração a
        # conferir pode ser gerado (o preço existe), e um sem pendência nenhuma
        # mas sem preço na CAR não pode. Confundir os dois travaria a operação
        # ou geraria documento vazio.
        "geravel": bool(cv.somar_textos([fixo, variavel_total])),
    }


def lancamentos_do_documento(doc: dict, competencia: str,
                             vencimento: str | None) -> list:
    """As linhas de lançamento de UM documento, no formato do Harmonit.

    Uma linha por contrato com valor (mensalidade) e uma por OS (serviço). 🚨 É
    aqui que o lote se torna exportável: a `descricao`, o `centroCusto` e a
    `categoria` são os do Harmonit, medidos no espelho.
    """
    linhas = []
    for c in doc.get("fixo_linhas") or []:
        if not c.get("valor") or c.get("cancelado"):
            continue
        linhas.append({
            "cnpj": doc["cnpj"], "cliente": doc["nome"],
            "tipo": "mensalidade",
            "termo_id": c["termo_id"], "numero_contrato": c["numero"],
            "descricao": descricao_mensalidade(c["numero"], competencia),
            "centro_custo": CENTRO_MENSALIDADE,
            "categoria": CATEGORIA_MENSALIDADE,
            "vencimento": vencimento,
            "valor": c["valor"],
        })
    for o in doc.get("variavel_linhas") or []:
        linhas.append({
            "cnpj": doc["cnpj"], "cliente": doc["nome"],
            "tipo": "servico",
            "numero_os": o["numero_os"],
            "descricao": descricao_servico(o["numero_os"]),
            "centro_custo": CENTRO_SERVICO,
            "categoria": CATEGORIA_SERVICO,
            "vencimento": vencimento,
            "valor": o["total"],
        })
    return linhas


def montar(prefatura: dict, variavel: dict, vencimento: str | None = None,
           apenas=None) -> dict:
    """O lote da competência: um documento por cliente, e as linhas do Harmonit.

    `apenas` é a seleção do operador (lista de CNPJ). `None` = a carteira
    inteira. 🚨 **NADA É GRAVADO AQUI**: este módulo é puro, e gerar é a decisão
    de quem clica -- a mesma régua da semeadura, onde eu não lancei os 274
    eventos porque o autor é quem clica.

    ⚠️ Cliente que só tem variável (OS, sem contrato com placa no mês) **entra**
    no lote: é cobrança real. Ele não apareceria se o lote fosse construído
    sobre a pré-fatura sozinha.
    """
    competencia = prefatura.get("competencia")
    por_cnpj = {c["cnpj"]: c for c in prefatura.get("clientes") or []}
    var_por_cnpj = dict(variavel.get("por_cliente") or {})
    # O detalhe do espelho, por cliente: é o único lugar com as LINHAS do que o
    # Harmonit cobra, e é delas que sai a amarração.
    detalhes = _fat(prefatura.get("faturado")).get("por_cliente") or {}
    selecao = set(apenas) if apenas is not None else None

    documentos = []
    for cnpj in sorted(set(por_cnpj) | set(var_por_cnpj)):
        cliente = por_cnpj.get(cnpj) or {
            "cnpj": cnpj,
            "nome": (var_por_cnpj.get(cnpj) or {}).get("cliente"),
            "contratos": [], "placas": 0, "faturado": {}}
        doc = _documento_do_cliente(cliente, var_por_cnpj.get(cnpj), competencia,
                                    detalhes.get(cnpj))
        doc["selecionado"] = (selecao is None) or (cnpj in selecao)
        documentos.append(doc)

    # 🔵 A ORDEM: o maior valor primeiro, como a tela do mockup declara no
    # rodapé ("ordenados por valor"). O que não tem valor vai para o fim, mas
    # NÃO desaparece -- é justo ele que precisa de ação.
    documentos.sort(key=lambda d: (-(cv._centavos(d["total"]) or 0),
                                   d["nome"] or d["cnpj"]))

    gerados = [d for d in documentos if d["selecionado"] and d["geravel"]]
    linhas = []
    for d in gerados:
        linhas.extend(lancamentos_do_documento(d, competencia, vencimento))

    fora = _fora(documentos, variavel)
    return {
        "competencia": competencia,
        "competencia_extenso": competencia_por_extenso(competencia),
        "vencimento": vencimento,
        "documentos": documentos,
        "lancamentos": linhas,
        "fora": fora,
        "totais": {
            "documentos": len(documentos),
            "geraveis": sum(1 for d in documentos if d["geravel"]),
            "selecionados": sum(1 for d in documentos if d["selecionado"]),
            "a_gerar": len(gerados),
            "lancamentos": len(linhas),
            "fixo": cv.somar_textos([d["fixo"] for d in gerados]),
            "variavel": cv.somar_textos([d["variavel"] for d in gerados]),
            "total": cv.somar_textos([d["total"] for d in gerados]),
            # O outro lado da virada, sempre visível: o que o Harmonit cobra da
            # mesma carteira na mesma competência.
            "cobrado_hoje": cv.somar_textos([d["cobrado_hoje"]
                                             for d in documentos]),
            "com_pendencia": sum(1 for d in documentos if d["pendencias"]),
            # 🚨 DOIS NÚMEROS, E A DIFERENÇA É O QUE A TELA MOSTRA. Medido em
            # 03/11 na produção: **481 de 481** documentos acusam "sem preço na
            # CAR", porque `car_evento` está vazia -- ninguém adotou as 274
            # propostas. Um contador só mostraria "481 exigem conferência", e o
            # achado de verdade (70 com amarração errada, 26 usando sem
            # faturar) afogaria no meio. `sem_preco` é o ESTADO da carteira;
            # `com_achado` é a fila de trabalho.
            "sem_preco": sum(1 for d in documentos
                             if SEM_PRECO in d["pendencias"]),
            "com_achado": sum(1 for d in documentos
                              if [p for p in d["pendencias"] if p != SEM_PRECO]),
        },
        # `M12` como ESTADO, não como parágrafo (regra dele de 30/10): o que
        # esta tela não faz fica dito em campo, e a tela desenha isso num selo.
        "limites": {
            "emite_boleto": False,
            "escreve_no_harmonit": False,
            "porque": ("a API financeira do Harmonit é 100% leitura: não existe "
                       "rota de criar cobrança, faturar ou emitir. O lote é a "
                       "lista pronta para lançamento (bloco G6/D8)"),
            "harmonit_continua_faturando": True,
            "risco": ("enquanto o automático do Harmonit não for desligado, "
                      "lançar daqui faz o cliente receber dois boletos"),
        },
    }


def _fora(documentos: list, variavel: dict) -> list:
    """A tabela "ficaram fora": motivo · quantos · onde resolver."""
    contagem: dict = {}
    for d in documentos:
        for p in d["pendencias"]:
            contagem[p] = contagem.get(p, 0) + 1
    fora = [{"motivo": m, "clientes": n, "onde": ONDE_RESOLVER.get(m, "")}
            for m, n in contagem.items()]
    cancelados = sum(d.get("contratos_cancelados") or 0 for d in documentos)
    if cancelados:
        fora.append({
            "motivo": "contrato com preço na CAR e cobrança cancelada",
            "clientes": cancelados,
            "onde": "Contas a Receber › carteira: renovar o contrato, se for o caso"})
    sem_cliente = (variavel.get("totais") or {}).get("os_sem_cliente") or 0
    if sem_cliente:
        fora.append({
            "motivo": "OS sem cliente nesta base",
            "clientes": sem_cliente,
            "onde": ONDE_RESOLVER[SEM_CLIENTE],
            "valor": (variavel.get("totais") or {}).get("sem_cliente"),
        })
    for estado, n in ((variavel.get("totais") or {}).get("descartadas") or {}).items():
        fora.append({"motivo": f"OS fora da fila: {cv.PORQUE[estado]}",
                     "clientes": n, "onde": "Conferência da OS no Harmonit"})
    fora.sort(key=lambda f: -f["clientes"])
    return fora


def para_csv(lote: dict) -> str:
    """Uma linha por lançamento. Separador `;`, como o resto da casa."""
    saida = ["cnpj;cliente;tipo;contrato;numero_os;descricao;centro_custo;"
             "categoria;vencimento;valor"]
    for l in lote.get("lancamentos") or []:
        saida.append(";".join(str(x if x is not None else "") for x in (
            l["cnpj"], l["cliente"], l["tipo"], l.get("numero_contrato"),
            l.get("numero_os"), (l["descricao"] or "").replace(";", ","),
            l["centro_custo"], l["categoria"], l["vencimento"], l["valor"])))
    return "\n".join(saida)
