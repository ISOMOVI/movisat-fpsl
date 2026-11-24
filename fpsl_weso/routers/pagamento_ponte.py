# -*- coding: utf-8 -*-
"""A ponte de **Serviço dos Técnicos** — 🔵 a aba 2 do Financeiro, 18/11.

🔵 *"É possível fazer tudo no FPSL com as rotas e etc, mas o painel é aqui."*
Os dados e os gestos moram neste lado; o MoviZap desenha e chama.

🚨 **MESMA CHAVE, MESMA GUARDA DA OUTRA PONTE.** `X-Ponte-Key` é
servidor-a-servidor: não há cookie, não há `requer_aba`. Quem alcança estas
rotas é o MoviZap, e a permissão de quem opera é conferida **lá**, na aba.

⚠️ **NENHUMA ROTA AQUI FALA COM O HARMONIT.** Tudo sai do cache (`os_historico`,
633 OS) e das tabelas da frente. O ERP esgota o pool todo dia, e uma tela de
fechamento que o consultasse por card entraria na fila com o painel da manhã.

🚨 **TODA ESCRITA DEVOLVE `ok` + `motivo`, nunca estoura.** Recusa é resposta: o
MoviZap grava o motivo ao lado do card, e quem lê chega já ciente -- 🔵 *"os
motivos de recusa deve aparecer descritos ao inves de erro generico"*.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import pagamento_servico
from .os_ponte import verificar_segredo

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pagamento", tags=["pagamento-ponte"],
                   dependencies=[Depends(verificar_segredo)])


@router.get("/quadro")
def quadro():
    """As cinco colunas, com os cards e os artefatos. Somente leitura."""
    return pagamento_servico.quadro()


class Desde(BaseModel):
    # 🔵 D6: 16/11/2026. ⚠️ `aaaa-mm-dd`, e quem recusa torto é o serviço, com
    # `ok`+`motivo` -- a régua desta ponte inteira: recusa é resposta.
    desde: str = Field(..., min_length=10, max_length=10)
    por: str | None = None


@router.post("/desde")
def definir_desde(entrada: Desde):
    """A data inicial da aba 2. 🔵 D6 e D7 dele, 23/11.

    🚨 **A PERMISSÃO NÃO MORA AQUI**, como em toda esta ponte: `X-Ponte-Key` é
    servidor-a-servidor. Quem cobra *"a data inicial é somente do Owner"* é o
    MoviZap, na rota dele -- mesma régua da data matriz da Operação.
    """
    return pagamento_servico.definir_desde(entrada.desde, por=entrada.por)


class Varrer(BaseModel):
    # ⚠️ `None` varre o cache inteiro — é o que a primeira rodada precisa, e o
    # modo do ensaio a seco. Com 24h a primeira nasceria com 2 artefatos em vez
    # de 79, e o histórico começaria truncado.
    horas: int | None = 24


@router.post("/varrer")
def varrer(entrada: Varrer):
    """🔵 *"Rotina automatizada visita todas as OS das ultimas 24hrs"*.

    🚨 Lê o cache, não o ERP: custa **zero** chamada ao Harmonit.
    """
    return pagamento_servico.varrer(horas=entrada.horas)


class ItemAPreparar(BaseModel):
    id: int = Field(..., ge=1)
    # 🚨 O orçamento vem do MoviZap, que é o dono dele (🔵 decisão dele): a
    # tabela `orcamento`, com numeração nossa. O FPSL não tem como sabê-lo, e
    # adivinhar seria inventar dado.
    orcamento_numero: int | None = None


class Preparar(BaseModel):
    artefatos: list[ItemAPreparar]
    por: str | None = None


@router.post("/preparar")
def preparar(entrada: Preparar):
    """🔵 *"Os itens flegados e clicados em preparar, vão gerar novo card do
    técnico, agora preparando para pagamento."*"""
    return pagamento_servico.preparar(
        [i.model_dump() for i in entrada.artefatos], por=entrada.por)


class Conferir(BaseModel):
    artefato_id: int = Field(..., ge=1)
    # 🚨 As OS que o MoviZap diz estarem na etapa NOSSA 2322 ("Serviço
    # Realizado"). Só ele sabe, porque a etapa é dele -- e é a porta dupla que
    # conserta o funil de 11/11 (70 → 16 → 8 OS).
    etapas_nossas: list[int] = []


@router.post("/conferir-situacao")
def conferir_situacao(entrada: Conferir):
    """🔵 *"A preparação vai trazer essas situações a tela e exibir para o
    operador confirmar 1 a 1 na tela modal que abrir."*"""
    return pagamento_servico.situacao_para_conferir(
        entrada.artefato_id, etapas_nossas=entrada.etapas_nossas)


class UmArtefato(BaseModel):
    artefato_id: int = Field(..., ge=1)
    por: str | None = None


@router.post("/ciente")
def ciente(entrada: UmArtefato):
    """🔵 *"Dando ciência das etapas que estiver"*."""
    return pagamento_servico.dar_ciente(entrada.artefato_id, por=entrada.por)


class Devolver(UmArtefato):
    # ⚠️ Sem justificativa não se devolve: laranja sem motivo é cor sem
    # informação, e o serviço decide isso -- aqui só se transporta.
    justificativa: str = ""


