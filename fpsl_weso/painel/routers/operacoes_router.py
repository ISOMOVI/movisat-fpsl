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
import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ..auth import requer_aba
from .. import operacoes_config as cfg
from ..pdf_extractor import extrair_campos
from ...client import weso_get, weso_post
from ...harmonit_client import harmonit_get
from ... import placas as regra_placa

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


# ── etapa 1: o documento ─────────────────────────────────────────────────────

def _so_doc(v) -> str:
    """CNPJ/CPF sem pontuação. Alfanumérico, não só dígito: o CNPJ novo tem
    letra (`WQ0P6GLD000108` é o da empresa de teste)."""
    return "".join(c for c in str(v or "") if c.isalnum())


@router.post("/extrair")
async def extrair(perfil: str = Query(...), arquivo: UploadFile = File(...),
                  _=Depends(requer_aba("operacoes"))):
    """Lê o termo. NÃO ESCREVE NADA e NÃO cruza cliente.

    ⚠️ SEPARADO DO CLIENTE, ao contrário da tela velha. Lá `/placas/extrair`
    lia o PDF e batia nos dois sistemas na mesma requisição -- e a consulta ao
    Harmonit e à WESO é justamente a parte que oscila. Se ela demora, a leitura
    do PDF, que é local e instantânea, demora junto e o operador não vê nada.
    Aqui a etapa 1 responde na hora e a etapa 2 pede o cliente quando chegar
    nela.

    Devolve os veículos NA ORDEM E NAS COLUNAS DO DOCUMENTO -- veículo primeiro,
    placa depois -- porque é assim que se confere linha a linha contra o papel.
    A tela oferece inverter por linha; padronizar isso é problema da origem.
    """
    if perfil not in cfg.PERFIS:
        raise HTTPException(400, f"Tipo de operação desconhecido: {perfil}")
    p = cfg.PERFIS[perfil]
    if p.get("sem_termo"):
        raise HTTPException(400,
            f"{p['label']} não nasce de documento — use a entrada digitada.")

    conteudo = await arquivo.read()
    try:
        campos = extrair_campos(io.BytesIO(conteudo), perfil)
    except Exception as exc:
        log.exception("operacoes: falha ao ler o PDF")
        raise HTTPException(422, f"Não foi possível ler o PDF: {exc}")

    # 🚨 A SUBSTITUIÇÃO NÃO USA `placas`, USA `pares` (medido em 19/08). O
    # extrator devolve `{placa_saida, veiculo_saida, placa_entrada,
    # veiculo_entrada}` -- é o único perfil com dois veículos por linha, porque
    # o equipamento muda de carro. Ler `placas` nele devolve LISTA VAZIA, e a
    # etapa 1 mostraria "0 veículos" num termo que tem 1.
    linhas = campos.get("placas") or []
    if not linhas and campos.get("pares"):
        linhas = [
            {"veiculo": par.get("veiculo_saida"), "placa": par.get("placa_saida"),
             "veiculo_entrada": par.get("veiculo_entrada"),
             "placa_entrada": par.get("placa_entrada"),
             "acessorios_entrada": par.get("acessorios_entrada")}
            for par in campos["pares"]
        ]

    itens = []
    for linha in linhas:
        bruta = str(linha.get("placa") or "").strip()
        entrada = str(linha.get("placa_entrada") or "").strip()
        item = {
            "veiculo": (linha.get("veiculo") or "").strip(),
            "placa": bruta,
            # 🚨 CHASSI E SÉRIE ENTRAM COMO ESTÃO -- provado nos dois sistemas
            # em 17/08. `convencional` é só rótulo para a tela destacar, não
            # tratamento diferente.
            "placa_gravada": regra_placa.formatar(bruta) or bruta,
            "convencional": regra_placa.eh_convencional(bruta),
            "sem_descricao": not (linha.get("veiculo") or "").strip(),
        }
        if entrada:
            item.update({
                "veiculo_entrada": (linha.get("veiculo_entrada") or "").strip(),
                "placa_entrada": entrada,
                "placa_entrada_gravada": regra_placa.formatar(entrada) or entrada,
            })
        itens.append(item)

    # 🚨 O QUE NÃO FOI LIDO APARECE. Linha de veículo sem placa reconhecida vai
    # para `sem_placa` e é mostrada -- nunca vira identificador inventado. Foi
    # assim que `RFD 2447`, placa que não existe na WESO, nasceu de texto solto
    # no termo 8800. Antes disso a tela dizia "9 veículos" num termo de 11 sem
    # nada indicar os 2 que faltavam.
    sem_placa = campos.get("veiculos_sem_placa") or []

    doc = _so_doc(campos.get("cnpj") or campos.get("cpf"))

    # 🚨 A RESCISÃO NÃO TRAZ O DOCUMENTO (medido em 19/08 nos dois fixtures,
    # 8788 e 8842: `cnpj` e `cpf` vêm `None`). O layout dela traz só o NOME.
    #
    # ⚠️ E NÃO SE CRUZA POR NOME -- é regra: o mesmo CNPJ é `Velasco Leite
    # Pastelaria ME` no Harmonit e `PASTELARIA VELASCO LTDA` na WESO, então
    # nome casa errado ou não casa. Quando falta o documento, quem informa é o
    # operador, com o nome do termo à vista para ele conferir.
    #
    # A tela precisa saber a diferença entre "o termo não tem" e "não consegui
    # ler" -- por isso o campo é explícito, não um vazio que ela adivinha.
    return {
        "perfil": perfil,
        "termo": campos.get("termo"),
        "documento": doc,
        "documento_no_termo": bool(doc),
        "nome_no_termo": campos.get("cliente_nome_sugerido"),
        "itens": itens,
        "sem_placa": sem_placa,
        "recipiente_sufixo": (p.get("placa_teste_sufixo") or "").upper() or None,
        # 🆕 A SUBSTITUIÇÃO TRAZ AS DUAS TAXAS NO PRÓPRIO TERMO (medido em
        # 19/08: `299,90` local diferente e `199,90` mesmo local). Elas sobem
        # aqui porque valor de serviço fixado em código apodrece -- é a mesma
        # família do `tipo = 55`, que sumiu da lista do Harmonit e ninguém viu.
        "taxa_local_diferente": campos.get("taxa_local_diferente"),
        "taxa_mesmo_local": campos.get("taxa_mesmo_local"),
        "resumo": {
            "veiculos": len(itens),
            "nao_convencionais": sum(1 for i in itens if not i["convencional"]),
            "sem_descricao": sum(1 for i in itens if i["sem_descricao"]),
            "nao_lidos": len(sem_placa),
            "com_entrada": sum(1 for i in itens if i.get("placa_entrada")),
        },
    }


