"""Cadastro de cliente no Harmonit a partir do termo (P1).

Pendencia aberta desde julho: o extrator ja le cliente, CNPJ e responsavel do
termo, mas nada gravava. O `/Cliente/CadastrarOuAtualizar` foi validado em
julho e nunca foi chamado pelo painel.

O que travava: **`codigoIBGE` e exigido e nao vem no termo**. Resolvido por CEP
(fpsl_weso/cep.py, ViaCEP). O mesmo lookup entrega o FUSO, que e a segunda
decisao do usuario de 29/07 -- cliente fora de UTC-3 ve horario de evento
diferente do nosso, e isso tem que aparecer no cadastro, nao ser descoberto
depois.

🚨 Read-after-write obrigatorio. O Harmonit mente no codigo de retorno
(10_Inconsistencias): `ativar: false` devolve 200 com errorMessage null e nao
faz nada. Aqui, depois de gravar, o cliente e RELIDO por CNPJ e o `ok` da
resposta reflete a releitura, nao o HTTP.
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import requer_aba
from ... import cep as consulta_cep
from ...harmonit_client import harmonit_get, harmonit_post

log = logging.getLogger(__name__)
router = APIRouter(prefix="/painel/api/clientes", tags=["clientes-cadastro"])

# 1 = Fisica, 2 = Juridica no EnumTipoPessoa do Harmonit. Derivado do documento
# em vez de pedido ao usuario: 11 digitos e CPF, 14 e CNPJ.
PESSOA_FISICA = 1
PESSOA_JURIDICA = 2
SITUACAO_ATIVO = 1


def _so_digitos(v) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(v or ""))


class PreviaInput(BaseModel):
    cnpjcpf: str
    cep: str | None = None


class CriarInput(BaseModel):
    cnpjcpf: str
    nome: str
    cep: str
    numero: str = "S/N"
    nome_fantasia: str | None = None
    complemento: str | None = None
    email: str | None = None
    # Preenchido a mao quando o CEP nao resolve o IBGE (ex.: Fernando de Noronha)
    codigo_ibge: str | None = None


async def _buscar_no_harmonit(doc: str) -> dict | None:
    """Cliente por CNPJ/CPF, ou None. Nao levanta se nao achar."""
    try:
        r = await harmonit_get("/ObterClientePorCpfCnpj", params={"CpfCnpj": doc})
    except HTTPException as exc:
        # 502 aqui pode ser "nao encontrado" travestido -- o Harmonit devolve
        # erro de negocio como falha HTTP. Nao da para distinguir sem o texto.
        log.info("clientes: busca de %s devolveu %s", doc, exc.detail)
        return None
    # O Harmonit responde em DUAS formas (conferido em 2026-07-29):
    #   existe     -> list  [{"id": 998063, "nome": "...", ...}]
    #   nao existe  -> dict  {"errorMessage": null, "message": null, "data": []}
    # O dict de "nao encontrado" e truthy, entao tratar `r` como verdade dizia
    # que TODO documento ja existia -- inclusive um CPF inventado. O que decide
    # e a lista: `r` quando vem lista, `r["data"]` quando vem envelope.
    if isinstance(r, list):
        itens = r
    elif isinstance(r, dict):
        itens = r.get("data") or []
        if not isinstance(itens, list):
            itens = [itens] if itens else []
    else:
        itens = []
    return itens[0] if itens else None


@router.post("/previa")
async def previa(body: PreviaInput, _=Depends(requer_aba("gerar_os"))):
    """O que se sabe ANTES de gravar: o cliente ja existe? o CEP resolve o
    IBGE? o fuso e o nosso? Serve para a tela decidir se cadastra ou segue."""
    doc = _so_digitos(body.cnpjcpf)
    if len(doc) not in (11, 14):
        raise HTTPException(400, f"Documento com {len(doc)} caracteres — "
                                 f"esperado 11 (CPF) ou 14 (CNPJ).")

    ja = await _buscar_no_harmonit(doc)
    endereco = await consulta_cep.consultar(body.cep) if body.cep else None

    fora = {
        "documento": doc,
        "tipo_pessoa": "fisica" if len(doc) == 11 else "juridica",
        "ja_existe": bool(ja),
        "cliente_harmonit": ja,
        "endereco": endereco,
        "pronto_para_cadastrar": bool(endereco and endereco.get("codigo_ibge")),
    }
    if endereco and not endereco.get("codigo_ibge"):
        fora["falta"] = ("O CEP resolveu o endereco mas nao o codigo IBGE, que o "
                         "Harmonit exige. Informe `codigo_ibge` manualmente.")
    if not endereco and body.cep:
        fora["falta"] = "CEP nao resolveu em nenhuma das fontes."
    if endereco and endereco["fuso"]["difere_do_nosso"]:
        fora["aviso_fuso"] = endereco["fuso"]["aviso"]
    return fora


@router.post("/criar")
async def criar(body: CriarInput, _=Depends(requer_aba("gerar_os"))):
    doc = _so_digitos(body.cnpjcpf)
    if len(doc) not in (11, 14):
        raise HTTPException(400, f"Documento com {len(doc)} caracteres — "
                                 f"esperado 11 (CPF) ou 14 (CNPJ).")

    ja = await _buscar_no_harmonit(doc)
    if ja:
        return {"ok": True, "acao": "ja_existe", "cliente": ja,
                "id": ja.get("id"), "verificado_relendo": True}

    endereco = await consulta_cep.consultar(body.cep)
    if not endereco:
        raise HTTPException(422, f"CEP {body.cep} nao resolveu em nenhuma fonte.")
    ibge = body.codigo_ibge or endereco.get("codigo_ibge")
    if not ibge:
        raise HTTPException(422,
            "O Harmonit exige codigoIBGE e o CEP nao o resolveu. Informe "
            "`codigo_ibge` manualmente (consulte a cidade na tabela do IBGE).")

    payload = {
        "id": 0,
        "cnpj_cpf": doc,
        "pessoa": PESSOA_FISICA if len(doc) == 11 else PESSOA_JURIDICA,
        "nome": body.nome.strip(),
        "nomeFantasia": (body.nome_fantasia or body.nome).strip(),
        "situacaoClienteId": SITUACAO_ATIVO,
        "enderecoPrincipal": {
            "cep": endereco["cep"],
            "codigoIBGE": str(ibge),
            "endereco": endereco["endereco"],
            "numero": body.numero or "S/N",
            "bairro": endereco["bairro"],
            "complemento": body.complemento or "",
            "cidade": endereco["cidade"],
            "uf": endereco["uf"],
        },
    }
    if body.email:
        payload["contatoPrincipal"] = {"email": body.email.strip()}

    try:
        resposta = await harmonit_post("/Cliente/CadastrarOuAtualizar", payload)
    except HTTPException as exc:
        # Pode ter gravado mesmo com erro -- confere antes de desistir.
        conferido = await _buscar_no_harmonit(doc)
        if conferido:
            log.warning("clientes: %s deu erro (%s) MAS o cliente existe — "
                        "gravou apesar do retorno", doc, exc.detail)
            return {"ok": True, "acao": "criado_apesar_do_erro",
                    "cliente": conferido, "id": conferido.get("id"),
                    "verificado_relendo": True, "erro_original": str(exc.detail)[:200]}
        raise

    conferido = await _buscar_no_harmonit(doc)
    return {
        "ok": bool(conferido),
        "acao": "criado" if conferido else "resposta_ok_sem_confirmacao",
        "cliente": conferido,
        "id": (conferido or {}).get("id"),
        "verificado_relendo": bool(conferido),
        "fuso": endereco["fuso"],
        "codigo_ibge_usado": str(ibge),
        "resposta_bruta": resposta,
    }
