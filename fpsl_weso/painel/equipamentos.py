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


# ── Upgrade: a placa-recipiente de teste ─────────────────────────────────────
# 🚨 O UPGRADE NAO TROCA DE VEICULO. Troca o equipamento do MESMO veiculo
# (XT40 fixo -> XT40 Portatil). O setor de configuracao cria na WESO uma placa
# derivada -- `OOM 4131` vira `OOM4131-UPGRADE`, descricao `TERMO 8820` -- e
# vincula nela o equipamento novo para testar antes de ir a campo.
#
# ⚠️ ESSA PLACA NAO E DESTINO E NUNCA VIRA VEICULO DA OS. Se virar, a OS sai
# mandando o tecnico instalar num veiculo que nao existe -- mesmo tipo de erro
# do `RFD 2447`: dado plausivel apontando para lugar nenhum. Ela serve so como
# CHAVE para descobrir a serie do equipamento que entra.

def placa_teste(placa: str, sufixo: str) -> str:
    """`OOM 4131` + `-UPGRADE` -> `OOM4131-UPGRADE`.

    Tira o espaco e sobe a caixa, que e a grafia usada na WESO (conferido nos
    3 registros existentes em 13/08). A busca depois normaliza de novo, entao
    o espaco perdido do ` OOM3895-UPGRADE` -- que esta gravado com espaco na
    frente na WESO -- nao atrapalha.
    """
    base = re.sub(r"\s+", "", str(placa or "").upper())
    return f"{base}{sufixo}" if base else ""


def descricao_da_placa(placa: str) -> str | None:
    """Descricao do veiculo na WESO, ou None se nao deu para saber.

    🚨 None significa NAO SEI, nunca "nao confere". Cache fora do ar e placa
    inexistente sao coisas diferentes de descricao divergente, e so a ultima
    autoriza bloquear alguma coisa.
    """
    c = _cache()
    if c is None:
        return None
    try:
        v = c.veiculo_por_placa(placa)
    except Exception as exc:
        log.warning("equipamentos: descricao de %r indisponivel: %s", placa, exc)
        return None
    return (v or {}).get("descricao")


# ── Modelo do rastreador ─────────────────────────────────────────────────────
# 🚨 O MODELO NAO VEM DO VINCULO. O vinculo (`painel_vinculos_itens`) mapeia o
# TEXTO ESCRITO NO TERMO para um produto fixo do Harmonit: "RASTREADOR" cai
# sempre em ST310U, "RASTREADOR 4G" sempre em XT40. Ou seja, quem decidia o
# modelo era o vendedor que redigiu o contrato.
#
# Medido em 13/08: a WESO tem 15+ modelos em uso (ST310 1646, ST340 889,
# ST300 523, XT40 153, ST4305 138, TK-100 85...) e o vinculo distingue DOIS.
# Um veiculo com ST340 gerava OS dizendo ST310U.
#
# A fonte certa e a WESO, pelo ID da placa. Decisao do usuario em 13/08.

MARCADOR_MODELO = "modelo nao localizado"

# 🚨 ST340 COM LEITOR RFID E ST340RB. Regra do usuario (13/08).
# ⚠️ A WESO NAO SABE DISSO: a API de rastreador devolve
# id/numeroSerie/lote/notaFiscal/firmware/data_cadastro/modelo/situacao/tipo/
# simcard/fornecedor -- nenhum campo de acessorio. O `acessorios` do espelho
# esta VAZIO nos 1998 registros. Entao o RFID so pode vir do TERMO, e por isso
# a regra depende dos itens alocados NAQUELA placa, nao do termo inteiro: num
# termo de 10 placas, so as que recebem leitor viram RB.
MODELO_COM_RFID = {
    "SUNTECH ST340": "Suntech ST340RB",
}


def modelo_da_placa(placa: str) -> str | None:
    """Modelo do rastreador vinculado a placa na WESO, ou None.

    🚨 None e NAO SEI, nunca "nao tem". Cache indisponivel, placa ausente e
    placa sem rastreador sao todos None -- e nenhum deles autoriza afirmar
    modelo nenhum.

    ⚠️ So o cache (sem rede). Placa cadastrada depois da ultima atualizacao do
    cache devolve None ate o proximo ciclo. Foi decisao de projeto no
    `buscar_seriais` nao deixar chamada de tempo imprevisivel dentro da geracao
    de OS, e vale igual aqui.
    """
    c = _cache()
    if c is None:
        return None
    try:
        v = c.veiculo_por_placa(placa)
        if not v or not v.get("rastreador_id"):
            return None
        r = c.rastreador_por_id(v["rastreador_id"])
    except Exception as exc:
        log.warning("equipamentos: modelo de %r indisponivel: %s", placa, exc)
        return None
    return (r or {}).get("modelo") or None


def tem_leitor_rfid(materiais: list[dict]) -> bool:
    """A placa recebe leitor RFID neste termo?

    Olha a DESCRICAO do item, nao o harmonit_id: o id do vinculo pode ser
    recadastrado, o texto do contrato nao. Hoje o vinculo e `LEITOR RFID`
    (6991); `LEITOR I-BUTTON` (6984) e outro acessorio e NAO conta.
    """
    return any("RFID" in str(m.get("descricao") or "").upper() for m in materiais or [])


def modelo_efetivo(modelo: str | None, tem_rfid: bool = False) -> str:
    """Modelo pronto para a OS, ja com a regra do RB aplicada."""
    if not modelo:
        return MARCADOR_MODELO
    if tem_rfid:
        alvo = MODELO_COM_RFID.get(modelo.strip().upper())
        if alvo:
            return alvo
    return modelo
