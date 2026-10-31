"""Pré-fatura da competência (`CAR_1.1`) — etapa E4. 2026-10-28.

Spec: `docs/fpsl/32_Contas_a_Receber.md`.

🚨 LÊ, NUNCA GRAVA. Nenhum `INSERT`, `UPDATE` ou `DELETE` -- travado por teste.
A pré-fatura de um mês é uma **função** do contrato naquele mês, não uma tabela:
é o que impede o recebível de congelar e de ninguém saber, no mês seguinte, por
que aquele valor está lá (doc 33 §11).

🚨 A SITUAÇÃO DA PLACA É RECALCULADA, NÃO LIDA DO CACHE. `contrato_placa` é o
retrato de **hoje**; perguntar "o que outubro cobrava" exige rodar o motor da
CTR com a data daquele mês. Ler o cache daria o mês errado em todo mês passado
-- e o aviso prévio de 90 dias vence pelo calendário, sem evento nenhum para
disparar a conta. Por isso aqui se reusa `contratos_registro.termos_de_todos`
(2 consultas) e `contratos_eventos.situacao_das_placas`, em vez de um `SELECT`
próprio em `contrato_placa`. Prova medida em 28/10: o cache, recalculado às
11:46 do mesmo dia, dizia **2.952** cobráveis; a releitura de 31/10 dá **2.946**.
Os 6 de diferença são aviso prévio que vence nos últimos 3 dias do mês.

🚨 O MÊS SE DEFINE POR "ESTEVE NO CONTRATO EM QUALQUER DIA DELE", e isso é regra
de receita: ver `cobraveis_do_mes`. Olhar só o último dia perdia **47 placas**
em outubro de 2026, em silêncio.

🚨 O QUE A DECISÃO 1 DELE (28/10) PRODUZ, MEDIDO NO MESMO DIA: das **2.952
placas cobráveis**, **ZERO** tem valor em `contrato_item` -- o único valor da
base inteira é de uma placa RESCINDIDA. Então a pré-fatura nasce com total
`None` e 2.952 linhas sem valor, **e isso aparece em `totais`**. Valor nulo
jamais vira `R$ 0,00`: zero afirma que a placa não cobra nada, nulo com motivo
diz a verdade, que é "não sabemos".

⚠️ A PARTE VARIÁVEL (decisão 6 dele: "mínimo de 1 e máximo depende") ainda NÃO
entra, e a resposta **declara isso** em `variavel`, com o motivo -- em vez de a
tela somar só a mensalidade e deixar o operador achar que é o total.

🆕 30/10, blocos **F2** e **F3**:

🚨 AS TRÊS COLUNAS NASCEM NO **CLIENTE**, não no termo -- e isso é conserto de um
erro meu de 28/10, medido duas vezes. Por termo, "usa e não é faturado" dava 512
contratos e R$ 198 mil; **por cliente são 25 clientes e R$ 11.710**, porque a
XOMV é faturada no termo 306 e usa 53 placas nos termos 8531/8754/8802. A unidade
da cobrança é o CLIENTE, porque é dele que sai o boleto; o termo é a trilha do
documento.

🚨 O COBRADO SAI DE `car_faturado`, PELA **COMPETÊNCIA DA DESCRIÇÃO**, e o eixo é
competência, não caixa. Lançamento cuja descrição não diz o período **não entra
na conta do mês**: ele aparece em `faturado.nao_amarrados` com o motivo. Somar
pelo vencimento diria o mês errado em 233 de 261 casos medidos.

🚨 O "EM USO NA WESO" É **INJETADO**, não lido daqui. `montar` recebe o mapa
`{chave: situação}` de quem o tem (o router, via
`services.contratos_auditoria._weso_do_cache`, cron 04:15). Duas razões: esta
função não abre arquivo nenhum hoje e não vai começar; e teste que lê o cache
real da VPS deixaria de ser determinístico. Sem o mapa, `em_uso_weso` é **`None`
em toda linha** -- nunca `False`, que afirmaria "não está instalada".

🔵 DECISÃO DELE, 30/10: *"interseção, com as duas colunas visíveis"*. Então a
régua da cobrança é a WESO em uso, **e a tela mostra as duas** com a diferença
por cliente -- trocar o número sem mostrar o que saiu seria a mesma tela que
mente, com outro número.
"""
from . import car_faturado as cf
from . import car_motor as motor
from . import contratos_eventos as ctr_motor
from . import contratos_registro as reg

