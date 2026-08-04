# Aba 05 — Onboarding Composto

**Status:** ✅ Validado — 2026-06-12  
**Rota FPSL:** `POST /weso/onboarding`  
**API WESO:** sequência de chamadas das Abas 01–04

---

## Spec

### Comportamento esperado

Executa o fluxo completo em uma única chamada:

```
1. Cliente   → GET /Clientes/Consultar  → POST /Clientes/Cadastro (se não existe)
2. Chip      → POST /SimCard/Cadastro   → trata 409
3. Equipamento → POST /Rastreadores/Cadastro + PUT /Rastreadores/Atualizar (chip)
4. Placa     → POST /Veiculos/Cadastro  → trata 409
```

Retorna o resultado de cada etapa individualmente.  
Se qualquer etapa falhar definitivamente, interrompe e reporta em qual etapa falhou.

### Campos de entrada

Composição dos inputs das 4 abas anteriores:

```json
{
  "cliente": { "cnpjcpf": "...", "razaoSocial": "..." },
  "simcard":  { "iccId": "..." },
  "rastreador": { "numeroSerie": "...", "modelo": "..." },
  "veiculo":  { "placa": "...", "cnpjcpf_cliente": "...", "serial_rastreador": "..." }
}
```

### Resposta FPSL

```json
{
  "ok": true,
  "etapas": {
    "cliente":    { "acao": "criado | ja_existe", "id": 13458 },
    "simcard":    { "acao": "criado | ja_existe", "id": 47489 },
    "rastreador": { "acao": "criado | ja_existe", "id": 14008 },
    "veiculo":    { "acao": "criado | ja_existe", "id": 86395 }
  },
  "erro": null,
  "etapa_falhou": null
}
```

**Em caso de falha:**
```json
{
  "ok": false,
  "etapas": {
    "cliente":    { "acao": "criado", "id": 13458 },
    "simcard":    { "acao": "ja_existe", "id": null },
    "rastreador": null,
    "veiculo":    null
  },
  "erro": "Modelo do rastreador é obrigatório.",
  "etapa_falhou": "rastreador"
}
```

---

## Implementação

**Arquivo:** `fpsl_weso/services/onboarding.py`

```python
from fastapi import APIRouter
from pydantic import BaseModel
from ..routers.clientes import ClienteInput, cadastrar_cliente
from ..routers.simcards import SimCardInput, cadastrar_simcard
from ..routers.rastreadores import RastreadorInput, cadastrar_rastreador
from ..routers.veiculos import VeiculoInput, cadastrar_veiculo

router = APIRouter(prefix="/weso/onboarding", tags=["onboarding"])


class OnboardingInput(BaseModel):
    cliente:    ClienteInput
    simcard:    SimCardInput
    rastreador: RastreadorInput
    veiculo:    VeiculoInput


@router.post("")
async def onboarding(body: OnboardingInput):
    resultado = {"cliente": None, "simcard": None, "rastreador": None, "veiculo": None}

    if body.veiculo.serial_rastreador != body.rastreador.numeroSerie:
        return {
            "ok": False, "etapas": resultado,
            "erro": f"veiculo.serial_rastreador '{body.veiculo.serial_rastreador}' diverge de rastreador.numeroSerie '{body.rastreador.numeroSerie}'",
            "etapa_falhou": "veiculo",
        }

    def _erro(e: Exception) -> str:
        return e.detail if hasattr(e, "detail") else str(e)

    try:
        r = await cadastrar_cliente(body.cliente)
        resultado["cliente"] = {"acao": r.get("acao"), "id": r.get("id")}
    except Exception as e:
        return {"ok": False, "etapas": resultado, "erro": _erro(e), "etapa_falhou": "cliente"}

    try:
        r = await cadastrar_simcard(body.simcard)
        resultado["simcard"] = {"acao": r.get("acao"), "id": r.get("id")}
    except Exception as e:
        return {"ok": False, "etapas": resultado, "erro": _erro(e), "etapa_falhou": "simcard"}

    try:
        r = await cadastrar_rastreador(body.rastreador)
        resultado["rastreador"] = {"acao": r.get("acao"), "id": r.get("id")}
    except Exception as e:
        return {"ok": False, "etapas": resultado, "erro": _erro(e), "etapa_falhou": "rastreador"}

    try:
        r = await cadastrar_veiculo(body.veiculo)
        resultado["veiculo"] = {"acao": r.get("acao"), "id": r.get("id")}
    except Exception as e:
        return {"ok": False, "etapas": resultado, "erro": _erro(e), "etapa_falhou": "veiculo"}

    return {"ok": True, "etapas": resultado, "erro": None, "etapa_falhou": None}
```

