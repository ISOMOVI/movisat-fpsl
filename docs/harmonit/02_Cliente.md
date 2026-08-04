# Harmonit — API de Clientes

> **Auth:** `Authorization: Bearer TOKEN`

---

## Endpoints

| Método   | Rota                                        | Ação                              |
|----------|---------------------------------------------|-----------------------------------|
| GET      | `/ObterClientes`                            | Listar clientes (paginado)        |
| GET      | `/ObterCliente`                             | Buscar por ID                     |
| GET      | `/ObterClientePorCpfCnpj`                   | Buscar por CPF/CNPJ               |
| GET      | `/ObterClientePeloCelular`                  | Buscar por celular (DDI+DDD+nº)   |
| GET      | `/ObterSituacaoCliente`                     | Listar situações disponíveis      |
| POST     | `/Cliente/CadastrarOuAtualizar`             | Criar ou atualizar cliente        |
| GET      | `/Cliente/ObterZonasParticoes`              | Listar zonas/partições do cliente |
| POST     | `/Cliente/CadastrarOuAtualizarZonasParticoes` | Salvar zona/partição             |
| DELETE   | `/Cliente/RemoverZonaParticao`              | Remover zona/partição             |

---

## 1. Listar Clientes

**GET** `/ObterClientes`

### Query Params

| Campo          | Tipo    | Descrição                               |
|----------------|---------|-----------------------------------------|
| `skip`         | integer | Offset para paginação                   |
| `take`         | integer | Limite de registros retornados          |
| `search`       | string  | Filtro de texto (nome, CPF/CNPJ, etc.) |
| `somenteAtivos`| boolean | `true` para retornar apenas ativos      |
| `tipoPessoa`   | enum    | Filtro por tipo de pessoa               |

```
GET /ObterClientes?skip=0&take=20&search=João&somenteAtivos=true
```

---

## 2. Buscar Cliente por ID

**GET** `/ObterCliente?Id=101`

| Campo | Tipo    | Descrição       |
|-------|---------|-----------------|
| `Id`  | integer | ID do cliente   |

---

## 3. Buscar por CPF/CNPJ

**GET** `/ObterClientePorCpfCnpj?CpfCnpj=12345678901`

| Campo     | Tipo   | Descrição              |
|-----------|--------|------------------------|
| `CpfCnpj` | string | CPF ou CNPJ do cliente |

---

## 4. Buscar por Celular

**GET** `/ObterClientePeloCelular`

Retorna o ID e CPF/CNPJ do cliente com base no número de celular.

| Campo     | Tipo   | Obrigatório | Descrição                                   |
|-----------|--------|-------------|---------------------------------------------|
| `ddi`     | string | ✅          | DDI (ex: `55` para Brasil)                  |
| `ddd`     | string | ✅          | DDD (ex: `11` para São Paulo)               |
| `celular` | string | ✅          | Número sem DDI/DDD (apenas dígitos)         |

```
GET /ObterClientePeloCelular?ddi=55&ddd=11&celular=987654321
```

**Resposta 200:**
```json
{
  "data": {
    "id": 101,
    "cpfCnpj": "123.456.789-00"
  },
  "errorMessage": null,
  "message": null
}
```

---

## 5. Listar Situações do Cliente

**GET** `/ObterSituacaoCliente`

Retorna todos os possíveis status de um cliente (lookup).

**Resposta:**
```json
{
  "data": [
    { "id": 1, "descricao": "Ativo" },
    { "id": 2, "descricao": "Inadimplente" },
    { "id": 3, "descricao": "Inativo" }
  ]
}
```

---

## 6. Cadastrar ou Atualizar Cliente

**POST** `/Cliente/CadastrarOuAtualizar`

Se `id` for informado e existir, **atualiza**. Se `id` for `0` ou omitido, **cria**.

### Body (JSON)

```json
{
  "id": 0,
  "cnpj_cpf": "123.456.789-00",
  "pessoa": "Fisica",
  "rg": "12.345.678-9",
  "im": "",
  "ie": "",
  "nome": "João da Silva",
  "nomeFantasia": "João",
  "codigo": "CLI-001",
  "situacaoClienteId": 1,
  "dataCadastro": "2024-01-15T00:00:00",
  "enderecoPrincipal": {
    "logradouro": "Rua das Flores",
    "numero": "123",
    "complemento": "Apto 4",
    "bairro": "Centro",
    "cidade": "São Paulo",
    "uf": "SP",
    "cep": "01000-000"
  },
  "contatoPrincipal": {
    "nome": "João da Silva",
    "email": "joao@email.com",
    "telefone": "(11) 98765-4321",
    "celular": "(11) 99999-9999"
  }
}
```

### Campos

| Campo             | Tipo    | Descrição                                  |
|-------------------|---------|--------------------------------------------|
| `id`              | integer | `0` para criar, ID existente para atualizar|
| `cnpj_cpf`        | string  | CPF ou CNPJ                                |
| `pessoa`          | enum    | `"Fisica"` ou `"Juridica"`                 |
| `rg`              | string  | RG (pessoa física)                         |
| `im`              | string  | Inscrição Municipal                        |
| `ie`              | string  | Inscrição Estadual                         |
| `nome`            | string  | Nome ou Razão Social                       |
| `nomeFantasia`    | string  | Nome fantasia                              |
| `codigo`          | string  | Código interno do cliente                  |
| `situacaoClienteId`| integer| ID da situação (obter via `/ObterSituacaoCliente`) |
| `dataCadastro`    | string  | Data de cadastro (ISO 8601)                |
| `enderecoPrincipal`| object | Endereço principal                         |
| `contatoPrincipal`| object  | Contato principal                          |

**Resposta 200:** retorna `object` (confirmar estrutura em teste real).

---

## 7. Zonas e Partições

Zonas e partições são sub-unidades de um cliente (ex: setores, áreas monitoradas).

### Listar zonas do cliente

**GET** `/Cliente/ObterZonasParticoes?contatoId=101`

**Resposta:**
```json
[
  { "id": 1, "codigo": "Z01", "descricao": "Área Norte" },
  { "id": 2, "codigo": "Z02", "descricao": "Área Sul" }
]
```

### Salvar zona/partição

**POST** `/Cliente/CadastrarOuAtualizarZonasParticoes`

```json
{
  "id": 0,
  "codigo": "Z03",
  "descricao": "Área Leste",
  "empresaId": 1,
  "parceiroId": 101
}
```

### Remover zona/partição

**DELETE** `/Cliente/RemoverZonaParticao?zonaParticaoId=3`
