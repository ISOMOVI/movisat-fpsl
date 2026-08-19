"""Rotas do painel de geração de OS por contrato."""
import re
import io
import logging
import unicodedata
from collections import Counter
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from ..auth import requer_aba
from ..templates_config import (
    PERFIS,
    ENTREGA_OS_ID,
    TIPO_CONTRATO_ID,
    SITUACAO_NOVA_ID,
    SITUACAO_FINANCEIRO_ID,
    FINANCEIRO_PROBLEMA_ID,
    FINANCEIRO_PRODUTO_SERVICO_ID,
    FINANCEIRO_TECNICO_ID,
    PRIORIDADE_NORMAL_ID,
)
from ..pdf_extractor import extrair_campos
from ..equipamentos import (MARCADOR_NAO_LOCALIZADO, MARCADOR_SERIE_A_PREENCHER,
                            buscar_seriais, chave_recipiente, dados_das_placas,
                            descricao_da_placa, liberar_recipiente,
                            modelo_da_placa, modelo_efetivo, placa_teste,
                            serie_de, tem_leitor_rfid)
from ..equipamentos import _chave as _chave_placa
from ...harmonit_client import harmonit_get, harmonit_post
from ... import storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/painel/api", tags=["painel"])


@router.get("/perfis")
# ⚠️ `cadastro_placas` entrou em 17/08. `/perfis` e lookup COMPARTILHADO -- ja
# servia Gerar OS e Vinculos, e agora serve a tela que cria as placas do termo,
# que precisa saber quais perfis nascem de documento e qual traz recipiente.
# Somar aba aqui NAO e o mesmo que somar no `/extrair`: aquele extrai PDF no
# fluxo de geracao de OS; este devolve metadado de configuracao, sem dado de
# cliente nenhum.
async def listar_perfis(_=Depends(requer_aba("gerar_os", "vinculos", "cadastro_placas"))):
    return {
        chave: {"label": p["label"], "os_por_placa": p["os_por_placa"],
                "agrupado": p.get("agrupado", False),
                # `sem_termo` é o que a Etapa 1 usa para esconder o campo de
                # anexo: sem documento não há o que extrair.
                "sem_termo": p.get("sem_termo", False),
                "sem_financeira": p.get("sem_financeira", False),
                "produto_servico_nome": p.get("produto_servico_nome"),
                "problema_nome": p.get("problema_nome"),
                "numero_na_descricao": p.get("numero_na_descricao", False),
                "liberar_serie": p.get("liberar_serie", False)}
        for chave, p in PERFIS.items()
    }


@router.get("/problemas")
async def listar_problemas(_=Depends(requer_aba("gerar_os"))):
    """Problemas do Harmonit para o seletor da Etapa 2 (perfis sem termo).

    Existe porque MANUTENÇÃO não é o único problema que cabe num chamado:
    `SOCORRO TECNICO` e `REINSTALAÇÃO` também são manutenção na prática, e quem
    sabe qual é quem abriu. Nos perfis de contrato o problema continua ditado
    pelo perfil -- ali oferecer escolha só convidaria erro.
    """
    lista = await _lista_do_harmonit("/Problema/ObterProblemas")
    if lista is None:
        raise HTTPException(502, "A lista de Problemas do Harmonit não respondeu.")
    return {"problemas": [{"id": p.get("id"), "descricao": p.get("descricao")}
                          for p in lista if p.get("id")]}


@router.get("/prioridades")
async def listar_prioridades(_=Depends(requer_aba("gerar_os"))):
    """Prioridades do Harmonit pro seletor da Etapa 2 (default Normal). Aplica só
    às OS operacionais -- a financeira sai sempre Normal."""
    r = await harmonit_get("/PrioridadeAtendimento/ObterPrioridades", params={"skip": 0, "take": 50})
    itens = r.get("data") if isinstance(r, dict) else r
    itens = itens or []
    return {
        "default": PRIORIDADE_NORMAL_ID,
        "prioridades": [{"id": i.get("id"), "descricao": i.get("descricao") or i.get("nome")} for i in itens],
    }


@router.post("/extrair")
async def extrair(
    perfil: str = Query(...),
    arquivo: UploadFile = File(...),
    _=Depends(requer_aba("gerar_os")),
):
    if perfil not in PERFIS:
        raise HTTPException(400, f"Perfil desconhecido: {perfil}")
    conteudo = await arquivo.read()
    try:
        campos = extrair_campos(io.BytesIO(conteudo), perfil)
    except Exception as exc:
        logger.exception("Falha ao extrair PDF")
        raise HTTPException(422, f"Não foi possível ler o PDF: {exc}")

    # Anexa o status de vínculo de cada item extraído -- o front usa isso pra
    # saber quais precisam de confirmação antes de liberar a geração.
    for item in campos.get("itens", []):
        vinc = await storage.buscar_vinculo_item(item["descricao"])
        item["vinculo"] = vinc

    return campos


@router.get("/clientes/buscar")
async def buscar_cliente(
    q: str = Query(..., min_length=3),
    _=Depends(requer_aba("gerar_os")),
):
    q_limpa = "".join(c for c in q if c.isdigit())
    if len(q_limpa) in (11, 14):
        try:
            r = await harmonit_get("/ObterClientePorCpfCnpj", params={"CpfCnpj": q_limpa})
            itens = r if isinstance(r, list) else ([r] if r else [])
            if itens:
                return {
                    "resultados": [
                        {"id": i.get("id"), "nome": i.get("nome"), "cnpjCpf": i.get("cnpJ_CPF")}
                        for i in itens
                    ]
                }
        except HTTPException:
            pass

    r = await harmonit_get("/ObterClientes", params={"skip": 0, "take": 15, "search": q})
    itens = r.get("lista") if isinstance(r, dict) else r
    itens = itens or []
    return {
        "resultados": [
            {"id": i.get("id"), "nome": i.get("nome"), "cnpjCpf": i.get("cnpJ_CPF") or i.get("cnpjCpf")}
            for i in itens
        ]
    }


@router.get("/servicos/buscar")
async def buscar_servico(
    q: str = Query("", min_length=0),
    _=Depends(requer_aba("gerar_os", "vinculos")),
):
    params = {"skip": 0, "take": 30}
    if q:
        params["search"] = q
    r = await harmonit_get("/Produto/ObterServicos", params=params)
    itens = r.get("data") if isinstance(r, dict) else r
    itens = itens or []
    return {
        "resultados": [
            {"id": i.get("id"), "descricao": i.get("descricao"), "grupo": i.get("grupo")}
            for i in itens
        ]
    }


@router.get("/produtos/buscar")
async def buscar_produto(
    q: str = Query("", min_length=0),
    _=Depends(requer_aba("gerar_os", "vinculos")),
):
    """Separado de /servicos/buscar -- tela de Vínculos precisa achar tanto
    produto quanto serviço (ex: RASTREADOR é produto; CENTRAL 24 HORAS é
    serviço), e a Harmonit expõe os dois em endpoints diferentes."""
    params = {"skip": 0, "take": 30}
    if q:
        params["search"] = q
    r = await harmonit_get("/Produto/ObterProdutos", params=params)
    itens = r.get("data") if isinstance(r, dict) else r
    itens = itens or []
    return {
        "resultados": [
            {"id": i.get("id"), "descricao": i.get("descricao"), "grupo": i.get("grupo")}
            for i in itens
        ]
    }


# ── Vínculos item-do-contrato ↔ catálogo Harmonit ───────────────────────────

class VinculoInput(BaseModel):
    nome_contrato: str
    harmonit_id: int | None = None
    harmonit_tipo: str | None = None  # 'produto' | 'servico'
    harmonit_descricao: str | None = None
    oculto: bool = False
    # O item entra TAMBÉM na OS operacional, como referência sem flag. Ver
    # `_duplicar_nas_duas`. Marcado por vínculo para não virar nome no código.
    nas_duas: bool = False


@router.get("/vinculos")
async def listar_vinculos(_=Depends(requer_aba("vinculos"))):
    return await storage.listar_vinculos_itens()


@router.post("/vinculos")
async def salvar_vinculo(body: VinculoInput, _=Depends(requer_aba("vinculos"))):
    if not body.oculto and body.harmonit_id is None:
        raise HTTPException(400, "Informe harmonit_id ou marque oculto=true")
    if body.oculto and body.nas_duas:
        # Oculto não entra em OS nenhuma; "nas duas" diz para entrar em duas.
        # Aceitar os dois juntos gravaria uma contradição que só apareceria na
        # hora de gerar, e em silêncio.
        raise HTTPException(400, "Um item não pode ser 'oculto' e 'nas duas OS' "
                                 "ao mesmo tempo — escolha um.")
    await storage.salvar_vinculo_item(
        body.nome_contrato, body.harmonit_id, body.harmonit_tipo,
        body.harmonit_descricao, body.oculto, body.nas_duas
    )
    return {"ok": True}


