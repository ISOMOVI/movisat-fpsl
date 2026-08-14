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
import time
import sys
import re

from fpsl_weso.client import weso_get, weso_post

log = logging.getLogger(__name__)

MARCADOR_NAO_LOCALIZADO = "série não localizada"

# 🚨 DOIS MARCADORES, DOIS SENTIDOS DIFERENTES (decisao do usuario, 14/08).
# `série não localizada` e o SAIRA: nao sei o que esta no veiculo, e ninguem
# vai preencher depois. `NUMERO DE SERIE` e o ENTRARA: o equipamento ainda nao
# foi vinculado, e o tecnico escreve a serie na hora da instalacao. E o mesmo
# texto literal que os templates de contrato ja usavam desde o inicio.
MARCADOR_SERIE_A_PREENCHER = "NUMERO DE SERIE"


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


# 🚨 O ESPACO PODE APARECER EM QUALQUER LUGAR, MESMO PADRONIZADO. Quem cria o
# recipiente digita a mao, e `GJN8689 - MANUT`, `GJN 8689-MANUT` e
# ` GJN8689-MANUT` (esta ultima ja existe na WESO) sao a mesma coisa. Por isso
# a comparacao normaliza OS DOIS LADOS, tirando TODO espaco.
#
# ⚠️ A TRAVA E A PLACA ORIGINAL, nao o texto todo (ideia do usuario, 14/08):
# como a chave e montada com a placa normalizada inteira mais o sufixo, um
# recipiente com a placa truncada (`GJN868-MANUT`) simplesmente nao casa. Nao
# ha margem para "parecido o bastante".

def chave_recipiente(placa: str, sufixo: str) -> str:
    """Chave normalizada do recipiente: `GJN 8689` + `-MANUT` -> `GJN8689-MANUT`."""
    base = _chave(placa)
    return f"{base}{_chave(sufixo)}" if base else ""


# 🚨 A MEDIÇÃO DE 29/07 ENVELHECEU E INVERTEU. Naquela data a base inteira
# custava 2,3s e filtrar UMA placa custava ~6s -- por isso todo este módulo foi
# escrito para puxar a base toda. Medido de novo em 14/08, depois de a geração
# de manutenção passar de 40s e o usuário reportar erro:
#
#     base inteira ......... 16,65s  (1.964 registros)
#     uma placa filtrada .... 0,67s
#
# A manutenção puxava a base DUAS vezes (uma para a placa real, outra para o
# recipiente), o que dava ~35s só de WESO -- perto do teto do nginx.
#
# ⚠️ NÚMERO DE DESEMPENHO TEM VALIDADE. O comentário antigo não estava errado
# quando foi escrito; ficou errado depois, e ninguém remede porque medição não
# tem teste. Se voltar a inverter, é este limiar que muda.
LIMIAR_PLACA_A_PLACA = 6

# 🚨 TETO PARA A BUSCA DE ULTIMO RECURSO. A base inteira oscila muito -- medido
# em 14/08 entre 7s e 33s no mesmo minuto -- e o nginx corta a requisicao em
# 35s (`proxy_read_timeout`). Sem teto, "o recipiente ainda nao foi criado"
# virava 504 na cara de quem esta usando, sem mensagem nenhuma. Foi o erro que
# a Erika viu.
#
# ⚠️ ESTOURAR O TETO FALHA PARA O LADO SEGURO: o recipiente e dado como nao
# encontrado, a OS sai com `NUMERO DE SERIE` e SEM equipamento, e o aviso
# aparece na tela. Nunca sai equipamento errado -- so falta, e com recado.
TETO_LEITURA_AO_VIVO = 18.0


def _grafias(placa: str) -> tuple:
    """As grafias que valem tentar antes de recorrer a base inteira.

    A consulta e por igualdade EXATA. A WESO tem registro com espaco na frente
    (` OOM3895-UPGRADE` e real) e o recipiente e digitado a mao pelo setor de
    configuracao, entao a variacao mora no espaco. Cada tentativa custa 0,67s.
    """
    p = str(placa or "")
    limpo = p.strip()
    vistas, saida = set(), []
    for g in (p, f" {p}", limpo, limpo.replace("-", " - "), limpo.replace(" ", "")):
        if g and g not in vistas:
            vistas.add(g)
            saida.append(g)
    return tuple(saida)


