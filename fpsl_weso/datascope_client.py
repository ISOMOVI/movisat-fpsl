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