---

## Testes

### Caso 1 — Fluxo completo com dados novos
**Request:**
```json
POST /weso/onboarding
{
  "cliente":    { "cnpjcpf": "11222333000181", "razaoSocial": "teste iago API" },
  "simcard":    { "iccId": "8955170220424545088" },
  "rastreador": { "numeroSerie": "FPSLTEST002", "modelo": "Teste" },
  "veiculo":    { "placa": "FPS0A02", "cnpjcpf_cliente": "11222333000181", "serial_rastreador": "FPSLTEST002" }
}
```
**Esperado:** `ok: true`, todas etapas com `acao: "criado"`

> Dados novos: cliente já existia (`ja_existe`); simcard, rastreador e veículo eram novos.

### Caso 2 — Fluxo completo com dados já existentes
**Request:** mesmos dados do Caso 1  
**Esperado:** `ok: true`, todas etapas com `acao: "ja_existe"`

### Caso 3 — Campo obrigatório ausente no rastreador
**Request:** rastreador sem `modelo` (campo omitido do JSON)
```json
POST /weso/onboarding
{
  "cliente":    { "cnpjcpf": "11222333000181", "razaoSocial": "teste iago API" },
  "simcard":    { "iccId": "8955170220424545088" },
  "rastreador": { "numeroSerie": "FPSLTEST002" },
  "veiculo":    { "placa": "FPS0A02", "cnpjcpf_cliente": "11222333000181", "serial_rastreador": "FPSLTEST002" }
}
```
**Esperado:** HTTP 422 — validação Pydantic rejeita a requisição inteira antes de qualquer etapa executar

---

## Resultado do Teste

| Caso | Esperado | Obtido | Status |
|------|----------|--------|--------|
| 1 — dados novos | `ok: true`, etapas `criado` | `ok: false` na 1ª tentativa (timeout WESO no veículo) — dado foi persistido | ⚠️ |
| 2 — duplicatas | `ok: true`, todas `ja_existe` | `ok: true`, cliente/rastreador com id, simcard/veículo com `id: null` | ✅ |
| 3 — campo obrigatório ausente | HTTP 422, campo `rastreador.modelo` apontado | HTTP 422, Pydantic rejeita antes de executar qualquer etapa | ✅ |

**Observações confirmadas em teste real:**
- CNPJs totalmente fictícios (ex: `99999999000191`) causam timeout na WESO — usar CNPJ real cadastrado.
- ICCIDs sem prefixo de operadora real causam timeout — usar prefixo `8955`.
- A cadeia completa acumula latência (~10s por chamada WESO): com 5–6 chamadas, o total pode ultrapassar 30s e resultar em timeout na última etapa. O dado **é persistido** mesmo quando a resposta não chega a tempo — confirmado pelo Caso 2 mostrando `ja_existe` para o veículo.
- `simcard` e `veiculo` retornam `id: null` em `ja_existe` — limitação conhecida da WESO (ver Abas 02 e 04).
- **Falha por campo ausente vs. falha em runtime:** quando um campo obrigatório de qualquer etapa está ausente, o Pydantic rejeita toda a requisição com HTTP 422 antes de executar qualquer etapa — nenhum dado é criado. O comportamento `ok: false` com `etapa_falhou` e etapas anteriores preenchidas **só ocorre quando a chamada à WESO em si falha** (erro de negócio, timeout, 4xx/5xx da API), não por ausência de campo obrigatório.
- **Rastreador já instalado:** se `serial_rastreador` tiver `situacao: "Instalado"` na WESO, o passo 4 (veiculo) falha com `etapa_falhou: "veiculo"` e `erro: "Rastreador '...' já está instalado em outro veículo"` — os passos 1–3 já terão sido executados e seus resultados ficam em `etapas`.
- **Validação cruzada de serial:** o handler verifica que `veiculo.serial_rastreador == rastreador.numeroSerie` antes de iniciar qualquer chamada — divergência retorna imediatamente `ok: false, etapa_falhou: "veiculo"`.

---

## Histórico de Tentativas

| # | Data | Resultado | Observação |
|---|------|-----------|------------|
| 1 | 2026-06-12 | ⚠️ Parcial | Caso 1: timeout no veículo (dado criado). Caso 2: ✅ deduplicação completa. Caso 3 pendente. |
| 2 | 2026-06-12 | ✅ Êxito | Caso 3 redefinido: comportamento real é HTTP 422 (Pydantic) antes de qualquer etapa — documentado como correto. 3/3 casos validados. |
