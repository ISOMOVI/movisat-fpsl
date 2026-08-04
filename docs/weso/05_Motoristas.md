# API de Motoristas

> **Rota base:** `/Motorista/`  
> **Autenticação:** `?key=SUA_CHAVE_API` em todas as requisições

---

## Endpoints

| Método | Rota                        | Ação                  |
|--------|-----------------------------|-----------------------|
| POST   | `/Motorista/Cadastro`       | Cadastrar motorista   |
| GET    | `/Motorista/Consultar`      | Consultar motoristas  |
| POST   | `/Motorista/Atualizar`      | Atualizar motorista   |
| POST   | `/Motorista/Excluir`        | Excluir motorista     |

---

## 1. Cadastrar Motorista

**POST** `/Motorista/Cadastro?key=SUA_CHAVE_API`

Cria um novo motorista com validação automática de cliente e processamento inteligente de municípios.

### Body (JSON)

```json
{
  "motorista": {
    "nome": "João Silva",
    "cpf": "12345678901",
    "rg": "12345678",
    "cracha": "CR001",
    "matricula": "MAT001",
    "cnhCategoria": "B",
    "cnhRegistro": 12345678901,
    "cnhValidade": "2025-12-31T00:00:00",
    "exameToxicologicoValidade": "2024-12-31T00:00:00",
    "dataNascimento": "1980-01-01T00:00:00",
    "dataAdmissao": "2023-01-01T00:00:00",
    "endereco": "Rua das Flores, 123",
    "cep": "01234-567",
    "telCelular1": "(11) 99999-9999",
    "telCelular2": "(11) 88888-8888",
    "telResidencial": "(11) 77777-7777",
    "observacoes": "Observações sobre o motorista",
    "municipio": "São Paulo",
    "cliente": {
      "id": 1,
      "cnpjcpf": "12345678000199",
      "razaoSocial": "Empresa Exemplo LTDA",
      "nomeFantasia": "Empresa Exemplo",
      "tipoCliente": "Juridica",
      "plano": "Plano Premium",
      "situacao": "adimplente",
      "email": "contato@empresa.com",
      "emailCobranca": "cobranca@empresa.com",
      "contato": "João da Silva",
      "endereco": "Rua da Empresa, 456",
      "telefone": "(11) 3333-3333",
      "telefone2": "(11) 4444-4444",
      "cep": "01234-567",
      "estado": "SP",
      "municipio": "São Paulo",
      "complemento": "Sala 101",
      "bairro": "Centro",
      "numeroEnd": "456",
      "obs": "Observações sobre o cliente",
      "senhaBloqueador": "123456"
    },
    "identificador": {
      "tipoIdentif": "iButton",
      "numero": "456",
      "apelido": "qwe"
    }
  }
}
```

### Campos do objeto `motorista`

| Campo                        | Tipo    | Obrigatório | Descrição                              |
|------------------------------|---------|-------------|----------------------------------------|
| `nome`                       | string  | ✅          | Nome completo do motorista             |
| `cpf`                        | string  | ✅          | CPF (apenas números)                   |
| `rg`                         | string  | ❌          | RG                                     |
| `cracha`                     | string  | ❌          | Código do crachá                       |
| `matricula`                  | string  | ❌          | Matrícula interna                      |
| `cnhCategoria`               | string  | ❌          | Categoria da CNH (A, B, C, D, E)       |
| `cnhRegistro`                | long    | ❌          | Número de registro da CNH              |
| `cnhValidade`                | datetime| ❌          | Data de validade da CNH                |
| `exameToxicologicoValidade`  | datetime| ❌          | Data de validade do exame toxicológico |
| `dataNascimento`             | datetime| ❌          | Data de nascimento                     |
| `dataAdmissao`               | datetime| ❌          | Data de admissão                       |
| `endereco`                   | string  | ❌          | Endereço completo                      |
| `cep`                        | string  | ❌          | CEP                                    |
| `telCelular1`                | string  | ❌          | Celular principal                      |
| `telCelular2`                | string  | ❌          | Celular secundário                     |
| `telResidencial`             | string  | ❌          | Telefone residencial                   |
| `observacoes`                | string  | ❌          | Observações internas                   |
| `municipio`                  | string  | ❌          | Nome do município (busca automática)   |
| `cliente`                    | object  | ❌          | Dados do cliente vinculado             |
| `identificador`              | object  | ❌          | Identificador físico (iButton, cartão) |

### `cnhCategoria` — Categorias CNH

| Valor | Descrição         |
|-------|-------------------|
| `A`   | Motocicletas      |
| `B`   | Automóveis        |
| `C`   | Caminhões         |
| `D`   | Ônibus            |
| `E`   | Combinação (carreta/reboque) |
| `AB`  | Categorias A + B  |
| `AC`  | Categorias A + C  |
| `AD`  | Categorias A + D  |
| `AE`  | Categorias A + E  |

