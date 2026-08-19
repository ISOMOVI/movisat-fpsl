"""Cadastro de placas na WESO a partir do termo, ou do chamado de manutencao.

🚨 POR QUE ESTA ABA EXISTE (decisao do usuario, 17/08). As placas que o termo
lista sao digitadas uma a uma na WESO por alguem, e os recipientes de teste
(`<PLACA>-UPGRADE`, `<PLACA>-MANUT`) nascem do mesmo jeito. O termo ja tem
todas, e o extrator ja as le -- o trabalho manual so existe porque nunca houve
tela para isso.

O QUE ESTA ABA NAO E. Nao existe "criacao de recipiente": recipiente e uma
placa cujo texto tem sufixo. Medido em 17/08 -- `TST 0A11` e `TST0A11-MANUT`
nasceram da MESMA chamada `/Veiculos/Cadastro`, mudando duas strings. Por isso
aqui ha um caminho de criacao so.

AS DUAS ORIGENS, e por que sao diferentes de verdade
-----------------------------------------------------
1. **COM TERMO** (upgrade e os perfis de contrato): as placas vem do PDF. O
   cliente pode nao existir na WESO ainda -- e cliente novo so tem equipamento
   depois desta etapa.
2. **SEM TERMO** (manutencao no local e com troca): nao ha documento. O
   operador digita a placa do chamado e o painel deriva o recipiente. Aqui o
   cliente SEMPRE existe -- e cliente com equipamento em campo -- e a placa
   real tambem. So o recipiente nasce.

AS TRAVAS, e o que cada uma impede
-----------------------------------
1. **O payload da placa manda SO o CNPJ do cliente, nunca os dados dele.**
   A WESO CRIA CLIENTE SOZINHA se receber `cliente` completo com documento
   desconhecido -- e o `objetos_processados` da resposta diz `"Criado"` mesmo
   quando reusou (medido em 17/08 com a Velasco, que continuou unica). Ou seja:
   um cliente poderia nascer sem nunca ter aparecido no resumo, e a resposta
   nao denunciaria. Mandando so o documento, criar cliente vira ato separado.

2. **A descricao do recipiente e CONTRATO com o gerador de OS**, nao enfeite.
   `manutencao_troca` procura recipiente com descricao `MANUTENCAO`;
   `upgrade` procura `TERMO {termo}`. Gravar outra coisa faz a geracao seguinte
   nao reconhecer o recipiente e cair em "sem serie", em silencio. Por isso a
   descricao do recipiente e DERIVADA aqui, nao digitada.

3. **Nada e gravado sem passar pela previa.** `/previa` nao escreve nada e diz,
   placa por placa, o que aconteceria. E o ponto de decisao.

4. **Sem interruptor. Subir o termo GRAVA** (decisao do usuario, 19/08:
   "se subir por la ele deve funcionar como rotina nativa"). O `/previa` do
   item 3 e o ponto de decisao -- ele existe justamente para que nao seja
   preciso um segundo botao de seguranca em cima do primeiro.
   ⚠️ Existiu um `placas_registro_ativo` de 17 a 19/08. Ele **nunca teve UI**:
   a tela de Configuracoes dizia "nenhum interruptor configuravel" enquanto o
   Cadastro de Placas mandava o operador procurar la. Interruptor sem tela e
   pior que interruptor nenhum -- parece uma trava e nao e.
"""
import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ..auth import requer_aba
from ...client import weso_get, weso_post
import time

from ...harmonit_client import harmonit_get, harmonit_post
from ...weso_lookup import buscar_veiculo
from ... import placas as regra_placa
from ... import storage
from ..equipamentos import placa_teste
from ..pdf_extractor import extrair_campos
from ..templates_config import PERFIS

log = logging.getLogger(__name__)
router = APIRouter(prefix="/painel/api/placas", tags=["placas"])

CACHE_DIR = "/home/claude/weso_cache"

# Sufixo -> descricao que o gerador de OS confere. Ver trava 2 no topo.
# 🚨 `MANUTENCAO` sem cedilha e sem til: e assim que os 5 recipientes existentes
# estao gravados na WESO. O `_norm_desc` do gerador dobra acento, entao os dois
# casariam de qualquer forma -- mas gravar na grafia que ja existe evita que a
# base fique com duas versoes do mesmo texto.
DESCRICAO_DO_SUFIXO = {
    "-MANUT": "MANUTENCAO",
    "-UPGRADE": "TERMO {termo}",
}

