# API de Rastreadores

> **Rota base:** `/Rastreadores/`  
> **Autenticação:** `?key=SUA_CHAVE_API` em todas as requisições

---

## Endpoints

| Método | Rota                             | Ação                  |
|--------|----------------------------------|-----------------------|
| POST   | `/Rastreadores/Cadastro`         | Cadastrar rastreador  |
| GET    | `/Rastreadores/Consultar`        | Consultar rastreadores|
| POST   | `/Rastreadores/Atualizar`        | Atualizar rastreador  |
| POST   | `/Rastreadores/Excluir`          | Excluir rastreador    |

---

## 1. Cadastrar Rastreador

**POST** `/Rastreadores/Cadastro?key=SUA_CHAVE_API`

Cadastra um novo rastreador. O endpoint é flexível e permite **vincular ou criar automaticamente** fornecedores e SIM cards.

### Body (JSON)

```json
{
  "numeroSerie": "9876543210987",
  "lote": "LOTE-2024-ABR",
  "notaFiscal": "NF-98765",
  "valorPago": 350.50,
  "modelo": {
    "descricao": "CRX3"
  },
  "tipo": {
    "descricao": "Veiculo"
  },
  "situacao": {
    "id": 2
  },
  "fornecedor": {
    "cnpjcpf": "11.222.333/0001-44",
    "razaoSocial": "Fornecedor de Rastreadores S/A"
  },
  "simCard": {
    "iccId": "89559988776655443322"
  }
}
```

### Campos

| Campo          | Tipo   | Obrigatório | Descrição                                                |
|----------------|--------|-------------|----------------------------------------------------------|
| `numeroSerie`  | string | ✅          | Número de série único do rastreador                      |
| `modelo`       | object | ✅          | Modelo do rastreador (`{ "descricao": "CRX3" }`) — **obrigatório confirmado em teste real** |
| `lote`         | string | ❌          | Lote de compra                                           |
| `notaFiscal`   | string | ❌          | Número da nota fiscal de compra                          |
| `valorPago`    | float  | ❌          | Valor pago pelo equipamento                              |
| `tipo`         | object | ❌          | Tipo do rastreador (`{ "descricao": "Veiculo" }`)        |
| `situacao`     | object | ❌          | Situação (`{ "id": 2 }` ou `{ "descricao": "Estoque" }`) |
| `fornecedor`   | object | ❌          | Dados do fornecedor (ver abaixo)                         |
| `simCard`      | object | ❌          | Associação ao SIM Card pelo `iccId` ou `id`              |

> **Nota:** `modelo` não aparecia como obrigatório na documentação original, mas testes reais confirmam que a API retorna 400 sem ele. Sempre incluir. O endpoint composto `POST /Veiculos/Cadastro` não exige `modelo` ao referenciar um rastreador existente pelo serial.

### Comportamentos automáticos do Cadastro

- **Fornecedor:** Se `fornecedor.cnpjcpf` for informado, a API busca o fornecedor e vincula. Se não existir, **cria automaticamente** com os dados fornecidos.
- **SIM Card:** Se `simCard.iccId` for informado, a API localiza o chip existente e vincula ao rastreador.
- **Ativação automática:** O SIM Card é ativado automaticamente ao ser associado ao rastreador, se aplicável.

### Resposta de Sucesso (201)

```json
{
  "status": "success",
  "data": {
    "id": 501,
    "numeroSerie": "9876543210987",
    "simcard_id": 150,
    "data_cadastro": "2024-05-22T09:15:00"
  }
}
```

### Erro 400 — Campo obrigatório ausente

```json
{
  "status": "error",
  "error": {
    "code": 400,
    "message": "O numeroSerie é obrigatório.",
    "details": [
      { "field": "numeroSerie", "issue": "Campo obrigatório" }
    ]
  }
}
```

---

## 2. Consultar Rastreadores

**GET** `/Rastreadores/Consultar?key=SUA_CHAVE_API`

Retorna rastreadores com filtros opcionais. Sem filtros, retorna todos os rastreadores da empresa.

### Parâmetros de Query

| Campo         | Tipo   | Obrigatório | Descrição                              |
|---------------|--------|-------------|----------------------------------------|
| `id`          | int    | ❌          | Filtrar por ID do rastreador           |
| `numeroSerie` | string | ❌          | Filtrar por número de série            |

### Exemplos de URL

```
GET /Rastreadores/Consultar?key=SUA_CHAVE_API
GET /Rastreadores/Consultar?key=SUA_CHAVE_API&id=501
GET /Rastreadores/Consultar?key=SUA_CHAVE_API&numeroSerie=987654
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "rastreadores": [
      {
        "id": 501,
        "numeroSerie": "9876543210987",
        "lote": "LOTE-2024-ABR",
        "notaFiscal": "NF-98765",
        "firmware": "v2.1.3",
        "data_cadastro": "2024-05-22T09:15:00",
        "modelo": "CRX3",
        "situacao": "Estoque",
        "tipo": "Veiculo",
        "simcard": {
          "id": 150,
          "iccId": "89559988776655443322",
          "numero": 5511912345678
        },
        "fornecedor": {
          "id": 35,
          "nome": "Fornecedor de Rastreadores S/A"
        }
      }
    ],
    "total": 1,
    "filtros": {
      "id": 501,
      "numeroSerie": null
    }
  }
}
```

---

## 3. Atualizar Rastreador

**POST** `/Rastreadores/Atualizar?key=SUA_CHAVE_API`

Atualiza dados de um rastreador existente. Apenas os campos enviados serão alterados.

### Campos de Identificação (um obrigatório)

| Campo         | Tipo   | Descrição                  |
|---------------|--------|----------------------------|
| `id`          | int    | ID do rastreador           |
| `numeroSerie` | string | Número de série            |

### Body (JSON)

```json
{
  "id": 501,
  "lote": "LOTE-2024-ABR-UPD",
  "valorPago": 375.00,
  "situacao": {
    "descricao": "Instalado"
  },
  "simCard": {
    "id": 155
  }
}
```

> Além do identificador, todos os campos do Cadastro são opcionais e podem ser enviados para atualização.

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 501,
    "numeroSerie": "9876543210987",
    "data_atualizacao": "2024-05-22T10:00:00"
  }
}
```

---

## 4. Excluir Rastreador

**POST** `/Rastreadores/Excluir?key=SUA_CHAVE_API`

### Body — informar um dos dois

```json
{ "id": 501 }
```
```json
{ "numeroSerie": "9876543210987" }
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 501,
    "numeroSerie": "9876543210987",
    "data_exclusao": "2024-05-22T11:30:00"
  }
}
```

---

## Códigos de Erro

| Código | Descrição                                       |
|--------|-------------------------------------------------|
| 400    | Bad Request — `numeroSerie` ausente ou inválido |
| 401    | Unauthorized — Chave de acesso inválida         |
| 404    | Not Found — Rastreador não encontrado           |
| 409    | Conflict — Número de série duplicado            |
| 500    | Internal Server Error — Erro interno            |

### Erro 401 — Chave inválida

```json
{
  "status": "error",
  "error": {
    "code": 401,
    "message": "Chave de acesso inválida",
    "details": [
      { "field": "key", "issue": "Chave de acesso inválida" }
    ]
  }
}
```