# Precedência quando (cnpj, número) aponta dois termos. Medido em 28/10: 555
# pares assim, **todos** MOVISAT × INSTITUTO e **zero** dentro da mesma empresa;
# nas placas cobráveis isso atinge 271 de 2.952 (9,2%).
# 🚨 NÃO É INVENÇÃO MINHA: a regra do projeto é que todo o Instituto migrou para
# a Movisat e "expectativa atual = só os termos da Movisat". Sem precedência, o
# preço de 9% das placas ficaria pendurado no documento errado -- ou duplicado,
# se o lançamento em lote rodasse nos dois termos homônimos.
PRECEDENCIA_EMPRESA = ("MOVISAT", "CADASTRO ANTIGO", "INSTITUTO")

# 🔵 A régua dele: *"a cobrança é pela WESO em uso (rastreador Instalado)"*
# (`C:\\code\\termos_harmonit\\contas_a_receber.py`). Situação intermediária
# (Estoque, Bancada, Manutenção, Comodato) **não** é uso -- e aparece com o nome
# na tela, em vez de virar um "não" sem causa. Medido no cache de 30/10: 1.860
# Instalado, 34 Comodato, 13 Estoque, 1 Manutenção, 1 Bancada.
SITUACAO_EM_USO = "Instalado"


def resolver_termo(termos, numero):
    """Qual termo o `termo_vigente` da placa quer dizer, ou `None`.

    `contrato_placa.termo_vigente` guarda o **número** do termo (`'8668'`), não
    o `id` -- e número se repete entre empresas. Desempata por
    `PRECEDENCIA_EMPRESA`; empate dentro da mesma empresa (nunca visto em
    28/10) cai no de `id` maior, que é o mais recente.
    """
    alvo = str(numero or "").strip()
    if not alvo:
        return None
    candidatos = [t for t in termos if str(t.get("numero") or "").strip() == alvo]
    if not candidatos:
        return None
    if len(candidatos) == 1:
        return candidatos[0]

    def ordem(t):
        emp = (t.get("empresa") or "").upper()
        pos = PRECEDENCIA_EMPRESA.index(emp) if emp in PRECEDENCIA_EMPRESA \
            else len(PRECEDENCIA_EMPRESA)
        return (pos, -(t.get("id") or 0))

    return sorted(candidatos, key=ordem)[0]


def cobraveis_do_mes(termos, inicio, fim):
    """As placas cobráveis da competência: as que estiveram no contrato em
    **qualquer dia** do mês. Devolve `(cobraveis, entrou, saiu)`.

    🚨 O INSTANTE QUE DEFINE O MÊS É REGRA DE RECEITA, NÃO DETALHE — e a
    primeira versão disto olhava só o ÚLTIMO dia, o que perdia dinheiro em
    silêncio. Medido na base real em 28/10: no dia 1º de outubro havia **2.993**
    placas cobráveis e no dia 31 havia **2.946** — **47 saíram no meio do mês**
    (e nenhuma entrou). Pela decisão dele de 28/10, "cobra cheio, sem pro rata",
    essas 47 **tiveram serviço em outubro** e são cobradas; olhar só o dia 31 as
    deixaria de fora sem ninguém notar.

    ⚠️ O preço disso, dito: substituição dentro do mesmo mês (uma placa sai, a
    outra entra) gera **duas** linhas para um veículo só. Em outubro de 2026 isso
    aconteceu **zero** vezes (nenhuma placa entrou), mas vai acontecer — então
    cada linha carrega `entrou_no_mes`/`saiu_no_mes` e a tela mostra, em vez de
    o operador descobrir pela soma.

    🟡 Trocar a régua para "só o último dia" ou "só o primeiro" é mudar as duas
    linhas abaixo. Está na lista de decisões abertas do documento de controle.
    """
    no_inicio = ctr_motor.situacao_das_placas(termos, inicio)
    no_fim = ctr_motor.situacao_das_placas(termos, fim)

    def cob(d):
        return {k: v for k, v in d.items()
                if (v.get("situacao") or "") in motor.SITUACOES_COBRAVEIS}

    ci, cf = cob(no_inicio), cob(no_fim)
    # Mostra a situação do FIM quando existe (é o estado mais recente do mês);
    # para quem saiu, mostra a do início, que é como a placa estava enquanto
    # havia serviço.
    cobraveis = {k: cf.get(k) or ci[k] for k in (set(ci) | set(cf))}
    return cobraveis, set(cf) - set(ci), set(ci) - set(cf)