# `tipoEqp` 11 = Bancada na tabela da WESO. E o que um recipiente e: bancada do
# setor de configuracao, nao veiculo. Medido em 17/08 -- o cadastro aceitou e
# gravou `complemento_id`.
TIPO_BANCADA = 11


def _cache():
    """Modulo do cache local, ou None. Nunca levanta: o cache e atalho."""
    import sys
    try:
        if CACHE_DIR not in sys.path:
            sys.path.insert(0, CACHE_DIR)
        import cache  # noqa: PLC0415
        return cache
    except Exception as exc:
        log.warning("placas: cache indisponivel (%s), indo tudo ao vivo", exc)
        return None


class ItemPlaca(BaseModel):
    placa: str
    descricao: str | None = None
    # Quando preenchido, esta linha e um RECIPIENTE e a descricao e derivada.
    sufixo: str | None = None
    # So usado quando o sufixo e `-UPGRADE`, para montar `TERMO {termo}`.
    termo: str | None = None


class PreviaInput(BaseModel):
    cnpjcpf: str
    itens: list[ItemPlaca]


class CriarInput(PreviaInput):
    pass


def _descricao_final(item: ItemPlaca) -> tuple[str | None, str | None]:
    """(descricao, erro). Recipiente tem descricao DERIVADA, nao digitada."""
    if not item.sufixo:
        return (item.descricao or None), None
    modelo = DESCRICAO_DO_SUFIXO.get(item.sufixo.upper())
    if not modelo:
        return None, (f"sufixo {item.sufixo!r} nao tem descricao definida — "
                      f"conhecidos: {', '.join(sorted(DESCRICAO_DO_SUFIXO))}")
    if "{termo}" in modelo:
        if not (item.termo or "").strip():
            return None, ("recipiente de upgrade exige o numero do termo — "
                          "sem ele a geracao da OS nao reconhece o recipiente")
        return modelo.format(termo=item.termo.strip()), None
    return modelo, None


def _texto_gravado(item: ItemPlaca) -> str:
    """Como a placa vai ficar escrita na WESO.

    🚨 NAO E O QUE O USUARIO DIGITOU. `placas.formatar` poe espaco na placa
    convencional (`TST0A11` -> `TST 0A11`) e deixa a nao-convencional intacta
    (`TST0A11-MANUT`). Medido em 17/08: por isso a placa real e o recipiente
    dela tem grafias DIFERENTES na base, e a consulta por placa e igualdade
    exata. A tela mostra este valor para ninguem se assustar depois.
    """
    if item.sufixo:
        return placa_teste(item.placa, item.sufixo.upper())
    return regra_placa.formatar(item.placa) or item.placa.strip().upper()


async def _cliente_na_weso(cnpjcpf: str) -> dict | None:
    doc = str(cnpjcpf or "").strip()
    if not doc:
        return None
    r = await weso_get("/Clientes/Consultar", {"cnpjcpf": doc})
    lista = (r.get("clientes") if isinstance(r, dict) else r) or []
    return lista[0] if lista else None


async def _situacao_das_placas(textos: list[str]) -> dict:
    """Para cada texto: existe na WESO? Cache primeiro, ao vivo o que faltar.

    🚨 O CACHE NAO PODE DECLARAR AUSENCIA. Ele e de 04:15; placa criada depois
    nao esta la, e oferecer criar uma placa que ja existe e pior que demorar.
    Entao: quem o cache ACHA esta resolvido; quem ele NAO acha vai ao vivo.

    ⚠️ Ir ao vivo custa. `buscar_veiculo` tenta a consulta exata e, se falhar,
    baixa a base inteira -- que hoje leva 16 a 33s (a medicao de 29/07 dizia
    2,3s e envelheceu). Por isso o cache vem primeiro, e nao o contrario.
    """
    fora = {}
    c = _cache()
    faltam = []
    for t in textos:
        achou = None
        if c is not None:
            try:
                achou = c.veiculo_por_placa(t)
            except Exception as exc:
                log.warning("placas: cache falhou em %r: %s", t, exc)
        if achou:
            fora[t] = {"existe": True, "onde": "cache",
                       "veiculo_id": achou.get("id"),
                       "descricao_atual": achou.get("descricao"),
                       "rastreador_id": achou.get("rastreador_id")}
        else:
            faltam.append(t)

    # 🚨 UMA LEITURA PARA TODOS OS QUE FALTAM, nao uma por placa.
    #
    # A versao anterior chamava `buscar_veiculo` por placa. Quando a consulta
    # exata nao acha -- que e o caso NORMAL desta tela, placa nova -- ele baixa
    # a BASE INTEIRA da WESO: 18,6s medidos em 17/08, 16 a 33s em 14/08. Com o
    # timeout do cliente em 30s, o limite superior estoura, e a conferencia
    # vira "nao consegui conferir" para placa que so nao existe ainda.
    #
    # Um termo de 11 placas novas fazia 11 downloads da base inteira. Agora e
    # um, guardado em memoria com validade curta -- mesmo padrao do espelho do
    # Harmonit logo abaixo.
    if faltam:
        try:
            base = await _base_weso()
        except HTTPException as exc:
            # NAO SEI e diferente de NAO EXISTE. Declarar ausencia por falha de
            # rede faria a tela oferecer criar placa que existe.
            for t in faltam:
                fora[t] = {"existe": None, "onde": "indisponivel",
                           "erro": f"nao consegui conferir na WESO: {exc.detail}"}
            return fora
        porchave = {_chave(v.get("placa")): v for v in base}
        for t in faltam:
            v = porchave.get(_chave(t))
            if v:
                fora[t] = {"existe": True, "onde": "ao_vivo",
                           "veiculo_id": v.get("id"),
                           "descricao_atual": v.get("descricao"),
                           "rastreador_id": v.get("rastreador_id")}
            else:
                fora[t] = {"existe": False, "onde": "ao_vivo"}
    return fora


