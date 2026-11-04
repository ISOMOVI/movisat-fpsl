"""A parte variável do contas a receber (`CAR_1.1`, bloco **G2**). 2026-11-03.

Spec: `docs/fpsl/32_Contas_a_Receber.md`. Controle da frente:
`C:\\Users\\Lenovo\\Desktop\\CAR_1.1_Financeiro_FPSL.md`, §V6.

🚨 MÓDULO PURO, SEM I/O -- no molde do `car_motor.py` e do `car_faturado.py`.
Quem fala com o banco é o router; aqui mora só a régua, e por isso ela é
testável sem rede e sem banco.

🚨 A RÉGUA É DELE, PORTADA AO PÉ DA LETRA (30/10): *"os variaveis que vierem de
OS do tipo financeiro que estão marcados para cobrar e finalizados"*. As três
pernas, cada uma medida antes de virar código:

  1. **"OS do tipo financeiro" é a SITUAÇÃO 15746 "Financeiro"**, não um tipo:
     não existe tipo "Financeiro" entre os 29 tipos de OS do Harmonit. O nome
     mudou em 29/10 -- 15746 passou a se chamar "Financeiro" -- e três telas
     ainda falavam o nome velho.
  2. **"marcados para cobrar" é o booleano `cobrar` POR ITEM**
     (`OrdemServicoXMaterialViewModel`: `cobrar`, `valor`, `valorTotal`). Medido
     em 30/10: a soma dos itens `cobrar` **reproduz o que o Harmonit faturou da
     OS** em 9 de 12 conferidas; nas outras 3 a diferença vai de centavos a
     R$ 19,94, o que é **divergência para apontar**, não régua nova. E `cobrar`
     é cobrar DO CLIENTE, não pagar técnico: PAGAMENTO DE TÉCNICO e KM vêm
     `cobrar = false` em 70 de 71 itens.
  3. **"finalizados" é `status_str = 'Finalizado'`** da `os_historico`.

🚨 A FONTE É LOCAL, E ISSO É DESENHO: a `os_historico` já guarda situação,
status e `materiais_json` de cada OS (varredura do `os_scan_router`, de 5 em 5
min). Não há no `swagger.json` rota que LISTE OS por situação -- só
`ObterOrdemServico` por `osId` e `ObterOrdemServicoPorNumero`. Montar esta fila
pelo Harmonit seria uma chamada por OS; pela varredura que já roda, é uma
consulta.

⚠️ O LIMITE DA DATA, DITO EM VEZ DE ESCONDIDO: a `os_historico` guarda
`data_previsao`, **não** a data de finalização (ela só existe no
`ObterTimeLine`, uma chamada por OS). Então a competência de uma OS sai da
PREVISÃO, e quem olha a tela lê isso na coluna. Chamar previsão de
"finalizada em" seria a tela mentindo pelo rótulo.

🚨 JÁ FATURADA NÃO ENTRA, e a prova é do próprio espelho: `car_faturado` guarda
`numero_os` de todo lançamento de serviço do Harmonit (280 em 30/10). O Harmonit
cobra a parte variável em dia -- 48 das 51 OS finalizadas com item a cobrar já
estavam faturadas --, então gerar sem esse filtro mandaria o cliente receber
**dois** boletos da mesma OS. É o mesmo risco da virada que o bloco G6 trata.

⚠️ `numero_os` do espelho é comparado CRU, sem competência: o lançamento de
serviço do Harmonit **não tem** período de referência na descrição (é o grupo
"sem competência" da `faturado_do_mes`), então restringir a comparação a um mês
deixaria passar OS já faturada em outro vencimento.
"""

# ── A situação da OS financeira. Mesmo valor de `operacoes_config` e de
#    `templates_config`, repetido aqui de propósito: este módulo é puro e não
#    importa nada de `operacoes_*` (a aba Operações é intocável). ────────────
SITUACAO_FINANCEIRO = 15746

# O status do Harmonit que quer dizer "acabou". Texto, como ele chega na
# `os_historico.status_str` -- e `status = 3` é o mesmo fato pelo número.
STATUS_FINALIZADO = "Finalizado"

# ── Os estados de uma OS nesta fila. Enum no CÓDIGO, não em CHECK: não há
#    tabela nova neste bloco, a fila é derivada a cada leitura. ─────────────
A_GERAR = "a_gerar"
JA_FATURADA = "ja_faturada"
NAO_FINALIZADA = "nao_finalizada"
SEM_ITEM_A_COBRAR = "sem_item_a_cobrar"
ESTADOS = frozenset({A_GERAR, JA_FATURADA, NAO_FINALIZADA, SEM_ITEM_A_COBRAR})

# O motivo de cada estado, em uma frase. 🚨 Estado sem causa manda o operador
# abrir a OS no Harmonit para descobrir por que ela não entrou -- é a mesma
# régua do `car_contrato.motivo`.
PORQUE = {
    A_GERAR: "finalizada, com item marcado para cobrar, e o Harmonit ainda não faturou",
    JA_FATURADA: "o Harmonit já lançou esta OS no financeiro",
    NAO_FINALIZADA: "a OS não está finalizada",
    SEM_ITEM_A_COBRAR: "nenhum item da OS está marcado para cobrar",
}


