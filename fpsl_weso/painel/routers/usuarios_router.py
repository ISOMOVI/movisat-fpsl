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
from .. import telas
from ..auth import get_owner_painel

router = APIRouter(prefix="/painel/api/usuarios", tags=["painel-usuarios"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UsuarioCreate(BaseModel):
    login: str
    senha: str
    admin: bool = False
    abas: list[str] = []
    email: str | None = None


class UsuarioUpdate(BaseModel):
    ativo: bool | None = None
    admin: bool | None = None
    senha: str | None = None
    abas: list[str] | None = None
    # E-mail de vinculo com a conta Google. `None` = nao mexer; "" = limpar.
    email: str | None = None


DOMINIO_PERMITIDO = "movisat.com.br"


def _validar_email(email: str) -> None:
    """🚨 SO O DOMINIO DA CASA. A trava de dominio tambem existe no
    `google_auth.entrar`, e nao e repeticao boba: la ela protege a ENTRADA
    (quem chega), aqui protege o CADASTRO (o que se grava). Sem esta, alguem
    cadastraria `fulano@gmail.com` como vinculo, o campo ficaria la parecendo
    valido, e a pessoa nunca conseguiria entrar -- falha que so aparece no dia
    em que ela tenta.
    """
    e = (email or "").strip().lower()
    if not e.endswith("@" + DOMINIO_PERMITIDO) or e.count("@") != 1 or len(e) < 5:
        raise HTTPException(
            400, f"O e-mail de vínculo precisa ser @{DOMINIO_PERMITIDO}.")


@router.patch("/meu-email")
async def meu_email(body: UsuarioUpdate, owner=Depends(get_owner_painel)):
    """O proprietario define o PROPRIO e-mail de vinculo.

    ⚠️ EXISTE PORQUE O `PATCH /{id}` RECUSA MEXER NO OWNER, de proposito (a
    conta proprietaria nao se altera pela tela de usuarios). Mas o owner e
    justamente quem mais precisa da porta do Google. Esta rota faz UMA coisa
    so -- o e-mail dele -- e nada mais.

    🚨 TROCAR O E-MAIL ZERA O `google_sub`: e assim que a conta passa de mao.
    Sem isso, a conta Google antiga continuaria entrando.
    """
    if body.email:
        _validar_email(body.email)
    await storage.definir_email_painel(owner["id"], body.email)
    return {"ok": True, "email": (body.email or "").strip().lower() or None}


@router.get("/telas")
# ⚠️ `get_owner_painel`, não `requer_aba("config")`: este router inteiro é do
# owner, e a permissão `config` já é só-owner no registro. Duas travas para a
# mesma coisa é uma delas mentindo em algum momento.
async def registro_de_telas(_=Depends(get_owner_painel)):
    """CFG_9.1 — o registro se mostrando, para conferência e auditoria.

    🚨 DEVOLVE O REGISTRO INTEIRO, inclusive as reservadas e os aposentados.
    Mostrar só o que está no ar esconderia justamente o que a tela existe para
    proteger: o código já ocupado, que ninguém pode reaproveitar.
    """
    return {
        "fase_atual": telas.FASE_ATUAL,
        "ativas": len(telas.ativas()),
        "reservadas": len([x for x in telas.TELAS if x["fase"] > telas.FASE_ATUAL]),
        "telas": telas.TELAS,
        "aposentados": sorted(telas.CODIGOS_APOSENTADOS),
        "permissoes_concediveis": sorted(telas.PERMISSOES_CONCEDIVEIS),
        "permissoes_so_owner": sorted(telas.PERMISSOES_SO_OWNER),
    }


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
    if body.email:
        _validar_email(body.email)
    await storage.criar_usuario_painel(
        login,
        pwd_ctx.hash(body.senha),
        admin=body.admin,
        abas=abas_painel.normalizar(body.abas),
    )
    if body.email:
        novo = await storage.buscar_usuario_painel(login)
        await storage.definir_email_painel(novo["id"], body.email)
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
    if body.email:
        _validar_email(body.email)
    await storage.atualizar_usuario_painel(
        usuario_id,
        ativo=body.ativo,
        admin=body.admin,
        senha_hash=senha_hash,
        abas=abas_painel.normalizar(body.abas) if body.abas is not None else None,
    )
    if body.email is not None:
        await storage.definir_email_painel(usuario_id, body.email)
    return {"ok": True}