# Espelho da base da WESO, irmao do `_base_harmonit`.
# ⚠️ 18,6s para 1.969 veiculos, contra 1,9s para os 9.107 do Harmonit -- a WESO
# e DEZ VEZES mais lenta com cinco vezes menos registros. Por isso o cache
# local (`weso_cache/weso.db`, cron 04:15) continua sendo consultado primeiro:
# ele resolve em ~1ms o que ja existia ontem.
_WESO_BASE: list | None = None
_WESO_EM: float = 0.0
_WESO_TTL = 120.0


async def _conferir_na_weso(texto: str) -> dict | None:
    """Relê UMA placa pela consulta exata. Rápido de propósito.

    🚨 NÃO USA `buscar_veiculo`. Ele tenta o exato e, falhando, baixa a base
    inteira (18,6s) -- caminho que a releitura pós-gravação NUNCA precisa, já
    que a placa acabou de ser escrita com a grafia exata que se procura.
    Medido: 0,2s por esta via contra 15 a 36s pela outra.

    ⚠️ NÃO ACHOU = NÃO GRAVOU. É a resposta certa, e foi assim que se descobriu
    que a `CHASSI: 9BD281AJPTYBM7701` nasceu no Harmonit e não na WESO.
    """
    r = await weso_get("/Veiculos/Consultar", {"placa": texto})
    achados = (r.get("veiculos") if isinstance(r, dict) else r) or []
    return achados[0] if achados else None


def _espelho_aprende(veiculo: dict) -> None:
    """Acrescenta ao espelho o que acabou de nascer.

    🚨 SEM ISTO O ESPELHO MENTE POR ATÉ 120s. Medido em 17/08: depois de criar
    quatro placas, a prévia respondeu `criar: 4` para as MESMAS quatro -- num
    segundo clique tentaria duplicar o que já existia.
    """
    global _WESO_BASE
    if _WESO_BASE is None or not veiculo:
        return
    alvo = _chave(veiculo.get("placa"))
    if not any(_chave(v.get("placa")) == alvo for v in _WESO_BASE):
        _WESO_BASE.append(veiculo)


async def _base_weso(forcar: bool = False) -> list:
    global _WESO_BASE, _WESO_EM
    if (not forcar and _WESO_BASE is not None
            and (time.monotonic() - _WESO_EM) < _WESO_TTL):
        return _WESO_BASE
    r = await weso_get("/Veiculos/Consultar", {})
    _WESO_BASE = (r.get("veiculos") if isinstance(r, dict) else r) or []
    _WESO_EM = time.monotonic()
    return _WESO_BASE


