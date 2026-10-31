"""Registro das Contas a Receber (`CAR_1.1`) — etapa E6. 2026-10-28.

Spec: `docs/fpsl/32_Contas_a_Receber.md`.

Núcleo **síncrono**, testável em memória, no padrão de `contratos_registro.py`.
Quem commita é o chamador: as rotas abrem a transação, e o teste controla a dele.

🚨 NUNCA `UPDATE` EM `car_evento`. As cinco ações só inserem; corrigir é lançar
`ANULA` apontando o errado, que **continua visível**. É isso que faz "por que
este cliente pagou isto neste mês?" ter o documento e o autor como resposta --
travado por teste, que reprova se um `UPDATE car_evento` aparecer no fonte.

🚨 `por` É OBRIGATÓRIO EM TODAS. Dinheiro sem autor é dinheiro sem responsável.
E `motivo` é obrigatório quando a origem é **gente** (`fonte='operador'`), em
`CANCELA`, em `EXCECAO` e em `ANULA`: meses depois, "o valor mudou" sem motivo
é exatamente a pergunta que esta aba existe para responder.

⚠️ O LANÇAMENTO EM LOTE existe por um número medido em 28/10: das **2.993**
placas cobráveis de outubro, **ZERO** tinha valor. Lançar uma a uma seria
inviável; e a concentração ajuda -- os 20 maiores contratos somam 866 placas
(29%) e os 50 maiores, 1.174 (40%). O lote lança **um `PRECO` por contrato**,
com `placa_chave` nula, que vale para todas as placas dele.

⚠️ `RENOVA` não guarda prazo de fidelidade: `contrato_item.fidelidade_meses` é
da CTR e continua sendo a fonte. Aqui a renovação é o **fato** (com documento e
autor) de que a vigência recomeçou naquela competência.
"""
from datetime import datetime, timezone

from . import car_motor as motor
from . import car_prefatura as pf
from . import contratos_registro as reg


class DadoInvalido(ValueError):
    """Entrada que não se grava, com o motivo na mensagem."""


class TermoNaoExiste(DadoInvalido):
    """O `termo_id` não está em `contrato_termo`, ou não é deste CNPJ."""


