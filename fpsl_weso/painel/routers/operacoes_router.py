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
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ..auth import requer_aba
from .. import operacoes_config as cfg
from ..pdf_extractor import extrair_campos
from .. import operacoes_espera as esp
from .. import operacoes_registro as reg
from .. import operacoes_rotina as rot
from ...client import weso_get, weso_post
from ...harmonit_client import harmonit_get, harmonit_post
from ... import placas as regra_placa
from .. import operacoes_equipamentos as eqp
from .. import operacoes_os as oos
from ... import storage

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
        # 🚨 OS ITENS DO CONTRATO, com nome proprio. O `itens` acima sao os
        # VEICULOS; estes sao as linhas de produto e servico do termo, e sao
        # eles que a etapa 4 resolve contra o catalogo do Harmonit. Sem eles a
        # OS sai so com o servico do cabecalho e o ENTREGA OS -- completa na
        # aparencia e vazia no conteudo.
        "itens_contrato": campos.get("itens") or [],
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


# ── etapa 3: as placas ───────────────────────────────────────────────────────
#
# 🚨 A ETAPA 3 NÃO É "CADASTRAR", É "GARANTIR". Em rescisão, transferência e
# ressarcimento as placas já existem: a etapa CONFERE e casa. Em contrato novo
# ela CRIA. Mesma etapa, mesmo desenho, decisão por perfil (`etapa_placas`).
# Se ela fosse só cadastrar, metade dos perfis a pularia -- e a corrente
# cliente → placa → OS, que é a razão desta aba existir, se quebraria
# justamente onde ela serve.

TIPO_BANCADA = 2   # `complemento.tipoEqp` que marca recipiente na WESO


class LoteInput(BaseModel):
    perfil: str
    termo: str | None = None
    documento: str | None = None
    # 🚨 O CLIENTE VEM DA ETAPA 2, QUE JÁ ACONTECEU. O `guardar_cliente` existia
    # desde a F3 e NUNCA foi chamado: as colunas `cliente_harmonit_id` e
    # `cliente_weso_id` ficavam nulas em todo lote, e com elas o Histórico não
    # sabia de quem era a rodada. Não dá para gravar na rota `/cliente` porque
    # lá o lote ainda não existe -- ele nasce ao entrar na etapa 3.
    cliente_harmonit_id: int | None = None
    cliente_weso_id: int | None = None


@router.post("/lote")
async def abrir_lote(body: LoteInput, usuario=Depends(requer_aba("operacoes"))):
    """Abre a rodada. É o `lote` que permite RETOMAR.

    🚨 UM TERMO DE 11 PLACAS LEVA MAIS DE UM MINUTO só nesta etapa (~4s por
    placa), e a WESO oscila entre 6s e timeout de 30s. Se cair no meio, o
    operador não pode recomeçar do PDF -- metade já nasceu, e recriar devolve
    409 ou duplica. O lote diz de onde continuar.
    """
    if body.perfil not in cfg.PERFIS:
        raise HTTPException(400, f"Tipo de operação desconhecido: {body.perfil}")
    lote = await reg.abrir_lote((usuario or {}).get("login"), body.perfil,
                                body.termo, _so_doc(body.documento))
    # A etapa 2 já terminou quando o lote nasce -- gravar o cliente aqui é o
    # que faz a coluna `etapa` sair de 1.
    await reg.guardar_cliente(lote, body.cliente_harmonit_id,
                              body.cliente_weso_id)
    return {"lote": lote}


@router.get("/lote/{lote}")
async def ler_lote(lote: str, _=Depends(requer_aba("operacoes"))):
    """O que já aconteceu nesta rodada -- é por aqui que a tela retoma."""
    cabecalho = await reg.ler_lote(lote)
    if not cabecalho:
        raise HTTPException(404, "Lote não encontrado.")
    return {"lote": cabecalho, "passos": await reg.passos(lote),
            "resumo": await reg.resumo(lote),
            "resolvidas": {p: sorted(s) for p, s in (await reg.ja_resolvidas(lote)).items()}}


async def _existe_na_weso(texto: str) -> dict | None:
    """Consulta EXATA, nunca a base inteira.

    🚨 Medido: base inteira 15,6s a timeout de 30s; uma placa 0,2s. E a placa
    acabou de ser escrita com a grafia procurada, então a consulta exata acha.
    ⚠️ `?placa=` compara por IGUALDADE e devolve VAZIO, não erro -- por isso
    "não achou" aqui significa "não existe com esta grafia", nada além disso.
    """
    r = await weso_get("/Veiculos/Consultar", {"placa": texto})
    lista = (r.get("veiculos") if isinstance(r, dict) else r) or []
    # ⚠️ TRAVA: se o filtro for ignorado, a WESO devolve a base inteira e
    # qualquer placa "existiria". Confere que o que voltou é o que se pediu.
    for v in lista:
        if str(v.get("placa") or "").strip().upper() == texto.strip().upper():
            return v
    return None


async def _existe_no_harmonit(texto: str) -> dict | None:
    """⚠️ `/Veiculo/ObterVeiculos` IGNORA TODOS OS FILTROS (medido). Lê a base
    e casa aqui. 9.114 registros, ~1,9s -- caro, mas é o que existe."""
    try:
        r = await harmonit_get("/Veiculo/ObterVeiculos")
    except Exception as exc:
        log.warning("operacoes: base do Harmonit indisponivel: %s", exc)
        return None
    d = r.get("data") if isinstance(r, dict) else r
    lista = (d.get("lista") if isinstance(d, dict) else d) or []
    alvo = "".join(str(texto or "").split()).upper()
    for v in lista:
        if "".join(str(v.get("placa") or "").split()).upper() == alvo:
            return v
    return None


