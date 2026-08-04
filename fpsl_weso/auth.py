import hmac
from fastapi import Header, HTTPException
from .config import settings


async def verificar_chave(x_fpsl_key: str = Header(...)) -> None:
    # hmac.compare_digest -- comparação constant-time, evita timing attack pra
    # adivinhar a chave byte a byte (mesmo padrão já usado no MoviChat).
    # Achado na auditoria de segurança de 2026-07-15.
    if not settings.fpsl_secret_key or not hmac.compare_digest(x_fpsl_key, settings.fpsl_secret_key):
        raise HTTPException(status_code=401, detail="Chave de acesso inválida")
