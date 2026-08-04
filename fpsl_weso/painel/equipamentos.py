"""Placa -> numero de serie do rastreador (o "ID do equipamento" da WESO).

Criado 2026-07-29. Motivo: a descricao da OS trazia o texto literal
`NUMERO DE SERIE` (os_router.py, perfil agrupado) -- o encaixe existia desde
sempre e nunca foi preenchido. O usuario confirmou que esse campo e o numero
do rastreador, o mesmo `numeroSerie` da WESO.

Caminho (2 passos, nao ha endpoint que va direto de placa a serie):
    /Veiculos/Consultar?placa=X   -> rastreador_id
    /Rastreadores/Consultar?id=N  -> numeroSerie

Custo medido em 2026-07-29:
    consulta de 1 placa .......... rapida
    1 rastreador por id .......... 0,16s
    base completa de veiculos .... 2,3s  (1.962 registros, so no fallback)
  => ~6s para um termo de 23 placas.

DUAS decisoes de projeto aqui:

1. BEST-EFFORT. Nada nesta funcao pode impedir a geracao de OS. Se a WESO
   estiver fora, devolve o que conseguiu e a descricao sai com o marcador de
   nao-localizado -- OS gerada com uma lacuna visivel e melhor que OS nao
   gerada.

2. TOLERANTE A ESPACO. `/Veiculos/Consultar?placa=` compara por igualdade
   EXATA. Em 29/07 havia 110 placas com espaco nas pontas na WESO (ja
   normalizadas), e a consulta devolvia VAZIO em vez de erro -- falha
   silenciosa. Se a consulta direta nao achar, cai na base completa e casa
   por placa normalizada. Ver docs/fpsl/21_Plano_Higiene_Placas.md.
"""
import asyncio
import logging
import sys
import re

from fpsl_weso.client import weso_get

log = logging.getLogger(__name__)

MARCADOR_NAO_LOCALIZADO = "série não localizada"


def _chave(placa: str) -> str:
    return re.sub(r"\s+", "", str(placa or "")).upper()


async def _rastreador_id_por_placa(placas: list[str]) -> dict[str, int]:
    """{chave_normalizada: rastreador_id}.

    UMA chamada para a base inteira, nao uma por placa. Medido em 29/07:
    base completa = 2,3s para 1.962 registros; consulta de UMA placa = ~6s
    (a API e mais lenta com filtro que sem). A primeira versao consultava
    placa a placa e levava 62s para 9 placas — inviavel dentro da geracao de
    OS. Como bonus, casar contra a base ja e tolerante a grafia divergente:
    nao precisa de fallback separado.
    """
    alvo = {_chave(p) for p in placas if str(p or "").strip()}
    if not alvo:
        return {}
    try:
        r = await weso_get("/Veiculos/Consultar", {})
    except Exception as exc:
        log.warning("equipamentos: base de veiculos indisponivel: %s", exc)
        return {}
    base = (r.get("veiculos") if isinstance(r, dict) else r) or []
    achados: dict[str, int] = {}
    for v in base:
        k = _chave(v.get("placa"))
        if k in alvo and v.get("rastreador_id") and k not in achados:
            achados[k] = v["rastreador_id"]
    faltando = alvo - set(achados)
    if faltando:
        log.info("equipamentos: %s placa(s) sem rastreador na WESO: %s",
                 len(faltando), ", ".join(sorted(faltando))[:200])
    return achados


LIMIAR_LOTE = 4  # acima disso, 1 chamada em lote vence N chamadas por id


# Cache local da base WESO, atualizado 1x/dia (04:15). Ver
# /home/claude/weso_cache/. Medido em 29/07: 21 placas em 1ms pelo cache
# contra 15 a 90s indo a WESO. Nao e otimizacao -- e o que tira uma chamada
# de tempo imprevisivel de dentro da geracao de OS.
CACHE_DIR = "/home/claude/weso_cache"


def _cache():
    """Modulo do cache, ou None se indisponivel. Nunca levanta: o cache e um
    atalho, nao um requisito."""
    try:
        if CACHE_DIR not in sys.path:
            sys.path.insert(0, CACHE_DIR)
        import cache  # noqa: PLC0415
        return cache
    except Exception as exc:
        log.warning("equipamentos: cache indisponivel (%s), indo a WESO", exc)
        return None


LIMIAR_LOTE = 4  # acima disso, 1 chamada em lote vence N chamadas por id


async def buscar_seriais(placas: list[str]) -> dict[str, str]:
    """{chave_normalizada: numeroSerie} para as placas que resolveram.

    Ordem: cache local primeiro; o que faltar (placa cadastrada depois da
    ultima atualizacao, ou cache velho) vai a WESO. Nunca levanta excecao --
    placa ausente simplesmente nao entra no dict.

    Custo medido em 29/07:
        cache ....................... ~1ms para 21 placas
        base de veiculos na WESO .... 2,3s a 24s
        1 rastreador por id ......... 0,16s a 3,6s
        TODOS os rastreadores ....... 11,6s a timeout
    """
    placas = [p for p in placas if str(p or "").strip()]
    if not placas:
        return {}

    seriais: dict[str, str] = {}
    faltando = list(placas)

    c = _cache()
    if c is not None:
        try:
            if not c.esta_fresco():
                log.warning("equipamentos: cache com %sh — usando assim mesmo e "
                            "completando na WESO", c.idade_horas())
            achado = c.seriais_por_placas(placas)
            for p, s in achado.items():
                if s:
                    seriais[_chave(p)] = str(s)
            faltando = [p for p in placas if _chave(p) not in seriais]
            log.info("equipamentos: %s de %s placas resolvidas pelo cache",
                     len(seriais), len(placas))
        except Exception as exc:
            log.warning("equipamentos: leitura do cache falhou (%s), indo a WESO", exc)
            faltando = list(placas)

    if not faltando:
        return seriais

    # O que o cache nao tinha: placa nova, ou cache indisponivel.
    log.info("equipamentos: %s placa(s) indo a WESO ao vivo", len(faltando))
    ids = await _rastreador_id_por_placa(faltando)
    if not ids:
        return seriais

    if len(ids) >= LIMIAR_LOTE:
        try:
            r = await weso_get("/Rastreadores/Consultar", {"numeroSerie": ""})
            todos = (r.get("rastreadores") if isinstance(r, dict) else r) or []
            por_id = {t.get("id"): t.get("numeroSerie") for t in todos if t.get("id")}
            for chave, rid in ids.items():
                if por_id.get(rid):
                    seriais[chave] = str(por_id[rid])
        except Exception as exc:
            log.warning("equipamentos: lote de rastreadores falhou (%s), "
                        "caindo para consulta por id", exc)

    for chave, rid in ids.items():
        if chave in seriais:
            continue
        try:
            r = await weso_get("/Rastreadores/Consultar", {"id": rid})
            lst = (r.get("rastreadores") if isinstance(r, dict) else r) or []
            serie = lst[0].get("numeroSerie") if lst else None
            if serie:
                seriais[chave] = str(serie)
        except Exception as exc:
            log.warning("equipamentos: rastreador %s falhou: %s", rid, exc)

    if len(seriais) < len(placas):
        log.info("equipamentos: %s de %s placas com numero de serie",
                 len(seriais), len(placas))
    return seriais


def serie_de(seriais: dict[str, str], placa: str) -> str:
    """Texto pronto para a descricao da OS."""
    return seriais.get(_chave(placa)) or MARCADOR_NAO_LOCALIZADO