class PlacaInput(BaseModel):
    lote: str
    placa: str
    descricao: str | None = None
    recipiente: bool = False
    cliente_harmonit_id: int | None = None
    documento: str | None = None


@router.post("/placas/uma")
async def criar_uma_placa(body: PlacaInput,
                          _=Depends(requer_aba("operacoes"))):
    """Garante UMA placa nos dois sistemas. Harmonit primeiro, WESO depois.

    🚨 HARMONIT ANTES DA WESO, E FALHA DO PRIMEIRO PARA. Na ordem inversa
    sobraria veículo na WESO sem par -- o estrago espelhado do de 27/07, quando
    um `PUT` sem `veiculoId` criou 88 veículos e quebrou 93 vínculos.

    🚨 RECIPIENTE SÓ NA WESO. Ele é bancada do setor de configuração, não
    veículo do cliente.

    🚨 A PROVA É RELER, NUNCA O CÓDIGO DE RETORNO. Este projeto já viu a WESO
    devolver erro HTML e GRAVAR, e devolver timeout com a escrita acontecendo
    depois. O que decide é a releitura.
    """
    cabecalho = await reg.ler_lote(body.lote)
    if not cabecalho:
        raise HTTPException(404, "Lote não encontrado.")
    perfil = cfg.PERFIS.get(cabecalho["perfil"])
    if not perfil:
        raise HTTPException(400, f"Perfil do lote é desconhecido: {cabecalho['perfil']}")

    texto = (regra_placa.formatar(body.placa) or body.placa or "").strip()
    if not texto:
        raise HTTPException(400, "Placa vazia.")
    # 🚨 O RECIPIENTE NÃO SE FORMATA. `TST0A11-MANUT` não é placa convencional
    # e ganhar espaço quebraria a chave que a geração de OS procura.
    if body.recipiente:
        texto = (body.placa or "").strip()

    # Chegou a escrever placa: a rodada está na etapa 3.
    await reg.marcar_etapa(body.lote, 3)

    doc = _so_doc(body.documento or cabecalho.get("documento"))
    comum = dict(placa_digitada=body.placa, placa_gravada=texto,
                 descricao=body.descricao, recipiente=body.recipiente)
    fora = {"placa_gravada": texto, "recipiente": body.recipiente,
            "harmonit": None, "weso": None}

    confere_apenas = perfil["etapa_placas"] == "confere"

    # ── Harmonit ─────────────────────────────────────────────────────────────
    if body.recipiente:
        await reg.registrar(body.lote, 3, "harmonit", "ignorado",
                            erro="recipiente é bancada, não veículo do cliente",
                            **comum)
        fora["harmonit"] = {"acao": "ignorado",
                            "motivo": "recipiente é bancada, não veículo do cliente"}
    else:
        ja = await _existe_no_harmonit(texto)
        if ja:
            acao = "confere_ok" if confere_apenas else "ja_existia"
            await reg.registrar(body.lote, 3, "harmonit", acao,
                                id_externo=ja.get("id"), **comum)
            fora["harmonit"] = {"acao": acao, "id": ja.get("id"),
                                "dono": ja.get("cliente"),
                                "dono_id": ja.get("clienteId")}
        elif confere_apenas:
            # 🚨 CONFERIR NÃO CRIA. Perfil de rescisão/transferência/
            # ressarcimento opera sobre placa que já existe: se ela não existe,
            # o dado está errado e criar seria esconder o erro.
            await reg.registrar(body.lote, 3, "harmonit", "confere_falta",
                                erro="não existe no Harmonit", **comum)
            fora["harmonit"] = {"acao": "confere_falta",
                                "motivo": "não existe no Harmonit"}
        elif not (body.cliente_harmonit_id or cabecalho.get("cliente_harmonit_id")):
            await reg.registrar(body.lote, 3, "harmonit", "ignorado",
                                erro="cliente não encontrado no Harmonit", **comum)
            fora["harmonit"] = {"acao": "ignorado",
                                "motivo": "cliente não encontrado no Harmonit"}
        else:
            cid = body.cliente_harmonit_id or cabecalho["cliente_harmonit_id"]
            payload = {"id": 0, "veiculo": body.descricao or texto,
                       "placa": texto, "clienteId": cid}
            try:
                await harmonit_post("/Veiculo/Incluir", payload)
            except HTTPException as exc:
                msg = f"o Harmonit recusou: {exc.detail}"
                await reg.registrar(body.lote, 3, "harmonit", "falhou",
                                    erro=msg, **comum)
                await reg.registrar(body.lote, 3, "weso", "ignorado",
                                    erro="o Harmonit falhou antes", **comum)
                fora["harmonit"] = {"acao": "falhou", "erro": msg}
                fora["weso"] = {"acao": "ignorado",
                                "motivo": "o Harmonit falhou antes"}
                return fora
            conferido = await _existe_no_harmonit(texto)
            if conferido:
                await reg.registrar(body.lote, 3, "harmonit", "criado",
                                    id_externo=conferido.get("id"), **comum)
                fora["harmonit"] = {"acao": "criado", "id": conferido.get("id"),
                                    "verificado_relendo": True}
            else:
                msg = ("o Harmonit não recusou, mas a placa não aparece na "
                       "releitura")
                await reg.registrar(body.lote, 3, "harmonit", "falhou",
                                    erro=msg, **comum)
                await reg.registrar(body.lote, 3, "weso", "ignorado",
                                    erro="o Harmonit falhou antes", **comum)
                fora["harmonit"] = {"acao": "falhou", "erro": msg}
                fora["weso"] = {"acao": "ignorado",
                                "motivo": "o Harmonit falhou antes"}
                return fora

    # ── WESO ─────────────────────────────────────────────────────────────────
    try:
        ja_w = await _existe_na_weso(texto)
    except HTTPException as exc:
        msg = f"não consegui conferir na WESO: {exc.detail}"
        await reg.registrar(body.lote, 3, "weso", "falhou", erro=msg, **comum)
        fora["weso"] = {"acao": "falhou", "erro": msg}
        return fora

    if ja_w:
        acao = "confere_ok" if confere_apenas else "ja_existia"
        await reg.registrar(body.lote, 3, "weso", acao,
                            id_externo=ja_w.get("id"), **comum)
        fora["weso"] = {"acao": acao, "id": ja_w.get("id"),
                        "descricao_atual": ja_w.get("descricao")}
        return fora

    if confere_apenas:
        await reg.registrar(body.lote, 3, "weso", "confere_falta",
                            erro="não existe na WESO", **comum)
        fora["weso"] = {"acao": "confere_falta", "motivo": "não existe na WESO"}
        return fora

    if not doc:
        await reg.registrar(body.lote, 3, "weso", "falhou",
                            erro="sem documento do cliente", **comum)
        fora["weso"] = {"acao": "falhou", "erro": "sem documento do cliente"}
        return fora

    # 🚨 TRAVA: SÓ O DOCUMENTO vai para a WESO, nunca os dados do cliente.
    equipamento = {"placa": texto, "cliente": {"cnpjcpf": doc}}
    if body.descricao:
        equipamento["descricao"] = body.descricao
    if body.recipiente:
        equipamento["complemento"] = {"tipoEqp": TIPO_BANCADA}
    try:
        await weso_post("/Veiculos/Cadastro", {"equipamento": equipamento},
                        allow_409=True)
    except HTTPException as exc:
        # ⚠️ NÃO DESISTE NO ERRO. A WESO já gravou devolvendo erro HTML, e já
        # processou depois de estourar o tempo. Quem decide é a releitura.
        log.warning("operacoes: cadastro de %r devolveu erro: %s", texto, exc.detail)

    conferido = await _existe_na_weso(texto)
    if conferido:
        await reg.registrar(body.lote, 3, "weso", "criado",
                            id_externo=conferido.get("id"), **comum)
        fora["weso"] = {"acao": "criado", "id": conferido.get("id"),
                        "verificado_relendo": True}
    else:
        msg = "a WESO não recusou, mas a placa não aparece na releitura"
        await reg.registrar(body.lote, 3, "weso", "falhou", erro=msg, **comum)
        fora["weso"] = {"acao": "falhou", "erro": msg}
    return fora