# ── etapa 2: o cliente ───────────────────────────────────────────────────────

async def _no_harmonit(doc: str) -> dict | None:
    """Cliente por CNPJ/CPF no Harmonit, ou None.

    🚨 O HARMONIT RESPONDE EM DUAS FORMAS: existe -> `list`; não existe ->
    `dict` com `data: []`. E o dict de "não encontrado" é TRUTHY -- tratar a
    resposta como verdade diria que todo documento já existe, inclusive um
    inventado.
    """
    if not doc:
        return None
    try:
        r = await harmonit_get("/ObterClientePorCpfCnpj", params={"CpfCnpj": doc})
    except Exception as exc:
        log.info("operacoes: busca de %s no Harmonit falhou: %s", doc, exc)
        return None
    if isinstance(r, list):
        itens = r
    elif isinstance(r, dict):
        itens = r.get("data") or []
        if not isinstance(itens, list):
            itens = [itens] if itens else []
    else:
        itens = []
    return itens[0] if itens else None


async def _na_weso(doc: str) -> dict | None:
    if not doc:
        return None
    r = await weso_get("/Clientes/Consultar", {"cnpjcpf": doc})
    lista = (r.get("clientes") if isinstance(r, dict) else r) or []
    return lista[0] if lista else None


def _situacao_cliente(no_harmonit, no_weso) -> tuple[str, str]:
    """(situação, o que a tela deve dizer). Uma função só, para os dois lados
    da decisão não divergirem entre o backend e a tela."""
    if not no_harmonit:
        return ("sem_harmonit",
                "Este documento não está no Harmonit. Termo existente implica "
                "cliente lá — confira o CNPJ do termo. O painel não cria "
                "cliente no Harmonit.")
    if not no_weso:
        return ("falta_na_weso",
                "Cliente existe no Harmonit e falta na WESO. Pode ser criado "
                "aqui, com os dados do Harmonit.")
    return ("ok", "Cliente existe nos dois sistemas.")


