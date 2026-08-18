import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .. import abas as abas_painel
from .. import telas as telas_registro
from ... import ratelimit
from ..auth import validar_login, criar_token, get_usuario_painel
from .. import google_auth
from fastapi.responses import RedirectResponse
from urllib.parse import quote

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
        # Mapa rota -> {codigo, titulo} de TODA tela ativa, inclusive as que
        # ficam fora do menu (o Historico de Cadastros). E o que a barra de
        # status usa para saber em que tela a pessoa esta, sem uma chamada por
        # pagina. Nao e segredo: e o catalogo, nao o conteudo -- a CFG_9.1
        # continua so-owner porque mostra fase, permissao e aposentados.
        "codigos": {
            t["rota"]: {"codigo": t["codigo"], "titulo": t["titulo"]}
            for t in telas_registro.ativas()
            # `permissao is None` sao as telas de demandas, publicas por token e
            # fora do painel: rota com `{token}` nunca casa com um caminho real
            # e elas nem carregam a barra. Ficariam so como ruido no payload.
            if t["permissao"] is not None
        },
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


# ── entrada pelo Google (17/08) ─────────────────────────────────────────────
# 🚨 PORTA A MAIS, NAO TROCA. O login por senha acima continua valendo para
# todo mundo -- decisao do usuario, para ninguem perder acesso no dia da
# mudanca. Quem nao tem `email` preenchido simplesmente nao usa esta porta.


@router.get("/auth/google/disponivel")
def google_disponivel():
    """A tela pergunta antes de desenhar o botao.

    Botao que nao funciona e pior que botao ausente: rende chamado. Sem
    credencial no .env, isto devolve False e o login fica so com senha.
    """
    return {"disponivel": google_auth.configurado()}


@router.get("/auth/google/inicio")
def google_inicio():
    if not google_auth.configurado():
        raise HTTPException(503, "Entrada pelo Google nao esta configurada.")
    return RedirectResponse(google_auth.url_de_entrada(), status_code=302)


@router.get("/auth/google/callback")
async def google_callback(code: str = "", state: str = "", error: str = ""):
    """Volta do Google e entrega a sessao a tela.

    🚨 O TOKEN VAI NO FRAGMENTO DA URL (`#t=`), NAO NA QUERY. Fragmento nao e
    enviado ao servidor nem entra no log de acesso do nginx; a tela le e limpa
    a barra de enderecos em seguida. Na query, o token de sessao de todo mundo
    ficaria gravado em disco no `access_log`.
    """
    destino = "/painel"
    if error or not code:
        return RedirectResponse(f"{destino}#erro=Entrada+cancelada", status_code=302)
    try:
        r = await google_auth.entrar(code, state)
    except google_auth.GoogleRecusado as e:
        return RedirectResponse(f"{destino}#erro={quote(str(e))}", status_code=302)
    return RedirectResponse(f"{destino}#t={r['token']}", status_code=302)
