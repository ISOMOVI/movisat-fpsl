# FPSL — FastAPI Proxy Service Local · WESO
## Proposta de Desenvolvimento

> Camada de proxy local entre a integração Harmonit↔WESO e a API pública da WESO.  
> Centraliza autenticação, encapsula inconsistências conhecidas e expõe um contrato limpo e previsível.

---

## Objetivo

A API WESO possui inconsistências documentadas (campos não declarados como obrigatórios, endpoints quebrados, formatos de resposta mistos) que não devem vazar para a camada de integração com o Harmonit. O FPSL absorve essas peculiaridades e expõe rotas com comportamento estável e uniforme.

---

## Stack

| Componente | Escolha |
|------------|---------|
| Framework | FastAPI |
| HTTP Client | `httpx.AsyncClient` (singleton via lifespan) |
| Configuração | `pydantic-settings` (`.env`) |
| Modelos de dados | Pydantic v2 |
| Python | 3.11+ |

---

## Estrutura de Arquivos

```
fpsl_weso/
├── main.py                  # app FastAPI + lifespan
├── config.py                # WESOSettings (base_url, api_key)
├── client.py                # httpx singleton + parsers de resposta
├── models/
│   ├── cliente.py
│   ├── simcard.py
│   ├── rastreador.py
│   └── veiculo.py
├── routers/
│   ├── clientes.py
│   ├── simcards.py
│   ├── rastreadores.py
│   └── veiculos.py
└── services/
    └── onboarding.py        # fluxo composto: Cliente→Chip→Equipamento→Placa
```

---

## Rotas Propostas

### Clientes · `/weso/clientes`

| Método | Rota | Ação | Deduplicação |
|--------|------|------|-------------|
| `GET` | `/weso/clientes` | Consultar por `cnpjcpf` | — |
| `POST` | `/weso/clientes` | Criar cliente | Consulta antes; cria só se não existe |
| `PUT` | `/weso/clientes/{cnpjcpf}` | Atualizar cliente | — |

### SIM Cards · `/weso/simcards`

| Método | Rota | Ação | Deduplicação |
|--------|------|------|-------------|
| `POST` | `/weso/simcards` | Criar chip | Tenta criar; 409 → retorna "já existe" |
| `PUT` | `/weso/simcards/{iccid}` | Atualizar chip | — |

> `GET /SimCard/Consultar` bloqueado na API — sem rota de consulta direta.

### Rastreadores · `/weso/rastreadores`

| Método | Rota | Ação | Deduplicação |
|--------|------|------|-------------|
| `GET` | `/weso/rastreadores/{id}` | Consultar por ID | — |
| `POST` | `/weso/rastreadores` | Criar rastreador | Tenta criar; 409 → retorna "já existe" |
| `PUT` | `/weso/rastreadores/{id}/chip` | Vincular chip ao rastreador | — |

### Veículos · `/weso/veiculos`

| Método | Rota | Ação | Deduplicação |
|--------|------|------|-------------|
| `POST` | `/weso/veiculos` | Criar veículo + vínculos | Tenta criar; 409 → retorna "já existe" |
| `PUT` | `/weso/veiculos/{id}` | Atualizar veículo | — |
| `DELETE` | `/weso/veiculos/{id}` | Excluir veículo | Usa `veiculo_id` — exclusão por placa não confiável |

> `GET /Veiculos/Consultar` com falha na API — sem rota de consulta direta.

### Onboarding Composto · `/weso/onboarding`

| Método | Rota | Ação |
|--------|------|------|
| `POST` | `/weso/onboarding` | Executa fluxo completo: Cliente → Chip → Equipamento → Placa em sequência, retorna IDs de todos os objetos criados/vinculados |

---

## Modelos de Entrada

### ClienteInput
```python
class ClienteInput(BaseModel):
    cnpjcpf:        str               # obrigatório — chave
    razaoSocial:    str               # obrigatório
    nomeFantasia:   str | None = None
    tipoCliente:    str | None = None  # Fisica / Juridica / NaoInformado
    situacao:       str | None = None  # Adimplente / Bloqueado / Teste / ...
    contato:        str | None = None
    telefone:       str | None = None
    emailCobranca:  str | None = None
    plano:          str | None = None
    endereco:       str | None = None
    numeroEnd:      str | None = None
    bairro:         str | None = None
    cep:            str | None = None
    obs:            str | None = None
```

### SimCardInput
```python
class SimCardInput(BaseModel):
    iccId:            str               # obrigatório — chave
    numero:           int | None = None
    operadora:        str | None = None
    apn:              str | None = None
    situacao:         str | None = None  # Estoque / EmUso / Inativo
    valorMensalidade: float | None = None
    obs:              str | None = None
```

