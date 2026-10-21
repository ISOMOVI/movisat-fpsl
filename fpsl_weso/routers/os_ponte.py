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
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ..config import settings
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
