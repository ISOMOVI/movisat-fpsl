"""Gestão de contas do painel — exclusiva do owner.

Perfil de acesso é por ABA (ver painel/abas.py): cada conta guarda a lista de
abas que enxerga, e o backend exige a aba no router correspondente. O owner é
intocável por esta rota -- não pode ser desativado, rebaixado nem ter o perfil
alterado, pra não existir caminho que deixe o painel sem dono.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext

from ... import storage
from .. import abas as abas_painel
from ..auth import get_owner_painel

router = APIRouter(prefix="/painel/api/usuarios", tags=["painel-usuarios"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UsuarioCreate(BaseModel):
    login: str
    senha: str
    admin: bool = False
    abas: list[str] = []


class UsuarioUpdate(BaseModel):
    ativo: bool | None = None
    admin: bool | None = None
    senha: str | None = None
    abas: list[str] | None = None


@router.get("/abas")
async def listar_abas(_=Depends(get_owner_painel)):
    """Alimenta o modal de perfil. Fonte única: painel/abas.py."""
    return abas_painel.para_frontend()


@router.get("")
async def listar(_=Depends(get_owner_painel)):
    return await storage.listar_usuarios_painel()


@router.post("")
async def criar(body: UsuarioCreate, _=Depends(get_owner_painel)):
    login = body.login.strip()
    if not login:
        raise HTTPException(400, "Informe um login")
    if await storage.buscar_usuario_painel(login):
        raise HTTPException(400, "Já existe um usuário com esse login")
    if len(body.senha) < 8:
        raise HTTPException(400, "Senha precisa ter ao menos 8 caracteres")
    await storage.criar_usuario_painel(
        login,
        pwd_ctx.hash(body.senha),
        admin=body.admin,
        abas=abas_painel.normalizar(body.abas),
    )
    return {"ok": True}


@router.patch("/{usuario_id}")
async def atualizar(usuario_id: int, body: UsuarioUpdate, owner=Depends(get_owner_painel)):
    alvo = await storage.buscar_usuario_painel_por_id(usuario_id)
    if not alvo:
        raise HTTPException(404, "Usuário não encontrado")
    if alvo["owner"]:
        raise HTTPException(400, "A conta proprietária não pode ser alterada por aqui")
    if body.senha is not None and len(body.senha) < 8:
        raise HTTPException(400, "Senha precisa ter ao menos 8 caracteres")
    senha_hash = pwd_ctx.hash(body.senha) if body.senha else None
    await storage.atualizar_usuario_painel(
        usuario_id,
        ativo=body.ativo,
        admin=body.admin,
        senha_hash=senha_hash,
        abas=abas_painel.normalizar(body.abas) if body.abas is not None else None,
    )
    return {"ok": True}
