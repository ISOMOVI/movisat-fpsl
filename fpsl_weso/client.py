import re
import httpx
from datetime import datetime, timezone
from fastapi import HTTPException
from .config import settings

_client: httpx.AsyncClient | None = None


async def start_client():
    global _client
    # 🚨 60 s, AUTORIZADO PELO USUÁRIO EM 21/08. Eram 30 s, calibrados quando a
    # base levava 2,3 s -- e a documentação da própria WESO registra resposta
    # normal de 30 a 90 s no `UltimaPosicao`. Medido em 18/08: base inteira de
    # 6,0 s a 30,7 s, mediana 23,8 s. O teto cortava o que o fornecedor chama
    # de normal, e foi ele que gerou a OS 16775 sem equipamento.
    #
    # ⚠️ ISTO SÓ VALE ATÉ O NGINX. O `location /` está em 35 s nos dois server
    # blocks: passando disso, quem corta é ele, com uma PÁGINA HTML de 504 que
    # a tela lê como JSON. Subir o nginx exige root e está pendente.
    _client = httpx.AsyncClient(base_url=settings.weso_base_url, timeout=60)


async def stop_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None


def _parse_date(value: str) -> str:
    if isinstance(value, str) and value.startswith("/Date("):
        inner = value[6:value.index(")")]
        ms = int(re.match(r'-?\d+', inner).group())
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    return value


def _normalize_dates(obj):
    if isinstance(obj, dict):
        return {k: _normalize_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_dates(i) for i in obj]
    if isinstance(obj, str):
        return _parse_date(obj)
    return obj


def _parse_response(r: httpx.Response, allow_409: bool = False) -> dict:
    ct = r.headers.get("content-type", "")

    if "text/html" in ct:
        if allow_409 and r.status_code == 409:
            return {"_ja_existe": True}
        raise HTTPException(status_code=502, detail="WESO retornou erro não estruturado")

    body = r.json()

    if "HasError" in body:
        if body["HasError"]:
            raise HTTPException(status_code=502, detail=body.get("Result", "Erro WESO"))
        return _normalize_dates(body)

    status = body.get("Status", "")
    if status == "error":
        err = body.get("Error", {})
        code = err.get("Code", 0)
        if allow_409 and code == 409:
            return {"_ja_existe": True}
        raise HTTPException(status_code=502, detail=err.get("Message", "Erro WESO"))

    return _normalize_dates(body.get("Data", body))


async def weso_get(path: str, params: dict | None = None) -> dict:
    p = {"key": settings.weso_api_key, **(params or {})}
    try:
        r = await _client.get(path, params=p)
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="WESO indisponível (timeout)")
    return _parse_response(r)


async def weso_post(path: str, body: dict, allow_409: bool = False) -> dict:
    p = {"key": settings.weso_api_key}
    try:
        r = await _client.post(path, params=p, json=body)
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="WESO indisponível (timeout)")
    return _parse_response(r, allow_409=allow_409)