def nomes_dos_clientes(conn) -> dict:
    return {c: n for c, n in conn.execute("SELECT cnpj, nome FROM contrato_cliente")}


def itens_com_valor(conn) -> dict:
    """`contrato_item.valor_mensal` por (cnpj, placa_chave). A fonte primeira do
    valor, pela regra dele de 13/10: "o valor vem do termo"."""
    return {(c, p): v for c, p, v in conn.execute(
        "SELECT cnpj, placa_chave, valor_mensal FROM contrato_item "
        "WHERE valor_mensal IS NOT NULL AND trim(valor_mensal) <> ''")}


def faturado_do_mes(conn, competencia: str) -> dict:
    """O que o Harmonit JÁ cobra naquela competência, agrupado por CLIENTE.

    Devolve `{"lido", "por_cliente", "nao_amarrados", "totais", "lido_em"}`.

    🚨 `lido = False` QUANDO A TABELA ESTÁ VAZIA, e a tela diz isso em vez de
    desenhar R$ 0 em toda linha. "O Harmonit não cobra nada deste cliente" e "a
    rotina do espelho nunca rodou" são afirmações opostas, e em 30/10 a verdade
    era a segunda (`car_faturado` nasceu vazia).

    ⚠️ Lançamento sem competência no texto, ou sem cliente que esta base
    conheça, **não entra na conta** e sai em `nao_amarrados` com o motivo --
    medido em 30/10: 5 lançamentos sem `contatoId` conhecido em 544.
    """
    try:
        linhas = conn.execute(
            """SELECT id, tipo, estado, competencia, cnpj, contato, contato_id,
                      termo_id, termo_numero, valor, descricao, numero_os,
                      venc_ano_mes
                 FROM car_faturado"""
        ).fetchall()
    except Exception:
        # Banco que nasceu antes do bloco F1 (cópia velha restaurada): a
        # ausência da tabela é "não lido", não erro de pré-fatura.
        return {"lido": False, "por_cliente": {}, "nao_amarrados": [],
                "lido_em": None, "totais": {},
                "porque": "a tabela car_faturado ainda não existe neste banco"}

    if not linhas:
        return {"lido": False, "por_cliente": {}, "nao_amarrados": [],
                "lido_em": None, "totais": {},
                "porque": ("o espelho do faturado do Harmonit está vazio: a "
                           "rotina F1 nasce desligada e ainda não passou")}

    lido_em = conn.execute("SELECT MAX(lido_em) FROM car_faturado").fetchone()[0]
    # 🚨 A COBERTURA, QUE A TELA TEM DE DIZER. Medido em 30/10: a competência
    # 2026-09 tem lançamento em SETE meses de vencimento (04 a 10/2026), e uma
    # janela curta fecharia a conta R$ 21 mil abaixo **sem avisar**. Aqui se
    # mostra de quantos meses de vencimento esta competência foi lida e qual o
    # mais antigo que o espelho tem -- quem olha decide se precisa de mais.
    meses_lidos = sorted({r[12] for r in linhas if r[12]})
    por_cliente: dict = {}
    nao = []
    # 🚨 DUAS LISTAS, NÃO UMA, e a diferença me pegou na primeira medição com
    # dado real: eu punha no "não amarrado do mês" **todo** lançamento sem
    # competência, de qualquer mês -- 340 linhas numa pré-fatura de setembro,
    # das quais 333 eram OS, venda e negociação que não pertencem a mês nenhum
    # pelo texto. Lista que mistura "errado neste mês" com "não é de mês" manda
    # o operador caçar problema onde não há.
    sem_comp: dict = {"lancamentos": 0, "por_tipo": {}, "valores": [],
                      "exemplos": []}
    venc_da_competencia: set = set()
    for (lid, tipo, estado, comp, cnpj, contato, contato_id, termo_id,
         termo_numero, valor, descricao, numero_os, venc) in linhas:
        if (comp or "") != competencia:
            if not comp:
                sem_comp["lancamentos"] += 1
                sem_comp["por_tipo"][tipo] = sem_comp["por_tipo"].get(tipo, 0) + 1
                sem_comp["valores"].append(valor)
                if len(sem_comp["exemplos"]) < 10:
                    sem_comp["exemplos"].append(
                        {"lancamento_id": lid, "tipo": tipo, "contato": contato,
                         "valor": valor, "numero_os": numero_os,
                         "descricao": descricao})
            continue
        if venc:
            venc_da_competencia.add(venc)
        if not cnpj:
            nao.append({"lancamento_id": lid, "tipo": tipo, "contato": contato,
                        "contato_id": contato_id, "valor": valor,
                        "descricao": descricao,
                        "motivo": ("o cliente deste lançamento não está em "
                                   "`clientes` (contatoId do Harmonit)")})
            continue
        bloco = por_cliente.setdefault(cnpj, {
            "mensalidade": [], "avulso": [], "recebido": [], "em_aberto": [],
            "lancamentos": 0, "por_termo": {}, "linhas": []})
        destino = "mensalidade" if tipo in cf.RECORRENTES else "avulso"
        bloco[destino].append(valor)
        bloco["recebido" if estado == cf.BAIXADO else "em_aberto"].append(valor)
        bloco["lancamentos"] += 1
        bloco["linhas"].append({
            "lancamento_id": lid, "tipo": tipo, "estado": estado,
            "valor": valor, "termo_id": termo_id, "termo_numero": termo_numero,
            "numero_os": numero_os, "descricao": descricao})
        if termo_id:
            t = bloco["por_termo"].setdefault(
                termo_id, {"mensalidade": [], "avulso": [], "recebido": [],
                           "em_aberto": []})
            t[destino].append(valor)
            t["recebido" if estado == cf.BAIXADO else "em_aberto"].append(valor)
        elif termo_numero:
            nao.append({"lancamento_id": lid, "tipo": tipo, "cnpj": cnpj,
                        "contato": contato, "valor": valor,
                        "termo_numero": termo_numero, "descricao": descricao,
                        "motivo": ("o contrato deste lançamento não existe nesta "
                                   "base para este cliente")})

    def _fechar(bloco: dict) -> dict:
        return {k: somar_textos(bloco[k]) for k in
                ("mensalidade", "avulso", "recebido", "em_aberto")}

    saida = {}
    for cnpj, bloco in por_cliente.items():
        saida[cnpj] = {**_fechar(bloco), "lancamentos": bloco["lancamentos"],
                       "linhas": bloco["linhas"],
                       "por_termo": {tid: _fechar(t)
                                     for tid, t in bloco["por_termo"].items()}}

    todos = [l for b in por_cliente.values() for l in b["linhas"]]
    return {
        "lido": True, "lido_em": lido_em, "por_cliente": saida,
        # Só o que é DESTA competência e não amarrou: sem cliente, ou sem o
        # contrato citado. É lista para agir.
        "nao_amarrados": nao,
        # 🚨 O que o Harmonit cobra FORA de competência: OS, venda, adesão sem
        # período, negociação (parcelamento). Não entra na conta de nenhum mês
        # **e isso é dito** -- é a resposta medida à pergunta dele de 30/10
        # ("e outras cobranças tbm?"), e o terreno da F6.
        "sem_competencia": {
            "lancamentos": sem_comp["lancamentos"],
            "por_tipo": sem_comp["por_tipo"],
            "total": somar_textos(sem_comp["valores"]),
            "exemplos": sem_comp["exemplos"],
            "porque": ("a descrição destes lançamentos não traz período de "
                       "referência (são OS, venda, adesão e parcelamento). Eles "
                       "ficam fora da conta do mês até a parte variável nascer "
                       "(bloco F6, decisão D6)"),
        },
        "cobertura": {
            "meses_de_vencimento_lidos": meses_lidos,
            "mais_antigo_lido": meses_lidos[0] if meses_lidos else None,
            "mais_novo_lido": meses_lidos[-1] if meses_lidos else None,
            "meses_de_vencimento_desta_competencia":
                sorted(venc_da_competencia),
            # ⚠️ O aviso existe porque o caso é REAL, e vale nas DUAS pontas: se
            # a competência aparece no mês mais antigo (ou no mais novo) que o
            # espelho leu, pode haver lançamento dela num mês ainda não lido.
            # 🚨 A ponta nova pegou um número meu: com janela até 2027-01, a
            # competência 2027-01 mostrava 12 lançamentos, e isso parecia carteira
            # caindo -- era o fim da janela. Previsão que não diz onde a janela
            # acaba é previsão que mente.
            "pode_faltar": bool(
                meses_lidos and venc_da_competencia
                and (min(venc_da_competencia) == meses_lidos[0]
                     or max(venc_da_competencia) == meses_lidos[-1])),
            "porque": ("a competência de um lançamento vive na descrição, não no "
                       "vencimento: a de 2026-09 tem lançamento em sete meses de "
                       "vencimento (medido em 30/10). O espelho só sabe dos meses "
                       "que leu."),
        },
        "totais": {
            "clientes": len(saida), "lancamentos": len(todos),
            "mensalidade": somar_textos(
                [l["valor"] for l in todos if l["tipo"] in cf.RECORRENTES]),
            "avulso": somar_textos(
                [l["valor"] for l in todos if l["tipo"] not in cf.RECORRENTES]),
            "recebido": somar_textos(
                [l["valor"] for l in todos if l["estado"] == cf.BAIXADO]),
            "em_aberto": somar_textos(
                [l["valor"] for l in todos if l["estado"] == cf.A_BAIXAR]),
            "nao_amarrados": len(nao),
        },
    }


