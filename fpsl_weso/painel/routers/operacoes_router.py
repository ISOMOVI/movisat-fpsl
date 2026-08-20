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
from .. import operacoes_registro as reg
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
# só, em `operacoes_os.montar`. Prévia que reconstrói o resultado por conta
# própria é prévia que mente, e o operador confia nela justamente por ser a
# última coisa que ele vê antes de escrever em dois sistemas.


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


async def _preparar(body: "oos.MontarInput"):
    """Tudo que a montagem precisa: vínculos, alocação e o que a WESO diz.

    Devolve (perfil, alocacao, resolvidos, contexto, avisos, pendentes,
    descartados). Não escreve em lugar nenhum.
    """
    if body.perfil not in cfg.PERFIS:
        raise HTTPException(400, f"Tipo de operação desconhecido: {body.perfil}")
    perfil = cfg.PERFIS[body.perfil]
    if not body.placas:
        raise HTTPException(400, "Nenhuma placa foi informada.")

    body.placas, avisos = oos.dedup_placas(body.placas)
    resolvidos, pendentes, descartados = await oos.resolver_vinculos(body.itens)

    # 🚨 SEPARA ANTES DE ALOCAR. A alocação por placa vale só para o que
    # vai na OS operacional; distribuir item de cobrança pelas placas o
    # faria aparecer nas DUAS OS -- que é o que a regra 7 acabou de
    # proibir ao tirar o `nas_duas`.
    itens_operacional, itens_financeiro = oos.separar_itens(perfil, resolvidos)
    alocacao, avisos_aloc = oos.alocar_itens_por_placa(
        itens_operacional, body.placas)
    avisos.extend(avisos_aloc)
    if descartados:
        avisos.append("Itens marcados NÃO CONTRATADO no termo, fora da OS: "
                      + "; ".join(descartados))

    # 🚨 A FALHA DE LEITURA VIRA AVISO NA TELA, NÃO SUMIÇO NO LOG. As cinco
    # funções de `equipamentos` anotam nesta lista; o que estiver aqui aparece
    # ANTES do botão Gerar. Não bloqueia -- continua valendo "lacuna é melhor
    # que apagar" -- mas a pessoa vê.
    falhas: list[str] = []
    placas_txt = [p.placa for p in body.placas]
    entradas = [p.placa_entrada for p in body.placas if p.placa_entrada]

    seriais = await eqp.buscar_seriais(placas_txt + entradas, falhas)
    dados = await eqp.dados_das_placas(placas_txt + entradas, falhas)
    recipientes = {}
    if perfil.get("placa_teste_sufixo"):
        recipientes = await eqp.buscar_recipientes(
            placas_txt, perfil["placa_teste_sufixo"])

    contexto = {"seriais": seriais, "dados": dados, "recipientes": recipientes,
                "falhas": falhas}
    return (perfil, alocacao, itens_financeiro, resolvidos, contexto,
            avisos, pendentes, descartados)


async def _estado_das_placas(body: "oos.MontarInput", perfil: dict,
                             contexto: dict) -> list[dict]:
    """Por placa: tem modelo? se não, POR QUÊ, e precisa de seletor?"""
    nascidas = await _nascidas_no_lote(body.lote)
    houve_falha = bool(contexto["falhas"])
    saida = []
    for p in body.placas:
        d = contexto["dados"].get(eqp.chave(p.placa)) or {}
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
    (perfil, alocacao, itens_financeiro, resolvidos, ctx, avisos,
     pendentes, descartados) = await _preparar(body)

    estado = await _estado_das_placas(body, perfil, ctx)
    operacoes = oos.montar(body, perfil, alocacao, itens_financeiro,
                           resolvidos, ctx["seriais"], ctx["recipientes"],
                           ctx["dados"])

    return {
        "perfil": body.perfil, "label": perfil["label"],
        "operacoes": operacoes,
        "placas": estado,
        "avisos": avisos,
        # ⚠️ VÍNCULO PENDENTE NÃO É AVISO, É BLOQUEIO. Item do termo sem
        # vínculo viraria OS sem o item, em silêncio.
        "pendentes": pendentes,
        "descartados": descartados,
        "falhas_de_leitura": ctx["falhas"],
        "pode_gerar": not pendentes,
    }


async def _criar_uma_os(op: dict, solucao: str) -> dict:
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
        return {"placa": op["placa"], "rotulo": op.get("rotulo"),
                "ok": False, "erro": exc.detail}
    os_id, numero = r.get("id"), r.get("numeroOrdem")

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

    return {"placa": op["placa"], "rotulo": op.get("rotulo"),
            "os_id": os_id, "numero_ordem": numero, "ok": True,
            "materiais_ok": materiais_ok, "materiais_erro": materiais_erro,
            "tecnico": tecnico}


@router.post("/os/gerar")
async def gerar_os(body: oos.MontarInput, usuario=Depends(requer_aba("operacoes"))):
    """Grava as OS no Harmonit. ESCREVE."""
    if not body.confirmar:
        raise HTTPException(400,
            "A geração exige confirmação explícita. Use a prévia para conferir "
            "e mande `confirmar` quando for gravar.")

    (perfil, alocacao, itens_financeiro, resolvidos, ctx, avisos,
     pendentes, descartados) = await _preparar(body)

    # ⚠️ PENDENTE BLOQUEIA. Item do termo sem vínculo sairia da OS em silêncio,
    # e OS incompleta ninguém percebe até a cobrança não bater.
    if pendentes:
        raise HTTPException(422,
            "Há itens do termo sem vínculo no catálogo do Harmonit — a OS "
            "sairia sem eles, e ninguém veria: " + "; ".join(pendentes))

    operacoes = oos.montar(body, perfil, alocacao, itens_financeiro,
                           resolvidos, ctx["seriais"], ctx["recipientes"],
                           ctx["dados"])
    solucao = oos.formatar_solucao_tecnica(body.solucao_tecnica, body.observacao)

    criadas = []
    for op in operacoes:
        criadas.append(await _criar_uma_os(op, solucao))

    if body.lote:
        for r in criadas:
            await reg.registrar(
                body.lote, 4, "harmonit",
                "criado" if r.get("ok") else "falhou",
                placa_gravada=r.get("placa"),
                descricao=r.get("rotulo"),
                id_externo=r.get("os_id"), erro=r.get("erro"))

    return {"criadas": criadas, "avisos": avisos,
            "falhas_de_leitura": ctx["falhas"],
            "total": len(criadas),
            "com_erro": sum(1 for r in criadas if not r.get("ok"))}
