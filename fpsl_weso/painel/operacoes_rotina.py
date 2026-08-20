"""A rotina da aba OPERAÇÕES (F5) — os quatro casos que terminam o trabalho.

O que a etapa 4 deixa pendente, esta rotina termina. Ela lê a tabela do painel,
não o Harmonit: o varredor de OS já roda a cada 5 min e guarda a oficina em
`os_historico`, e a rotina consome dali.

Os quatro casos, na ordem obrigatória da spec:

    recipiente ..... série apareceu na WESO -> escreve na OS -> devolve ao
                     estoque -> remove o recipiente
    rescisao ....... oficina de desinstalação -> devolve ao estoque
    ressarcimento .. oficina na híbrida -> devolve ao estoque
    substituicao ... solta do veículo antigo -> confere Estoque relendo ->
                     vincula na placa_entrada

🚨 DEVOLVER AO ESTOQUE É SEMPRE O PRIMEIRO PASSO. Excluir o veículo NÃO libera
o rastreador -- são duas chamadas, e `situacao` é objeto, não texto. Medido em
14/08 na Velasco: apagado o veículo, o rastreador continuou `Instalado` sem
veículo nenhum.

🚨 A SUBSTITUIÇÃO É A ÚNICA QUE VINCULA, e a WESO RECUSA vincular rastreador já
`Instalado` (409 em HTML). Inverter a ordem prende o equipamento no veículo
errado.

═══════════════════════════════════════════════════════════════════════════════
🚨 A OFICINA É O GATILHO PARA IR OLHAR. QUEM DECIDE É O ESTADO RELIDO.

Medido no `os_historico` em 20/08: `status` só tem dois valores, 1 (87
ocorrências) e 2 (99). A investigação de 08/2026 que está em
`backups/scripts_avulsos_2026-08/testar_hipotese_os.py` identifica os dois --
**2 é desinstalação, 1 é instalação** -- e levanta uma hipótese que muda o
desenho desta rotina:

    "o registro de oficina numa OS é uma INTENÇÃO. Quem executa (fecha a
     instalação e vira o 'instalado' do rastreador) é a FINALIZAÇÃO da OS."

Se a hipótese vale, agir só porque a oficina existe seria agir antes de o
trabalho acontecer. Não achei registro de que ela tenha sido confirmada.

Por isso a rotina NÃO age sobre o registro: ela usa a oficina apenas para saber
que vale a pena ir olhar, e decide pelo estado que ela mesma relê na WESO. Se o
equipamento já está em `Estoque`, não há o que fazer e a pendência fecha; se
ainda está `Instalado`, ela faz e confere relendo.

Isso vale com a hipótese verdadeira e com ela falsa — que é o único desenho
possível enquanto ninguém mediu. Ver `docs/fpsl/28_Operacoes.md`.
═══════════════════════════════════════════════════════════════════════════════
"""
import asyncio
import json
import logging

from . import operacoes_equipamentos as eqp
from . import operacoes_espera as esp
from .. import storage
from ..harmonit_client import harmonit_get, harmonit_post

log = logging.getLogger("fpsl.operacoes.rotina")

# 🚨 MEDIDO, NÃO SUPOSTO. Ver o bloco no topo do arquivo.
STATUS_OFICINA_INSTALACAO = 1
STATUS_OFICINA_DESINSTALACAO = 2

# A cada 6 h, como a spec pede. O `TETO_TENTATIVAS` de `operacoes_espera` é que
# impede o laço infinito.
INTERVALO_ROTINA = 6 * 60 * 60


def _unwrap(r):
    d = r.get("data", r) if isinstance(r, dict) else r
    if isinstance(d, dict) and "lista" in d:
        return d["lista"]
    return d


# ── ler a oficina, do painel e não do Harmonit ───────────────────────────────

async def _oficinas_da_os(numero_os: int | None) -> list[dict] | None:
    """As oficinas que o varredor já guardou. None = a OS ainda não foi vista.

    🚨 None NÃO É "SEM OFICINA". A OS pode ter sido criada há minutos e o
    varredor ainda não ter chegado nela. Tratar as duas como a mesma coisa faria
    a rotina desistir de trabalho que só não tinha sido lido ainda.
    """
    if not numero_os:
        return None

    def _run():
        with storage._connect() as conn:
            r = conn.execute("SELECT oficinas_json FROM os_historico "
                             "WHERE numero_os = ?", (numero_os,)).fetchone()
        return None if r is None else json.loads(r[0] or "[]")
    return await asyncio.get_running_loop().run_in_executor(None, _run)


