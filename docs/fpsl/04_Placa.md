# Aba 04 — Placa (Veículo)

**Status:** ✅ Validado — 2026-06-15  
**Rota FPSL:** `POST /weso/veiculos` · `PUT /weso/veiculos/{id}` · `DELETE /weso/veiculos/{id}`  
**API WESO:** `POST /Veiculos/Cadastro` · `POST /Veiculos/Atualizar` · `POST /Veiculos/Excluir`

---

## Spec

### Comportamento esperado

1. `POST /weso/veiculos` — cria veículo e vincula cliente + rastreador em uma chamada.
   - Consulta o rastreador por `serial_rastreador` via `GET /Rastreadores/Consultar`.
   - Se não encontrado → 404.
   - Envia `POST /Veiculos/Cadastro` com `rastreador.id`.
   - 201 → criado.
   - 409 (placa duplicada) → retorna `acao: "ja_existe"`.
2. `PUT /weso/veiculos/{id}` — atualiza dados do veículo.
3. `DELETE /weso/veiculos/{id}` — exclui veículo por ID.

> `GET /Veiculos/Consultar` retorna HTTP 500 com qualquer parâmetro — endpoint quebrado.  
> `POST /Veiculos/Atualizar` com apenas `placa` dá timeout — não confiável para lookup.  
> Não há rota funcional para obter `id` de veículo existente. Quando `ja_existe`, `id` retorna `null`. Comportamento documentado e esperado.  
> Deduplicação via 409 (HTML). Exclusão sempre por `veiculo_id`.

### Deduplicação

```
GET /Rastreadores/Consultar?numeroSerie=...
  → não encontrado  →  404

POST /Veiculos/Cadastro
  → 201  →  acao: "criado"
  → 409  →  acao: "ja_existe"  (placa duplicada)
```

### Campos de entrada

| Campo | Obrigatório | Tipo | Observação |
|-------|------------|------|------------|
| `placa` | ✅ | string | Chave de deduplicação |
| `cnpjcpf_cliente` | ✅ | string | Vínculo ao cliente (obrigatório no fluxo) |
| `serial_rastreador` | ✅ | string | Vínculo ao rastreador — resolvido para `id` via `GET /Rastreadores/Consultar?numeroSerie=` antes do cadastro |
| `tipoEqp` | ❌ | int | Tipo do veículo (ver tabela em `01_Veiculos.md`) |
| `descricao` | ❌ | string | |
| `cor` | ❌ | string | |
| `chassi` | ❌ | string | |
| `renavam` | ❌ | string | |
| `anoFab` | ❌ | int | |
| `anoMod` | ❌ | int | |
| `valorMensalidade` | ❌ | float | |
| `observacoes` | ❌ | string | Visível ao cliente |
| `observacoesGestor` | ❌ | string | Interno |

### Resposta FPSL

```json
{
  "ok": true,
  "acao": "criado | ja_existe | atualizado | excluido",
  "id": 86400,
  "dados": { ... },
  "erro": null
}
```

> **Atenção:** quando `acao: "ja_existe"`, `id` é sempre `null`. A WESO não oferece endpoint funcional para recuperar o ID de um veículo existente por placa. Limitação conhecida da API.

### Casos de erro tratados

| Cenário | HTTP FPSL | `erro` |
|---------|-----------|--------|
| `placa` ausente | 422 | Validação Pydantic |
| `cnpjcpf_cliente` ausente | 422 | Validação Pydantic |
| `serial_rastreador` ausente | 422 | Validação Pydantic |
| Rastreador não encontrado na WESO | 404 | "Rastreador '...' não encontrado" |
| Resposta HTML da WESO | 502 | "WESO retornou erro não estruturado" |
| API WESO indisponível | 502 | "WESO indisponível" |

---

## Implementação

