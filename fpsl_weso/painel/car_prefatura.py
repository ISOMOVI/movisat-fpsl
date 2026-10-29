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
"""
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


def montar(conn, competencia: str, cnpj: str | None = None) -> dict:
    """A pré-fatura da competência. Só leitura.

    Devolve `{"competencia", "clientes", "totais", "variavel", "sem_termo"}`.
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
                })
            com = sum(1 for l in linhas if l["valor"])
            contratos.append({
                "termo_id": tid, "numero": termo.get("numero"),
                "empresa": termo.get("empresa"), "assinado": bool(termo.get("assinado")),
                "situacao": estado["situacao"], "motivo": estado["motivo"],
                "divergencia": estado["divergencia"],
                "placas": len(linhas), "com_valor": com,
                "sem_valor": len(linhas) - com,
                "linhas": linhas,
            })
            t_contratos += 1
            t_placas += len(linhas)
            t_com += com
            t_sem += len(linhas) - com

        contratos.sort(key=lambda c: (-c["sem_valor"], c["numero"] or ""))
        clientes.append({
            "cnpj": doc, "nome": nomes.get(doc),
            "placas": sum(c["placas"] for c in contratos),
            "com_valor": sum(c["com_valor"] for c in contratos),
            "sem_valor": sum(c["sem_valor"] for c in contratos),
            "contratos": contratos,
        })

    # 🟡 Ordem: quem tem mais placa cobrável SEM valor vem primeiro. Quem senta
    # na tela ataca o que mais pesa, em vez de rolar a lista alfabética.
    clientes.sort(key=lambda c: (-c["sem_valor"], -c["placas"], c["nome"] or c["cnpj"]))

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
            # 🚨 `total` é a soma DO QUE TEM VALOR, e `cobertura` diz de quanto
            # da carteira ele fala. Total que soma parte da carteira sem dizer é
            # tela que mente por omissão.
            "total": _somar(clientes),
            "cobertura": (t_com / t_placas) if t_placas else None,
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
             "valor;fonte_do_valor;motivo"]
    for c in prefatura["clientes"]:
        for ct in c["contratos"]:
            for l in ct["linhas"]:
                saida.append(";".join(str(x if x is not None else "") for x in (
                    c["cnpj"], c["nome"], ct["numero"], ct["empresa"], ct["situacao"],
                    l["placa"], l["situacao"], l["valor"], l["fonte_do_valor"],
                    (l["motivo"] or "").replace(";", ","))))
    for s in prefatura["sem_termo"]:
        saida.append(";".join(str(x if x is not None else "") for x in (
            s["cnpj"], s["nome"], s["termo_vigente"], "", "SEM TERMO",
            s["placa"], s["situacao"], "", "", s["motivo"])))
    return "\n".join(saida)
