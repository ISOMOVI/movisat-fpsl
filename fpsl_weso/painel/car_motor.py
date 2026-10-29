"""Motor das Contas a Receber (`CAR_1.1`) — etapa E3. 2026-10-28.

Spec: `docs/fpsl/32_Contas_a_Receber.md`.

🚨 LÓGICA PURA, SEM I/O. Nada de banco, nada de rede, nada de arquivo. Entram
listas de dicionários, sai o veredito. É o mesmo desenho de
`contratos_eventos.py`, e por isso o teste consegue provar as regras com
fixtures à mão, sem o `fpsl.db` -- e uma suíte travada no fonte garante que o
`import sqlite3` não entre aqui por descuido amanhã.

🚨 O CONJUNTO DE AÇÕES VIVE AQUI, NÃO NO BANCO. Sem `CHECK` na tabela: quando a
CTR precisou da ação `ANULA`, em 14/10, bastou mudar o motor -- com `CHECK` no
SQLite teria sido reconstruir uma tabela de 12 mil linhas.

As duas perguntas que este módulo responde:
  1. quanto vale a mensalidade desta placa NESTE mês?
  2. este contrato está ativo ou inativo NESTE mês, e por quê?

Ambas são perguntas sobre **um mês**, nunca sobre "agora": é o que faz a
cobrança de outubro ser uma RELEITURA de outubro, e não uma cópia guardada
(doc 33 §11).
"""
import calendar
import re
from datetime import date

# ── As ações, e o que cada uma faz ───────────────────────────────────────────
PRECO = "PRECO"        # a mensalidade passa a ser X a partir desta competência
CANCELA = "CANCELA"    # a COBRANÇA para a partir desta competência
RENOVA = "RENOVA"      # nova vigência/fidelidade a partir desta competência
EXCECAO = "EXCECAO"    # a negociação: vale NA competência lançada, só nela
ANULA = "ANULA"        # corrige um evento desta tabela, sem apagá-lo

ACOES = frozenset({PRECO, CANCELA, RENOVA, EXCECAO, ANULA})

# ── Situação do contrato (o nível de CIMA da decisão dele de 28/10) ──────────
ATIVO = "ATIVO"
INATIVO = "INATIVO"

# As situações de placa da CTR que sustentam cobrança. 🚨 `EM_AVISO_PREVIO`
# ENTRA: decisão dele de 28/10 -- "é o 1", mês cheio durante os 90 dias, porque
# o serviço está rodando. Negociação é `EXCECAO`, com autor e motivo.
SITUACOES_COBRAVEIS = frozenset({"ATIVA", "EM_AVISO_PREVIO"})

_COMPETENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class CompetenciaInvalida(ValueError):
    """'AAAA-MM', e nada além disso.

    Existe como exceção própria porque competência errada não é erro de
    digitação qualquer: ela decide QUAL mês se cobra. Deixar passar
    `"2026-13"` ou `"out/2026"` daria pré-fatura vazia e silenciosa, que é
    pior que erro.
    """


class AcaoInvalida(ValueError):
    """Ação fora de `ACOES`."""


# ─────────────────────────────────────────────────────────────────────────────
# Competência
# ─────────────────────────────────────────────────────────────────────────────
def competencia_de(d: date) -> str:
    """A competência de uma data. `date(2026,10,28)` -> `'2026-10'`."""
    return f"{d.year:04d}-{d.month:02d}"


def validar_competencia(c: str) -> str:
    if not isinstance(c, str) or not _COMPETENCIA.match(c):
        raise CompetenciaInvalida(f"competência inválida: {c!r} (esperado 'AAAA-MM')")
    return c