# ── etapa 4: as OS ───────────────────────────────────────────────────────────
#
# 🚨 MOSTRA O QUE VAI SER GRAVADO, NÃO O QUE FOI DIGITADO. A prévia monta
# exatamente as mesmas operações que a gravação usa -- a montagem é uma função
# só, em `operacoes_os.montar`, e o cabeçalho é aplicado pela mesma função nos
# dois caminhos. Prévia que reconstrói o resultado por conta própria é prévia
# que mente, e o operador confia nela justamente por ser a última coisa que ele
# vê antes de escrever em dois sistemas.


@router.get("/modelos")
async def listar_modelos(_=Depends(requer_aba("operacoes"))):
    """O de-para modelo → produto: o seletor da regra 9."""
    return {"modelos": storage.listar_modelos_produto()}


async def _nascidas_no_lote(lote: str | None) -> set[str]:
    """As placas que ESTA rodada criou.

    🚨 É O QUE SEPARA OS DOIS ESTADOS. "Ainda não vinculado, porque a placa
    nasceu agora" e "não consegui ler a WESO" produziam o mesmo texto, e o
    segundo é o defeito da OS 16775. A tela sabe em qual está porque ela mesma
    criou a placa segundos antes -- o lote registrou `criado`. Sem isto,
    estaríamos adivinhando depois o que já sabíamos na hora.
    """
    if not lote:
        return set()
    return {eqp.chave(p["placa_gravada"]) for p in await reg.passos(lote)
            if p["acao"] == "criado" and p["placa_gravada"]}


# ── Tipo e Problema por NOME, não por id ────────────────────────────────────

async def _lista_do_harmonit(path: str) -> list[dict] | None:
    """Lista do Harmonit, ou None quando a chamada não respondeu.

    🚨 None É "NÃO SEI", e não autoriza recusar nada. É a diferença entre a rede
    ter falhado e o item ter sumido do cadastro -- só a segunda justifica parar
    a geração.
    """
    try:
        r = await harmonit_get(path, params={"empresaId": 98})
    except Exception as exc:
        log.warning("operacoes: lista %s indisponivel: %s", path, exc)
        return None
    d = r.get("data", r) if isinstance(r, dict) else r
    if isinstance(d, dict):
        d = d.get("lista") or d.get("itens") or []
    return list(d or [])


def _achar_por_nome(lista: list[dict], nome: str) -> int | None:
    alvo = oos.norm_desc(nome)
    for x in lista:
        for campo in ("descricao", "nome", "titulo"):
            if x.get(campo) and oos.norm_desc(x[campo]) == alvo:
                return x.get("id")
    return None


