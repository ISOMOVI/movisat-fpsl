"""Tela `FIN_1.1` — Conferência de Fechamento. Lista o que a rotina em
`fpsl_weso/services/conferencia_fechamento.py` gravou, e liga/desliga essa
rotina.

🔵 O INTERRUPTOR MORA AQUI, NA TELA DA PRÓPRIA ROTINA, por decisão dele em
01/10: *"coloque interruptor nesse recurso, na propria tela dele"*. Antes disto
a flag só se ligava por SQL -- `config.html` não tem interruptor nenhum desde
17/08, e uma rotina que ninguém consegue ligar sem banco é uma rotina que não
existe para quem usa o painel.

⚠️ É o OPOSTO da convenção do MoviZap (`CFG_7.1`: interruptor em
`/config` › Geral). São projetos diferentes e a decisão é desta obra -- não
"corrigir" para o padrão do outro.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth import requer_aba
from ...services.conferencia_fechamento import INTERVALO_ROTINA, run_conferencia
from ... import storage

router = APIRouter(prefix="/painel/api/conferencia-fechamento", tags=["painel-financeiro"])

FLAG = "conferencia_fechamento_ativa"


class InterruptorInput(BaseModel):
    ativa: bool


@router.get("")
async def listar(limit: int = Query(300, le=1000),
                 _=Depends(requer_aba("financeiro"))):
    return {"itens": await storage.listar_conferencia_fechamento(limit)}


@router.get("/interruptor")
async def ler_interruptor(_=Depends(requer_aba("financeiro"))):
    """Estado da rotina. Quem tem a aba LÊ; mudar é só do dono (ver o PUT)."""
    return {"ativa": await storage.get_config(FLAG, "false") == "true",
            "intervalo_min": INTERVALO_ROTINA // 60}


@router.put("/interruptor")
async def mudar_interruptor(corpo: InterruptorInput,
                            _=Depends(requer_aba("config"))):
    """Liga/desliga a rotina periódica.

    🚨 A TRANCA É `requer_aba("config")`, NÃO `get_owner_painel`. As duas barram
    quem não é dono -- `config` está em `PERMISSOES_SO_OWNER`, e
    `abas.pode_acessar` devolve `False` para permissão não concedível. A
    diferença é o RECADO: `get_owner_painel` responde "só o proprietário do
    painel gerencia usuários", que é mentira para quem tentou ligar uma rotina.
    Tranca certa, recado certo.

    ⚠️ Ligar NÃO faz a rotina rodar na hora: o laço relê esta flag a cada
    `INTERVALO_ROTINA`. Para rodar já existe o "Rodar agora". A tela diz isso --
    prometer efeito imediato aqui seria tela que mente.
    """
    await storage.set_config(FLAG, "true" if corpo.ativa else "false")
    # A prova é RELER, nunca o que acabamos de mandar gravar.
    return {"ativa": await storage.get_config(FLAG, "false") == "true",
            "intervalo_min": INTERVALO_ROTINA // 60}


@router.post("/rodar-agora")
async def rodar_agora(_=Depends(requer_aba("financeiro"))):
    """Roda a conferência na hora, sem esperar o próximo ciclo de 1h --
    para validar a rotina sem esperar. Independe do interruptor: é ação de
    gente, não o laço."""
    return await run_conferencia()
