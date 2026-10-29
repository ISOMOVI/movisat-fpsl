"""A ponte de OS entre o FPSL e o MoviZap — 21/10.

⚠️ NÃO É MAIS "somente leitura", e a linha que dizia isso ficou oito dias
velha: a escrita de endereço entrou em 21/10 e a criação de OS em 29/10. São
duas rotas que GRAVAM NO ERP, as duas no fim deste arquivo.

🔵 Decisão 8 dele (19/10): *"o FPSL expõe endpoint de OS e o MoviZap consome
pelo `FPSL_BASE_URL`"*. As OS vivem aqui, em SQLite (`os_historico`, varrida do
Harmonit a cada 5 min); o MoviZap é Postgres, e até hoje nenhum dos dois
consultava o outro.

🚨 ESTA ROTA NÃO USA `requer_aba`. Toda rota do painel exige sessão de pessoa
(cookie), e chamada servidor-a-servidor não tem cookie -- medido em 21/10,
antes de escrever. A autenticação é o segredo `PONTE_FPSL_SEGREDO`, que vive
nos dois `.env` e é comparado em tempo constante, como a `verificar_chave` da
API WESO já fazia desde a auditoria de 15/07.

🚨 A CHAVE DO CRUZAMENTO É O `harmonit_id`, e nenhum campo novo de identidade
foi criado: `os_historico.cliente_id` é o id do cliente no Harmonit, e o
MoviZap já tem esse mesmo número em `cliente.harmonit_id` (text, 959 de 959
preenchidos). Medido em 19/10 e reconferido em 21/10.

⚠️ `data_previsao` É TEXTO `dd/mm/aaaa HH:MM:SS`, NÃO data ISO. O plano de
19/10 dizia para filtrar com `date(data_previsao)` -- e isso devolve **zero
linha**, porque o SQLite não entende o formato brasileiro. Com o recorte
certo: 431 OS abertas de 96 clientes nos últimos 6 meses. Medido em 21/10,
nas 572 OS da base. Formato conferido: 0 nulas, 0 fora de `__/__/____`.
"""
import hmac
import json
import logging
import unicodedata
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import settings
from ..harmonit_client import harmonit_get, harmonit_post
from .. import storage

log = logging.getLogger(__name__)

# `substr` em vez de `date()`: ver a advertência do topo. Vira 'aaaa-mm-dd',
# que é o único formato que o SQLite compara como data.
_PREVISAO_ISO = (
    "substr(data_previsao, 7, 4) || '-' || "
    "substr(data_previsao, 4, 2) || '-' || "
    "substr(data_previsao, 1, 2)"
)

# 🚨 "Em aberto" = não finalizada E não excluída. `status_str` é NULO em 37 das
# 572, e nulo NÃO é finalizado: entra na lista, marcado como sem situação.
# Escrever `status_str <> 'Finalizado'` sozinho sumiria com as 37 em silêncio,
# porque em SQL nulo não é diferente de nada.
_EM_ABERTO = "(status_str IS NULL OR status_str <> 'Finalizado')"


async def verificar_segredo(x_ponte_key: str = Header(...)) -> None:
    """Autenticação da ponte. Comparação constant-time, como a `verificar_chave`."""
    segredo = settings.ponte_fpsl_segredo
    if not segredo or not hmac.compare_digest(x_ponte_key, segredo):
        raise HTTPException(status_code=401, detail="Chave da ponte inválida")


router = APIRouter(
    prefix="/api/os",
    tags=["ponte-movizap"],
    dependencies=[Depends(verificar_segredo)],
)


def _placas(oficinas_json: str | None) -> list[dict]:
    """As placas da OS, do `oficinas_json`.

    ⚠️ SÓ 236 DAS 572 OS TÊM OFICINA -- a lista vazia é o caso comum, não erro,
    e quem desenha a tela tem de dizer "sem placa registrada" em vez de
    mostrar um espaço em branco. O mesmo `veiculoId` aparece em mais de uma
    oficina (retirada + instalação do mesmo veículo), por isso a deduplicação.
    """
    if not oficinas_json:
        return []
    try:
        oficinas = json.loads(oficinas_json)
    except (ValueError, TypeError):
        # Dado do Harmonit, varrido por rotina: não derruba a consulta.
        log.warning("oficinas_json ilegível numa OS -- devolvendo sem placa")
        return []
    if not isinstance(oficinas, list):
        return []
    vistos: dict[str, dict] = {}
    for of in oficinas:
        if not isinstance(of, dict):
            continue
        placa = (of.get("veiculoPlaca") or "").strip()
        if not placa or placa in vistos:
            continue
        vistos[placa] = {"placa": placa, "veiculo": of.get("veiculoNome") or None}
    return list(vistos.values())


def _desde(meses: int) -> str:
    """O corte de data, em ISO. 30 dias por mês é de propósito: o recorte é
    "últimos 6 meses" no sentido da conversa, não aniversário de calendário."""
    return (date.today() - timedelta(days=30 * meses)).isoformat()


@router.get("/por-cliente")
async def os_por_cliente(
    cliente_id: int = Query(..., description="id do cliente NO HARMONIT"),
    meses: int = Query(6, ge=1, le=60),
    abertas: int = Query(1, ge=0, le=1),
):
    """As OS de um cliente, para a etapa 2 da aba Agendar.

    Devolve sempre `{"cliente_id", "meses", "os": [...]}` -- lista vazia aqui
    significa "este cliente não tem OS no recorte", e é por isso que o cliente
    HTTP do outro lado nunca converte erro de rede em lista vazia.
    """
    sql = [
        "SELECT numero_os, tipo, problema, status_str, situacao_id,",
        "       data_previsao, oficinas_json",
        "  FROM os_historico",
        " WHERE excluida = 0 AND cliente_id = ?",
        f"   AND {_PREVISAO_ISO} >= ?",
    ]
    params: list = [cliente_id, _desde(meses)]
    if abertas:
        sql.append(f"   AND {_EM_ABERTO}")
    sql.append(f" ORDER BY {_PREVISAO_ISO} DESC, numero_os DESC")

    with storage._connect() as conn:
        linhas = conn.execute("\n".join(sql), params).fetchall()
        # 🆕 21/10, ponta 1 do plano: o dicionário de nomes de tipo, varrido
        # 1×/dia pela rotina `sync_tipos_os`. Lido na mesma conexão, uma vez
        # por requisição -- e não por linha.
        nomes_de_tipo = storage.nomes_dos_tipos_os(conn)

    return {
        "cliente_id": cliente_id,
        "meses": meses,
        "os": [
            {
                "numero_os": n,
                # `tipo` é o ID do tipo no Harmonit, não o nome -- a base não
                # guarda o nome na própria OS.
                "tipo": tipo,
                # 🚨 `tipo_nome` É NULO COM FREQUÊNCIA, e isso é resposta, não
                # falha: 173 das 547 OS têm `tipo` fora da lista do Harmonit
                # (nove ids, medido em 21/10 -- entre eles o 55, que o
                # `os_router` já documentava como tipo morto desde 14/08).
                # Quem monta a mensagem do agendamento OMITE o segmento do
                # cabeçalho quando isto vem nulo; inventar rótulo seria tela
                # que mente, e imprimir o número não diz nada ao cliente.
                "tipo_nome": nomes_de_tipo.get(tipo),
                "problema": problema,
                "status_str": status,
                "sem_situacao": status is None,
                "situacao_id": situacao,
                "data_previsao": previsao,
                "veiculos": _placas(oficinas),
            }
            for n, tipo, problema, status, situacao, previsao, oficinas in linhas
        ],
    }


@router.get("/placas-ativas")
async def placas_ativas_do_cliente(
    cliente_id: int = Query(..., description="id do cliente NO HARMONIT"),
):
    """As placas que o cliente tem ATIVAS, para o formulário do MoviZap.

    🔵 Pedido dele em 29/10, no formulário de Suporte: trazer os veículos que o
    cliente tem ativos na WESO em vez de pedir que ele digite a placa.

    🚨 SÃO DUAS BASES, E NENHUMA RESPONDE SOZINHA (medido em 23/10):
      · quem sabe **de quem** é a placa é o Harmonit (`harmonit_veiculos`,
        9.114 linhas, com `clienteId`);
      · quem diz que a placa está **ativa** é a WESO (`weso_equipamentos`,
        1.998) -- é ela que tem rastreador instalado --, e é ela que tem o
        **apelido** ("SAVEIRO / BRUNO"), que o Harmonit não tem (lá o nome é o
        modelo, "Ford Courier").
    Por isso a lista é o cruzamento, e por isso ela nasce aqui: as duas bases
    vivem neste projeto.

    ⚠️ A CHAVE DE PLACA SE NORMALIZA DOS DOIS LADOS (maiúscula, sem espaço e
    sem traço): em 23/10 mediu-se **95%** de cruzamento (1.828 de 1.921), e
    parte do que não casava era espaço no meio da placa.

    Devolve sempre `{"cliente_id", "placas": [...]}`. Lista vazia significa
    "este cliente não tem veículo ativo", e é por isso que o cliente HTTP do
    outro lado nunca converte erro de rede em lista vazia.
    """
    chave = ("upper(replace(replace({c}, ' ', ''), '-', ''))")
    sql = f"""
        SELECT h.placa, h.veiculo, w.apelido
          FROM harmonit_veiculos h
          JOIN weso_equipamentos w
            ON {chave.format(c='w.placa')} = {chave.format(c='h.placa')}
         WHERE h.clienteId = ?
         ORDER BY h.placa
    """
    with storage._connect() as conn:
        linhas = conn.execute(sql, (cliente_id,)).fetchall()

    return {
        "cliente_id": cliente_id,
        "placas": [
            {
                "placa": (placa or "").strip().upper(),
                # ⚠️ O apelido é o que a pessoa reconhece; o modelo do Harmonit
                # é o reforço. Os dois podem vir vazios, e aí sobra a placa --
                # que é o que importa.
                "apelido": (apelido or "").strip() or None,
                "veiculo": (veiculo or "").strip() or None,
            }
            for placa, veiculo, apelido in linhas
        ],
    }


