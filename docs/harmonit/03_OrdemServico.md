# Harmonit — API de Ordens de Serviço

> **Auth:** `Authorization: Bearer TOKEN`  
> O módulo mais completo da API — 17 endpoints cobrindo o ciclo inteiro de uma OS.

---

## Endpoints

| Método | Rota                                          | Ação                                   |
|--------|-----------------------------------------------|----------------------------------------|
| GET    | `/OrdemServico/ObterOrdemServico`             | Buscar OS por ID                       |
| GET    | `/OrdemServico/ObterOrdemServicoPorNumero`    | Buscar OS por número                   |
| POST   | `/OrdemServico/SalvarOrdemServico`            | Criar/atualizar OS completa            |
| POST   | `/OrdemServico/SalvarOrdemServicoBasica`      | Criar OS básica (forma simplificada)   |
| DELETE | `/OrdemServico/RemoverOrdemServico`           | Excluir OS                             |
| GET    | `/OrdemServico/ObterTimeLine`                 | Histórico de status da OS              |
| GET    | `/OrdemServico/ObterMateriaisOrdemServico`    | Listar materiais da OS                 |
| POST   | `/OrdemServico/SalvarMaterialOrdemServico`    | Adicionar/atualizar material           |
| DELETE | `/OrdemServico/RemoverMaterialOrdemServico`   | Remover material da OS                 |
| GET    | `/OrdemServico/ObterTecnicoOrdemServico`      | Listar técnicos da OS                  |
| POST   | `/OrdemServico/SalvarTecnicoOrdemServico`     | Vincular técnico à OS                  |
| DELETE | `/OrdemServico/RemoverTecnicoOrdemServico`    | Remover técnico da OS                  |
| POST   | `/OrdemServico/AgendarTecnico`                | Agendar técnico (agenda)               |
| GET    | `/OrdemServico/ObterCheckListOrdemServico`    | Listar checklist da OS                 |
| POST   | `/OrdemServico/SalvarCheckListOrdemServico`   | Adicionar item ao checklist            |
| PUT    | `/OrdemServico/AtualizarStatusCheckList`      | Marcar item como executado/não executado|
| DELETE | `/OrdemServico/RemoverCheckListOrdemServico`  | Remover item do checklist              |
| GET    | `/OrdemServico/ObterOficinas`                 | Listar equipamentos instalados na OS   |
| POST   | `/OrdemServico/AdicionarOficina`              | Registrar instalação de rastreador     |
| POST   | `/OrdemServico/DesinstalarOficina`            | Registrar desinstalação de rastreador  |

---

## 1. Buscar OS

### Por ID

**GET** `/OrdemServico/ObterOrdemServico?osId=123`

### Por Número

**GET** `/OrdemServico/ObterOrdemServicoPorNumero?numeroOs=456`

### Resposta (OrdemServicoMobile)

```json
{
  "data": {
    "id": 123,
    "empresaId": 1,
    "numeroOrdem": 456,
    "dataPrevisao": "2024-05-30T10:00:00",
    "localServico": 1,
    "situacaoId": 2,
    "tipoId": 1,
    "prioridadeId": 3,
    "problemaId": 5,
    "clienteId": 101,
    "bairro": "Centro",
    "cep": "01000-000",
    "cidade": "São Paulo",
    "endereco": "Rua das Flores, 123",
    "uf": "SP",
    "descricaoDetalhada": "Instalação de rastreador veicular",
    "solucaoTecnica": "Rastreador instalado com sucesso"
  }
}
```

---

## 2. Criar OS Básica *(forma recomendada para criação rápida)*

**POST** `/OrdemServico/SalvarOrdemServicoBasica`

Versão simplificada — mínimo de campos para abrir uma OS.

```json
{
  "id": 0,
  "descricao": "Instalação de rastreador",
  "codigoProblema": 10,
  "codigoTipoOrdemServico": 1,
  "clienteId": 101
}
```

| Campo                    | Tipo    | Descrição                                               |
|--------------------------|---------|---------------------------------------------------------|
| `id`                     | integer | `0` para criar, ID para atualizar                       |
| `descricao`              | string  | Descrição da OS                                         |
| `codigoProblema`         | integer | Código do problema (obter via `/Problema/ObterProblemas`)|
| `codigoTipoOrdemServico` | integer | Código do tipo de OS (via `/TipoOrdemServico/...`)      |
| `clienteId`              | integer | ID do cliente                                           |