def eventos_por_termo(conn) -> dict:
    """Os eventos da CAR, por `termo_id`. Uma consulta."""
    por_termo: dict = {}
    for (eid, cnpj, tid, placa, acao, valor, comp, motivo, doc, fonte, por,
         criado, corrige) in conn.execute(
            """SELECT id, cnpj, termo_id, placa_chave, acao, valor_mensal, competencia,
                      motivo, documento, fonte, por, criado_em, corrige_evento_id
                 FROM car_evento ORDER BY id"""):
        por_termo.setdefault(tid, []).append(
            {"id": eid, "cnpj": cnpj, "termo_id": tid, "placa_chave": placa,
             "acao": acao, "valor_mensal": valor, "competencia": comp,
             "motivo": motivo, "documento": doc, "fonte": fonte, "por": por,
             "criado_em": criado, "corrige_evento_id": corrige})
    return por_termo


def montar(conn, competencia: str, cnpj: str | None = None,
           weso: dict | None = None, idade_weso: float | None = None) -> dict:
    """A pré-fatura da competência. Só leitura.

    Devolve `{"competencia", "clientes", "totais", "variavel", "sem_termo",
    "faturado", "weso"}`.

    `weso` é o mapa `{chave da placa: situação na WESO}` do cache diário, e
    `idade_weso` a idade dele em horas. **Injetados**, nunca lidos aqui -- ver o
    aviso no topo. Sem eles, `em_uso_weso` é `None` em toda linha e a resposta
    declara que a régua da WESO não foi consultada nesta passada.
    """
    motor.validar_competencia(competencia)
    inicio = motor.inicio_da_competencia(competencia)
    fim = motor.fim_da_competencia(competencia)

    if cnpj:
        termos_por_cnpj = {cnpj: reg.termos_do_cliente(conn, cnpj)}
    else:
        termos_por_cnpj = reg.termos_de_todos(conn)

    nomes = nomes_dos_clientes(conn)
    itens = itens_com_valor(conn)
    eventos_car = eventos_por_termo(conn)
    faturado = faturado_do_mes(conn, competencia)

    def _em_uso(chave):
        """`True/False/None`. 🚨 `None` NUNCA VIRA `False`: sem o cache da WESO
        a resposta honesta é "não dá para afirmar", e `False` acusaria placa
        instalada de estar fora de serviço."""
        if weso is None:
            return None
        return weso.get(chave) == SITUACAO_EM_USO

    clientes = []
    sem_termo = []          # placa cobrável cuja origem não resolve: tem de APARECER
    t_placas = t_com = t_sem = t_contratos = 0

    for doc, termos in sorted(termos_por_cnpj.items()):
        cobraveis, entrou, saiu = cobraveis_do_mes(termos, inicio, fim)
        if not cobraveis:
            continue

        # Agrupa as placas pelo termo que as sustenta naquele mês.
        por_termo: dict = {}
        for chave, sit in cobraveis.items():
            termo = resolver_termo(termos, sit.get("termo_vigente"))
            if termo is None:
                sem_termo.append({
                    "cnpj": doc, "nome": nomes.get(doc),
                    "placa": sit.get("placa") or chave,
                    "situacao": sit.get("situacao"),
                    "termo_vigente": sit.get("termo_vigente"),
                    "motivo": "a placa aponta um termo que não existe nesta base"})
                continue
            por_termo.setdefault(termo["id"], (termo, []))[1].append((chave, sit))

        contratos = []
        for tid, (termo, placas) in por_termo.items():
            eventos = eventos_car.get(tid, [])
            estado = motor.situacao_do_contrato(
                termo,
                [{"situacao": s.get("situacao")} for _k, s in placas],
                eventos, competencia)

            linhas = []
            for chave, sit in sorted(placas, key=lambda x: x[1].get("placa") or x[0]):
                v = motor.valor_da_placa(eventos, competencia, chave,
                                         valor_do_item=itens.get((doc, chave)))
                linhas.append({
                    "tipo": "mensalidade",          # decisão 6: 1 por placa
                    "placa": sit.get("placa") or chave,
                    "placa_chave": chave,
                    "situacao": sit.get("situacao"),
                    "base": sit.get("base"),
                    "aviso_ate": sit.get("aviso_ate"),
                    # Mês cheio, sem pro rata (decisão 7) — mas a tela DIZ que
                    # a placa não atravessou o mês inteiro, para a substituição
                    # dentro do mês não aparecer só na soma.
                    "entrou_no_mes": chave in entrou,
                    "saiu_no_mes": chave in saiu,
                    "valor": v["valor"],
                    "fonte_do_valor": v["fonte"],
                    "motivo": v["motivo"],
                    # F3: a régua dele. `situacao_weso` carrega o NOME do que a
                    # WESO diz (Estoque, Bancada...), porque "não está em uso"
                    # sem a causa manda o operador abrir a WESO para descobrir.
                    "em_uso_weso": _em_uso(chave),
                    "situacao_weso": None if weso is None else weso.get(chave),
                })
            com = sum(1 for l in linhas if l["valor"])
            em_uso = sum(1 for l in linhas if l["em_uso_weso"])
            contratos.append({
                "termo_id": tid, "numero": termo.get("numero"),
                "empresa": termo.get("empresa"), "assinado": bool(termo.get("assinado")),
                "situacao": estado["situacao"], "motivo": estado["motivo"],
                "divergencia": estado["divergencia"],
                "placas": len(linhas), "com_valor": com,
                "sem_valor": len(linhas) - com,
                # Previsto no contrato × em uso na WESO, lado a lado: é a
                # interseção que ele pediu em 30/10, com as duas visíveis.
                "em_uso": None if weso is None else em_uso,
                "contratadas_sem_uso": None if weso is None else len(linhas) - em_uso,
                "faturado": faturado["por_cliente"].get(doc, {})
                            .get("por_termo", {}).get(tid),
                "linhas": linhas,
            })
            t_contratos += 1
            t_placas += len(linhas)
            t_com += com
            t_sem += len(linhas) - com

        contratos.sort(key=lambda c: (-c["sem_valor"], c["numero"] or ""))
        em_uso_cli = sum(c["em_uso"] or 0 for c in contratos)
        do_cliente = faturado["por_cliente"].get(doc, {})
        clientes.append({
            "cnpj": doc, "nome": nomes.get(doc),
            "placas": sum(c["placas"] for c in contratos),
            "com_valor": sum(c["com_valor"] for c in contratos),
            "sem_valor": sum(c["sem_valor"] for c in contratos),
            "em_uso": None if weso is None else em_uso_cli,
            "contratadas_sem_uso": None if weso is None else
            sum(c["placas"] for c in contratos) - em_uso_cli,
            # 🚨 AS TRÊS COLUNAS, NO CLIENTE: deveria cobrar (as placas e o
            # valor acima) × cobrado × recebido. Vazio = o espelho não leu nada
            # deste cliente neste mês, e a tela diz isso.
            "faturado": {
                "mensalidade": do_cliente.get("mensalidade"),
                "avulso": do_cliente.get("avulso"),
                "recebido": do_cliente.get("recebido"),
                "em_aberto": do_cliente.get("em_aberto"),
                "lancamentos": do_cliente.get("lancamentos", 0),
            },
            # 🚨 A PERGUNTA DA GESTÃO MENSAL, por cliente: tem placa em uso e
            # não há mensalidade cobrada no mês. É o vazamento dos 25 clientes
            # medido em 28/10, e é por isso que a fila passa a ordenar por ele.
            "em_uso_sem_faturar": (None if weso is None else
                                   em_uso_cli > 0 and not do_cliente.get("mensalidade")),
            "contratos": contratos,
        })

    # 🔵 ORDEM NOVA (30/10, decisão dele): primeiro quem tem placa EM USO e não
    # é faturado -- o vazamento. Depois quem tem placa cobrável sem preço.
    # 🚨 A ordem velha (`-sem_valor`) é o achado A1 da auditoria de 28/10: ela
    # punha a Horse em primeiro lugar, com 356 placas cobráveis e **zero** em
    # uso na WESO. Seguir aquela fila lançaria preço em placa fora de serviço.
    clientes.sort(key=lambda c: (not c["em_uso_sem_faturar"], -(c["em_uso"] or 0),
                                 -c["sem_valor"], -c["placas"],
                                 c["nome"] or c["cnpj"]))

    return {
        "competencia": competencia,
        "de": inicio.isoformat(),
        "ate": fim.isoformat(),
        "clientes": clientes,
        "sem_termo": sem_termo,
        "totais": {
            "clientes": len(clientes),
            "contratos": t_contratos,
            "placas": t_placas,
            # Quantas não atravessaram o mês inteiro. Mês cheio para as duas
            # (decisão 7), mas o número tem de ser visível: é ele que explica
            # uma soma que subiu sem contrato novo.
            "entraram_no_mes": sum(
                1 for c in clientes for ct in c["contratos"]
                for l in ct["linhas"] if l["entrou_no_mes"]),
            "sairam_no_mes": sum(
                1 for c in clientes for ct in c["contratos"]
                for l in ct["linhas"] if l["saiu_no_mes"]),
            "com_valor": t_com,
            "sem_valor": t_sem,
            # F3: as duas colunas somadas. `None` quando a WESO não foi
            # consultada -- zero diria "nenhuma placa em uso", que é outra coisa.
            "em_uso": None if weso is None else
            sum(c["em_uso"] or 0 for c in clientes),
            "contratadas_sem_uso": None if weso is None else
            sum(c["contratadas_sem_uso"] or 0 for c in clientes),
            "clientes_em_uso_sem_faturar": None if weso is None else
            sum(1 for c in clientes if c["em_uso_sem_faturar"]),
            # 🚨 `total` é a soma DO QUE TEM VALOR, e `cobertura` diz de quanto
            # da carteira ele fala. Total que soma parte da carteira sem dizer é
            # tela que mente por omissão.
            "total": _somar(clientes),
            "cobertura": (t_com / t_placas) if t_placas else None,
        },
        # F2: o cobrado e o recebido do Harmonit, por cliente, na competência.
        # `lido: false` com o porquê é o que impede a tela de desenhar R$ 0 onde
        # a verdade é "a rotina do espelho ainda não passou".
        "faturado": faturado,
        # F3: de quando é a régua da WESO, e se ela foi consultada.
        "weso": {
            "lido": weso is not None,
            "idade_h": idade_weso,
            "chaves": None if weso is None else len(weso),
            "situacao_em_uso": SITUACAO_EM_USO,
            "porque": None if weso is not None else
            ("o cache da WESO não foi consultado nesta chamada; nenhuma linha "
             "afirma estar ou não em uso"),
        },
        "variavel": {
            "ligada": False,
            # `M12`: a tela declara o que não faz, em vez de somar só a
            # mensalidade e deixar parecer que é o total.
            "porque": ("a parte variável (serviço de OS) espera a lista de itens do "
                       "catálogo do Harmonit que se cobram do cliente — hoje o único "
                       "classificador que existe é o de PAGAR técnico"),
        },
    }


