"""Entrada pelo Google no painel do FPSL.

Adaptado do `movizap/google_auth.py`, que esta em producao desde 10/08. Aqui e
MAIS SIMPLES de proposito: o MoviZap tambem usa o Google para ler a caixa de
e-mail e a agenda, com refresh token e escopos de Gmail. **O FPSL so quer
login** -- escopo `openid email profile` e nada mais. Nenhum consentimento novo,
nada guardado alem do vinculo.

AS TRES TRAVAS, e o que cada uma impede
---------------------------------------
1. **Dominio.** So e-mail do dominio configurado passa. Sem isto, qualquer
   conta Google do mundo que chegue ao callback vira candidata -- e este painel
   cria OS e escreve na WESO.

2. **Conta tem que existir.** Quem nao tem linha em `painel_usuarios` e
   RECUSADO, nunca criado. Criar sozinho faria qualquer pessoa do dominio virar
   usuario sem ninguem decidir; cadastrar e ato de gestao e mora na tela de
   Usuarios, que ja e `somente_owner`.

3. **`state` assinado.** Sem ele, um terceiro monta a URL de callback e dispara
   a troca de codigo. O `state` e um JWT de 10 minutos assinado com o
   `painel_jwt_secret`, e valida-lo prova que o retorno veio de um inicio nosso.

⚠️ O `id_token` vem da resposta do endpoint de token do Google, por TLS, com o
nosso client secret na requisicao -- nao e algo que o navegador possa forjar.
Por isso o corpo e lido sem reverificar a assinatura, mas `aud` e o dominio SAO
conferidos: e o que impede um token emitido para outro aplicativo.

🚨 O LOGIN POR SENHA CONTINUA VALENDO. Esta e uma porta A MAIS, nao uma troca.
Quem nao tem e-mail preenchido entra como sempre entrou -- decisao do usuario
em 17/08, para ninguem perder acesso no dia da mudanca.
"""
import base64
import json
import logging
import time
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt

from . import auth
from ..config import settings

log = logging.getLogger(__name__)

AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
TROCAR = "https://oauth2.googleapis.com/token"
VALIDADE_STATE = 600          # 10 min: tempo de fazer login, nao mais
TIPO_STATE = "fpsl_google_state"

# 🚨 SO LOGIN. Nada de Gmail nem Calendar -- o FPSL nao le caixa de ninguem.
# Manter este escopo minimo tambem significa que a tela de consentimento nao
# pede nada assustador, e que isto nao encosta na delegacao de dominio que o
# MoviZap usa para outra coisa.
ESCOPO = "openid email profile"


class GoogleRecusado(Exception):
    """Motivo em portugues, ja pronto para a tela."""


def configurado() -> bool:
    """A tela so mostra o botao se houver credencial.

    Botao que nao funciona e pior que botao ausente: rende chamado.
    """
    return bool(getattr(settings, "google_client_id", "")
                and getattr(settings, "google_client_secret", ""))


def _novo_state() -> str:
    return jwt.encode({"tipo": TIPO_STATE, "exp": int(time.time()) + VALIDADE_STATE},
                      settings.painel_jwt_secret, algorithm=auth.ALGORITHM)


def _state_valido(state: str) -> bool:
    try:
        corpo = jwt.decode(state, settings.painel_jwt_secret,
                           algorithms=[auth.ALGORITHM])
    except JWTError:
        return False
    return corpo.get("tipo") == TIPO_STATE


def url_de_entrada() -> str:
    return AUTORIZAR + "?" + urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect,
        "response_type": "code",
        "scope": ESCOPO,
        "state": _novo_state(),
        # ⚠️ `hd` e DICA ao Google, NAO garantia: ele filtra a tela de escolha,
        # mas quem manipular a URL passa por cima. A trava de verdade e a
        # conferencia do dominio em `entrar()`.
        "hd": settings.google_dominio,
        "prompt": "select_account",
    })


def _corpo_do_id_token(id_token: str) -> dict:
    partes = id_token.split(".")
    if len(partes) != 3:
        raise GoogleRecusado("Resposta do Google em formato inesperado.")
    corpo = partes[1] + "=" * (-len(partes[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(corpo))


async def entrar(codigo: str, state: str) -> dict:
    """Troca o codigo pelo e-mail, confere as travas e devolve o nosso token."""
    from .. import storage

    if not _state_valido(state):
        raise GoogleRecusado("Pedido de entrada expirado. Tente de novo.")

    try:
        async with httpx.AsyncClient(timeout=20) as c:
            resposta = await c.post(TROCAR, data={
                "code": codigo,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect,
                "grant_type": "authorization_code",
            })
    except httpx.HTTPError as e:
        log.warning("Google fora do ar: %s", e)
        raise GoogleRecusado("Nao consegui falar com o Google. Tente de novo.")

    if resposta.status_code != 200:
        # ⚠️ NUNCA registrar o corpo: ele carrega o codigo e, em erro de
        # configuracao, pedacos da credencial.
        log.warning("troca de codigo recusada: HTTP %s", resposta.status_code)
        raise GoogleRecusado("O Google recusou a entrada.")

    dados = _corpo_do_id_token(resposta.json().get("id_token") or "")

    if dados.get("aud") != settings.google_client_id:
        raise GoogleRecusado("Este acesso nao e deste aplicativo.")

    email = (dados.get("email") or "").strip().lower()
    if not dados.get("email_verified") or not email:
        raise GoogleRecusado("O Google nao confirmou este e-mail.")

    dominio = (settings.google_dominio or "").lower()
    if not dominio or not email.endswith("@" + dominio):
        raise GoogleRecusado(f"So contas @{dominio} entram no painel.")

    # 🚨 TRAVA 2: a conta tem que existir. Casa pelo `google_sub` (quem ja
    # entrou) ou pelo e-mail (primeira vez). NUNCA cria.
    usuario = await storage.buscar_usuario_painel_por_google(dados.get("sub"), email)
    if not usuario:
        raise GoogleRecusado(
            f"{email} nao tem conta no painel. Peca ao proprietario para "
            f"cadastrar em Usuarios e preencher este e-mail.")
    if not usuario["ativo"]:
        raise GoogleRecusado("Esta conta esta inativa.")

    # Carimba o `sub` na primeira entrada: e ele, e nao o e-mail, que identifica
    # a conta Google para sempre.
    if dados.get("sub"):
        await storage.gravar_google_sub(usuario["id"], dados["sub"])

    log.info("entrada pelo Google: %s (usuario %s)", email, usuario["id"])
    return {"token": auth.criar_token(usuario["login"]), "usuario": usuario}
