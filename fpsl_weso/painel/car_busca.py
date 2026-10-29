"""Busca das Contas a Receber (`CAR_1.1`) — etapa E5. 2026-10-28.

Spec: `docs/fpsl/32_Contas_a_Receber.md` §5. Pedido dele, textual: *"podendo
consultar os dados do contrato através da placa, do ID em uso, do contrato, do
cliente, etc."*

🚨 UMA CAIXA, SEIS DEGRAUS, EM ORDEM FIXA. Cada degrau só roda se o anterior não
achou, e **a resposta sempre diz por qual degrau achou** (`achou_por` e `como`).
Sem isso o operador não distingue "não existe" de "procurei no campo errado" --
e é essa dúvida que faz ele concluir que o filtro não funciona.

🚨 A ARMADILHA DO `"2hm"`, que é real e já aconteceu na CTR: extrair dígito de
qualquer texto parecia inofensivo e não era. `"2hm"` virava o dígito `"2"`, que
casa com quase todo CNPJ, e a busca **devolvia a base inteira**. Daí a regra:
**letra procura nome; texto sem letra procura CNPJ.**

🚨 E A EXCEÇÃO QUE A AUDITORIA DE CNPJ ALFANUMÉRICO OBRIGOU A CRIAR: um
documento novo (`WQ0P6GLD000108`) **tem letra**, e pela regra acima cairia na
busca por nome e nunca seria achado. Por isso o degrau 0 vem ANTES de tudo e
reconhece documento pela **forma** -- sem pontuação, todo alfanumérico, **11 ou
14 posições, as 2 últimas numéricas**. `"2hm"` tem 3 posições e nunca satisfaz
isso, então a armadilha não volta. Medido em 28/10: a Gestão de Contratos
(`contratos_grid._passa`) **não tem esse degrau** e por isso não acha cliente
nenhum pelo CNPJ alfanumérico -- conserto X1, fora desta etapa.

⚠️ O degrau do **ID em uso** é o único que sai deste banco: o vínculo
rastreador → veículo → placa só existe no cache da WESO. Ele **carimba a idade
do cache** e a resposta carrega isso. A regra das 48 h da casa proíbe o cache
**decidir** (fechar placa, apontar divergência); **procurar** com cache velho é
legítimo, desde que a tela diga a idade -- e por isso aqui não há recusa, há
aviso.
"""
import re
import sqlite3
from datetime import datetime, timezone

from . import contratos_grid as grid

CACHE_WESO = "/home/claude/weso_cache/weso.db"

# 14 posições: as 12 primeiras alfanuméricas, as 2 últimas obrigatoriamente
# numéricas. É a forma do CNPJ novo, e a mesma que `movizap/bitrix_arquivo.py`
# usa para validar -- o validador de DV da casa, escrito para o formato novo.
_DOCUMENTO = re.compile(r"^[0-9A-Z]{12}\d{2}$")


def _limpo(q: str) -> str:
    """Tira pontuação e normaliza a caixa. Preserva LETRA, de propósito: é o que
    faz o CNPJ alfanumérico sobreviver até a comparação."""
    return "".join(ch for ch in (q or "") if ch.isalnum()).upper()


def parece_documento(q: str) -> bool:
    """CPF (11 dígitos) ou CNPJ (14 posições, as 12 primeiras alfanuméricas).

    🚨 A FORMA É A REGRA, não o conteúdo: 14 posições alfanuméricas terminando
    em 2 dígitos é CNPJ, com letra ou sem. O dígito verificador não se confere
    aqui -- buscar documento digitado errado tem de devolver "não achei", não
    "inválido"; quem valida DV é quem **grava**.
    """
    limpo = _limpo(q)
    if len(limpo) == 11:
        return limpo.isdigit()
    if len(limpo) == 14:
        return bool(_DOCUMENTO.match(limpo))
    return False


def _vazio(q, como):
    return {"achou_por": None, "como": como, "q": q, "cnpjs": [], "termos": [],
            "placas": [], "cache": None}


def _clientes(conn) -> list:
    return [{"cnpj": c, "nome": n} for c, n in conn.execute(
        "SELECT cnpj, nome FROM contrato_cliente")]


def _idade_do_cache(caminho: str):
    """`(atualizado_em, horas)` do cache da WESO, ou `(None, None)`."""
    try:
        with sqlite3.connect(f"file:{caminho}?mode=ro", uri=True) as c:
            linha = c.execute(
                "SELECT valor FROM meta WHERE chave = 'atualizado_em'").fetchone()
    except sqlite3.Error:
        return None, None
    if not linha or not linha[0]:
        return None, None
    try:
        quando = datetime.fromisoformat(linha[0])
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
    except ValueError:
        return linha[0], None
    horas = (datetime.now(timezone.utc) - quando).total_seconds() / 3600
    return linha[0], round(horas, 1)


