"""Tela de placas — conferir quais existem na WESO e criar as que faltam.

Decisao do usuario (2026-07-29): entre validar os vinculos e gerar as OS entra
uma etapa de placas. Sem ela, a geracao segue com placa que a WESO nao conhece
e a OS nasce apontando para nada.

A conferencia sai do cache local (/home/claude/weso_cache, 04:15 diario): 23
placas em ~1ms contra 15 a 90s indo a WESO. Placa cadastrada depois da ultima
atualizacao nao esta no cache -- por isso o que o cache nao acha e reconferido
AO VIVO antes de ser declarado ausente. Cache errado aqui faria o painel
oferecer criar uma placa que ja existe.
"""
import logging
import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import requer_aba
from ...client import weso_post
from ...weso_lookup import buscar_veiculo
from ... import placas as regra_placa

log = logging.getLogger(__name__)
router = APIRouter(prefix="/painel/api/placas", tags=["placas"])

CACHE_DIR = "/home/claude/weso_cache"


def _cache():
    try:
        if CACHE_DIR not in sys.path:
            sys.path.insert(0, CACHE_DIR)
        import cache  # noqa: PLC0415
        return cache
    except Exception as exc:
        log.warning("placas: cache indisponivel (%s)", exc)
        return None


class StatusInput(BaseModel):
    placas: list[str]


class CriarInput(BaseModel):
    placa: str
    cnpjcpf_cliente: str
    serial_rastreador: str
    descricao: str | None = None
    apelido: str | None = None


@router.post("/status")
async def status_placas(body: StatusInput, _=Depends(requer_aba("gerar_os"))):
    """Situacao de cada placa: existe na WESO? com qual equipamento?

    Nunca declara ausencia so pelo cache — o que falta la e conferido ao vivo.
    """
    c = _cache()
    fora, faltando = [], []

    for p in body.placas:
        bruta = str(p or "").strip()
        if not bruta:
            continue
        item = {
            "placa": bruta,
            "placa_formatada": regra_placa.formatar(bruta) or bruta,
            "convencional": regra_placa.eh_convencional(bruta),
            "existe": False, "veiculo_id": None, "serial": None,
            "modelo": None, "situacao": None, "origem": None,
        }
        if c:
            try:
                v = c.veiculo_por_placa(bruta)
                if v:
                    r = c.rastreador_por_id(v["rastreador_id"]) if v.get("rastreador_id") else None
                    item.update(existe=True, veiculo_id=v["id"], origem="cache",
                                serial=(r or {}).get("numero_serie"),
                                modelo=(r or {}).get("modelo"),
                                situacao=(r or {}).get("situacao"))
            except Exception as exc:
                log.warning("placas: leitura do cache falhou (%s)", exc)
        if not item["existe"]:
            faltando.append(item)
        fora.append(item)

    # O cache nao achou: pode ser placa criada depois da ultima atualizacao.
    # Confirma ao vivo antes de dizer que nao existe.
    for item in faltando:
        try:
            v = await buscar_veiculo(item["placa"])
            if v:
                item.update(existe=True, veiculo_id=v.get("id"), origem="weso_ao_vivo")
        except Exception as exc:
            item["erro_consulta"] = str(exc)[:120]
            log.warning("placas: consulta ao vivo de %r falhou: %s", item["placa"], exc)

    ausentes = [i for i in fora if not i["existe"]]
    return {
        "total": len(fora),
        "existentes": len(fora) - len(ausentes),
        "ausentes": len(ausentes),
        "cache_idade_horas": c.idade_horas() if c else None,
        "placas": fora,
    }


@router.post("/criar")
async def criar_placa(body: CriarInput, _=Depends(requer_aba("gerar_os"))):
    """Cria o veiculo na WESO.

    O serial do rastreador e resolvido pelo CACHE. O endpoint antigo
    (/weso/veiculos) resolvia por uma tabela local com 1 linha, o que o
    tornava inutilizavel na pratica.
    """
    placa_fmt = regra_placa.formatar(body.placa) or body.placa
    serial = str(body.serial_rastreador or "").strip()
    if not serial:
        raise HTTPException(400, "Informe o serial do rastreador.")

    c = _cache()
    if not c:
        raise HTTPException(503, "Cache da WESO indisponivel — nao da para "
                                 "resolver o serial do rastreador agora.")
    r = c.rastreador_por_serial(serial)
    if not r:
        raise HTTPException(404, f"Rastreador '{serial}' nao encontrado na WESO. "
                                 f"Confira o serial ou aguarde a atualizacao do cache "
                                 f"(idade atual: {c.idade_horas()}h).")
    if r.get("situacao") and str(r["situacao"]).lower() not in ("estoque", "disponivel", "disponível"):
        log.info("placas: rastreador %s esta como %r — criando assim mesmo",
                 serial, r["situacao"])

    payload = {"equipamento": {
        "placa": placa_fmt,
        "cliente": {"cnpjcpf": body.cnpjcpf_cliente},
        "rastreador": {"id": r["id"]},
        **({} if not body.descricao else {"descricao": body.descricao}),
        **({} if not body.apelido else {"observacoes": body.apelido}),
    }}
    res = await weso_post("/Veiculos/Cadastro", payload, allow_409=True)

    # A WESO mente no codigo de retorno nos DOIS sentidos (10_Inconsistencias
    # B8/B10/B11): 500 pode ter gravado, 200 pode nao ter feito nada. A unica
    # prova e reler o estado.
    conferido = await buscar_veiculo(placa_fmt)
    return {
        "ok": bool(conferido),
        "acao": "ja_existe" if res.get("_ja_existe") else "criado",
        "placa": placa_fmt,
        "veiculo_id": (conferido or {}).get("id"),
        "rastreador_id": r["id"],
        "serial": r.get("numero_serie"),
        "verificado_relendo": bool(conferido),
        "resposta_bruta": res,
    }
