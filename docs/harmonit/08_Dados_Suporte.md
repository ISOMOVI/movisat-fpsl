# Harmonit — Tabelas de Apoio (Dados de Suporte)

> Endpoints de lookup — usados para popular selects e validar IDs antes de criar OS, produtos, etc.  
> **Auth:** `Authorization: Bearer TOKEN`

---

## Visão geral

| Módulo                   | Para que serve                                          |
|--------------------------|---------------------------------------------------------|
| `SituacaoOrdemServico`   | Status possíveis de uma OS (campo `situacaoId`)         |
| `TipoOrdemServico`       | Tipos de OS (campo `tipoId`)                            |
| `PrioridadeAtendimento`  | Prioridades de atendimento (campo `prioridadeId`)       |
| `Problema`               | Categorias de problema (campo `problemaId`)             |
| `UnidadeMedida`          | Unidades de medida de produtos                          |
| `EstoqueLocal`           | Locais de estoque da empresa                            |
| `Operadora`              | Operadoras de telefonia para SIM Cards                  |

---

## Situação de OS

| Método | Rota                                           | Ação                     |
|--------|------------------------------------------------|--------------------------|
| GET    | `/SituacaoOrdemServico/ObterSituacoesOS`       | Listar todos os status   |
| GET    | `/SituacaoOrdemServico/ObterSituacaoOS`        | Buscar status por ID     |
| POST   | `/SituacaoOrdemServico/CadastrarOuAtualizar`   | Criar ou atualizar       |
| DELETE | `/SituacaoOrdemServico/Excluir`                | Excluir                  |

**GET** `/SituacaoOrdemServico/ObterSituacoesOS?search=Aberta&skip=0&take=20`

**Resposta:**
```json
[
  { "id": 1, "empresaId": 1, "descricao": "Aberta" },
  { "id": 2, "empresaId": 1, "descricao": "Em Andamento" },
  { "id": 3, "empresaId": 1, "descricao": "Concluída" },
  { "id": 4, "empresaId": 1, "descricao": "Cancelada" }
]
```

**POST** `/SituacaoOrdemServico/CadastrarOuAtualizar`
```json
{ "id": 0, "empresaId": 1, "descricao": "Aguardando Peça" }
```

**DELETE** `/SituacaoOrdemServico/Excluir?situacaoOsId=5`

---

## Tipo de OS

| Método | Rota                                              | Ação                        |
|--------|---------------------------------------------------|-----------------------------|
| GET    | `/TipoOrdemServico/ObterTiposOrdemServico`        | Listar tipos (com search)   |
| GET    | `/TipoOrdemServico/ObterListaTipoOrdemServico`    | Listar tipos básicos        |

**GET** `/TipoOrdemServico/ObterTiposOrdemServico?seacrh=Instalacao`

> **Atenção:** typo no param — é `seacrh` (não `search`) neste endpoint específico.

**Resposta:**
```json
[
  { "id": 1, "empresaId": 1, "codigo": 10, "descricao": "Instalação", "fullControl": true },
  { "id": 2, "empresaId": 1, "codigo": 20, "descricao": "Manutenção", "fullControl": false }
]
```

**GET** `/TipoOrdemServico/ObterListaTipoOrdemServico`  
Versão simplificada sem `empresaId`.

---

## Prioridade de Atendimento

| Método | Rota                                            | Ação                     |
|--------|-------------------------------------------------|--------------------------|
| GET    | `/PrioridadeAtendimento/ObterPrioridades`       | Listar prioridades       |
| GET    | `/PrioridadeAtendimento/ObterPrioridade`        | Buscar por ID            |

**GET** `/PrioridadeAtendimento/ObterPrioridades?skip=0&take=20`

**Resposta:**
```json
[
  { "id": 1, "descricao": "Alta", "sla": "4h", "limite": "2h" },
  { "id": 2, "descricao": "Média", "sla": "24h", "limite": "12h" },
  { "id": 3, "descricao": "Baixa", "sla": "72h", "limite": "48h" }
]
```

**GET** `/PrioridadeAtendimento/ObterPrioridade?prioridadeId=1`

---

## Problema (Categoria de Chamado)