async def _resolver_cabecalho_por_nome(perfil: dict) -> tuple[dict, list[str]]:
    """{tipo_id, problema_id} resolvidos pelo NOME contra a lista viva.

    🚨 ID FIXO EM CÓDIGO APODRECE EM SILÊNCIO. Medido em 14/08: das 14 OS de
    manutenção que a casa abriu na mão, 7 usam `tipo = 55` -- que não está mais
    na lista de tipos do Harmonit. Se o painel tivesse nascido com aquele
    número, hoje estaria gravando um tipo morto sem ninguém perceber.

    Política: nome sumiu da lista => RECUSA, porque é apodrecimento e precisa de
    decisão humana. Lista não respondeu => usa o `*_id` do perfil e avisa,
    porque é transiente e travar a geração por causa de rede seria pior.
    """
    alvos = (("tipo_nome", "tipo_id",
              "/TipoOrdemServico/ObterListaTipoOrdemServico", "Tipo"),
             ("problema_nome", "problema_id", "/Problema/ObterProblemas",
              "Problema"))
    resolvido: dict[str, int] = {}
    avisos: list[str] = []
    for chave_nome, chave_id, path, rotulo in alvos:
        nome = perfil.get(chave_nome)
        if not nome:
            continue
        lista = await _lista_do_harmonit(path)
        if lista is None:
            resolvido[chave_id] = perfil.get(chave_id)
            avisos.append(
                f"A lista de {rotulo} do Harmonit não respondeu — usei o último "
                f"id conhecido para {nome!r}. Confira a OS gerada.")
            continue
        achado = _achar_por_nome(lista, nome)
        if achado is None:
            raise HTTPException(400,
                f"{rotulo} {nome!r} não existe mais na lista do Harmonit. "
                "Alguém renomeou ou removeu o cadastro — escolha o novo antes "
                "de gerar, em vez de eu mandar um id velho.")
        resolvido[chave_id] = achado
    return resolvido, avisos


def _aplicar_cabecalho(operacoes: list[dict], perfil: dict, cabecalho: dict,
                       body: "oos.MontarInput") -> None:
    """Aplica Tipo/Problema resolvidos, e a escolha da tela onde ela vale.

    ⚠️ A FINANCEIRA FICA DE FORA. Ela traz o próprio cabeçalho (Problema
    FINANCEIRO, situação Financeiro, técnico Karla) e sobrescrevê-lo com o
    Tipo/Problema da operação a transformaria noutra coisa.
    """
    for op in operacoes:
        if op.get("eh_financeira"):
            continue
        if cabecalho.get("tipo_id"):
            op["tipo_id"] = cabecalho["tipo_id"]
        if cabecalho.get("problema_id"):
            op["problema_id"] = cabecalho["problema_id"]
        # 🚨 A ESCOLHA DA TELA SÓ VENCE NOS PERFIS SEM TERMO. Num contrato o
        # problema é ditado pelo documento; deixar quem digita trocá-lo faria a
        # OS divergir do papel assinado.
        if body.problema_id and perfil.get("sem_termo"):
            op["problema_id"] = body.problema_id


# ── a leitura da WESO ────────────────────────────────────────────────────────

async def _ler_weso(body: "oos.MontarInput", perfil: dict) -> dict:
    """Séries, dados e recipientes -- com o custo que cada perfil justifica.

    🚨 AO VIVO SÓ NOS PERFIS SEM TERMO. O recipiente da manutenção nasce
    minutos antes da OS e o cache local só atualiza às 04:15 -- ler do cache ali
    devolveria "modelo nao localizado" para equipamento que existe. Nos perfis
    de contrato o cache basta: o termo demora dias, e pagar rede a cada geração
    não se justifica.

    🚨 UMA LEITURA SÓ, para a placa real E o recipiente juntos. Antes eram duas
    chamadas independentes, e cada uma que não achasse pela consulta exata caía
    na base inteira -- 16,65s cada. Uma geração de manutenção com recipiente
    ainda não criado levava 43s, perto do teto do nginx. Foi o erro visto em
    14/08.

    ⚠️ E POR ISSO O RECIPIENTE NÃO ENTRA NO `buscar_seriais` DA MANUTENÇÃO: a
    leitura ao vivo abaixo já traz série e modelo dele. No upgrade continua
    entrando, porque lá não há leitura ao vivo.
    """
    falhas: list[str] = []
    sufixo = perfil.get("placa_teste_sufixo")

    todas = [p.placa for p in body.placas]
    todas += [p.placa_entrada for p in body.placas if p.placa_entrada]
    if sufixo and not perfil.get("sem_termo"):
        todas += [eqp.placa_teste(p.placa, sufixo) for p in body.placas]
    seriais = await eqp.buscar_seriais(todas, falhas)

    dados: dict = {}
    recipientes: dict = {}
    if perfil.get("sem_termo"):
        alvos = [p.placa for p in body.placas]
        if sufixo:
            alvos += [eqp.placa_teste(p.placa, sufixo) for p in body.placas]
        lidos = await eqp.dados_das_placas(alvos, falhas)
        for p in body.placas:
            ch = eqp.chave(p.placa)
            if lidos.get(ch):
                dados[ch] = lidos[ch]
            if sufixo:
                rec = lidos.get(eqp.chave_recipiente(p.placa, sufixo))
                if rec:
                    recipientes[ch] = rec
    elif sufixo:
        # Upgrade: o recipiente é criado junto com o termo, então o cache basta
        # -- monta o mesmo formato a partir dele.
        for p in body.placas:
            pt = eqp.placa_teste(p.placa, sufixo)
            serie = eqp.serie_de(seriais, pt)
            recipientes[eqp.chave(p.placa)] = {
                "descricao": eqp.descricao_da_placa(pt),
                "modelo": eqp.modelo_da_placa(pt),
                "serie": None if serie == eqp.MARCADOR_NAO_LOCALIZADO else serie,
            }

    # 🚨 PLACA FORA DO CACHE VAI AO VIVO, uma a uma. O cache atualiza as 04:15
    # e envelhece dentro do dia -- a etapa 3 acabou de criar a placa, e sem isto
    # a etapa 4 diria "sem equipamento" para um veiculo que tem.
    dados = await eqp.completar_do_vivo(todas, dados, falhas)

    return {"seriais": seriais, "dados": dados, "recipientes": recipientes,
            "falhas": falhas}


