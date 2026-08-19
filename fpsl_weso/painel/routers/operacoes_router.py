"""Rotas da aba OPERAÇÕES (`OPR_1.1`) — a aba única que substitui Cadastro de
Placas e Gerar OS.

🚨 ROUTER PRÓPRIO, SEM IMPORTAR `os_router` NEM `placas_router`. Os dois vão
ser desmontados quando a substituição acontecer (F7) -- o `placas_router`
inteiro, e o `os_router` partido em dois, porque ele hospeda as rotas da tela
de Vínculos, que fica. Qualquer import daqui para lá seria uma dependência num
arquivo com data de validade.

O que este arquivo PODE usar sem medo, porque é infraestrutura e não some:
    fpsl_weso.client / harmonit_client   falam HTTP com os fornecedores
    fpsl_weso.storage                    banco (com tabelas próprias desta aba)
    fpsl_weso.painel.auth                permissão
    fpsl_weso.painel.pdf_extractor       leitura do termo -- a regra NÃO muda

O que ele CLONA, porque carrega regra que mudou:
    operacoes_config.py                  os 11 perfis

Escopo, as 14 regras e as fases: `docs/fpsl/28_Operacoes.md`.

⚠️ PREFIXO PRÓPRIO `/painel/api/operacoes`. Não reaproveita `/painel/api` (do
`os_router`) nem `/painel/api/placas`: quando aqueles saírem, nenhuma rota
desta aba muda de endereço.
"""
import logging

from fastapi import APIRouter, Depends

from ..auth import requer_aba
from .. import operacoes_config as cfg

log = logging.getLogger("fpsl.operacoes")

router = APIRouter(prefix="/painel/api/operacoes", tags=["operacoes"])


@router.get("/perfis")
async def listar_perfis(_=Depends(requer_aba("operacoes"))):
    """Os 11 tipos de operação, com o que cada um implica.

    🚨 A LISTA VEM DAQUI, NUNCA ESCRITA NA TELA. Duplicá-la no navegador
    criaria duas verdades, e a que o operador vê seria a errada -- é a mesma
    família do defeito de 17/08, em que a sidebar lia um contrato de JSON que
    o servidor tinha deixado de cumprir.

    ⚠️ Devolve o que a TELA consome, não o perfil inteiro. `tipo_id`,
    `problema_id` e templates de descrição não têm o que fazer no navegador.
    """
    return {
        "perfis": [
            {
                "id": nome,
                "label": p["label"],
                "sem_termo": bool(p.get("sem_termo")),
                "etapa_placas": p["etapa_placas"],
                "recipiente": p.get("placa_teste_sufixo"),
                "sem_financeira": bool(p.get("sem_financeira")),
                "os_por_placa": p.get("os_por_placa"),
                "agregada": bool(p.get("agregada")),
                "hibrida": bool(p.get("hibrida")),
            }
            for nome, p in cfg.PERFIS.items()
        ]
    }
