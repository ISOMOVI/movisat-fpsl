# API de Clientes

> **Rota base:** `/Clientes/`  
> **Autenticação:** `?key=SUA_CHAVE_API` em todas as requisições

---

## Endpoints

| Método | Rota                         | Ação               |
|--------|------------------------------|--------------------|
| POST   | `/Clientes/Cadastro`         | Cadastrar cliente  |
| GET    | `/Clientes/Consultar`        | Consultar clientes |
| POST   | `/Clientes/Atualizar`        | Atualizar cliente  |
| POST   | `/Clientes/Excluir`          | Excluir cliente    |

---

## 1. Cadastrar Cliente

**POST** `/Clientes/Cadastro?key=SUA_CHAVE_API`

Cria um novo registro de cliente associado à sua empresa.

### Body (JSON)

```json
{
  "cnpjcpf": "123.456.789-00",
  "razaoSocial": "João da Silva",
  "nomeFantasia": "João",
  "contato": "Maria Souza",
  "telefone": "(11) 98765-4321",
  "emailCobranca": "cobranca.joao@email.com",
  "tipoCliente": "Fisica",
  "situacao": "Adimplente",
  "plano": "Plano Básico",
  "endereco": "Rua das Flores",
  "numeroEnd": "123",
  "bairro": "Centro",
  "cep": "01000-000",
  "obs": "Cliente prefere contato via WhatsApp."
}
```

### Campos

| Campo           | Tipo   | Obrigatório | Descrição                                          |
|-----------------|--------|-------------|----------------------------------------------------|
| `cnpjcpf`       | string | ✅          | CPF (Pessoa Física) ou CNPJ (Pessoa Jurídica)      |
| `razaoSocial`   | string | ✅          | Nome completo ou razão social                      |
| `nomeFantasia`  | string | ❌          | Nome fantasia ou apelido                           |
| `contato`       | string | ❌          | Nome do contato responsável                        |
| `telefone`      | string | ❌          | Telefone principal                                 |
| `emailCobranca` | string | ❌          | E-mail para envio de cobranças                     |
| `tipoCliente`   | string | ❌          | Tipo: `Fisica`, `Juridica` ou `NaoInformado`       |
| `situacao`      | string | ❌          | Situação financeira do cliente (ver tabela abaixo) |
| `plano`         | string | ❌          | Nome do plano — buscado automaticamente pelo nome  |
| `endereco`      | string | ❌          | Logradouro                                         |
| `numeroEnd`     | string | ❌          | Número do endereço                                 |
| `bairro`        | string | ❌          | Bairro                                             |
| `cep`           | string | ❌          | CEP                                                |
| `obs`           | string | ❌          | Observações internas                               |

### Comportamentos automáticos do Cadastro

- O campo `plano` aceita o **nome exato** (case-sensitive) do plano. A API busca e associa automaticamente.
- Se o plano não for encontrado, o cliente é criado **sem plano associado**.

### `tipoCliente` — Valores aceitos

| Valor          | Descrição                             |
|----------------|---------------------------------------|
| `Fisica`       | Pessoa Física (CPF)                   |
| `Juridica`     | Pessoa Jurídica (CNPJ)                |
| `NaoInformado` | Padrão, caso não seja especificado    |

### `situacao` — Valores aceitos

| Valor          | Descrição                                    |
|----------------|----------------------------------------------|
| `Adimplente`   | Pagamentos em dia (padrão no cadastro)        |
| `Inadimplente` | Possui pendências financeiras                 |
| `Bloqueado`    | Serviços bloqueados por falta de pagamento    |
| `Teste`        | Cliente em período de teste                   |
| `Negociacao`   | Em negociação de dívidas                      |
| `Cortesia`     | Serviço oferecido sem custo                   |

> A API aceita tanto a string (`"Adimplente"`) quanto o ID numérico para os campos de situação e tipo.

### Resposta de Sucesso (201)

```json
{
  "status": "success",
  "data": {
    "id": 101,
    "cnpjcpf": "123.456.789-00",
    "razaoSocial": "João da Silva",
    "data_cadastro": "2023-10-27T10:30:00"
  }
}
```

---

## 2. Consultar Clientes

**GET** `/Clientes/Consultar?key=SUA_CHAVE_API`

Consulta clientes com filtros opcionais. Sem filtros, retorna todos os clientes da empresa.

### Lógica de busca (priorizada)

1. **Busca por ID** (Prioritária) — se `cliente_id` for informado, retorna diretamente.
2. **Busca por CNPJ/CPF** — se `cnpjcpf` for informado, filtra ignorando formatação.
3. **Buscar Todos** — sem filtros, retorna todos os clientes.

### Parâmetros de Query

| Campo        | Tipo   | Obrigatório | Descrição                                            |
|--------------|--------|-------------|------------------------------------------------------|
| `cliente_id` | int    | ❌          | Filtrar por ID                                       |
| `cnpjcpf`    | string | ❌          | CNPJ ou CPF (a busca ignora formatação)             |

