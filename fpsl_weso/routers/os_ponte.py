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

    return {
        "cliente_id": cliente_id,
        "meses": meses,
        "os": [
            {
                "numero_os": n,
                # `tipo` é o ID do tipo no Harmonit, não o nome -- a base não
                # guarda o nome, e inventar um seria tela que mente.
                "tipo": tipo,
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

    🚨 NUNCA ESCOLHE NO ESCURO. Sem telefone, só aceita quando há um único
    técnico livre na OS; em qualquer outro caso devolve o motivo com os nomes
    e e-mails que a OS tem -- agendar no técnico errado é pior que não
    agendar.
    """
    livres = [t for t in tecnicos if not t.get("agendamentoId")]

    # 1º o vínculo gravado, que é identidade e não semelhança.
    if tecnico_id:
        casados = [t for t in tecnicos if t.get("usuarioId") == tecnico_id]
        if not casados:
            return None, (f"o tecnico {tecnico_id} vinculado a esta conversa nao "
                          f"esta nesta OS (tem: {_quem_tem(tecnicos)})")
        livre = [t for t in casados if not t.get("agendamentoId")]
        if not livre:
            return None, (f"{casados[0].get('nomeTecnico')} ja tem compromisso "
                          f"nesta OS (agendamentoId "
                          f"{casados[0].get('agendamentoId')})")
        return livre[0], ""

    chave = _chave_do_telefone(telefone)
    if chave:
        casados = [t for t in tecnicos if _email_do_tecnico(t) == chave]
        if not casados:
            return None, (
                f"nenhum tecnico desta OS tem o telefone {chave} no e-mail do "
                f"cadastro do Harmonit (tem: {_quem_tem(tecnicos)})")
        livre = [t for t in casados if not t.get("agendamentoId")]
        if not livre:
            return None, (f"{casados[0].get('nomeTecnico')} ja tem compromisso "
                          f"nesta OS (agendamentoId "
                          f"{casados[0].get('agendamentoId')})")
        return livre[0], ""
    if len(livres) == 1:
        return livres[0], ""
    if not livres:
        return None, "todos os tecnicos desta OS ja tem compromisso"
    return None, (f"a OS tem {len(livres)} tecnicos sem compromisso e o contato "
                  f"nao tem telefone para casar ({_quem_tem(livres)})")


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
    return {
        "ok": True,
        "numero_os": entrada.numero_os,
        "agendamento_id": agendamento_id,
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
