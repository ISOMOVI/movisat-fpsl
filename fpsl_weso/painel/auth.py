"""Autenticação do painel de geração de OS — login básico por enquanto.

Usuários ficam na tabela `painel_usuarios` (SQLite, mesmo banco do FPSL).
Login/senha do .env (PAINEL_ADMIN_LOGIN/SENHA) só serve de seed inicial --
na primeira subida, se a tabela estiver vazia, cria esse usuário como admin.
Daí em diante, gerenciamento é todo pela tela de Usuários do painel.

Quando o Google OAuth entrar em produção (~20/07), troca por validação de
token Google + checagem de domínio (só e-mails @movisat.com.br).
"""
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext

from . import abas as abas_painel
from .. import storage
from ..config import settings

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8
bearer = HTTPBearer()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed_admin_inicial() -> None:
    if await storage.contar_usuarios_painel() > 0:
        return
    if not settings.painel_admin_senha:
        return
    # primeira subida em banco vazio: essa conta é o OWNER do painel.
    await storage.criar_usuario_painel(
        settings.painel_admin_login,
        pwd_ctx.hash(settings.painel_admin_senha),
        admin=True,
        owner=True,
    )


def criar_token(login: str) -> str:
    agora = datetime.utcnow()
    payload = {
        "sub": login,
        "tipo": "painel_os",
        # `iat` existe para a barra de status medir ha quanto tempo a sessao
        # comecou. Token antigo, sem o campo, so mostra "--" ate a pessoa
        # entrar de novo -- nada quebra e nao ha migracao.
        "iat": agora,
        "exp": agora + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.painel_jwt_secret, algorithm=ALGORITHM)


async def validar_login(login: str, senha: str) -> dict | None:
    usuario = await storage.buscar_usuario_painel(login)
    if not usuario or not usuario["ativo"]:
        return None
    if not pwd_ctx.verify(senha, usuario["senha_hash"]):
        return None
    return usuario


async def get_usuario_painel(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, settings.painel_jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida ou expirada")
    if payload.get("tipo") != "painel_os":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    usuario = await storage.buscar_usuario_painel(payload["sub"])
    if not usuario or not usuario["ativo"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inativo")
    return usuario


async def get_admin_painel(usuario: dict = Depends(get_usuario_painel)) -> dict:
    if not usuario["admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requer administrador")
    return usuario


async def get_owner_painel(usuario: dict = Depends(get_usuario_painel)) -> dict:
    """Gestão de contas é exclusiva do owner -- só ele cria e edita usuários."""
    if not usuario.get("owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Só o proprietário do painel gerencia usuários",
        )
    return usuario


def requer_aba(*aba_ids: str):
    """Dependency que exige a aba no perfil do usuário. Owner passa em tudo.

    É o que torna a permissão real: antes, esconder o link na sidebar era o
    único controle das abas operacionais, e a API respondia a qualquer um.

    Aceita mais de uma aba porque alguns lookups são compartilhados -- `/perfis`
    e as buscas de produto/serviço servem tanto a Gerar OS quanto a Vínculos.
    Basta ter UMA das abas listadas.
    """
    async def _checar(usuario: dict = Depends(get_usuario_painel)) -> dict:
        if not any(abas_painel.pode_acessar(usuario, a) for a in aba_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Seu perfil não tem acesso a esta aba",
            )
        return usuario
    return _checar