### Exemplos de URL

```
GET /Clientes/Consultar?key=SUA_CHAVE_API
GET /Clientes/Consultar?key=SUA_CHAVE_API&cliente_id=101
GET /Clientes/Consultar?key=SUA_CHAVE_API&cnpjcpf=12345678901
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "clientes": [
      {
        "id": 101,
        "cnpjcpf": "123.456.789-00",
        "razaoSocial": "João da Silva",
        "nomeFantasia": "João",
        "contato": "Maria Souza",
        "telefone": "(11) 98765-4321",
        "emailCobranca": "cobranca.joao@email.com",
        "tipoCliente": "Fisica",
        "situacao": "Adimplente",
        "plano": "Plano Básico",
        "endereco": {
          "logradouro": "Rua das Flores",
          "numero": "123",
          "bairro": "Centro",
          "cep": "01000-000"
        }
      }
    ],
    "total": 1
  }
}
```

---

## 3. Atualizar Cliente

**POST** `/Clientes/Atualizar?key=SUA_CHAVE_API`

Atualiza dados de um cliente existente. Apenas os campos enviados serão alterados.

### Lógica de busca (priorizada)

1. **Atualização por ID** — se `cliente_id` for informado no body.
2. **Atualização por CNPJ/CPF** — se `cnpjcpf` for informado no body.

> É obrigatório informar **pelo menos um** dos identificadores.

### Body com identificação por ID

```json
{
  "cliente_id": 101,
  "nomeFantasia": "Empresa XPTO",
  "contato": "Ana Paula",
  "telefone": "(11) 98877-6655",
  "situacao": "Inadimplente"
}
```

### Body com identificação por CNPJ/CPF

```json
{
  "cnpjcpf": "12.345.678/0001-99",
  "endereco": "Avenida Principal, 789",
  "bairro": "Jardins",
  "cep": "01415-000",
  "obs": "Cliente solicitou mudança de plano."
}
```

### Campos para Atualização (todos opcionais, exceto o identificador)

Todos os campos do Cadastro são aceitos na Atualização. Envie apenas os que deseja modificar.

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 101,
    "message": "Cliente atualizado com sucesso.",
    "metodo_busca": "ID"
  }
}
```

### Erros específicos

**400 — Sem identificador:**
```json
{
  "status": "error",
  "error": {
    "code": 400,
    "message": "Parâmetros de identificação não informados",
    "details": [
      { "field": "body", "issue": "É obrigatório informar 'cliente_id' ou 'cnpjcpf'." }
    ]
  }
}
```

**404 — Cliente não encontrado:**
```json
{
  "status": "error",
  "error": {
    "code": 404,
    "message": "Cliente não encontrado",
    "details": [
      { "field": "ID", "issue": "Cliente não encontrado com os critérios fornecidos." }
    ]
  }
}
```

---

## 4. Excluir Cliente

**POST** `/Clientes/Excluir?key=SUA_CHAVE_API`

### Body — informar um dos dois

```json
{ "cliente_id": 101 }
```
```json
{ "cnpjcpf": "12.345.678/0001-99" }
```

> **Campo:** `CNPJ ou CPF do cliente que você deseja excluir.`

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 101,
    "razaoSocial": "Empresa Exemplo LTDA",
    "data_exclusao": "2023-10-28T14:00:00",
    "metodo_busca": "ID"
  }
}
```

---

## Códigos de Status HTTP

### Sucesso

| Código     | Status    | Descrição                          | Endpoints Comuns              |
|------------|-----------|------------------------------------|-------------------------------|
| `200 OK`   | OK        | A operação foi bem-sucedida.       | Consultar, Atualizar, Excluir |
| `201 Created` | Created| O recurso foi criado com sucesso.  | Cadastro                      |

### Erros do Cliente (4xx)

| Código              | Status       | Descrição                         | Cenários Comuns                                             |
|---------------------|--------------|-----------------------------------|-------------------------------------------------------------|
| `400 Bad Request`   | Bad Request  | A requisição é inválida.          | Campos obrigatórios ausentes, JSON mal formatado            |
| `401 Unauthorized`  | Unauthorized | Autenticação falhou.              | A `key` está ausente, inválida ou expirou                   |
| `404 Not Found`     | Not Found    | O recurso não foi encontrado.     | Tentar atualizar/excluir um `cliente_id` inexistente        |
| `409 Conflict`      | Conflict     | Conflito de dados.                | Cadastrar CNPJ/CPF já existente                             |

### Erros do Servidor (5xx)

| Código                   | Status                | Descrição                        |
|--------------------------|-----------------------|----------------------------------|
| `500 Internal Server Error` | Internal Server Error | Erro interno. Contate o suporte. |