async def _veiculos_ao_vivo(placas: list[str], alvo: set[str]) -> list | None:
    """Registros de veículo da WESO para estas placas. `None` = não deu para ler.

    Poucas placas: uma consulta por placa (0,67s cada). Muitas: a base inteira,
    que a partir de ~25 placas volta a compensar.

    ⚠️ `?placa=` compara por IGUALDADE EXATA e devolve VAZIO, não erro. Placa
    gravada com grafia diferente some -- por isso o que não aparecer na consulta
    individual é procurado na base inteira, que casa por chave normalizada.
    """
    if len(alvo) <= LIMIAR_PLACA_A_PLACA:
        # 🚨 O ORCAMENTO E DO CONJUNTO, NAO DE CADA CHAMADA. Medido em 14/08: a
        # WESO oscila muito, e quando esta carregada ate a consulta de UMA placa
        # passa de 5s. Com teto so por chamada, 10 tentativas somavam 40s e o
        # nginx cortava em 35s -- o usuario via a tela morrer sem mensagem.
        inicio = time.monotonic()

        def restante():
            return TETO_LEITURA_AO_VIVO - (time.monotonic() - inicio)

        achados, faltando = [], set(alvo)
        for p in placas:
            if not str(p or "").strip():
                continue
            # ⚠️ GRAFIAS CONHECIDAS ANTES DE DESISTIR. A consulta e por
            # igualdade EXATA, e a WESO tem registro gravado com espaco na
            # frente -- ` OOM3895-UPGRADE` e real.
            for grafia in _grafias(p):
                if _chave(p) not in faltando or restante() <= 1:
                    break
                try:
                    r = await asyncio.wait_for(
                        weso_get("/Veiculos/Consultar", {"placa": grafia}),
                        min(6.0, restante()))
                except asyncio.TimeoutError:
                    log.warning("equipamentos: consulta de %r passou do tempo", grafia)
                    continue
                except Exception as exc:
                    log.warning("equipamentos: consulta de %r falhou: %s", grafia, exc)
                    continue
                for v in (r.get("veiculos") if isinstance(r, dict) else r) or []:
                    achados.append(v)
                    faltando.discard(_chave(v.get("placa")))
        if not faltando:
            return achados
        if restante() <= 3:
            log.warning("equipamentos: sem tempo para a base inteira; %s placa(s) "
                        "ficam como NAO ENCONTRADAS: %s",
                        len(faltando), ", ".join(sorted(faltando))[:120])
            return achados
        log.info("equipamentos: %s placa(s) sem resposta exata -- indo a base "
                 "inteira: %s", len(faltando), ", ".join(sorted(faltando))[:120])
        base = await _base_inteira(restante())
        if base is None:
            return achados
        # 🚨 DEDUPLICAR POR ID. O mesmo veículo volta nas duas consultas, e
        # `dados_das_placas` trata chave repetida como AMBIGUIDADE -- ele
        # descartaria o recipiente achado, dizendo que há dois. Falsa
        # ambiguidade é pior que lentidão: some o equipamento da OS.
        return _sem_repetido(achados + base)

    return await _base_inteira()


def _sem_repetido(veiculos: list) -> list:
    vistos, saida = set(), []
    for v in veiculos:
        vid = v.get("id")
        if vid in vistos:
            continue
        vistos.add(vid)
        saida.append(v)
    return saida


async def _base_inteira(teto: float | None = None) -> list | None:
    """A base toda. `teto` em segundos: estourou, devolve None (= nao sei)."""
    try:
        chamada = weso_get("/Veiculos/Consultar", {})
        r = await (asyncio.wait_for(chamada, teto) if teto else chamada)
    except asyncio.TimeoutError:
        log.warning("equipamentos: base de veiculos passou de %ss -- desisti; "
                    "o que faltava fica como NAO ENCONTRADO", teto)
        return None
    except Exception as exc:
        log.warning("equipamentos: base de veiculos indisponivel ao vivo: %s", exc)
        return None
    return (r.get("veiculos") if isinstance(r, dict) else r) or []


