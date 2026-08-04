# Aba 07 — Registro Local de Veículos

**Status:** ✅ Validado — 2026-06-15  
**Rota FPSL:** `GET /weso/veiculos/local` · `DELETE /weso/veiculos/placa/{placa}`  
**Storage:** SQLite local — `/home/claude/fpsl_weso/data/fpsl.db`

---

## Problema

`GET /Veiculos/Consultar` está quebrado na WESO (HTTP 500).  
`POST /Veiculos/Excluir` por placa retorna HTTP 400 vazio.  
O painel WeFleet não exibe o `veiculo_id` numérico.

**Consequência:** sem o `veiculo_id` capturado no momento da criação, é impossível excluir um veículo via API.

---

## Spec

### Comportamento esperado

1. `POST /weso/veiculos` com `acao: "criado"` → salva `{placa, veiculo_id, criado_em}` no SQLite local.
2. `GET /weso/veiculos/local` → lista todos os veículos registrados localmente.
3. `DELETE /weso/veiculos/placa/{placa}` → fluxo de exclusão segura com validação interna.

### Fluxo de exclusão com validação

```
DELETE /weso/veiculos/placa/{placa}
  1. Busca {placa, veiculo_id} no storage local pela placa recebida
     → não encontrado → 404 "Placa não registrada localmente"

  2. VALIDAÇÃO INTERNA: placa do request == placa registrada no storage?
     → divergência → 409 "Placa não corresponde ao registro"
     (proteção contra corrupção do storage)

  3. POST /Veiculos/Excluir { veiculo_id } → WESO
     → erro da WESO → 502, registro local mantido intacto
     → sucesso → remove do storage local

  4. Retorna acao: "excluido", id, dados da WESO
```

> A validação do passo 2 protege o fluxo de integração: quando um sistema externo (ex: Harmonit) envia DELETE por placa, o FPSL confirma internamente que a placa recebida corresponde exatamente ao `veiculo_id` armazenado antes de executar qualquer operação na WESO.

### Storage — tabela `veiculos`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `placa` | TEXT PRIMARY KEY | Placa do veículo |
| `veiculo_id` | INTEGER | ID numérico retornado pela WESO no cadastro |
| `criado_em` | TEXT | ISO 8601 UTC |

### Resposta `GET /weso/veiculos/local`

```json
{
  "ok": true,
  "total": 2,
  "veiculos": [
    { "placa": "FPS0A01", "veiculo_id": 86400, "criado_em": "2026-06-15T12:00:00+00:00" },
    { "placa": "FPS0A02", "veiculo_id": 86401, "criado_em": "2026-06-15T12:05:00+00:00" }
  ]
}
```

### Resposta `DELETE /weso/veiculos/placa/{placa}`

```json
{ "ok": true, "acao": "excluido", "id": 86400, "dados": { ... }, "erro": null }
```

### Casos de erro tratados

| Cenário | HTTP FPSL | `erro` |
|---------|-----------|--------|
| Placa não registrada localmente | 404 | "Placa '{placa}' não registrada localmente" |
| Divergência interna placa ↔ ID | 409 | "Placa não corresponde ao registro" |
| WESO retorna erro no Excluir | 502 | mensagem WESO |
| API WESO indisponível | 502 | "WESO indisponível (timeout)" |

---

## Implementação

### `fpsl_weso/storage.py` (novo arquivo)

```python
import sqlite3
import asyncio
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "fpsl.db"


def _connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS veiculos (
                placa      TEXT PRIMARY KEY,
                veiculo_id INTEGER NOT NULL,
                criado_em  TEXT NOT NULL
            )
        """)


async def salvar_veiculo(placa: str, veiculo_id: int):
    def _run():
        criado_em = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO veiculos (placa, veiculo_id, criado_em) VALUES (?, ?, ?)",
                (placa, veiculo_id, criado_em),
            )
    await asyncio.get_event_loop().run_in_executor(None, _run)


async def buscar_veiculo(placa: str) -> dict | None:
    def _run():
        with _connect() as conn:
            row = conn.execute(
                "SELECT placa, veiculo_id, criado_em FROM veiculos WHERE placa = ?", (placa,)
            ).fetchone()
        return {"placa": row[0], "veiculo_id": row[1], "criado_em": row[2]} if row else None
    return await asyncio.get_event_loop().run_in_executor(None, _run)


async def remover_veiculo(placa: str):
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: _connect().__enter__().execute("DELETE FROM veiculos WHERE placa = ?", (placa,))
    )


async def listar_veiculos() -> list[dict]:
    def _run():
        with _connect() as conn:
            rows = conn.execute(
                "SELECT placa, veiculo_id, criado_em FROM veiculos ORDER BY criado_em"
            ).fetchall()
        return [{"placa": r[0], "veiculo_id": r[1], "criado_em": r[2]} for r in rows]
    return await asyncio.get_event_loop().run_in_executor(None, _run)
```