def _montar(body: PreviaInput, situacao: dict) -> list[dict]:
    # 🚨 A MESMA PLACA PODE VIR VARIAS VEZES. `ABC1D23`, `abc1d23` e `ABC 1D23`
    # sao a mesma coisa depois de formatadas, e a situacao e lida UMA vez, antes
    # de gravar -- entao as tres diriam "vai ser criada", a primeira criaria e
    # as outras duas entrariam na contagem de criadas sem terem criado nada.
    # A partir da segunda, a linha e marcada como `duplicada` e nao grava.
    linhas = []
    vistos = set()
    for item in body.itens:
        texto = _texto_gravado(item)
        descricao, erro = _descricao_final(item)
        s = situacao.get(texto, {"existe": None, "onde": "nao_conferido"})
        if erro:
            acao = "recusar"
        elif texto in vistos:
            acao = "duplicada"
        elif s["existe"] is None:
            acao = "indisponivel"
        elif s["existe"]:
            acao = "ja_existe"
        else:
            acao = "criar"
        linhas.append({
            "placa_digitada": item.placa,
            "placa_gravada": texto,
            "recipiente": bool(item.sufixo),
            "descricao": descricao,
            "acao": acao,
            "erro": erro or s.get("erro"),
            "conferido_em": s.get("onde"),
            "repetida_de": texto if acao == "duplicada" else None,
            "veiculo_id": s.get("veiculo_id"),
            "descricao_atual": s.get("descricao_atual"),
            "rastreador_id": s.get("rastreador_id"),
        })
        vistos.add(texto)
    return linhas


@router.post("/previa")
async def previa(body: PreviaInput, _=Depends(requer_aba("cadastro_placas"))):
    """O que aconteceria. NAO ESCREVE NADA."""
    if not body.itens:
        raise HTTPException(400, "Nenhuma placa informada.")

    cliente = await _cliente_na_weso(body.cnpjcpf)
    situacao = await _situacao_das_placas(
        [_texto_gravado(i) for i in body.itens])
    linhas = _montar(body, situacao)

    contagem = {}
    for l in linhas:
        contagem[l["acao"]] = contagem.get(l["acao"], 0) + 1

    return {
        "cliente": {
            "cnpjcpf": body.cnpjcpf,
            "existe_na_weso": bool(cliente),
            "id": (cliente or {}).get("id"),
            "razao_social": (cliente or {}).get("razaoSocial"),
            "situacao": (cliente or {}).get("situacao"),
        },
        # ⚠️ Cliente ausente NAO bloqueia: a WESO vincula pelo CNPJ e, se ele
        # nao existir, a placa nao nasce -- o erro aparece por placa. Bloquear
        # aqui esconderia o resto da conferencia, que e o que a tela quer ver.
        "aviso_cliente": None if cliente else (
            f"O CNPJ {body.cnpjcpf} nao esta na WESO. Cadastre o cliente antes, "
            f"senao nenhuma placa vai nascer."),
        "itens": linhas,
        "resumo": contagem,
    }


@router.post("/criar")
async def criar(body: CriarInput, _=Depends(requer_aba("cadastro_placas"))):
    """Cria as que faltam. Reconfere ANTES e RELE DEPOIS."""
    if not body.itens:
        raise HTTPException(400, "Nenhuma placa informada.")

    cliente = await _cliente_na_weso(body.cnpjcpf)
    # 🚨 AGORA BLOQUEIA DE VERDADE. Com o interruptor, esta trava so valia com a
    # escrita ligada -- sem cliente na WESO nenhuma placa nasce, e deixar seguir
    # produzia um lote inteiro de falhas placa a placa em vez de um erro so.
    if not cliente:
        raise HTTPException(422,
            f"O CNPJ {body.cnpjcpf} nao esta na WESO. Cadastre o cliente antes.")

    # 🚨 RECONFERE. A previa pode ter sido vista ha minutos e alguem pode ter
    # criado a placa nesse meio tempo -- e criar em cima devolve 409.
    situacao = await _situacao_das_placas(
        [_texto_gravado(i) for i in body.itens])
    linhas = _montar(body, situacao)

    resultados = []
    for item, linha in zip(body.itens, linhas):
        if linha["acao"] != "criar":
            resultados.append({**linha, "ok": linha["acao"] == "ja_existe",
                               "gravou": False})
            continue

        equipamento = {
            "placa": linha["placa_gravada"],
            # trava 1: SO o documento. Nunca os dados do cliente.
            "cliente": {"cnpjcpf": body.cnpjcpf},
        }
        if linha["descricao"]:
            equipamento["descricao"] = linha["descricao"]
        if linha["recipiente"]:
            equipamento["complemento"] = {"tipoEqp": TIPO_BANCADA}

        try:
            r = await weso_post("/Veiculos/Cadastro", {"equipamento": equipamento},
                                allow_409=True)
        except HTTPException as exc:
            resultados.append({**linha, "ok": False, "gravou": False,
                               "erro": f"a WESO recusou: {exc.detail}"})
            continue

        # 🚨 A PROVA E RELER. `objetos_processados` mente (diz "Criado" para
        # cliente reusado) e este projeto ja viu 200 que nao gravou nada.
        conferido = await _conferir_na_weso(linha["placa_gravada"])
        if conferido:
            _espelho_aprende(conferido)
            resultados.append({**linha, "ok": True, "gravou": True,
                               "veiculo_id": conferido.get("id"),
                               "ja_existia": bool(r.get("_ja_existe")),
                               "verificado_relendo": True})
        else:
            resultados.append({**linha, "ok": False, "gravou": False,
                               "erro": "a WESO respondeu sem erro mas a placa "
                                       "nao aparece na releitura",
                               "verificado_relendo": True})

    return {
        "cliente_id": (cliente or {}).get("id"),
        "itens": resultados,
        "criadas": sum(1 for r in resultados if r.get("gravou")),
        "ja_existiam": sum(1 for r in resultados if r["acao"] == "ja_existe"),
        "falharam": sum(1 for r in resultados if not r.get("ok")),
    }