class JaAnulado(DadoInvalido):
    """O evento já foi anulado. Anular duas vezes empilharia correção sobre
    correção, e o histórico mostraria a mesma coisa repetida -- o índice único
    parcial do banco também barra, e aqui a mensagem diz qual anulação existe."""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texto(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _exigir_termo(conn, cnpj: str, termo_id: int) -> dict:
    linha = conn.execute(
        "SELECT id, cnpj, numero, empresa, assinado FROM contrato_termo WHERE id = ?",
        (termo_id,)).fetchone()
    if linha is None:
        raise TermoNaoExiste(f"termo {termo_id} não existe nesta base")
    if cnpj and linha[1] != cnpj:
        # 🚨 Não é paranoia: o CNPJ vem da tela e o `termo_id` do clique. Se os
        # dois discordarem, gravar lançaria preço no contrato de OUTRO cliente,
        # e a conferência só pegaria isso meses depois.
        raise TermoNaoExiste(
            f"termo {termo_id} é do CNPJ {linha[1]}, não de {cnpj}")
    return {"id": linha[0], "cnpj": linha[1], "numero": linha[2],
            "empresa": linha[3], "assinado": bool(linha[4])}


def _inserir(conn, *, cnpj, termo_id, acao, competencia, por, valor=None,
             placa_chave=None, motivo=None, documento=None, fonte="operador",
             corrige=None) -> int:
    motor.validar_competencia(competencia)
    if acao not in motor.ACOES:
        raise DadoInvalido(f"ação desconhecida: {acao!r}")
    if not _texto(por):
        raise DadoInvalido("quem lançou não pode ficar vazio")
    cur = conn.execute(
        """INSERT INTO car_evento (cnpj, termo_id, placa_chave, acao, valor_mensal,
                                   competencia, motivo, documento, fonte, por,
                                   criado_em, corrige_evento_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cnpj, termo_id, _texto(placa_chave), acao, _texto(valor), competencia,
         _texto(motivo), _texto(documento), fonte, _texto(por), _agora(), corrige))
    return cur.lastrowid


# ─────────────────────────────────────────────────────────────────────────────
# As cinco ações
# ─────────────────────────────────────────────────────────────────────────────
def lancar_preco(conn, cnpj: str, termo_id: int, valor: str, competencia: str,
                 por: str, motivo=None, documento=None, fonte="operador",
                 placa_chave=None) -> int:
    """A mensalidade passa a ser `valor` a partir de `competencia`.

    🚨 NASCER O VALOR E REAJUSTAR SÃO O MESMO FATO. Não existe "editar preço":
    existe preço novo, com data, autor e documento -- e o anterior continua na
    linha do tempo, que é o histórico de reajuste de graça.
    """
    _exigir_termo(conn, cnpj, termo_id)
    if not _texto(valor):
        raise DadoInvalido("preço sem valor não é preço")
    if fonte == "operador" and not _texto(motivo):
        # Quando vem do termo, o documento é o motivo. Quando vem de gente, o
        # motivo tem de estar escrito.
        raise DadoInvalido("preço lançado à mão exige motivo")
    return _inserir(conn, cnpj=cnpj, termo_id=termo_id, acao=motor.PRECO,
                    competencia=competencia, por=por, valor=valor,
                    placa_chave=placa_chave, motivo=motivo, documento=documento,
                    fonte=fonte)


def cancelar(conn, cnpj: str, termo_id: int, competencia: str, por: str,
             motivo: str) -> int:
    """Interrompe a COBRANÇA a partir da competência.

    🚨 NÃO MEXE EM PLACA. Rescisão de placa é evento da CTR (`RESCINDE`), e sai
    do documento. Cancelar aqui é dizer "pare de faturar"; se as placas seguem
    sustentadas na CTR, a `CAR_1.1` mostra isso como **divergência**, em vez de
    as duas abas discordarem caladas.
    """
    _exigir_termo(conn, cnpj, termo_id)
    if not _texto(motivo):
        raise DadoInvalido("cancelar cobrança exige motivo")
    return _inserir(conn, cnpj=cnpj, termo_id=termo_id, acao=motor.CANCELA,
                    competencia=competencia, por=por, motivo=motivo)


def renovar(conn, cnpj: str, termo_id: int, competencia: str, por: str,
            documento=None, motivo=None) -> int:
    """A vigência recomeça nesta competência."""
    _exigir_termo(conn, cnpj, termo_id)
    return _inserir(conn, cnpj=cnpj, termo_id=termo_id, acao=motor.RENOVA,
                    competencia=competencia, por=por, documento=documento,
                    motivo=motivo)


def excecao(conn, cnpj: str, termo_id: int, competencia: str, por: str,
            motivo: str, valor=None, placa_chave=None) -> int:
    """A negociação do mês: `valor` nesta competência, ou nada a cobrar.

    🚨 VALE SÓ NO MÊS LANÇADO. Desconto permanente é `PRECO` novo. Desconto que
    se renova sozinho é o que ninguém lembra de desligar -- e seis meses depois
    a receita caiu e nenhuma tela sabe dizer por quê.
    """
    _exigir_termo(conn, cnpj, termo_id)
    if not _texto(motivo):
        raise DadoInvalido("exceção exige motivo — é o que a torna auditável")
    return _inserir(conn, cnpj=cnpj, termo_id=termo_id, acao=motor.EXCECAO,
                    competencia=competencia, por=por, valor=valor,
                    placa_chave=placa_chave, motivo=motivo)


def anular(conn, evento_id: int, por: str, motivo: str) -> int:
    """Anula um evento da CAR, sem apagá-lo."""
    linha = conn.execute(
        "SELECT id, cnpj, termo_id, competencia FROM car_evento WHERE id = ?",
        (evento_id,)).fetchone()
    if linha is None:
        raise DadoInvalido(f"evento {evento_id} não existe")
    if not _texto(motivo):
        raise DadoInvalido("anular exige motivo")
    ja = conn.execute(
        "SELECT id FROM car_evento WHERE corrige_evento_id = ?",
        (evento_id,)).fetchone()
    if ja is not None:
        raise JaAnulado(
            f"o evento {evento_id} já foi anulado pelo evento {ja[0]}")
    return _inserir(conn, cnpj=linha[1], termo_id=linha[2], acao=motor.ANULA,
                    competencia=linha[3], por=por, motivo=motivo,
                    corrige=evento_id)


# ─────────────────────────────────────────────────────────────────────────────
# Lançamento em lote — o que tira o `total: None` do chão
# ─────────────────────────────────────────────────────────────────────────────
def lancar_preco_em_lote(conn, termos: list, valor: str, competencia: str,
                         por: str, motivo: str) -> dict:
    """Um `PRECO` por contrato, valendo para todas as placas dele.

    `termos` é uma lista de `(cnpj, termo_id)`. Devolve
    `{"lancados", "repetidos", "recusados", "ids"}`.

    🚨 IDEMPOTENTE POR (termo, competência, valor): clicar duas vezes **não**
    lança duas vezes. Duplicar não mudaria a conta (o último ganha), mas
    encheria o histórico de preço com a mesma linha repetida -- e é esse
    histórico que responde "por que mudou".

    ⚠️ Um contrato recusado **não derruba o lote**: ele volta em `recusados`,
    com o motivo, e os outros entram. Lote que morre no meio deixa metade da
    carteira precificada e ninguém sabe qual metade.
    """
    if not _texto(valor):
        raise DadoInvalido("preço sem valor não é preço")
    if not _texto(motivo):
        raise DadoInvalido("lançamento em lote exige motivo")
    motor.validar_competencia(competencia)

    r = {"lancados": 0, "repetidos": 0, "recusados": [], "ids": []}
    for cnpj, termo_id in termos:
        try:
            _exigir_termo(conn, cnpj, termo_id)
        except DadoInvalido as e:
            r["recusados"].append({"termo_id": termo_id, "cnpj": cnpj,
                                   "motivo": str(e)})
            continue
        igual = conn.execute(
            """SELECT id FROM car_evento
                WHERE termo_id = ? AND acao = ? AND competencia = ?
                  AND placa_chave IS NULL AND valor_mensal = ?""",
            (termo_id, motor.PRECO, competencia, _texto(valor))).fetchone()
        if igual is not None:
            r["repetidos"] += 1
            continue
        r["ids"].append(_inserir(
            conn, cnpj=cnpj, termo_id=termo_id, acao=motor.PRECO,
            competencia=competencia, por=por, valor=valor, motivo=motivo))
        r["lancados"] += 1
    return r


MOTIVO_SEMEADURA = "preço adotado do que o Harmonit já fatura neste contrato"


def semear_em_lote(conn, propostas: list, por: str, motivo=None) -> dict:
    """Um `PRECO` por contrato, **com o valor de cada um** (bloco F4, 30/10).

    🚨 POR QUE NÃO SERVE O `lancar_preco_em_lote`: aquele aplica **um** valor a
    vários termos (é o "todos a R$ 149,90"). A semeadura é o contrário -- cada
    contrato tem o valor que o Harmonit já cobra NELE, e aplicar um valor só
    seria inventar número em cima de dado medido.

    🔵 DECISÃO DELE, 30/10: *"faça o 2 [o lote], mas deixe as regras do 1 tbm,
    para quando alguem alterar os demais"*. Então o lote entra aqui e o "adotar"
    de uma linha continua sendo `lancar_preco` -- a mesma trilha, o mesmo autor.

    Cada proposta é `{cnpj, termo_id, valor, competencia, documento}`. O
    `documento` é o lançamento financeiro de origem (`"mov. financeira 10396439"`),
    e é ele que responde "de onde veio este preço?" meses depois.

    🚨 IDEMPOTENTE POR (termo, competência, valor) e **recusado não derruba o
    lote** -- as mesmas duas invariantes do outro lote, e pelo mesmo motivo:
    clicar duas vezes não pode encher o histórico de preço com a mesma linha, e
    lote que morre no meio deixa metade da carteira precificada sem ninguém
    saber qual metade.
    """
    if not propostas:
        raise DadoInvalido("semeadura sem proposta nenhuma")
    texto_motivo = _texto(motivo) or MOTIVO_SEMEADURA

    r = {"lancados": 0, "repetidos": 0, "recusados": [], "ids": []}
    for p in propostas:
        termo_id = p.get("termo_id")
        cnpj = p.get("cnpj")
        valor = _texto(p.get("valor"))
        comp = p.get("competencia")
        try:
            motor.validar_competencia(comp)
            if not valor:
                raise DadoInvalido("proposta sem valor não é preço")
            _exigir_termo(conn, cnpj, termo_id)
        except (DadoInvalido, motor.CompetenciaInvalida) as e:
            r["recusados"].append({"termo_id": termo_id, "cnpj": cnpj,
                                   "motivo": str(e)})
            continue
        igual = conn.execute(
            """SELECT id FROM car_evento
                WHERE termo_id = ? AND acao = ? AND competencia = ?
                  AND placa_chave IS NULL AND valor_mensal = ?""",
            (termo_id, motor.PRECO, comp, valor)).fetchone()
        if igual is not None:
            r["repetidos"] += 1
            continue
        r["ids"].append(_inserir(
            conn, cnpj=cnpj, termo_id=termo_id, acao=motor.PRECO,
            competencia=comp, por=por, valor=valor, motivo=texto_motivo,
            documento=_texto(p.get("documento"))))
        r["lancados"] += 1
    return r


def contratos_sem_valor(conn, competencia: str, limite: int = 200,
                        weso: dict | None = None,
                        idade_weso: float | None = None) -> list:
    """Os contratos com placa cobrável e SEM valor. É a fila de trabalho do lote,
    e sai da própria pré-fatura -- a régua de "cobrável" não se reescreve aqui.

    🔵 ORDEM NOVA (30/10): **placa EM USO na WESO primeiro**, depois o volume.
    🚨 A ordem velha era só `-sem_valor`, e é o achado A1 da auditoria de 28/10:
    ela punha a Horse na frente -- 356 placas cobráveis, **zero** em uso. Seguir
    aquela fila lançaria preço em placa fora de serviço, que foi exatamente o
    que ele barrou ao dizer *"as placas ativas são somente as que estão na Weso
    ativa"*.

    Sem o mapa da WESO a ordem cai na antiga, e a linha carrega `em_uso: None`
    para a tela não afirmar o que não foi consultado.
    """
    pre = pf.montar(conn, competencia, weso=weso, idade_weso=idade_weso)
    fila = [
        {"cnpj": c["cnpj"], "nome": c["nome"], "termo_id": ct["termo_id"],
         "numero": ct["numero"], "empresa": ct["empresa"],
         "assinado": ct["assinado"], "situacao": ct["situacao"],
         "placas": ct["placas"], "sem_valor": ct["sem_valor"],
         "em_uso": ct.get("em_uso"),
         "faturado": ct.get("faturado")}
        for c in pre["clientes"] for ct in c["contratos"] if ct["sem_valor"]
    ]
    fila.sort(key=lambda x: (-(x["em_uso"] or 0), -x["sem_valor"],
                             x["nome"] or x["cnpj"]))
    return fila[:limite]


def historico_de_preco(conn, termo_id: int) -> list:
    """A linha do tempo do preço deste contrato, anulados inclusive.

    ⚠️ O anulado **aparece**, marcado. Esconder a correção transformaria o
    histórico em versão final, e versão final não responde "por que mudou".
    """
    eventos = pf.eventos_por_termo(conn).get(termo_id, [])
    mortos = motor.anulados(eventos)
    saida = []
    for e in eventos:
        if e["acao"] not in (motor.PRECO, motor.EXCECAO):
            continue
        saida.append({**e, "anulado": e["id"] in mortos})
    return saida


# ─────────────────────────────────────────────────────────────────────────────
# car_contrato — a derivada
# ─────────────────────────────────────────────────────────────────────────────
def recalcular_todos(conn, competencia: str) -> dict:
    """Refaz `car_contrato` para TODOS os termos, na competência dada.

    🚨 APAGA E INSERE, nunca atualiza -- igual ao `_gravar_situacoes` da CTR. E
    a régua do status **não é reescrita aqui**: vem de
    `car_motor.situacao_do_contrato`, a mesma que a pré-fatura usa. Duas cópias
    da régua seriam duas verdades, e a tela mostraria a que estivesse em cache.

    ⚠️ Entram **todos** os termos, não só os que têm placa cobrável: ele pediu
    status "pelo contrato em si", e contrato sem placa ativa também tem status
    (e motivo). São 4.599 termos em 28/10.
    """
    motor.validar_competencia(competencia)
    inicio = motor.inicio_da_competencia(competencia)
    fim = motor.fim_da_competencia(competencia)

    termos_por_cnpj = reg.termos_de_todos(conn)
    eventos = pf.eventos_por_termo(conn)
    itens = pf.itens_com_valor(conn)
    agora = _agora()

    conn.execute("DELETE FROM car_contrato")
    r = {"termos": 0, "ativos": 0, "inativos": 0, "divergencias": 0}

    for cnpj, termos in termos_por_cnpj.items():
        cobraveis, _entrou, _saiu = pf.cobraveis_do_mes(termos, inicio, fim)
        por_termo: dict = {}
        for chave, sit in cobraveis.items():
            t = pf.resolver_termo(termos, sit.get("termo_vigente"))
            if t is not None:
                por_termo.setdefault(t["id"], []).append((chave, sit))

        for t in termos:
            placas = por_termo.get(t["id"], [])
            ev = eventos.get(t["id"], [])
            estado = motor.situacao_do_contrato(
                t, [{"situacao": s.get("situacao")} for _k, s in placas],
                ev, competencia)
            com = sem = 0
            centavos, achou = 0, False
            for chave, _s in placas:
                v = motor.valor_da_placa(ev, competencia, chave,
                                         valor_do_item=itens.get((cnpj, chave)))
                if v["valor"]:
                    com += 1
                    c = pf._centavos(v["valor"])
                    if c is not None:
                        centavos += c
                        achou = True
                else:
                    sem += 1
            total = f"{centavos // 100},{centavos % 100:02d}" if achou else None
            conn.execute(
                """INSERT INTO car_contrato
                   (termo_id, cnpj, numero, empresa, situacao, motivo,
                    placas_ativas, placas_com_valor, placas_sem_valor,
                    valor_mensal_total, divergencia, competencia, calculado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (t["id"], cnpj, t.get("numero"), t.get("empresa"),
                 estado["situacao"], estado["motivo"], len(placas), com, sem,
                 total, estado["divergencia"], competencia, agora))
            r["termos"] += 1
            r["ativos"] += 1 if estado["situacao"] == motor.ATIVO else 0
            r["inativos"] += 1 if estado["situacao"] == motor.INATIVO else 0
            r["divergencias"] += 1 if estado["divergencia"] else 0
    return r