**Arquivo:** `fpsl_weso/routers/veiculos.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..client import weso_get, weso_post

router = APIRouter(prefix="/weso/veiculos", tags=["veiculos"])


class VeiculoInput(BaseModel):
    placa:             str
    cnpjcpf_cliente:   str
    serial_rastreador: str
    tipoEqp:           int | None = None
    descricao:         str | None = None
    cor:               str | None = None
    chassi:            str | None = None
    renavam:           str | None = None
    anoFab:            int | None = None
    anoMod:            int | None = None
    valorMensalidade:  float | None = None
    observacoes:       str | None = None
    observacoesGestor: str | None = None


class VeiculoUpdate(BaseModel):
    descricao:        str | None = None
    cor:              str | None = None
    valorMensalidade: float | None = None  # enviado à WESO como valor_mensalidade
    observacoes:      str | None = None


@router.post("")
async def cadastrar_veiculo(body: VeiculoInput):
    # WESO Veiculos/Cadastro ignora numeroSerie ao referenciar rastreador existente — exige id
    consulta = await weso_get("/Rastreadores/Consultar", params={"numeroSerie": body.serial_rastreador})
    items = consulta.get("rastreadores", [])
    if not items:
        raise HTTPException(status_code=404, detail=f"Rastreador '{body.serial_rastreador}' não encontrado")
    rastreador_id = items[0]["id"]

    complemento = {k: v for k, v in {
        "tipoEqp": body.tipoEqp, "cor": body.cor,
        "chassi": body.chassi, "renavam": body.renavam,
        "anoFab": body.anoFab, "anoMod": body.anoMod,
    }.items() if v is not None}

    payload = {
        "equipamento": {
            "placa": body.placa,
            "cliente": {"cnpjcpf": body.cnpjcpf_cliente},
            "rastreador": {"id": rastreador_id},
            **({} if not body.descricao else {"descricao": body.descricao}),
            **({} if not body.observacoes else {"observacoes": body.observacoes}),
            **({} if not body.observacoesGestor else {"observacoesGestor": body.observacoesGestor}),
            **({} if not body.valorMensalidade else {"valorMensalidade": body.valorMensalidade}),
            **({} if not complemento else {"complemento": complemento}),
        }
    }
    result = await weso_post("/Veiculos/Cadastro", payload, allow_409=True)
    acao = "ja_existe" if result.get("_ja_existe") else "criado"
    return {"ok": True, "acao": acao, "id": result.get("id"), "dados": result, "erro": None}


@router.put("/{veiculo_id}")
async def atualizar_veiculo(veiculo_id: int, body: VeiculoUpdate):
    payload = {"veiculo_id": veiculo_id}
    if body.descricao is not None:        payload["descricao"] = body.descricao
    if body.cor is not None:              payload["cor"] = body.cor
    if body.observacoes is not None:      payload["observacoes"] = body.observacoes
    if body.valorMensalidade is not None: payload["valor_mensalidade"] = body.valorMensalidade
    result = await weso_post("/Veiculos/Atualizar", payload)
    return {"ok": True, "acao": "atualizado", "id": veiculo_id, "dados": result, "erro": None}


@router.delete("/{veiculo_id}")
async def excluir_veiculo(veiculo_id: int):
    result = await weso_post("/Veiculos/Excluir", {"veiculo_id": veiculo_id})
    return {"ok": True, "acao": "excluido", "id": veiculo_id, "dados": result, "erro": None}
```

---

## Testes

### Caso 1 — Placa nova → criação completa
**Request:**
```json
POST /weso/veiculos
{ "placa": "FPS0A01", "cnpjcpf_cliente": "11222333000181", "serial_rastreador": "FPSLTEST001" }
```
**Esperado:** `acao: "criado"`, `id` numérico, HTTP 200

### Caso 2 — Placa existente → deduplicação
**Request:** mesmo payload do Caso 1  
**Esperado:** `acao: "ja_existe"`, `id: null`, HTTP 200

### Caso 3 — Excluir por ID
**Request:** `DELETE /weso/veiculos/{id}`  
**Esperado:** `acao: "excluido"`, HTTP 200