# ── ler o termo (passo 2) ────────────────────────────────────────────────────
#
# 🚨 ENDPOINT PRÓPRIO, e não `requer_aba("gerar_os", "cadastro_placas")` no
# `/painel/api/extrair` que já existe. É o mesmo motivo do
# `/vinculos/extrair-preview`, cuja doc diz "nunca gera OS a partir daqui, é o
# ambiente seguro que você pediu": somar a aba abriria a rota de extração da
# geração de OS para um perfil que não deve chegar perto dela.


def _so_doc(v) -> str:
    return "".join(c for c in str(v or "") if c.isalnum())


async def _cliente_no_harmonit(doc: str) -> dict | None:
    """Cliente por CNPJ/CPF, ou None.

    🚨 O HARMONIT RESPONDE EM DUAS FORMAS (conferido em 29/07):
        existe     -> list  [{"id": 998063, ...}]
        não existe -> dict  {"errorMessage": null, "data": []}
    O dict de "não encontrado" é TRUTHY, então tratar a resposta como verdade
    diria que todo documento já existe -- inclusive um inventado.
    """
    if not doc:
        return None
    try:
        r = await harmonit_get("/ObterClientePorCpfCnpj", params={"CpfCnpj": doc})
    except Exception as exc:
        log.info("placas: busca de %s no Harmonit falhou: %s", doc, exc)
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


@router.post("/extrair")
async def extrair(perfil: str = Query(...), arquivo: UploadFile = File(...),
                  _=Depends(requer_aba("cadastro_placas"))):
    """Lê o termo e cruza o cliente. NÃO ESCREVE NADA.

    Devolve os veículos na ORDEM E NAS COLUNAS DO DOCUMENTO -- veículo primeiro,
    placa depois -- porque é assim que o operador confere linha a linha contra
    o papel. A tela oferece inverter, para o caso de o contrato ter trocado os
    campos; padronizar isso é problema da origem, não daqui.
    """
    if perfil not in PERFIS:
        raise HTTPException(400, f"Perfil desconhecido: {perfil}")
    if PERFIS[perfil].get("sem_termo"):
        raise HTTPException(400,
            f"O perfil {perfil!r} não nasce de documento — use o caminho digitado.")

    conteudo = await arquivo.read()
    try:
        campos = extrair_campos(io.BytesIO(conteudo), perfil)
    except Exception as exc:
        log.exception("placas: falha ao ler o PDF")
        raise HTTPException(422, f"Não foi possível ler o PDF: {exc}")

    doc = _so_doc(campos.get("cnpj") or campos.get("cpf"))

    # ⚠️ TERMO EXISTE ⇒ CLIENTE EXISTE NO HARMONIT (regra do usuário, 17/08):
    # o termo vem de lá. Por isso a busca abaixo NÃO é uma validação e não
    # ramifica o fluxo -- ela existe só para pegar o `clienteId`, que o
    # `/Veiculo/Incluir` exige e o termo não traz. Falhar aqui é erro a
    # reportar, não caminho alternativo.
    no_harmonit = await _cliente_no_harmonit(doc)
    no_weso = await _cliente_na_weso(doc)

    sufixo = (PERFIS[perfil].get("placa_teste_sufixo") or "").upper() or None

    itens = []
    for p in (campos.get("placas") or []):
        bruta = str(p.get("placa") or "").strip()
        itens.append({
            # a ordem do documento: veículo, depois placa
            "veiculo": (p.get("veiculo") or "").strip(),
            "placa": bruta,
            "placa_gravada": regra_placa.formatar(bruta) or bruta,
            # 🚨 chassi e série entram COMO ESTÃO -- provado em 17/08 nos dois
            # sistemas. Isto aqui é só rótulo para a tela destacar a linha, não
            # tratamento diferente.
            "convencional": regra_placa.eh_convencional(bruta),
            "sem_descricao": not (p.get("veiculo") or "").strip(),
        })

    return {
        "termo": campos.get("termo"),
        "perfil": perfil,
        "documento": doc,
        "cliente": {
            # 🚨 CRUZA POR CNPJ, NUNCA POR NOME. Medido em 17/08: o mesmo
            # documento é `Velasco Leite Pastelaria ME` no Harmonit e
            # `PASTELARIA VELASCO LTDA` na WESO. A tela mostra os dois, senão
            # parece que achou o cliente errado.
            "nome_no_termo": campos.get("cliente_nome_sugerido"),
            "harmonit_id": (no_harmonit or {}).get("id"),
            "harmonit_nome": (no_harmonit or {}).get("nome"),
            "weso_id": (no_weso or {}).get("id"),
            "weso_nome": (no_weso or {}).get("razaoSocial"),
            "weso_situacao": (no_weso or {}).get("situacao"),
        },
        "recipiente_sufixo": sufixo,
        "itens": itens,
        "sem_placa": campos.get("veiculos_sem_placa") or [],
    }