@router.post("/devolver")
def devolver(entrada: Devolver):
    """🔵 *"o item de pagamento será removido e devolvido ao card na coluna de
    Movimentação abrindo um campo de justificativa"*. 🚨 Sempre para a coluna 1."""
    return pagamento_servico.devolver(
        entrada.artefato_id, entrada.justificativa, por=entrada.por)


class UmLote(BaseModel):
    lote_id: int = Field(..., ge=1)
    por: str | None = None


class DevolverLote(UmLote):
    # ⚠️ Mesma regra do artefato: sem justificativa não se devolve, e quem
    # decide isso é o serviço -- aqui só se transporta.
    justificativa: str = ""


@router.post("/devolver-lote")
def devolver_lote(entrada: DevolverLote):
    """🔵 *"Excluir o card inteiro devolvendo tudo à coluna 1, com
    justificativa única"* -- tarefa 2.4. 🚨 Sempre para a coluna 1, e a mesma
    justificativa em todos os itens."""
    return pagamento_servico.devolver_lote(
        entrada.lote_id, entrada.justificativa, por=entrada.por)


@router.post("/auditar")
def auditar(entrada: UmLote):
    """🔵 *"o botão (...) 'Auditar' que irá mover o card somente com os cientes
    de situação e não negados para a próxima coluna"*."""
    return pagamento_servico.auditar(entrada.lote_id, por=entrada.por)


@router.post("/datascope")
def datascope(entrada: UmArtefato):
    """A situação que está no DataScope para a OS deste artefato.

    ⚠️ **SÓ LEITURA, e do cache.** A correção da situação no DataScope é outra
    rota (ainda não construída) e 🔵 ele decidiu que ela abre modal antes de
    escrever -- `change_state` dispara os webhooks deles e manda push para o
    técnico que enviou a resposta.
    """
    return pagamento_servico.datascope_do_artefato(entrada.artefato_id)


class Comprovante(UmArtefato):
    arquivo: str | None = None
    valor: float | None = None
    dispensa: str | None = None


@router.post("/comprovante")
def comprovante(entrada: Comprovante):
    """🔵 *"haverá campo para que em cada 1 dos artefatos de pagamento seja
    inserido anexo que comprove o pagamento. Após o envio do anexo, abre o
    campo que pede o valor"*."""
    return pagamento_servico.guardar_comprovante(
        entrada.artefato_id, arquivo=entrada.arquivo, valor=entrada.valor,
        dispensa=entrada.dispensa, por=entrada.por)


class Revalidar(UmLote):
    etapas_nossas: list[int] = []


@router.post("/revalidar")
def revalidar(entrada: Revalidar):
    """🔵 *"todos os cards tem botão de 'atualizar' para rodar novamente as
    verificações daquele card"*. 🚨 Não move nada."""
    return pagamento_servico.revalidar(
        entrada.lote_id, etapas_nossas=entrada.etapas_nossas, por=entrada.por)


class MontarArquivo(UmLote):
    # 🔵 Os quatro do cadastro do Procfy chegam do `/config` do MoviZap.
    # ⚠️ E PODEM VIR VAZIOS: 🔵 *"pode gerar com elas em branco nesse momento,
    # pois podem preencher a mão por informação confidencial"*. A resposta diz
    # quais saíram em branco.
    config: dict = {}


@router.post("/montar-arquivo")
def montar_arquivo(entrada: MontarArquivo):
    """🔵 *"o botão de ação da vez é 'Montar Arquivo'"*."""
    return pagamento_servico.montar_arquivo(
        entrada.lote_id, entrada.config or {}, por=entrada.por)


@router.post("/previa-do-arquivo")
def previa_do_arquivo(entrada: MontarArquivo):
    """As linhas que o arquivo teria, **sem gerar nada**.

    🔵 *"dentro deles um resumo dos artefatos que vão para pagamento"* — e é o
    que a tela mostra antes de o operador clicar. ⚠️ Separada de quem grava de
    propósito: ver o resumo não pode mover card.
    """
    return pagamento_servico.linhas_do_procfy(
        entrada.lote_id, entrada.config or {})


@router.post("/reabrir")
def reabrir(entrada: UmLote):
    """🔵 *"Reabrir na coluna 5 e gerar o arquivo de novo"* -- tarefa 2.5.
    🚨 Sem justificativa de propósito: nada é devolvido nem desfeito, o lote só
    volta para a Validação para o arquivo ser gerado outra vez."""
    return pagamento_servico.reabrir_lote(entrada.lote_id, por=entrada.por)


@router.post("/enviar")
def enviar(entrada: UmLote):
    """🔵 *"Depois de ter o arquivo gerado e baixado, os artefatos (...) ficam
    neste card que vai para a próxima coluna."*"""
    return pagamento_servico.enviar_pagamento(entrada.lote_id, por=entrada.por)


@router.get("/arquivo")
def arquivo(lote_id: int = Query(..., ge=1)):
    """O `.xlsx` de um lote, em linhas — quem monta o arquivo binário é o
    MoviZap, que é quem o entrega ao navegador.

    🚨 **A PONTE NÃO SERVE BINÁRIO.** Ela fala JSON com o MoviZap e nada mais:
    abrir um caminho de download aqui exporia o FPSL a quem só deveria falar
    com o painel.
    """
    with_config: dict = {}
    r = pagamento_servico.linhas_do_procfy(lote_id, with_config)
    if not r.get("ok"):
        raise HTTPException(status_code=404, detail=r.get("motivo"))
    return r
