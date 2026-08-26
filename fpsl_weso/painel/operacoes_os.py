"""Montagem das OS da aba OPERAÇÕES (`OPR_1.1`) — a etapa 4.

🚨 CLONE DA MONTAGEM DO `os_router`, E É DE PROPÓSITO. O critério está em
`docs/fpsl/28_Operacoes.md`:

    Se a regra muda entre a aba velha e a nova, CLONA.
    Se é infraestrutura sem regra, REUSA.

A montagem é o coração das seis regras que mudaram (4, 7, 9, 10, 11 e 12).
Compartilhá-la obrigaria a escolher entre quebrar a tela velha e travar esta.

⚠️ NÃO IMPORTE `os_router` NEM `templates_config` AQUI. Nem "só uma constante".

O que muda em relação à montagem velha, e por quê:

  regra 4  a financeira LISTA os itens de cobrança SEMPRE; `cobrar` só é
           marcado quando o valor é maior que zero. Antes, financeira de valor
           zero saía com o corpo vazio e ninguém via o que tinha sido
           contratado -- é por isso que "teste de tecnologia" precisava de um
           perfil só dele.
  regra 7  cada item pertence a um lado só -- COM UMA EXCEÇÃO, aberta pelo
           usuário em 26/08: o item marcado `nas_duas` no vínculo (hoje só a
           Central 24h) vai para os DOIS lados, sempre com valor zero e sem
           `cobrar` nem `comodato`. Não é o `nas_duas` de 14/08 de volta:
           aquele copiava um item de COBRANÇA para a operacional e mantinha a
           cobrança na financeira. Este não cobra em lado nenhum.
  regra 9  a WESO manda no modelo; quando não há equipamento, o operador
           escolhe pelo de-para. Não escolheu, fica em branco COM AVISO.
  regra 10 transferência novo titular vira DUAS OS: 1 operacional de comodato
           + 1 financeira. A híbrida antiga (cobrança + comodato juntos) morreu
           porque a regra 7 proíbe item de cobrança na OS de comodato.
  regra 11 ressarcimento é híbrida NOVA: cobrança + oficina, SEM comodato.
           Não é a mesma híbrida da regra 10 -- esta não tem item de comodato,
           então não esbarra na regra 7.
  regra 12 substituição ganha financeira.
"""
import logging
import re
import unicodedata
from collections import Counter
from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel

from . import operacoes_config as cfg
from . import operacoes_equipamentos as eqp
from .. import storage

log = logging.getLogger("fpsl.operacoes.os")


# ── O que a tela manda ───────────────────────────────────────────────────────

class PlacaOS(BaseModel):
    placa: str
    veiculo: str = ""
    # achado 2026-07-15: marca quem NÃO recebe bloqueio veicular. Não é "os N
    # primeiros da lista" -- a marcação está no texto do próprio veículo.
    sem_bloqueio: bool = False
    # só na substituição: o veículo que RECEBE o equipamento
    placa_entrada: str | None = None
    veiculo_entrada: str = ""
    # só na transferência: o cliente que passa a ser dono
    cliente_id_destino: int | None = None
    # 🆕 REGRA 9: o modelo escolhido na tela quando a WESO não tem equipamento
    # nesta placa. Vem do de-para, não é texto livre.
    modelo_escolhido: str | None = None


class ItemContrato(BaseModel):
    descricao: str
    quantidade: str | None = None
    valor_unitario: str | None = None
    comodato_ou_aquisicao: str | None = None


class MontarInput(BaseModel):
    perfil: str
    cliente_id: int
    lote: str | None = None
    termo: str = ""
    observacao: str = ""
    problema_id: int | None = None
    termo_relacionado: str = ""
    produto_servico_id: int
    placas: list[PlacaOS]
    itens: list[ItemContrato] = []
    solucao_tecnica: str | None = None
    prioridade_id: int = cfg.PRIORIDADE_NORMAL_ID
    motivo_financeira_zero: str = ""
    # 🆕 REGRA 12: a substituição pergunta se foi no mesmo local ou em local
    # diferente, e o VALOR vem do termo. Ver `financeira_substituicao`.
    local_diferente: bool = True
    valor_substituicao: float | None = None
    # ressarcimento sem termo: o operador digita o valor
    valor_ressarcimento: float | None = None
    confirmar: bool = False


# ── Conversões ───────────────────────────────────────────────────────────────

