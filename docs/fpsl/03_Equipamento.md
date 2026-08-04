# Aba 03 — Equipamento (Rastreador)

**Status:** ✅ Validado — 2026-06-12  
**Rota FPSL:** `POST /weso/rastreadores` · `PUT /weso/rastreadores/{id}/chip`  
**API WESO:** `POST /Rastreadores/Cadastro` · `POST /Rastreadores/Atualizar` · `GET /Rastreadores/Consultar`

---

## Spec

### Comportamento esperado

1. `POST /weso/rastreadores` — tenta cadastrar o rastreador.
   - 201 → criado; em seguida vincula chip via `Rastreadores/Atualizar`.
   - 409 → já existe; garante vínculo do chip via `Rastreadores/Atualizar`.
2. `PUT /weso/rastreadores/{id}/chip` — vincula chip a rastreador existente.
3. `GET /weso/rastreadores/{id}` — consulta rastreador por ID (com filtro funciona).

### Deduplicação

```
POST /Rastreadores/Cadastro  (com modelo obrigatório)
  → 201  →  criado
       └──► POST /Rastreadores/Atualizar  { id, simCard: {iccId} }  (vincular chip se iccId informado)
  → 409  →  ja_existe
       └──► POST /Rastreadores/Atualizar  { numeroSerie, simCard: {iccId} }  (retorna id + vincula chip)
            Se sem iccId: GET /Rastreadores/Consultar?numeroSerie=...  (somente para obter o id)
```

> `GET /Rastreadores/Consultar` sem filtro dá timeout.  
> Funciona corretamente com `?id=` e também com `?numeroSerie=` (confirmado em teste).

### Campos de entrada

| Campo | Obrigatório | Tipo | Observação |
|-------|------------|------|------------|
| `numeroSerie` | ✅ | string | Chave de deduplicação |
| `modelo` | ✅ | string | Descrição do modelo (ex: `"CRX3"`) — obrigatório confirmado em teste |
| `iccId` | ❌ | string | Linka chip ao rastreador via `Rastreadores/Atualizar` |
| `tipo` | ❌ | string | Ex: `"Veiculo"` |
| `situacao` | ❌ | string | Ex: `"Estoque"` / `"Instalado"` |
| `lote` | ❌ | string | |
| `notaFiscal` | ❌ | string | |
| `valorPago` | ❌ | float | |

> `fornecedor` removido do FPSL — campo opcional na WESO sem endpoint de consulta prévia; gestão de fornecedor pertence ao Harmonit.

### Resposta FPSL

```json
{
  "ok": true,
  "acao": "criado | ja_existe",
  "id": 14008,
  "dados": {
    "numeroSerie": "007559809",
    "modelo": "Suntech ST310",
    "simcard": { "iccId": "8955170220424545007" }
  },
  "erro": null
}
```

### Casos de erro tratados

| Cenário | HTTP FPSL | `erro` |
|---------|-----------|--------|
| `numeroSerie` ausente | 422 | Validação Pydantic |
| `modelo` ausente | 422 | Validação Pydantic |
| Falha ao vincular chip | 502 | mensagem WESO |
| API WESO indisponível | 502 | "WESO indisponível" |

---

## Implementação

