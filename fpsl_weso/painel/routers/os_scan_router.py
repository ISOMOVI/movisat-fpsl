"""Painel "Histórico de OS" — varredura sequencial das OS do Harmonit por número
crescente, lendo a oficina embutida em cada uma.

FASE 1 (2026-07-24): SÓ LEITURA. Popula o histórico local (`os_historico`) e o
checkpoint (`os_scan_checkpoint`), sem escrever nada na WESO. O disparo pra WESA
(por evento de oficina) entra na Fase 2.

Cadências:
  - varredura a cada 5 min (pra frente, do checkpoint);
  - resync a cada 12 h da janela recente (pega oficina adicionada depois + detecta
    exclusão de OS);
  - alerta se passar >1 dia sem OS nova (numeração/scan pode ter travado).

Design (decisão do usuário): a oficina cai sempre numa OS recente (nunca se mexe em
OS antiga), então a varredura vai só pra frente; após `LIMITE_BURACOS` números
inexistentes seguidos, considera fim da sequência. O checkpoint é editável (re-scan
a partir de um número), pra cobrir exclusão em massa.
"""
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import requer_aba
from ...harmonit_client import harmonit_get
from ... import storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/painel/api/os-scan", tags=["painel-os-scan"])

CHECKPOINT_INICIAL = 16449   # 1º número - 1; a 1ª varredura começa em 16450
LIMITE_BURACOS = 10          # nº de OS inexistentes seguidas p/ considerar fim
MAX_LEITURAS = 3000          # trava de segurança por execução
RESYNC_JANELA = 400          # nº de OS recentes re-lidas no resync (~2 dias)
INTERVALO_SCAN = 300         # 5 min
INTERVALO_RESYNC = 43200     # 12 h
ALERTA_SEM_OS_SEG = 86400    # 1 dia

# Serializa scan/resync/varredura-manual -- SQLite não gosta de escrita concorrente
# e não faz sentido duas varreduras ao mesmo tempo.
_scan_lock = asyncio.Lock()


def _eh_nao_encontrada(exc: HTTPException) -> bool:
    """True só quando o Harmonit disse claramente 'Ordem de Serviço não encontrada'
    -- NÃO marca exclusão por timeout/502 genérico (evita falso-positivo)."""
    d = str(getattr(exc, "detail", "")).lower()
    return "não encontrada" in d or "nao encontrada" in d


def _unwrap(r):
    d = r.get("data") if (isinstance(r, dict) and r.get("data")) else r
    return d[0] if isinstance(d, list) else d


