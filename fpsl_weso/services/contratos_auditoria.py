"""Rotina de auditoria da Gestão de Contratos (`CTR_1.1`) — etapa C6. 2026-10-13.

Compara o que os termos sustentam com o que está em uso na WESO, e grava os
achados para a tela mostrar. **Não escreve no Harmonit, na WESO nem na
Clicksign** — aponta, nunca corrige.

🚨 NASCE DESLIGADA, com interruptor NA PRÓPRIA TELA. É a convenção do FPSL
(oposta à do MoviZap, onde o interruptor mora em `/config` › Geral), e a
`FIN_1.1` provou por que ela importa: ficou desligada de 02/10 a 08/10 e
**nada na tela dizia**. Aqui o estado da rotina aparece onde ela é usada.

🚨 LÊ O CACHE DA WESO, NÃO A API. A base inteira ao vivo levou de 15,6 s a
TIMEOUT em medições de 18/08, com o teto do cliente em 30 s. O cache
(`/home/claude/weso_cache/weso.db`, cron 04:15) é o irmão do cache do Harmonit
e existe para isso.

🚨 E RECUSA COMPARAR COM CACHE VELHO. Cache de 3 dias faria a rotina acusar
"em uso sem contrato" para placa retirada ontem, e "contratada e não instalada"
para placa instalada hoje. Acima de `IDADE_MAXIMA_H` ela não roda e DIZ por
quê -- comparação silenciosa com dado velho é pior que nenhuma comparação.
"""
import asyncio
import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .. import storage
from ..painel import contratos_eventos as motor
from ..painel import contratos_registro as registro
from ..painel import contratos_tabelas

logger = logging.getLogger("fpsl.contratos_auditoria")

FLAG = "contratos_auditoria_ativa"
INTERVALO_ROTINA = 6 * 60 * 60          # 6 h: o cache da WESO é diário (04:15)
IDADE_MAXIMA_H = 48
CACHE_WESO = Path("/home/claude/weso_cache/weso.db")

# Tipos de achado, e o que cada um quer dizer. A tela usa estes textos.
TIPOS = {
    "EM_USO_SEM_CONTRATO": "em uso na WESO e nenhum termo a coloca em contrato",
    "EM_USO_FALTA_ASSINAR": "em uso, sustentada só por termo sem assinatura",
    "ENCERRADA_EM_USO": "encerrada no contrato e ainda em uso na WESO",
    "CONTRATADA_NAO_INSTALADA": "sustentada pelo contrato e ausente na WESO",
    "SUBSTITUICAO_PELA_METADE": "substituição assinada executada só de um lado",
    "PLACA_EM_DOIS_CLIENTES": "a mesma placa está ativa em mais de um cliente",
}


def _weso_do_cache() -> tuple[dict, float | None, int]:
    """{chave: situação do rastreador}, idade do cache em horas, e nº de VEÍCULOS.

    🚨 CHAVE NÃO É VEÍCULO. O mesmo veículo entra no dicionário duas vezes
    quando tem placa E chassi -- são duas formas de achá-lo. A primeira versão
    devolvia `len(placas)` como "veículos na WESO" e a tela mostrou **2.146**
    onde a base tem **1.931**. Número inflado em tela é defeito, mesmo quando o
    resto da conta está certo.
    """
    if not CACHE_WESO.exists():
        return {}, None, 0
    conn = sqlite3.connect(f"file:{CACHE_WESO}?mode=ro", uri=True)
    try:
        idade = None
        try:
            v = conn.execute("SELECT valor FROM meta WHERE chave='atualizado_em'").fetchone()
            if v:
                quando = datetime.fromisoformat(v[0])
                if quando.tzinfo is None:
                    quando = quando.replace(tzinfo=timezone.utc)
                idade = (datetime.now(timezone.utc) - quando).total_seconds() / 3600
        except sqlite3.Error:
            pass
        placas = {}
        n_veiculos = 0
        for placa, chave, chassi, rid in conn.execute(
                "SELECT placa, chave_placa, chassi, rastreador_id FROM veiculos"):
            n_veiculos += 1
            sit = "sem rastreador"
            if rid:
                r = conn.execute("SELECT situacao FROM rastreadores WHERE id=?", (rid,)).fetchone()
                sit = (r[0] if r and r[0] else "sem situacao")
            for k in {motor.chave(chave or placa), motor.chave(chassi or "")} - {""}:
                placas.setdefault(k, sit)
        return placas, idade, n_veiculos
    finally:
        conn.close()