async def _preparar(body: "oos.MontarInput"):
    """Tudo que a montagem precisa. Não escreve em lugar nenhum."""
    if body.perfil not in cfg.PERFIS:
        raise HTTPException(400, f"Tipo de operação desconhecido: {body.perfil}")
    perfil = cfg.PERFIS[body.perfil]
    if not body.placas:
        raise HTTPException(400, "Nenhuma placa foi informada.")

    body.placas, avisos = oos.dedup_placas(body.placas)
    resolvidos, pendentes, descartados = await oos.resolver_vinculos(body.itens)

    # 🚨 SEPARA ANTES DE ALOCAR. A alocação por placa vale só para o que vai na
    # OS operacional; distribuir item de cobrança pelas placas o faria aparecer
    # nas DUAS OS -- que é o que a regra 7 acabou de proibir ao tirar o
    # `nas_duas`.
    itens_operacional, itens_financeiro = oos.separar_itens(perfil, resolvidos)
    alocacao, avisos_aloc = oos.alocar_itens_por_placa(
        itens_operacional, body.placas)
    avisos.extend(avisos_aloc)
    if descartados:
        avisos.append("Itens marcados NÃO CONTRATADO no termo, fora da OS: "
                      + "; ".join(descartados))

    ctx = await _ler_weso(body, perfil)
    # 🚨 A FALHA DE LEITURA VIRA AVISO NA TELA, NÃO SUMIÇO NO LOG. Não bloqueia
    # -- continua valendo "lacuna é melhor que apagar" -- mas a pessoa vê antes
    # de clicar em Gerar.
    avisos.extend(ctx["falhas"])

    # Sem "entrará" plausível, não inventa: o recipiente duvidoso é descartado
    # com aviso, e a OS sai sem o equipamento em vez de com um errado.
    ctx["recipientes"], avisos_rec = oos.conferir_recipientes(
        body, perfil, ctx["recipientes"])
    avisos.extend(avisos_rec)
    avisos.extend(oos.aviso_cobranca_sem_motivo(body, perfil, resolvidos))

    cabecalho, avisos_cab = {}, []
    if perfil.get("tipo_nome") or perfil.get("problema_nome"):
        cabecalho, avisos_cab = await _resolver_cabecalho_por_nome(perfil)
        avisos.extend(avisos_cab)

    return {"perfil": perfil, "alocacao": alocacao,
            "itens_financeiro": itens_financeiro, "resolvidos": resolvidos,
            "ctx": ctx, "avisos": avisos, "pendentes": pendentes,
            "descartados": descartados, "cabecalho": cabecalho}


def _montar_tudo(body: "oos.MontarInput", pre: dict) -> list[dict]:
    """A montagem, idêntica na prévia e na gravação."""
    operacoes = oos.montar(body, pre["perfil"], pre["alocacao"],
                           pre["itens_financeiro"], pre["resolvidos"],
                           pre["ctx"]["seriais"], pre["ctx"]["recipientes"],
                           pre["ctx"]["dados"])
    _aplicar_cabecalho(operacoes, pre["perfil"], pre["cabecalho"], body)
    return operacoes


async def _estado_das_placas(body: "oos.MontarInput", ctx: dict) -> list[dict]:
    """Por placa: tem modelo? se não, POR QUÊ, e precisa de seletor?"""
    nascidas = await _nascidas_no_lote(body.lote)
    houve_falha = bool(ctx["falhas"])
    saida = []
    for p in body.placas:
        d = ctx["dados"].get(eqp.chave(p.placa)) or {}
        modelo = d.get("modelo") or eqp.modelo_da_placa(p.placa)
        linha = {"placa": p.placa, "veiculo": p.veiculo,
                 "modelo_na_weso": modelo,
                 "modelo_escolhido": p.modelo_escolhido,
                 "precisa_escolher": False, "motivo": None, "recado": None}
        if not modelo:
            motivo = oos.motivo_sem_equipamento(p.placa, nascidas, houve_falha)
            linha["motivo"] = motivo
            linha["recado"] = oos.RECADO_SEM_EQUIPAMENTO[motivo]
            # 🚨 NÃO SE INVENTA. Sem escolha, a OS sai com o marcador e sem
            # material -- que é visível -- em vez de um modelo plausível e
            # errado, que não é.
            linha["precisa_escolher"] = not p.modelo_escolhido
        saida.append(linha)
    return saida