async def dados_das_placas(placas: list[str]) -> dict[str, dict]:
    """{chave_normalizada: dados} lido AO VIVO da WESO, sem passar pelo cache.

    🚨 AO VIVO E REQUISITO, NAO LUXO, nos perfis de manutencao: o recipiente
    e criado pelo setor de configuracao minutos antes da OS, e o cache local
    so atualiza as 04:15. Ler do cache devolveria "modelo nao localizado" para
    um equipamento que existe -- e OS sem a linha do equipamento e exatamente
    o defeito que o usuario achou auditando o termo 8820.

    O custo se inverteu entre julho e agosto -- ver `LIMIAR_PLACA_A_PLACA`
    acima. Hoje: poucas placas vao uma a uma (0,67s cada), muitas vao pela
    base inteira (16,65s).

    Devolve, por placa: veiculo_id, placa como esta gravada, descricao,
    rastreador_id, serie e modelo. Nunca levanta -- placa que nao resolveu
    simplesmente nao entra no dict.
    """
    alvo = {_chave(p) for p in placas if str(p or "").strip()}
    if not alvo:
        return {}
    base = await _veiculos_ao_vivo(placas, alvo)
    if base is None:
        return {}

    # Junta TODOS os casos por chave antes de decidir: duas placas diferentes
    # que normalizam igual sao ambiguidade, e ambiguidade nao se resolve por
    # "pega o primeiro" -- e assim que se grava a serie do equipamento errado.
    por_chave: dict[str, list[dict]] = {}
    for v in base:
        k = _chave(v.get("placa"))
        if k in alvo:
            por_chave.setdefault(k, []).append(v)

    dados: dict[str, dict] = {}
    for chave, achados in por_chave.items():
        if len(achados) > 1:
            log.warning("equipamentos: %s casos para a chave %r na WESO -- ambiguo",
                        len(achados), chave)
            dados[chave] = {"ambiguo": [a.get("placa") for a in achados]}
            continue
        v = achados[0]
        dados[chave] = {
            "veiculo_id": v.get("id"),
            "placa": v.get("placa"),
            "descricao": v.get("descricao"),
            "rastreador_id": v.get("rastreador_id"),
            "serie": None,
            "modelo": None,
        }

    ids = [d["rastreador_id"] for d in dados.values()
           if not d.get("ambiguo") and d.get("rastreador_id")]
    if ids:
        por_id = await _rastreadores_por_id(ids)
        for d in dados.values():
            r_ = por_id.get(d.get("rastreador_id"))
            if r_:
                d["serie"] = r_.get("numeroSerie")
                d["modelo"] = r_.get("modelo")
    return dados


async def _rastreadores_por_id(ids: list[int]) -> dict[int, dict]:
    """{id: registro} -- em lote acima do limiar, um a um abaixo dele.

    Mesmo criterio ja usado em `buscar_seriais`: 1 rastreador por id custa
    0,16s, e a lista inteira custa 11,6s. Abaixo de 4 ids, N chamadas ganham.
    """
    unicos = sorted({i for i in ids if i})
    if not unicos:
        return {}
    achados: dict[int, dict] = {}
    if len(unicos) >= LIMIAR_LOTE:
        try:
            r = await weso_get("/Rastreadores/Consultar", {"numeroSerie": ""})
            todos = (r.get("rastreadores") if isinstance(r, dict) else r) or []
            alvo = set(unicos)
            for t in todos:
                if t.get("id") in alvo:
                    achados[t["id"]] = t
            return achados
        except Exception as exc:
            log.warning("equipamentos: lote de rastreadores falhou (%s), indo por id", exc)
    for rid in unicos:
        if rid in achados:
            continue
        try:
            r = await weso_get("/Rastreadores/Consultar", {"id": rid})
            lst = (r.get("rastreadores") if isinstance(r, dict) else r) or []
            if lst:
                achados[rid] = lst[0]
        except Exception as exc:
            log.warning("equipamentos: rastreador %s falhou: %s", rid, exc)
    return achados


async def buscar_recipientes(placas: list[str], sufixo: str) -> dict[str, dict]:
    """{chave_da_placa_ORIGINAL: dados_do_recipiente} -- ao vivo.

    A chave e a placa original normalizada (`GJN8689`), nao a do recipiente:
    quem consulta depois tem a placa do veiculo em maos, nao a derivada.
    """
    if not sufixo:
        return {}
    mapa = {chave_recipiente(p, sufixo): _chave(p) for p in placas if str(p or "").strip()}
    mapa.pop("", None)
    if not mapa:
        return {}
    achados = await dados_das_placas(list(mapa))
    return {mapa[k]: v for k, v in achados.items() if k in mapa}


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


# ── Liberar a serie depois da OS ─────────────────────────────────────────────
# 🚨 EXCLUIR O VEICULO NAO LIBERA O RASTREADOR. Medido na Pastelaria Velasco em
# 14/08: criei `OVG7C78-MANUT` com o rastreador 50171 (que estava em Estoque),
# ele virou Instalado, apaguei o veiculo com `/Veiculos/Excluir` -- e o
# rastreador CONTINUOU Instalado, agora sem veiculo nenhum. Sao duas chamadas,
# nao uma. Quem devolve ao estoque e `/Rastreadores/Atualizar`.
#
# 🚨 `situacao` E OBJETO, NAO TEXTO. `{"situacao": "Estoque"}` devolve
# "JSON invalido"; o formato certo e `{"situacao": {"descricao": "Estoque"}}`.
#
# 🚨 A ORDEM E LIBERAR PRIMEIRO, APAGAR DEPOIS. Se a segunda falhar sobra um
# recipiente vazio -- visivel e inofensivo. Na ordem contraria sobraria serie
# presa sem dono, que e invisivel e e justamente o que estamos consertando.
#
# ⚠️ A WESO MENTE NO CODIGO DE RETORNO NOS DOIS SENTIDOS. No mesmo teste, o
# cadastro do recipiente devolveu erro HTML e GRAVOU o registro. Por isso cada
# passo aqui e conferido RELENDO O ESTADO, nunca pelo status da resposta.

