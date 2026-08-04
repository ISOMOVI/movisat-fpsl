"""Cliente HTTP do Harmonit, com disjuntor (circuit breaker).

Motivo do disjuntor (achado de 2026-07-28): a API do Harmonit ficou ~14 h fora
com HTTP 400 e "Connect Timeout expired. All pooled connections are in use" —
exaustão do pool MySQL do lado deles. Nosso volume era baixo (~2 req/min), mas
o cliente tinha DOIS padrões que amplificam a insistência num servidor já caído:

  1. `_token = None` em QUALQUER erro. O erro deles não tinha nada a ver com
     token, mas zerávamos assim mesmo — e a chamada seguinte ia bater no
     `/Account/Token`, justamente o endpoint que estava sofrendo. Cada leitura
     de OS virava uma autenticação.

  2. Nenhum recuo. A varredura reinsistia a cada 5 min, indefinidamente.

Agora: token só é descartado em 401 (que é o único erro que REALMENTE indica
token inválido), e falhas de autenticação abrem o disjuntor por alguns minutos.

De quebra, o disjuntor torna a queda VISÍVEL: `estado()` diz se estamos com a
API fora, o que antes ficava indistinguível de "não há OS nova".
"""
import logging
import time

import httpx
from fastapi import HTTPException

from .config import settings

log = logging.getLogger("fpsl.harmonit")

_client: httpx.AsyncClient | None = None
_token: str | None = None

# ── Disjuntor ────────────────────────────────────────────────────────────────
FALHAS_PARA_ABRIR = 3      # falhas seguidas de autenticação antes de abrir
ESPERA_ABERTO_SEG = 600    # 10 min sem tentar nada

_falhas_seguidas = 0
_aberto_ate = 0.0
_ultimo_erro = ""


def estado() -> dict:
    """Estado do disjuntor. Quem chama consegue distinguir 'API fora' de 'sem dado'."""
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
    log.error(
        "harmonit: DISJUNTOR ABERTO por %ss apos %s falhas seguidas de autenticacao — %s",
        ESPERA_ABERTO_SEG, _falhas_seguidas, motivo,
    )


def _registrar_falha_auth(motivo: str) -> None:
    global _falhas_seguidas
    _falhas_seguidas += 1
    if _falhas_seguidas >= FALHAS_PARA_ABRIR:
        _abrir(motivo)


def _registrar_sucesso() -> None:
    global _falhas_seguidas, _aberto_ate, _ultimo_erro
    if _falhas_seguidas or _aberto_ate:
        log.info("harmonit: autenticacao normalizada, disjuntor fechado")
    _falhas_seguidas = 0
    _aberto_ate = 0.0
    _ultimo_erro = ""


def _checar_disjuntor() -> None:
    resta = _aberto_ate - time.time()
    if resta > 0:
        raise HTTPException(
            status_code=503,
            detail=(f"Harmonit indisponível (disjuntor aberto, {int(resta)}s restantes). "
                    f"Último erro: {_ultimo_erro}"),
        )


# ── Ciclo de vida ────────────────────────────────────────────────────────────

async def start_harmonit_client():
    global _client
    _client = httpx.AsyncClient(base_url=settings.harmonit_base_url, timeout=30)


async def stop_harmonit_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def _renovar_token() -> str:
    global _token
    _checar_disjuntor()
    try:
        r = await _client.get(
            "/Account/Token",
            params={
                "clientId": settings.harmonit_client_id,
                "secretId": settings.harmonit_secret_id,
            },
        )
    except httpx.TimeoutException:
        _registrar_falha_auth("timeout no /Account/Token")
        raise HTTPException(status_code=502, detail="Harmonit indisponível (timeout)")

    if r.status_code != 200:
        # o corpo costuma trazer o motivo real — registrar ajuda no chamado com eles
        motivo = f"HTTP {r.status_code}"
        try:
            msg = (r.json() or {}).get("errorMessage")
            if msg:
                motivo = f"HTTP {r.status_code}: {str(msg)[:160]}"
        except Exception:
            pass
        _registrar_falha_auth(motivo)
        raise HTTPException(status_code=502, detail="Harmonit: falha na autenticação")

    body = r.json()
    token = (body.get("data") or {}).get("token")
    if not token:
        _registrar_falha_auth("200 sem token no corpo")
        raise HTTPException(status_code=502, detail="Harmonit: token não retornado")

    _token = token
    _registrar_sucesso()
    return _token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token}"}


def _parse(r: httpx.Response) -> dict:
    try:
        body = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Harmonit: resposta não estruturada")
    if body.get("errorMessage"):
        raise HTTPException(status_code=502, detail=f"Harmonit: {body['errorMessage']}")
    return body.get("data") or body


async def _registrar(path: str, metodo: str, t0: float, ok: bool,
                     http: int | None, erro: str | None) -> None:
    from . import storage  # import tardio: evita ciclo storage <-> client
    await storage.registrar_chamada_harmonit(
        path, metodo, int((time.perf_counter() - t0) * 1000), ok, http, erro)


async def _executar(metodo: str, path: str, *, params=None, body=None) -> dict:
    """Caminho único dos 4 verbos: disjuntor, token, 1 retry em 401, parse.

    O token só é descartado em 401. Antes era descartado em qualquer erro, o que
    transformava falha de dado em tempestade de autenticação.
    """
    global _token
    _checar_disjuntor()

    if not _token:
        await _renovar_token()

    async def _chamar():
        kwargs = {"headers": _headers()}
        if params is not None:
            kwargs["params"] = params
        if body is not None:
            kwargs["json"] = body
        return await getattr(_client, metodo)(path, **kwargs)

    # Auditoria: mede TODA chamada. Ponto unico de propriedade -- os 4 verbos
    # passam por aqui, entao instrumentar em outro lugar seria espalhar. O
    # registro nunca levanta (ver storage.registrar_chamada_harmonit): auditoria
    # que derruba a operacao auditada e pior que auditoria nenhuma.
    _t0 = time.perf_counter()
    _http = None
    try:
        r = await _chamar()
        if r.status_code == 401:
            _token = None          # aqui SIM: 401 é o erro que fala de token
            await _renovar_token()
            r = await _chamar()
        _http = r.status_code
    except httpx.TimeoutException:
        await _registrar(path, metodo, _t0, False, None, "timeout")
        raise HTTPException(status_code=502, detail="Harmonit indisponível (timeout)")
    except Exception as exc:
        await _registrar(path, metodo, _t0, False, None, f"{type(exc).__name__}: {exc}")
        raise

    try:
        dados = _parse(r)
    except Exception as exc:
        await _registrar(path, metodo, _t0, False, _http, f"{type(exc).__name__}: {exc}")
        raise
    await _registrar(path, metodo, _t0, True, _http, None)
    return dados


async def harmonit_get(path: str, params: dict | None = None) -> dict:
    return await _executar("get", path, params=params)


async def harmonit_post(path: str, body: dict) -> dict:
    return await _executar("post", path, body=body)


async def harmonit_put(path: str, body: dict) -> dict:
    """PUT com renovação de token, igual aos demais verbos.

    Existe desde 2026-07-27. Faltava, e as duas rotas de ESCRITA que mais
    importam são PUT: `/Rastreador/Atualizar` e `/SIMCard/Atualizar`. Sem isso,
    todo script de lote abria um httpx próprio pegando `_token` de dentro deste
    módulo -- e perdia a renovação em 401 (que foi o que deu um falso
    diagnóstico de erro de API em 27/07).
    """
    return await _executar("put", path, body=body)


async def harmonit_delete(path: str, params: dict | None = None) -> dict:
    return await _executar("delete", path, params=params)