@router.post("/placas-ativas/conferir")
async def conferir_placas_ativas(corpo: dict):
    """Quais destas placas estão ATIVAS na WESO. 🔵 Regra dele, 29/10: *"só é
    possível abrir chamados para placas ativas na weso"*.

    🚨 QUEM DIZ "ATIVA" É A WESO, SOZINHA -- e aqui está a diferença em relação
    a `/placas-ativas`: lá o Harmonit entra para dizer **de quem** é a placa;
    aqui a pergunta é outra, *"esta placa tem rastreador instalado?"*, e isso é
    só WESO. Exigir o Harmonit nesta conferência recusaria as **30 placas**
    (medido em 29/10) que estão ativas na WESO e **não** estão no cadastro do
    Harmonit -- e pela regra dele essas podem abrir chamado.

    ⚠️ A CHAVE É NORMALIZADA (maiúscula, só letra e dígito), porque a WESO
    grava `BYL 2170` e a pessoa digita `byl-2170`.

    Devolve `{"placas": {<como veio>: {ativa, apelido}}}` -- a chave é o texto
    que o cliente escreveu, para quem chamou não ter de casar de volta.
    """
    pedidas = [str(x) for x in (corpo.get("placas") or [])][:50]
    if not pedidas:
        return {"placas": {}}

    def so_alfanum(texto: str) -> str:
        return "".join(c for c in (texto or "").upper() if c.isalnum())

    with storage._connect() as conn:
        linhas = conn.execute(
            "SELECT placa, apelido FROM weso_equipamentos "
            " WHERE placa IS NOT NULL AND trim(placa) <> ''").fetchall()
    ativas = {so_alfanum(placa): (apelido or "").strip() or None
              for placa, apelido in linhas}

    # 🚨 A PESSOA PODE ESCREVER "SAVEIRO ABC1234", e isso é resposta certa: o
    # campo pede *"Veículo e Placa"*. Então procura-se cada pedaço do texto,
    # não só o texto inteiro.
    saida = {}
    for escrito in pedidas:
        achou = None
        pedacos = [so_alfanum(t) for t in escrito.replace("-", " ").split()]
        for pedaco in [so_alfanum(escrito), *pedacos]:
            if pedaco in ativas:
                achou = pedaco
                break
        saida[escrito] = {"ativa": achou is not None,
                          "apelido": ativas.get(achou) if achou else None}
    return {"placas": saida}


@router.get("/clientes-com-os")
async def clientes_com_os(
    meses: int = Query(6, ge=1, le=60),
    abertas: int = Query(1, ge=0, le=1),
):
    """Os clientes que têm OS no recorte — a lista da etapa 2 (decisão 5 dele:
    *"a etapa do cliente lista só clientes com OS em aberto nos últimos 6
    meses"*).

    Devolve só `cliente_id` e a contagem: o NOME é do MoviZap, que cruza pelo
    `harmonit_id`. Mandar o nome daqui criaria uma segunda versão do cadastro,
    e as duas divergiriam no primeiro cliente renomeado.
    """
    sql = [
        "SELECT cliente_id, COUNT(*)",
        "  FROM os_historico",
        " WHERE excluida = 0 AND cliente_id IS NOT NULL",
        f"   AND {_PREVISAO_ISO} >= ?",
    ]
    params: list = [_desde(meses)]
    if abertas:
        sql.append(f"   AND {_EM_ABERTO}")
    sql.append(" GROUP BY cliente_id ORDER BY COUNT(*) DESC")

    with storage._connect() as conn:
        linhas = conn.execute("\n".join(sql), params).fetchall()

    return {
        "meses": meses,
        "clientes": [{"cliente_id": cid, "quantas": q} for cid, q in linhas],
    }


# ---------------------------------------------------------------------------
# A ESCRITA — 🔵 ligada por decisão dele em 21/10, depois do relatório do teste
# na OS 16991: *"pode deixar ligado e seguir com o plano"*.
# ---------------------------------------------------------------------------
#
# 🚨 O QUE O TESTE MEDIU, e que desenha esta rota (OS 16991, Velasco):
#   · `id: 0` **CRIA** — nasceu o agendamento 944767 (Aline, 23/10 09:00-11:00),
#     conferido RELENDO a OS, não pelo retorno da chamada;
#   · mandar o `id` de um compromisso que já existe **RECUSA**, com
#     `Erro ao alterar Evento: TecnicoJaAgendado`, e nada muda;
#   · `agendado` continua `false` depois de agendar — o campo NÃO quer dizer
#     "tem compromisso";
#   · a data vai em ISO e volta em `dd/mm/aaaa`.
#
# 🚨 O MOVIZAP CONTINUA SENDO O DONO (decisão 7 dele): esta rota devolve a
# recusa por extenso, quem chama grava o erro ao lado do compromisso, e o
# agendamento do MoviZap NÃO depende disto dar certo.


class AgendarTecnicoEntrada(BaseModel):
    numero_os: int
    inicio: datetime
    fim: datetime | None = None
    # 🔵 21/10, decisão dele: **a validação é pelo E-MAIL do técnico**, e o
    # telefone é o que o encontra. O MoviZap manda o número do contato.
    tecnico_telefone: str | None = Field(default=None, max_length=32)
    # 🚨 O JEITO EXATO, quando o MoviZap já tem o vínculo gravado: o
    # `usuarioId` de cada técnico da OS **é o `tecnico_id` do cadastro**
    # (medido em 21/10: Iago 7493, Franck 14262, dos dois lados). Com ele não
    # há casamento nenhum a fazer -- e é o que faz o vínculo MANUAL funcionar,
    # inclusive a exceção dele (6168 → Iago), que por telefone nunca casaria.
    tecnico_id: int | None = None
    # Só para a mensagem de recusa ficar legível. ⚠️ NÃO casa por nome.
    tecnico_nome: str | None = Field(default=None, max_length=200)


def _so_digitos(texto: str) -> str:
    return "".join(c for c in (texto or "") if c.isdigit())


def _chave_do_telefone(telefone: str | None) -> str:
    """Os 9 últimos dígitos — é o que serve de chave dos dois lados.

    🚨 MEDIDO EM 21/10, e é isto que faz a regra dele funcionar: o e-mail do
    técnico no Harmonit é o **telefone dele**. `Franck` tem
    `997394026@movisat.com.br`, e o contato no MoviZap é `+5519997394026`.
    **186 dos 200 técnicos** do cadastro seguem esse padrão; os 14 que não
    seguem são contas internas (`comercial@`, `parceiros@`, pessoas da casa),
    não técnicos de campo.

    Nove dígitos porque é o número sem DDI nem DDD -- comparar o e164 inteiro
    erraria em todo técnico cujo DDD o Harmonit não guardou.
    """
    so = _so_digitos(telefone)
    return so[-9:] if len(so) >= 9 else ""


def _email_do_tecnico(t: dict) -> str:
    """A parte do e-mail antes do `@`, só dígitos. Vazio quando não é número."""
    email = (t.get("email") or "").strip()
    local = email.split("@")[0] if "@" in email else ""
    return local if local.isdigit() else ""


def _simples(texto: str) -> str:
    """Nome sem acento, sem caixa e sem espaço dobrado, só para a mensagem."""
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


def _quem_tem(tecnicos: list) -> list:
    """Como a OS descreve os técnicos dela, para a recusa dizer algo útil."""
    return [{"nome": t.get("nomeTecnico"), "email": t.get("email")}
            for t in tecnicos]


def _escolher_vinculo(tecnicos: list, telefone: str | None,
                      nome: str | None = None,
                      tecnico_id: int | None = None) -> tuple[dict | None, str]:
    """Qual `ordemServicoxTecnico` recebe o compromisso.

    🔵 Decisão dele, 21/10: *"a validação será pelo e-mail do técnico"*. O
    nome **não** casa nada — e a medição explica por quê: dos 179 contatos de
    técnico que casam por telefone, **21 têm nome diferente** do cadastro do
    Harmonit, e quase todos os nomes do MoviZap carregam um sufixo de cidade
    (`Franck | Campinas - SP`). Casar por nome recusaria praticamente todos.

    🚨 NUNCA ESCOLHE NO ESCURO. Sem telefone, só aceita quando a OS tem um
    único técnico; em qualquer outro caso devolve o motivo com os nomes e
    e-mails que a OS tem -- agendar no técnico errado é pior que não agendar.

    🔵 21/10, SEGUNDA DECISÃO DELE: **ter compromisso não barra mais nada**
    -- *"a barreira de agendamento do tecnico não deve existir, no harmonit ja
    foi liberada tbm"*. A barreira era DAQUI, não do Harmonit: este arquivo
    recusava antes de chamar, e foi o que derrubou o teste dele das 15:11
    (*"Iago Santos do Ó Souza ja tem compromisso nesta OS, agendamentoId
    930447"*). Agora quem decide é o Harmonit, e a recusa dele chega por
    extenso.

    ⚠️ O QUE SOBROU DA GUARDA, e tem de sobrar: **ambiguidade**. "Vários
    técnicos na OS e nenhuma pista de qual" continua sendo recusa. O que caiu
    foi `agendamentoId`, não o cuidado de não escolher no escuro.
    """

    # 1º o vínculo gravado, que é identidade e não semelhança.
    if tecnico_id:
        casados = [t for t in tecnicos if t.get("usuarioId") == tecnico_id]
        if not casados:
            return None, (f"o tecnico {tecnico_id} vinculado a esta conversa nao "
                          f"esta nesta OS (tem: {_quem_tem(tecnicos)})")
        # ⚠️ Prefere o vínculo SEM compromisso quando o mesmo usuário aparece
        # duas vezes na OS: criar onde não há é mais barato que mexer onde há.
        # Mas ter compromisso **não recusa** -- ver o docstring.
        livre = [t for t in casados if not t.get("agendamentoId")]
        return (livre or casados)[0], ""

    chave = _chave_do_telefone(telefone)
    if chave:
        casados = [t for t in tecnicos if _email_do_tecnico(t) == chave]
        if not casados:
            return None, (
                f"nenhum tecnico desta OS tem o telefone {chave} no e-mail do "
                f"cadastro do Harmonit (tem: {_quem_tem(tecnicos)})")
        livre = [t for t in casados if not t.get("agendamentoId")]
        return (livre or casados)[0], ""

    # Sem telefone e sem vínculo: só quando não há dúvida de quem é.
    # ⚠️ A conta agora é sobre TODOS os técnicos da OS, não só os sem
    # compromisso: com a barreira fora, "livre" deixou de ser critério de
    # escolha -- e contar só os livres faria a OS de três técnicos, dois já
    # agendados, escolher o terceiro sozinha e em silêncio.
    if len(tecnicos) == 1:
        return tecnicos[0], ""
    return None, (f"a OS tem {len(tecnicos)} tecnicos e o contato nao tem "
                  f"telefone nem vinculo para casar ({_quem_tem(tecnicos)})")