### `fpsl_weso/routers/veiculos.py` — alterações

**Adicionar import:**
```python
from .. import storage
```

**No `cadastrar_veiculo`, após `acao: "criado"`:**
```python
    if acao == "criado" and result.get("id"):
        await storage.salvar_veiculo(body.placa, result["id"])
```

**Novas rotas:**
```python
@router.get("/local")
async def listar_veiculos_local():
    veiculos = await storage.listar_veiculos()
    return {"ok": True, "total": len(veiculos), "veiculos": veiculos}


@router.delete("/placa/{placa}")
async def excluir_veiculo_por_placa(placa: str):
    registro = await storage.buscar_veiculo(placa)
    if not registro:
        raise HTTPException(status_code=404, detail=f"Placa '{placa}' não registrada localmente")
    if registro["placa"] != placa:
        raise HTTPException(status_code=409, detail="Placa não corresponde ao registro")
    result = await weso_post("/Veiculos/Excluir", {"veiculo_id": registro["veiculo_id"]})
    await storage.remover_veiculo(placa)
    return {"ok": True, "acao": "excluido", "id": registro["veiculo_id"], "dados": result, "erro": None}
```

### `main.py` — inicializar storage no lifespan

```python
from fpsl_weso import storage

@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    await start_client()
    yield
    await stop_client()
```

---

## Testes

### Caso 1 — Criar veículo e verificar registro local
**Request:** `POST /weso/veiculos` com placa nova  
**Esperado:** `acao: "criado"`, id numérico, registro salvo no SQLite

### Caso 2 — Listar registros locais
**Request:** `GET /weso/veiculos/local`  
**Esperado:** lista com a placa criada no Caso 1, ordenada por `criado_em`

### Caso 3 — Excluir por placa
**Request:** `DELETE /weso/veiculos/placa/{placa}` (placa do Caso 1)  
**Esperado:** `acao: "excluido"`, registro removido do SQLite

### Caso 4 — Placa não registrada localmente
**Request:** `DELETE /weso/veiculos/placa/INEXISTENTE`  
**Esperado:** HTTP 404, "Placa não registrada localmente"

### Caso 5 — Campo obrigatório ausente
**Request:** `POST /weso/veiculos` sem `placa`  
**Esperado:** HTTP 422 — nada salvo no storage

---

## Equivalente para RASTREADORES (documentado em 2026-07-27)

A auditoria de documentação de 27/07 achou 2 rotas que existiam no código desde
sempre e **não estavam em doc nenhum**. Mesmo conceito deste arquivo, só que sobre
a tabela `rastreadores_serials` (mapa `serial ↔ weso_id`) em vez de `veiculos`.

| Rota | Faz o quê |
|---|---|
| `GET /weso/rastreadores/local` | Lista o mapa serial↔weso_id inteiro: `{ok, total, rastreadores[]}` |
| `POST /weso/rastreadores/local` | Registra manualmente um par `{serial, weso_id}` — a saída de emergência quando o vínculo se perdeu (ex.: timeout que engoliu o id, W6) |

**Auth:** as duas exigem `X-FPSL-Key`, como todo o resto de `/weso/*` — a dependency
está no nível do `APIRouter` (`dependencies=[Depends(verificar_chave)]`), não em
cada função. **Conferido em 2026-07-27**, para não parecer que estão abertas ao ler
só o corpo da função.

O `POST /local` grava via `salvar_rastreador_serial()` e loga `registrado_manual`.
É o par do lookup bidirecional do W7 (ver `10_Inconsistencias.md`).
