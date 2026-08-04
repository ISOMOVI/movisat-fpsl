# Aba 08 — Logs de Requisições

**Status:** ✅ Validado — 2026-06-15  
**Formato:** JSON Lines (uma linha por requisição)  
**Arquivo na VPS:** `/home/claude/fpsl_weso/logs/requests.log`

---

## Spec

### O que é registrado

Todas as requisições processadas pelo FPSL — sem exceção de entidade. Um registro por chamada ao FPSL, independente de sucesso ou erro.

### Campos por linha

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `timestamp` | string (ISO 8601 UTC) | Momento da requisição |
| `entidade` | string | `"cliente"` · `"simcard"` · `"rastreador"` · `"veiculo"` · `"onboarding"` |
| `metodo` | string | `"GET"` · `"POST"` · `"PUT"` · `"DELETE"` |
| `rota` | string | Rota FPSL, ex: `"/weso/veiculos"` |
| `acao` | string \| null | `"criado"` · `"ja_existe"` · `"encontrado"` · `"atualizado"` · `"excluido"` · `null` em erro |
| `id` | integer \| null | ID numérico retornado pela WESO (null se não retornado) |
| `ref` | string \| null | Referência principal da entidade (cnpjcpf, iccId, numeroSerie, placa) |
| `ok` | boolean | `true` se processou sem erro FPSL |
| `erro` | string \| null | Mensagem de erro quando `ok: false` |

### Exemplo de linhas no log

```json
{"timestamp":"2026-06-15T14:00:00.123456+00:00","entidade":"cliente","metodo":"GET","rota":"/weso/clientes","acao":"encontrado","id":13458,"ref":"11222333000181","ok":true,"erro":null}
{"timestamp":"2026-06-15T14:01:02.456789+00:00","entidade":"veiculo","metodo":"POST","rota":"/weso/veiculos","acao":"criado","id":86400,"ref":"FPS0A01","ok":true,"erro":null}
{"timestamp":"2026-06-15T14:02:30.789012+00:00","entidade":"veiculo","metodo":"DELETE","rota":"/weso/veiculos/placa/FPS0A01","acao":"excluido","id":86400,"ref":"FPS0A01","ok":true,"erro":null}
{"timestamp":"2026-06-15T14:03:10.000000+00:00","entidade":"simcard","metodo":"POST","rota":"/weso/simcards","acao":null,"id":null,"ref":"89550330300020000012","ok":false,"erro":"ICCID já cadastrado."}
```

---

## Implementação

### `fpsl_weso/logger.py` (novo arquivo)

```python
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
```

### Uso nos routers

Adicionar ao final de cada handler, antes do `return`:

```python
from ..logger import log_req

# cliente — GET
log_req("cliente", "GET", "/weso/clientes", acao, result.get("id"), body.cnpjcpf, True, None)

# veiculo — POST
log_req("veiculo", "POST", "/weso/veiculos", acao, result.get("id"), body.placa, True, None)

# em caso de erro capturado
log_req("veiculo", "POST", "/weso/veiculos", None, None, body.placa, False, str(e))
```

---

## Consulta na VPS

### Últimas 50 requisições

```bash
ssh vps "tail -50 /home/claude/fpsl_weso/logs/requests.log"
```

### Apenas erros

```bash
ssh vps "grep '\"ok\":false' /home/claude/fpsl_weso/logs/requests.log"
```

### Por entidade

```bash
ssh vps "grep '\"entidade\":\"veiculo\"' /home/claude/fpsl_weso/logs/requests.log"
```

### Hoje (UTC)

```bash
ssh vps "grep '$(date -u +%Y-%m-%d)' /home/claude/fpsl_weso/logs/requests.log"
```

### Formato legível (linha a linha)

```bash
ssh vps "tail -20 /home/claude/fpsl_weso/logs/requests.log | python3 -c \"import sys,json; [print(json.dumps(json.loads(l),indent=2,ensure_ascii=False)) for l in sys.stdin]\""
```

---

## Testes

### Caso 1 — GET cliente gera log
**Request:** `GET /weso/clientes?cnpjcpf=11222333000181`  
**Esperado:** linha no log com `entidade: "cliente"`, `metodo: "GET"`, `acao: "encontrado"`, `id: 13458`, `ok: true`

### Caso 2 — POST falho gera log de erro
**Request:** `POST /weso/simcards` com ICCID duplicado  
**Esperado:** linha com `ok: false`, `erro: "ICCID já cadastrado."`, `acao: null`

### Caso 3 — Logs persistem após restart
**Ação:** `systemctl --user restart fpsl-weso`  
**Esperado:** arquivo existe, registros anteriores preservados, novos registros acrescentados ao fim (append)
