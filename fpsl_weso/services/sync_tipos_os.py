"""Rotina diaria: o NOME de cada tipo de OS, para a mensagem do agendamento.

🔵 Ponta 1 do plano de Agendamentos (§7.4): o cabecalho da mensagem que sai
para o cliente deve dizer **o tipo da OS**, e nao a palavra `(SERVICO)`.

🚨 UMA CONSULTA POR DIA, NAO UMA POR MENSAGEM. A lista de tipos muda em
cadastro, nao em operacao -- consultar o Harmonit no meio da montagem da
mensagem poria a tela do operador na frente de uma rota lenta, e o nome do
tipo nao vale uma espera.

🚨 29/10: ESTA ROTINA LIA A ROTA ERRADA, E ERA A CAUSA DOS 173 SEM NOME.
O Harmonit tem DUAS rotas de tipo de OS, e a diferenca nao esta no nome delas:
  · `ObterListaTipoOrdemServico` devolve **5** -- os selecionaveis em tela;
  · `ObterTiposOrdemServico` devolve **28** -- o catalogo inteiro.

A rotina usava a primeira. Entao o dicionario tinha 5 nomes, cobria **374 das
547** OS, e as outras **173** vinham com `tipo_nome` nulo -- o que fazia a
mensagem do agendamento OMITIR o segmento do tipo em uma de cada tres OS.

🚨 E A EXPLICACAO QUE EU HAVIA ESCRITO AQUI ESTAVA ERRADA. Dizia que os nove
ids de fora (57, 76, 73, 72, 55, 77, 75, 576, 814) eram *"tipos que o Harmonit
removeu ou renomeou"*. **Nao foram removidos: estao todos no catalogo de 28** --
`57` Retirada · `76` Instalacao rastreador · `77` Upgrade · `72`
Substituicao/Instalacao · `73` Substituicao/Retirada · `55` Manutencao · `75`
Entrega de Equipamentos · `576` Ressarcimento · `814` Trans.
Titularidade/Retirada. Eu inferi "removido" de uma ausencia que era so da rota
curta, e a inferencia virou comentario -- o mesmo erro de metodo que ele
apontou em 29/10: *"voce quem decidiu algo sem perguntar"*. **Ausencia numa
lista nao prova ausencia no cadastro.**

⚠️ ISTO MUDA O QUE O CLIENTE LE: a mensagem do agendamento passa a trazer o
tipo nas OS que antes o omitiam. A regra *"nulo omite o segmento"* nao mudou --
nulo e que ficou raro.

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

# 🚨 O CATALOGO INTEIRO (28), nao a lista curta (5). Ver o topo.
ROTA = "/TipoOrdemServico/ObterTiposOrdemServico"

# ⚠️ A rota do catalogo pagina; o `take` tem de caber o catalogo
# inteiro, senao o dicionario volta a ficar incompleto -- em
# silencio, que e o jeito ruim.
PARAMS = {"skip": 0, "take": 500}


def _lista(bruto) -> list[dict]:
    """A lista de tipos, de qualquer um dos dois formatos.

    ⚠️ Medido em 21/10: a rota CURTA devolvia lista crua. A do catalogo, que
    passou a ser usada em 29/10, devolve embrulhada em `data` -- e e por isso
    que tratar os dois formatos aqui ja valia a pena antes de valer.
    Conferido nas duas em 29/10.
    """
    if isinstance(bruto, dict):
        bruto = bruto.get("data")
    if not isinstance(bruto, list):
        return []
    return [t for t in bruto if isinstance(t, dict)]


async def sync_tipos_os() -> dict:
    """Consulta o Harmonit e atualiza a tabela `tipos_os`."""
    tipos = _lista(await harmonit_get(ROTA, params=PARAMS))
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
