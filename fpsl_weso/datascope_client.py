"""Cliente HTTP do DataScope (mydatascope.com), leitura só.

29/09 — primeiro consumidor: a Conferência de Fechamento. Autenticação é uma
chave estática num header (`Authorization: <chave>`, sem prefixo Bearer,
sem renovação) -- bem mais simples que o Harmonit, que tem token com
expiração. Mesmo assim mantém o disjuntor: é uma API de terceiro, e a
rotina roda sozinha de hora em hora sem ninguém olhando.
"""
import logging
import time

import httpx
from fastapi import HTTPException

from .config import settings

log = logging.getLogger("fpsl.datascope")

_client: httpx.AsyncClient | None = None

# ── Disjuntor (mesmo padrão do harmonit_client, mais simples: sem token) ─────
FALHAS_PARA_ABRIR = 3
ESPERA_ABERTO_SEG = 600

_falhas_seguidas = 0
_aberto_ate = 0.0
_ultimo_erro = ""


def estado() -> dict:
    resta = int(_aberto_ate - time.time())
    return {
        "aberto": resta > 0,
        "segundos_restantes": max(resta, 0),
        "falhas_seguidas": _falhas_seguidas,
        "ultimo_erro": _ultimo_erro,
    }


def _abrir(motivo: str) -> None:
    global _aberto_ate, _ultimo_erro
    _aberto_ate = time.time() + ESPERA_ABERTO_SEG
    _ultimo_erro = motivo
    log.error("datascope: DISJUNTOR ABERTO por %ss apos %s falhas seguidas — %s",
              ESPERA_ABERTO_SEG, _falhas_seguidas, motivo)


def _registrar_falha(motivo: str) -> None:
    global _falhas_seguidas
    _falhas_seguidas += 1
    if _falhas_seguidas >= FALHAS_PARA_ABRIR:
        _abrir(motivo)


def _registrar_sucesso() -> None:
    global _falhas_seguidas, _aberto_ate, _ultimo_erro
    if _falhas_seguidas or _aberto_ate:
        log.info("datascope: chamada normalizada, disjuntor fechado")
    _falhas_seguidas = 0
    _aberto_ate = 0.0
    _ultimo_erro = ""


def _checar_disjuntor() -> None:
    resta = _aberto_ate - time.time()
    if resta > 0:
        raise HTTPException(
            status_code=503,
            detail=(f"DataScope indisponível (disjuntor aberto, {int(resta)}s "
                    f"restantes). Último erro: {_ultimo_erro}"))


async def start_datascope_client():
    global _client
    _client = httpx.AsyncClient(base_url=settings.datascope_base_url, timeout=30)


async def stop_datascope_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None


def _headers() -> dict:
    return {"Authorization": settings.datascope_api_key}


async def datascope_post(path: str, dados: dict | None = None) -> dict:
    """ESCREVE no DataScope. 🚨 Primeira escrita deste cliente, 25/11.

    📏 Este arquivo era **GET-only por decisao de projeto**, nao por limite da
    API: o `change_state` foi testado e documentado em
    `docs/fpsl/30_Painel_Financeiro.md` -- funciona nos dois sentidos,
    repetidamente, sem trava de prazo.

    🚨 **A CHAMADA DISPARA OS WEBHOOKS DELES E MANDA PUSH PARA O TECNICO** que
    enviou a resposta. Esta medido e documentado, e e por isso que quem chama
    daqui tem interruptor proprio e modal antes.

    ⚠️ **Formulario, nao JSON:** a API deles le `application/x-www-form-urlencoded`
    (`form_name=...&form_code=...&form_state_id=...`), como esta no doc. Mandar
    JSON daria 400 sem corpo, que e o pior tipo de recusa -- a que nao explica.
    ⚠️ Passa pelo MESMO disjuntor do GET: servico de terceiro que cai nao pode
    ser martelado, e escrita insistente e pior que leitura insistente.
    """
    _checar_disjuntor()
    try:
        r = await _client.post(path, data=dados or {}, headers=_headers())
        r.raise_for_status()
    except Exception as exc:
        _registrar_falha("post %s: %s" % (path, exc))
        raise
    _registrar_sucesso()
    try:
        return r.json()
    except ValueError:
        # ⚠️ Resposta sem JSON nao e erro: o doc mostra 400 com corpo VAZIO.
        # Devolver o texto cru deixa quem chamou dizer o que aconteceu.
        return {"status": r.status_code, "texto": r.text}


async def datascope_get(path: str, params: dict | None = None) -> dict | list:
    """GET com disjuntor. Só leitura -- não existe write neste cliente de
    propósito: a Conferência de Fechamento nunca escreve no DataScope."""
    _checar_disjuntor()
    _t0 = time.perf_counter()
    try:
        r = await _client.get(path, headers=_headers(), params=params)
    except httpx.TimeoutException:
        _registrar_falha("timeout")
        raise HTTPException(status_code=502, detail="DataScope indisponível (timeout)")
    except Exception as exc:
        _registrar_falha(f"{type(exc).__name__}: {exc}")
        raise

    if r.status_code != 200:
        motivo = f"HTTP {r.status_code}: {r.text[:200]}"
        _registrar_falha(motivo)
        raise HTTPException(status_code=502, detail=f"DataScope: {motivo}")

    try:
        corpo = r.json()
    except Exception:
        _registrar_falha("resposta não estruturada")
        raise HTTPException(status_code=502, detail="DataScope: resposta não estruturada")

    _registrar_sucesso()
    return corpo