async def varrer_os(desde: int | None = None, limite_buracos: int = LIMITE_BURACOS,
                    max_leituras: int = MAX_LEITURAS) -> dict:
    """Varre OS por número crescente. `desde` força um ponto de partida (re-scan);
    sem ele, começa em checkpoint+1. NÃO escreve na WESO."""
    async with _scan_lock:
        checkpoint = int(await storage.get_config("os_scan_checkpoint", str(CHECKPOINT_INICIAL)) or CHECKPOINT_INICIAL)
        inicio = desde if desde is not None else checkpoint + 1
        n = inicio
        buracos = lidas = novas = com_oficina = leituras = 0
        ultima = checkpoint
        while buracos < limite_buracos and leituras < max_leituras:
            leituras += 1
            try:
                d = _unwrap(await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero", params={"numeroOs": n}))
            except HTTPException:
                d = None
            if not d:
                buracos += 1
                n += 1
                continue
            buracos = 0
            lidas += 1
            oficinas = d.get("oficina") or []
            if oficinas:
                com_oficina += 1
            nova = await storage.salvar_os_historico(
                numero_os=n, tipo=d.get("tipo"), problema=d.get("problema"),
                produto_id=d.get("produtoId"), cliente_id=d.get("parceiro") or d.get("clienteId"),
                data_previsao=d.get("dataPrevisao"), oficinas=oficinas,
            )
            if nova:
                novas += 1
            ultima = max(ultima, n)
            n += 1
        if ultima > checkpoint:
            await storage.set_config("os_scan_checkpoint", str(ultima))
        if novas > 0:
            await storage.set_config("os_scan_ultima_nova_em", datetime.now(timezone.utc).isoformat())
        return {"desde": inicio, "leituras": leituras, "lidas": lidas, "novas": novas,
                "com_oficina": com_oficina, "ultima_os": ultima, "parou_em": n - 1,
                "buracos_no_fim": buracos, "atingiu_max": leituras >= max_leituras}


async def resync_os(janela: int = RESYNC_JANELA) -> dict:
    """Re-lê a janela recente de OS pra pegar oficina adicionada depois e detectar
    exclusão (OS que sumiu do Harmonit -> marca `excluida`). NÃO escreve na WESO."""
    async with _scan_lock:
        numeros = await storage.os_para_resync(janela)
        reencontradas = excluidas = erros = 0
        for num in numeros:
            try:
                d = _unwrap(await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero", params={"numeroOs": num}))
            except HTTPException as exc:
                if _eh_nao_encontrada(exc):
                    await storage.marcar_os_excluida(num); excluidas += 1
                else:
                    erros += 1
                continue
            if not d:
                await storage.marcar_os_excluida(num); excluidas += 1
                continue
            await storage.salvar_os_historico(
                numero_os=num, tipo=d.get("tipo"), problema=d.get("problema"),
                produto_id=d.get("produtoId"), cliente_id=d.get("parceiro") or d.get("clienteId"),
                data_previsao=d.get("dataPrevisao"), oficinas=d.get("oficina") or [],
            )
            reencontradas += 1
        return {"janela": len(numeros), "reencontradas": reencontradas, "excluidas": excluidas, "erros": erros}


async def _alerta_data() -> str | None:
    ultima = await storage.get_config("os_scan_ultima_nova_em", "")
    if not ultima:
        return None
    try:
        delta = datetime.now(timezone.utc) - datetime.fromisoformat(ultima)
    except ValueError:
        return None
    if delta.total_seconds() > ALERTA_SEM_OS_SEG:
        return f"Nenhuma OS nova há {int(delta.total_seconds() // 3600)}h — verifique a numeração/scan."
    return None


# ── Agendadores (iniciados no lifespan do app) ────────────────────────────────

async def loop_scan_os():
    """Varredura a cada 5 min. Sobe uma baseline de 'ultima_nova' pra não alertar
    falso no 1º dia."""
    if not await storage.get_config("os_scan_ultima_nova_em", ""):
        await storage.set_config("os_scan_ultima_nova_em", datetime.now(timezone.utc).isoformat())
    while True:
        try:
            r = await varrer_os()
            if r["novas"]:
                logger.info("scan-os: %s OS novas (última %s)", r["novas"], r["ultima_os"])
        except Exception:
            logger.exception("scan-os: falha na varredura periódica")
        await asyncio.sleep(INTERVALO_SCAN)


async def loop_resync_os():
    """Resync a cada 12 h da janela recente."""
    await asyncio.sleep(600)  # espaça do boot pra não competir com a 1ª varredura
    while True:
        try:
            r = await resync_os()
            logger.info("resync-os: %s reencontradas, %s excluídas, %s erros", r["reencontradas"], r["excluidas"], r["erros"])
        except Exception:
            logger.exception("resync-os: falha no resync periódico")
        await asyncio.sleep(INTERVALO_RESYNC)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/varrer")
async def varrer(desde: int | None = Query(None), _=Depends(requer_aba("os_historico"))):
    return await varrer_os(desde=desde)


@router.post("/resync")
async def resync(_=Depends(requer_aba("os_historico"))):
    return await resync_os()


@router.get("/historico")
async def historico(limit: int = Query(300, le=1000),
                    apenas_com_oficina: bool = Query(False),
                    _=Depends(requer_aba("os_historico"))):
    total = await storage.contar_os_historico()
    checkpoint = int(await storage.get_config("os_scan_checkpoint", str(CHECKPOINT_INICIAL)))
    itens = await storage.listar_os_historico(limit, apenas_com_oficina)
    return {"checkpoint": checkpoint, "total": total,
            "ultima_nova_em": await storage.get_config("os_scan_ultima_nova_em", ""),
            "alerta": await _alerta_data(), "itens": itens}


class CheckpointInput(BaseModel):
    valor: int


@router.get("/checkpoint")
async def obter_checkpoint(_=Depends(requer_aba("os_historico"))):
    return {"checkpoint": int(await storage.get_config("os_scan_checkpoint", str(CHECKPOINT_INICIAL)))}


@router.put("/checkpoint")
async def definir_checkpoint(body: CheckpointInput, _=Depends(requer_aba("os_historico"))):
    await storage.set_config("os_scan_checkpoint", str(body.valor))
    return {"ok": True, "checkpoint": body.valor}