def por_id_em_uso(conn, q: str, cache_weso: str = CACHE_WESO) -> dict:
    """O "ID em uso": número de série do rastreador -> veículo -> placa -> CNPJ.

    ⚠️ Cruza DOIS bancos, e é o degrau mais caro -- por isso é o último. Os três
    índices que ele usa já existem no cache (`idx_rastr_serie`, `idx_veic_rastr`,
    `idx_veic_chave`).

    ⚠️ Cache ausente ou ilegível **não levanta**: devolve vazio com o motivo em
    `cache.erro`. Busca que estoura por causa de um arquivo de apoio tiraria a
    tela do ar inteira.
    """
    alvo = _limpo(q)
    atualizado, horas = _idade_do_cache(cache_weso)
    cache = {"atualizado_em": atualizado, "horas": horas, "erro": None}
    if not alvo:
        return {**_vazio(q, "ID em uso: nada a procurar"), "cache": cache}
    try:
        with sqlite3.connect(f"file:{cache_weso}?mode=ro", uri=True) as c:
            achados = c.execute(
                """SELECT r.numero_serie, v.chave_placa, v.placa
                     FROM rastreadores r JOIN veiculos v ON v.rastreador_id = r.id
                    WHERE upper(replace(r.numero_serie,' ','')) LIKE ?""",
                (f"%{alvo}%",)).fetchall()
    except sqlite3.Error as e:
        cache["erro"] = f"o cache da WESO não pôde ser lido: {e}"
        return {**_vazio(q, "ID em uso: cache indisponível"), "cache": cache}

    if not achados:
        return {**_vazio(q, "ID em uso: nenhum rastreador com esta série"),
                "cache": cache, "serie_encontrada": False}

    # 🚨 `serie_encontrada` existe para o `resolver` NÃO jogar fora a
    # explicação. Sem ela, o rastreador que existe na WESO mas cuja placa não
    # está em contrato caía na mensagem genérica "não achei em lugar nenhum" --
    # e essa é a resposta MAIS útil da busca inteira: ela diz que o equipamento
    # está instalado e não há contrato por trás. Era um defeito meu, pego pela
    # própria suíte.
    chaves = [k for _s, k, _p in achados if k]
    if not chaves:
        return {**_vazio(q, "ID em uso: o rastreador existe na WESO, mas não "
                            "está em veículo com placa"),
                "cache": cache, "serie_encontrada": True}
    marcas = ",".join("?" * len(chaves))
    placas = [{"cnpj": c, "placa": p, "situacao": s, "termo_vigente": t}
              for c, p, s, t in conn.execute(
                  f"""SELECT cnpj, placa_texto, situacao, termo_vigente
                        FROM contrato_placa WHERE placa_chave IN ({marcas})""",
                  tuple(chaves))]
    series = sorted({s for s, _k, _p in achados})
    if not placas:
        return {**_vazio(q, f"ID em uso: série {', '.join(series)} está na WESO, "
                            f"mas a placa não está em contrato nenhum"),
                "cache": cache, "placas": [], "serie_encontrada": True}
    return {"achou_por": "id_em_uso",
            "como": f"série {', '.join(series)} do rastreador na WESO",
            "q": q, "cnpjs": sorted({p["cnpj"] for p in placas}),
            "termos": [], "placas": placas, "cache": cache,
            "serie_encontrada": True}


def _por_contrato(conn, bruto: str) -> dict:
    """Termos com este número, ou vazio.

    🚨 DEVOLVE TODOS OS HOMÔNIMOS. Medido em 28/10: 4.599 termos para 4.041
    números, e **555 pares (cnpj, número) repetidos** -- todos MOVISAT ×
    INSTITUTO. Devolver "o" termo escolheria um documento calado; devolver os
    dois deixa a escolha com quem sabe qual é.
    """
    termos = [{"termo_id": i, "cnpj": c, "numero": n, "empresa": e,
               "assinado": bool(a)}
              for i, c, n, e, a in conn.execute(
                  "SELECT id, cnpj, numero, empresa, assinado FROM contrato_termo "
                  "WHERE numero = ? ORDER BY empresa, id", (bruto,))]
    if not termos:
        return _vazio(bruto, "nenhum termo com este número")
    como = f"número de termo {bruto}"
    if len(termos) > 1:
        como += (f" — {len(termos)} termos com este número, em "
                 + " e ".join(sorted({t["empresa"] or "?" for t in termos})))
    return {"achou_por": "contrato", "como": como, "q": bruto,
            "cnpjs": sorted({t["cnpj"] for t in termos}),
            "termos": termos, "placas": [], "cache": None}