@router.post("/vinculos/extrair-preview")
async def extrair_preview(
    perfil: str = Query(""),
    arquivo: UploadFile = File(...),
    _=Depends(requer_aba("vinculos")),
):
    """Mesma extração do fluxo principal, mas só pra revisar/confirmar vínculos
    -- nunca gera OS a partir daqui, é o ambiente seguro que você pediu."""
    conteudo = await arquivo.read()
    try:
        campos = extrair_campos(io.BytesIO(conteudo), perfil)
    except Exception as exc:
        raise HTTPException(422, f"Não foi possível ler o PDF: {exc}")
    for item in campos.get("itens", []):
        item["vinculo"] = await storage.buscar_vinculo_item(item["descricao"])
    return campos


# ── Geração de OS ────────────────────────────────────────────────────────────

class PlacaInput(BaseModel):
    placa: str
    veiculo: str = ""
    sem_bloqueio: bool = False  # achado 2026-07-15: marca quem NÃO recebe bloqueio veicular (não é "os N primeiros")
    # -- só usados quando perfil == "substituicao" (veículo de saída != entrada) --
    placa_entrada: str | None = None
    veiculo_entrada: str = ""
    # -- só usado quando perfil == "transferencia" (mesmo veículo, cliente diferente) --
    cliente_id_destino: int | None = None


class ItemContratoInput(BaseModel):
    descricao: str
    quantidade: str | None = None
    valor_unitario: str | None = None
    comodato_ou_aquisicao: str | None = None


class GerarOsInput(BaseModel):
    perfil: str
    cliente_id: int  # cliente "principal" -- origem, no caso de Transferência
    # 🚨 DEIXOU DE SER OBRIGATORIO EM 14/08. Os perfis de manutencao nascem de
    # um chamado, nao de documento assinado -- nao ha numero de termo. Quem
    # exige o termo agora e o perfil (`sem_termo`), nao o modelo.
    termo: str = ""
    # Campo livre do painel. Vai para a OBS da OS (solucaoTecnica), ABAIXO da
    # linha de criacao -- nao entra na descricao.
    observacao: str = ""
    # Problema escolhido na tela (perfis sem termo). Vence a resolucao por nome
    # do perfil -- e o operador quem sabe se aquele chamado e MANUTENCAO,
    # SOCORRO TECNICO ou REINSTALACAO.
    problema_id: int | None = None
    termo_relacionado: str = ""  # nº do contrato do OUTRO lado (titularidade) -- vai pra descrição
    produto_servico_id: int
    placas: list[PlacaInput]
    itens: list[ItemContratoInput] = []
    solucao_tecnica: str | None = None  # contexto da extração (transferência, particularidade) -- vai pro campo solucaoTecnica
    prioridade_id: int = PRIORIDADE_NORMAL_ID  # prioridade das OS OPERACIONAIS (a financeira é sempre Normal)
    motivo_financeira_zero: str = ""  # justificativa quando a financeira sai sem custo (por conta do técnico / acordo interno / ...)
    confirmar: bool = False  # false = simula (dry-run), sem escrever no Harmonit


