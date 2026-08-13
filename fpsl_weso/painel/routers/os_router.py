"""Rotas do painel de geração de OS por contrato."""
import re
import io
import logging
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
from ..equipamentos import (buscar_seriais, descricao_da_placa,
                            modelo_da_placa, modelo_efetivo, placa_teste,
                            serie_de, tem_leitor_rfid)
from ...harmonit_client import harmonit_get, harmonit_post
from ... import storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/painel/api", tags=["painel"])


@router.get("/perfis")
async def listar_perfis(_=Depends(requer_aba("gerar_os", "vinculos"))):
    return {
        chave: {"label": p["label"], "os_por_placa": p["os_por_placa"], "agrupado": p.get("agrupado", False)}
        for chave, p in PERFIS.items()
    }


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


@router.get("/vinculos")
async def listar_vinculos(_=Depends(requer_aba("vinculos"))):
    return await storage.listar_vinculos_itens()


@router.post("/vinculos")
async def salvar_vinculo(body: VinculoInput, _=Depends(requer_aba("vinculos"))):
    if not body.oculto and body.harmonit_id is None:
        raise HTTPException(400, "Informe harmonit_id ou marque oculto=true")
    await storage.salvar_vinculo_item(
        body.nome_contrato, body.harmonit_id, body.harmonit_tipo, body.harmonit_descricao, body.oculto
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
    termo: str
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


def _formatar_solucao_tecnica(contexto: str | None) -> str:
    """solucaoTecnica é o campo que o técnico preenche DEPOIS do serviço --
    não sobrescrevemos, só deixamos um cabeçalho com data + separador,
    orientando a preencher dali pra baixo. Combinado com o usuário em
    2026-07-15."""
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    linha_contexto = (contexto or "").strip()
    if linha_contexto:
        return f"[{agora}] Contexto da extração automática:\n{linha_contexto}\n-------------\n"
    return f"[{agora}] Contexto da extração automática:\n-------------\n"


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
                      seriais: dict[str, str] | None = None) -> list[dict]:
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
        # O equipamento que a WESO diz estar/entrar nesta placa vira material.
        equip = _material_do_equipamento(perfil, p.placa, materiais_placa)
        if equip:
            materiais_placa = list(materiais_placa) + [equip]

        if perfil["os_por_placa"] == 1:
            operacoes.append({
                "cliente_id": body.cliente_id,
                "placa": p.placa, "veiculo": p.veiculo,
                "tipo_id": perfil["tipo_id"], "problema_id": perfil["problema_id"],
                "descricao": perfil["descricao_template"].format(
                    placa=p.placa, veiculo=p.veiculo, termo=body.termo,
                    serie=serie_de(seriais, p.placa),
                    serie_entrada=_serie_que_entra(perfil, seriais, p.placa),
                    modelo=_modelo_da_operacao(perfil, p.placa, materiais_placa),
                    modelo_saida=modelo_efetivo(modelo_da_placa(p.placa),
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
                "descricao": perfil["descricao_template_retirada"].format(placa=p.placa, veiculo=p.veiculo, termo=body.termo, serie=serie_de(seriais, p.placa)),
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
                "descricao": perfil["descricao_template_instalacao"].format(placa=p.placa_entrada, veiculo=p.veiculo_entrada, termo=body.termo, serie=serie_de(seriais, p.placa_entrada)),
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


def _descricao_titularidade(perfil: dict, body: "GerarOsInput") -> str:
    """Descrição das OS de titularidade -- aponta o termo do OUTRO lado (SPEC
    2026-07-24: novo titular cita o termo anterior; antigo, o posterior) e lista
    as placas envolvidas."""
    placas_txt = ", ".join(p.placa for p in body.placas)
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


async def _criar_uma_os(op: dict, solucao_txt: str) -> tuple[dict, int | None]:
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


@router.post("/gerar-os")
async def gerar_os(body: GerarOsInput, _=Depends(requer_aba("gerar_os"))):
    perfil = PERFIS.get(body.perfil)
    if not perfil:
        raise HTTPException(400, f"Perfil desconhecido: {body.perfil}")
    if not body.placas:
        raise HTTPException(400, "Nenhuma placa informada")

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
    titularidade = perfil.get("titularidade")
    if titularidade == "novo":
        operacoes = _montar_novo_titular(body, perfil, itens_resolvidos)
    elif titularidade == "antigo":
        # Antigo titular (decisao do usuario, 2026-07-29): gera tudo numa OS
        # so, com TODOS os itens do termo, e SEM flegar financeiro nem
        # comodato -- so insere. O contrato antigo esta encerrando; quem
        # assume comodato e cobranca e o novo titular, na OS dele. Antes daqui
        # o codigo filtrava so os itens de comodato e mantinha os flags.
        itens_sem_flag = [{**i, "cobrar": False, "comodato": False}
                          for i in itens_resolvidos]
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
        else:
            itens_operacional = [i for i in itens_resolvidos if not i["cobrar"]]
            itens_financeiro = [i for i in itens_resolvidos if i["cobrar"]]
        alocacao, avisos_aloc = _alocar_itens_por_placa(itens_operacional, body.placas)
        avisos += avisos_aloc
        # Serial do rastreador para a descricao. Best-effort e fora do
        # caminho critico: falha aqui nao impede a OS.
        # Serial do rastreador para a descricao, em TODOS os perfis -- ate
        # 29/07 so o agrupado preenchia, e os templates por placa mandavam o
        # literal 'NUMERO DE SERIE' para a OS. Best-effort: WESO/cache fora
        # deixa o marcador e nao impede a geracao.
        todas = [p.placa for p in body.placas]
        todas += [p.placa_entrada for p in body.placas if getattr(p, "placa_entrada", None)]
        # Upgrade: a serie do equipamento que ENTRA vive na placa-recipiente de
        # teste (`OOM4131-UPGRADE`). Ela entra aqui SO para a busca resolver --
        # nao vira veiculo de OS nenhuma.
        if perfil.get("placa_teste_sufixo"):
            todas += [placa_teste(p.placa, perfil["placa_teste_sufixo"]) for p in body.placas]
        seriais = await buscar_seriais(todas)
        _conferir_placas_teste(body, perfil)
        operacoes = _montar_operacoes(body, perfil, alocacao, seriais)
        for op in operacoes:
            # Materiais finais: serviço do cabeçalho (sem flag) + alocados +
            # ENTREGA OS. Substitui a lista só-alocada -> dry-run == real.
            op["materiais"] = _materiais_operacional(op["materiais"], body)
        # Financeira sempre nos perfis padrão (mesmo saldo 0 -> motivo na descrição).
        if not perfil.get("financeira_embutida"):
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
        if sem_valor and not body.motivo_financeira_zero.strip():
            avisos.append("Cobrança sem valor (saldo 0) e sem motivo informado — "
                          "preencha o motivo (mudança de gestão, acordo interno, etc.) antes de gerar.")

    # E1: Tipo é sempre Contrato; situação padrão Nova sollicitação e produto do
    # painel (o novo titular/financeira já trazem os seus -> setdefault preserva).
    for op in operacoes:
        op["tipo_id"] = TIPO_CONTRATO_ID
        op.setdefault("situacao_id", SITUACAO_NOVA_ID)
        op.setdefault("produto_servico_id", body.produto_servico_id)
        op["prioridade_id"] = body.prioridade_id  # OPs usam a prioridade do painel (financeira já traz Normal)
    solucao_tecnica_txt = _formatar_solucao_tecnica(body.solucao_tecnica)

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
        resultado, numero = await _criar_uma_os(op, solucao_tecnica_txt)
        criadas.append(resultado)
        if numero:
            numeros_operacionais.append(str(numero))

    if financeira:
        nums = ", ".join(f"nº {n}" for n in numeros_operacionais) or "(nenhuma)"
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        solucao_fin = f"[{agora}] {len(numeros_operacionais)} OS de instalação/serviço geradas neste termo: {nums}"
        resultado_fin, _num = await _criar_uma_os(financeira, solucao_fin)
        criadas.append(resultado_fin)

    return {"simulado": False, "total_os": len(todas), "resultados": criadas, "avisos": avisos}


def _serie_que_entra(perfil: dict, seriais: dict, placa: str) -> str:
    """Serie do equipamento que ENTRA, via placa-recipiente de teste.

    Vazio nos perfis que nao usam recipiente -- `str.format` ignora chave que
    o template nao cita, entao passar sempre e mais simples que ramificar.
    """
    sufixo = perfil.get("placa_teste_sufixo")
    if not sufixo:
        return ""
    return serie_de(seriais, placa_teste(placa, sufixo))


def _norm_desc(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip().upper()


def _conferir_placas_teste(body, perfil: dict) -> None:
    """🚨 A placa-recipiente tem que ser DESTE termo.

    Placa que ja passou por upgrade antes deixa um recipiente velho na WESO,
    com a descricao do termo ANTERIOR. Sem esta conferencia a OS sairia com a
    serie do equipamento passado -- plausivel, errada e silenciosa, que e como
    nasceram o `RFD 2447` e o card de ano 0002.

    ⚠️ AUSENCIA NAO BLOQUEIA, CONTRADICAO BLOQUEIA. `descricao_da_placa`
    devolve None para "nao sei" (cache fora, recipiente ainda nao criado pelo
    setor de configuracao) -- ai vale o best-effort da casa e a descricao sai
    com o marcador de serie nao localizada. So descricao DIVERGENTE, que e
    prova positiva de recipiente errado, derruba a geracao.
    """
    sufixo = perfil.get("placa_teste_sufixo")
    if not sufixo:
        return
    modelo = perfil.get("placa_teste_descricao") or "TERMO {termo}"
    esperado = modelo.format(termo=body.termo)
    for p in body.placas:
        pt = placa_teste(p.placa, sufixo)
        achado = descricao_da_placa(pt)
        if achado is None:
            continue
        if _norm_desc(achado) != _norm_desc(esperado):
            raise HTTPException(
                400,
                f"Placa {p.placa}: o recipiente de teste {pt} na WESO esta como "
                f"{achado!r}, mas o termo subido e {esperado!r}. Provavelmente e "
                f"o recipiente de um upgrade ANTERIOR desta placa -- gerar assim "
                f"colocaria na OS a serie do equipamento antigo. Confira com o "
                f"setor de configuracao antes de gerar.")


def _modelo_da_operacao(perfil: dict, placa: str, materiais: list[dict]) -> str:
    """Modelo do rastreador para a descricao da OS, lido da WESO.

    🚨 IGNORA O VINCULO PARA ESTE ITEM, por decisao do usuario (13/08): o
    vinculo diz o que o TERMO escreveu, a WESO diz o que ESTA no veiculo.

    Qual placa se le depende do perfil:
      upgrade ......... o recipiente `<PLACA>-UPGRADE` (o que ENTRARA)
      demais .......... a propria placa da operacao (o que ESTIVER)

    ⚠️ Cliente novo nao tem o que ler -- e instalacao nova, o veiculo ainda nao
    existe na WESO. Ali o marcador aparece, e e honesto: nao ha equipamento.
    """
    origem = perfil.get("modelo_origem")
    alvo = placa
    if origem == "placa_teste" and perfil.get("placa_teste_sufixo"):
        alvo = placa_teste(placa, perfil["placa_teste_sufixo"])
    return modelo_efetivo(modelo_da_placa(alvo), tem_leitor_rfid(materiais))


# 🚨 O EQUIPAMENTO E MATERIAL, NAO SO TEXTO. Ate 13/08 o modelo resolvido na
# WESO ia apenas para a descricao da OS, e o material saia so com o servico do
# cabecalho + ENTREGA OS -- foi o que o usuario achou auditando o termo 8820.
_MARCA_RASTREADOR = ("RASTREADOR", "EQUIPAMENTO RASTREADOR")


def _ja_tem_rastreador(materiais: list[dict]) -> bool:
    """O termo ja trouxe um item de rastreador (via vinculo)?"""
    for m in materiais or []:
        d = str(m.get("descricao") or "").upper()
        if any(marca in d for marca in _MARCA_RASTREADOR):
            return True
    return False


def _material_do_equipamento(perfil: dict, placa: str, materiais: list[dict]) -> dict | None:
    """Material do equipamento que a WESO diz estar (ou entrar) nesta placa.

    ⚠️ COMODATO, NUNCA COBRA. O valor e PATRIMONIAL -- vai para a DANFE de
    comodato, nao e preco. Mesma regra que `_resolver_vinculos` ja aplica:
    comodato e cobrar nunca sao verdadeiros ao mesmo tempo.

    ⚠️ NAO DUPLICA. Se o termo ja listou um rastreador, este material NAO e
    acrescentado -- sairiam dois equipamentos na mesma OS. Substituir o do
    vinculo pelo real ainda NAO foi decidido pelo usuario, e sobrescrever o que
    o contrato escreveu sem ordem seria pior que a lacuna.
    """
    if not perfil.get("modelo_origem"):
        return None
    if _ja_tem_rastreador(materiais):
        logger.info("equipamento: %s ja tem item de rastreador no termo -- nao acrescento", placa)
        return None
    modelo = _modelo_da_operacao(perfil, placa, materiais)
    prod = storage.produto_do_modelo(modelo)
    if not prod:
        logger.info("equipamento: modelo %r sem produto no de-para -- fica so na descricao", modelo)
        return None
    return {"harmonit_id": prod["harmonit_id"], "quantidade": 1,
            "valor_unitario": prod["valor"], "comodato": True, "cobrar": False,
            "descricao": prod["descricao"]}