**Resposta 200:**
```json
{
  "data": {
    "ordemServicoId": 789,
    "numeroOrdem": 456,
    "dataSolicitadoEm": "2024-05-22T14:00:00",
    "status": "..."
  }
}
```

---

## 3. Criar/Atualizar OS Completa

**POST** `/OrdemServico/SalvarOrdemServico`

```json
{
  "id": 0,
  "empresaId": 1,
  "numeroOrdem": 0,
  "dataPrevisaoEntrega": "2024-06-01T10:00:00",
  "localServicoId": 1,
  "tipoId": 1,
  "prioridadeId": 2,
  "situacaoId": 1,
  "problemaId": 5,
  "produtoServicoId": 10,
  "clienteId": 101,
  "bairro": "Centro",
  "cep": "01000-000",
  "cidade": "São Paulo",
  "endereco": "Rua das Flores",
  "uf": "SP",
  "complemento": "Sala 1",
  "numero": "123",
  "descricaoDetalhada": "Instalação de rastreador veicular",
  "status": 1,
  "valorRetAlimentacao": 0.00,
  "valorRetProdutosLimpeza": 0.00,
  "valorRetValeTransporte": 0.00,
  "vendedorId": 5,
  "solucaoTecnica": ""
}
```

| Campo                    | Tipo    | Descrição                                               |
|--------------------------|---------|---------------------------------------------------------|
| `id`                     | integer | `0` para criar, ID para atualizar                       |
| `empresaId`              | integer | ID da empresa                                           |
| `localServicoId`         | integer | Local do serviço                                        |
| `tipoId`                 | integer | Tipo de OS (via `/TipoOrdemServico/...`)                 |
| `prioridadeId`           | integer | Prioridade (via `/PrioridadeAtendimento/...`)           |
| `situacaoId`             | integer | Status (via `/SituacaoOrdemServico/...`)                |
| `problemaId`             | integer | Problema/categoria (via `/Problema/...`)               |
| `produtoServicoId`       | integer | Produto ou serviço associado                            |
| `clienteId`              | integer | ID do cliente                                           |
| `vendedorId`             | integer | ID do vendedor responsável                              |
| `descricaoDetalhada`     | string  | Descrição detalhada do problema                         |
| `solucaoTecnica`         | string  | Solução técnica aplicada                                |

---

## 4. Excluir OS

**DELETE** `/OrdemServico/RemoverOrdemServico?osId=123`

---

## 5. Timeline da OS

**GET** `/OrdemServico/ObterTimeLine?osId=123`

Retorna o histórico completo de mudanças de status.

```json
[
  {
    "id": 1,
    "osId": 123,
    "numeroOs": "456",
    "status": 2,
    "statusDesc": "Em Andamento",
    "dataHora": "2024-05-22T14:30:00"
  },
  {
    "id": 2,
    "osId": 123,
    "numeroOs": "456",
    "status": 5,
    "statusDesc": "Concluída",
    "dataHora": "2024-05-22T17:00:00"
  }
]
```

---

## 6. Materiais da OS

### Listar

**GET** `/OrdemServico/ObterMateriaisOrdemServico?ordemServicoId=123`

**Resposta:**
```json
[
  {
    "id": 1,
    "produtoId": 10,
    "codigo": "PROD-001",
    "descricao": "Rastreador CRX3",
    "quantidade": 1,
    "valor": 350.00,
    "cobrar": true,
    "comodato": false
  }
]
```

### Adicionar/Atualizar Material

**POST** `/OrdemServico/SalvarMaterialOrdemServico`

```json
{
  "id": 0,
  "empresaId": 1,
  "osId": 123,
  "produtoId": 10,
  "quantidade": 1,
  "valor": 350.00,
  "cobrar": true,
  "locacao": false,
  "comodato": false,
  "quantidade_Fator": 1,
  "produtoConversaoUnidadeId": null,
  "locacaoBens": false,
  "pesoBruto": 0.5,
  "pesoLiquido": 0.45,
  "zonasParticoesId": null
}
```

### Remover Material

**DELETE** `/OrdemServico/RemoverMaterialOrdemServico?ordemServicoId=123&id=1`

---