def _texto(v) -> str:
    return "" if v is None else str(v).strip()


def valor_texto(v) -> str | None:
    """Número do Harmonit -> dinheiro em texto brasileiro: `"200,53"`.

    🚨 MESMA RAZÃO DO `car_faturado.valor_texto`, e o defeito que ela conserta é
    real: o Harmonit manda `200.53` (ponto decimal) e o `_centavos` desta casa
    lê o ponto como separador de **milhar** -- R$ 200,53 viraria R$ 20.053,00 na
    soma. Aqui a entrada é `valorTotal` do item da OS, que é `float` no JSON.
    """
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return f"{v:.2f}".replace(".", ",")
    return _texto(v) or None


def competencia_da_os(data_previsao) -> str | None:
    """`"16/09/2026 14:45:00"` -> `"2026-09"`. `None` quando o texto não diz.

    ⚠️ É a PREVISÃO, não a finalização -- ver o aviso do topo. E `None` nunca
    vira o mês de hoje: OS sem data não pertence a competência nenhuma, e
    chutar o mês corrente a faria aparecer numa fatura por acidente.
    """
    t = _texto(data_previsao)
    if len(t) < 10 or t[2] != "/" or t[5] != "/":
        return None
    dia, mes, ano = t[0:2], t[3:5], t[6:10]
    if not (dia.isdigit() and mes.isdigit() and ano.isdigit()):
        return None
    if not ("01" <= mes <= "12"):
        return None
    return f"{ano}-{mes}"


def itens_a_cobrar(materiais) -> list:
    """Os itens da OS com `cobrar` verdadeiro, em ordem de valor.

    ⚠️ `materiais` é a lista já desserializada -- quem lê o campo de texto do
    banco e o converte é o router. Módulo puro não lê arquivo nem banco, e a
    trava do `teste_car_variavel` confere isso no próprio fonte.

    🚨 Item com `cobrar` e valor ZERO continua na lista, marcado. Ele existe no
    dado (ENTREGA OS vem assim) e some-lo em silêncio faria a OS parecer ter
    menos item do que tem -- mas ele não muda a soma.
    """
    saida = []
    for item in materiais or []:
        if not isinstance(item, dict) or not item.get("cobrar"):
            continue
        saida.append({
            "id": item.get("id"),
            "descricao": _texto(item.get("descricao")) or None,
            "quantidade": item.get("quantidade"),
            "valor": valor_texto(item.get("valor")),
            "valor_total": valor_texto(item.get("valorTotal")),
            "comodato": bool(item.get("comodato")),
        })
    saida.sort(key=lambda i: (-(_centavos(i["valor_total"]) or 0),
                              i["descricao"] or ""))
    return saida


def _centavos(texto):
    """`"R$ 1.234,56"` -> 123456. `None` quando não dá para converter.

    ⚠️ Repetido do `car_prefatura` de propósito: lá ele é privado do módulo que
    soma a pré-fatura, e este módulo é puro e não importa aquele (que lê banco).
    A régua é a mesma e os dois têm teste.
    """
    if not texto:
        return None
    limpo = "".join(ch for ch in str(texto) if ch.isdigit() or ch in ",.")
    limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return int(round(float(limpo) * 100))
    except (ValueError, TypeError):
        return None


def somar_textos(valores) -> str | None:
    """Soma valores em texto. `None` quando nada soma -- nunca `'0,00'`.

    🚨 `None` E `'0,00'` SÃO AFIRMAÇÕES OPOSTAS: zero diz "esta OS não cobra
    nada", nulo diz "não há item a cobrar aqui". A tela mostra a diferença.
    """
    centavos, achou = 0, False
    for v in valores or []:
        c = _centavos(v)
        if c is None:
            continue
        centavos += c
        achou = True
    if not achou:
        return None
    return f"{centavos // 100},{centavos % 100:02d}"