def _tem_desinstalacao(oficinas: list[dict]) -> bool:
    return any(o.get("status") == STATUS_OFICINA_DESINSTALACAO
               for o in oficinas or [])


# ── escrever a série na OS já criada ─────────────────────────────────────────

async def _escrever_serie_na_os(numero_os: int, serie: str) -> tuple[bool, str]:
    """Regrava a OS trocando `NUMERO DE SERIE` pela série de verdade.

    🚨 É SAVE COMPLETO, NÃO EDIÇÃO DE CAMPO. Regravar com `id` atualiza em vez
    de duplicar -- medido em 14/08 na OS de teste 16755 -- mas o payload vai
    INTEIRO: mandar só a descrição apagaria todo o resto. Por isso relê a OS
    antes de gravar.
    """
    try:
        d = _unwrap(await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero",
                                       params={"numeroOs": numero_os}))
    except Exception as exc:
        return False, f"não consegui reler a OS {numero_os}: {exc}"
    if not d:
        return False, f"a OS {numero_os} não foi encontrada para reler"

    descricao = str(d.get("descricaoDetalhada") or "")
    if eqp.MARCADOR_SERIE_A_PREENCHER not in descricao:
        # Já tem série, ou a descrição mudou. Não reescreve por cima.
        return True, "a descrição já não tinha o marcador — nada a trocar"

    nova = descricao.replace(eqp.MARCADOR_SERIE_A_PREENCHER, serie)
    payload = dict(d)
    payload["descricaoDetalhada"] = nova
    try:
        await harmonit_post("/OrdemServico/SalvarOrdemServico", payload)
    except Exception as exc:
        return False, f"a regravação da OS {numero_os} falhou: {exc}"

    # A prova é reler, nunca o código de retorno.
    try:
        conf = _unwrap(await harmonit_get(
            "/OrdemServico/ObterOrdemServicoPorNumero",
            params={"numeroOs": numero_os}))
    except Exception as exc:
        return False, f"gravei mas não consegui conferir a OS {numero_os}: {exc}"
    if serie in str((conf or {}).get("descricaoDetalhada") or ""):
        return True, f"série {serie} escrita na OS {numero_os}"
    return False, (f"a OS {numero_os} não recusou, mas a série não aparece na "
                   "releitura")


# ── caso 1: o recipiente ─────────────────────────────────────────────────────