def parse_valor(txt) -> float:
    if txt is None or txt == "":
        return 0.0
    if isinstance(txt, (int, float)):
        return float(txt)
    try:
        return float(str(txt).replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def parse_qtd(txt) -> int:
    if not txt:
        return 0
    try:
        return int(str(txt).strip())
    except ValueError:
        return 0


def formatar_solucao_tecnica(contexto: str | None, observacao: str = "") -> str:
    """`solucaoTecnica` é o campo que o técnico preenche DEPOIS do serviço --
    não sobrescrevemos, só deixamos um cabeçalho com data e um separador,
    orientando a preencher dali para baixo. Combinado com o usuário em 15/07.

    A OBS do painel entra ABAIXO da linha de criação e ACIMA do separador: é
    contexto de quem abriu, não resultado de quem atendeu."""
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    linhas = [f"[{agora}] Contexto da extração automática:"]
    if (contexto or "").strip():
        linhas.append(contexto.strip())
    if (observacao or "").strip():
        linhas.append(f"OBS: {observacao.strip()}")
    return "\n".join(linhas) + "\n-------------\n"


# ── O aviso prévio, e a redação que muda a cada termo ────────────────────────
#
# 🚨 O VÍNCULO CASA POR TEXTO EXATO, E O TERMO NEGOCIA O PRAZO. O modelo traz
# "90 DIAS DE AVISO PRÉVIO DE CANCELAMENTO"; quando o comercial concede prazo
# menor, o mesmo campo vira "(90) 30 DIAS DE AVISO PRÉVIO DE CANCELAMENTO" --
# outra grafia, mesmo encargo. Sem isto o item vira PENDENTE, bloqueia a
# geração, e a saída fácil na tela de Vínculos é marcar OCULTO: foi assim que
# os R$ 131,74 do termo 8848 sumiram da financeira, em silêncio (25/08).
#
# ⚠️ MEDE O SUFIXO E O QUE VEM ANTES DELE, não a ocorrência da palavra. Só
# normaliza quando a parte à esquerda for exclusivamente número, parêntese,
# barra ou espaço -- "SEM AVISO PRÉVIO DE CANCELAMENTO", se um dia existir,
# NÃO é este item e continua pendente, que é o comportamento honesto.

AVISO_PREVIO_SUFIXO = "DIAS DE AVISO PREVIO DE CANCELAMENTO"
AVISO_PREVIO_CANONICO = "90 DIAS DE AVISO PREVIO DE CANCELAMENTO"
_SO_PRAZO_RE = re.compile(r"^[\d()/\s.\-]*$")


def _sem_acento(txt: str) -> str:
    t = unicodedata.normalize("NFKD", str(txt or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def eh_aviso_previo(descricao: str) -> bool:
    """A descrição é a linha de aviso prévio do termo, em qualquer redação?"""
    norm = _sem_acento(descricao)
    if not norm.endswith(AVISO_PREVIO_SUFIXO):
        return False
    prefixo = norm[: -len(AVISO_PREVIO_SUFIXO)]
    return bool(_SO_PRAZO_RE.match(prefixo))


def nome_para_vinculo(descricao: str) -> str:
    """O nome com que este item procura o vínculo. Igual à descrição, exceto no
    aviso prévio -- onde o prazo negociado muda a grafia sem mudar o item.

    🚨 A DESCRIÇÃO ORIGINAL NÃO SE PERDE: ela continua no item resolvido, é ela
    que a financeira lista e é dela que sai o prazo na solução técnica. Isto
    aqui é só a chave de busca.
    """
    return AVISO_PREVIO_CANONICO if eh_aviso_previo(descricao) else descricao


def prazo_do_aviso(descricao: str) -> str:
    """Os prazos escritos na linha, na ordem: '(90) 30' -> '90/30'."""
    numeros = re.findall(r"\d+", _sem_acento(descricao).split(AVISO_PREVIO_SUFIXO)[0])
    return "/".join(numeros)


def contexto_do_termo(resolvidos: list[dict]) -> str:
    """As linhas do termo que o técnico e o financeiro precisam LER, e que não
    cabem em material: hoje, o prazo do aviso prévio.

    Decisão do usuário (26/08): "essas informações de prazo podem aparecer no
    final da OS, no campo de soluções, conforme traço, data e detalhes do
    termo". O cabeçalho com data e o separador já existiam e vinham sempre
    vazios -- a aba nunca preencheu o `solucao_tecnica`.
    """
    linhas = []
    for item in resolvidos:
        if not eh_aviso_previo(item.get("descricao") or ""):
            continue
        prazo = prazo_do_aviso(item["descricao"])
        valor = float(item.get("valor_unitario") or 0)
        texto = f"Aviso prévio: {prazo} dias conforme termo" if prazo \
            else "Aviso prévio conforme termo"
        if valor > 0:
            texto += f" — R$ {valor:,.2f}".replace(",", "X").replace(
                ".", ",").replace("X", ".")
        linhas.append(texto + ".")
    return "\n".join(linhas)


def contexto_da_os(contexto_da_tela: str | None, resolvidos: list[dict]) -> str:
    """O que vai acima do traço: o que a tela mandou, mais o que o termo diz.

    ⚠️ A tela NUNCA mandou `solucao_tecnica` -- o campo existe no `MontarInput`
    desde sempre e todas as OS saíram com o cabeçalho seguido direto do traço.
    Somar os dois em vez de escolher um evita que preencher a tela um dia
    apague o que o termo diz.
    """
    partes = [p for p in ((contexto_da_tela or "").strip(),
                          contexto_do_termo(resolvidos)) if p]
    return "\n".join(partes)


# ── O que o termo diz na coluna "COMODATO OU AQUISIÇÃO" ──────────────────────
#
# 🚨 O PAINEL SÓ CONHECIA DUAS PALAVRAS: `COMODATO` e `NÃO CONTRATADO`. Todo o
# resto -- `CONTRATADO`, `DESATIVAR NO SISTEMA`, `NÃO POSSUI` -- caía no mesmo
# balde de aquisição e ia para a financeira, cobrando se tivesse valor. Medido
# em 26/08 nos termos 8848 e 8842.

_NAO_TEM = ("NAO CONTRATAD", "NAO POSSUI")


def eh_nao_tem(tipo_normalizado: str) -> bool:
    """O termo diz que este veículo NÃO tem o item — não entra em OS nenhuma.

    ⚠️ Recebe o texto JÁ normalizado (`_sem_acento`). Receber cru e normalizar
    aqui dobraria a normalização em quem chama e faria a regra depender de
    quem lembra de aplicá-la.
    """
    return any(marca in tipo_normalizado for marca in _NAO_TEM)


# ── Vínculos ─────────────────────────────────────────────────────────────────

async def resolver_vinculos(itens: list[ItemContrato]):
    """(resolvidos, pendentes, descartados, ocultados).

    🚨 O QUARTO VALOR NASCEU DE UM PREJUÍZO. Item com vínculo marcado OCULTO
    sumia da OS sem deixar rastro: nem aviso, nem linha na prévia, nada. No
    termo 8848 (25/08) o operador ocultou o aviso prévio para destravar a
    geração -- porque a redação do prazo não casava com o vínculo -- e a
    financeira saiu sem R$ 131,74, com a prévia aberta 6 segundos antes.
    `NÃO CONTRATADO` sempre virou aviso; oculto era mudo. Agora os dois falam.

    A decisão de COBRAR vem da coluna Tipo do contrato, NÃO do valor (regra do
    negócio, 20/07): comodato nunca cobra -- o valor da linha é patrimonial,
    vai para a DANFE de comodato, não é preço. Assim `cobrar` e `comodato`
    nunca são verdadeiros ao mesmo tempo.

    🚨 O `nas_duas` VOLTOU A SER LIDO EM 26/08, COM OUTRA REGRA. Histórico, que
    é o que impede de desfazer isto por engano:

      14/08  nasce do termo 8839: a Central vinha CONTRATADO com valor, caía só
             em cobrança e sumia da OS que o técnico lê. A cópia operacional
             ia com valor zero, mas a financeira continuava COBRANDO.
      19/08  a regra 7 tira o conceito: cada item de um lado só. Na prática a
             Central passou a existir só na financeira, cobrando.
      26/08  o usuário pede as duas de volta -- e fecha a cobrança: "a central
             nunca vai ter flag de cobrar ou comodato em ambas OS, nunca",
             entrando "com valor zerado". Não é o de 14/08: lá cobrava de um
             lado; aqui não cobra de nenhum.

    ⚠️ A coluna sempre esteve no banco, marcada por você na tela de Vínculos.
    Entre 19 e 26/08 ela existia e não era lida.
    """
    resolvidos, pendentes, descartados, ocultados = [], [], [], []
    for item in itens:
        tipo = _sem_acento(item.comodato_ou_aquisicao)
        # 'NÃO CONTRATADO' é por LINHA do contrato, não pelo vínculo oculto: o
        # mesmo item pode ser contratado em outro termo. Descarta antes do
        # lookup, senão viraria 'pendente' e bloquearia a geração.
        #
        # 🆕 'NÃO POSSUI' entra no mesmo caminho (usuário, 26/08). Até aqui o
        # painel não conhecia essa palavra: item 'NÃO POSSUI' COM valor caía no
        # balde de aquisição e ia COBRADO para a financeira.
        if eh_nao_tem(tipo):
            descartados.append(item.descricao)
            continue
        # 🚨 ID FIXO ANTES DO VÍNCULO, e só para os itens que o usuário mandou
        # fixar (hoje: a TAXA DE MIGRAÇÃO, decisão de 26/08). Sem isto o item
        # nasceria pendente e bloquearia a geração até alguém criar o vínculo
        # à mão -- que é o trabalho que a decisão de fixar existe para evitar.
        fixo = cfg.ITENS_COM_ID_FIXO.get(_sem_acento(item.descricao))
        vinc = ({"harmonit_id": fixo, "oculto": False, "nas_duas": False}
                if fixo else
                await storage.buscar_vinculo_item(nome_para_vinculo(item.descricao)))
        if vinc is None:
            pendentes.append(item.descricao)
            continue
        if vinc["oculto"]:
            ocultados.append(item.descricao)
            continue
        comodato = tipo.startswith("COMODATO")
        valor = parse_valor(item.valor_unitario)
        resolvido = {
            "descricao": item.descricao,
            "harmonit_id": vinc["harmonit_id"],
            "quantidade": parse_qtd(item.quantidade) or 1,
            "valor_unitario": valor,
            "comodato": comodato,
            "cobrar": False if comodato else valor > 0,
        }
        # 🚨 A REGRA DA CENTRAL, E ELA NASCE AQUI DE PROPÓSITO. Decisão do
        # usuário em 26/08: "a central nunca vai ter flag de cobrar ou comodato
        # em ambas OS, nunca" -- e entra "com valor zerado".
        #
        # Aplicar na ORIGEM e não no corte é o que faz a regra valer nos onze
        # perfis sem depender de eu lembrar de cada caminho: o antigo titular,
        # a manutenção e o ressarcimento montam a OS a partir de `resolvidos`
        # SEM passar por `separar_itens`, e ficariam de fora se a regra vivesse
        # lá. Um deles -- a transferência novo titular -- já tinha me escapado
        # na auditoria, com placar verde.
        #
        # 🚨 E NUNCA SOBRE COMODATO. Um item de comodato marcado `nas_duas` na
        # tela de Vínculos perderia a flag e o VALOR PATRIMONIAL -- a DANFE de
        # comodato sairia zerada e o rastreador do contrato viraria linha
        # informativa. Comodato já vai na operacional e já não cobra: não há o
        # que a regra acrescente ali, e há muito o que ela estrague.
        # Achado pelo `teste_operacoes_f4`, cujo dublê marcava o RASTREADOR
        # assim -- e em produção `nas_duas` nunca esteve num comodato.
        if vinc.get("nas_duas") and not comodato:
            resolvido.update({"nas_duas": True, "valor_unitario": 0.0,
                              "comodato": False, "cobrar": False})
        resolvidos.append(resolvido)
    return resolvidos, pendentes, descartados, ocultados


def alocar_itens_por_placa(resolvidos: list[dict], placas: list[PlacaOS]):
    """Distribui a quantidade de cada item pelas placas, em ordem, com uma
    exceção: item de bloqueio veicular só aloca nas placas que NÃO estão
    marcadas `sem_bloqueio` (achado 15/07: 28 veículos, só 11 recebem bloqueio,
    e quem é está no texto do próprio veículo)."""
    n = len(placas)
    alocacao: list[list[dict]] = [[] for _ in range(n)]
    avisos: list[str] = []
    for item in resolvidos:
        qtd = item["quantidade"]
        # 🚨 O INFORMATIVO É PRESENÇA, NÃO CONTAGEM. A Central entra em TODAS as
        # placas, uma linha cada, sem passar pela regra de quantidade: um termo
        # que escreve "01 CENTRAL 24 HORAS" para 2 veículos não quer dizer que
        # só um deles tem Central -- e alocar pela quantidade deixaria o
        # segundo técnico sem o recado. Como o valor é zero, repetir não soma
        # nada em lugar nenhum.
        if item.get("nas_duas"):
            for i in range(n):
                alocacao[i].append({**item, "quantidade": 1})
            continue
        if "BLOQUEIO" in item["descricao"].upper():
            elegiveis = [i for i, p in enumerate(placas) if not p.sem_bloqueio]
        else:
            elegiveis = list(range(n))
        if qtd > len(elegiveis):
            # DOIS NÍVEIS (decisão do usuário, 29/07). Rastreador e chip são 1
            # por placa SEMPRE: divergência neles significa veículo faltando no
            # termo. Acessório pode legitimamente ser menor que a frota. Um
            # aviso único treinava a pessoa a ignorar o alerta justamente
            # quando ele importava.
            desc = item["descricao"].upper()
            um_por_placa = any(t in desc for t in ("RASTREADOR", "CHIP", "EQUIPAMENTO"))
            if um_por_placa:
                avisos.append(
                    f"ERRO - '{item['descricao']}': o contrato tem {qtd} e "
                    f"chegaram {len(elegiveis)} placas. Este item é 1 por "
                    "veículo, então a diferença indica veículo faltando no "
                    "termo ou cadastrado fora do FPSL. Confira ANTES de gerar.")
            else:
                avisos.append(
                    f"'{item['descricao']}': {qtd} para {len(elegiveis)} placas "
                    "- acessório pode ser menor que a frota; alocado nas "
                    "primeiras, confira se são as certas.")
            qtd = len(elegiveis)
        for i in elegiveis[:qtd]:
            # cópia com quantidade=1 -- é a unidade alocada NESTA placa, não a
            # quantidade total do contrato
            alocacao[i].append({**item, "quantidade": 1})
    return alocacao, avisos


def dedup_placas(placas: list[PlacaOS]):
    """Colapsa placas repetidas, mantendo a primeira ocorrência. A mesma placa
    nunca deve gerar 2 OS (achado real, termo 8788: o documento listava as
    mesmas 3 placas em 2 referências diferentes)."""
    def _norm(p: PlacaOS) -> str:
        return " ".join((p.placa or "").upper().split())

    contagem = Counter(_norm(p) for p in placas if _norm(p))
    vistas: set[str] = set()
    unicas: list[PlacaOS] = []
    for p in placas:
        chave = _norm(p)
        if not chave:
            unicas.append(p)
            continue
        if chave in vistas:
            continue
        vistas.add(chave)
        unicas.append(p)

    avisos = []
    duplicadas = {k: v for k, v in contagem.items() if v > 1}
    if duplicadas:
        detalhe = "; ".join(f"{pl} ({n}x)" for pl, n in duplicadas.items())
        avisos.append("Placas repetidas no termo — gerada 1 OS por placa "
                      f"(não duplicada): {detalhe}")
    return unicas, avisos


# ── REGRA 9: o modelo, e os DOIS estados que produziam o mesmo texto ─────────
#
# 🚨 "AINDA NÃO VINCULADO" E "NÃO CONSEGUI LER A WESO" SÃO COISAS DIFERENTES, e
# até aqui produziam o mesmo texto. O primeiro é normal nesta aba: a etapa 3
# acabou de criar a placa, e placa criada há segundos não tem rastreador. O
# segundo é o defeito da OS 16775, em que `_rastreador_id_por_placa` engoliu a
# exceção e devolveu `{}` -- indistinguível de "a WESO respondeu e nenhuma
# placa tem equipamento".
#
# A tela SABE em qual estado está, porque ela mesma criou a placa segundos
# antes: o lote registra a ação `criado`. Por isso o motivo é calculado aqui,
# com o conjunto de placas nascidas no lote, e não adivinhado depois.

SEM_EQUIPAMENTO_NASCEU_AGORA = "nasceu_agora"
SEM_EQUIPAMENTO_WESO_MUDA = "weso_nao_respondeu"
SEM_EQUIPAMENTO_SEM_REGISTRO = "sem_equipamento"

RECADO_SEM_EQUIPAMENTO = {
    SEM_EQUIPAMENTO_NASCEU_AGORA:
        "A placa foi criada nesta rodada e ainda não tem equipamento "
        "vinculado na WESO — isso é esperado. Escolha o modelo que vai ser "
        "instalado.",
    SEM_EQUIPAMENTO_WESO_MUDA:
        "NÃO CONSEGUI LER A WESO para esta placa. Não é 'sem equipamento': é "
        "leitura falhada. Confira antes de gerar — foi assim que a OS 16775 "
        "saiu sem rastreador.",
    SEM_EQUIPAMENTO_SEM_REGISTRO:
        "A WESO respondeu e esta placa não tem equipamento vinculado. "
        "Escolha o modelo, ou deixe em branco e a OS sai sem material.",
}


def motivo_sem_equipamento(placa: str, nascidas_no_lote: set[str],
                           houve_falha_de_leitura: bool) -> str:
    """Por que esta placa não tem modelo. Ordem importa: falha de leitura vence
    tudo, porque é a única que significa 'não sei'."""
    if houve_falha_de_leitura:
        return SEM_EQUIPAMENTO_WESO_MUDA
    if eqp.chave(placa) in nascidas_no_lote:
        return SEM_EQUIPAMENTO_NASCEU_AGORA
    return SEM_EQUIPAMENTO_SEM_REGISTRO


def modelo_da_operacao(perfil: dict, placa: PlacaOS, materiais: list[dict],
                       recipientes: dict | None = None,
                       dados: dict | None = None) -> str | None:
    """Modelo do rastreador para a descrição da OS.

    🚨 IGNORA O VÍNCULO PARA ESTE ITEM (decisão do usuário, 13/08): o vínculo
    diz o que o TERMO escreveu, a WESO diz o que ESTÁ no veículo.

    🆕 REGRA 9: sem equipamento na WESO, vale o que o operador escolheu no
    de-para. Não escolheu, devolve None -- e None vira aviso na tela, nunca
    texto inventado. É a mesma família da placa inventada da regra 13.
    """
    origem = perfil.get("modelo_origem")
    if origem == "placa_teste" and perfil.get("placa_teste_sufixo"):
        d = (recipientes or {}).get(eqp.chave(placa.placa)) or {}
        bruto = d.get("modelo")
    else:
        d = (dados or {}).get(eqp.chave(placa.placa)) or {}
        bruto = d.get("modelo") or eqp.modelo_da_placa(placa.placa)

    if not bruto and placa.modelo_escolhido:
        bruto = placa.modelo_escolhido
    if not bruto:
        return None
    return eqp.modelo_efetivo(bruto, eqp.tem_leitor_rfid(materiais))


# ── o recipiente: sem "entrará" plausível, não inventa ───────────────────────

def norm_desc(t: str) -> str:
    """Texto comparável: espaço colapsado, caixa alta e SEM ACENTO.

    🚨 O ACENTO QUASE DERRUBOU A MANUTENÇÃO INTEIRA. Os recipientes `-MANUT` da
    WESO estão gravados `MANUTENCAO`, sem cedilha e sem til; o usuário
    padroniza escrevendo `MANUTENÇÃO`. Sem dobrar acento aqui, os dois nunca
    casariam e TODA geração de manutenção morreria em HTTP 400 -- com uma
    mensagem falando de upgrade anterior, que não tem nada a ver.
    """
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def conferir_recipientes(body: MontarInput, perfil: dict,
                         recipientes: dict) -> tuple[dict, list[dict]]:
    """Separa os recipientes CONFIÁVEIS dos demais, e avisa sobre cada descarte.

    🚨 SEM "ENTRARÁ" PLAUSÍVEL, NÃO INVENTA (decisão do usuário, 14/08). Até
    aquela data o upgrade derrubava a geração com HTTP 400 quando o recipiente
    não batia. Agora o duvidoso é DESCARTADO: a descrição sai com
    `NUMERO DE SERIE` para o técnico preencher e o equipamento NÃO entra nos
    materiais. Nenhum dado errado entra, sem travar quem está trabalhando.

    ⚠️ TODO DESCARTE VIRA AVISO NA TELA. Recipiente ignorado em silêncio seria
    pior que o 400: a OS pareceria completa e sairia sem o equipamento -- que é
    exatamente o defeito achado auditando o termo 8820.

    Quatro motivos, cada um com o seu texto: ausente, ambíguo, divergente
    (recipiente de uma rodada anterior) e sem série.
    """
    sufixo = perfil.get("placa_teste_sufixo")
    if not sufixo:
        return {}, []
    modelo = perfil.get("placa_teste_descricao") or "TERMO {termo}"
    esperado = modelo.format(termo=body.termo or "")
    bons: dict[str, dict] = {}
    avisos: list[dict] = []
    for p in body.placas:
        ch = eqp.chave(p.placa)
        pt = eqp.placa_teste(p.placa, sufixo)
        dado = recipientes.get(ch)
        if not dado:
            avisos.append(aviso(
                f"O recipiente {pt} não existe na WESO. A OS sai com "
                f"'{eqp.MARCADOR_SERIE_A_PREENCHER}' e SEM o equipamento nos "
                "materiais — peça ao setor de configuração para vincular.",
                p.placa))
            continue
        if dado.get("ambiguo"):
            achados = ", ".join(str(x) for x in dado["ambiguo"])
            avisos.append(aviso(
                f"Mais de um recipiente na WESO casa com {pt} ({achados}). "
                "Ambiguidade não se resolve por escolha automática — a OS sai "
                "sem o equipamento.", p.placa))
            continue
        achado = dado.get("descricao")
        if achado is not None and norm_desc(achado) != norm_desc(esperado):
            avisos.append(aviso(
                f"O recipiente {pt} está descrito como {achado!r}, e o "
                f"esperado é {esperado!r} — provavelmente é o recipiente de "
                "uma rodada ANTERIOR desta placa. A OS sai sem o equipamento.",
                p.placa))
            continue
        if not dado.get("serie"):
            avisos.append(aviso(
                f"O recipiente {pt} existe mas não tem rastreador vinculado. "
                f"A OS sai com '{eqp.MARCADOR_SERIE_A_PREENCHER}'.",
                p.placa))
            continue
        bons[ch] = dado
    return bons, avisos


_MARCA_RASTREADOR = ("RASTREADOR", "EQUIPAMENTO RASTREADOR")


def eh_rastreador(material: dict) -> bool:
    d = str(material.get("descricao") or "").upper()
    return any(marca in d for marca in _MARCA_RASTREADOR)


def substituir_rastreador(materiais: list[dict], equip: dict | None) -> list[dict]:
    """Troca o rastreador que veio do VÍNCULO pelo que a WESO diz estar no
    veículo. Sem equipamento resolvido NÃO mexe: apagar o item do contrato e
    não pôr nada no lugar é pior que a imprecisão."""
    if not equip:
        return list(materiais or [])
    restantes = [m for m in materiais or [] if not eh_rastreador(m)]
    return restantes + [equip]


def material_do_equipamento(perfil: dict, placa: PlacaOS, materiais: list[dict],
                            recipientes: dict | None = None,
                            dados: dict | None = None) -> dict | None:
    """Material do equipamento que a WESO diz estar (ou entrar) nesta placa.

    ⚠️ COMODATO, NUNCA COBRA -- nos perfis de contrato. O valor é PATRIMONIAL.

    🚨 MANUTENÇÃO NÃO FLEGA NADA (`sem_flags`, decisão do usuário 14/08): ali o
    equipamento não está saindo do patrimônio nem sendo vendido.

    🆕 REGRA 9: quando o modelo veio da escolha do operador, o produto e o
    valor patrimonial vêm do de-para, exatamente como viriam se a WESO tivesse
    respondido. O que muda é a origem do NOME, não o resto.
    """
    if not perfil.get("modelo_origem"):
        return None
    modelo = modelo_da_operacao(perfil, placa, materiais, recipientes, dados)
    if not modelo or modelo == eqp.MARCADOR_MODELO:
        return None
    produto = storage.produto_do_modelo(modelo)
    if not produto:
        # None é "não há de-para", e NUNCA bloqueia: a OS sai com o equipamento
        # apenas na descrição. TK-100, ST500, NT2x e Concox são esse caso.
        log.info("operacoes: modelo %r sem produto no de-para — fica só na "
                 "descrição", modelo)
        return None

    # ⚠️ O DE-PARA SÓ TEM VALOR PATRIMONIAL NOS MODELOS 4G; nos 2G é vazio. Ao
    # substituir, herda o valor do item do contrato que está saindo — senão a OS
    # trocaria um valor patrimonial real por nada.
    #
    # 🚨 ZERO AQUI É "NÃO SEI", NÃO "VALE NADA". `produto_do_modelo` devolve
    # `row[2] or 0.0`, então o de-para sem valor chega como 0.0 e não como
    # None — testar `is not None` nunca herdaria nada, e o comodato sairia
    # zerado. Medido em 14/08 ensaiando a Substituição: o ST310U saiu com
    # R$ 0,00 enquanto o contrato dizia R$ 1.100,00.
    substituidos = [m for m in materiais or [] if eh_rastreador(m)]
    herdado = next((m.get("valor_unitario") for m in substituidos
                    if m.get("valor_unitario")), 0.0)
    valor = produto["valor"] or herdado

    sem_flags = bool(perfil.get("sem_flags"))
    return {"harmonit_id": produto["harmonit_id"], "quantidade": 1,
            "valor_unitario": 0.0 if sem_flags else (valor or 0.0),
            "comodato": not sem_flags, "cobrar": False,
            "descricao": produto["descricao"],
            # 🚨 MARCA INTERNA, e a F5 depende dela: é por ela que a liberação
            # da série confirma que o equipamento REALMENTE foi anexado antes
            # de apagar o recipiente. `_criar_uma_os` só lê as chaves que o
            # Harmonit espera, então esta sobra não viaja no payload.
            "_equipamento": True}


# ── Materiais ────────────────────────────────────────────────────────────────

def material_fixo(harmonit_id: int, descricao: str) -> dict:
    return {"harmonit_id": harmonit_id, "quantidade": 1, "valor_unitario": 0.0,
            "comodato": False, "cobrar": False, "descricao": descricao}


def materiais_operacional(alocados: list[dict], produto_servico_id: int) -> list[dict]:
    """Ordem da OS operacional (regra 6, mantida): linha do Produto/Serviço do
    cabeçalho SEM flag -> itens alocados -> ENTREGA OS (fixo em toda OS)."""
    servico = material_fixo(produto_servico_id, "SERVIÇO DO CABEÇALHO (sem flag)")
    entrega = material_fixo(cfg.ENTREGA_OS_ID, "ENTREGA OS")
    return [servico] + list(alocados) + [entrega]


# ── REGRA 4: a financeira lista os itens SEMPRE ──────────────────────────────

def itens_de_cobranca(resolvidos: list[dict]) -> list[dict]:
    """Os itens que pertencem ao lado financeiro: tudo que NÃO é comodato.

    🚨 REGRA 4: entram TODOS, inclusive os de valor zero. O `cobrar` é que
    depende do valor. Antes, a financeira só listava o que tinha `cobrar`
    marcado, e uma financeira de valor zero saía com o corpo vazio -- ninguém
    via o que tinha sido contratado. Era por isso que "teste de tecnologia"
    precisava de um perfil próprio; agora quem separa contrato pago de teste
    gratuito é o VALOR, não uma flag.
    """
    saida = []
    for item in resolvidos:
        if item.get("comodato"):
            continue
        copia = dict(item)
        copia["cobrar"] = float(copia.get("valor_unitario") or 0) > 0
        saida.append(copia)
    return saida


def separar_itens(perfil: dict, resolvidos: list[dict]):
    """(itens_operacional, itens_financeiro). A separação vem ANTES da alocação.

    🚨 A ALOCAÇÃO POR PLACA RODA SÓ SOBRE O QUE VAI NA OPERACIONAL. Distribuir
    item de cobrança pelas placas o faria aparecer nas duas OS -- que é
    exatamente o que a regra 7 acabou de proibir.

    🆕 REGRA 4 MUDA O CORTE. Antes, o operacional levava tudo que não tinha
    `cobrar` marcado, e item sem comodato com valor zero caía lá. Agora o corte
    é por NATUREZA, não por valor: comodato é da operacional, o resto é do lado
    financeiro -- listado sempre, com `cobrar` dependendo do valor.

    ⚠️ Dois perfis fogem do corte, e continuam como estavam:
      `financeira_embutida` (rescisão) manda TUDO por placa, cobrança inclusive,
        preservando o `cobrar` de cada item -- muda só ONDE, não O QUÊ. Decisão
        de 29/07, ainda de pé.
      `sem_flags` (manutenção) zera as duas flags e não gera financeira.

    🆕 O ITEM `nas_duas` (a Central) É O ÚNICO QUE VAI PARA OS DOIS LADOS.
    Decisão do usuário em 26/08: o técnico precisa ver que o veículo tem
    Central -- é ele quem desativa -- e o financeiro precisa saber que ela
    existe para parar de cobrar. Ele já chega aqui zerado e sem flags, então
    aparecer duas vezes não soma valor em lugar nenhum.

    ⚠️ NÃO É O `nas_duas` DE 14/08 DE VOLTA. Aquele copiava um item de
    COBRANÇA para a operacional com valor zero, deixando a cobrança de pé na
    financeira. Este não cobra em lado nenhum.
    """
    if perfil.get("financeira_embutida"):
        return list(resolvidos), []
    if perfil.get("sem_flags"):
        return [{**i, "cobrar": False, "comodato": False}
                for i in resolvidos], []
    return ([i for i in resolvidos if i.get("comodato") or i.get("nas_duas")],
            itens_de_cobranca(resolvidos))


def montar_financeira(body: MontarInput, itens_financeiro: list[dict],
                      extras: list[dict] | None = None) -> dict:
    """OS financeira: 1 por termo, agregada de todas as placas.

    Cabeçalho fixo (regra 5): situação Financeiro, técnico Karla, prioridade
    sempre Normal -- a prioridade escolhida na tela é das operacionais.

    ⚠️ Recebe a lista JÁ SEPARADA, não `resolvidos`. Se ela rederivasse aqui, a
    prévia e a gravação poderiam divergir no dia em que o corte mudasse de
    lugar -- e prévia que diverge da gravação é pior que não ter prévia.
    """
    placas_txt = ", ".join(p.placa for p in body.placas)
    corpo = [dict(i) for i in itens_financeiro] + list(extras or [])
    itens_txt = "; ".join(i["descricao"] for i in corpo) or "—"
    descricao = (f"FINANCEIRO — TERMO {body.termo} | placas: {placas_txt} | "
                 f"itens: {itens_txt}")
    if not any(i.get("cobrar") for i in corpo):
        motivo = body.motivo_financeira_zero.strip() or "(não informado)"
        descricao += f" | SEM CUSTO — motivo: {motivo}"
    materiais = [dict(i) for i in corpo] + [
        material_fixo(cfg.ENTREGA_OS_ID, "ENTREGA OS")]
    return {
        "cliente_id": body.cliente_id,
        "placa": "(financeira)", "veiculo": "",
        "tipo_id": cfg.TIPO_CONTRATO_ID,
        "problema_id": cfg.FINANCEIRO_PROBLEMA_ID,
        "situacao_id": cfg.SITUACAO_FINANCEIRO_ID,
        "produto_servico_id": cfg.FINANCEIRO_PRODUTO_SERVICO_ID,
        "prioridade_id": cfg.PRIORIDADE_NORMAL_ID,
        "tecnico_id": cfg.FINANCEIRO_TECNICO_ID,
        "rotulo": "Financeira",
        "descricao": descricao,
        "materiais": materiais,
        "eh_financeira": True,
    }


# ── REGRA 12: a financeira da substituição ───────────────────────────────────

def financeira_substituicao(body: MontarInput, perfil: dict) -> dict:
    """O item de serviço da substituição, para entrar na financeira.

    🚨 O SERVIÇO ESTÁ PENDENTE DE DECISÃO SUA, E FALHA ALTO. O nome pedido não
    existe no Harmonit e o mais próximo tem DOIS registros idênticos (6967 e
    54845). A regra da casa é resolver por nome -- e aqui o nome não decide.
    Escolher o primeiro da lista no chute geraria OS com o serviço errado sem
    nada acusar.

    🆕 O VALOR VEM DO TERMO, NÃO DO CÓDIGO. Medido em 19/08: o termo de
    substituição já traz `taxa_local_diferente` (299,90) e `taxa_mesmo_local`
    (199,90). Valor de serviço fixado em código apodrece igual a id de tipo --
    foi assim que 7 das 14 OS de manutenção ficaram com `tipo = 55`, que não
    existe mais na lista. O código só entra como último recurso, quando o termo
    não trouxe o valor.
    """
    servico_id = perfil.get("financeira_servico_id")
    if not servico_id:
        raise HTTPException(422,
            "A financeira da substituição precisa do serviço de "
            "'substituição em local diferente', e ele ainda não foi escolhido. "
            "Há dois registros com o nome idêntico no Harmonit (6967 e 54845) "
            "e resolver por nome pegaria um no chute. Escolha o id antes de "
            "gerar.")
    valor = body.valor_substituicao
    if valor is None:
        valor = perfil.get("financeira_servico_valor") or 0.0
    valor = float(valor)
    onde = "local diferente" if body.local_diferente else "mesmo local"
    return {"harmonit_id": servico_id, "quantidade": 1,
            "valor_unitario": valor, "comodato": False,
            "cobrar": valor > 0,
            "descricao": f"SUBSTITUIÇÃO — {onde}"}


# ── REGRA 10: novo titular vira DUAS OS ──────────────────────────────────────

def equipamentos_agregados(body: MontarInput, perfil: dict, itens: list[dict],
                           dados: dict | None = None) -> list[dict]:
    """Na OS agregada (titularidade), UMA linha de equipamento POR PLACA.

    🚨 O VÍNCULO TRAZIA UM ÚNICO ITEM COM A QUANTIDADE DO TERMO -- 28 unidades
    de "RASTREADOR" para 28 veículos -- e todas viravam o mesmo ST310U, porque
    o vínculo mapeia TEXTO para produto fixo. Aqui cada veículo entra com o
    modelo que a WESO diz que ele tem.

    ⚠️ Sem nenhum equipamento resolvido, devolve a lista como estava: apagar o
    item do contrato e não pôr nada no lugar é pior que a imprecisão.
    """
    achados = []
    for p in body.placas:
        e = material_do_equipamento(perfil, p, itens, None, dados)
        if e:
            achados.append(e)
    if not achados:
        return list(itens)
    return [m for m in itens if not eh_rastreador(m)] + achados


def aviso(texto: str, placa: str | None = None) -> dict:
    """Um aviso, e de qual placa ele é.

    🚨 `placa=None` NÃO É DESCUIDO: é a marca de "isto é do lote, não de um
    veículo". "A base da WESO mudou no meio da leitura" não pertence a placa
    nenhuma, e forçar uma poria o recado numa OS ao acaso.
    """
    return {"texto": texto, "placa": placa}


def aviso_cobranca_sem_motivo(body: MontarInput, perfil: dict,
                              resolvidos: list[dict]) -> list[str]:
    """Cobrança zerada exige motivo, e vale nos DOIS caminhos.

    🚨 Com a financeira embutida (rescisão) a lista de cobrança separada fica
    sempre vazia por construção, então checar "não há itens financeiros"
    deixaria de valer justamente onde mais importa: no termo 8788 a TAXA DE
    RETIRADA vem riscada, valendo R$ 0,00. Por isso olha os itens de cobrança
    de verdade e o VALOR deles.
    """
    if perfil.get("sem_financeira"):
        return []
    # 🚨 O PERFIL PODE TRAZER O PROPRIO VALOR, e ate 21/08 isto nao era
    # olhado. `resolvidos` sao os itens do TERMO; num perfil SEM TERMO a lista
    # e vazia por construcao, entao `not cobrancas` dava True e o aviso
    # disparava mesmo com o perfil carregando valor. O operador lia "preencha o
    # motivo" com a cobranca ja preenchida -- e aviso falso treina a equipe a
    # ignorar aviso, que e a regra escrita em 19/08.
    # Espelha a linha que monta a hibrida: o valor e o DIGITADO, e o padrao do
    # perfil so entra quando ninguem digitou.
    _valor = (body.valor_ressarcimento if body.valor_ressarcimento is not None
              else perfil.get("servico_valor_inicial"))
    if float(_valor or 0) > 0:
        return []
    cobrancas = [i for i in resolvidos if i.get("cobrar")]
    sem_valor = (not cobrancas) or all(
        float(i.get("valor_unitario") or 0) == 0 for i in cobrancas)
    if sem_valor and not body.motivo_financeira_zero.strip():
        return ["Cobrança sem valor (saldo 0) e sem motivo informado — "
                "preencha o motivo (mudança de gestão, acordo interno, etc.) "
                "antes de gerar."]
    return []


def descricao_titularidade(perfil: dict, body: MontarInput,
                           dados: dict | None = None) -> str:
    """Aponta o termo do OUTRO lado (novo titular cita o anterior; antigo, o
    posterior) e lista as placas, cada uma com o modelo lido da WESO."""
    partes = []
    for p in body.placas:
        d = (dados or {}).get(eqp.chave(p.placa)) or {}
        modelo = d.get("modelo") or eqp.modelo_da_placa(p.placa)
        partes.append(f"{p.placa} ({eqp.modelo_efetivo(modelo)})" if modelo
                      else p.placa)
    rel = (f" | termo relacionado {body.termo_relacionado}"
           if body.termo_relacionado else "")
    return (f"{perfil['descricao_prefixo']}: TERMO {body.termo}{rel} | "
            f"placas: {', '.join(partes)}")


def montar_novo_titular(body: MontarInput, perfil: dict, resolvidos: list[dict],
                        dados: dict | None = None) -> list[dict]:
    """🆕 REGRA 10: DUAS OS, não mais uma híbrida.

    A híbrida antiga punha financeiro e comodato JUNTOS na mesma OS. A regra 7
    proíbe item de cobrança na OS de comodato, então ela não pode continuar
    existindo. Passa a ser 1 operacional só de comodato + 1 financeira com o
    cabeçalho padrão.

    ⚠️ NÃO CONFUNDIR com a híbrida que NASCE no ressarcimento (regra 11): lá é
    cobrança + oficina, sem nenhum item de comodato -- por isso não esbarra na
    regra 7. São compatíveis e não são a mesma coisa.
    """
    # 🆕 O `nas_duas` (a Central) entra aqui também. Esta OS não passa por
    # `separar_itens` -- foi o caminho que escapou na auditoria de 26/08, e
    # escaparia com placar verde. Como a OS é AGREGADA, a quantidade é o número
    # de placas, e não uma linha por placa.
    informativos = [{**i, "quantidade": len(body.placas)}
                    for i in resolvidos if i.get("nas_duas")]
    comodato = equipamentos_agregados(
        body, perfil, [i for i in resolvidos if i.get("comodato")], dados)
    comodato = list(comodato) + informativos
    descricao = descricao_titularidade(perfil, body, dados)
    placas_txt = ", ".join(p.placa for p in body.placas)
    operacional = {
        "cliente_id": body.cliente_id,
        "placa": placas_txt, "veiculo": "",
        "tipo_id": perfil.get("tipo_id", cfg.TIPO_CONTRATO_ID),
        "problema_id": perfil["problema_id"],
        "situacao_id": cfg.SITUACAO_NOVA_ID,
        "produto_servico_id": body.produto_servico_id,
        "prioridade_id": body.prioridade_id,
        "rotulo": "Novo titular (comodato)",
        "descricao": descricao,
        "materiais": materiais_operacional(comodato, body.produto_servico_id),
    }
    financeira = montar_financeira(body, itens_de_cobranca(resolvidos))
    financeira["rotulo"] = "Novo titular (financeira)"
    return [operacional, financeira]


def montar_antigo_titular(body: MontarInput, perfil: dict,
                          resolvidos: list[dict],
                          dados: dict | None = None) -> list[dict]:
    """1 OS agregada, com TODOS os itens do termo e SEM flegar nada.

    Decisão de 29/07, mantida: o contrato antigo está encerrando; quem assume
    comodato e cobrança é o novo titular, na OS dele. Por isso também NÃO tem
    financeira.
    """
    sem_flag = equipamentos_agregados(
        body, perfil,
        [{**i, "comodato": False, "cobrar": False} for i in resolvidos], dados)
    # ⚠️ O equipamento resolvido pela WESO volta com `comodato=True` nos perfis
    # de contrato; aqui ele também não flega, porque o contrato antigo está
    # encerrando e quem assume o comodato é o novo titular, na OS dele.
    sem_flag = [{**i, "comodato": False, "cobrar": False} for i in sem_flag]
    return [{
        "cliente_id": body.cliente_id,
        "placa": ", ".join(p.placa for p in body.placas), "veiculo": "",
        "tipo_id": perfil.get("tipo_id", cfg.TIPO_CONTRATO_ID),
        "problema_id": perfil["problema_id"],
        "situacao_id": cfg.SITUACAO_NOVA_ID,
        "produto_servico_id": body.produto_servico_id,
        "prioridade_id": body.prioridade_id,
        "rotulo": "Antigo titular",
        "descricao": descricao_titularidade(perfil, body, dados),
        "materiais": materiais_operacional(sem_flag, body.produto_servico_id),
    }]


# ── REGRA 11: a híbrida do ressarcimento ─────────────────────────────────────

def montar_ressarcimento(body: MontarInput, perfil: dict,
                         resolvidos: list[dict],
                         dados: dict | None = None) -> list[dict]:
    """🆕 REGRA 11: UMA OS híbrida por termo — cobrança + oficina, SEM comodato.

    🚨 POR QUE ELA PODE SER HÍBRIDA E A DO NOVO TITULAR NÃO. A regra 7 proíbe
    item de COBRANÇA na OS de COMODATO. Esta OS não tem item de comodato
    nenhum: é cobrança mais o trabalho de oficina que devolve o equipamento ao
    estoque. Sem comodato, sem conflito.

    A oficina não é exclusiva da OS operacional (decisão do usuário, 19/08) --
    é justamente ela que dispara a rotina de devolver ao estoque, na F5.

    O valor: no perfil COM termo ele vem do documento; no perfil SEM termo o
    operador digita. Zero mantém `cobrar` desmarcado, pela regra 4, sem
    exceção.
    """
    corpo = itens_de_cobranca(resolvidos)
    if perfil.get("produto_servico_id"):
        # 🚨 `is None`, NAO `or`: `or` nao distingue "nao informou" de
        # "informou zero", e zero e um valor legitimo -- o ramo "SEM CUSTO —
        # motivo" existe exatamente para ele. Enquanto o padrao do perfil era
        # 0,00 dava na mesma; com 0,01 passaria a ser impossivel digitar zero.
        valor = float(body.valor_ressarcimento
                      if body.valor_ressarcimento is not None
                      else (perfil.get("servico_valor_inicial") or 0.0))
        corpo.append({"harmonit_id": perfil["produto_servico_id"],
                      "quantidade": 1, "valor_unitario": valor,
                      "comodato": False, "cobrar": valor > 0,
                      "descricao": "RESSARCIMENTO"})
    placas_txt = ", ".join(p.placa for p in body.placas)
    termo_txt = f"TERMO {body.termo} | " if body.termo else ""
    descricao = f"{perfil['descricao_prefixo']}: {termo_txt}placas: {placas_txt}"
    if not any(i.get("cobrar") for i in corpo):
        motivo = body.motivo_financeira_zero.strip() or "(não informado)"
        descricao += f" | SEM CUSTO — motivo: {motivo}"
    return [{
        "cliente_id": body.cliente_id,
        "placa": placas_txt, "veiculo": "",
        "tipo_id": cfg.TIPO_CONTRATO_ID,
        "problema_id": perfil["problema_id"],
        # A híbrida nasce no Financeiro, com a técnica Karla -- é dali que a
        # cobrança sai. A oficina acontece na mesma OS.
        "situacao_id": perfil.get("situacao_id", cfg.SITUACAO_FINANCEIRO_ID),
        "produto_servico_id": body.produto_servico_id,
        "prioridade_id": cfg.PRIORIDADE_NORMAL_ID,
        "tecnico_id": perfil.get("tecnico_id"),
        "rotulo": "Ressarcimento (híbrida: cobrança + oficina)",
        "descricao": descricao,
        "materiais": [dict(i) for i in corpo] + [
            material_fixo(cfg.ENTREGA_OS_ID, "ENTREGA OS")],
        "hibrida": True,
    }]


# ── A montagem ───────────────────────────────────────────────────────────────

def _op_por_placa(body: MontarInput, perfil: dict, p: PlacaOS,
                  materiais: list[dict], seriais: dict, recipientes: dict,
                  dados: dict) -> dict:
    """Uma OS operacional para uma placa."""
    d = (dados or {}).get(eqp.chave(p.placa)) or {}
    serie_saida = d.get("serie") or eqp.serie_de(seriais, p.placa)
    modelo = modelo_da_operacao(perfil, p, materiais, recipientes, dados)
    saida_bruto = d.get("modelo") or eqp.modelo_da_placa(p.placa)
    return {
        "cliente_id": body.cliente_id,
        "placa": p.placa, "veiculo": p.veiculo,
        "tipo_id": perfil["tipo_id"],
        # ⚠️ O `problema_id` da TELA não entra aqui. Ele só vence nos perfis
        # SEM TERMO -- num contrato o problema é ditado pelo documento, não
        # escolhido por quem digita. Quem aplica isso é `_aplicar_cabecalho`,
        # no router, junto com a resolução por nome.
        "problema_id": perfil["problema_id"],
        "situacao_id": cfg.SITUACAO_NOVA_ID,
        "produto_servico_id": body.produto_servico_id,
        "prioridade_id": body.prioridade_id,
        "descricao": perfil["descricao_template"].format(
            placa=p.placa, veiculo=p.veiculo, termo=body.termo,
            serie=serie_saida,
            serie_entrada=eqp.serie_que_entra(perfil, recipientes, p.placa),
            # 🚨 MODELO AUSENTE NÃO VIRA TEXTO INVENTADO. Sai o marcador, que é
            # honesto e visível, e a tela avisa antes do botão Gerar.
            modelo=modelo or eqp.MARCADOR_MODELO,
            modelo_saida=eqp.modelo_efetivo(saida_bruto,
                                            eqp.tem_leitor_rfid(materiais))),
        "rotulo": perfil["label"],
        "materiais": materiais_operacional(materiais, body.produto_servico_id),
    }


def montar(body: MontarInput, perfil: dict, alocacao: list[list[dict]],
           itens_financeiro: list[dict], resolvidos: list[dict],
           seriais: dict | None = None, recipientes: dict | None = None,
           dados: dict | None = None) -> list[dict]:
    """1 operação = 1 OS a criar. Devolve a lista completa, operacionais e
    financeira, na ordem em que serão gravadas."""
    seriais = seriais or {}
    recipientes = recipientes or {}
    dados = dados or {}

    # ── perfis agregados: uma OS por termo, não por placa ────────────────────
    if perfil.get("hibrida"):
        return montar_ressarcimento(body, perfil, resolvidos, dados)
    if perfil.get("titularidade") == "novo":
        return montar_novo_titular(body, perfil, resolvidos, dados)
    if perfil.get("titularidade") == "antigo":
        return montar_antigo_titular(body, perfil, resolvidos, dados)

    operacoes: list[dict] = []
    for idx, p in enumerate(body.placas):
        materiais = alocacao[idx]
        equip = material_do_equipamento(perfil, p, materiais, recipientes, dados)
        materiais = substituir_rastreador(materiais, equip)

        if perfil["os_por_placa"] == 1:
            operacoes.append(_op_por_placa(body, perfil, p, materiais,
                                           seriais, recipientes, dados))
            continue

        if body.perfil == "substituicao":
            if not p.placa_entrada:
                raise HTTPException(400,
                    f"Placa {p.placa}: a Substituição exige a placa de entrada "
                    "(o veículo que recebe o equipamento).")
            base = dict(cliente_id=body.cliente_id,
                        situacao_id=cfg.SITUACAO_NOVA_ID,
                        produto_servico_id=body.produto_servico_id,
                        prioridade_id=body.prioridade_id,
                        materiais=materiais_operacional(
                            materiais, body.produto_servico_id))
            modelo = modelo_da_operacao(perfil, p, materiais, recipientes, dados)
            operacoes.append({
                **base,
                "placa": p.placa, "veiculo": p.veiculo,
                "tipo_id": perfil["tipo_id_retirada"],
                "problema_id": perfil["problema_id_retirada"],
                "descricao": perfil["descricao_template_retirada"].format(
                    placa=p.placa, veiculo=p.veiculo, termo=body.termo,
                    serie=eqp.serie_de(seriais, p.placa),
                    modelo=modelo or eqp.MARCADOR_MODELO),
                "rotulo": "Retirada",
            })
            # 🚨 SÉRIE E MODELO DA MESMA PLACA. Esta linha descreve o veículo
            # que RECEBE, então lê dele. Misturar a série de um com o modelo de
            # outro produz "007933914 (modelo nao localizado)", que parece
            # defeito e não é.
            # ⚠️ O MATERIAL continua vindo da placa que SAI: na substituição o
            # equipamento é O MESMO e muda de veículo.
            entrada = PlacaOS(placa=p.placa_entrada,
                              veiculo=p.veiculo_entrada,
                              modelo_escolhido=p.modelo_escolhido)
            modelo_entrada = modelo_da_operacao(perfil, entrada, materiais,
                                                recipientes, dados)
            operacoes.append({
                **base,
                "placa": p.placa_entrada, "veiculo": p.veiculo_entrada,
                "tipo_id": perfil["tipo_id_instalacao"],
                "problema_id": perfil["problema_id_instalacao"],
                "descricao": perfil["descricao_template_instalacao"].format(
                    placa=p.placa_entrada, veiculo=p.veiculo_entrada,
                    termo=body.termo,
                    serie=eqp.serie_de(seriais, p.placa_entrada),
                    modelo=modelo_entrada or eqp.MARCADOR_MODELO),
                "rotulo": "Instalação",
            })
            continue

        raise HTTPException(500,
            f"Perfil '{body.perfil}' tem os_por_placa=2 e nenhum tratamento "
            "explícito. Isto é erro de configuração, não de uso.")

    # ── a financeira, uma por termo ──────────────────────────────────────────
    #
    # ⚠️ `financeira_embutida` É A RESCISÃO, E CONTINUA VALENDO. Decisão do
    # usuário em 29/07: na rescisão a cobrança vai em CADA OS de placa, com o
    # `cobrar` preservado, "é mais seguro assim" -- fica amarrada ao veículo
    # que a gerou, em vez de num agregado que pode ser fechado sem conferir
    # placa a placa. A regra 3 da spec 28 reverteria isto e está PENDENTE de
    # confirmação sua; até lá vale o que foi decidido.
    if perfil.get("sem_financeira") or perfil.get("financeira_embutida"):
        return operacoes

    extras = []
    if body.perfil == "substituicao":
        extras.append(financeira_substituicao(body, perfil))
    operacoes.append(montar_financeira(body, itens_financeiro, extras))
    return operacoes
