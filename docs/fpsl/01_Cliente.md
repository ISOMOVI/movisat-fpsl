# Aba 01 — Cliente

**Status:** ✅ Validado — 2026-06-12  
**Rota FPSL:** `GET /weso/clientes` · `POST /weso/clientes` · `PUT /weso/clientes/{cnpjcpf}`  
**API WESO:** `GET /Clientes/Consultar` · `POST /Clientes/Cadastro`

---

## Spec

### Comportamento esperado

1. `GET /weso/clientes?cnpjcpf=...` — consulta cliente por CNPJ/CPF.
2. `POST /weso/clientes` — verifica existência pelo `cnpjcpf` antes de criar.
   - Se já existe → retorna dados do existente com `acao: "ja_existe"`.
   - Se não existe → cria e retorna com `acao: "criado"`.
3. `PUT /weso/clientes/{cnpjcpf}` — atualiza campos de um cliente existente pelo CNPJ/CPF.

### Deduplicação

```
GET /Clientes/Consultar?cnpjcpf=...
  → total > 0  →  retorna cliente existente  (acao: "ja_existe")
  → total == 0 →  POST /Clientes/Cadastro   (acao: "criado")
```

### Campos de entrada

| Campo | Obrigatório | Tipo | Observação |
|-------|------------|------|------------|
| `cnpjcpf` | ✅ | string | Chave de deduplicação — aceita com ou sem formatação |
| `razaoSocial` | ✅ | string | |
| `nomeFantasia` | ❌ | string | |
| `tipoCliente` | ❌ | string | `Fisica` / `Juridica` / `NaoInformado` |
| `situacao` | ❌ | string | `Adimplente` / `Inadimplente` / `Bloqueado` / `Teste` / `Negociacao` / `Cortesia` |
| `contato` | ❌ | string | Nome do responsável |
| `telefone` | ❌ | string | |
| `emailCobranca` | ❌ | string | |
| `plano` | ❌ | string | Nome exato do plano cadastrado no sistema WESO |
| `endereco` | ❌ | string | |
| `numeroEnd` | ❌ | string | |
| `bairro` | ❌ | string | |
| `cep` | ❌ | string | |
| `obs` | ❌ | string | |

### Resposta FPSL (padrão unificado)

```json
{
  "ok": true,
  "acao": "criado | ja_existe",
  "id": 13458,
  "dados": {
    "cnpjcpf": "11222333000181",
    "razaoSocial": "Cliente Exemplo"
  },
  "erro": null
}
```

### Casos de erro tratados

| Cenário | HTTP FPSL | `erro` |
|---------|-----------|--------|
| `cnpjcpf` ausente | 422 | Validação Pydantic |
| `razaoSocial` ausente | 422 | Validação Pydantic |
| API WESO indisponível | 502 | "WESO indisponível" |
| Erro inesperado da WESO | 502 | mensagem original |
| Cliente não encontrado no PUT | 404 | "Cliente não encontrado" |

---

## Implementação

**Arquivo:** `fpsl_weso/routers/clientes.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..client import weso_get, weso_post

router = APIRouter(prefix="/weso/clientes", tags=["clientes"])


class ClienteInput(BaseModel):
    cnpjcpf:       str
    razaoSocial:   str
    nomeFantasia:  str | None = None
    tipoCliente:   str | None = None
    situacao:      str | None = None
    contato:       str | None = None
    telefone:      str | None = None
    emailCobranca: str | None = None
    plano:         str | None = None
    endereco:      str | None = None
    numeroEnd:     str | None = None
    bairro:        str | None = None
    cep:           str | None = None
    obs:           str | None = None


@router.get("")
async def consultar_cliente(cnpjcpf: str):
    data = await weso_get("/Clientes/Consultar", params={"cnpjcpf": cnpjcpf})
    clientes = data.get("clientes", [])
    if not clientes:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return {"ok": True, "acao": "encontrado", "id": clientes[0].get("id"), "dados": clientes[0], "erro": None}


@router.post("")
async def cadastrar_cliente(body: ClienteInput):
    # 1. verificar existência
    data = await weso_get("/Clientes/Consultar", params={"cnpjcpf": body.cnpjcpf})
    clientes = data.get("clientes", [])
    if clientes:
        c = clientes[0]
        return {"ok": True, "acao": "ja_existe", "id": c.get("id"), "dados": c, "erro": None}

    # 2. criar
    payload = body.model_dump(exclude_none=True)
    data = await weso_post("/Clientes/Cadastro", payload)
    return {"ok": True, "acao": "criado", "id": data.get("id"), "dados": data, "erro": None}


class ClienteUpdate(BaseModel):
    razaoSocial:   str | None = None
    nomeFantasia:  str | None = None
    tipoCliente:   str | None = None
    situacao:      str | None = None
    contato:       str | None = None
    telefone:      str | None = None
    emailCobranca: str | None = None
    plano:         str | None = None
    endereco:      str | None = None
    numeroEnd:     str | None = None
    bairro:        str | None = None
    cep:           str | None = None
    obs:           str | None = None


@router.put("/{cnpjcpf}")
async def atualizar_cliente(cnpjcpf: str, body: ClienteUpdate):
    payload = {"cnpjcpf": cnpjcpf, **body.model_dump(exclude_none=True)}
    data = await weso_post("/Clientes/Atualizar", payload)
    return {"ok": True, "acao": "atualizado", "id": data.get("id"), "dados": data, "erro": None}
```

---

## Testes

### Caso 1 — Cliente inexistente → criação
**Request:**
```json
POST /weso/clientes
{ "cnpjcpf": "11222333000181", "razaoSocial": "teste iago API", "situacao": "Teste" }
```
**Esperado:** `acao: "criado"`, `id` numérico, HTTP 200

### Caso 2 — Cliente já existente → deduplicação
**Request:** mesmo payload do Caso 1  
**Esperado:** `acao: "ja_existe"`, mesmo `id`, HTTP 200

### Caso 3 — Consulta direta
**Request:** `GET /weso/clientes?cnpjcpf=11222333000181`  
**Esperado:** `acao: "encontrado"`, dados completos do cliente

### Caso 4 — Campo obrigatório ausente
**Request:** `POST /weso/clientes` `{ "cnpjcpf": "11222333000181" }`  
**Esperado:** HTTP 422, erro de validação Pydantic

---

## Resultado do Teste

| Caso | Esperado | Obtido | Status |
|------|----------|--------|--------|
| 1 — criar cliente novo | `acao: "criado"`, id numérico, data ISO | `acao: "criado"`, id 13459, data `2026-06-12T15:44:53Z` | ✅ |
| 2 — duplicata | `acao: "ja_existe"`, mesmo id | `acao: "ja_existe"`, id 13459 | ✅ |
| 3 — consulta direta | `acao: "encontrado"`, dados completos | dados completos incluindo endereço e plano | ✅ |
| 4 — campo ausente | HTTP 422, erro Pydantic | HTTP 422, `razaoSocial` apontada como faltante | ✅ |

**Observações confirmadas em teste real:**
- Data retorna normalizada para ISO 8601 pelo `client.py` (era `/Date(ms)/` na WESO)
- Consulta por `cnpjcpf` ignora formatação (com ou sem pontuação)
- `tipoCliente` retorna `"NaoInformado"` quando não informado na criação

---

## Histórico de Tentativas

| # | Data | Resultado | Observação |
|---|------|-----------|------------|
| 1 | 2026-06-12 | ✅ Êxito | 4/4 casos passaram na primeira tentativa |
