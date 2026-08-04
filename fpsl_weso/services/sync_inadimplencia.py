import asyncio
import logging
from datetime import datetime, date, timedelta

from ..harmonit_client import harmonit_get
from ..client import weso_get, weso_post
from .. import storage
from ..logger import log_req

logger = logging.getLogger(__name__)


async def run_sync() -> dict:
    try:
        grace_days = int(await storage.get_config("inadimplencia_grace_days", "7"))
    except ValueError:
        grace_days = 7
    threshold = date.today() - timedelta(days=grace_days)

    clientes = await storage.listar_clientes()
    resultado = {"processados": 0, "inadimplentes": 0, "adimplentes": 0, "erros": 0}

    for cliente in clientes:
        cnpj = cliente["cnpjcpf"]
        try:
            resp = await harmonit_get(
                "/Financeiro/v2/ObterBoletosEmAbertoPorCpfCnpj",
                params={"cpfCnpjCliente": cnpj},
            )
            boletos = resp if isinstance(resp, list) else (resp.get("boletos") or [])

            tem_vencido = False
            for b in boletos:
                venc_raw = b.get("dataVencimento") or b.get("DataVencimento") or ""
                if not venc_raw:
                    continue
                try:
                    venc = datetime.fromisoformat(venc_raw[:10]).date()
                except ValueError:
                    continue
                if venc < threshold:
                    tem_vencido = True
                    break

            weso_data = await weso_get("/Clientes/Consultar", params={"cnpjcpf": cnpj})
            weso_clientes = weso_data.get("clientes") or []
            situacao_atual = weso_clientes[0].get("situacao", "") if weso_clientes else ""

            if tem_vencido and situacao_atual != "Inadimplente":
                await weso_post("/Clientes/Atualizar", {"cnpjcpf": cnpj, "situacao": "Inadimplente"})
                log_req("sync", "PUT", "/weso/clientes/situacao", "inadimplente", None, cnpj, True, None)
                resultado["inadimplentes"] += 1

            elif not tem_vencido and situacao_atual == "Inadimplente":
                await weso_post("/Clientes/Atualizar", {"cnpjcpf": cnpj, "situacao": "Adimplente"})
                log_req("sync", "PUT", "/weso/clientes/situacao", "adimplente_restaurado", None, cnpj, True, None)
                resultado["adimplentes"] += 1

            resultado["processados"] += 1

        except Exception as exc:
            logger.error("sync_inadimplencia: erro em %s — %s", cnpj, exc)
            log_req("sync", "ERR", "/sync/inadimplencia", "erro", None, cnpj, False, str(exc))
            resultado["erros"] += 1

    await storage.set_config("sync_last_run_date", date.today().isoformat())
    logger.info("sync_inadimplencia: concluido %s — %s", date.today().isoformat(), resultado)
    return resultado


async def loop_inadimplencia():
    """Cron interno: dispara run_sync() apos 05:00 BRT, uma vez por dia."""
    while True:
        await asyncio.sleep(600)
        now = datetime.now()
        if now.hour < 5:
            continue
        last_run = await storage.get_config("sync_last_run_date", "")
        if last_run == date.today().isoformat():
            continue
        sync_on = await storage.get_config("inadimplencia_sync", "false")
        if sync_on != "true":
            continue
        try:
            await run_sync()
        except Exception as exc:
            logger.error("loop_inadimplencia: falha nao tratada — %s", exc)