## 7. Técnicos da OS

### Listar

**GET** `/OrdemServico/ObterTecnicoOrdemServico?osId=123`

```json
[
  {
    "id": 1,
    "osId": 123,
    "usuarioId": 50,
    "nomeTecnico": "Carlos Técnico",
    "email": "carlos@empresa.com"
  }
]
```

### Vincular Técnico

**POST** `/OrdemServico/SalvarTecnicoOrdemServico`

```json
{
  "osId": 123,
  "empresaId": 1,
  "tecnicoId": 50,
  "veiculoId": "VEI-001",
  "veiculoNome": "Fiat Uno",
  "veiculoPlaca": "ABC1234",
  "tecnicoResponsavelPelaOS": true
}
```

### Agendar Técnico

**POST** `/OrdemServico/AgendarTecnico`

```json
{
  "id": 0,
  "clienteId": 101,
  "ordemServicoId": 123,
  "ordemServicoxTecnicoId": 1,
  "inicioCompromisso": "2024-06-01T09:00:00",
  "fimCompromisso": "2024-06-01T11:00:00"
}
```

### Remover Técnico

**DELETE** `/OrdemServico/RemoverTecnicoOrdemServico?osId=123&id=1&agendaId=0`

> Se não houver `agendaId`, enviar `0`.

---

## 8. Checklist da OS

### Listar

**GET** `/OrdemServico/ObterCheckListOrdemServico?osId=123`

```json
[
  { "id": 1, "descricao": "Testar ignição", "tecnico": "Carlos", "status": false },
  { "id": 2, "descricao": "Verificar conexões", "tecnico": "Carlos", "status": true }
]
```

### Adicionar Item

**POST** `/OrdemServico/SalvarCheckListOrdemServico?osId=123&descricao=Testar GPS`

### Atualizar Status

**PUT** `/OrdemServico/AtualizarStatusCheckList?osId=123&checkListId=1&status=true`

| `status` | Significado      |
|----------|------------------|
| `true`   | Executado        |
| `false`  | Não executado    |

### Remover Item

**DELETE** `/OrdemServico/RemoverCheckListOrdemServico?osId=123&checkListId=1`

---

## 9. Oficinas (Instalações de Rastreador)

### Listar equipamentos instalados na OS

**GET** `/OrdemServico/ObterOficinas?osId=123`

```json
[
  {
    "id": 1,
    "instalacaoId": "INS-001",
    "equipamentoId": "EQP-456",
    "equipamentoDesc": "Rastreador CRX3",
    "veiculoPlaca": "ABC1234"
  }
]
```

### Registrar Instalação

**POST** `/OrdemServico/AdicionarOficina`

```json
{
  "empresaId": 1,
  "osId": 123,
  "tipoVeic": 1,
  "idAparelho": "EQP-456",
  "idVeiculo": "VEI-001",
  "rastreadorId": 501,
  "placaVeiculo": "ABC1234",
  "nomeVeiculo": "Fiat Uno",
  "trocaOficinaAntigaId": null,
  "tipo": 1
}
```

**Resposta:**
```json
{ "status": true, "message": "Instalado com sucesso" }
```

### Registrar Desinstalação

**POST** `/OrdemServico/DesinstalarOficina`

```json
{
  "empresaId": 1,
  "osId": 123,
  "ras_ins_id": "INS-001",
  "idAparelho": "EQP-456",
  "idVeiculo": "VEI-001",
  "rastreadorId": 501,
  "placaVeiculo": "ABC1234",
  "nomeVeiculo": "Fiat Uno",
  "tipo": 1,
  "veiculoId": 10
}
```

---

## Fluxo típico de uma OS

```
1. Criar OS básica
   POST /OrdemServico/SalvarOrdemServicoBasica
   → Obtém ordemServicoId

2. Vincular técnico
   POST /OrdemServico/SalvarTecnicoOrdemServico

3. Agendar técnico
   POST /OrdemServico/AgendarTecnico

4. Adicionar materiais
   POST /OrdemServico/SalvarMaterialOrdemServico

5. (Campo) Registrar instalação
   POST /OrdemServico/AdicionarOficina

6. Atualizar checklist
   PUT /OrdemServico/AtualizarStatusCheckList

7. Finalizar OS (mudar status via SalvarOrdemServico com novo situacaoId)
```
