from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import abas as abas_painel
from ..auth import validar_login, criar_token, get_usuario_painel

router = APIRouter(prefix="/painel/api", tags=["painel"])


class LoginInput(BaseModel):
    login: str
    senha: str


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
async def login(body: LoginInput):
    usuario = await validar_login(body.login, body.senha)
    if not usuario:
        raise HTTPException(401, "Login ou senha incorretos")
    return {"access_token": criar_token(usuario["login"]), **_perfil(usuario)}


@router.get("/me")
async def me(usuario: dict = Depends(get_usuario_painel)):
    return _perfil(usuario)