# ── escrever, uma placa por requisição (passos 4 e 5) ────────────────────────
#
# 🚨 UMA REQUISIÇÃO POR PLACA, e não um lote. Medido em 17/08: gravar custa
# ~4,4s por placa, porque cada criação é seguida de releitura para provar. Um
# termo de 11 placas em lote levaria ~50s, e com recipientes passaria de 1,5
# min -- perto demais do teto do nginx. Mexer no teto trataria o sintoma; uma
# requisição por placa resolve a causa, e ainda isola o erro: falhou a sétima,
# as seis anteriores estão gravadas E PROVADAS.

# Espelho em memória da base do Harmonit.
# ⚠️ EXISTE PORQUE `/Veiculo/ObterVeiculos` IGNORA TODOS OS FILTROS -- medido:
# `?placa=X` e `?clienteId=Y` devolvem os 9.107 igual. Para saber se uma placa
# existe lá, só baixando tudo. Custa 1,9s, então cabe; sem o espelho seriam
# 1,9s POR PLACA só para conferir.
_HARMONIT_BASE: list | None = None
_HARMONIT_EM: float = 0.0
_HARMONIT_TTL = 120.0


async def _base_harmonit(forcar: bool = False) -> list:
    global _HARMONIT_BASE, _HARMONIT_EM
    if (not forcar and _HARMONIT_BASE is not None
            and (time.monotonic() - _HARMONIT_EM) < _HARMONIT_TTL):
        return _HARMONIT_BASE
    r = await harmonit_get("/Veiculo/ObterVeiculos")
    _HARMONIT_BASE = r if isinstance(r, list) else (r.get("data") or [])
    _HARMONIT_EM = time.monotonic()
    return _HARMONIT_BASE


def _chave(v) -> str:
    """Comparação de placa SEM espaço e em caixa alta.

    🚨 100% DE ADERÊNCIA COM NORMALIZAÇÃO DE ESPAÇOS (regra do usuário, 17/08).
    A consulta da WESO é igualdade exata e a placa é gravada COM espaço; o
    Harmonit grava como veio. Comparar texto cru diria "não existe" para placa
    que existe -- foi assim que a TTX 0H91 do termo 8788 sumiu em julho.
    """
    return "".join(str(v or "").upper().split())


async def _achar_no_harmonit(texto: str, forcar: bool = False) -> dict | None:
    alvo = _chave(texto)
    for v in await _base_harmonit(forcar):
        if _chave(v.get("placa")) == alvo:
            return v
    return None


class CriarUmaInput(BaseModel):
    lote: str
    cnpjcpf: str
    placa: str
    descricao: str | None = None
    sufixo: str | None = None
    termo: str | None = None
    perfil: str | None = None
    cliente_harmonit_id: int | None = None
    cliente_weso_id: int | None = None


