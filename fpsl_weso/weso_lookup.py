"""Busca de veiculo na WESO por placa, tolerante a grafia.

Etapa 2 do docs/fpsl/21_Plano_Higiene_Placas.md.

Problema: `/Veiculos/Consultar?placa=` compara por IGUALDADE EXATA. Em
2026-07-29 havia 110 placas com espaco nas pontas, espaco duplo ou minuscula
na base da WESO (ja normalizadas), e a consulta devolvia LISTA VAZIA em vez de
erro. Falha silenciosa: o sistema concluia "placa nao existe" para veiculo que
existia. Foi assim que a TTX 0H91 do termo 8788 sumiu.

Normalizar a base nao basta: a WESO tambem recebe cadastro por fora do FPSL,
entao grafia divergente volta a aparecer. A leitura precisa ser tolerante por
principio, nao por dependencia de faxina.

Estrategia (2 niveis, do barato para o caro):
  1. consulta direta com a placa FORMATADA (placas.formatar) -- resolve a
     esmagadora maioria e e o caminho rapido;
  2. se vier vazio, baixa a base completa (1 chamada, ~2,3s para 1.962
     registros) e casa por chave normalizada (placas.normalizar).

O nivel 2 so paga o custo quando o nivel 1 falha, que e o caso raro.
"""
import logging

from . import placas
from .client import weso_get

log = logging.getLogger(__name__)


async def buscar_veiculo(placa: str) -> dict | None:
    """Registro do veiculo na WESO, ou None. Nunca levanta por 'nao achou' --
    so propaga falha de comunicacao, que e outra coisa."""
    bruta = str(placa or "").strip()
    if not bruta:
        return None

    formatada = placas.formatar(bruta) or bruta
    r = await weso_get("/Veiculos/Consultar", {"placa": formatada})
    achados = (r.get("veiculos") if isinstance(r, dict) else r) or []
    if achados:
        return achados[0]

    # Nao achou pela grafia limpa: pode ser divergencia na base deles.
    alvo = placas.normalizar(bruta)
    if not alvo:
        return None
    r = await weso_get("/Veiculos/Consultar", {})
    base = (r.get("veiculos") if isinstance(r, dict) else r) or []
    for v in base:
        if placas.normalizar(v.get("placa")) == alvo:
            log.info("weso_lookup: placa %r so encontrada na base completa "
                     "(gravada na WESO como %r) -- grafia divergente",
                     bruta, v.get("placa"))
            return v
    return None


async def buscar_veiculo_id(placa: str) -> int | None:
    v = await buscar_veiculo(placa)
    return v.get("id") if v else None