SITUACAO_LIVRE = "Estoque"
SITUACAO_PRESA = "Instalado"


async def _situacao_do_rastreador(rastreador_id: int) -> str | None:
    try:
        r = await weso_get("/Rastreadores/Consultar", {"id": rastreador_id})
    except Exception as exc:
        log.warning("equipamentos: situacao do rastreador %s indisponivel: %s",
                    rastreador_id, exc)
        return None
    lst = (r.get("rastreadores") if isinstance(r, dict) else r) or []
    return (lst[0].get("situacao") if lst else None)


async def _veiculo_existe(veiculo_id: int) -> bool | None:
    """True/False, ou None quando nao deu para saber (que nao autoriza nada)."""
    try:
        r = await weso_get("/Veiculos/Consultar", {"veiculo_id": veiculo_id})
    except Exception as exc:
        log.warning("equipamentos: veiculo %s indisponivel: %s", veiculo_id, exc)
        return None
    return bool((r.get("veiculos") if isinstance(r, dict) else r) or [])


async def _mudar_situacao(rastreador_id: int, situacao: str) -> bool:
    try:
        await weso_post("/Rastreadores/Atualizar",
                        {"id": rastreador_id, "situacao": {"descricao": situacao}})
    except Exception as exc:
        log.warning("equipamentos: mudar situacao de %s para %r falhou: %s",
                    rastreador_id, situacao, exc)
    # Confirma RELENDO -- o retorno da WESO nao e prova de nada.
    return (await _situacao_do_rastreador(rastreador_id)) == situacao


async def liberar_recipiente(veiculo_id: int, rastreador_id: int | None) -> dict:
    """Devolve a serie ao estoque e apaga o recipiente. Nunca levanta.

    Devolve sempre um dicionario com `ok`, `passos` (o que aconteceu em cada
    etapa) e, quando deu errado, `erro` e `dados_para_correcao` -- os numeros
    que uma pessoa precisa para resolver na mao.
    """
    passos: list[str] = []

    if not veiculo_id:
        return {"ok": False, "erro": "recipiente sem veiculo_id -- nada a liberar",
                "passos": passos, "dados_para_correcao": {}}

    liberou = False
    if rastreador_id:
        liberou = await _mudar_situacao(rastreador_id, SITUACAO_LIVRE)
        if not liberou:
            situacao = await _situacao_do_rastreador(rastreador_id)
            return {
                "ok": False,
                "erro": (f"nao consegui devolver o equipamento ao estoque "
                         f"(esta como {situacao!r}). NADA foi alterado: o "
                         f"recipiente continua na WESO."),
                "passos": passos,
                "dados_para_correcao": {"veiculo_id": veiculo_id,
                                        "rastreador_id": rastreador_id,
                                        "situacao_atual": situacao},
            }
        passos.append(f"equipamento {rastreador_id} devolvido ao estoque")

    try:
        await weso_post("/Veiculos/Excluir", {"veiculo_id": veiculo_id})
    except Exception as exc:
        log.warning("equipamentos: exclusao do recipiente %s falhou: %s", veiculo_id, exc)

    ainda_existe = await _veiculo_existe(veiculo_id)
    if ainda_existe is False:
        passos.append(f"recipiente {veiculo_id} excluido")
        return {"ok": True, "passos": passos, "dados_para_correcao": {}}

    # 🚨 DESFAZER: o recipiente continua de pe (ou nao deu para conferir) e o
    # equipamento ja saiu do Instalado. Deixar assim seria pior que nao ter
    # mexido -- um recipiente vivo apontando para equipamento "em estoque".
    desfez = False
    if liberou and rastreador_id:
        desfez = await _mudar_situacao(rastreador_id, SITUACAO_PRESA)
        passos.append("desfeito: equipamento voltou para Instalado" if desfez
                      else "DESFAZER TAMBEM FALHOU")
    motivo = ("nao consegui excluir o recipiente" if ainda_existe
              else "nao consegui confirmar se o recipiente foi excluido")
    return {
        "ok": False,
        "erro": (f"{motivo}. "
                 + ("O equipamento foi devolvido ao estado anterior."
                    if desfez else
                    "ATENCAO: o equipamento NAO voltou ao estado anterior.")),
        "passos": passos,
        "dados_para_correcao": {"veiculo_id": veiculo_id,
                                "rastreador_id": rastreador_id,
                                "desfeito": desfez},
    }