@router.post("/criar-uma")
async def criar_uma(body: CriarUmaInput,
                    usuario=Depends(requer_aba("cadastro_placas"))):
    """Cria UMA placa: Harmonit primeiro, WESO depois. Registra as duas.

    🚨 HARMONIT ANTES DA WESO. Falhou o Harmonit, PARA -- não sobra veículo na
    WESO sem par. A ordem inversa deixaria o estrago espelhado do de 27/07.

    🚨 SÓ `/Veiculo/Incluir`, COM `id: 0` EXPLÍCITO. O `PUT /Veiculo/Atualizar`
    tem os MESMOS campos e, sem `id`, CRIA em vez de atualizar -- foi ele que
    fez 88 veículos por engano em 27/07 e quebrou 93 vínculos, que continuam
    quebrados. Deixando-o fora, esse erro fica impossível por construção.
    """
    item = ItemPlaca(placa=body.placa, descricao=body.descricao,
                     sufixo=body.sufixo, termo=body.termo)
    texto = _texto_gravado(item)
    descricao, erro_desc = _descricao_final(item)
    recipiente = bool(body.sufixo)

    comum = dict(usuario=(usuario or {}).get("login"), termo=body.termo,
                 perfil=body.perfil, cnpjcpf=body.cnpjcpf,
                 cliente_weso_id=body.cliente_weso_id,
                 cliente_harmonit_id=body.cliente_harmonit_id,
                 placa_digitada=body.placa, placa_gravada=texto,
                 descricao=descricao, recipiente=recipiente)

    fora = {"placa_digitada": body.placa, "placa_gravada": texto,
            "descricao": descricao, "recipiente": recipiente,
            "harmonit": None, "weso": None}

    if erro_desc:
        for sis in ("harmonit", "weso"):
            await storage.registrar_cadastro_placa(body.lote, sis, "ignorado",
                                                   erro=erro_desc, **comum)
            fora[sis] = {"acao": "ignorado", "erro": erro_desc}
        return fora

    # ── Harmonit ────────────────────────────────────────────────────────────
    # ⚠️ RECIPIENTE NÃO VAI PARA O HARMONIT. Ele é bancada do setor de
    # configuração, não veículo do cliente -- lá só entra o que roda na rua.
    if recipiente:
        await storage.registrar_cadastro_placa(body.lote, "harmonit", "ignorado",
                                               erro="recipiente não vai ao Harmonit",
                                               **comum)
        fora["harmonit"] = {"acao": "ignorado",
                            "motivo": "recipiente é bancada, não veículo do cliente"}
    elif not body.cliente_harmonit_id:
        # Sem `clienteId` não há como criar lá. Não trava o fluxo: a WESO segue.
        await storage.registrar_cadastro_placa(body.lote, "harmonit", "ignorado",
                                               erro="cliente não encontrado no Harmonit",
                                               **comum)
        fora["harmonit"] = {"acao": "ignorado",
                            "motivo": "cliente não encontrado no Harmonit"}
    else:
        ja = await _achar_no_harmonit(texto)
        if ja:
            # Já existe: INFORMA e NÃO CRIA (regra do usuário, 17/08).
            await storage.registrar_cadastro_placa(body.lote, "harmonit", "ja_existia",
                                                   id_externo=ja.get("id"), **comum)
            fora["harmonit"] = {"acao": "ja_existia", "id": ja.get("id"),
                                "dono": ja.get("cliente"),
                                "dono_id": ja.get("clienteId")}
        else:
            payload = {"id": 0, "veiculo": descricao or texto, "placa": texto,
                       "clienteId": body.cliente_harmonit_id}
            try:
                r = await harmonit_post("/Veiculo/Incluir", payload)
            except HTTPException as exc:
                msg = f"o Harmonit recusou: {exc.detail}"
                await storage.registrar_cadastro_placa(body.lote, "harmonit",
                                                       "falhou", erro=msg, **comum)
                fora["harmonit"] = {"acao": "falhou", "erro": msg}
                # 🚨 PARA AQUI. Nada na WESO sem par no Harmonit.
                await storage.registrar_cadastro_placa(body.lote, "weso", "ignorado",
                                                       erro="o Harmonit falhou antes",
                                                       **comum)
                fora["weso"] = {"acao": "ignorado",
                                "motivo": "o Harmonit falhou antes"}
                return fora
            # A PROVA: relê a base, forçando -- não confia no id devolvido.
            conferido = await _achar_no_harmonit(texto, forcar=True)
            if conferido:
                await storage.registrar_cadastro_placa(body.lote, "harmonit", "criado",
                                                       id_externo=conferido.get("id"),
                                                       **comum)
                fora["harmonit"] = {"acao": "criado", "id": conferido.get("id"),
                                    "verificado_relendo": True}
            else:
                msg = ("o Harmonit respondeu sem erro mas a placa não aparece "
                       "na releitura")
                await storage.registrar_cadastro_placa(body.lote, "harmonit",
                                                       "falhou", erro=msg,
                                                       id_externo=(r or {}).get("id"),
                                                       **comum)
                fora["harmonit"] = {"acao": "falhou", "erro": msg}
                await storage.registrar_cadastro_placa(body.lote, "weso", "ignorado",
                                                       erro="o Harmonit falhou antes",
                                                       **comum)
                fora["weso"] = {"acao": "ignorado",
                                "motivo": "o Harmonit falhou antes"}
                return fora

    # ── WESO ────────────────────────────────────────────────────────────────
    situacao = await _situacao_das_placas([texto])
    s = situacao.get(texto, {})
    if s.get("existe") is None:
        msg = s.get("erro") or "não consegui conferir na WESO"
        await storage.registrar_cadastro_placa(body.lote, "weso", "falhou",
                                               erro=msg, **comum)
        fora["weso"] = {"acao": "falhou", "erro": msg}
        return fora
    if s.get("existe"):
        await storage.registrar_cadastro_placa(body.lote, "weso", "ja_existia",
                                               id_externo=s.get("veiculo_id"),
                                               **comum)
        fora["weso"] = {"acao": "ja_existia", "id": s.get("veiculo_id"),
                        "descricao_atual": s.get("descricao_atual")}
        return fora
    equipamento = {"placa": texto, "cliente": {"cnpjcpf": body.cnpjcpf}}
    if descricao:
        equipamento["descricao"] = descricao
    if recipiente:
        equipamento["complemento"] = {"tipoEqp": TIPO_BANCADA}
    try:
        await weso_post("/Veiculos/Cadastro", {"equipamento": equipamento},
                        allow_409=True)
    except HTTPException as exc:
        msg = f"a WESO recusou: {exc.detail}"
        await storage.registrar_cadastro_placa(body.lote, "weso", "falhou",
                                               erro=msg, **comum)
        fora["weso"] = {"acao": "falhou", "erro": msg}
        return fora

    conferido = await _conferir_na_weso(texto)
    if conferido:
        _espelho_aprende(conferido)
        await storage.registrar_cadastro_placa(body.lote, "weso", "criado",
                                               id_externo=conferido.get("id"),
                                               **comum)
        fora["weso"] = {"acao": "criado", "id": conferido.get("id"),
                        "verificado_relendo": True}
    else:
        msg = "a WESO respondeu sem erro mas a placa não aparece na releitura"
        await storage.registrar_cadastro_placa(body.lote, "weso", "falhou",
                                               erro=msg, **comum)
        fora["weso"] = {"acao": "falhou", "erro": msg}
    return fora


