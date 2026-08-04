# Harmonit — Serviços Integrados (Padrões de Uso Composto)

> Fluxos que combinam múltiplos endpoints da Harmonit (e fontes externas) em operações de negócio.  
> Estes serviços vivem na camada de aplicação — não são endpoints nativos da Harmonit.

---

## 1. Onboarding de Frota (Cliente + Placas)

### Problema

Cadastrar um cliente e suas placas evitando duplicidade, com retorno claro sobre o que foi criado vs. o que já existia.

### Fluxo

```
POST /meu-servico/cadastrar-frota
Body: {
  "cnpj": "12.345.678/0001-99",
  "placas": ["ABC1234", "XYZ5678"]
}
```

**Passo 1 — Verificar cliente por CNPJ**

```
GET /ObterClientePorCpfCnpj?cpfCnpj=12.345.678/0001-99
```

- Encontrado → usa `clienteId` retornado, `clienteStatus = "existing"`
- Não encontrado (404 / data vazia) → cria cliente:

```
POST /Cliente/CadastrarOuAtualizar
{
  "id": 0,
  "cnpj_cpf": "12.345.678/0001-99",
  "pessoa": "Juridica",
  "nome": "...",
  "situacaoClienteId": 1
}
```
→ `clienteStatus = "created"`, salva o `clienteId` retornado

**Passo 2 — Verificar placas existentes**

```
GET /Veiculo/ObterVeiculos
```

> Retorna todos os veículos sem filtro. Filtrar por `placa` no lado da aplicação.

Para cada placa recebida:
- Já existe na lista → `status = "existing"`, salva `veiculoId`
- Não existe → cria:

```
POST /Veiculo/Incluir
{
  "id": 0,
  "placa": "ABC1234",
  "clienteId": <clienteId>,
  "veiculo": "...",
  "tipo": "...",
  "marca": "..."
}
```
→ `status = "created"`, salva `veiculoId` retornado

**Passo 3 — Retorno consolidado**

```json
{
  "clienteId": 101,
  "clienteStatus": "existing",
  "veiculos": [
    { "placa": "ABC1234", "status": "existing", "veiculoId": 45 },
    { "placa": "XYZ5678", "status": "created",  "veiculoId": 46 }
  ]
}
```

### Cuidados

| Ponto | Detalhe |
|-------|---------|
| `GET /Veiculo/ObterVeiculos` sem filtro | Carrega todos os veículos. Em bases grandes, considerar cache local indexado por placa ou checagem incremental |
| CNPJ com/sem máscara | Testar se a Harmonit aceita `12345678000199` (sem formatação) ou exige `12.345.678/0001-99` |
| Race condition | Se dois cadastros simultâneos chegarem para a mesma placa, ambos passam no GET e um cria duplicata. Serializar por CNPJ ou usar lock se relevante |

---

## 2. Monitoramento de Chips por Operadora

### Problema

Verificar se os chips instalados nos veículos estão ativos na operadora e gerar alerta quando houver risco de desativação ou consumo elevado.

### Arquitetura

```
[Scheduler — ex: diário às 07h]
        ↓
[Módulo: HarmonitRastreadorService]
        ↓
POST /Rastreador/ObterRastreadores   ← Harmonit
        ↓
Para cada rastreador com ativar == true e simCardId != null:
        ↓
[Módulo: OperadoraConsultaService]   ← API externa da operadora
  Vivo IoT / Claro M2M / TIM API
  Input: numeroLinha ou numeroChip (ICCID)
  Output: status (ativo/suspenso), consumo MB/ciclo, data renovação
        ↓
[Módulo: AlertaService]
  Se consumo > threshold OU status == suspenso:
    → dispara notificação (email / webhook / WhatsApp)
```

### Campos relevantes retornados pela Harmonit

| Campo | Tipo | Uso |
|-------|------|-----|
| `simCardId` | integer | ID interno do chip |
| `numeroChip` | string | ICCID — chave de consulta na operadora |
| `numeroLinha` | string | Número da linha — alternativa de consulta |
| `veiculoId` | integer | Vínculo com veículo |
| `placa` | string | Identificação humana do veículo |
| `instalado` | boolean | Se o rastreador está fisicamente instalado |
| `ativar` | boolean | Status de ativação no ERP |

### Regra de elegibilidade para consulta na operadora

```python
chip_elegivel = (
    rastreador["instalado"] == True and
    rastreador["ativar"] == True and
    rastreador["simCardId"] is not None and
    rastreador["numeroLinha"] is not None
)
```

### O que a Harmonit não cobre (responsabilidade do serviço próprio)

- Conexão com APIs das operadoras (credenciais externas)
- Thresholds de consumo configuráveis por operadora
- Histórico de alertas gerados
- Canal de notificação (email, push, webhook)
- Lógica de supressão (não renotificar o mesmo chip em 24h)

---

## Relação entre os dois serviços

Estes dois serviços compartilham dados base:

```
OnboardingFrota → cria Veiculo (veiculoId) + Cliente (clienteId)
                         ↓
              Rastreador.Incluir vincula simCardId + veiculoId
                         ↓
              MonitoramentoChip consulta por rastreadores instalados
```

O onboarding correto (cliente → veículo → rastreador → simcard) é pré-requisito para o monitoramento funcionar.