### `identificador` — Objeto de identificação

| Campo        | Tipo   | Obrigatório | Descrição                                                              |
|--------------|--------|-------------|------------------------------------------------------------------------|
| `tipoIdentif`| string | ✅          | Tipo do identificador: `"iButton"`, `"Cartao"`, etc.                   |
| `numero`     | string | ✅          | Número/código do identificador                                         |
| `apelido`    | string | ❌          | Apelido/nome amigável para o identificador                             |

### Comportamentos automáticos do Cadastro

- **Município:** O campo `municipio` aceita o nome da cidade. A API busca automaticamente o município no banco. Retorna `404` se não encontrado.
- **Cliente:** Se `cliente.id` for informado, vincula diretamente. Se informado `cnpjcpf` sem ID, busca e vincula. Se não existir, **cria automaticamente** com os dados fornecidos.
- **Identificador:** Se informado, cria e vincula automaticamente ao motorista.

### Exemplos de cenários de cadastro

**Cenário 1 — Motorista com cliente existente por CPF:**
```json
{
  "motorista": {
    "nome": "Maria Santos",
    "cpf": "98765432100",
    "municipio": "Rio de Janeiro",
    "cliente": {
      "cpf": "12345678900"
    }
  }
}
```

**Cenário 2 — Motorista com criação automática de cliente:**
```json
{
  "motorista": {
    "nome": "Carlos Oliveira",
    "cpf": "11122233344",
    "cnhCategoria": "D",
    "municipio": "Belo Horizonte",
    "cliente": {
      "cnpjcpf": "11222333000144",
      "razaoSocial": "Transportes BH LTDA",
      "nomeFantasia": "BH Transportes",
      "tipoCliente": "Juridica",
      "plano": "Plano Empresarial",
      "situacao": "adimplente",
      "email": "contato@bhtransportes.com"
    }
  }
}
```

### Resposta de Sucesso (201)

```json
{
  "status": "success",
  "data": {
    "id": 123,
    "nome": "João Silva",
    "cpf": "12345678901",
    "cliente_id": 456,
    "data_cadastro": "2024-01-15T10:30:00",
    "identificador": {
      "id": 26586,
      "tipo_identif": "iButton",
      "cliente_id": 456,
      "motorista_id": 123,
      "data_cadastro": "2024-09-21T00:00:00",
      "ativo": true,
      "numero": "456",
      "apelido": "qwe"
    },
    "objetos_processados": {
      "cliente": "Validado",
      "identificador": "Criado"
    }
  }
}
```

### Erros específicos

**400 — Campos obrigatórios ausentes:**
```json
{
  "status": "error",
  "error": {
    "code": 400,
    "message": "Parâmetros obrigatórios não informados ou inválidos",
    "details": [
      { "field": "motorista.nome", "issue": "Campo obrigatório" }
    ]
  }
}
```

**409 — CPF duplicado:**
```json
{
  "status": "error",
  "error": {
    "code": 409,
    "message": "CPF já cadastrado",
    "details": { "cpf": "12345678901" }
  }
}
```

**404 — Município não encontrado:**
```json
{
  "status": "error",
  "error": {
    "code": 404,
    "message": "Município não encontrado",
    "details": { "municipio": "São Paulo" }
  }
}
```

---

## 2. Consultar Motoristas

**GET** `/Motorista/Consultar?key=SUA_CHAVE_API`

Consulta motoristas com filtros opcionais por ID ou CPF.

### Lógica de busca (priorizada)

1. **Busca direta por `motorista_id`** (Alta prioridade)
2. **Busca por CPF** (quando ID não encontrado)
3. **Buscar Todos** — sem filtros

### Parâmetros de Query