| Método | Rota                             | Ação                     |
|--------|----------------------------------|--------------------------|
| GET    | `/Problema/ObterProblemas`       | Listar problemas         |
| GET    | `/Problema/ObterProblema`        | Buscar por ID            |
| POST   | `/Problema/CadastrarOuAtualizar` | Criar ou atualizar       |
| DELETE | `/Problema/Excluir`              | Excluir                  |

**GET** `/Problema/ObterProblemas?search=Rastreador`

**Resposta:**
```json
[
  { "id": 5, "codigo": 10, "descricao": "Rastreador sem sinal", "empresaId": 1, "status": true },
  { "id": 6, "codigo": 11, "descricao": "Rastreador desligado", "empresaId": 1, "status": true }
]
```

**POST** `/Problema/CadastrarOuAtualizar`
```json
{ "id": 0, "codigo": 15, "descricao": "GPS desatualizado", "empresaId": 1, "status": true }
```

**DELETE** `/Problema/Excluir?problemaId=5`

---

## Unidade de Medida

| Método | Rota                                   | Ação                     |
|--------|----------------------------------------|--------------------------|
| GET    | `/UnidadeMedida/ObterUnidadesMedidas`  | Listar unidades          |
| GET    | `/UnidadeMedida/ObterUnidadeMedida`    | Buscar por ID            |
| POST   | `/UnidadeMedida/CadastrarOuAtualizar`  | Criar ou atualizar       |
| DELETE | `/UnidadeMedida/Excluir`               | Excluir                  |

**GET** `/UnidadeMedida/ObterUnidadesMedidas?search=un`

**Resposta:**
```json
[
  { "id": 1, "descricao": "Unidade", "codigo": "UN", "empresaId": 1 },
  { "id": 2, "descricao": "Metro", "codigo": "MT", "empresaId": 1 }
]
```

---

## Estoque Local

| Método | Rota                                   | Ação                        |
|--------|----------------------------------------|-----------------------------|
| GET    | `/EstoqueLocal/ObterEstoqueLocais`     | Listar locais de estoque    |
| GET    | `/EstoqueLocal/ObterEstoqueLocal`      | Buscar local por ID         |
| POST   | `/EstoqueLocal/CadastrarOuAtualizar`   | Criar ou atualizar          |
| DELETE | `/EstoqueLocal/Excluir`                | Excluir                     |

**GET** `/EstoqueLocal/ObterEstoqueLocais?somenteAtivos=true`

**Resposta:**
```json
[
  { "id": 1, "descricao": "Almoxarifado Central", "principal": true, "empresaId": 1, "tipo": "Interno" },
  { "id": 2, "descricao": "Estoque Técnico Carlos", "principal": false, "empresaId": 1, "tipo": "Técnico" }
]
```

**POST** `/EstoqueLocal/CadastrarOuAtualizar`
```json
{ "id": 0, "descricao": "Estoque Filial SP", "ativo": true, "empresaId": 1 }
```

---

## Operadora de Telefonia

| Método | Rota                           | Ação                     |
|--------|--------------------------------|--------------------------|
| GET    | `/Operadora/ObterOperadoras`   | Listar operadoras        |
| GET    | `/Operadora/ObterPorId`        | Buscar por ID            |
| POST   | `/Operadora/CadastrarOuAtualizar` | Criar ou atualizar    |
| PUT    | `/Operadora/Atualizar`         | Atualizar (PUT)          |

**GET** `/Operadora/ObterOperadoras?skip=0&take=20`

**Resposta:**
```json
[
  { "id": 1, "descricao": "Vivo" },
  { "id": 2, "descricao": "Claro" },
  { "id": 3, "descricao": "TIM" }
]
```

**POST** `/Operadora/CadastrarOuAtualizar`
```json
{ "id": 0, "descricao": "Oi" }
```

---

## Sequência recomendada para popular lookups

Antes de criar uma OS, obter os IDs necessários:

```
1. GET /SituacaoOrdemServico/ObterSituacoesOS   → situacaoId
2. GET /TipoOrdemServico/ObterListaTipoOrdemServico → tipoId + codigoTipoOrdemServico
3. GET /PrioridadeAtendimento/ObterPrioridades  → prioridadeId
4. GET /Problema/ObterProblemas                 → problemaId + codigoProblema
5. GET /Usuario/ObterTecnicos                   → tecnicoId
6. GET /Usuario/ObterVendedores                 → vendedorId
7. GET /ObterCliente ou /ObterClientePorCpfCnpj → clienteId
```
