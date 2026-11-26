"""Rotina diaria oculta: separa tecnicos reais de usuarios do sistema.

TRES camadas de exclusao:
1. Quem aparece em ObterUsuarios E em ObterTecnicos (cruzamento por ID).
2. Quem tem o mesmo email de um usuario do painel FPSL (painel_usuarios).
A API do Harmonit nao devolve todos os usuarios em ObterUsuarios, entao a
segunda camada pega quem escapou (ex: owner cadastrado so como tecnico).
3. Quem tem email NOMINAL no dominio da empresa (`e_da_casa`, 25/11) --
   a camada que pega quem escapou das duas primeiras.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone

from fpsl_weso.harmonit_client import harmonit_get
from fpsl_weso import rotinas, storage

log = logging.getLogger("fpsl.sync_tecnicos")

INTERVALO_SEG = 86_400  # 1x/dia

# -- A terceira camada -------------------------------------------------------
# 🔵 Ele, 25/11: *"bruna, vanessa e karla nao sao tecnicos"*, *"segue a regra
# de quem e ou nao tecnico"*.
#
# 📏 MEDIDO ANTES DE ESCREVER, e e o que define a regra: **190 dos 191**
# tecnicos nao excluidos tem email `@movisat.com.br`, porque o Harmonit usa
# `telefone@movisat.com.br` como email sintetico. O DOMINIO nao separa nada.
# O que separa e a parte ANTES do @: numero e o telefone do tecnico de campo;
# nome e gente da casa.
#
# 🚨 Hoje isto separa EXATAMENTE os tres que ele nomeou -- Karla Alves (9617),
# Vanessa Guimaraes (7148) e Bruna Souza (10909) -- e nenhum outro. As duas
# camadas anteriores nao os pegavam: nenhum esta em `ObterUsuarios` nem tem
# email de usuario do painel FPSL.
#
# ⚠️ So no DOMINIO DA EMPRESA. O unico email de fora do dominio e
# `checklistpreenchidosoficial@gmail.com`: alfabetico, mas de terceiro --
# julgar cadastro de fora por um padrao nosso seria inventar regra.
# ⚠️ E "nao sei" nao vira "nao e tecnico": email vazio ou torto devolve False,
# senao a falta de cadastro tiraria alguem do pagamento.
DOMINIO_DA_CASA = "@movisat.com.br"
# Telefone com separador ainda e telefone: digito, espaco, `-`, `+`, `(`, `)`.
_SO_TELEFONE = re.compile(r"^[0-9+()\s-]+$")


def e_da_casa(email: str | None) -> bool:
    """O email e de gente da casa (parte local NOMINAL no dominio da empresa)?

    ⚠️ Caixa e espaco nao enganam: a comparacao e em minusculas e aparada --
    o C maiusculo ja custou tres textos nesta casa.
    """
    limpo = (email or "").strip().lower()
    if not limpo.endswith(DOMINIO_DA_CASA):
        return False
    local = limpo[: -len(DOMINIO_DA_CASA)]
    if not local or "@" in local:
        return False
    return not _SO_TELEFONE.match(local)


async def sync_tecnicos() -> dict:
    """Consulta Harmonit e atualiza a tabela `tecnicos`."""
    tec_resp = await harmonit_get("/Usuario/ObterTecnicos")
    usr_resp = await harmonit_get("/Usuario/ObterUsuarios")

    if not tec_resp or not usr_resp:
        log.warning("sync_tecnicos: resposta vazia do Harmonit, pulando")
        return {"ok": False, "motivo": "resposta vazia"}

    tecnicos = tec_resp if isinstance(tec_resp, list) else []
    usuarios = usr_resp if isinstance(usr_resp, list) else []

    ids_usuarios = {u.get("id") for u in usuarios if u.get("id")}
    emails_painel = await storage.listar_emails_painel()

    total = 0
    excluidos = 0
    da_casa: list[str] = []
    for t in tecnicos:
        tid = t.get("id")
        nome = t.get("nome", "").strip()
        if not tid:
            continue
        email_tec = (t.get("email") or "").strip().lower()
        # 🚨 AS TRES CAMADAS, E O LOG DIZ QUAL PEGOU: no dia em que a regra
        # tirar alguem errado, ele precisa saber por que. "excluido" sem motivo
        # e um numero que nao se audita.
        por_id = tid in ids_usuarios
        por_painel = email_tec in emails_painel
        por_email = e_da_casa(email_tec)
        eh_usuario = por_id or por_painel or por_email
        await storage.salvar_tecnico(tid, nome, excluido=eh_usuario,
                                     email=email_tec or None)
        total += 1
        if eh_usuario:
            excluidos += 1
            if por_id:
                camada = "ObterUsuarios"
            elif por_painel:
                camada = "email de usuario do painel"
            else:
                camada = "email nominal no dominio da casa"
                da_casa.append(f"{tid} {nome}")
            log.info("sync_tecnicos: %s (%s) fora -- %s", nome, tid, camada)

    reais = total - excluidos
    log.info("sync_tecnicos: %d tecnicos, %d excluidos (usuarios), %d reais; "
             "pela 3a camada: %s", total, excluidos, reais,
             ", ".join(da_casa) or "nenhum")
    return {"ok": True, "total": total, "excluidos": excluidos,
            "reais": reais, "da_casa": len(da_casa)}


async def loop_sync_tecnicos():
    """Roda sync_tecnicos() uma vez por dia."""
    log.info("loop_sync_tecnicos: iniciando (intervalo=%ds)", INTERVALO_SEG)
    while True:
        resultado = "ok"
        try:
            r = await sync_tecnicos()
            if isinstance(r, dict):
                resultado = ", ".join(f"{k}={v}" for k, v in r.items())
        except Exception as exc:
            log.exception("loop_sync_tecnicos: erro na rodada")
            resultado = f"ERRO: {exc}"
        await rotinas.marcar("sync_tecnicos", resultado)
        await asyncio.sleep(INTERVALO_SEG)