**Arquivo:** `fpsl_weso/routers/rastreadores.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..client import weso_get, weso_post

router = APIRouter(prefix="/weso/rastreadores", tags=["rastreadores"])


class RastreadorInput(BaseModel):
    numeroSerie: str
    modelo:      str
    iccId:       str | None = None
    tipo:        str | None = None
    situacao:    str | None = None
    lote:        str | None = None
    notaFiscal:  str | None = None
    valorPago:   float | None = None


@router.get("/{rastreador_id}")
async def consultar_rastreador(rastreador_id: int):
    data = await weso_get("/Rastreadores/Consultar", params={"id": rastreador_id})
    items = data.get("rastreadores", [])
    if not items:
        raise HTTPException(status_code=404, detail="Rastreador não encontrado")
    return {"ok": True, "acao": "encontrado", "id": items[0].get("id"), "dados": items[0], "erro": None}


@router.post("")
async def cadastrar_rastreador(body: RastreadorInput):
    payload = {
        "numeroSerie": body.numeroSerie,
        "modelo": {"descricao": body.modelo},
        **({} if not body.tipo else {"tipo": {"descricao": body.tipo}}),
        **({} if not body.situacao else {"situacao": {"descricao": body.situacao}}),
        **({k: v for k, v in {"lote": body.lote, "notaFiscal": body.notaFiscal,
                               "valorPago": body.valorPago}.items() if v is not None}),
    }
    result = await weso_post("/Rastreadores/Cadastro", payload, allow_409=True)

    if result.get("_ja_existe"):
        if body.iccId:
            # Atualizar aceita numeroSerie como identificador e retorna o id
            upd = await weso_post("/Rastreadores/Atualizar",
                                  {"numeroSerie": body.numeroSerie, "simCard": {"iccId": body.iccId}})
            rastreador_id = upd.get("id")
        else:
            consulta = await weso_get("/Rastreadores/Consultar", params={"numeroSerie": body.numeroSerie})
            items = consulta.get("rastreadores", [])
            rastreador_id = items[0].get("id") if items else None
        return {"ok": True, "acao": "ja_existe", "id": rastreador_id, "dados": result, "erro": None}

    rastreador_id = result.get("id")
    if body.iccId and rastreador_id:
        await weso_post("/Rastreadores/Atualizar", {"id": rastreador_id, "simCard": {"iccId": body.iccId}})

    return {"ok": True, "acao": "criado", "id": rastreador_id, "dados": result, "erro": None}


@router.put("/{rastreador_id}/chip")
async def vincular_chip(rastreador_id: int, iccId: str):
    result = await weso_post("/Rastreadores/Atualizar", {"id": rastreador_id, "simCard": {"iccId": iccId}})
    return {"ok": True, "acao": "atualizado", "id": rastreador_id, "dados": result, "erro": None}
```

---

## Testes

### Caso 1 — Serial existente → deduplicação + chip vinculado
**Request:**
```json
POST /weso/rastreadores
{ "numeroSerie": "007559809", "modelo": "Suntech ST310", "iccId": "8955170220424545007" }
```
**Esperado:** `acao: "ja_existe"`, chip vinculado confirmado

### Caso 2 — Serial novo
**Request:**
```json
POST /weso/rastreadores
{ "numeroSerie": "997559809", "modelo": "Teste" }
```
**Esperado:** `acao: "criado"`, `id` numérico

### Caso 3 — Sem modelo
**Request:**
```json
POST /weso/rastreadores
{ "numeroSerie": "997559809" }
```
**Esperado:** HTTP 422 (Pydantic, antes de chamar a API)

---

## Resultado do Teste

| Caso | Esperado | Obtido | Status |
|------|----------|--------|--------|
| 1 — serial existente + chip | `acao: "ja_existe"`, chip vinculado, id real | `acao: "ja_existe"`, id 14008 (via Atualizar) | ✅ |
| 2 — serial novo | `acao: "criado"`, id numérico | `acao: "criado"`, id 49129 | ✅ |
| 3 — sem modelo | HTTP 422 | HTTP 422, `modelo` apontado como faltante | ✅ |

**Observações confirmadas em teste real:**
- Quando `ja_existe` com `iccId`: `POST /Rastreadores/Atualizar` com `{ "numeroSerie": ..., "simCard": {iccId} }` retorna `id` e vincula o chip em uma única chamada.
- Quando `ja_existe` sem `iccId`: `GET /Rastreadores/Consultar?numeroSerie=...` funciona para obter o `id`.
- `GET /Rastreadores/Consultar?numeroSerie=...` confirmado funcional (doc original dizia apenas `?id=`).

---

## Histórico de Tentativas

| # | Data | Resultado | Observação |
|---|------|-----------|------------|
| 1 | 2026-06-12 | ⚠️ Parcial | Caso 1 retornou `id: null` — lógica de `ja_existe` não obtinha o ID |
| 2 | 2026-06-12 | ✅ Êxito | Corrigido: Atualizar com `numeroSerie` retorna `id`; 3/3 casos passaram |
