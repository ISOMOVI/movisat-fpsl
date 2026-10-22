"""A ponte de leitura de OS para o MoviZap — 21/10. SOMENTE LEITURA.

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

    depois = _uma_os(await harmonit_get(
        "/OrdemServico/ObterOrdemServicoPorNumero",
        params={"numeroOs": entrada.numero_os}))
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
