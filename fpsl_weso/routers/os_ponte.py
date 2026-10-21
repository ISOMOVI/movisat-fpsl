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
    # O nome do técnico no MoviZap. ⚠️ É o único elo que existe: o MoviZap
    # conhece o técnico como CONTATO de WhatsApp e o Harmonit como usuário da
    # OS — não há tabela ligando os dois. Por isso o casamento é por nome, e
    # por isso ele falha em voz alta em vez de escolher sozinho.
    tecnico_nome: str | None = Field(default=None, max_length=200)


def _simples(texto: str) -> str:
    """Nome sem acento, sem caixa e sem espaço dobrado, só para comparar."""
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


def _escolher_vinculo(tecnicos: list, nome: str | None) -> tuple[dict | None, str]:
    """Qual `ordemServicoxTecnico` recebe o compromisso.

    🚨 NUNCA ESCOLHE NO ESCURO. Com nome, casa pelo nome; sem nome, só aceita
    quando há um único técnico livre. Em qualquer outro caso devolve o motivo,
    e quem chama mostra os nomes para a pessoa decidir — agendar no técnico
    errado é pior do que não agendar.
    """
    livres = [t for t in tecnicos if not t.get("agendamentoId")]
    if nome:
        alvo = _simples(nome)
        casados = [t for t in tecnicos if _simples(t.get("nomeTecnico") or "") == alvo]
        if not casados:
            return None, (f"nenhum tecnico da OS se chama {nome!r} "
                          f"(tem: {[t.get('nomeTecnico') for t in tecnicos]})")
        livre = [t for t in casados if not t.get("agendamentoId")]
        if not livre:
            return None, (f"{nome} ja tem compromisso nesta OS "
                          f"(agendamentoId {casados[0].get('agendamentoId')})")
        return livre[0], ""
    if len(livres) == 1:
        return livres[0], ""
    if not livres:
        return None, "todos os tecnicos desta OS ja tem compromisso"
    return None, (f"a OS tem {len(livres)} tecnicos sem compromisso "
                  f"({[t.get('nomeTecnico') for t in livres]}) -- diga qual")


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

    vinculo, motivo = _escolher_vinculo(tecnicos, entrada.tecnico_nome)
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
        "tecnico": vinculo.get("nomeTecnico"),
        "janela": novo.get("agendamentoOS") or {},
    }