@router.get("/cliente")
async def conferir_cliente(documento: str = Query(...),
                           _=Depends(requer_aba("operacoes"))):
    """Os dois sistemas lado a lado. NÃO ESCREVE.

    🚨 CRUZA POR DOCUMENTO, NUNCA POR NOME. Medido em 17/08: o mesmo CNPJ é
    `Velasco Leite Pastelaria ME` no Harmonit e `PASTELARIA VELASCO LTDA` na
    WESO. A tela mostra os DOIS nomes, senão parece que achou o cliente errado.
    """
    doc = _so_doc(documento)
    if not doc:
        raise HTTPException(400, "Documento vazio.")

    no_harmonit = await _no_harmonit(doc)
    no_weso = await _na_weso(doc)
    situacao, recado = _situacao_cliente(no_harmonit, no_weso)

    return {
        "documento": doc,
        "situacao": situacao,
        "recado": recado,
        "harmonit": None if not no_harmonit else {
            "id": no_harmonit.get("id"),
            "nome": no_harmonit.get("nome"),
        },
        "weso": None if not no_weso else {
            "id": no_weso.get("id"),
            "nome": no_weso.get("razaoSocial"),
            "situacao": no_weso.get("situacao"),
        },
    }


class CriarClienteInput(BaseModel):
    documento: str


@router.post("/cliente/criar-na-weso")
async def criar_cliente_na_weso(body: CriarClienteInput,
                                _=Depends(requer_aba("operacoes"))):
    """Cria na WESO o cliente que já existe no Harmonit. ESCREVE.

    🚨 OS DADOS VÊM DO HARMONIT, NUNCA DA TELA. O operador não digita nome de
    cliente aqui: se o Harmonit é a fonte, deixar alguém redigitar é convidar
    duas verdades. `cnpjcpf` + `razaoSocial` bastam -- `situacao` vem
    `Adimplente` sozinha.

    🚨 A CONFIRMAÇÃO É RELER, NUNCA O HTTP. Este projeto já viu a WESO devolver
    erro HTML e GRAVAR, e devolver timeout com a escrita acontecendo depois.
    """
    doc = _so_doc(body.documento)
    if not doc:
        raise HTTPException(400, "Documento vazio.")

    no_harmonit = await _no_harmonit(doc)
    if not no_harmonit:
        # Falha fechado: sem o Harmonit não há de onde tirar o nome, e inventar
        # um cliente na WESO é pior que não criar.
        raise HTTPException(422,
            "Não achei este documento no Harmonit — não há de onde tirar os "
            "dados. O painel não cria cliente no Harmonit.")

    ja = await _na_weso(doc)
    if ja:
        return {"acao": "ja_existia", "id": ja.get("id"),
                "nome": ja.get("razaoSocial")}

    nome = (no_harmonit.get("nome") or "").strip()
    if not nome:
        raise HTTPException(422,
            "O cliente do Harmonit veio sem nome — não dá para cadastrar na "
            "WESO sem `razaoSocial`.")

    try:
        await weso_post("/Clientes/Cadastro",
                        {"cnpjcpf": doc, "razaoSocial": nome}, allow_409=True)
    except HTTPException as exc:
        # ⚠️ NÃO DESISTE NO ERRO. A WESO já gravou devolvendo erro HTML, e já
        # processou depois de estourar o tempo. Quem decide é a releitura.
        log.warning("operacoes: cadastro do cliente %s devolveu erro: %s",
                    doc, exc.detail)

    conferido = await _na_weso(doc)
    if not conferido:
        raise HTTPException(502,
            "A WESO não recusou, mas o cliente não aparece na releitura. "
            "Nada foi confirmado — tente de novo.")
    return {"acao": "criado", "id": conferido.get("id"),
            "nome": conferido.get("razaoSocial"), "verificado_relendo": True}