async def _caso_recipiente(p: dict) -> dict:
    passos: list[str] = []
    placa_rec = p.get("recipiente_placa")
    if not placa_rec:
        await esp.falhar(p["id"], "pendência sem placa de recipiente", passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "erro": "pendência sem placa de recipiente"}

    lidos = await eqp.dados_das_placas([placa_rec])
    dado = lidos.get(eqp.chave(placa_rec)) or {}
    serie = dado.get("serie")
    if not serie:
        estado = await esp.falhar(
            p["id"], "a série ainda não apareceu no recipiente", passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": "a série ainda não apareceu"}
    passos.append(f"série {serie} encontrada em {placa_rec}")

    ok, msg = await _escrever_serie_na_os(p.get("numero_os"), serie)
    passos.append(msg)
    if not ok:
        estado = await esp.falhar(p["id"], msg, passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": msg, "passos": passos}

    # 🚨 DEVOLVE AO ESTOQUE E SÓ ENTÃO APAGA. Na ordem contrária sobraria série
    # presa sem dono, que é invisível.
    r = await eqp.liberar_recipiente(
        dado.get("veiculo_id") or p.get("veiculo_id"),
        dado.get("rastreador_id") or p.get("rastreador_id"))
    passos.extend(r.get("passos") or [])
    if not r.get("ok"):
        estado = await esp.falhar(p["id"], r.get("erro") or "falha ao liberar",
                                  passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": r.get("erro"), "passos": passos,
                "dados_para_correcao": r.get("dados_para_correcao")}

    await esp.concluir(p["id"], passos)
    return {"id": p["id"], "caso": p["caso"], "ok": True, "passos": passos}


# ── caso 2 e 3: devolver ao estoque (rescisão e ressarcimento) ───────────────

async def _caso_devolver(p: dict) -> dict:
    """Rescisão e ressarcimento: o equipamento volta ao estoque.

    ⚠️ O veículo NÃO é apagado. Regra 14: devolver o rastreador ao estoque
    deixa o veículo com `rastreador_id` nulo -- não transmite, não aparece, não
    some. `/Veiculos/Excluir` apagaria um veículo real do cliente.
    """
    passos: list[str] = []
    oficinas = await _oficinas_da_os(p.get("numero_os"))
    if oficinas is None:
        estado = await esp.falhar(
            p["id"], "a OS ainda não foi vista pelo varredor", passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": "OS ainda não varrida"}
    if not _tem_desinstalacao(oficinas):
        estado = await esp.falhar(
            p["id"], "ainda não há oficina de desinstalação nesta OS", passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": "sem oficina de desinstalação"}
    passos.append("oficina de desinstalação registrada na OS")

    lidos = await eqp.dados_das_placas([p["placa"]])
    dado = lidos.get(eqp.chave(p["placa"])) or {}
    rid = dado.get("rastreador_id") or p.get("rastreador_id")
    if not rid:
        # 🚨 SEM RASTREADOR NÃO É ERRO: pode já ter sido solto. Conclui, porque
        # o estado desejado é o que existe.
        await esp.concluir(p["id"], passos + ["o veículo já não tem rastreador"])
        return {"id": p["id"], "caso": p["caso"], "ok": True,
                "passos": passos + ["já não tinha rastreador"]}

    situacao = await eqp._situacao_do_rastreador(rid)
    if situacao == eqp.SITUACAO_LIVRE:
        await esp.concluir(p["id"], passos + ["já estava em Estoque"])
        return {"id": p["id"], "caso": p["caso"], "ok": True,
                "passos": passos + ["já estava em Estoque"]}

    liberou = await eqp._mudar_situacao(rid, eqp.SITUACAO_LIVRE)
    passos.append(f"rastreador {rid} -> Estoque: "
                  f"{'confirmado relendo' if liberou else 'NÃO confirmou'}")
    if not liberou:
        estado = await esp.falhar(
            p["id"], f"o rastreador {rid} não voltou para Estoque", passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": "não voltou para Estoque",
                "passos": passos, "dados_para_correcao": {"rastreador_id": rid}}

    await esp.concluir(p["id"], passos)
    return {"id": p["id"], "caso": p["caso"], "ok": True, "passos": passos}


# ── caso 4: a substituição, a única que vincula ─────────────────────────────

async def _caso_substituicao(p: dict) -> dict:
    """Solta do veículo antigo, confere Estoque relendo, vincula no novo.

    🚨 A ORDEM NÃO É PREFERÊNCIA. A WESO recusa vincular rastreador que já está
    `Instalado`, devolvendo 409 em HTML. Vincular antes de soltar prenderia o
    equipamento no veículo errado -- e o 409 em HTML é justamente o tipo de
    resposta que o cliente lê como sucesso.
    """
    passos: list[str] = []
    if not p.get("placa_entrada"):
        await esp.falhar(p["id"], "pendência de substituição sem placa de "
                                  "entrada", passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "erro": "sem placa de entrada"}

    oficinas = await _oficinas_da_os(p.get("numero_os"))
    if oficinas is None:
        estado = await esp.falhar(p["id"], "a OS ainda não foi vista pelo "
                                           "varredor", passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": "OS ainda não varrida"}
    if not _tem_desinstalacao(oficinas):
        estado = await esp.falhar(p["id"], "ainda não há oficina de "
                                           "desinstalação nesta OS", passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": "sem oficina de desinstalação"}

    lidos = await eqp.dados_das_placas([p["placa"], p["placa_entrada"]])
    saida = lidos.get(eqp.chave(p["placa"])) or {}
    entrada = lidos.get(eqp.chave(p["placa_entrada"])) or {}
    rid = saida.get("rastreador_id") or p.get("rastreador_id")
    if not rid:
        estado = await esp.falhar(
            p["id"], f"a placa {p['placa']} já não tem rastreador para mover",
            passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": "sem rastreador para mover"}

    # 1. soltar
    if (await eqp._situacao_do_rastreador(rid)) != eqp.SITUACAO_LIVRE:
        if not await eqp._mudar_situacao(rid, eqp.SITUACAO_LIVRE):
            estado = await esp.falhar(
                p["id"], f"o rastreador {rid} não soltou do veículo antigo",
                passos)
            return {"id": p["id"], "caso": p["caso"], "ok": False,
                    "estado": estado, "erro": "não soltou",
                    "dados_para_correcao": {"rastreador_id": rid}}
    passos.append(f"rastreador {rid} solto e conferido em Estoque")

    # 2. vincular no novo
    vid = entrada.get("veiculo_id")
    if not vid:
        estado = await esp.falhar(
            p["id"], f"a placa de entrada {p['placa_entrada']} não existe na "
                     "WESO — não há onde vincular", passos)
        return {"id": p["id"], "caso": p["caso"], "ok": False,
                "estado": estado, "erro": "placa de entrada não existe",
                "dados_para_correcao": {"rastreador_id": rid}}

    try:
        await eqp.weso_post("/Rastreadores/Atualizar",
                            {"id": rid, "veiculo": {"id": vid},
                             "situacao": {"descricao": eqp.SITUACAO_PRESA}})
    except Exception as exc:
        log.warning("rotina: vinculo de %s em %s devolveu erro: %s",
                    rid, vid, exc)

    # A prova é reler.
    confere = await eqp.dados_das_placas([p["placa_entrada"]])
    novo = confere.get(eqp.chave(p["placa_entrada"])) or {}
    if novo.get("rastreador_id") == rid:
        passos.append(f"rastreador {rid} vinculado em {p['placa_entrada']} "
                      "(conferido relendo)")
        await esp.concluir(p["id"], passos)
        return {"id": p["id"], "caso": p["caso"], "ok": True, "passos": passos}

    estado = await esp.falhar(
        p["id"], f"o rastreador {rid} soltou mas não aparece vinculado em "
                 f"{p['placa_entrada']} na releitura", passos)
    return {"id": p["id"], "caso": p["caso"], "ok": False, "estado": estado,
            "erro": "soltou e não vinculou — o equipamento está em Estoque",
            "passos": passos,
            "dados_para_correcao": {"rastreador_id": rid, "veiculo_id": vid}}


# ── o laço ───────────────────────────────────────────────────────────────────

_TRATADORES = {
    "recipiente": _caso_recipiente,
    "rescisao": _caso_devolver,
    "ressarcimento": _caso_devolver,
    "substituicao": _caso_substituicao,
}


async def rodar(caso: str | None = None) -> dict:
    """Uma passada. Nunca levanta: pendência que estoura vira falha contada."""
    pendentes = await esp.pendentes(caso)
    resultados = []
    for p in pendentes:
        tratador = _TRATADORES.get(p["caso"])
        if not tratador:
            await esp.falhar(p["id"], f"caso sem tratador: {p['caso']!r}")
            continue
        try:
            resultados.append(await tratador(p))
        except Exception as exc:
            log.exception("rotina: pendência %s estourou", p["id"])
            await esp.falhar(p["id"], f"erro inesperado: {exc}")
            resultados.append({"id": p["id"], "caso": p["caso"], "ok": False,
                               "erro": f"erro inesperado: {exc}"})
    return {"lidas": len(pendentes), "resultados": resultados,
            "concluidas": sum(1 for r in resultados if r.get("ok")),
            "resumo": await esp.resumo()}


async def loop_rotina():
    """O laço de 6 h. Espaça do boot para não competir com a primeira varredura
    de OS, que é quem alimenta a tabela que esta rotina lê."""
    await asyncio.sleep(900)
    while True:
        try:
            r = await rodar()
            if r["lidas"]:
                log.info("rotina: %s pendências, %s concluídas",
                         r["lidas"], r["concluidas"])
        except Exception:
            log.exception("rotina: a passada falhou inteira")
        await asyncio.sleep(INTERVALO_ROTINA)
