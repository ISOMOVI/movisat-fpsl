# Harmonit — API de Produtos e Serviços

> **Auth:** `Authorization: Bearer TOKEN`

---

## Endpoints

| Método | Rota                                     | Ação                           |
|--------|------------------------------------------|--------------------------------|
| GET    | `/Produto/ObterProdutos`                 | Listar produtos (paginado)     |
| GET    | `/Produto/ObterProduto`                  | Buscar produto por ID          |
| POST   | `/Produto/CadastrarOuAtualizarProduto`   | Criar ou atualizar produto     |
| DELETE | `/Produto/ExcluirProdutoServico`         | Excluir produto ou serviço     |
| GET    | `/Produto/ObterServicos`                 | Listar serviços (paginado)     |
| GET    | `/Produto/ObterServico`                  | Buscar serviço por ID          |
| POST   | `/Produto/CadastrarOuAtualizarServico`   | Criar ou atualizar serviço     |
| POST   | `/Produto/SalvarChecklist`               | Salvar item de checklist       |
| DELETE | `/Produto/RemoverCheckList`              | Remover item de checklist      |

---

## 1. Produtos

### Listar Produtos

**GET** `/Produto/ObterProdutos`

| Campo          | Tipo    | Descrição                         |
|----------------|---------|-----------------------------------|
| `skip`         | integer | Offset                            |
| `take`         | integer | Limite                            |
| `search`       | string  | Filtro por nome/código            |
| `somenteAtivos`| boolean | Apenas produtos ativos            |

**Resposta:**
```json
{
  "data": {
    "totalRegistros": 50,
    "data": [
      {
        "id": 1,
        "codigo": "PROD-001",
        "descricao": "Rastreador CRX3",
        "descricaoResumida": "CRX3"
      }
    ]
  }
}
```

### Buscar Produto por ID

**GET** `/Produto/ObterProduto?produtoId=1`

**Resposta (ProdutoApiDataViewModel):**
```json
{
  "data": {
    "id": 1,
    "codigo": "PROD-001",
    "descricao": "Rastreador CRX3",
    "descricaoResumida": "CRX3",
    "codigoBarras": "7890123456789",
    "tipo": 1,
    "situacao": 1,
    "grupoId": 2,
    "marcaId": 3,
    "unidadeMedidaId": 1,
    "pesoBruto": 0.5,
    "pesoLiquido": 0.45
  }
}
```

### Criar/Atualizar Produto

**POST** `/Produto/CadastrarOuAtualizarProduto`

```json
{
  "id": 0,
  "codigo": "PROD-002",
  "descricao": "Rastreador GV75",
  "descricaoResumida": "GV75",
  "codigoBarras": "7890000000001",
  "tipo": 1,
  "situacao": 1,
  "grupoId": 2,
  "marcaId": 3,
  "unidadeMedidaId": 1,
  "centroId": null,
  "categoriaId": null,
  "pesoBruto": 0.6,
  "pesoLiquido": 0.55,
  "referencia": "GV75-2024"
}
```

| Campo              | Tipo    | Descrição                                    |
|--------------------|---------|----------------------------------------------|
| `id`               | integer | `0` para criar, ID para atualizar            |
| `codigo`           | string  | Código interno do produto                    |
| `descricao`        | string  | Nome completo                                |
| `descricaoResumida`| string  | Nome curto                                   |
| `codigoBarras`     | string  | EAN/código de barras                         |
| `tipo`             | enum    | Tipo do produto (enum)                       |
| `situacao`         | enum    | `1` = Ativo \| `2` = Inativo                |
| `grupoId`          | integer | ID do grupo de produtos                      |
| `marcaId`          | integer | ID da marca                                  |
| `unidadeMedidaId`  | integer | ID da unidade de medida                      |
| `centroId`         | integer | Centro de custo                              |
| `categoriaId`      | integer | Categoria do produto                         |
| `pesoBruto`        | decimal | Peso bruto em kg                             |
| `pesoLiquido`      | decimal | Peso líquido em kg                           |
| `referencia`       | string  | Referência interna                           |

### Excluir Produto/Serviço

**DELETE** `/Produto/ExcluirProdutoServico?produtoServicoId=1`

---

## 2. Serviços

### Listar Serviços

**GET** `/Produto/ObterServicos`

Mesmos parâmetros de paginação que `/ObterProdutos`.

### Buscar Serviço por ID

**GET** `/Produto/ObterServico?servicoId=5`

**Resposta (ServicoApiDataViewModel):**
```json
{
  "data": {
    "id": 5,
    "codigo": "SERV-001",
    "descricao": "Instalação de Rastreador",
    "descricaoResumida": "Instalação",
    "situacao": 1,
    "checkList": [
      { "id": 1, "sequencia": 1, "descricao": "Verificar fiação", "obrigatorio": true }
    ]
  }
}
```

### Criar/Atualizar Serviço

**POST** `/Produto/CadastrarOuAtualizarServico`

```json
{
  "id": 0,
  "codigo": "SERV-002",
  "descricao": "Manutenção Preventiva",
  "descricaoResumida": "Manutenção",
  "situacao": 1,
  "grupoId": 1,
  "unidadeMedidaId": 1,
  "centroId": null,
  "categoriaId": null,
  "checkList": [
    { "id": 0, "sequencia": 1, "descricao": "Verificar conexões", "obrigatorio": true }
  ]
}
```

---

## 3. Checklist de Serviço

O checklist é uma lista de tarefas obrigatórias ou opcionais associadas a um serviço.

### Salvar Item

**POST** `/Produto/SalvarChecklist`

```json
{
  "id": 0,
  "sequencia": 1,
  "descricao": "Testar GPS após instalação",
  "obrigatorio": true,
  "servicoId": 5
}
```

| Campo       | Tipo    | Descrição                              |
|-------------|---------|----------------------------------------|
| `id`        | integer | `0` para criar, ID para atualizar      |
| `sequencia` | integer | Ordem de exibição do item              |
| `descricao` | string  | Texto do item de checklist             |
| `obrigatorio`| boolean| `true` = obrigatório para concluir a OS|
| `servicoId` | integer | ID do serviço pai                      |

### Remover Item

**DELETE** `/Produto/RemoverCheckList?checkListId=1`