def fim_da_competencia(c: str) -> date:
    """O ÚLTIMO dia do mês.

    🚨 UMA DAS DUAS PONTAS, não a resposta sozinha. A pré-fatura mede a
    competência no primeiro **e** no último dia e cobra quem esteve no contrato
    em **qualquer** dia dela -- ver `car_prefatura._cobraveis_do_mes`.

    ⚠️ A primeira versão disto afirmava que o último dia era a régua, com o
    argumento de que o dia 1º deixaria de fora quem ficou ativo 30 dias. O
    argumento valia para o outro lado também, e a medição decidiu: em outubro
    de 2026, 1º tinha 2.993 placas cobráveis e dia 31 tinha 2.946 -- **47
    saíram no meio do mês**. Com "mês cheio, sem pro rata" (decisão dele,
    28/10), elas se cobram.
    """
    validar_competencia(c)
    ano, mes = int(c[:4]), int(c[5:7])
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def inicio_da_competencia(c: str) -> date:
    validar_competencia(c)
    return date(int(c[:4]), int(c[5:7]), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Anulação
# ─────────────────────────────────────────────────────────────────────────────
def anulados(eventos) -> set:
    """Os `id` de evento que foram anulados e seguem anulados.

    Uma `ANULA` pode ela mesma ser anulada -- alguém corrigiu e depois se
    arrependeu -- e nesse caso o evento original **volta a valer**.

    🚨 UMA PASSADA, EM ORDEM DECRESCENTE DE `id`, e a ordem é a regra: a
    correção de uma correção é sempre lançada DEPOIS dela, logo tem `id`
    maior. Olhando do mais novo para o mais velho, quando chegamos numa
    `ANULA` já sabemos se ela própria foi anulada.

    ⚠️ A primeira versão disto era um laço "até estabilizar", e eu o troquei
    antes de existir: com duas anulações MÚTUAS (A1 anula A2 e A2 anula A1) o
    conjunto oscilava entre `{A1,A2}` e `∅` e o laço **nunca terminava**. O
    índice único parcial do banco impede duas `ANULA` no mesmo alvo, mas não
    impede esse par. Uma passada decrescente termina sempre, e no par mútuo dá
    um resultado determinístico: ganha a de `id` maior, que é a mais recente.
    """
    mortos: set = set()
    for e in sorted(eventos, key=lambda x: x.get("id") or 0, reverse=True):
        if e.get("acao") != ANULA or e.get("id") in mortos:
            continue
        alvo = e.get("corrige_evento_id")
        if alvo is not None:
            mortos.add(alvo)
    return mortos


def vivos(eventos) -> list:
    """Os eventos que valem: os não anulados, e sem as próprias `ANULA`."""
    mortos = anulados(eventos)
    return [e for e in eventos
            if e.get("acao") != ANULA and e.get("id") not in mortos]


# ─────────────────────────────────────────────────────────────────────────────
# Preço
# ─────────────────────────────────────────────────────────────────────────────
def _ordem(e) -> tuple:
    """Competência primeiro, `id` como desempate.

    O `id` desempata dois fatos do MESMO mês: o último lançado ganha. É a mesma
    escolha da CTR de ordenar por número de termo, e pelo mesmo motivo -- a
    data não serve de ordem quando duas coisas cabem no mesmo mês.
    """
    return (e.get("competencia") or "", e.get("id") or 0)


def preco_vigente(eventos, competencia: str, placa_chave=None):
    """O `PRECO` que vale para esta placa nesta competência, ou `None`.

    Regra: entre os `PRECO` vivos com `competencia <= a pedida`, vence o **mais
    recente**; no empate de mês, vence o **da placa** sobre o do contrato.

    🚨 O FATO MAIS RECENTE MANDA, inclusive quando é do contrato inteiro. Então
    um reajuste geral **substitui** o preço individual de uma placa, e isso é
    desenho: reajuste que não alcança todo mundo é reajuste que vaza. Quem
    precisa preservar um acordo de uma placa lança o `PRECO` dela **depois** do
    geral, ou usa `EXCECAO` no mês. 🟡 Escolha minha, trocável -- está na lista
    de decisões abertas do documento de controle.
    """
    validar_competencia(competencia)
    candidatos = [
        e for e in vivos(eventos)
        if e.get("acao") == PRECO
        and (e.get("competencia") or "") <= competencia
        and (e.get("placa_chave") is None or e.get("placa_chave") == placa_chave)
    ]
    if not candidatos:
        return None
    # `placa_chave is not None` entra na chave de ordenação só como desempate
    # de mês igual: 0 para o do contrato, 1 para o da placa.
    return max(candidatos,
               key=lambda e: (e.get("competencia") or "",
                              1 if e.get("placa_chave") is not None else 0,
                              e.get("id") or 0))


def excecao_da_competencia(eventos, competencia: str, placa_chave=None):
    """A `EXCECAO` lançada NESTA competência, ou `None`.

    🚨 A EXCEÇÃO VALE SÓ NO MÊS EM QUE FOI LANÇADA. Desconto permanente é
    `PRECO` novo, com motivo. A razão é financeira, não estética: desconto que
    se renova sozinho é o tipo de coisa que ninguém lembra de desligar, e seis
    meses depois a receita caiu e nenhuma tela sabe dizer por quê. Negociação
    de mês se reafirma a cada mês, e isso é o mecanismo, não o incômodo.
    🟡 Escolha minha, trocável -- decisão em aberto no documento de controle.
    """
    validar_competencia(competencia)
    candidatos = [
        e for e in vivos(eventos)
        if e.get("acao") == EXCECAO
        and e.get("competencia") == competencia
        and (e.get("placa_chave") is None or e.get("placa_chave") == placa_chave)
    ]
    if not candidatos:
        return None
    return max(candidatos,
               key=lambda e: (1 if e.get("placa_chave") is not None else 0,
                              e.get("id") or 0))


def valor_da_placa(eventos, competencia: str, placa_chave=None,
                   valor_do_item=None) -> dict:
    """Quanto esta placa cobra nesta competência, e DE ONDE veio o valor.

    Devolve sempre `{"valor", "fonte", "evento_id", "motivo"}`.
    `valor=None` **nunca** significa zero: significa *não sabemos*, e o
    `motivo` diz por quê. Em 28/10 isto vale para quase toda a base -- 1 item
    com valor, de 6.463 -- e a tela tem de mostrar isso, não um `R$ 0,00` que
    afirmaria que a placa não cobra nada.

    `valor_do_item` é o `contrato_item.valor_mensal` lido do termo pela CTR: a
    fonte primeira, pela decisão dele de 13/10 ("o valor vem do termo").
    """
    exc = excecao_da_competencia(eventos, competencia, placa_chave)
    if exc is not None:
        return {"valor": exc.get("valor_mensal"), "fonte": "excecao",
                "evento_id": exc.get("id"),
                "motivo": exc.get("motivo") or "negociação do mês, sem motivo escrito"}

    pre = preco_vigente(eventos, competencia, placa_chave)
    if pre is not None:
        return {"valor": pre.get("valor_mensal"),
                "fonte": "preco_" + (pre.get("fonte") or "?"),
                "evento_id": pre.get("id"), "motivo": pre.get("motivo")}

    if valor_do_item:
        return {"valor": valor_do_item, "fonte": "contrato_item",
                "evento_id": None, "motivo": None}

    return {"valor": None, "fonte": None, "evento_id": None,
            "motivo": "o termo não trouxe valor por veículo e nenhum preço foi lançado"}


# ─────────────────────────────────────────────────────────────────────────────
# Situação do contrato
# ─────────────────────────────────────────────────────────────────────────────
def cancelamento_vigente(eventos, competencia: str):
    """O `CANCELA` que já vale nesta competência, ou `None`."""
    validar_competencia(competencia)
    candidatos = [e for e in vivos(eventos)
                  if e.get("acao") == CANCELA
                  and (e.get("competencia") or "") <= competencia]
    return max(candidatos, key=_ordem) if candidatos else None


def renovacao_vigente(eventos, competencia: str):
    """O último `RENOVA` que já vale nesta competência, ou `None`."""
    validar_competencia(competencia)
    candidatos = [e for e in vivos(eventos)
                  if e.get("acao") == RENOVA
                  and (e.get("competencia") or "") <= competencia]
    return max(candidatos, key=_ordem) if candidatos else None


def situacao_do_contrato(termo, placas, eventos, competencia: str) -> dict:
    """ATIVO ou INATIVO nesta competência, **com o motivo**, e a divergência.

    `termo`   dict de `contrato_termo` (usa `assinado`)
    `placas`  as linhas de `contrato_placa` deste termo (usa `situacao`)

    A régua, nesta ordem (a ordem é a regra):
      1. termo não assinado  -> INATIVO. "vale o assinado" é regra dele de
         13/10, e são 1.543 termos assim em 28/10. Dizer ATIVO aqui seria
         prometer cobrança sem documento.
      2. cancelamento vigente -> INATIVO, com o mês escrito.
      3. tem placa cobrável   -> ATIVO.
      4. senão                -> INATIVO, "sem placa ativa".

    🚨 `divergencia` existe para a CAR e a CTR não mentirem uma para a outra:
    contrato cancelado aqui com placa ATIVA lá é serviço rodando sem cobrança,
    e é exatamente o vazamento que esta aba existe para achar.
    """
    validar_competencia(competencia)
    cobraveis = [p for p in placas
                 if (p.get("situacao") or "") in SITUACOES_COBRAVEIS]

    cancel = cancelamento_vigente(eventos, competencia)
    divergencia = None
    if cancel is not None and cobraveis:
        divergencia = (f"cancelado na CAR em {cancel.get('competencia')} e "
                       f"{len(cobraveis)} placa(s) seguem sustentadas na CTR")

    if not termo.get("assinado"):
        # ⚠️ Sem assinatura o contrato é inativo PARA COBRANÇA, e isso não
        # tira a placa de lugar nenhum: na CTR ela segue sustentada, porque
        # "placa na WESO vence, mesmo sem assinatura" (regra dele, 14/10). As
        # duas coisas são verdadeiras ao mesmo tempo, e é por isso que a falta
        # de assinatura é ACHADO, não remoção.
        if cobraveis and divergencia is None:
            divergencia = (f"{len(cobraveis)} placa(s) sustentadas na CTR com "
                           f"termo sem assinatura")
        return {"situacao": INATIVO, "motivo": "termo não assinado",
                "divergencia": divergencia, "placas_cobraveis": len(cobraveis)}

    if cancel is not None:
        return {"situacao": INATIVO,
                "motivo": f"cobrança cancelada em {cancel.get('competencia')}"
                          + (f" — {cancel['motivo']}" if cancel.get("motivo") else ""),
                "divergencia": divergencia, "placas_cobraveis": len(cobraveis)}

    if cobraveis:
        return {"situacao": ATIVO,
                "motivo": f"{len(cobraveis)} placa(s) sustentadas pelo contrato",
                "divergencia": None, "placas_cobraveis": len(cobraveis)}

    return {"situacao": INATIVO, "motivo": "sem placa ativa",
            "divergencia": None, "placas_cobraveis": 0}