def resolver(conn, q: str, cache_weso: str = CACHE_WESO) -> dict:
    """A caixa única. Devolve sempre o mesmo formato, com `achou_por` e `como`."""
    bruto = (q or "").strip()
    if len(bruto) < 2:
        return _vazio(q, "escreva ao menos 2 caracteres")

    # ── 0. documento pela FORMA (é o que faz o CNPJ alfanumérico funcionar) ──
    if parece_documento(bruto):
        limpo = _limpo(bruto)
        achados = [c for c in _clientes(conn) if _limpo(c["cnpj"]) == limpo]
        if achados:
            return {"achou_por": "documento",
                    "como": f"CNPJ/CPF {limpo} (14 ou 11 posições, forma de documento)",
                    "q": q, "cnpjs": [c["cnpj"] for c in achados],
                    "termos": [], "placas": [], "cache": None}
        # Não achou: NÃO cai para nome. Documento é documento, e "não existe
        # nesta base" é uma resposta útil -- procurar o CNPJ como nome devolveria
        # vazio com a explicação errada.
        return _vazio(q, f"CNPJ/CPF {limpo} não está nesta base")

    alvo = bruto.lower()

    # ── 1. tem letra -> nome ────────────────────────────────────────────────
    if any(ch.isalpha() for ch in alvo):
        achados = [c for c in _clientes(conn)
                   if alvo in (c["nome"] or "").lower()]
        if achados:
            return {"achou_por": "nome", "como": f"nome contendo {bruto!r}",
                    "q": q, "cnpjs": [c["cnpj"] for c in achados],
                    "termos": [], "placas": [], "cache": None}
    else:
        # ── 2. sem letra: o EXATO vence o PARCIAL ───────────────────────────
        # 🚨 ORDEM CORRIGIDA EM 28/10, por medição no dado real: buscar o termo
        # `1000` devolvia *"CNPJ contendo 1000"* com **67 clientes**, porque o
        # degrau do CNPJ parcial rodava antes e engolia o do número de contrato.
        # Número de termo é **igualdade**; pedaço de CNPJ é **substring** -- e
        # igualdade ganha. Com 4.041 números distintos, quase todos de 1 a 4
        # dígitos, procurar contrato era o caso comum e era o que nunca
        # funcionava.
        achados = _por_contrato(conn, bruto)
        if achados["achou_por"]:
            return achados
        digitos = "".join(ch for ch in alvo if ch.isdigit())
        # ⚠️ E o piso subiu de 3 para 6 dígitos: 3 dígitos casam com dezenas de
        # CNPJ e não respondem nada. Quem quer o cliente digita o nome ou o
        # documento inteiro.
        if len(digitos) >= 6:
            achados = [c for c in _clientes(conn) if digitos in (c["cnpj"] or "")]
            if achados:
                return {"achou_por": "cnpj",
                        "como": f"CNPJ contendo {digitos}", "q": q,
                        "cnpjs": [c["cnpj"] for c in achados],
                        "termos": [], "placas": [], "cache": None}

    # ── 3. placa ────────────────────────────────────────────────────────────
    placas = grid.clientes_por_placa(conn, bruto)
    if placas:
        return {"achou_por": "placa", "como": f"placa ou chassi {bruto!r}",
                "q": q, "cnpjs": sorted({p["cnpj"] for p in placas}),
                "termos": [], "placas": placas, "cache": None}

    # ── 4. número do contrato (para quem tem letra; o numérico já tentou) ───
    achados = _por_contrato(conn, bruto)
    if achados["achou_por"]:
        return achados

    # ── 5. ID em uso (o mais caro, e o único que sai deste banco) ───────────
    por_id = por_id_em_uso(conn, bruto, cache_weso)
    # Devolve também quando a série EXISTE na WESO e não deu em contrato: essa é
    # a resposta mais útil da busca inteira ("o equipamento está instalado e não
    # há contrato por trás"), e a mensagem genérica a apagava.
    if por_id["achou_por"] or por_id.get("serie_encontrada"):
        return por_id

    return {**_vazio(q, "não achei por nome, CNPJ, placa, número de termo nem "
                        "série de rastreador"),
            "cache": por_id.get("cache")}