### Caso 4 — Campo obrigatório ausente
**Request:** `POST /weso/veiculos` `{ "placa": "TST0T01" }`  
**Esperado:** HTTP 422

---

## Resultado do Teste

| Caso | Esperado | Obtido | Status |
|------|----------|--------|--------|
| 1 — placa nova | `acao: "criado"`, id numérico | `acao: "criado"`, id 86400, dados completos | ✅ |
| 2 — placa existente | `acao: "ja_existe"` | `acao: "ja_existe"`, `id: null` (limitação WESO) | ✅ |
| 3 — excluir por ID | `acao: "excluido"` | `acao: "excluido"`, id 86400, `data_exclusao` ISO | ✅ |
| 4 — campos obrigatórios ausentes | HTTP 422 | HTTP 422, `cnpjcpf_cliente` e `serial_rastreador` apontados | ✅ |

**Observações confirmadas em teste real:**
- `POST /Veiculos/Cadastro` com `rastreador: {numeroSerie}` retorna HTTP 500 HTML — a WESO exige `rastreador: {id}`. Solução: busca prévia via `GET /Rastreadores/Consultar?numeroSerie=`.
- `id: null` para `ja_existe` é limitação real: `GET /Veiculos/Consultar` retorna HTTP 500 e `POST /Veiculos/Atualizar` com apenas `placa` dá timeout.
- Resposta inclui campo `objetos_processados` com strings em encoding inconsistente (bug no servidor WESO — não afeta funcionalidade).
- Exclusão por `veiculo_id` confirmada funcional. Não testar exclusão por `placa` (comportamento instável documentado).
- `PUT /Veiculos/Atualizar` espera `valor_mensalidade` em snake_case no nível raiz do payload.

---

## Limpeza de Dados de Teste

**Contexto:** rastreador `007559809` (id: 14008, modelo: Suntech ST310) foi usado em múltiplos cadastros de veículo durante os testes, gerando duplicatas na WESO.

**Investigação realizada em 2026-06-12:**

| Placa | Resultado ao tentar criar | Diagnóstico |
|-------|--------------------------|-------------|
| `FPS0A02` | 409 Conflict | Placa existe na WESO |
| `FPS0A03` | 409 Conflict | Placa existe na WESO |
| `TST0T01` | 409 Conflict | Placa existe na WESO |
| `FPS0A01`, `TST0A01`, `FPSL001`, `FPSL002` | HTTP 500 | Não existem |

**Estado atual do rastreador:** `situacao: "Estoque"` — indica que **no momento da consulta não estava vinculado a nenhum veículo**. Se os vínculos existissem, a WESO teria atualizado automaticamente para `"Instalado"`.

**Hipótese:** as placas `FPS0A02`, `FPS0A03` e `TST0T01` existem na WESO mas possivelmente com `rastreador.id` diferente de 14008, ou os vínculos já foram removidos em algum momento.

**Pendência:** `GET /Veiculos/Consultar` está quebrado (HTTP 500) — impossível confirmar via API qual rastreador está vinculado a cada placa, nem obter os IDs dos veículos para exclusão.  
Para concluir a limpeza: verificar IDs das placas via painel WeFleet e executar `DELETE /weso/veiculos/{id}` para cada duplicata confirmada.

---

## Histórico de Tentativas

| # | Data | Resultado | Observação |
|---|------|-----------|------------|
| 1 | 2026-06-12 | ⚠️ Falha | `Veiculos/Cadastro` retornava HTTP 500 ao usar `rastreador: {numeroSerie}` |
| 2 | 2026-06-12 | ✅ Êxito | Corrigido para buscar `id` do rastreador antes do cadastro; 4/4 casos passaram |
| 3 | 2026-06-15 | ✅ Fechado | Guard de `situacao` removido do escopo (validação além de campo obrigatório). Spec alinhada ao código. |
