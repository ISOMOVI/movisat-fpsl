import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .. import abas as abas_painel
from ... import ratelimit
from ..auth import validar_login, criar_token, get_usuario_painel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/painel/api", tags=["painel"])


class LoginInput(BaseModel):
    # Teto de tamanho: sem ele, um POST de 10 MB no campo senha vira trabalho
    # de bcrypt em cima de lixo. O bcrypt ja ignora alem de 72 bytes.
    login: str = Field(min_length=1, max_length=64)
    senha: str = Field(min_length=1, max_length=256)


def _perfil(usuario: dict) -> dict:
    """Payload que a sidebar usa pra se montar. `abas` já vem resolvida --
    o frontend não decide permissão, só desenha o que veio."""
    return {
        "login": usuario["login"],
        "admin": usuario["admin"],
        "owner": usuario.get("owner", False),
        "abas": abas_painel.do_usuario(usuario),
    }


@router.post("/login")
async def login(body: LoginInput, request: Request):
    """🚨 Rota mais atacada de qualquer painel.

    Ate 2026-08-05 aceitava tentativas ilimitadas -- a auditoria dos quatro
    paineis mostrou que so o MoviServer tinha trava. O limite roda ANTES do
    bcrypt: se rodasse depois, a propria verificacao (250ms) seria o custo do
    ataque, e sairia de graca para o atacante.
    """
    chave = ratelimit.chave_de(ratelimit.ip_do_cliente(request), body.login)

    resta = ratelimit.bloqueado_por(chave)
    if resta:
        log.warning("login bloqueado por tentativas: %s (%ss restantes)", chave, resta)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Muitas tentativas. Tente de novo em {resta // 60 + 1} min.",
        )

    usuario = await validar_login(body.login, body.senha)
    if not usuario:
        ratelimit.registrar_falha(chave)
        # mensagem unica: nao entrega se o erro foi o login ou a senha
        raise HTTPException(401, "Login ou senha incorretos")

    ratelimit.registrar_sucesso(chave)
    return {"access_token": criar_token(usuario["login"]), **_perfil(usuario)}


@router.get("/me")
async def me(usuario: dict = Depends(get_usuario_painel)):
    return _perfil(usuario)
