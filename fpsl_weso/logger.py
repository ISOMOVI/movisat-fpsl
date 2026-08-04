import json
import logging
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent / "logs" / "requests.log"


def _get_logger() -> logging.Logger:
    logger = logging.getLogger("fpsl.requests")
    if logger.handlers:
        return logger
    LOG_PATH.parent.mkdir(exist_ok=True)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_req(
    entidade: str,
    metodo: str,
    rota: str,
    acao: str | None,
    id: int | None,
    ref: str | None,
    ok: bool,
    erro: str | None,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entidade": entidade,
        "metodo": metodo,
        "rota": rota,
        "acao": acao,
        "id": id,
        "ref": ref,
        "ok": ok,
        "erro": erro,
    }
    _get_logger().info(json.dumps(entry, ensure_ascii=False))

# 2026-07-29: a chave da WESO viaja na QUERY STRING (?key=...), e o httpx loga
# a URL completa quando esta em INFO. Producao roda sem INFO do httpx, entao
# nunca vazou no journal (conferido: 0 ocorrencias em 7 dias) -- mas bastava
# alguem subir o nivel de log, aqui ou numa lib, para a credencial cair em
# disco. O MoviChat aplicou esta mesma trava em 26/06 DEPOIS de ver a chave no
# log. Aqui e preventivo: silencia na origem, sem depender de ninguem lembrar.
for _nome in ("httpx", "httpcore", "hpack"):
    logging.getLogger(_nome).setLevel(logging.WARNING)