@router.post("/lote")
async def abrir_lote(_=Depends(requer_aba("cadastro_placas"))):
    """Identificador da rodada. A tela pega um antes de começar o laço."""
    return {"lote": storage.novo_lote()}


# ── histórico (passo 6) ──────────────────────────────────────────────────────
#
# 🚨 POR QUE ELE IMPORTA MAIS AQUI DO QUE NA OS. OS errada alguém abre e vê;
# veículo criado errado some no meio de 9.107 no Harmonit e 1.969 na WESO. Sem
# esta tela, auditar um cadastro exigiria comparar as bases inteiras.
#
# Só leitura. Reprocessar entra depois, se fizer falta -- placa que falhou pode
# ser refeita subindo o mesmo termo, e botão que escreve merece rodada própria.


@router.get("/historico")
async def historico(limite: int = Query(100, le=500),
                    incluir_simulado: bool = Query(False),
                    _=Depends(requer_aba("cadastro_placas"))):
    """Um resumo por rodada. Simulação fica de fora por padrão."""
    return {"lotes": await storage.listar_lotes_cadastro(limite, incluir_simulado)}


@router.get("/historico/{lote}")
async def historico_do_lote(lote: str,
                            _=Depends(requer_aba("cadastro_placas"))):
    """As linhas de uma rodada. Simulação INCLUÍDA -- quem abriu um lote
    específico quer ver tudo o que aconteceu nele, inclusive o ensaio."""
    return {"lote": lote,
            "itens": await storage.listar_cadastro_placas(500, lote, True)}