| Campo          | Tipo   | Obrigatório | Descrição                             |
|----------------|--------|-------------|---------------------------------------|
| `id`           | int    | ❌          | ID do motorista (busca direta)        |
| `cpf`          | string | ❌          | CPF apenas números                    |

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "motoristas": [
      {
        "id": 123,
        "nome": "João Silva",
        "cpf": "12345678901",
        "rg": "12345678",
        "cracha": "CR001",
        "matricula": "MAT001",
        "cnh_categoria": "B",
        "cnh_registro": 12345678901,
        "cnh_validade": "2025-12-31T00:00:00",
        "exame_toxicologico_validade": "2024-12-31T00:00:00",
        "data_nascimento": "1980-01-01T00:00:00",
        "data_admissao": "2023-01-01T00:00:00",
        "endereco": "Rua das Flores, 123",
        "cep": "01234-567",
        "tel_celular1": "(11) 99999-9999",
        "tel_celular2": "(11) 88888-8888",
        "tel_residencial": "(11) 77777-7777",
        "observacoes": "Observações sobre o motorista",
        "cliente_id": 456,
        "estado_id": 25,
        "municipio_id": 3550308,
        "identificador": {
          "id": 54321,
          "tipo_identif": "iButton",
          "cliente_id": 456,
          "motorista_id": 123,
          "data_cadastro": "2024-09-21T00:00:00",
          "ativo": true,
          "numero": "4560001234",
          "apelido": "qwe"
        }
      }
    ],
    "total": 1,
    "metodo_busca": "ID",
    "filtros": {
      "id": 123,
      "cpf": null
    }
  }
}
```

### Erros específicos

**404 — Nenhum motorista encontrado:**
```json
{
  "status": "error",
  "error": {
    "code": 404,
    "message": "Nenhum motorista encontrado",
    "details": {
      "filtros_aplicados": { "cpf": "12345678901", "nome": null }
    }
  }
}
```

**400 — CPF com caracteres inválidos:**
```json
{
  "status": "error",
  "error": {
    "code": 400,
    "message": "Parâmetros de consulta inválidos",
    "details": [
      { "field": "cpf", "issue": "CPF deve conter apenas números" }
    ]
  }
}
```

---

## 3. Atualizar Motorista

**POST** `/Motorista/Atualizar?key=SUA_CHAVE_API`

Atualiza dados de um motorista existente.

### Campos de Identificação (um obrigatório)

| Campo  | Tipo   | Descrição                                           |
|--------|--------|-----------------------------------------------------|
| `id`   | int    | ID do motorista (**obrigatório se CPF não informado**) |
| `cpf`  | string | CPF do motorista (**obrigatório se ID não informado**) |

### Body (JSON)

```json
{
  "cpf": "12345678901",
  "nome": "João Silva Atualizado",
  "rg": "12345678",
  "cracha": "CR001",
  "matricula": "MAT001",
  "cnhCategoria": "B",
  "cnhRegistro": 12345678901,
  "cnhValidade": "2025-12-31T00:00:00",
  "exameToxicologicoValidade": "2024-12-31T00:00:00",
  "dataNascimento": "1980-01-01T00:00:00",
  "dataAdmissao": "2023-01-01T00:00:00",
  "endereco": "Rua das Flores, 123",
  "cep": "01234-567",
  "telCelular1": "(11) 99999-9999",
  "telCelular2": "(11) 88888-8888",
  "telResidencial": "(11) 77777-7777",
  "observacoes": "Observações atualizadas",
  "cliente_id": 456,
  "municipio": "São Paulo",
  "identificador": {
    "tipoIdentif": "ibutton",
    "numero": "456789",
    "apelido": "qwe"
  }
}
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 123,
    "nome": "João Silva Atualizado",
    "cpf": "12345678901",
    "data_atualizacao": "2024-01-15T10:30:00",
    "metodo_busca": "ID",
    "identificador": {
      "id": 789,
      "tipoIdentif": "ibutton",
      "numero": "456789",
      "apelido": "qwe"
    }
  },
  "objetos_processados": {
    "motorista": "Atualizado",
    "identificador": "Atualizado"
  }
}
```

---

## 4. Excluir Motorista

**POST** `/Motorista/Excluir?key=SUA_CHAVE_API`

### Body — informar um dos dois

```json
{ "id": 123 }
```
```json
{ "cpf": "12345678901" }
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 123,
    "cpf": "12345678901",
    "data_exclusao": "2024-01-15T10:30:00",
    "metodo_busca": "ID"
  }
}
```

### Erros específicos

**404 — Motorista não encontrado:**
```json
{
  "status": "error",
  "error": {
    "code": 404,
    "message": "Motorista não encontrado",
    "details": {
      "id": 999,
      "verificacao_realizada": "2024-01-15T10:30:00Z"
    }
  }
}
```

**400 — Sem identificador:**
```json
{
  "status": "error",
  "error": {
    "code": 400,
    "message": "Dados de entrada inválidos",
    "details": [
      { "field": "id", "issue": "Campo obrigatório não fornecido" }
    ]
  }
}
```

---

## Códigos de Erro

| Código | Descrição                                              |
|--------|--------------------------------------------------------|
| 400    | Bad Request — Campos obrigatórios ausentes ou inválidos|
| 401    | Unauthorized — Chave de acesso inválida                |
| 404    | Not Found — Motorista ou município não encontrado      |
| 409    | Conflict — CPF já cadastrado                           |
| 500    | Internal Server Error — Erro interno                   |