def _somar(clientes) -> str | None:
    """Soma o que tem valor. `None` quando nada tem -- nunca '0,00'.

    ⚠️ `valor_mensal` é TEXT de propósito (o termo escreve "R$ 999,90"), então a
    conversão acontece **aqui, num lugar só**. O que não converte **não é
    silenciado**: entra em `nao_somados`, e a tela mostra.
    """
    centavos, achou = 0, False
    for c in clientes:
        for ct in c["contratos"]:
            for l in ct["linhas"]:
                v = _centavos(l["valor"])
                if v is None:
                    if l["valor"]:
                        l["motivo"] = (l.get("motivo") or "") + \
                            f" | valor não numérico, fora da soma: {l['valor']!r}"
                    continue
                centavos += v
                achou = True
    if not achou:
        return None
    return f"{centavos // 100},{centavos % 100:02d}"


def somar_textos(valores) -> str | None:
    """Soma uma lista de valores em texto. `None` quando nada soma.

    ⚠️ MESMA REGRA DO `_somar`, e de propósito no mesmo arquivo: a conversão de
    dinheiro acontece num lugar só. `None` nunca vira `'0,00'` -- zero afirma
    "não cobra nada", nulo diz "não sabemos", e a diferença é o que a tela
    precisa mostrar.
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


def _centavos(texto):
    """"R$ 1.234,56" -> 123456. `None` quando não dá para converter."""
    if not texto:
        return None
    limpo = "".join(ch for ch in str(texto) if ch.isdigit() or ch in ",.")
    limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return int(round(float(limpo) * 100))
    except (ValueError, TypeError):
        return None


def para_csv(prefatura: dict) -> str:
    """Uma linha por linha de cobrança. Separador `;`, como o resto da casa."""
    saida = ["cnpj;cliente;termo;empresa;situacao_contrato;placa;situacao_placa;"
             "em_uso_weso;situacao_weso;valor;fonte_do_valor;"
             "mensalidade_cobrada_cliente;recebido_cliente;motivo"]
    for c in prefatura["clientes"]:
        fat = c.get("faturado") or {}
        for ct in c["contratos"]:
            for l in ct["linhas"]:
                saida.append(";".join(str(x if x is not None else "") for x in (
                    c["cnpj"], c["nome"], ct["numero"], ct["empresa"], ct["situacao"],
                    l["placa"], l["situacao"], l.get("em_uso_weso"),
                    l.get("situacao_weso"), l["valor"], l["fonte_do_valor"],
                    fat.get("mensalidade"), fat.get("recebido"),
                    (l["motivo"] or "").replace(";", ","))))
    for s in prefatura["sem_termo"]:
        saida.append(";".join(str(x if x is not None else "") for x in (
            s["cnpj"], s["nome"], s["termo_vigente"], "", "SEM TERMO",
            s["placa"], s["situacao"], "", "", "", "", "", "", s["motivo"])))
    return "\n".join(saida)