def classificar(os_linha: dict, faturadas=None) -> dict:
    """Uma OS da `os_historico` -> a linha da fila variável.

    `os_linha` traz `numero_os`, `os_id`, `situacao_id`, `status_str`,
    `cliente_id`, `data_previsao` e `materiais` (lista já desserializada).
    `faturadas` é o conjunto de `numero_os` que o Harmonit já lançou.

    🚨 A ORDEM DOS CORTES É A RÉGUA DELE, e ela importa: primeiro "já faturada"
    (o risco de dois boletos ganha de tudo), depois "finalizada", depois "tem
    item a cobrar". Uma OS pode falhar em mais de um critério; o estado diz o
    PRIMEIRO que a barrou, e é esse que o operador precisa resolver.

    ⚠️ Esta função NÃO julga a situação 15746: quem filtra por ela é a consulta,
    e o parâmetro é explícito lá. Classificar OS de outra situação aqui faria o
    módulo decidir escopo em silêncio.
    """
    faturadas = faturadas or set()
    numero = os_linha.get("numero_os")
    itens = itens_a_cobrar(os_linha.get("materiais"))
    total = somar_textos([i["valor_total"] for i in itens])

    if numero in faturadas:
        estado = JA_FATURADA
    elif _texto(os_linha.get("status_str")) != STATUS_FINALIZADO:
        estado = NAO_FINALIZADA
    elif total is None:
        estado = SEM_ITEM_A_COBRAR
    else:
        estado = A_GERAR

    return {
        "numero_os": numero,
        "os_id": os_linha.get("os_id"),
        "situacao_id": os_linha.get("situacao_id"),
        "status": _texto(os_linha.get("status_str")) or None,
        "cliente_id": os_linha.get("cliente_id"),
        "cnpj": os_linha.get("cnpj"),
        "cliente": os_linha.get("cliente"),
        # 🚨 O cliente da OS pode não existir nesta base (`clientes` é indexada
        # pelo `harmonit_id`): medido em 03/11, a OS 16846 tem `cliente_id`
        # 1036572, que não está lá. Ela NÃO é escondida -- aparece na tela com
        # a causa, e é o bloco G5 ("ficaram fora") que a recolhe.
        "cliente_conhecido": bool(os_linha.get("cnpj")),
        # ⚠️ PREVISÃO, não finalização. O nome do campo diz o que ele é.
        "data_previsao": _texto(os_linha.get("data_previsao")) or None,
        "competencia": competencia_da_os(os_linha.get("data_previsao")),
        "itens": itens,
        "itens_a_cobrar": len(itens),
        "total": total,
        "estado": estado,
        "porque": PORQUE[estado],
    }


def fila(linhas, competencia: str | None = None, faturadas=None) -> dict:
    """A fila variável da competência, agrupada por CLIENTE.

    Devolve `{"competencia", "por_cliente", "a_gerar", "fora", "totais"}`.

    🚨 AGRUPA POR CLIENTE porque é do cliente que sai o boleto (decisão dele de
    28/10) -- mas a LINHA do lançamento continua por OS, que é como o Harmonit
    lança. As duas unidades convivem, e é esse encaixe que a tela mostra.

    ⚠️ `competencia = None` traz TODAS as competências. A tela sempre passa um
    mês; o `None` serve à conferência ("esta OS caiu em que mês?").
    """
    por_cliente: dict = {}
    fora: list = []
    a_gerar: list = []
    descartadas: dict = {}

    for linha in linhas or []:
        item = classificar(linha, faturadas)
        if competencia and item["competencia"] != competencia:
            # Não é descarte: é outra competência. Não entra em nenhuma conta
            # desta, e não vira "ficou fora" (ficar fora é do mês que se gera).
            continue
        if item["estado"] != A_GERAR:
            descartadas[item["estado"]] = descartadas.get(item["estado"], 0) + 1
            fora.append(item)
            continue
        a_gerar.append(item)
        if not item["cliente_conhecido"]:
            # Fica na fila, visível, mas sem cliente não há documento: o lote a
            # recolhe em "ficaram fora" com o motivo.
            continue
        bloco = por_cliente.setdefault(item["cnpj"], {
            "cnpj": item["cnpj"], "cliente": item["cliente"],
            "os": [], "total": None})
        bloco["os"].append(item)

    for bloco in por_cliente.values():
        bloco["total"] = somar_textos([o["total"] for o in bloco["os"]])
        bloco["os"].sort(key=lambda o: o["numero_os"] or 0)

    return {
        "competencia": competencia,
        "por_cliente": por_cliente,
        "a_gerar": sorted(a_gerar, key=lambda o: o["numero_os"] or 0),
        # 🚨 LISTA, NÃO AVISO (regra de tela dele, 30/10): o que ficou fora
        # aparece com motivo e número, para agir -- não como parágrafo.
        "fora": sorted(fora, key=lambda o: o["numero_os"] or 0),
        "totais": {
            "os_a_gerar": len(a_gerar),
            "clientes": len(por_cliente),
            "total": somar_textos([o["total"] for o in a_gerar
                                   if o["cliente_conhecido"]]),
            # Separado do total: dinheiro de OS sem cliente nesta base existe,
            # mas não pode virar documento. Somar junto inflaria o lote.
            "sem_cliente": somar_textos([o["total"] for o in a_gerar
                                         if not o["cliente_conhecido"]]),
            "os_sem_cliente": sum(1 for o in a_gerar if not o["cliente_conhecido"]),
            "descartadas": descartadas,
        },
        "regra": {
            "situacao_id": SITUACAO_FINANCEIRO,
            "status": STATUS_FINALIZADO,
            "porque": ("situação 15746 Financeiro, finalizada, com item marcado "
                       "para cobrar, que o Harmonit ainda não faturou"),
            "data": ("a competência da OS sai da data de PREVISÃO: a varredura "
                     "local não guarda a data de finalização"),
        },
    }