def _uma_os(bruto) -> dict:
    d = bruto.get("data") if isinstance(bruto, dict) and "data" in bruto else bruto
    if isinstance(d, list):
        d = d[0] if d else None
    return d or {}


def _cliente_da_os(numero_os: int) -> int | None:
    """O `cliente_id`, da nossa própria base.

    ⚠️ O corpo da OS do Harmonit **não traz `clienteId`** (medido em 21/10: as
    39 chaves do retorno não incluem nenhuma). Quem tem esse número é a
    `os_historico`, varrida a cada 5 min — e é dela que ele sai.
    """
    with storage._connect() as conn:
        linha = conn.execute(
            "SELECT cliente_id FROM os_historico WHERE numero_os = ?",
            (numero_os,)).fetchone()
    return linha[0] if linha else None


async def _segundo_vinculo(os_dict: dict, vinculo: dict) -> tuple[dict | None, str]:
    """Cria OUTRA linha `ordemServicoxTecnico` para o mesmo tecnico, e devolve-a.

    🚨 ESTE E O CAMINHO DO PROPRIO HARMONIT, e nao uma invencao nossa. O que a
    medicao de 21/10 mostrou, lendo as 547 OS da base sem escrever nada: o
    mesmo tecnico tem varios compromissos, inclusive **dois na mesma OS** --
    `usuarioId 14316` aparece duas vezes na OS 16921, com os agendamentos
    935886 e 938166. Cada linha de vinculo guarda UM `agendamentoId`, e e por
    isso que `AgendarTecnico` responde `TecnicoJaAgendado` quando o vinculo ja
    tem um: a recusa e do VINCULO, nunca do tecnico.

    🔵 21/10: foi assim que a decisao dele (*"a barreira de agendamento do
    tecnico nao deve existir"*) virou comportamento. Provado ao vivo na OS
    16991, que ele liberou: vinculo novo 1143047 -> compromisso 945219, com o
    930447 dele intacto ao lado.

    ⚠️ `tecnicoResponsavelPelaOS: False` de proposito: o vinculo novo e para
    carregar um compromisso, e nao para tirar de alguem a responsabilidade pela
    OS.

    🚨 A PROVA E RELER A OS e achar um id de vinculo que nao existia antes --
    o retorno da rota traz um `osxTecId`, mas confiar nele seria confiar no
    retorno em vez do estado.
    """
    antes = {t_.get("id") for t_ in (os_dict.get("tecnico") or [])}
    corpo = {
        "osId": os_dict.get("id"),
        "empresaId": os_dict.get("empresaId"),
        "tecnicoId": vinculo.get("usuarioId"),
        "tecnicoResponsavelPelaOS": False,
    }
    try:
        await harmonit_post("/OrdemServico/SalvarTecnicoOrdemServico", corpo)
    except Exception as e:  # noqa: BLE001 -- rota crua
        log.warning("SalvarTecnicoOrdemServico falhou na OS %s: %s",
                    os_dict.get("numeroOrdem"), e)
        return None, f"nao deu para criar o segundo vinculo do tecnico: {e}"

    depois = _uma_os(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": os_dict.get("numeroOrdem")}))
    novos = [t_ for t_ in (depois.get("tecnico") or [])
             if t_.get("id") not in antes
             and t_.get("usuarioId") == vinculo.get("usuarioId")]
    if not novos:
        return None, ("a rota aceitou e a OS continua com os mesmos vinculos ao "
                      "reler -- o segundo vinculo nao foi criado")
    return novos[0], ""


@router.post("/agendar-tecnico")
async def agendar_tecnico(entrada: AgendarTecnicoEntrada):
    """Cria o compromisso na OS do Harmonit. 🚨 A prova é RELER a OS."""
    os_dict = _uma_os(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": entrada.numero_os}))
    if not os_dict:
        raise HTTPException(
            status_code=404,
            detail=f"OS {entrada.numero_os} nao encontrada no Harmonit")

    # ⚠️ A chave é `tecnico`, no SINGULAR, e é uma lista. Chutar o nome fez a
    # primeira versão do script de medição relatar "sem técnico" numa OS com
    # três — achado por rodar, não por ler o swagger.
    tecnicos = os_dict.get("tecnico") or []
    if not tecnicos:
        return {"ok": False, "numero_os": entrada.numero_os,
                "motivo": "esta OS nao tem tecnico vinculado no Harmonit"}

    vinculo, motivo = _escolher_vinculo(tecnicos, entrada.tecnico_telefone,
                                        entrada.tecnico_nome, entrada.tecnico_id)
    if not vinculo:
        return {"ok": False, "numero_os": entrada.numero_os, "motivo": motivo}

    cliente_id = _cliente_da_os(entrada.numero_os)
    if not cliente_id:
        return {"ok": False, "numero_os": entrada.numero_os,
                "motivo": "nao sei o cliente desta OS (ela nao esta na os_historico)"}

    # 🔵 A BARREIRA CAIU EM 21/10, e aqui está o que faz dela comportamento:
    # se o vínculo escolhido já carrega um compromisso, cria-se OUTRO vínculo
    # para o mesmo técnico e agenda-se nele. Sem isto, a decisão dele pararia
    # na recusa do Harmonit (`TecnicoJaAgendado`), que é do vínculo e não do
    # técnico -- medido na base e provado na 16991.
    vinculo_criado = False
    if vinculo.get("agendamentoId"):
        novo_vinculo, motivo = await _segundo_vinculo(os_dict, vinculo)
        if not novo_vinculo:
            return {"ok": False, "numero_os": entrada.numero_os,
                    "motivo": motivo, "tecnico": vinculo.get("nomeTecnico")}
        vinculo = novo_vinculo
        vinculo_criado = True

    # 🚨 O QUE A PROVA PASSOU A SER, e por que ela TINHA de mudar junto com a
    # barreira: antes, "a OS tem `agendamentoId`" só podia ser verdade depois
    # da escrita, porque este arquivo recusava quando já havia. Com a barreira
    # fora, isso é verdade ANTES de chamar -- e relatar sucesso por ele seria
    # dizer "agendei" sobre o compromisso de outra pessoa. Então guarda-se o id
    # de antes, e só vale se ele MUDOU.
    id_antes = vinculo.get("agendamentoId") or 0

    fim = entrada.fim or (entrada.inicio + timedelta(hours=2))
    corpo = {
        # 0 CRIA. Com id existente a rota recusa — medido em 21/10.
        "id": 0,
        "clienteId": cliente_id,
        "ordemServicoId": os_dict.get("id"),
        "ordemServicoxTecnicoId": vinculo.get("id"),
        "inicioCompromisso": entrada.inicio.replace(tzinfo=None).isoformat(),
        "fimCompromisso": fim.replace(tzinfo=None).isoformat(),
    }
    try:
        await harmonit_post("/OrdemServico/AgendarTecnico", corpo)
    except HTTPException as e:
        # A rota é crua: a recusa vem como texto, e é esse texto que ajuda.
        log.warning("AgendarTecnico recusou a OS %s: %s", entrada.numero_os, e.detail)
        return {"ok": False, "numero_os": entrada.numero_os,
                "motivo": str(e.detail), "tecnico": vinculo.get("nomeTecnico")}
    except Exception as e:  # noqa: BLE001 -- rota crua, qualquer coisa pode vir
        log.warning("AgendarTecnico falhou na OS %s: %s", entrada.numero_os, e)
        return {"ok": False, "numero_os": entrada.numero_os,
                "motivo": f"{type(e).__name__}: {e}"}

    # 🚨 RELÊ A OS: o retorno da rota não é prova de que gravou.
    depois = _uma_os(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": entrada.numero_os}))
    novo = next((t for t in depois.get("tecnico") or []
                 if t.get("id") == vinculo.get("id")), {})
    agendamento_id = novo.get("agendamentoId") or 0
    if not agendamento_id:
        return {"ok": False, "numero_os": entrada.numero_os,
                "motivo": "a rota aceitou e a OS continua sem compromisso ao reler"}
    if agendamento_id == id_antes:
        # 🚨 Mesmo id que antes: o Harmonit aceitou a chamada e NADA mudou na
        # OS. Isto é falha, e dizê-la por extenso é o que impede "achei que
        # tinha ido" -- o compromisso que está lá é o de antes, não o nosso.
        return {"ok": False, "numero_os": entrada.numero_os,
                "motivo": (f"a rota aceitou e o compromisso continua sendo o "
                           f"mesmo de antes (agendamentoId {id_antes}) -- nada "
                           f"foi criado"),
                "tecnico": vinculo.get("nomeTecnico")}
    return {
        "ok": True,
        "numero_os": entrada.numero_os,
        "agendamento_id": agendamento_id,
        # O id anterior vai na resposta: quando havia um, quem lê o rastro
        # precisa saber que este técnico passou a ter DOIS compromissos nesta
        # OS -- e não que o antigo virou este.
        "agendamento_id_anterior": id_antes or None,
        # Quando foi preciso criar o segundo vínculo, isto fica dito: a OS
        # ganhou uma linha de técnico, e quem olhar a OS depois tem de saber
        # por quê.
        "vinculo_criado": vinculo_criado,
        # 🔵 O nome que vale é o do cadastro do Harmonit, não o do contato
        # do WhatsApp: *"mesmo que nomeiem errado, ele vai trazer no orcamento
        # o nome do cadastro harmonit"*.
        "tecnico": vinculo.get("nomeTecnico"),
        "tecnico_email": vinculo.get("email"),
        "janela": novo.get("agendamentoOS") or {},
    }


@router.get("/tecnico-por-telefone")
async def tecnico_por_telefone(telefone: str = Query(..., min_length=8)):
    """O técnico do cadastro do Harmonit, achado pelo telefone.

    🔵 Decisão dele, 21/10: o orçamento imprime **o nome do cadastro do
    Harmonit**, e não o do contato de WhatsApp -- *"mesmo que nomeiem errado,
    ele vai trazer no orcamento o nome do cadastro harmonit"*.

    Lê a tabela `tecnicos`, sincronizada do Harmonit (200 linhas), e não a OS:
    o orçamento pode ser emitido antes de qualquer OS ser escolhida.

    ⚠️ Devolve `{"achado": false}` em vez de 404: **não achar é resposta**, e
    quem chama cai no nome do contato, avisando na tela.
    """
    chave = _chave_do_telefone(telefone)
    if not chave:
        return {"achado": False, "motivo": "telefone curto demais para casar"}
    with storage._connect() as conn:
        linhas = conn.execute(
            "SELECT tecnico_id, nome, email, excluido FROM tecnicos "
            " WHERE email LIKE ?", (f"{chave}@%",)).fetchall()
    if not linhas:
        return {"achado": False, "motivo": f"nenhum tecnico com o telefone {chave}"}
    # Ativo primeiro: o cadastro guarda excluídos, e o nome de um excluído
    # continua certo, mas o ativo é quem está trabalhando.
    linhas.sort(key=lambda l: l[3] or 0)
    tecnico_id, nome, email, excluido = linhas[0]
    return {"achado": True, "tecnico_id": tecnico_id, "nome": nome,
            "email": email, "excluido": bool(excluido)}


@router.get("/tecnicos")
async def listar_tecnicos(ativos: int = Query(1, ge=0, le=1)):
    """O cadastro de técnicos do Harmonit, para a varredura do MoviZap.

    🔵 Pedido dele, 21/10: ligar o contato tipo técnico ao cadastro, *"assim
    já traz sugerido pelo número dele"*.

    A fonte é a tabela `tecnicos`, que a rotina `sync_tecnicos` atualiza
    **1×/dia** cruzando `ObterTecnicos` com `ObterUsuarios` — ela já separa
    técnico real de usuário do sistema, e é por isso que esta rota não precisa
    falar com o Harmonit.

    ⚠️ `excluido = 1` NÃO quer dizer "saiu da empresa": quer dizer **é usuário
    do sistema**, não técnico de campo (9 dos 200 em 21/10, entre eles o
    próprio dono). Por padrão eles ficam de fora — se entrassem, todo usuário
    interno viraria candidato a técnico.

    Devolve `chave`, que são os dígitos do e-mail: é por ela que o MoviZap
    casa, e calculá-la aqui mantém a regra num lugar só.
    """
    sql = "SELECT tecnico_id, nome, email, excluido FROM tecnicos"
    if ativos:
        sql += " WHERE excluido = 0"
    with storage._connect() as conn:
        linhas = conn.execute(sql + " ORDER BY nome").fetchall()
    return {
        "tecnicos": [
            {
                "tecnico_id": tid,
                "nome": nome,
                "email": email,
                "excluido": bool(excluido),
                # Vazio quando o e-mail não é numérico (conta interna).
                "chave": _email_do_tecnico({"email": email}),
            }
            for tid, nome, email, excluido in linhas
        ]
    }


@router.get("/endereco")
async def ler_endereco_da_os(numero_os: int = Query(..., ge=1)):
    """O endereço estruturado da OS, ao vivo do Harmonit.

    🔵 21/10: é o que pré-preenche os sete campos do modal de agendamento --
    endereço vindo da fonte é melhor que endereço digitado.

    ⚠️ VEM VAZIO COM FREQUÊNCIA, e isso é resposta: em 30 OS amostradas em
    21/10, **7 têm os oito campos em branco**. `tem_endereco: false` é o que
    diz à tela para oferecer o caminho do CEP em vez de mostrar campos vazios
    sem explicação.
    """
    os_dict = _uma_os(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": numero_os}))
    if not os_dict:
        raise HTTPException(status_code=404,
                            detail=f"OS {numero_os} nao encontrada no Harmonit")
    endereco = {c: (os_dict.get(c) or None) for c in CAMPOS_DO_ENDERECO}
    return {
        "numero_os": numero_os,
        "endereco": endereco,
        # "Tem endereço" = tem rua. CEP sozinho não leva técnico a lugar nenhum.
        "tem_endereco": bool(endereco.get("endereco")),
    }


# ---------------------------------------------------------------------------
# O ENDEREÇO DA OS — 🔵 pedido dele, 21/10: *"vai enviar para o endereço da OS
# e salvar ela lá no harmonit corretamente"*.
# ---------------------------------------------------------------------------
#
# 🚨 NÃO EXISTE "ATUALIZAR SÓ O ENDEREÇO". A única rota de escrita é
# `SalvarOrdemServico`, que a doc do Harmonit chama de *"criar/atualizar OS
# completa"*: manda-se a OS inteira, e o que não for mandado se perde. Por
# isso aqui a OS é LIDA, remontada campo a campo, gravada e **relida**, e a
# resposta diz o que mudou de verdade.
#
# 🚨 OS NOMES DE LEITURA E DE ESCRITA NÃO BATEM, e é a armadilha central desta
# rota (medido na OS 16991, em 21/10):
#
#   leitura        ->  escrita
#   tipo           ->  tipoId
#   localServico   ->  localServicoId
#   prioridade     ->  prioridadeId
#   problema       ->  problemaId
#   produtoId      ->  produtoServicoId
#   descricao      ->  descricaoDetalhada
#   dataPrevisao   ->  dataPrevisaoEntrega  (⚠️ `dd/mm/aaaa HH:MM:SS` -> ISO)
#
# ⚠️ `clienteId` NÃO TEM O MESMO NOME NOS DOIS LADOS TAMBÉM: na leitura ele vem
# como **`parceiro`** (998063 na 16991, igual ao `cliente_id` da nossa
# `os_historico`). Medido em UMA OS, então a `os_historico` continua sendo a
# fonte e o `parceiro` é só o reforço -- a base tem 547 OS e eu conferi uma.
#
# 🚨 ENSAIO A SECO ANTES DE GRAVAR: com `conferir: true` a rota monta tudo,
# diz o que mudaria e **não escreve**. Foi assim que o remapeamento foi provado
# na OS 16991 (que ele liberou) antes de a primeira escrita de verdade sair.

# Os campos escalares que a OS devolve e que esta rota tem de preservar
# inteiros. ⚠️ `checkList`, `materiais`, `oficina` e `tecnico` são LISTAS e
# **não entram no corpo da escrita** -- a rota de OS não os aceita, e cada um
# tem rota própria. Eles entram na conferência de depois: se uma lista encurtar
# por causa desta escrita, isto grita.
_ESCALARES_DA_OS = (
    "bairro", "cep", "cidade", "complemento", "dataPrevisao", "descricao",
    "empresaId", "endereco", "id", "isMobile", "localServico", "nomeVendedor",
    "numero", "numeroOrdem", "origem", "parceiro", "parceiroCodigoStr",
    "parceiroTelefone", "prioridade", "problema", "produtoCodigo",
    "produtoDescricao", "produtoId", "servicoPorTecnico", "situacaoId",
    "solucaoTecnica", "status", "statusStr", "tipo", "uf",
    "usuaroIdResponsavel", "valorOutrasRetencoes", "valorRetAlimentacao",
    "valorRetProdutosLimpeza", "valorRetValeTransporte", "vendedorId",
)
_LISTAS_DA_OS = ("checkList", "materiais", "oficina", "tecnico")

# Os únicos campos que esta rota tem o direito de mudar.
CAMPOS_DO_ENDERECO = ("cep", "endereco", "numero", "bairro", "cidade", "uf",
                      "complemento")


class EnderecoDaOS(BaseModel):
    numero_os: int
    # ⚠️ NENHUM É OBRIGATÓRIO, e os limites são os que a tela mostra. O teto
    # real do Harmonit não está documentado: o que se mediu em 30 OS reais é o
    # PISO (logradouro 41, bairro 54, cidade 21, número 4, complemento 9) --
    # prova que cabe, não prova o limite. Estes tetos são escolha nossa,
    # folgada sobre o piso medido.
    cep: str | None = Field(default=None, max_length=9)
    endereco: str | None = Field(default=None, max_length=80)
    numero: str | None = Field(default=None, max_length=10)
    bairro: str | None = Field(default=None, max_length=60)
    cidade: str | None = Field(default=None, max_length=50)
    uf: str | None = Field(default=None, max_length=2)
    complemento: str | None = Field(default=None, max_length=40)
    # 🚨 Ensaio a seco: monta, diz o que mudaria, NÃO grava.
    conferir: bool = False


def _so_digitos_cep(valor: str | None) -> str | None:
    """O CEP vai como a base o guarda: 8 dígitos, SEM máscara.

    ⚠️ A doc do Harmonit mostra `"01000-000"` com máscara e o dado real vem
    `"19013180"` sem -- medido em 30 OS. Gravar com máscara criaria duas
    formas do mesmo CEP na mesma coluna.
    """
    if valor is None:
        return None
    so = "".join(c for c in valor if c.isdigit())
    return so or None


def _previsao_iso(valor) -> str | None:
    """`dd/mm/aaaa HH:MM:SS` -> ISO, que é o que a escrita espera.

    🚨 DEVOLVER O TEXTO BRUTO AQUI APAGARIA A PREVISÃO DA OS: o campo é 100%
    preenchido na base (572 de 572) e é por ele que a aba Operações mede
    prazo.
    """
    if not valor:
        return None
    texto = str(valor).strip()
    for forma in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, forma).isoformat()
        except ValueError:
            continue
    # Já vem ISO? Então segue. Formato desconhecido NÃO vira None em silêncio.
    try:
        return datetime.fromisoformat(texto).isoformat()
    except ValueError:
        log.warning("dataPrevisao em formato desconhecido: %r", texto)
        raise HTTPException(
            status_code=500,
            detail=(f"nao sei converter a dataPrevisao {texto!r} desta OS, e "
                    f"gravar sem ela apagaria a previsao"))


def _corpo_de_escrita(os_dict: dict, cliente_id: int, novo: dict) -> dict:
    """A OS inteira, remontada, com SÓ o endereço trocado."""
    atual = {c: os_dict.get(c) for c in CAMPOS_DO_ENDERECO}
    atual.update({k: v for k, v in novo.items() if v is not None})
    return {
        "id": os_dict.get("id"),
        "empresaId": os_dict.get("empresaId"),
        "numeroOrdem": os_dict.get("numeroOrdem"),
        "dataPrevisaoEntrega": _previsao_iso(os_dict.get("dataPrevisao")),
        "localServicoId": os_dict.get("localServico"),
        "tipoId": os_dict.get("tipo"),
        "prioridadeId": os_dict.get("prioridade"),
        "situacaoId": os_dict.get("situacaoId"),
        "problemaId": os_dict.get("problema"),
        "produtoServicoId": os_dict.get("produtoId"),
        "clienteId": cliente_id,
        "descricaoDetalhada": os_dict.get("descricao"),
        "status": os_dict.get("status"),
        # 🚨 PASSA O VALOR COMO ESTA, sem `or ""`: a escrita no-op de 21/10
        # provou que `or ""` troca `null` por string vazia nesta coluna -- e a
        # comparacao de depois acusou. Diferenca pequena e diferenca.
        "solucaoTecnica": os_dict.get("solucaoTecnica"),
        "valorRetAlimentacao": os_dict.get("valorRetAlimentacao") or 0,
        "valorRetProdutosLimpeza": os_dict.get("valorRetProdutosLimpeza") or 0,
        "valorRetValeTransporte": os_dict.get("valorRetValeTransporte") or 0,
        "vendedorId": os_dict.get("vendedorId") or 0,
        "bairro": atual.get("bairro"),
        "cep": _so_digitos_cep(atual.get("cep")),
        "cidade": atual.get("cidade"),
        "endereco": atual.get("endereco"),
        "uf": atual.get("uf"),
        "complemento": atual.get("complemento"),
        "numero": atual.get("numero"),
    }


def _diferencas(antes: dict, depois: dict) -> dict:
    """O que mudou de fato, lendo os dois retratos da OS."""
    mudou = {}
    for c in _ESCALARES_DA_OS:
        if antes.get(c) != depois.get(c):
            mudou[c] = {"antes": antes.get(c), "depois": depois.get(c)}
    for c in _LISTAS_DA_OS:
        a, d = len(antes.get(c) or []), len(depois.get(c) or [])
        if a != d:
            mudou[c] = {"antes": f"{a} itens", "depois": f"{d} itens"}
    return mudou


@router.post("/endereco")
async def gravar_endereco_da_os(entrada: EnderecoDaOS):
    """Grava o endereço na OS do Harmonit. 🚨 A prova é RELER e COMPARAR.

    Devolve `{"ok", "mudou", "fora_do_endereco"}`. 🚨 `fora_do_endereco` é o
    que importa: se esta escrita tocou qualquer campo que não é endereço, ela
    diz quais, por extenso. Não dá para desfazer -- o que dá é não descobrir
    seis meses depois.
    """
    antes = _uma_os(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": entrada.numero_os}))
    if not antes:
        raise HTTPException(
            status_code=404,
            detail=f"OS {entrada.numero_os} nao encontrada no Harmonit")

    # ⚠️ A `os_historico` é a fonte do cliente; o `parceiro` da própria OS é o
    # reforço quando ela não o tem (OS nova, ainda não varrida).
    cliente_id = _cliente_da_os(entrada.numero_os) or antes.get("parceiro")
    if not cliente_id:
        return {"ok": False, "numero_os": entrada.numero_os,
                "motivo": "nao sei o cliente desta OS, e gravar sem ele a "
                          "desvincularia do cadastro"}

    novo = {c: getattr(entrada, c) for c in CAMPOS_DO_ENDERECO}
    corpo = _corpo_de_escrita(antes, cliente_id, novo)

    if entrada.conferir:
        # 🚨 Ensaio a seco: nada é escrito.
        return {
            "ok": True, "conferido_sem_gravar": True,
            "numero_os": entrada.numero_os, "corpo": corpo,
            "endereco_antes": {c: antes.get(c) for c in CAMPOS_DO_ENDERECO},
            "endereco_depois": {c: corpo.get(c) for c in CAMPOS_DO_ENDERECO},
        }

    try:
        await harmonit_post("/OrdemServico/SalvarOrdemServico", corpo)
    except HTTPException as e:
        log.warning("SalvarOrdemServico recusou a OS %s: %s",
                    entrada.numero_os, e.detail)
        return {"ok": False, "numero_os": entrada.numero_os,
                "motivo": str(e.detail)}
    except Exception as e:  # noqa: BLE001 -- rota crua
        log.warning("SalvarOrdemServico falhou na OS %s: %s", entrada.numero_os, e)
        return {"ok": False, "numero_os": entrada.numero_os,
                "motivo": f"{type(e).__name__}: {e}"}

    # 🚨 AQUI E O CASO PERIGOSO, e e o irmao exato do `criada: null` da criacao
    # de OS: a escrita JA FOI ENVIADA e aceita. Se a releitura falhar, nao se
    # sabe se a situacao mudou -- e `gravou: False` seria mentira tanto quanto
    # `gravou: True`. Entao: `gravou: None`, e a mensagem manda conferir a mao.
    try:
        depois = _uma_os(await harmonit_get(
            "/OrdemServico/ObterOrdemServicoPorNumero",
            params={"numeroOs": entrada.numero_os}))
    except Exception as e:  # noqa: BLE001 -- rota crua
        log.error("a situacao da OS %s foi ENVIADA e a releitura falhou: %s",
                  entrada.numero_os, e)
        return {
            "ok": False, "gravou": None, "numero_os": entrada.numero_os,
            "de": de, "para": entrada.situacao_id,
            "motivo": (f"a escrita da situacao foi ENVIADA e aceita, e a "
                       f"releitura falhou ({type(e).__name__}): NAO SE SABE se "
                       f"a OS {entrada.numero_os} mudou. Confira a mao e NAO "
                       f"tente de novo as cegas"),
        }
    mudou = _diferencas(antes, depois)
    fora = {k: v for k, v in mudou.items() if k not in CAMPOS_DO_ENDERECO}
    if fora:
        # 🚨 ISTO É FALHA, mesmo com o endereço gravado: a OS perdeu ou ganhou
        # algo que esta rota não devia tocar, e dizê-lo é a única reação
        # honesta -- o remapeamento está errado em algum campo.
        log.error("SalvarOrdemServico mudou campos fora do endereco na OS %s: %s",
                  entrada.numero_os, fora)
    return {
        "ok": not fora,
        "numero_os": entrada.numero_os,
        "mudou": mudou,
        "fora_do_endereco": fora or None,
        "endereco": {c: depois.get(c) for c in CAMPOS_DO_ENDERECO},
    }


# ---------------------------------------------------------------------------
# CRIAR A OS DO CHAMADO — Bloco A do pipeline da operação (29/10)
# ---------------------------------------------------------------------------
#
# 🔵 Decisão D4 dele: *"todo chamado de suporte abrirá uma OS"*, automático no
# envio. E D3: **uma OS por placa** informada — o que inverteu a decisão de
# 23/10 (uma por envio).
#
# 🚨 A OS QUE NASCE AQUI É DE ANÁLISE, NUNCA DE SERVIÇO. Palavras dele, em
# 23/10: *"somente 1 OS para analise do problema mesmo, se for necessário
# manutenção, daí será gerada pelo painel de 'Operações' do FPSL"*. É por isso
# que o `problemaId` do chamado de suporte é **12760 ANÁLISE OPERACIONAL** e a
# OS nasce **sem técnico** (3.4: *"o tecnico é outro fluxo"*).
#
# 🚨 POR QUE `SalvarOrdemServico` E NÃO `SalvarOrdemServicoBasica`: a básica
# aceita 5 campos e não aceita `situacaoId` nem `produtoServicoId` — e os dois
# são decisão dele (38 e o `ABERTURA DE OS` de R$ 0,01). A OS nasceria fora da
# primeira coluna do painel e sem o item que ele criou para contar abertura.
#
# 🚨 OS IDS DE CATÁLOGO FORAM CONFERIDOS CONTRA O ERP em 29/10, lendo: `1782`
# Demanda Interna · `1783` Solicitação de Cliente · `12760` ANÁLISE
# OPERACIONAL · `38` Novo Solicitação 1ª · `382` Normal. Id de catálogo errado
# não dá erro de escrita: dá OS torta e muda.
#
# ⚠️ `status = 2` ("Nova") NÃO É CHUTE: a doc do Harmonit mostra `1` no exemplo
# e o dado real diz outra coisa — no cache, `2` é "Nova" em 302 OS, e a 17050,
# aberta por eles em 29/10, nasceu com `2`. Segue-se o dado.
#
# ⚠️ O ENDEREÇO NASCE VAZIO, de propósito: o chamado de análise não tem
# endereço de serviço, e inventar um seria pior que não ter. Quem agenda
# preenche depois, pela rota `/endereco` (21/10).

# A empresa e o local do serviço são os mesmos de toda OS da casa — lidos da
# OS 17050 em 29/10, e iguais aos da 16991 de 21/10.
EMPRESA_PADRAO = 98
LOCAL_SERVICO_PADRAO = 1

# "Nova". Ver a advertência acima: medido, não copiado da doc.
STATUS_NOVA = 2


class CriarOS(BaseModel):
    """O chamado que vira OS. 🚨 Nada aqui tem valor-padrão de catálogo.

    ⚠️ DE PROPÓSITO: `tipo_id`, `problema_id`, `situacao_id` e `prioridade_id`
    são obrigatórios e vêm de quem chama. Um padrão aqui faria esta rota
    decidir regra de negócio que é do MoviZap — o `tipoId` vem da ORIGEM do
    chamado, e a origem este lado não conhece.
    """
    cliente_id: int = Field(..., ge=1)
    tipo_id: int = Field(..., ge=1)
    problema_id: int = Field(..., ge=1)
    situacao_id: int = Field(..., ge=1)
    prioridade_id: int = Field(..., ge=1)
    descricao: str = Field(..., min_length=1, max_length=4000)
    produto_servico_id: int | None = None
    empresa_id: int = EMPRESA_PADRAO
    local_servico_id: int = LOCAL_SERVICO_PADRAO
    # 🚨 Ensaio a seco, como na rota de endereço: monta, devolve o corpo, NÃO
    # escreve. É o que permite provar o corpo inteiro antes de a primeira OS de
    # verdade existir no ERP.
    conferir: bool = False


def _corpo_de_criacao(e: CriarOS) -> dict:
    """A OS nova, inteira. `id: 0` e `numeroOrdem: 0` é o que manda criar."""
    return {
        "id": 0,
        "numeroOrdem": 0,
        "empresaId": e.empresa_id,
        "localServicoId": e.local_servico_id,
        "tipoId": e.tipo_id,
        "prioridadeId": e.prioridade_id,
        "situacaoId": e.situacao_id,
        "problemaId": e.problema_id,
        "produtoServicoId": e.produto_servico_id or 0,
        "clienteId": e.cliente_id,
        "descricaoDetalhada": e.descricao,
        "status": STATUS_NOVA,
        # ⚠️ A previsão é AGORA: medido em 29/10, `dataPrevisao` é a data de
        # criação da OS em 12 de 12 conferidas. Mandar nulo deixaria em branco
        # o campo pelo qual a aba Operações mede prazo (100% preenchido nas 572).
        "dataPrevisaoEntrega": datetime.now().isoformat(timespec="seconds"),
        # Nasce vazia. Ver a advertência do cabeçalho.
        "solucaoTecnica": "",
        "bairro": None, "cep": None, "cidade": None,
        "endereco": None, "uf": None, "complemento": None, "numero": None,
        "valorRetAlimentacao": 0,
        "valorRetProdutosLimpeza": 0,
        "valorRetValeTransporte": 0,
        "vendedorId": 0,
    }


def _numero_da_resposta(r) -> tuple[int | None, int | None]:
    """`(numeroOrdem, osId)` do que o Harmonit devolveu na criação.

    🚨 NÃO SE CONFIA NISTO COMO PROVA — serve só para saber ONDE reler. A
    prova é a releitura, logo abaixo.

    ⚠️ A doc mostra `{"data": {"ordemServicoId", "numeroOrdem"}}` para a rota
    BÁSICA e não documenta o retorno da completa. Então aqui se procura por
    todos os nomes plausíveis, e não achar nenhum é uma resposta tratada, não
    um `KeyError`.
    """
    d = r.get("data") if isinstance(r, dict) and "data" in r else r
    if isinstance(d, list):
        d = d[0] if d else {}
    if not isinstance(d, dict):
        return None, None

    def _int(valor):
        try:
            return int(valor) if valor else None
        except (TypeError, ValueError):
            return None

    numero = _int(d.get("numeroOrdem") or d.get("numeroOs") or d.get("numero"))
    os_id = _int(d.get("ordemServicoId") or d.get("osId") or d.get("id"))
    return numero, os_id


# O que a releitura tem de encontrar igual ao pedido. 🚨 A chave é o nome de
# LEITURA e o valor é o campo da entrada: os dois lados não têm o mesmo nome, e
# é a armadilha central desta ponte (ver o cabeçalho da escrita de endereço).
_CONFERIR_NA_RELEITURA = {
    "tipo": "tipo_id",
    "problema": "problema_id",
    "situacaoId": "situacao_id",
    "prioridade": "prioridade_id",
    "parceiro": "cliente_id",
}


@router.post("/criar")
async def criar_os(entrada: CriarOS):
    """Cria a OS de análise do chamado no Harmonit. 🚨 A prova é RELER.

    Devolve `{"ok", "criada", "numero_os", "os_id", "divergencias"}`.

    🚨 `ok: false` COM OS CRIADA É POSSÍVEL, e é o segundo pior caso desta
    rota: o Harmonit aceitou a escrita e a releitura achou campo diferente do
    pedido. A resposta diz **quais**, por extenso, e quem chama tem de guardar
    o número de qualquer forma — OS criada e não registrada do nosso lado é OS
    órfã no ERP, que ninguém sabe que existe.

    🚨 E `criada: null` É O PIOR, O QUE NÃO SE PODE MASCARAR: se o Harmonit
    respondeu sem dizer o número, pode haver OS criada e nós não sabemos qual.
    A resposta diz isso em voz alta em vez de devolver "falhou" — que faria
    quem chama tentar de novo e criar a segunda.
    """
    corpo = _corpo_de_criacao(entrada)

    if entrada.conferir:
        # 🚨 Ensaio a seco: nada é escrito.
        return {"ok": True, "conferido_sem_gravar": True, "corpo": corpo}

    try:
        resposta = await harmonit_post("/OrdemServico/SalvarOrdemServico", corpo)
    except HTTPException as e:
        log.warning("SalvarOrdemServico recusou a OS nova do cliente %s: %s",
                    entrada.cliente_id, e.detail)
        return {"ok": False, "criada": False, "motivo": str(e.detail)}
    except Exception as e:  # noqa: BLE001 -- rota crua
        log.warning("SalvarOrdemServico falhou na OS nova do cliente %s: %s",
                    entrada.cliente_id, e)
        return {"ok": False, "criada": False,
                "motivo": f"{type(e).__name__}: {e}"}

    numero, os_id = _numero_da_resposta(resposta)
    if not numero:
        # 🚨 Ver a advertência do docstring: isto NÃO é "falhou".
        log.error("SalvarOrdemServico nao devolveu numero de OS; resposta: %r",
                  resposta)
        return {
            "ok": False, "criada": None, "numero_os": None, "os_id": os_id,
            "motivo": ("o Harmonit aceitou a escrita e nao disse o numero da "
                       "OS. PODE HAVER OS CRIADA no ERP sem registro deste "
                       "lado -- nao tente de novo sem conferir a mao, ou "
                       "nascem duas"),
            "resposta_crua": resposta,
        }

    # 🚨 A PROVA: reler a OS e comparar com o que foi pedido. O retorno da
    # escrita não é prova -- é a régua desta frente inteira.
    lida = _uma_os(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": numero}))
    if not lida:
        log.error("OS %s criada e a releitura nao a encontrou", numero)
        return {"ok": False, "criada": True, "numero_os": numero,
                "os_id": os_id,
                "motivo": (f"a OS {numero} foi criada e a releitura nao a "
                           f"encontrou -- registre o numero e confira a mao")}

    divergencias = {}
    for campo_lido, campo_pedido in _CONFERIR_NA_RELEITURA.items():
        pedido = getattr(entrada, campo_pedido)
        achado = lida.get(campo_lido)
        if achado != pedido:
            divergencias[campo_lido] = {"pedido": pedido, "gravado": achado}

    if divergencias:
        log.error("OS %s nasceu diferente do pedido: %s", numero, divergencias)

    return {
        "ok": not divergencias,
        "criada": True,
        "numero_os": numero,
        "os_id": lida.get("id") or os_id,
        "situacao_id": lida.get("situacaoId"),
        "cliente_id": lida.get("parceiro"),
        "divergencias": divergencias or None,
    }


# ---------------------------------------------------------------------------
# AS OS DO PAINEL — Bloco B do pipeline da operação (29/10)
# ---------------------------------------------------------------------------
#
# 🔵 Decisão D8 dele: o card é a OS, **de qualquer origem** — *"seja pelo
# painel, seja pelo FPSL, seja pelo formulario, seja a mão"*. Até aqui o painel
# lia só `formulario_solicitacao`, e havia **uma** solicitação na base: a tela
# estava tecnicamente certa e praticamente vazia.
#
# 🔵 D9: a data matriz é **24/10/2026** e *"a data inicial é somente do
# Owner"* · *"não vamos retroagir mais do que o dia que pedi"*.
#
# 🚨 LÊ O CACHE, NÃO O ERP. A `os_historico` é varrida do Harmonit a cada 5 min
# pelo `os_scan_router`, e é o único jeito de montar 17 colunas sem uma chamada
# ao ERP por OS. O preço é a defasagem — e por isso a resposta DIZ quando cada
# OS foi vista (`visto_em`). Tela que mostra dado velho sem dizer que é velho é
# da mesma família do `M12`.
#
# ⚠️ `data_previsao` É TEXTO `dd/mm/aaaa HH:MM:SS`, e o corte usa o
# `_PREVISAO_ISO` do topo deste arquivo: `date()` devolve zero linha no formato
# brasileiro. Já custou um plano inteiro em 19/10.
#
# 🚨 E O CORTE POR `dataPrevisao` TEM PRAZO DE VALIDADE. Medido em 29/10: ela é
# a data de criação da OS em 12 de 12 conferidas — **mas a frente do aviso
# prévio vai movê-la em +90 dias**. No dia em que isso entrar, este filtro
# deixa de significar "criada desde" e passa a significar outra coisa, **sem
# erro e sem aviso**. Quem mexer no aviso prévio tem de voltar aqui.


@router.get("/por-situacao")
async def os_por_situacao(
    desde: str = Query(..., description="aaaa-mm-dd — a data matriz do painel"),
    so_abertas: int = Query(1, ge=0, le=1),
    teto: int = Query(600, ge=1, le=3000),
):
    """As OS por situação, desde uma data — o que o painel da Operação monta.

    🚨 `so_abertas` É INTERRUPTOR, LIGADO POR PADRÃO, e a razão é medida: "em
    aberto" = não finalizada, e isso **não** esvazia as colunas finais (as OS
    em "Atendimento finalizado" estão com `status` *Iniciada* — situação e
    status são eixos independentes), **mas zera o Financeiro**, porque as OS
    financeiras nascem `Finalizado`. Quem quer ver o Financeiro desliga, e a
    tela tem de dizer que está desligado.

    ⚠️ A OS EXCLUÍDA NUNCA ENTRA, com interruptor ou sem: excluída no ERP não é
    "fechada", é inexistente.

    🚨 `situacao_id = 0` NÃO É UMA SITUAÇÃO, e esta rota não o traduz. São 129
    OS no cache (medido em 29/10), e **o que fazer com elas é decisão dele** —
    a proposta no plano é `0` + *Nova* → primeira etapa e `0` + *Finalizado* →
    finalizado, e enquanto ele não disser, quem monta o quadro as conta em
    `fora_do_quadro` em vez de escolher calado por ele.
    """
    try:
        date.fromisoformat(desde)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"a data matriz {desde!r} nao esta em aaaa-mm-dd")

    sql = [
        "SELECT numero_os, os_id, situacao_id, tipo, problema, produto_id,",
        "       cliente_id, data_previsao, status, status_str, n_oficinas,",
        "       oficinas_json, tecnicos_json, visto_em, atualizado_em",
        "  FROM os_historico",
        " WHERE coalesce(excluida, 0) = 0",
        f"   AND {_PREVISAO_ISO} >= ?",
    ]
    params: list = [desde]
    if so_abertas:
        sql.append(f"   AND {_EM_ABERTO}")
    sql.append(" ORDER BY numero_os DESC")
    sql.append(" LIMIT ?")
    params.append(teto)

    with storage._connect() as conn:
        linhas = conn.execute("\n".join(sql), params).fetchall()
        # O dicionário de nomes, lido UMA vez por requisição e não por linha —
        # como a `os_por_cliente` já faz.
        # 🚨 Desde 29/10 ele tem os **28** do catálogo, não os 5 da rota curta:
        # era a rota curta que fazia 189 OS aparecerem sem nome de tipo.
        nomes_de_tipo = storage.nomes_dos_tipos_os(conn)

    conhecidas = {sid for sid, _ in _SITUACOES_DO_PAINEL}
    saida = []
    for (numero, os_id, situacao, tipo, problema, produto, cliente, previsao,
         status, status_str, n_oficinas, oficinas, tecnicos, visto,
         atualizado) in linhas:
        saida.append({
            "numero_os": numero,
            "os_id": os_id,
            "situacao_id": situacao,
            # 🚨 `0` e `NULL` NÃO SÃO A MESMA COISA, e já custou uma coluna
            # inteira em 22/10: `0` é "o ERP gravou zero" e `NULL` é "a
            # varredura não leu". A tela precisa dos dois separados.
            "sem_situacao": situacao is None,
            "situacao_zero": situacao == 0,
            "tem_coluna": situacao in conhecidas,
            "tipo": tipo,
            # ⚠️ Nulo só se o tipo não estiver no catálogo de 28. Desde 29/10
            # isso não acontece em nenhuma das 574 OS da base — mas continua
            # podendo acontecer com tipo criado depois da última varredura.
            "tipo_nome": nomes_de_tipo.get(tipo),
            "problema": problema,
            "produto_id": produto,
            "cliente_id": cliente,
            "data_previsao": previsao,
            "status": status,
            "status_str": status_str,
            "finalizada": status_str == "Finalizado",
            "placas": _placas(oficinas),
            "n_oficinas": n_oficinas,
            "tecnicos": _tecnicos_da_os(tecnicos),
            # 🚨 QUANDO ESTA OS FOI VISTA. É o que permite a tela dizer "dado
            # de 5 min atrás" em vez de deixar o operador supor que é agora.
            "visto_em": visto,
            "atualizado_em": atualizado,
        })

    return {
        "desde": desde,
        "so_abertas": bool(so_abertas),
        "quantas": len(saida),
        # 🚨 O teto é DITO quando bate, nunca cortado em silêncio.
        "no_teto": len(saida) >= teto,
        # Quantas não têm coluna no painel, já contadas aqui para quem monta o
        # quadro não precisar varrer a lista de novo.
        "sem_coluna": sum(1 for o in saida if not o["tem_coluna"]),
        "os": saida,
    }


# As 17 situações do painel da Operação. ⚠️ A FONTE É O MOVIZAP
# (`movizap/paineis.py`, tupla `SITUACOES`) — aqui elas existem só para a ponte
# poder dizer `tem_coluna`, e a ordem não importa deste lado.
#
# 🚨 DUAS CÓPIAS É UMA VERDADE A MAIS, e isso está assumido: a alternativa era
# o MoviZap mandar as 17 em toda chamada, e a lista é decisão dele que muda em
# cadastro, não em operação. Se divergirem, quem manda é o MoviZap — e o
# sintoma será `tem_coluna` errado, não card perdido: quem monta o quadro
# reconfere pela tupla dele.
_SITUACOES_DO_PAINEL = (
    (38, "Novo Solicitação 1ª"),
    (16487, "Pendente de ação da Movisat"),
    (251, "Configurar equipamentos e Sistemas"),
    (16488, "Entrega de materiais prontos"),
    (677, "Enviar por correio/transportadora"),
    (15747, "Aguardando recebimento via correio/transportadora"),
    (15797, "Rescisão Aguardando Aviso Prévio"),
    (890, "Agendar serviço"),
    (16489, "Confirmação agendamento"),
    (1316, "Serviço Agendado"),
    (15696, "Aguardando devolução de equipamento"),
    (16490, "Analise de Equipamentos Retornados"),
    (15694, "Atendimento finalizado"),
    (16491, "Não atendido"),
    (15746, "Financeiro"),
    (15695, "Pós venda"),
    (16492, "Contratual"),
)


def _tecnicos_da_os(tecnicos_json: str | None) -> list[dict]:
    """Quem está vinculado à OS, do `tecnicos_json`.

    ⚠️ A MAIORIA DAS OS NÃO TEM TÉCNICO, e isso não é erro: a OS de análise
    nasce sem técnico por decisão dele (*"o tecnico é outro fluxo e talvez não
    chegue a ter tecnico"*). Lista vazia é o caso comum.

    🚨 O MESMO TÉCNICO APARECE MAIS DE UMA VEZ, e é de propósito no Harmonit: o
    segundo vínculo de 21/10 é o caminho para reagendar (`TecnicoJaAgendado` é
    do VÍNCULO, não do técnico). Então a tela recebe um por técnico, e o número
    de vínculos fica dito em `vinculos` — deduplicar escondendo isso faria
    desaparecer a razão pela qual o reagendamento funciona.
    """
    if not tecnicos_json:
        return []
    try:
        tecnicos = json.loads(tecnicos_json)
    except (ValueError, TypeError):
        # Dado do Harmonit, varrido por rotina: não derruba a consulta.
        log.warning("tecnicos_json ilegivel numa OS -- devolvendo sem tecnico")
        return []
    if not isinstance(tecnicos, list):
        return []
    por_usuario: dict = {}
    for t in tecnicos:
        if not isinstance(t, dict):
            continue
        uid = t.get("usuarioId")
        if uid is None:
            continue
        atual = por_usuario.setdefault(uid, {
            "usuario_id": uid,
            "nome": t.get("nome") or t.get("usuarioNome") or None,
            "agendamento_id": None,
            "vinculos": 0,
        })
        atual["vinculos"] += 1
        # ⚠️ O vínculo COM agendamento ganha: é o que a tela quer mostrar, e um
        # técnico com dois vínculos tem o compromisso em apenas um deles.
        if t.get("agendamentoId") and not atual["agendamento_id"]:
            atual["agendamento_id"] = t.get("agendamentoId")
    return list(por_usuario.values())


# ---------------------------------------------------------------------------
# ESCREVER A SITUAÇÃO DA OS — Bloco D do pipeline da operação (29/10)
# ---------------------------------------------------------------------------
#
# 🔵 É o motivo que ele deu para o painel existir (22/10): *"hoje ainda não
# usamos a situação da OS, por isso o painel e consulta para atualizar a
# situação no painel"*.
#
# 🔵 E a ordem é LIVRE, por decisão dele em 29/10: *"que tal de caminho proibido
# é esse??"* — não existe caminho proibido. ⚠️ A pergunta era minha, não dele, e
# fica registrado que ela foi descartada: **esta rota não valida transição**. O
# Harmonit também não (medido: de "Serviço Realizado" para "Agendamento" e ele
# aceitou).
#
# 🚨 NÃO EXISTE "ALTERAR SÓ A SITUAÇÃO". Como no endereço (21/10), a única
# escrita é `SalvarOrdemServico`, que grava a OS INTEIRA — então aqui a OS é
# lida, remontada campo a campo pelo `_corpo_de_escrita`, gravada e **relida**.
# Provado em 29/10 na OS 16991: a releitura dos 40 campos/listas acusa **só** o
# `situacaoId`.
#
# 🚨 E ESTA ROTA ATUALIZA O CACHE, diferente da do endereço. O card vem da
# `os_historico`, varrida a cada 5 min: sem isto, movido o card ele **voltaria
# para a coluna antiga** na próxima abertura do painel por até 5 minutos — e a
# pessoa concluiria que não gravou e moveria de novo.


class SituacaoDaOS(BaseModel):
    numero_os: int = Field(..., ge=1)
    situacao_id: int = Field(..., ge=0)
    # 🚨 A TRAVA DE CONCORRÊNCIA: a situação que a TELA tinha quando carregou o
    # card. A rota relê e, se o ERP já estiver em outra, **recusa**. 🔵 Ele
    # considerou o risco pequeno (*"cada 1 atua em uma área especifica do
    # fluxo"*) e pediu a trava mesmo assim (*"mas pode ter sim"*).
    #
    # ⚠️ NULO É LEGÍTIMO e quer dizer "a OS não tinha situação quando eu li" —
    # não "não confira". Quem não quiser conferir manda `conferir_antes: false`.
    situacao_esperada: int | None = None
    conferir_antes: bool = True


@router.post("/situacao")
async def gravar_situacao_da_os(entrada: SituacaoDaOS):
    """Grava a situação da OS no Harmonit. 🚨 A prova é RELER e COMPARAR.

    Devolve `{"ok", "numero_os", "de", "para", "mudou", "fora_da_situacao"}`.

    🚨 `fora_da_situacao` É O QUE IMPORTA quando vem preenchido: esta escrita
    tocou algum campo que não é a situação, e aí `ok` é falso **mesmo com a
    situação gravada** — o remapeamento está errado em algum campo. Não dá para
    desfazer; o que dá é não descobrir seis meses depois.
    """
    # 🚨 A LEITURA DE ANTES TAMBEM FALHA, e ela estava sem guarda: um 502 do
    # Harmonit aqui estourava a rota, e quem chamava recebia "o FPSL respondeu
    # 502" -- que nao diz nada sobre a escrita. Aqui e SEGURO (nada foi escrito
    # ainda), e por isso a resposta pode ser clara: nao gravou, e pode tentar
    # de novo.
    try:
        antes = _uma_os(await harmonit_get(
            "/OrdemServico/ObterOrdemServicoPorNumero",
            params={"numeroOs": entrada.numero_os}))
    except Exception as e:  # noqa: BLE001 -- rota crua
        log.warning("nao deu para ler a OS %s antes de mover: %s",
                    entrada.numero_os, e)
        return {"ok": False, "gravou": False, "numero_os": entrada.numero_os,
                "de": None, "para": entrada.situacao_id,
                "motivo": (f"nao deu para ler a OS {entrada.numero_os} no "
                           f"Harmonit antes de mover ({type(e).__name__}) -- "
                           f"nada foi escrito, pode tentar de novo")}
    if not antes:
        raise HTTPException(
            status_code=404,
            detail=f"OS {entrada.numero_os} nao encontrada no Harmonit")

    de = antes.get("situacaoId")

    # 🚨 A TRAVA DE CONCORRÊNCIA, antes de qualquer escrita.
    if entrada.conferir_antes and de != entrada.situacao_esperada:
        return {
            "ok": False, "gravou": False, "numero_os": entrada.numero_os,
            "de": de, "para": entrada.situacao_id,
            "motivo": (f"a OS {entrada.numero_os} esta na situacao {de} no "
                       f"Harmonit, e a tela carregou "
                       f"{entrada.situacao_esperada}. Alguem mudou no meio -- "
                       f"recarregue o painel antes de mover"),
            "conflito": True,
        }

    # ⚠️ Mover para onde já está não é erro, e também não é escrita: gravar a
    # OS inteira por nada é risco sem ganho.
    if de == entrada.situacao_id:
        return {"ok": True, "gravou": False, "numero_os": entrada.numero_os,
                "de": de, "para": entrada.situacao_id,
                "motivo": "a OS ja estava nesta situacao"}

    cliente_id = _cliente_da_os(entrada.numero_os) or antes.get("parceiro")
    if not cliente_id:
        return {"ok": False, "gravou": False, "numero_os": entrada.numero_os,
                "de": de, "para": entrada.situacao_id,
                "motivo": "nao sei o cliente desta OS, e gravar sem ele a "
                          "desvincularia do cadastro"}

    # 🚨 O MESMO MONTADOR DO ENDEREÇO, sem campo de endereço para trocar: o
    # `novo` vem vazio, então ele remonta o endereço como está. Dois montadores
    # do mesmo corpo seriam duas verdades.
    corpo = _corpo_de_escrita(antes, cliente_id, {})
    corpo["situacaoId"] = entrada.situacao_id

    try:
        await harmonit_post("/OrdemServico/SalvarOrdemServico", corpo)
    except HTTPException as e:
        log.warning("SalvarOrdemServico recusou a situacao da OS %s: %s",
                    entrada.numero_os, e.detail)
        return {"ok": False, "gravou": False, "numero_os": entrada.numero_os,
                "de": de, "para": entrada.situacao_id, "motivo": str(e.detail)}
    except Exception as e:  # noqa: BLE001 -- rota crua
        log.warning("SalvarOrdemServico falhou na situacao da OS %s: %s",
                    entrada.numero_os, e)
        return {"ok": False, "gravou": False, "numero_os": entrada.numero_os,
                "de": de, "para": entrada.situacao_id,
                "motivo": f"{type(e).__name__}: {e}"}

    depois = _uma_os(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": entrada.numero_os}))
    mudou = _diferencas(antes, depois)
    fora = {k: v for k, v in mudou.items() if k != "situacaoId"}
    if fora:
        log.error("a escrita de situacao mudou campos fora dela na OS %s: %s",
                  entrada.numero_os, fora)

    gravou = (depois or {}).get("situacaoId") == entrada.situacao_id

    # 🚨 O CACHE, para o card não voltar para a coluna antiga. Ver o cabeçalho.
    # ⚠️ Só depois de a releitura confirmar: gravar no cache o que o ERP não
    # confirmou faria a tela mentir por 5 minutos no sentido contrário.
    if gravou and depois:
        try:
            await storage.salvar_os_historico(
                numero_os=entrada.numero_os,
                tipo=depois.get("tipo"), problema=depois.get("problema"),
                produto_id=depois.get("produtoId"),
                cliente_id=depois.get("parceiro") or cliente_id,
                data_previsao=depois.get("dataPrevisao"),
                oficinas=depois.get("oficina") or [],
                status=depois.get("status"), status_str=depois.get("statusStr"),
                materiais=depois.get("materiais"),
                situacao_id=depois.get("situacaoId"),
                os_id=depois.get("id"), tecnicos=depois.get("tecnico"))
        except Exception as e:  # noqa: BLE001
            # ⚠️ NÃO derruba a resposta: a escrita no ERP já aconteceu e é o
            # que importa. O cache se corrige na varredura dos 5 min.
            log.warning("a situacao da OS %s foi gravada e o cache nao "
                        "atualizou: %s", entrada.numero_os, e)

    return {
        "ok": bool(gravou) and not fora,
        "gravou": bool(gravou),
        "numero_os": entrada.numero_os,
        "de": de,
        "para": (depois or {}).get("situacaoId"),
        "mudou": mudou,
        "fora_da_situacao": fora or None,
    }


# ---------------------------------------------------------------------------
# A FICHA DA OS — Bloco E do pipeline da operação (29/10)
# ---------------------------------------------------------------------------
#
# 🔵 Ele, vendo o card aberto sem os resumos: *"onde estão os temas do card,
# após clicar?"* — os quatro do mockup: **Descrição da OS**, **Solução
# técnica**, **Dados do chamado** e **Agendamento**.
#
# 🚨 POR QUE ISTO É UMA ROTA PRÓPRIA, e não vem no quadro: `descricao` e
# `solucaoTecnica` **não estão no cache** (`os_historico` guarda tipo, problema,
# produto, cliente, previsão, status, situação, oficinas, materiais e técnicos —
# e nenhum dos dois textos). Então vêm **ao vivo do ERP**, e por isso é
# **1 chamada por card aberto** — nunca na montagem do quadro, que teria 11.
#
# ⚠️ O AGENDAMENTO sai do `tecnico` da própria OS: é lá que vive o
# `agendamentoId`. 🔵 No desenho dele o painel do agendamento *"nasce
# desabilitado e acende em Serviço Agendado"* — quem decide isso é a tela, e
# esta rota só diz o que existe.


@router.get("/ficha")
async def ficha_da_os(numero_os: int = Query(..., ge=1)):
    """A OS ao vivo, para o card aberto. 🚨 Os dois textos só existem aqui.

    Devolve `{numero_os, descricao, solucao_tecnica, previsao, prioridade,
    tipo, tipo_nome, problema, situacao_id, status_str, endereco, placas,
    tecnicos, materiais, checklist, oficina}`.

    ⚠️ **TEXTO VAZIO É RESPOSTA, NÃO FALHA.** A `solucaoTecnica` é nula ou
    vazia na maioria das OS, e o card tem de dizer *"sem solução técnica
    escrita"* em vez de mostrar uma caixa em branco que parece defeito.

    🚨 **E A FALHA DO ERP NÃO VIRA FICHA VAZIA:** se a leitura não responder,
    esta rota **estoura** — quem chama mostra *"não deu para ler a OS agora"*.
    Uma ficha vazia seria indistinguível de uma OS sem dados, e o operador
    concluiria que não há o que ver.
    """
    lida = _uma_os(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": numero_os}))
    if not lida:
        raise HTTPException(
            status_code=404,
            detail=f"OS {numero_os} nao encontrada no Harmonit")

    with storage._connect() as conn:
        nomes_de_tipo = storage.nomes_dos_tipos_os(conn)

    # ⚠️ As listas vêm da própria OS e **não** entram em escrita nenhuma —
    # cada uma tem rota própria no Harmonit e sobrevive a um save da OS.
    tecnicos = _tecnicos_da_os(json.dumps(lida.get("tecnico") or []))
    agendados = [t for t in tecnicos if t.get("agendamento_id")]

    return {
        "numero_os": numero_os,
        "os_id": lida.get("id"),
        # 🚨 Os dois textos, que é o motivo desta rota existir.
        "descricao": (lida.get("descricao") or "").strip() or None,
        "solucao_tecnica": (lida.get("solucaoTecnica") or "").strip() or None,
        "previsao": lida.get("dataPrevisao"),
        "prioridade": lida.get("prioridade"),
        "tipo": lida.get("tipo"),
        "tipo_nome": nomes_de_tipo.get(lida.get("tipo")),
        "problema": lida.get("problema"),
        "produto_descricao": lida.get("produtoDescricao"),
        "situacao_id": lida.get("situacaoId"),
        "status_str": lida.get("statusStr"),
        "cliente_id": lida.get("parceiro"),
        "cliente_telefone": lida.get("parceiroTelefone"),
        # Os sete campos, como a rota `/endereco` os devolve.
        "endereco": {c: (lida.get(c) or None) for c in CAMPOS_DO_ENDERECO},
        "tem_endereco": bool(lida.get("endereco")),
        "placas": _placas(json.dumps(lida.get("oficina") or [])),
        "tecnicos": tecnicos,
        # 🔵 O painel do agendamento *"acende em Serviço Agendado"*; aqui só se
        # diz se existe compromisso, e a tela decide.
        "tem_agendamento": bool(agendados),
        "agendamentos": agendados,
        "n_materiais": len(lida.get("materiais") or []),
        "n_checklist": len(lida.get("checkList") or []),
        "n_oficina": len(lida.get("oficina") or []),
    }
