# Aba 02 — Chip (SIM Card)

**Status:** ✅ Validado — 2026-06-12  
**Rota FPSL:** `POST /weso/simcards` · `PUT /weso/simcards/{iccid}`  
**API WESO:** `POST /SimCard/Cadastro` · `POST /SimCard/Atualizar`

---

## Spec

### Comportamento esperado

1. `POST /weso/simcards` — tenta cadastrar o chip.
   - 201 → criado com sucesso.
   - 409 → ICCID já existe; retorna `acao: "ja_existe"`.
2. `PUT /weso/simcards/{iccid}` — atualiza dados de um chip existente.

> `GET /SimCard/Consultar` está bloqueado pelo servidor (anti-JSON-hijacking).  
> Não há rota de consulta direta disponível na API WESO.  
> Deduplicação feita via detecção do 409 na tentativa de criação.

### Deduplicação

```
POST /SimCard/Cadastro
  → HTTP 201  →  acao: "criado"
  → HTTP 200 + Status: error + Code: 409  →  acao: "ja_existe"
```

### Campos de entrada

| Campo | Obrigatório | Tipo | Observação |
|-------|------------|------|------------|
| `iccId` | ✅ | string | Chave de deduplicação (ICCID do chip) |
| `numero` | ❌ | int | Número de telefone da linha |
| `operadora` | ❌ | string | `Vivo` / `Claro` / `TIM` |
| `apn` | ❌ | string | |
| `situacao` | ❌ | string | `Estoque` / `EmUso` / `Inativo` |
| `valorMensalidade` | ❌ | float | |
| `obs` | ❌ | string | |

### Resposta FPSL

```json
{
  "ok": true,
  "acao": "criado | ja_existe | atualizado",
  "id": 47489,
  "dados": { "iccId": "8955170220424545007" },
  "erro": null
}
```

### Casos de erro tratados

| Cenário | HTTP FPSL | `erro` |
|---------|-----------|--------|
| `iccId` ausente | 422 | Validação Pydantic |
| Resposta HTML da WESO | 502 | "WESO retornou erro não estruturado" |
| API WESO indisponível | 502 | "WESO indisponível" |

---

## Implementação

**Arquivo:** `fpsl_weso/routers/simcards.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..client import weso_post

router = APIRouter(prefix="/weso/simcards", tags=["simcards"])


class SimCardInput(BaseModel):
    iccId:            str
    numero:           int | None = None
    operadora:        str | None = None
    apn:              str | None = None
    situacao:         str | None = None
    valorMensalidade: float | None = None
    obs:              str | None = None


class SimCardUpdate(BaseModel):
    numero:           int | None = None
    operadora:        str | None = None
    apn:              str | None = None
    situacao:         str | None = None
    valorMensalidade: float | None = None


@router.post("")
async def cadastrar_simcard(body: SimCardInput):
    result = await weso_post("/SimCard/Cadastro", body.model_dump(exclude_none=True), allow_409=True)
    if result.get("_ja_existe"):
        return {"ok": True, "acao": "ja_existe", "id": None, "dados": {"iccId": body.iccId}, "erro": None}
    return {"ok": True, "acao": "criado", "id": result.get("id"), "dados": result, "erro": None}


@router.put("/{iccid}")
async def atualizar_simcard(iccid: str, body: SimCardUpdate):
    payload = {"iccId": iccid, **body.model_dump(exclude_none=True)}
    result = await weso_post("/SimCard/Atualizar", payload)
    return {"ok": True, "acao": "atualizado", "id": result.get("id"), "dados": result, "erro": None}
```

---

## Testes

### Caso 1 — Chip já existente → deduplicação
**Request:**
```json
POST /weso/simcards
{ "iccId": "8955170220424545007" }
```
**Esperado:** `acao: "ja_existe"`, HTTP 200

### Caso 2 — Chip novo
**Request:**
```json
POST /weso/simcards
{ "iccId": "8955170220424545099", "situacao": "Estoque" }
```
**Esperado:** `acao: "criado"`, `id` numérico, HTTP 200

> ICCID precisou ter o prefixo real `8955` — ICCID totalmente fictício (`0000000000000000001`) causou timeout na WESO.

### Caso 3 — Campo obrigatório ausente
**Request:** `POST /weso/simcards` `{}`  
**Esperado:** HTTP 422

---

## Resultado do Teste

| Caso | Esperado | Obtido | Status |
|------|----------|--------|--------|
| 1 — chip já existente | `acao: "ja_existe"`, HTTP 200 | `acao: "ja_existe"`, `id: null`, HTTP 200 | ✅ |
| 2 — chip novo | `acao: "criado"`, id numérico | `acao: "criado"`, id 56386, data ISO | ✅ |
| 3 — campo ausente | HTTP 422 | HTTP 422, `iccId` apontado como faltante | ✅ |

**Observações confirmadas em teste real:**
- ICCID totalmente fictício (`0000...001`) causa timeout na WESO — usar prefixo de operadora real (ex: `8955`).
- `id` retorna `null` quando `acao: "ja_existe"` — a WESO não disponibiliza `GET /SimCard/Consultar` (bloqueado por anti-JSON-hijacking), impossibilitando a resolução do ID. Comportamento esperado e documentado.

---

## Histórico de Tentativas

| # | Data | Resultado | Observação |
|---|------|-----------|------------|
| 1 | 2026-06-12 | ✅ Êxito | 3/3 casos passaram. ICCID de teste ajustado para prefixo real. |