### RastreadorInput
```python
class RastreadorInput(BaseModel):
    numeroSerie: str               # obrigatório — chave
    modelo:      str               # obrigatório — confirmado em teste
    iccId:       str | None = None  # vínculo do chip (via Rastreadores/Atualizar)
    tipo:        str | None = None
    situacao:    str | None = None
    lote:        str | None = None
    notaFiscal:  str | None = None
    valorPago:   float | None = None
    # fornecedor removido — WESO não tem endpoint de consulta de fornecedor;
    # auto-criação indesejada; gestão de fornecedor pertence ao Harmonit
```

### VeiculoInput
```python
class VeiculoInput(BaseModel):
    placa:              str               # obrigatório — chave
    cnpjcpf_cliente:    str               # obrigatório para o fluxo
    serial_rastreador:  str               # obrigatório para o fluxo
    tipoEqp:            int | None = None
    descricao:          str | None = None
    cor:                str | None = None
    chassi:             str | None = None
    renavam:            str | None = None
    anoFab:             int | None = None
    anoMod:             int | None = None
    valorMensalidade:   float | None = None
    observacoes:        str | None = None
    observacoesGestor:  str | None = None
```

### OnboardingInput
```python
class OnboardingInput(BaseModel):
    cliente:    ClienteInput
    simcard:    SimCardInput
    rastreador: RastreadorInput
    veiculo:    VeiculoInput
```

---

## Modelo de Resposta Padrão

Todas as rotas FPSL retornam o mesmo envelope, independente do formato A ou B da WESO:

```python
class FPSLResponse(BaseModel):
    ok:      bool
    acao:    str        # "criado" | "ja_existe" | "atualizado" | "excluido"
    id:      int | None = None
    dados:   dict | None = None
    erro:    str | None = None
```

---

## Tratamento de Inconsistências Internas

| Inconsistência | Tratamento no FPSL |
|---------------|-------------------|
| `SimCard/Consultar` bloqueado | POST + captura 409 → `acao: "ja_existe"` |
| `Veiculos/Consultar` quebrado | POST + captura 409 → `acao: "ja_existe"` |
| `modelo` obrigatório no Rastreador | Campo exposto como obrigatório no `RastreadorInput` |
| Resposta HTML em erros (Veiculos, Motorista) | Verificar `Content-Type` antes do parse JSON; HTML → erro genérico |
| Formato de data `/Date(ms)/` | Normalizar para ISO 8601 no `client.py` antes de repassar |
| Dois envelopes de resposta (A e B) | `client.py` detecta pelo campo `Status` vs `HasError` e normaliza |

---

## Fluxo de Deduplicação por Etapa

```
CLIENTE
  GET /Clientes/Consultar?cnpjcpf=...
    → encontrou → retorna id existente
    → não encontrou → POST /Clientes/Cadastro → retorna id criado

CHIP
  POST /SimCard/Cadastro
    → 201 → criado
    → 409 → já existe (usa iccId como referência)

EQUIPAMENTO
  POST /Rastreadores/Cadastro  (com modelo obrigatório)
    → 201 → criado → PUT /Rastreadores/Atualizar para vincular chip
    → 409 → já existe → PUT /Rastreadores/Atualizar para garantir vínculo do chip

PLACA
  POST /Veiculos/Cadastro  (com cnpjcpf_cliente + serial_rastreador)
    → 201 → criado e vinculado
    → 409 → já existe
```

---

## Pontos em Aberto

| # | Ponto | Status | Decisão / Resolução |
|---|-------|--------|---------------------|
| P1 | Usuário de acesso WeFleet | ⚠️ Em análise | Endpoint não existe ainda — criação manual via painel web por enquanto. Pode ser liberado futuramente. Fora do escopo do FPSL até lá. |
| P2 | `situacao` do cliente | ✅ Documentado | Tabela de-para em `Harmonit_WESO_Mapeamento.md` — ex: Ativo→Adimplente, Bloqueado→Bloqueado. Implementar como config na camada de integração. |
| P3 | `tipoEqp` do veículo | ✅ Documentado | Tabela de-para em `Harmonit_WESO_Mapeamento.md` — ex: Automóvel→1, Moto→2, Caminhão→3. |
| P4 | `modelo` do rastreador | ✅ Resolvido | `modeloEquipamento` do Harmonit mapeia direto para `modelo` no WESO. |
| P5 | Fornecedor do rastreador | ✅ Resolvido | `fornecedor` é **opcional** na WESO (`/Rastreadores/Cadastro`). Omitir no FPSL — não é necessário definir padrão. |
| P6 | Campos opcionais do veículo | ✅ Resolvido | Harmonit tem: `cor`, `ano`, `numeroChassi`, `modelo`, `marca`, `odometro` — nenhum tem equivalente na WESO. Apenas `placa` e `tipo`→`tipoEqp` são sincronizados. |

> **Foco atual:** operação manual via FPSL. Integração com Harmonit será proposta em etapa posterior.