def _parse_valor(txt: str | None) -> float:
    if not txt:
        return 0.0
    try:
        return float(txt.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _parse_qtd(txt: str | None) -> int:
    if not txt:
        return 0
    try:
        return int(txt.strip())
    except ValueError:
        return 0


def _formatar_solucao_tecnica(contexto: str | None, observacao: str = "") -> str:
    """solucaoTecnica é o campo que o técnico preenche DEPOIS do serviço --
    não sobrescrevemos, só deixamos um cabeçalho com data + separador,
    orientando a preencher dali pra baixo. Combinado com o usuário em
    2026-07-15.

    A OBS do painel (14/08) entra ABAIXO da linha de criação e ACIMA do
    separador: é contexto de quem abriu, não resultado de quem atendeu."""
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    linhas = [f"[{agora}] Contexto da extração automática:"]
    if (contexto or "").strip():
        linhas.append(contexto.strip())
    if (observacao or "").strip():
        linhas.append(f"OBS: {observacao.strip()}")
    return "\n".join(linhas) + "\n-------------\n"


async def _resolver_vinculos(itens: list[ItemContratoInput]) -> tuple[list[dict], list[str], list[str]]:
    """Retorna (itens_resolvidos, nomes_pendentes, descartados_nao_contratado).
    Descartados (nunca viram material de OS): itens de vínculo oculto E linhas
    marcadas 'NÃO CONTRATADO' na coluna Tipo do contrato -- estas últimas voltam
    na lista de descartados para o preview avisar o operador.

    A decisão de COBRAR vem da coluna Tipo, NÃO do valor (regra do negócio,
    2026-07-20): comodato nunca cobra -- o valor da linha é patrimonial (vai pra
    DANFE de comodato), não é preço. Aquisição/serviço cobra se tiver valor.
    Assim `cobrar` e `comodato` nunca são verdadeiros ao mesmo tempo."""
    resolvidos = []
    pendentes = []
    descartados = []
    for item in itens:
        tipo = (item.comodato_ou_aquisicao or "").strip().upper()
        # 'NÃO CONTRATADO' é por LINHA do contrato (não pelo vínculo fixo oculto):
        # o mesmo item pode ser contratado em outro termo. Descarta só esta linha,
        # antes do lookup de vínculo (senão viraria 'pendente' e bloquearia a geração).
        if "NÃO CONTRATAD" in tipo or "NAO CONTRATAD" in tipo:
            descartados.append(item.descricao)
            continue
        vinc = await storage.buscar_vinculo_item(item.descricao)
        if vinc is None:
            pendentes.append(item.descricao)
            continue
        if vinc["oculto"]:
            continue
        comodato = tipo.startswith("COMODATO")
        resolvidos.append({
            "descricao": item.descricao,
            "harmonit_id": vinc["harmonit_id"],
            "quantidade": _parse_qtd(item.quantidade) or 1,
            "valor_unitario": _parse_valor(item.valor_unitario),
            "comodato": comodato,
            # comodato nunca cobra; senão cobra se a linha tem valor
            "cobrar": False if comodato else _parse_valor(item.valor_unitario) > 0,
            # marcado no vínculo: aparece também na OS operacional, sem flag
            "nas_duas": bool(vinc.get("nas_duas")),
        })
    return resolvidos, pendentes, descartados


def _alocar_itens_por_placa(itens_resolvidos: list[dict], placas: list[PlacaInput]) -> tuple[list[list[dict]], list[str]]:
    """Distribui a quantidade de cada item pelas placas, em ordem -- COM UMA
    EXCEÇÃO: item de bloqueio veicular só aloca nas placas que NÃO estão
    marcadas sem_bloqueio (achado 2026-07-15, cliente novo2.pdf: 28 veículos,
    só 11 recebem bloqueio, e a marcação de quem é está no texto do próprio
    veículo, não é 'os N primeiros da lista'). Quantidade maior que o número
    de placas elegíveis é erro (avisa, não bloqueia)."""
    n = len(placas)
    alocacao: list[list[dict]] = [[] for _ in range(n)]
    avisos: list[str] = []
    for item in itens_resolvidos:
        qtd = item["quantidade"]
        if "BLOQUEIO" in item["descricao"].upper():
            elegiveis = [i for i, p in enumerate(placas) if not p.sem_bloqueio]
        else:
            elegiveis = list(range(n))
        if qtd > len(elegiveis):
            # DOIS NIVEIS (decisao do usuario, 29/07). Rastreador e chip sao
            # 1 por placa SEMPRE: divergencia neles significa veiculo faltando
            # no termo ou item cadastrado fora do FPSL, e precisa ser conferido
            # antes de gerar. Acessorio (leitor RFID, etc.) pode legitimamente
            # ser menor que a frota -- 5 leitores para 10 veiculos e contrato
            # normal. Um aviso unico para os dois casos treinava a pessoa a
            # ignorar o alerta justamente quando ele importava.
            desc = item["descricao"].upper()
            um_por_placa = any(t in desc for t in ("RASTREADOR", "CHIP", "EQUIPAMENTO"))
            if um_por_placa:
                avisos.append(
                    f"ERRO - '{item['descricao']}': o contrato tem {qtd} e chegaram "
                    f"{len(elegiveis)} placas. Este item e 1 por veiculo, entao a "
                    "diferenca indica veiculo faltando no termo ou cadastrado fora "
                    "do FPSL. Confira ANTES de gerar."
                )
            else:
                avisos.append(
                    f"'{item['descricao']}': {qtd} para {len(elegiveis)} placas - "
                    "acessorio pode ser menor que a frota; alocado nas primeiras, "
                    "confira se sao as certas."
                )
            qtd = len(elegiveis)
        for i in elegiveis[:qtd]:
            # copia com quantidade=1 -- é a unidade alocada NESSA placa, não a
            # quantidade total do contrato (bug encontrado em teste, corrigido
            # antes de qualquer geração real usar essa lógica)
            alocacao[i].append({**item, "quantidade": 1})
    return alocacao, avisos


def _montar_operacoes(body: GerarOsInput, perfil: dict, alocacao: list[list[dict]],
                      seriais: dict[str, str] | None = None,
                      recipientes: dict | None = None,
                      dados: dict | None = None) -> list[dict]:
    """1 operação = 1 OS a criar. Perfis com os_por_placa==1 geram 1 por
    placa. Substituição (2 veículos diferentes, mesmo cliente) e Transferência
    (mesmo veículo, 2 clientes) são formas DIFERENTES de 'os_por_placa==2' --
    tratadas explicitamente, não com a mesma lógica genérica (achado
    2026-07-15: a versão anterior usava a mesma placa/cliente pras duas OS
    em ambos os casos, o que está certo pra Transferência mas errado pra
    Substituição)."""
    if perfil.get("agrupado"):
        # Transferencia de titularidade: 1 OS de retirada (cliente origem) + 1
        # OS de instalacao (cliente destino) por DOCUMENTO, juntando todas as
        # placas do termo numa descricao so -- mudanca de decisao 2026-07-16
        # (antes gerava 1 par de OS por placa).
        cliente_destino = next((p.cliente_id_destino for p in body.placas if p.cliente_id_destino), body.cliente_id)
        # 'NUMERO DE SERIE' era texto literal ate 2026-07-29 -- o encaixe
        # existia e nunca foi preenchido. E o numeroSerie do rastreador na
        # WESO (confirmado pelo usuario). Busca best-effort: WESO fora deixa
        # o marcador, nao impede a geracao. Ver painel/equipamentos.py.
        seriais = seriais or {}
        placas_txt = "; ".join(
            f"({p.placa} | {p.veiculo} | {serie_de(seriais, p.placa)})" for p in body.placas
        )
        descricao = f"{perfil['descricao_prefixo']}: {placas_txt}"
        materiais_todos = [m for lista in alocacao for m in lista]
        placas_resumo = ", ".join(p.placa for p in body.placas)
        return [
            {
                "cliente_id": body.cliente_id,
                "placa": placas_resumo, "veiculo": "",
                "tipo_id": perfil["tipo_id_retirada"],
                "problema_id": perfil.get("problema_id_retirada", perfil.get("problema_id")),
                "descricao": descricao,
                "rotulo": "Retirada (origem)",
                "materiais": [],
            },
            {
                "cliente_id": cliente_destino,
                "placa": placas_resumo, "veiculo": "",
                "tipo_id": perfil["tipo_id_instalacao"],
                "problema_id": perfil.get("problema_id_instalacao", perfil.get("problema_id")),
                "descricao": descricao,
                "rotulo": "Instalação (destino)",
                "materiais": materiais_todos,
            },
        ]

    operacoes = []
    for idx, p in enumerate(body.placas):
        materiais_placa = alocacao[idx]
        # O equipamento que a WESO diz estar/entrar nesta placa SUBSTITUI o
        # rastreador que o vínculo trouxe do texto do contrato.
        equip = _material_do_equipamento(perfil, p.placa, materiais_placa,
                                         recipientes, dados)
        materiais_placa = _substituir_rastreador(materiais_placa, equip)

        if perfil["os_por_placa"] == 1:
            # O que SAI: sempre a propria placa. Ao vivo quando ha leitura ao
            # vivo (manutencao), cache nos perfis de contrato.
            #
            # 🚨 SERIE E MODELO PRECISAM VIR DA MESMA FONTE. O ENTRARA ja vinha
            # ao vivo e o SAIRA vinha do cache das 04:15 -- num veiculo que
            # trocou de equipamento no mesmo dia (a manutencao anterior, por
            # exemplo) a OS sairia dizendo que remove uma serie que nao esta
            # mais la. Plausivel, errada e silenciosa.
            dado_placa = (dados or {}).get(_chave_placa(p.placa)) or {}
            saida = dado_placa.get("modelo")
            serie_saida = dado_placa.get("serie") or serie_de(seriais, p.placa)
            operacoes.append({
                "cliente_id": body.cliente_id,
                "placa": p.placa, "veiculo": p.veiculo,
                "tipo_id": perfil["tipo_id"], "problema_id": perfil["problema_id"],
                "descricao": perfil["descricao_template"].format(
                    placa=p.placa, veiculo=p.veiculo, termo=body.termo,
                    serie=serie_saida,
                    serie_entrada=_serie_que_entra(perfil, recipientes, p.placa),
                    modelo=_modelo_da_operacao(perfil, p.placa, materiais_placa,
                                               recipientes, dados),
                    modelo_saida=modelo_efetivo(saida or modelo_da_placa(p.placa),
                                                tem_leitor_rfid(materiais_placa))),
                "rotulo": perfil["label"],
                "materiais": materiais_placa,
            })
            continue

        if body.perfil == "substituicao":
            if not p.placa_entrada:
                raise HTTPException(400, f"Placa {p.placa}: perfil Substituição exige placa_entrada (veículo que entra).")
            operacoes.append({
                "cliente_id": body.cliente_id,
                "placa": p.placa, "veiculo": p.veiculo,
                "tipo_id": perfil["tipo_id_retirada"],
                "problema_id": perfil.get("problema_id_retirada", perfil.get("problema_id")),
                "descricao": perfil["descricao_template_retirada"].format(
                    placa=p.placa, veiculo=p.veiculo, termo=body.termo,
                    serie=serie_de(seriais, p.placa),
                    modelo=_modelo_da_operacao(perfil, p.placa, materiais_placa,
                                               recipientes, dados)),
                "rotulo": "Retirada",
                # Decisão do usuário 2026-07-23: a retirada também lista o equipamento
                # (o que é REMOVIDO do veículo antigo), com os mesmos itens da instalação.
                # Comodato/cobrar já vêm False do _resolver_vinculos (substituição não
                # tem Tipo nem valor). Mesma referência de lista das duas OS -- ninguém
                # muta os dicts (gerar_os monta um `todos_materiais` novo por OS).
                "materiais": materiais_placa,
            })
            operacoes.append({
                "cliente_id": body.cliente_id,
                "placa": p.placa_entrada, "veiculo": p.veiculo_entrada,
                "tipo_id": perfil["tipo_id_instalacao"],
                "problema_id": perfil.get("problema_id_instalacao", perfil.get("problema_id")),
                # 🚨 SÉRIE E MODELO DA MESMA PLACA. Esta linha descreve o
                # veículo que RECEBE, então lê dele -- misturar a série de um
                # com o modelo de outro produz `007933914 (modelo nao
                # localizado)`, que parece defeito e não é.
                # ⚠️ O MATERIAL continua vindo da placa que SAI: na
                # Substituição o equipamento é o MESMO e muda de veículo.
                "descricao": perfil["descricao_template_instalacao"].format(
                    placa=p.placa_entrada, veiculo=p.veiculo_entrada, termo=body.termo,
                    serie=serie_de(seriais, p.placa_entrada),
                    modelo=_modelo_da_operacao(perfil, p.placa_entrada, materiais_placa,
                                               recipientes, dados)),
                "rotulo": "Instalação",
                "materiais": materiais_placa,
            })
            continue

        raise HTTPException(500, f"Perfil '{body.perfil}' com os_por_placa==2 sem tratamento explícito nem 'agrupado'.")
    return operacoes


def _dedup_placas(placas: list[PlacaInput]) -> tuple[list[PlacaInput], list[str]]:
    """Colapsa placas repetidas, mantendo a 1ª ocorrência -- a mesma placa nunca
    deve gerar 2 OS (achado real, termo 8788: o documento listava as mesmas 3
    placas em 2 referências diferentes; gerar 2 retiradas pro mesmo veículo é
    sempre errado). Devolve (placas_unicas, avisos): o aviso lista o que foi
    colapsado pra o operador enxergar, não some em silêncio."""
    def _norm(p: PlacaInput) -> str:
        return " ".join((p.placa or "").upper().split())

    contagem = Counter(_norm(p) for p in placas if _norm(p))
    vistas: set[str] = set()
    unicas: list[PlacaInput] = []
    for p in placas:
        chave = _norm(p)
        if not chave:  # sem placa não deveria chegar aqui, mas não colapsa
            unicas.append(p)
            continue
        if chave in vistas:
            continue
        vistas.add(chave)
        unicas.append(p)

    avisos: list[str] = []
    duplicadas = {k: v for k, v in contagem.items() if v > 1}
    if duplicadas:
        detalhe = "; ".join(f"{placa} ({n}x)" for placa, n in duplicadas.items())
        avisos.append(f"Placas repetidas no termo — gerada 1 OS por placa (não duplicada): {detalhe}")
    return unicas, avisos


def _material_fixo(harmonit_id: int, descricao: str) -> dict:
    return {"harmonit_id": harmonit_id, "quantidade": 1, "valor_unitario": 0.0,
            "comodato": False, "cobrar": False, "descricao": descricao}


def _materiais_operacional(alocados: list[dict], body: "GerarOsInput") -> list[dict]:
    """Materiais finais de uma OS operacional -- WYSIWYG: o dry-run mostra o mesmo
    que é gravado no Harmonit. Ordem (SPEC financeiro×operacional, 2026-07-24):
    linha do Produto/Serviço do painel SEM flag  ->  itens alocados (comodato/
    sem-flag)  ->  ENTREGA OS (fixo em toda OS)."""
    servico = _material_fixo(body.produto_servico_id, "SERVIÇO DO CABEÇALHO (sem flag)")
    entrega = _material_fixo(ENTREGA_OS_ID, "ENTREGA OS")
    return [servico] + list(alocados) + [entrega]


def _equipamentos_agregados(body: "GerarOsInput", perfil: dict,
                            itens: list[dict]) -> list[dict]:
    """Na OS agregada (titularidade), UMA linha de equipamento por placa.

    🚨 O vínculo trazia um único item de rastreador com a quantidade do termo
    (28 unidades de "RASTREADOR" para 28 veículos), e todas viravam o mesmo
    ST310U. Agora cada veículo entra com o modelo que a WESO diz que ele tem.
    """
    equipamentos = [e for e in (_material_do_equipamento(perfil, p.placa, itens)
                                for p in body.placas) if e]
    if not equipamentos:
        return list(itens)
    return [m for m in itens if not _eh_rastreador(m)] + equipamentos


def _descricao_titularidade(perfil: dict, body: "GerarOsInput") -> str:
    """Descrição das OS de titularidade -- aponta o termo do OUTRO lado (SPEC
    2026-07-24: novo titular cita o termo anterior; antigo, o posterior) e lista
    as placas envolvidas, cada uma com o modelo real lido da WESO."""
    placas_txt = ", ".join(
        f"{p.placa} ({modelo_efetivo(modelo_da_placa(p.placa))})"
        if modelo_da_placa(p.placa) else p.placa
        for p in body.placas)
    rel = f" | termo relacionado {body.termo_relacionado}" if body.termo_relacionado else ""
    return f"{perfil['descricao_prefixo']}: TERMO {body.termo}{rel} | placas: {placas_txt}"


def _montar_novo_titular(body: "GerarOsInput", perfil: dict, itens_resolvidos: list[dict]) -> list[dict]:
    """1 OS híbrida (SPEC 2026-07-24): financeiro + comodato JUNTOS na mesma OS,
    sem split, qtd acompanhando os itens (sem alocação por placa), independe do
    nº de placas. Situação Financeiro + técnico Karla (anexado na E3). Os itens
    mantêm seus flags (comodato/cobrar) do _resolver_vinculos."""
    return [{
        "cliente_id": body.cliente_id,
        "placa": ", ".join(p.placa for p in body.placas), "veiculo": "",
        "problema_id": perfil["problema_id"],
        "situacao_id": perfil["situacao_id"],   # Financeiro
        "tecnico_id": perfil.get("tecnico_id"),  # Karla -- anexado na geração real (E3)
        "rotulo": "Novo titular (financeiro+comodato)",
        "descricao": _descricao_titularidade(perfil, body),
        "materiais": _materiais_operacional(itens_resolvidos, body),
    }]


def _montar_antigo_titular(body: "GerarOsInput", perfil: dict, itens_comodato: list[dict]) -> list[dict]:
    """1 OS (SPEC 2026-07-24): só comodato (o equipamento liberado do contrato
    antigo), SEM financeira e SEM técnico. Situação padrão (Nova sollicitação)."""
    return [{
        "cliente_id": body.cliente_id,
        "placa": ", ".join(p.placa for p in body.placas), "veiculo": "",
        "problema_id": perfil["problema_id"],
        "rotulo": "Antigo titular",
        "descricao": _descricao_titularidade(perfil, body),
        "materiais": _materiais_operacional(itens_comodato, body),
    }]


def _montar_financeira(body: "GerarOsInput", itens_todos: list[dict], itens_financeiro: list[dict]) -> dict:
    """OS financeira (1 por termo, agregada de todas as placas). Corpo = itens de
    cobrança (flag Cobrar) + ENTREGA OS. Cabeçalho FINANCEIRO, Situação Financeiro,
    técnico Karla. Descrição = termo + placas + acessórios/serviços (todos os itens,
    pra referência). Saldo 0 (sem cobrança): gera mesmo assim -- só ENTREGA OS -- e
    a descrição informa o motivo (SPEC 2026-07-24). solucaoTecnica (os nºs das OS
    operacionais) é preenchida na fase 2 da geração real."""
    placas_txt = ", ".join(p.placa for p in body.placas)
    itens_txt = "; ".join(i["descricao"] for i in itens_todos) or "—"
    descricao = f"FINANCEIRO — TERMO {body.termo} | placas: {placas_txt} | itens: {itens_txt}"
    if not itens_financeiro:
        descricao += f" | SEM CUSTO — motivo: {body.motivo_financeira_zero.strip() or '(não informado)'}"
    materiais = [dict(i) for i in itens_financeiro] + [_material_fixo(ENTREGA_OS_ID, "ENTREGA OS")]
    return {
        "cliente_id": body.cliente_id,
        "placa": "(financeira)", "veiculo": "",
        "tipo_id": TIPO_CONTRATO_ID,
        "problema_id": FINANCEIRO_PROBLEMA_ID,
        "situacao_id": SITUACAO_FINANCEIRO_ID,
        "produto_servico_id": FINANCEIRO_PRODUTO_SERVICO_ID,
        "prioridade_id": PRIORIDADE_NORMAL_ID,  # financeira sempre Normal
        "tecnico_id": FINANCEIRO_TECNICO_ID,
        "rotulo": "Financeira",
        "descricao": descricao,
        "materiais": materiais,
        "eh_financeira": True,
    }


async def _criar_uma_os(op: dict, solucao_txt: str,
                        numero_na_descricao: bool = False) -> tuple[dict, int | None]:
    """Cria 1 OS no Harmonit: cabeçalho + materiais + técnico (se houver). Devolve
    (resultado, numeroOrdem). Não levanta -- erros viram campos do resultado, pra
    uma OS que falha não derrubar as outras."""
    payload = {
        "id": 0, "empresaId": 98, "clienteId": op["cliente_id"],
        "tipoId": op["tipo_id"], "problemaId": op["problema_id"],
        "situacaoId": op["situacao_id"], "produtoServicoId": op["produto_servico_id"],
        "prioridadeId": op["prioridade_id"],
        "descricaoDetalhada": op["descricao"], "solucaoTecnica": solucao_txt,
    }
    try:
        r = await harmonit_post("/OrdemServico/SalvarOrdemServico", payload)
    except HTTPException as exc:
        return {"placa": op["placa"], "rotulo": op.get("rotulo"), "cliente_id": op["cliente_id"],
                "ok": False, "erro": exc.detail}, None
    os_id = r.get("id")
    numero = r.get("numeroOrdem")

    # 🚨 O NÚMERO DA PRÓPRIA OS NA DESCRIÇÃO custa uma SEGUNDA chamada -- por
    # isso a decisão de 14/07 foi não fazer nos perfis de contrato. Na
    # manutenção o usuário pediu igual à mão (as 14 OS abertas manualmente
    # terminam com `O.S: nnnnn`), aceitando a demora com a caixa de progresso.
    #
    # ⚠️ Regravar com `id` ATUALIZA, não duplica -- medido em 14/08 na OS de
    # teste 16755: mesmo id de volta, descrição trocada, e o número seguinte
    # continuou livre. É um save COMPLETO, então o payload vai inteiro: mandar
    # só a descrição limparia o resto.
    if numero_na_descricao and os_id and numero:
        nova = f"{op['descricao']} | O.S: {numero}"
        try:
            await harmonit_post("/OrdemServico/SalvarOrdemServico",
                                {**payload, "id": os_id, "numeroOrdem": numero,
                                 "descricaoDetalhada": nova})
            op["descricao"] = nova
        except HTTPException as exc:
            logger.warning("os %s: nao consegui gravar o numero na descricao: %s",
                           numero, exc.detail)
    materiais_ok, materiais_erro = [], []
    for mat in op["materiais"]:
        try:
            await harmonit_post("/OrdemServico/SalvarMaterialOrdemServico", {
                "id": 0, "empresaId": 98, "osId": os_id,
                "produtoId": mat["harmonit_id"], "quantidade": mat.get("quantidade", 1),
                "valor": mat["valor_unitario"], "cobrar": mat["cobrar"], "comodato": mat["comodato"],
            })
            materiais_ok.append(mat["descricao"])
        except HTTPException as exc:
            materiais_erro.append(f"{mat['descricao']}: {exc.detail}")
    tecnico_ok = None
    if op.get("tecnico_id"):
        try:
            await harmonit_post("/OrdemServico/SalvarTecnicoOrdemServico",
                                {"id": 0, "empresaId": 98, "osId": os_id, "tecnicoId": op["tecnico_id"]})
            tecnico_ok = op["tecnico_id"]
        except HTTPException as exc:
            materiais_erro.append(f"técnico {op['tecnico_id']}: {exc.detail}")
    return {
        "placa": op["placa"], "rotulo": op.get("rotulo"), "cliente_id": op["cliente_id"],
        "os_id": os_id, "numero_ordem": numero, "ok": True,
        "materiais_ok": materiais_ok, "materiais_erro": materiais_erro, "tecnico": tecnico_ok,
    }, numero


async def _lista_do_harmonit(path: str) -> list[dict] | None:
    """Lista do Harmonit, ou None quando a chamada nao respondeu.

    🚨 None E "NAO SEI", e nao autoriza recusar nada. E a diferenca entre a
    rede ter falhado e o item ter sumido do cadastro -- so a segunda justifica
    parar a geracao.
    """
    try:
        r = await harmonit_get(path, params={"empresaId": 98})
    except Exception as exc:
        logger.warning("harmonit: lista %s indisponivel: %s", path, exc)
        return None
    d = r.get("data", r) if isinstance(r, dict) else r
    if isinstance(d, dict):
        d = d.get("lista") or d.get("itens") or []
    return list(d or [])


def _achar_por_nome(lista: list[dict], nome: str) -> int | None:
    alvo = _norm_desc(nome)
    for x in lista:
        for campo in ("descricao", "nome", "titulo"):
            if x.get(campo) and _norm_desc(x[campo]) == alvo:
                return x.get("id")
    return None


async def _resolver_cabecalho_por_nome(perfil: dict) -> tuple[dict, list[str]]:
    """{tipo_id, problema_id} resolvidos pelo NOME contra a lista viva.

    🚨 ID FIXO EM CODIGO APODRECE EM SILENCIO. Medido em 14/08: das 14 OS de
    manutencao que a casa abriu na mao, 7 usam `tipo = 55` -- que nao esta
    mais na lista de tipos do Harmonit. Se o painel tivesse nascido com aquele
    numero, hoje estaria gravando um tipo morto sem ninguem perceber.

    Politica: nome some da lista -> RECUSA (e rot, precisa de decisao humana).
    Lista nao responde -> usa o `*_id` do perfil e avisa (e transiente, e
    travar a geracao por causa de rede seria pior).
    """
    alvos = (("tipo_nome", "tipo_id", "/TipoOrdemServico/ObterListaTipoOrdemServico", "Tipo"),
             ("problema_nome", "problema_id", "/Problema/ObterProblemas", "Problema"))
    resolvido: dict[str, int] = {}
    avisos: list[str] = []
    for chave_nome, chave_id, path, rotulo in alvos:
        nome = perfil.get(chave_nome)
        if not nome:
            continue
        lista = await _lista_do_harmonit(path)
        if lista is None:
            resolvido[chave_id] = perfil.get(chave_id)
            avisos.append(f"A lista de {rotulo} do Harmonit nao respondeu — usei o "
                          f"ultimo id conhecido para {nome!r}. Confira a OS gerada.")
            continue
        achado = _achar_por_nome(lista, nome)
        if achado is None:
            raise HTTPException(
                400,
                f"{rotulo} {nome!r} nao existe mais na lista do Harmonit. Alguem "
                f"renomeou ou removeu o cadastro — escolha o novo antes de gerar, "
                f"em vez de eu mandar um id velho.")
        resolvido[chave_id] = achado
    return resolvido, avisos


def _duplicar_nas_duas(itens_resolvidos: list[dict], n_placas: int) -> list[dict]:
    """Copia, para a OS operacional, os itens marcados `nas_duas` no vinculo.

    🚨 O ITEM CONTINUA COBRANDO NA FINANCEIRA -- aqui e so a copia de
    referencia. Por isso a copia vai SEM flag nenhuma e com valor ZERO: um
    item que nao e comodato nem cobranca carregando preco e um numero que
    alguem vai somar em algum relatorio, e o valor ja esta contado na
    financeira. Decisao do usuario, 14/08.

    🚨 A QUANTIDADE DA COPIA E O NUMERO DE PLACAS, NAO A DO CONTRATO.
    Regra do usuario: "um aditivo de 100 placas tera o central em todos os
    veiculos". A alocacao normal distribui pela quantidade contratada -- e um
    termo que lista a Central como UMA linha faria a copia chegar em UM
    veiculo, com os outros 99 sem nada e sem aviso. Medido em 14/08: qtd 1
    para 100 placas chegava em 1. A cobranca na financeira continua com a
    quantidade do contrato; so a copia de referencia e forcada a cobrir a
    frota.
    """
    return [{**i, "comodato": False, "cobrar": False, "valor_unitario": 0.0,
             "quantidade": max(int(n_placas), 1)}
            for i in itens_resolvidos if i.get("nas_duas") and i.get("cobrar")]


@router.post("/gerar-os")
async def gerar_os(body: GerarOsInput, _=Depends(requer_aba("gerar_os"))):
    perfil = PERFIS.get(body.perfil)
    if not perfil:
        raise HTTPException(400, f"Perfil desconhecido: {body.perfil}")
    if not body.placas:
        raise HTTPException(400, "Nenhuma placa informada")
    # Quem exige o termo e o perfil, nao o modelo: manutencao nasce de chamado.
    if not perfil.get("sem_termo") and not (body.termo or "").strip():
        raise HTTPException(400, f"O perfil {perfil['label']!r} exige o numero do termo.")
    if perfil.get("sem_termo") and len(body.placas) > 1:
        # Decisao do usuario (14/08): manutencao e uma placa por geracao.
        raise HTTPException(400, "Manutenção é uma placa por geração — "
                                 "gere uma OS para cada veículo.")

    # Placa repetida no termo -> 1 OS só + aviso (decisão do usuário 2026-07-23).
    body.placas, avisos_dup = _dedup_placas(body.placas)

    itens_resolvidos, pendentes, descartados = await _resolver_vinculos(body.itens)
    if pendentes:
        raise HTTPException(
            409,
            {"tipo": "vinculos_pendentes", "itens": pendentes,
             "mensagem": "Existem itens do contrato sem vínculo com o catálogo Harmonit. Vincule-os antes de gerar."},
        )

    avisos = list(avisos_dup)
    if descartados:
        avisos.append(f"Itens ignorados (não contratados, fora da OS): {', '.join(descartados)}")

    # E5 (SPEC 2026-07-24) -- Transferência de titularidade foge da arquitetura
    # de financeira separada:
    #   novo titular  -> 1 OS híbrida (financeiro + comodato JUNTOS, sem split);
    #   antigo titular -> 1 OS só comodato, SEM financeira.
    # Os demais perfis seguem o split da E2 (operacional × financeira).
    financeira = None
    recipientes: dict = {}   # só o caminho padrão preenche; titularidade não usa
    titularidade = perfil.get("titularidade")
    if titularidade == "novo":
        operacoes = _montar_novo_titular(
            body, perfil, _equipamentos_agregados(body, perfil, itens_resolvidos))
    elif titularidade == "antigo":
        # Antigo titular (decisao do usuario, 2026-07-29): gera tudo numa OS
        # so, com TODOS os itens do termo, e SEM flegar financeiro nem
        # comodato -- so insere. O contrato antigo esta encerrando; quem
        # assume comodato e cobranca e o novo titular, na OS dele. Antes daqui
        # o codigo filtrava so os itens de comodato e mantinha os flags.
        itens_sem_flag = [{**i, "cobrar": False, "comodato": False}
                          for i in _equipamentos_agregados(body, perfil, itens_resolvidos)]
        operacoes = _montar_antigo_titular(body, perfil, itens_sem_flag)
    else:
        # E2: split -- operacional = não-cobrança (comodato + sem-flag); cobrança
        # alimenta a financeira. E3: a financeira é montada aqui (1 por termo).
        if perfil.get("financeira_embutida"):
            # Rescisao: TUDO vai por placa, cobranca inclusive. A flag `cobrar`
            # de cada item e preservada, entao o Harmonit continua sabendo o
            # que cobrar -- muda so ONDE. Sem financeira agregada.
            itens_operacional = list(itens_resolvidos)
            itens_financeiro = []
        elif perfil.get("sem_flags"):
            # Manutencao: nenhum item flega cobrar nem comodato, e nao ha
            # financeira. Decisao do usuario, 14/08.
            itens_operacional = [{**i, "cobrar": False, "comodato": False}
                                 for i in itens_resolvidos]
            itens_financeiro = []
        else:
            itens_operacional = [i for i in itens_resolvidos if not i["cobrar"]]
            itens_financeiro = [i for i in itens_resolvidos if i["cobrar"]]
            # Item marcado `nas_duas` no vinculo aparece TAMBEM na operacional,
            # como referencia sem flag -- continua cobrando na financeira.
            itens_operacional = itens_operacional + _duplicar_nas_duas(
                itens_resolvidos, len(body.placas))
        alocacao, avisos_aloc = _alocar_itens_por_placa(itens_operacional, body.placas)
        avisos += avisos_aloc
        # Serial do rastreador para a descricao. Best-effort e fora do
        # caminho critico: falha aqui nao impede a OS.
        # Serial do rastreador para a descricao, em TODOS os perfis -- ate
        # 29/07 so o agrupado preenchia, e os templates por placa mandavam o
        # literal 'NUMERO DE SERIE' para a OS. Best-effort: WESO/cache fora
        # deixa o marcador e nao impede a geracao.
        # 🚨 O QUE A WESO DEIXOU DE RESPONDER VIRA AVISO NA TELA. Antes ficava
        # so no journal, e a OS saia sem equipamento sem ninguem notar -- foi
        # assim que nasceu a 16775. Ver `_anotar` em `equipamentos.py`.
        falhas_weso: list[str] = []
        todas = [p.placa for p in body.placas]
        todas += [p.placa_entrada for p in body.placas if getattr(p, "placa_entrada", None)]
        # Upgrade: a serie do equipamento que ENTRA vive na placa-recipiente de
        # teste (`OOM4131-UPGRADE`). Ela entra aqui SO para a busca resolver --
        # nao vira veiculo de OS nenhuma.
        # 🚨 NA MANUTENCAO O RECIPIENTE NAO ENTRA AQUI. A leitura ao vivo logo
        # abaixo ja traz serie e modelo dele; pedir tambem ao `buscar_seriais`
        # fazia uma SEGUNDA varredura da base inteira da WESO (16 a 30s), que
        # somada as demais estourava o `proxy_read_timeout` de 35s do nginx.
        # No upgrade continua entrando: la nao ha leitura ao vivo.
        if perfil.get("placa_teste_sufixo") and not perfil.get("sem_termo"):
            todas += [placa_teste(p.placa, perfil["placa_teste_sufixo"]) for p in body.placas]
        seriais = await buscar_seriais(todas, falhas_weso)

        # 🚨 MANUTENCAO LE AO VIVO. O recipiente nasce minutos antes da OS e o
        # cache local so atualiza as 04:15 -- ler do cache aqui devolveria
        # "modelo nao localizado" para equipamento que existe. Nos perfis de
        # contrato o cache continua valendo: o termo demora dias, e 2,3s de
        # rede por geracao nao se paga.
        dados_ao_vivo: dict = {}
        recipientes: dict = {}
        if perfil.get("sem_termo"):
            # 🚨 UMA LEITURA SÓ, para a placa real E o recipiente juntos. Antes
            # eram duas chamadas independentes, e cada uma que não achasse pela
            # consulta exata caía na base inteira -- 16,65s cada. Uma geração de
            # manutenção com recipiente ainda não criado levava 43s, perto do
            # teto do nginx. Foi o erro que a Erika viu em 14/08.
            sufixo = perfil.get("placa_teste_sufixo")
            alvos = [p.placa for p in body.placas]
            if sufixo:
                alvos += [placa_teste(p.placa, sufixo) for p in body.placas]
            lidos = await dados_das_placas(alvos, falhas_weso)
            for p in body.placas:
                chave = _chave_placa(p.placa)
                if lidos.get(chave):
                    dados_ao_vivo[chave] = lidos[chave]
                if sufixo and lidos.get(chave_recipiente(p.placa, sufixo)):
                    recipientes[chave] = lidos[chave_recipiente(p.placa, sufixo)]
        if perfil.get("placa_teste_sufixo"):
            if perfil.get("sem_termo"):
                pass  # já resolvido acima, na leitura única
            else:
                # Upgrade: o recipiente e criado junto com o termo, entao o
                # cache basta -- monta o mesmo formato a partir dele.
                for p in body.placas:
                    pt = placa_teste(p.placa, perfil["placa_teste_sufixo"])
                    recipientes[_chave_placa(p.placa)] = {
                        "descricao": descricao_da_placa(pt),
                        "modelo": modelo_da_placa(pt),
                        "serie": serie_de(seriais, pt)
                        if serie_de(seriais, pt) != MARCADOR_NAO_LOCALIZADO else None,
                    }
        avisos += falhas_weso
        recipientes, avisos_rec = _conferir_recipientes(body, perfil, recipientes)
        avisos += avisos_rec

        operacoes = _montar_operacoes(body, perfil, alocacao, seriais,
                                      recipientes, dados_ao_vivo)
        for op in operacoes:
            # Materiais finais: serviço do cabeçalho (sem flag) + alocados +
            # ENTREGA OS. Substitui a lista só-alocada -> dry-run == real.
            op["materiais"] = _materiais_operacional(op["materiais"], body)
        # Financeira sempre nos perfis padrão (mesmo saldo 0 -> motivo na descrição).
        # Manutenção não gera nenhuma: sem termo não há item de cobrança, e uma
        # financeira zerada por manutenção só criaria papel (decisão 14/08).
        if not perfil.get("financeira_embutida") and not perfil.get("sem_financeira"):
            financeira = _montar_financeira(body, itens_resolvidos, itens_financeiro)
        # Cobranca zerada exige motivo -- vale nos DOIS caminhos. Com a
        # financeira embutida (rescisao) `itens_financeiro` fica sempre vazio
        # por construcao, entao a checagem antiga (`not itens_financeiro`)
        # deixaria de valer justo onde mais importa: no termo 8788 a TAXA DE
        # RETIRADA vem riscada, valendo R$ 0,00. Agora olha os itens de
        # cobranca de verdade e o valor deles.
        cobrancas = [i for i in itens_resolvidos if i.get("cobrar")]
        sem_valor = (not cobrancas) or all(
            float(i.get("valor_unitario") or 0) == 0 for i in cobrancas
        )
        if (sem_valor and not perfil.get("sem_financeira")
                and not body.motivo_financeira_zero.strip()):
            avisos.append("Cobrança sem valor (saldo 0) e sem motivo informado — "
                          "preencha o motivo (mudança de gestão, acordo interno, etc.) antes de gerar.")

    # E1: Tipo é sempre Contrato NOS PERFIS DE CONTRATO; situação padrão Nova
    # sollicitação e produto do painel (o novo titular/financeira já trazem os
    # seus -> setdefault preserva).
    #
    # 🚨 A MANUTENÇÃO FOGE DAQUI. Ela não vem de contrato: o Tipo dela é
    # resolvido pelo NOME contra a lista viva do Harmonit (decisão 14/08), e
    # forçar Contrato aqui apagaria essa resolução em silêncio.
    cabecalho, avisos_cab = ({}, [])
    if perfil.get("tipo_nome") or perfil.get("problema_nome"):
        cabecalho, avisos_cab = await _resolver_cabecalho_por_nome(perfil)
        avisos += avisos_cab
    for op in operacoes:
        op["tipo_id"] = cabecalho.get("tipo_id") or (
            op.get("tipo_id") if perfil.get("tipo_nome") else TIPO_CONTRATO_ID)
        if cabecalho.get("problema_id"):
            op["problema_id"] = cabecalho["problema_id"]
        # A escolha da tela vence o padrão do perfil (só os perfis sem termo
        # mostram o seletor -- num contrato o problema é ditado pelo documento).
        if body.problema_id and perfil.get("sem_termo"):
            op["problema_id"] = body.problema_id
        op.setdefault("situacao_id", SITUACAO_NOVA_ID)
        op.setdefault("produto_servico_id", body.produto_servico_id)
        op["prioridade_id"] = body.prioridade_id  # OPs usam a prioridade do painel (financeira já traz Normal)
    solucao_tecnica_txt = _formatar_solucao_tecnica(body.solucao_tecnica, body.observacao)

    # Lista pra exibição/contagem: operacionais + financeira (por último).
    todas = operacoes + ([financeira] if financeira else [])

    if not body.confirmar:
        fin_preview = None
        if financeira:
            fin_preview = f"[após gerar] {len(operacoes)} OS operacional(is) geradas -- os números entram aqui na geração real."
        return {"simulado": True, "total_os": len(todas), "operacoes": todas,
                "avisos": avisos, "solucao_tecnica_preview": solucao_tecnica_txt,
                "financeira_solucao_preview": fin_preview}

    # === Geração real: FASE DUPLA (SPEC 2026-07-24) ===
    # Fase 1: operacionais primeiro, colhendo os números. Fase 2: a financeira,
    # citando esses números na solução técnica. Assim a financeira aponta as OS
    # de instalação/serviço geradas pelo mesmo termo.
    criadas = []
    numeros_operacionais = []
    for op in operacoes:
        resultado, numero = await _criar_uma_os(
            op, solucao_tecnica_txt, bool(perfil.get("numero_na_descricao")))
        criadas.append(resultado)
        if numero:
            numeros_operacionais.append(str(numero))

    if financeira:
        nums = ", ".join(f"nº {n}" for n in numeros_operacionais) or "(nenhuma)"
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        solucao_fin = f"[{agora}] {len(numeros_operacionais)} OS de instalação/serviço geradas neste termo: {nums}"
        resultado_fin, _num = await _criar_uma_os(financeira, solucao_fin)
        criadas.append(resultado_fin)

    liberacoes = await _liberar_series(perfil, operacoes, criadas, recipientes)

    return {"simulado": False, "total_os": len(todas), "resultados": criadas,
            "avisos": avisos, "liberacoes": liberacoes}


async def _liberar_series(perfil: dict, operacoes: list[dict], criadas: list[dict],
                          recipientes: dict) -> list[dict]:
    """Devolve ao estoque a serie de cada recipiente usado, e apaga o recipiente.

    🚨 SO DEPOIS DE TUDO CERTO (condicao do usuario, 14/08). Tres provas, e as
    tres precisam valer:
      1. a OS foi criada (`ok`)
      2. a serie ESTA na descricao -- se saiu `NUMERO DE SERIE`, nao houve
         equipamento nenhum e nao ha o que liberar
      3. o material do equipamento foi mesmo anexado (`materiais_ok`)

    Falhou qualquer uma, o recipiente fica onde esta. E melhor sobrar um
    recipiente do que liberar a serie de uma OS que nasceu incompleta.
    """
    if not perfil.get("liberar_serie") or not recipientes:
        return []
    resultados = []
    for op, criada in zip(operacoes, criadas):
        rec = recipientes.get(_chave_placa(op.get("placa", "")))
        if not rec:
            continue
        equipamentos = [m for m in op.get("materiais") or [] if m.get("_equipamento")]
        if not criada.get("ok"):
            motivo = "a OS não foi criada"
        elif MARCADOR_SERIE_A_PREENCHER in str(op.get("descricao") or ""):
            motivo = "a descrição saiu sem o número de série"
        elif not equipamentos:
            motivo = "o equipamento não entrou nos materiais"
        elif any(e["descricao"] not in (criada.get("materiais_ok") or [])
                 for e in equipamentos):
            motivo = "o equipamento não foi aceito pelo Harmonit"
        else:
            motivo = None
        if motivo:
            resultados.append({"placa": op.get("placa"), "ok": False,
                               "erro": f"equipamento NÃO liberado: {motivo}",
                               "passos": [], "dados_para_correcao": {
                                   "veiculo_id": rec.get("veiculo_id"),
                                   "rastreador_id": rec.get("rastreador_id")}})
            continue
        r = await liberar_recipiente(rec.get("veiculo_id"), rec.get("rastreador_id"))
        r["placa"] = op.get("placa")
        resultados.append(r)
    return resultados


def _serie_que_entra(perfil: dict, recipientes: dict, placa: str) -> str:
    """Serie do equipamento que ENTRA, vinda do recipiente ja conferido.

    Vazio nos perfis que nao usam recipiente -- `str.format` ignora chave que
    o template nao cita, entao passar sempre e mais simples que ramificar.

    🚨 Sem recipiente confiavel sai `NUMERO DE SERIE`, para o tecnico escrever
    na instalacao -- e nao o marcador de "nao localizada", que significa outra
    coisa (ver equipamentos.MARCADOR_SERIE_A_PREENCHER).
    """
    if not perfil.get("placa_teste_sufixo"):
        return ""
    d = (recipientes or {}).get(_chave_placa(placa)) or {}
    return d.get("serie") or MARCADOR_SERIE_A_PREENCHER


def _norm_desc(t: str) -> str:
    """Texto comparavel: espaco colapsado, caixa alta e SEM ACENTO.

    🚨 O ACENTO QUASE DERRUBOU A MANUTENCAO INTEIRA. Os 5 recipientes `-MANUT`
    da WESO estao gravados `MANUTENCAO`, sem cedilha e sem til; o usuario
    padroniza escrevendo `MANUTENÇÃO`. Sem dobrar acento aqui, os dois nunca
    casariam e TODA geracao de manutencao morreria em HTTP 400 -- com uma
    mensagem falando de upgrade anterior, que nao tem nada a ver.
    """
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def _conferir_recipientes(body, perfil: dict, recipientes: dict) -> tuple[dict, list[str]]:
    """Separa os recipientes CONFIAVEIS dos demais, e avisa sobre cada descarte.

    🚨 SEM ENTRARA PLAUSIVEL, NAO INVENTA (decisao do usuario, 14/08). Ate esta
    data o upgrade derrubava a geracao com HTTP 400 quando o recipiente nao
    batia. Agora o recipiente duvidoso e simplesmente DESCARTADO: a descricao
    sai com `NUMERO DE SERIE` para o tecnico preencher e o equipamento NAO
    entra nos materiais. O resultado e o mesmo -- nenhum dado errado entra --
    sem travar quem esta tentando trabalhar.

    ⚠️ TODO DESCARTE VIRA AVISO NA TELA. Recipiente ignorado em silencio seria
    pior que o 400: a OS pareceria completa e sairia sem o equipamento, que e
    exatamente o defeito que o usuario achou auditando o termo 8820.

    Quatro motivos de descarte, cada um com o seu texto:
      ausente ....... o setor de configuracao ainda nao criou o recipiente
      ambiguo ....... duas placas da WESO normalizam para a mesma chave
      divergente .... a descricao nao e a esperada (upgrade de outro termo)
      sem serie ..... o recipiente existe mas nao tem rastreador vinculado
    """
    sufixo = perfil.get("placa_teste_sufixo")
    if not sufixo:
        return {}, []
    modelo = perfil.get("placa_teste_descricao") or "TERMO {termo}"
    esperado = modelo.format(termo=body.termo or "")
    bons: dict[str, dict] = {}
    avisos: list[str] = []
    for p in body.placas:
        chave = _chave_placa(p.placa)
        pt = placa_teste(p.placa, sufixo)
        dado = recipientes.get(chave)
        if not dado:
            avisos.append(
                f"Placa {p.placa}: o recipiente {pt} nao existe na WESO. A OS sai "
                f"com '{MARCADOR_SERIE_A_PREENCHER}' e SEM o equipamento nos "
                f"materiais -- peca ao setor de configuracao para vincular.")
            continue
        if dado.get("ambiguo"):
            avisos.append(
                f"Placa {p.placa}: mais de um recipiente na WESO casa com {pt} "
                f"({', '.join(str(x) for x in dado['ambiguo'])}). Ambiguidade nao "
                f"se resolve por escolha automatica -- a OS sai sem o equipamento.")
            continue
        achado = dado.get("descricao")
        if achado is not None and _norm_desc(achado) != _norm_desc(esperado):
            avisos.append(
                f"Placa {p.placa}: o recipiente {pt} esta descrito como {achado!r}, "
                f"e o esperado e {esperado!r} -- provavelmente e o recipiente de "
                f"uma rodada ANTERIOR desta placa. A OS sai sem o equipamento.")
            continue
        if not dado.get("serie"):
            avisos.append(
                f"Placa {p.placa}: o recipiente {pt} existe mas nao tem rastreador "
                f"vinculado. A OS sai com '{MARCADOR_SERIE_A_PREENCHER}'.")
            continue
        bons[chave] = dado
    return bons, avisos


def _modelo_da_operacao(perfil: dict, placa: str, materiais: list[dict],
                        recipientes: dict | None = None,
                        dados: dict | None = None) -> str:
    """Modelo do rastreador para a descricao da OS, lido da WESO.

    🚨 IGNORA O VINCULO PARA ESTE ITEM, por decisao do usuario (13/08): o
    vinculo diz o que o TERMO escreveu, a WESO diz o que ESTA no veiculo.

    Qual placa se le depende do perfil:
      upgrade / manutencao com troca ... o recipiente (o que ENTRARA)
      manutencao no local / demais ..... a propria placa (o que ESTIVER)

    ⚠️ Cliente novo nao tem o que ler -- e instalacao nova, o veiculo ainda nao
    existe na WESO. Ali o marcador aparece, e e honesto: nao ha equipamento.
    """
    origem = perfil.get("modelo_origem")
    if origem == "placa_teste" and perfil.get("placa_teste_sufixo"):
        # So recipiente CONFERIDO chega aqui -- o duvidoso ja foi descartado em
        # `_conferir_recipientes`, com aviso. Nada de reler a WESO por dentro.
        d = (recipientes or {}).get(_chave_placa(placa)) or {}
        bruto = d.get("modelo")
    else:
        # Leitura ao vivo quando ela existe (manutencao), cache quando nao
        # (perfis de contrato, que nao pagam por 2,3s de rede a toa).
        d = (dados or {}).get(_chave_placa(placa)) or {}
        bruto = d.get("modelo") or modelo_da_placa(placa)
    return modelo_efetivo(bruto, tem_leitor_rfid(materiais))


# 🚨 O EQUIPAMENTO E MATERIAL, NAO SO TEXTO. Ate 13/08 o modelo resolvido na
# WESO ia apenas para a descricao da OS, e o material saia so com o servico do
# cabecalho + ENTREGA OS -- foi o que o usuario achou auditando o termo 8820.
_MARCA_RASTREADOR = ("RASTREADOR", "EQUIPAMENTO RASTREADOR")


def _eh_rastreador(material: dict) -> bool:
    """Este material e o equipamento (e nao acessorio, servico ou taxa)?"""
    d = str(material.get("descricao") or "").upper()
    return any(marca in d for marca in _MARCA_RASTREADOR)


def _ja_tem_rastreador(materiais: list[dict]) -> bool:
    """O termo ja trouxe um item de rastreador (via vinculo)?"""
    return any(_eh_rastreador(m) for m in materiais or [])


def _substituir_rastreador(materiais: list[dict], equip: dict | None) -> list[dict]:
    """Troca o rastreador que veio do VINCULO pelo que a WESO diz estar no veiculo.

    🚨 O VINCULO DIZ O QUE O VENDEDOR ESCREVEU, A WESO DIZ O QUE ESTA LA. O
    vinculo mapeia TEXTO do termo para produto fixo: "RASTREADOR" cai sempre em
    ST310U, "RASTREADOR 4G" sempre em XT40 -- dois modelos para os 20+ que a
    WESO tem em uso. Um veiculo com ST340 gerava OS dizendo ST310U.

    ⚠️ Sem equipamento resolvido, NAO mexe: devolve a lista como estava. Apagar
    o item do contrato e nao pôr nada no lugar seria pior que a imprecisao.
    """
    if not equip:
        return list(materiais or [])
    restantes = [m for m in materiais or [] if not _eh_rastreador(m)]
    return restantes + [equip]


def _material_do_equipamento(perfil: dict, placa: str, materiais: list[dict],
                             recipientes: dict | None = None,
                             dados: dict | None = None) -> dict | None:
    """Material do equipamento que a WESO diz estar (ou entrar) nesta placa.

    ⚠️ COMODATO, NUNCA COBRA -- nos perfis de CONTRATO. O valor e PATRIMONIAL,
    vai para a DANFE de comodato e nao e preco. Mesma regra que
    `_resolver_vinculos` aplica: comodato e cobrar nunca sao verdadeiros ao
    mesmo tempo.

    🚨 MANUTENCAO NAO FLEGA NADA (decisao do usuario, 14/08, `sem_flags`).
    Ali o equipamento nao esta saindo do patrimonio nem sendo vendido: ele
    aparece para o tecnico saber com o que vai lidar e qual pegar. Flegar
    comodato numa manutencao emitiria patrimonio que ja esta com o cliente.

    🚨 SUBSTITUI O ITEM DO VINCULO (decisao do usuario, 14/08). Ate aqui, se o
    termo ja tivesse listado um rastreador, este material era descartado para
    nao duplicar -- e a OS saia com o que o VENDEDOR escreveu no contrato
    ("RASTREADOR" cai sempre em ST310U) em vez do que esta no veiculo. Agora a
    WESO manda: o item do vinculo sai e este entra. Vale para os 9 perfis.

    ⚠️ O VEICULO JA EXISTE NA WESO quando a OS e gerada -- inclusive em Cliente
    novo e Aditivo (confirmado pelo usuario): "se chegou para fazer OS e porque
    o equipamento ja esta na WESO". Se ainda assim nao houver modelo, nada e
    substituido e o item do vinculo fica -- lacuna e melhor que apagar.
    """
    if not perfil.get("modelo_origem"):
        return None
    modelo = _modelo_da_operacao(perfil, placa, materiais, recipientes, dados)
    prod = storage.produto_do_modelo(modelo)
    if not prod:
        logger.info("equipamento: modelo %r sem produto no de-para -- fica so na descricao", modelo)
        return None
    sem_flags = bool(perfil.get("sem_flags"))
    # ⚠️ O de-para so tem valor patrimonial nos modelos 4G; nos 2G e None. Ao
    # substituir, herda o valor do item do contrato que esta saindo -- senao a
    # OS trocaria um valor patrimonial real por vazio.
    # 🚨 ZERO AQUI E "NAO SEI", NAO "VALE NADA". `produto_do_modelo` devolve
    # `row[2] or 0.0`, entao o de-para sem valor chega como 0.0 e nao como
    # None -- testar `is not None` nunca herdava nada, e o comodato saia
    # zerado. Achado em 14/08 ensaiando a Substituicao: o ST310U saiu com
    # R$ 0,00 enquanto o contrato dizia R$ 1.100,00.
    substituidos = [m for m in materiais or [] if _eh_rastreador(m)]
    herdado = next((m.get("valor_unitario") for m in substituidos
                    if m.get("valor_unitario")), 0.0)
    valor = prod["valor"] or herdado
    return {"harmonit_id": prod["harmonit_id"], "quantidade": 1,
            "valor_unitario": 0.0 if sem_flags else (valor or 0.0),
            "comodato": not sem_flags, "cobrar": False,
            "descricao": prod["descricao"],
            # Marca interna: e por ela que a liberacao da serie confirma que o
            # equipamento REALMENTE foi anexado antes de apagar o recipiente.
            # `_criar_uma_os` so le as chaves que o Harmonit espera, entao esta
            # sobra nao viaja no payload.
            "_equipamento": True}
