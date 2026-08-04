"""Consulta de CEP: cidade, UF, codigo IBGE e FUSO HORARIO.

Existe por dois motivos, os dois de 2026-07-29:

1. **codigoIBGE.** O `/Cliente/CadastrarOuAtualizar` do Harmonit exige o codigo
   IBGE do municipio, e ele NAO vem no termo. Sem resolver por CEP, o cadastro
   de cliente (P1) nao sai do lugar.

2. **Fuso horario.** Decisao do usuario: "atencao na informacao do CEP para
   fuso horario, nosso fuso e de Sao Paulo, se tiver diferente, os dados do
   cliente tbm mudam no painel dele". Cliente no Acre ve horario de evento com
   2h de diferenca do nosso; sem aviso, isso e lido como erro de dado.

FONTES, nesta ordem:
  1. **ViaCEP** -- e a que traz o campo `ibge`. Verificado em 29/07:
     01310-100 -> 3550308, 69900-064 -> 1200401.
  2. **BrasilAPI v2** -- reserva. NAO devolve IBGE (conferido no mesmo dia: a
     resposta tem cep/state/city/neighborhood/street e nada mais), entao serve
     so para nao ficar sem endereco se a ViaCEP cair.

Nenhuma das duas exige chave. `consultar` NUNCA levanta: CEP invalido ou as duas
fontes fora devolvem None, e quem chama decide.
"""
import logging
import re

import httpx

log = logging.getLogger(__name__)

_VIACEP = "https://viacep.com.br/ws/{cep}/json/"
_BRASILAPI = "https://brasilapi.com.br/api/cep/v2/{cep}"
_UA = "FPSL-Movisat/1.0 (contato: iago@movisat.com.br)"
TIMEOUT = 8

UF_REFERENCIA = "SP"
FUSO_REFERENCIA = -3

# Fuso por UF. Aproximacao POR ESTADO, que e o que o CEP entrega de forma
# confiavel; excecoes intra-estaduais ficam em RESSALVAS_FUSO.
_FUSO_POR_UF = {
    "AC": -5,
    "AM": -4, "RO": -4, "RR": -4, "MT": -4, "MS": -4,
}
RESSALVAS_FUSO = {
    "AM": "o sudoeste do estado (Tabatinga, Eirunepe) fica em UTC-5, nao -4",
    "PE": "Fernando de Noronha e UTC-2, nao -3 (e a ViaCEP nem resolve o CEP dela)",
}


def limpar(cep) -> str:
    return re.sub(r"[^0-9]", "", str(cep or ""))


def fuso_da_uf(uf: str) -> int:
    return _FUSO_POR_UF.get(str(uf or "").upper().strip(), FUSO_REFERENCIA)


def diagnostico_fuso(uf: str) -> dict:
    uf = str(uf or "").upper().strip()
    fuso = fuso_da_uf(uf)
    dif = fuso - FUSO_REFERENCIA
    fora = {
        "uf": uf,
        "fuso_utc": fuso,
        "fuso_referencia_utc": FUSO_REFERENCIA,
        "difere_do_nosso": dif != 0,
        "diferenca_horas": dif,
    }
    if dif != 0:
        fora["aviso"] = (
            f"Cliente em {uf} (UTC{fuso:+d}), {abs(dif)}h "
            f"{'atras' if dif < 0 else 'a frente'} de Sao Paulo. O horario dos "
            f"eventos no painel dele nao bate com o nosso -- confira antes de "
            f"tratar divergencia de horario como erro de dado."
        )
    if uf in RESSALVAS_FUSO:
        fora["ressalva"] = RESSALVAS_FUSO[uf]
    return fora


async def _viacep(client, limpo: str) -> dict | None:
    r = await client.get(_VIACEP.format(cep=limpo), headers={"User-Agent": _UA})
    if r.status_code != 200:
        return None
    d = r.json()
    if d.get("erro"):          # ViaCEP sinaliza CEP inexistente no CORPO, com 200
        return None
    return {
        "endereco": d.get("logradouro") or "",
        "bairro": d.get("bairro") or "",
        "cidade": d.get("localidade") or "",
        "uf": d.get("uf") or "",
        "codigo_ibge": str(d.get("ibge") or ""),
        "fonte": "viacep",
        "bruto": d,
    }


async def _brasilapi(client, limpo: str) -> dict | None:
    r = await client.get(_BRASILAPI.format(cep=limpo), headers={"User-Agent": _UA})
    if r.status_code != 200:
        return None
    d = r.json()
    return {
        "endereco": d.get("street") or "",
        "bairro": d.get("neighborhood") or "",
        "cidade": d.get("city") or "",
        "uf": d.get("state") or "",
        "codigo_ibge": "",     # esta fonte nao tem IBGE -- ver docstring
        "fonte": "brasilapi",
        "bruto": d,
    }


async def consultar(cep) -> dict | None:
    """{cep, endereco, bairro, cidade, uf, codigo_ibge, fuso, fonte} ou None."""
    limpo = limpar(cep)
    if len(limpo) != 8:
        log.info("cep: %r nao tem 8 digitos", cep)
        return None

    achado = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        for fonte in (_viacep, _brasilapi):
            try:
                achado = await fonte(c, limpo)
                if achado:
                    break
            except Exception as exc:
                log.warning("cep %s: %s falhou (%s)", limpo, fonte.__name__, exc)
    if not achado:
        return None

    achado["cep"] = limpo
    achado["fuso"] = diagnostico_fuso(achado["uf"])
    if not achado["codigo_ibge"]:
        log.warning("cep %s: resolveu por %s, mas SEM codigo IBGE -- o cadastro "
                    "de cliente no Harmonit vai precisar dele preenchido a mao",
                    limpo, achado["fonte"])
    return achado