@router.post("/os/previa")
async def previa_os(body: oos.MontarInput, _=Depends(requer_aba("operacoes"))):
    """O que SERÁ gravado. Não escreve nada."""
    pre = await _preparar(body)
    estado = await _estado_das_placas(body, pre["ctx"])
    operacoes = _montar_tudo(body, pre)
    return {
        "perfil": body.perfil, "label": pre["perfil"]["label"],
        "operacoes": operacoes,
        "placas": estado,
        "avisos": pre["avisos"],
        # ⚠️ VÍNCULO PENDENTE NÃO É AVISO, É BLOQUEIO: item do termo sem vínculo
        # viraria OS sem o item, em silêncio.
        "pendentes": pre["pendentes"],
        "descartados": pre["descartados"],
        "falhas_de_leitura": pre["ctx"]["falhas"],
        "solucao_tecnica_preview": oos.formatar_solucao_tecnica(
            body.solucao_tecnica, body.observacao),
        "pode_gerar": not pre["pendentes"],
    }


async def _criar_uma_os(op: dict, solucao: str,
                        numero_na_descricao: bool = False) -> tuple[dict, int | None]:
    """Cria UMA OS no Harmonit: cabeçalho, materiais e técnico.

    ⚠️ NÃO LEVANTA. Erro vira campo do resultado, para uma OS que falha não
    derrubar as outras do mesmo termo.
    """
    payload = {
        "id": 0, "empresaId": 98, "clienteId": op["cliente_id"],
        "tipoId": op.get("tipo_id"), "problemaId": op["problema_id"],
        "situacaoId": op["situacao_id"],
        "produtoServicoId": op["produto_servico_id"],
        "prioridadeId": op["prioridade_id"],
        "descricaoDetalhada": op["descricao"], "solucaoTecnica": solucao,
    }
    try:
        r = await harmonit_post("/OrdemServico/SalvarOrdemServico", payload)
    except HTTPException as exc:
        return ({"placa": op["placa"], "rotulo": op.get("rotulo"),
                 "ok": False, "erro": exc.detail}, None)
    os_id, numero = r.get("id"), r.get("numeroOrdem")

    # 🚨 O NÚMERO DA PRÓPRIA OS NA DESCRIÇÃO custa uma SEGUNDA chamada -- por
    # isso não se faz nos perfis de contrato. Na manutenção o usuário pediu
    # igual à mão (as 14 OS abertas manualmente terminam com `O.S: nnnnn`),
    # aceitando a demora com a caixa de progresso.
    #
    # ⚠️ Regravar com `id` ATUALIZA, não duplica -- medido em 14/08 na OS de
    # teste 16755. É um save COMPLETO, então o payload vai inteiro: mandar só a
    # descrição limparia o resto.
    if numero_na_descricao and os_id and numero:
        nova = f"{op['descricao']} | O.S: {numero}"
        try:
            await harmonit_post("/OrdemServico/SalvarOrdemServico",
                                {**payload, "id": os_id, "numeroOrdem": numero,
                                 "descricaoDetalhada": nova})
            op["descricao"] = nova
        except HTTPException as exc:
            log.warning("operacoes: OS %s -- nao gravei o numero na descricao: %s",
                        numero, exc.detail)

    materiais_ok, materiais_erro = [], []
    for mat in op["materiais"]:
        try:
            await harmonit_post("/OrdemServico/SalvarMaterialOrdemServico", {
                "id": 0, "empresaId": 98, "osId": os_id,
                "produtoId": mat["harmonit_id"],
                "quantidade": mat.get("quantidade", 1),
                "valor": mat["valor_unitario"], "cobrar": mat["cobrar"],
                "comodato": mat["comodato"]})
            materiais_ok.append(mat["descricao"])
        except HTTPException as exc:
            materiais_erro.append(f"{mat['descricao']}: {exc.detail}")

    tecnico = None
    if op.get("tecnico_id"):
        try:
            await harmonit_post("/OrdemServico/SalvarTecnicoOrdemServico",
                                {"id": 0, "empresaId": 98, "osId": os_id,
                                 "tecnicoId": op["tecnico_id"]})
            tecnico = op["tecnico_id"]
        except HTTPException as exc:
            materiais_erro.append(f"técnico {op['tecnico_id']}: {exc.detail}")

    return ({"placa": op["placa"], "rotulo": op.get("rotulo"),
             "os_id": os_id, "numero_ordem": numero, "ok": True,
             "materiais_ok": materiais_ok, "materiais_erro": materiais_erro,
             "tecnico": tecnico}, numero)