def _achar(conn, weso: dict, hoje=None) -> list:
    """Compara contrato × WESO. Devolve a lista de achados, sem gravar."""
    hoje = hoje or date.today()
    achados = []

    # 🚨 RECALCULA ANTES DE COMPARAR. `contrato_placa` é cache, e o aviso
    # prévio vence pelo CALENDÁRIO -- sem nenhum evento novo para disparar a
    # conta. Comparar sobre o cache velho acusaria como "encerrada em uso" uma
    # placa ainda dentro do prazo, e vice-versa.
    for (cnpj,) in conn.execute("SELECT DISTINCT cnpj FROM contrato_termo").fetchall():
        registro.recalcular(conn, cnpj, hoje)

    instalada = {k for k, s in weso.items() if s == "Instalado"}
    por_placa = {}
    for cnpj, chave, texto, situacao, base in conn.execute(
            "SELECT cnpj, placa_chave, placa_texto, situacao, base FROM contrato_placa"):
        por_placa.setdefault(chave, []).append((cnpj, texto, situacao, base))
        em_uso = chave in instalada
        sustentada = situacao in (motor.ATIVA, motor.EM_AVISO_PREVIO)
        if sustentada and em_uso and (base or "").startswith("nao assinado"):
            achados.append(("EM_USO_FALTA_ASSINAR", cnpj, texto,
                            "nenhum termo assinado trata desta placa"))
        elif sustentada and not em_uso:
            achados.append(("CONTRATADA_NAO_INSTALADA", cnpj, texto,
                            f"situação no contrato: {situacao}; não está na WESO com rastreador instalado"))
        elif not sustentada and em_uso:
            achados.append(("ENCERRADA_EM_USO", cnpj, texto,
                            f"situação no contrato: {situacao}; na WESO o rastreador está Instalado"))

    # Placa em uso que nenhum contrato menciona.
    # ⚠️ SÓ PLACA OU CHASSI RECONHECÍVEL. A WESO tem ~100 códigos de frota
    # (`OBD 2`, `EGP 05`, `TERMO 8396`) que não são placa; acusá-los aqui
    # encheria a tela de ruído que ninguém resolve.
    import re
    for k in sorted(instalada - set(por_placa)):
        if re.fullmatch(r"[A-Z]{3}\d[A-J0-9]\d{2}", k) or len(k) == 17:
            achados.append(("EM_USO_SEM_CONTRATO", None, k,
                            "está na WESO com rastreador instalado e não aparece em termo nenhum"))

    for k, linhas in por_placa.items():
        ativos = [l for l in linhas if l[2] in (motor.ATIVA, motor.EM_AVISO_PREVIO)]
        if len({l[0] for l in ativos}) > 1:
            achados.append(("PLACA_EM_DOIS_CLIENTES", ativos[0][0], ativos[0][1],
                            "também ativa em: " + ", ".join(sorted({l[0] for l in ativos[1:]}))))

    # Substituição pela metade: o par do mesmo termo não foi executado inteiro.
    # Caso real que a originou: Zago 8838 -- entrou a FUX7B86, a BRX9I89 não
    # foi para a WESO e a RVF5G49 não saiu.
    for tid, cnpj, numero in conn.execute(
            "SELECT id, cnpj, numero FROM contrato_termo WHERE tipo LIKE '%SUBSTITUI%' AND assinado=1"):
        sai, entra = [], []
        for acao, texto, ch in conn.execute(
                "SELECT acao, placa_texto, placa_chave FROM contrato_evento WHERE termo_id=?", (tid,)):
            (sai if acao == motor.SAI else entra if acao == motor.ENTRA else []).append((texto, ch))
        pendentes = [f"{t} deveria ter saído e está em uso" for t, c in sai if c in instalada]
        pendentes += [f"{t} deveria ter entrado e não está na WESO" for t, c in entra if c not in instalada]
        if pendentes:
            achados.append(("SUBSTITUICAO_PELA_METADE", cnpj, numero,
                            f"termo {numero}: " + "; ".join(pendentes[:4])))
    return achados


def rodar(conn, hoje=None) -> dict:
    """Roda a auditoria e grava os achados. Devolve o resumo."""
    contratos_tabelas.criar(conn)
    weso, idade, n_veiculos = _weso_do_cache()
    if not weso:
        return {"rodou": False, "motivo": "o cache da WESO não foi encontrado", "idade_h": idade}
    if idade is not None and idade > IDADE_MAXIMA_H:
        return {"rodou": False,
                "motivo": f"o cache da WESO está com {idade:.0f} h (teto {IDADE_MAXIMA_H} h) — "
                          "comparar com dado velho acusaria problema que não existe",
                "idade_h": idade}

    achados = _achar(conn, weso, hoje)
    agora = datetime.now(timezone.utc).isoformat()
    conn.execute("DELETE FROM contrato_achado")
    conn.executemany(
        "INSERT INTO contrato_achado (tipo, cnpj, placa_texto, detalhe, rodada_em) VALUES (?,?,?,?,?)",
        [(t, c, p, d, agora) for t, c, p, d in achados])
    resumo = {}
    for t, _c, _p, _d in achados:
        resumo[t] = resumo.get(t, 0) + 1
    return {"rodou": True, "idade_h": idade,
            "veiculos_weso": n_veiculos, "chaves_weso": len(weso),
            "achados": len(achados), "por_tipo": resumo, "rodada_em": agora}


async def run_auditoria(hoje=None) -> dict:
    def _run():
        with registro._connect() as conn:
            r = rodar(conn, hoje)
            conn.commit()
            return r
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def loop_contratos_auditoria():
    """Laço periódico. **Relê a flag a cada volta** — ligar não roda na hora."""
    while True:
        try:
            if await storage.get_config(FLAG, "false") == "true":
                r = await run_auditoria()
                if r.get("rodou"):
                    logger.info("contratos_auditoria: %s achados %s", r["achados"], r["por_tipo"])
                else:
                    logger.warning("contratos_auditoria: não rodou — %s", r.get("motivo"))
        except Exception:
            logger.exception("contratos_auditoria: falha na rotina periódica")
        await asyncio.sleep(INTERVALO_ROTINA)
