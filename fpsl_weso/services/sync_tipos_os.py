"""Rotina diaria: o NOME de cada tipo de OS, para a mensagem do agendamento.

🔵 Ponta 1 do plano de Agendamentos (§7.4): o cabecalho da mensagem que sai
para o cliente deve dizer **o tipo da OS**, e nao a palavra `(SERVICO)`.

🚨 UMA CONSULTA POR DIA, NAO UMA POR MENSAGEM. A lista de tipos muda em
cadastro, nao em operacao -- consultar o Harmonit no meio da montagem da
mensagem poria a tela do operador na frente de uma rota lenta, e o nome do
tipo nao vale uma espera.

🚨 O QUE A MEDICAO DE 21/10 DIZ, e que desenha esta rotina:
  · a rota devolve **5 tipos** (`Contrato` 2, `Demanda Interna` 1782,
    `Solicitacao de Cliente` 1783, `Ordem de Servico` 1784, `Teste ou
    Treinamento` 1785), como **lista crua**, nao embrulhada em `data`;
  · eles cobrem **374 das 547** OS nao excluidas;
  · as outras **173** estao em NOVE ids fora da lista (57, 76, 73, 72, 55, 77,
    75, 576, 814) -- tipos que o Harmonit removeu ou renomeou. O
    `os_router._resolver_cabecalho_por_nome` ja registrava isso desde 14/08
    para o `tipo = 55`: *"id fixo em codigo apodrece em silencio"*.

⚠️ POR ISSO ESTA TABELA NAO E AUTORIDADE SOBRE "QUE TIPOS EXISTEM": ela e o
dicionario do que o Harmonit sabe nomear HOJE. Quem pergunta o nome de um
tipo fora dela recebe `None`, e quem desenha a mensagem **omite o segmento**
em vez de imprimir numero ou rotulo inventado -- tela que mente e defeito.

⚠️ NUNCA APAGA O QUE JA SABIA. Se a rota responder vazio (ou com menos tipos),
os nomes antigos ficam: um nome gravado continua certo mesmo depois de o
cadastro sair da lista, e esvaziar a tabela por uma resposta ruim faria toda
mensagem do dia perder o segmento de uma vez.
"""

import asyncio
import logging

from fpsl_weso.harmonit_client import harmonit_get
from fpsl_weso import rotinas, storage

log = logging.getLogger("fpsl.sync_tipos_os")

INTERVALO_SEG = 86_400  # 1x/dia, como o `sync_tecnicos`

ROTA = "/TipoOrdemServico/ObterListaTipoOrdemServico"


def _lista(bruto) -> list[dict]:
    """A lista de tipos, de qualquer um dos dois formatos.

    ⚠️ Medido em 21/10: esta rota devolve lista crua. O embrulho `{"data": [...]}`
    aparece em OUTRAS rotas do Harmonit, e tratar os dois aqui custa tres
    linhas -- a alternativa e a rotina parar de achar tipo nenhum no dia em
    que eles padronizarem o retorno.
    """
    if isinstance(bruto, dict):
        bruto = bruto.get("data")
    if not isinstance(bruto, list):
        return []
    return [t for t in bruto if isinstance(t, dict)]


async def sync_tipos_os() -> dict:
    """Consulta o Harmonit e atualiza a tabela `tipos_os`."""
    tipos = _lista(await harmonit_get(ROTA))
    if not tipos:
        # 🚨 Nao e erro, e nao apaga nada: ver a advertencia do topo.
        log.warning("sync_tipos_os: a lista de tipos veio vazia, nada a gravar")
        return {"ok": False, "motivo": "lista vazia"}

    gravados = 0
    for t in tipos:
        tipo_id = t.get("id")
        nome = (t.get("descricao") or "").strip()
        if not tipo_id or not nome:
            continue
        await storage.salvar_tipo_os(int(tipo_id), nome, t.get("codigo"))
        gravados += 1

    log.info("sync_tipos_os: %d tipos gravados", gravados)
    return {"ok": True, "tipos": gravados}


async def loop_sync_tipos_os():
    """Roda sync_tipos_os() uma vez por dia."""
    log.info("loop_sync_tipos_os: iniciando (intervalo=%ds)", INTERVALO_SEG)
    while True:
        resultado = "ok"
        try:
            r = await sync_tipos_os()
            if isinstance(r, dict):
                resultado = ", ".join(f"{k}={v}" for k, v in r.items())
        except Exception as exc:  # noqa: BLE001 -- rotina nao morre por uma passada
            log.exception("loop_sync_tipos_os: erro na rodada")
            resultado = f"ERRO: {exc}"
        await rotinas.marcar("sync_tipos_os", resultado)
        await asyncio.sleep(INTERVALO_SEG)