@router.post("/os/gerar")
async def gerar_os(body: oos.MontarInput, _=Depends(requer_aba("operacoes"))):
    """Grava as OS no Harmonit. ESCREVE."""
    if not body.confirmar:
        raise HTTPException(400,
            "A geração exige confirmação explícita. Use a prévia para conferir "
            "e mande `confirmar` quando for gravar.")

    pre = await _preparar(body)
    # ⚠️ PENDENTE BLOQUEIA. Item do termo sem vínculo sairia da OS em silêncio,
    # e OS incompleta ninguém percebe até a cobrança não bater.
    if pre["pendentes"]:
        raise HTTPException(422,
            "Há itens do termo sem vínculo no catálogo do Harmonit — a OS "
            "sairia sem eles, e ninguém veria: " + "; ".join(pre["pendentes"]))

    operacoes = _montar_tudo(body, pre)
    solucao = oos.formatar_solucao_tecnica(body.solucao_tecnica, body.observacao)
    numero_na_desc = bool(pre["perfil"].get("numero_na_descricao"))

    # 🚨 FASE DUPLA. Operacionais primeiro, colhendo os números; a financeira
    # depois, citando esses números na solução técnica. Assim ela aponta as OS
    # de instalação/serviço geradas pelo mesmo termo -- que é o que faz a
    # cobrança ser conferível placa a placa.
    operacionais = [o for o in operacoes if not o.get("eh_financeira")]
    financeiras = [o for o in operacoes if o.get("eh_financeira")]

    criadas, numeros = [], []
    for op in operacionais:
        resultado, numero = await _criar_uma_os(op, solucao, numero_na_desc)
        criadas.append(resultado)
        if numero:
            numeros.append(str(numero))

    for fin in financeiras:
        nums = ", ".join(f"nº {n}" for n in numeros) or "(nenhuma)"
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        solucao_fin = (f"[{agora}] {len(numeros)} OS de instalação/serviço "
                       f"geradas neste termo: {nums}")
        resultado, _n = await _criar_uma_os(fin, solucao_fin)
        criadas.append(resultado)

    if body.lote:
        for r in criadas:
            await reg.registrar(
                body.lote, 4, "harmonit",
                "criado" if r.get("ok") else "falhou",
                placa_gravada=r.get("placa"), descricao=r.get("rotulo"),
                id_externo=r.get("os_id"), erro=r.get("erro"))

    if body.lote:
        await reg.encerrar(body.lote)

    pendencias = await _gravar_pendencias(body, pre, operacionais, criadas)

    return {"criadas": criadas, "avisos": pre["avisos"],
            "pendencias": pendencias,
            "falhas_de_leitura": pre["ctx"]["falhas"],
            "total": len(criadas),
            "com_erro": sum(1 for r in criadas if not r.get("ok"))}


async def _gravar_pendencias(body: "oos.MontarInput", pre: dict,
                             operacionais: list[dict],
                             criadas: list[dict]) -> list[dict]:
    """Grava o que a rotina (F5) vai ter de terminar depois.

    🚨 QUEM SABE É QUEM GEROU. Seis horas depois, a rotina não tem como saber
    qual OS estava esperando qual recipiente -- deduzir pela descrição é frágil
    e falha calado, que é a família de defeito mais cara deste projeto.

    Só OS criada com sucesso vira pendência: uma OS que falhou não deixou nada
    pendente, deixou um erro, e esse já está no registro do lote.

    Os quatro casos vêm do PERFIL, nunca do nome da placa:
      `libera_serie` .......... recipiente a devolver e apagar
      `desativa_apos_oficina` . rescisão e ressarcimento
      `vincula_apos_oficina` .. substituição, a única que vincula
    """
    perfil = pre["perfil"]
    recipientes = pre["ctx"]["recipientes"]
    pendencias: list[dict] = []

    # As criadas vêm na MESMA ordem das operacionais -- a financeira entra
    # depois, e por isso `criadas` é cortado no tamanho de `operacionais`.
    for op, criada in zip(operacionais, criadas):
        if not criada.get("ok"):
            continue

        caso = None
        if perfil.get("libera_serie") and perfil.get("placa_teste_sufixo"):
            caso = "recipiente"
        elif perfil.get("vincula_apos_oficina"):
            caso = "substituicao"
        elif perfil.get("desativa_apos_oficina"):
            caso = ("ressarcimento" if perfil.get("hibrida") else "rescisao")
        if not caso:
            continue

        rec = recipientes.get(eqp.chave(op.get("placa") or "")) or {}
        # ⚠️ Na substituição a OS de RETIRADA é a que carrega a pendência: é
        # dela que sai o equipamento. A de instalação recebe, e recebe pela
        # mesma linha -- por isso `placa_entrada` viaja junto.
        if caso == "substituicao" and op.get("rotulo") != "Retirada":
            continue

        entrada = next((p.placa_entrada for p in body.placas
                        if p.placa == op.get("placa")), None)
        novo = await esp.registrar(
            lote=body.lote, perfil=body.perfil, caso=caso,
            os_id=criada.get("os_id"), numero_os=criada.get("numero_ordem"),
            placa=op.get("placa") or "", placa_entrada=entrada,
            recipiente_placa=(eqp.placa_teste(op.get("placa") or "",
                                              perfil["placa_teste_sufixo"])
                              if perfil.get("placa_teste_sufixo") else None),
            veiculo_id=rec.get("veiculo_id"),
            rastreador_id=rec.get("rastreador_id"))
        if novo:
            pendencias.append({"id": novo, "caso": caso,
                               "placa": op.get("placa"),
                               "numero_os": criada.get("numero_ordem")})
    return pendencias


@router.get("/pendencias")
async def listar_pendencias(caso: str | None = Query(None),
                            _=Depends(requer_aba("operacoes"))):
    """O que a rotina ainda deve, e o que ela desistiu de tentar."""
    return {"pendentes": await esp.pendentes(caso), "resumo": await esp.resumo(),
            "teto_tentativas": esp.TETO_TENTATIVAS}


@router.post("/rotina/rodar")
async def rodar_rotina(caso: str | None = Query(None),
                       _=Depends(requer_aba("operacoes"))):
    """Roda uma passada da rotina agora, sem esperar as 6 h.

    ⚠️ MESMA FUNÇÃO DO LAÇO. Um caminho manual que faça algo diferente do
    automático é um caminho que ninguém testa de verdade -- e o que se prova
    clicando deixa de valer para o que roda de madrugada.
    """
    return await rot.rodar(caso)


# ── apoio da etapa 4: as listas que os seletores consomem ───────────────────
#
# 🚨 PREFIXO PRÓPRIO, e não é preciosismo. As equivalentes do `os_router`
# exigem `gerar_os` — quem tem só `operacoes` toma 403 nas três, e isso só
# apareceria ao usar a tela. Aqui elas nascem sob `operacoes`, e quando as
# telas velhas saírem (F7) nenhuma rota desta aba muda de endereço.


@router.get("/placas/do-cliente")
async def placas_do_cliente(cliente_harmonit_id: int = Query(...),
                            _=Depends(requer_aba("operacoes"))):
    """As placas do cliente, da base local, para os perfis SEM TERMO.

    Devolve também `atualizada_em` para a tela poder dizer de quando é o dado.
    Lista que não diz a própria idade é lista em que se confia demais.
    """
    def _ler():
        with storage._connect() as conn:
            linhas = conn.execute(
                "SELECT placa, veiculo FROM harmonit_veiculos "
                "WHERE clienteId = ? ORDER BY placa", (cliente_harmonit_id,)
            ).fetchall()
        return [{"placa": p, "veiculo": v} for p, v in linhas]

    veiculos = await asyncio.get_running_loop().run_in_executor(None, _ler)
    return {"veiculos": veiculos, "total": len(veiculos)}


@router.get("/clientes/buscar")
async def buscar_cliente(q: str = Query(..., min_length=3),
                         _=Depends(requer_aba("operacoes"))):
    """Cliente por nome, CNPJ ou CPF -- para TROCAR o que veio do termo.

    🚨 O TERMO MANDA, MAS NÃO É INFALÍVEL (decisão do usuário, 21/08): "o
    painel importa do termo e confirma, como no Gerar OS, mas é possível mudar
    pelo painel sim". Até aqui a etapa 2 só mostrava o resultado do cruzamento
    e não oferecia saída nenhuma quando ele vinha errado.

    ⚠️ MÍNIMO DE 3 CARACTERES, igual ao Gerar OS: `search` de 1 letra no
    `/ObterClientes` devolve a base com cara de resposta útil.

    🚨 DOCUMENTO ANTES DE NOME. Se o que foi digitado tem 11 ou 14 dígitos, é
    documento e a consulta é exata -- cruzar por nome é proibido nesta casa, e
    o mesmo CNPJ tem razão social diferente nos dois sistemas.
    """
    so_digitos = "".join(c for c in q if c.isdigit())
    if len(so_digitos) in (11, 14):
        achado = await _no_harmonit(so_digitos)
        if achado:
            return {"resultados": [{"id": achado.get("id"),
                                    "nome": achado.get("nome"),
                                    "documento": achado.get("cnpJ_CPF")}],
                    "por_documento": True}

    r = await harmonit_get("/ObterClientes",
                           params={"skip": 0, "take": 15, "search": q})
    itens = (r.get("lista") if isinstance(r, dict) else r) or []
    return {"resultados": [{"id": i.get("id"), "nome": i.get("nome"),
                            "documento": i.get("cnpJ_CPF") or i.get("cnpjCpf")}
                           for i in itens],
            "por_documento": False}


@router.get("/servicos/buscar")
async def buscar_servico(q: str = Query("", min_length=0),
                         _=Depends(requer_aba("operacoes"))):
    """Serviços do Harmonit para o Produto/Serviço do cabeçalho da OS."""
    params = {"skip": 0, "take": 30}
    if q:
        params["search"] = q
    r = await harmonit_get("/Produto/ObterServicos", params=params)
    itens = (r.get("data") if isinstance(r, dict) else r) or []
    return {"resultados": [{"id": i.get("id"), "descricao": i.get("descricao"),
                            "grupo": i.get("grupo")} for i in itens]}


@router.get("/prioridades")
async def listar_prioridades(_=Depends(requer_aba("operacoes"))):
    """Prioridade das OS OPERACIONAIS. A financeira é sempre Normal (regra 5).

    ⚠️ Lista muda não trava a tela: ela cai no padrão Normal, que é o que a
    esmagadora maioria das OS usa de qualquer forma.
    """
    lista = await _lista_do_harmonit("/PrioridadeAtendimento/ObterPrioridades")
    return {"default": cfg.PRIORIDADE_NORMAL_ID,
            "prioridades": [{"id": i.get("id"),
                             "descricao": i.get("descricao") or i.get("nome")}
                            for i in (lista or []) if i.get("id")]}


@router.get("/problemas")
async def listar_problemas(_=Depends(requer_aba("operacoes"))):
    """Problemas do Harmonit — só os perfis SEM TERMO mostram este seletor.

    🚨 Num contrato o problema é ditado pelo documento; oferecer escolha ali
    só convidaria a OS a divergir do papel assinado. Quem aplica essa distinção
    é `_aplicar_cabecalho`.
    """
    lista = await _lista_do_harmonit("/Problema/ObterProblemas")
    if lista is None:
        raise HTTPException(502, "A lista de Problemas do Harmonit não respondeu.")
    return {"problemas": [{"id": p.get("id"), "descricao": p.get("descricao")}
                          for p in lista if p.get("id")]}


@router.get("/historico")
async def historico(limite: int = Query(100, le=500),
                    _=Depends(requer_aba("operacoes"))):
    """O que esta aba fez, e o que a rotina ainda deve.

    🚨 AS PENDENCIAS VEM JUNTO, E NAO NUMA TELA A PARTE. Pendencia que
    `desistiu` e o unico jeito de alguem saber que um recipiente ficou preso ou
    que uma oficina nunca chegou -- se ela morar noutro lugar, ninguem abre.
    """
    return {"lotes": await reg.listar_lotes(limite),
            "pendentes": await esp.pendentes(),
            "resumo_pendencias": await esp.resumo(),
            "teto_tentativas": esp.TETO_TENTATIVAS}
