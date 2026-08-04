# API de Veículos

> **Rota base:** `/Veiculos/`  
> **Autenticação:** `?key=SUA_CHAVE_API` em todas as requisições

---

## Endpoints

| Método | Rota                          | Ação              |
|--------|-------------------------------|-------------------|
| POST   | `/Veiculos/Cadastro`          | Cadastrar veículo |
| GET    | `/Veiculos/Consultar`         | Consultar veículos|
| POST   | `/Veiculos/Atualizar`         | Atualizar veículo |
| POST   | `/Veiculos/Excluir`           | Excluir veículo   |

---

## 1. Cadastrar Veículo

**POST** `/Veiculos/Cadastro?key=SUA_CHAVE_API`

Cadastra um veículo com estrutura completa. Suporta **criação automática** de clientes, rastreadores, SIM cards e complementos em uma única requisição.

### Body (JSON)

```json
{
  "equipamento": {
    "placa": "ABC1234",
    "descricao": "Veículo da empresa",
    "situacao": "instalado",
    "observacoes": "Observações no cliente",
    "observacoesGestor": "Observações do gestor",
    "valorMensalidade": 150.00,
    "cliente": {
      "id": 123,
      "cnpjcpf": "12345678901",
      "razaoSocial": "Empresa LTDA",
      "nomeFantasia": "Empresa",
      "tipoCliente": "Juridica",
      "plano": "Plano Básico",
      "situacao": "adimplente",
      "email": "contato@empresa.com",
      "emailCobranca": "cobranca@empresa.com",
      "contato": "João Silva",
      "endereco": "Rua das Flores, 123",
      "telefone": "(11) 99999-9999",
      "telefone2": "(11) 88888-8888",
      "cep": "01234-567",
      "estado": "SP",
      "municipio": "São Paulo",
      "complemento": "Sala 1",
      "bairro": "Centro",
      "numeroEnd": "123",
      "obs": "Observações do cliente",
      "senhaBloqueador": "123456"
    },
    "rastreador": {
      "id": 456,
      "numeroSerie": "123456789",
      "modelo": "GV75",
      "tipo": "instalado",
      "lote": "LOTE001",
      "grupoEvento": "Grupo A",
      "notaFiscal": "NF123456",
      "valorPago": 500.00,
      "fornecedor": {
        "id": 789,
        "cnpjcpf": "98765432100",
        "razaoSocial": "Fornecedor LTDA"
      },
      "simCard": {
        "id": 101,
        "iccId": "89550000001234567890",
        "numero": 5511999999999,
        "apn": "internet",
        "fornecedor": "Vivo",
        "valorMensalidade": 10.0
      }
    },
    "complemento": {
      "id": 202,
      "chassi": "9BWZZZ377VT004251",
      "cor": "Branco",
      "renavam": "12345678901",
      "anoFab": 2020,
      "anoMod": 2021,
      "tipoEqp": "carro"
    }
  }
}
```

### Campos do objeto `equipamento`

| Campo             | Tipo    | Obrigatório | Descrição                          |
|-------------------|---------|-------------|-------------------------------------|
| `placa`           | string  | ✅          | Placa do veículo                    |
| `descricao`       | string  | ❌          | Descrição/nome do veículo           |
| `situacao`        | string  | ❌          | Situação atual do veículo           |
| `observacoes`     | string  | ❌          | Observações visíveis ao cliente     |
| `observacoesGestor` | string | ❌         | Observações internas do gestor      |
| `valorMensalidade`| float   | ❌          | Valor mensal cobrado                |
| `cliente`         | object  | ❌          | Dados do cliente vinculado          |
| `rastreador`      | object  | ❌          | Dados do rastreador instalado       |
| `complemento`     | object  | ❌          | Dados complementares do veículo     |

### Comportamentos automáticos do Cadastro

- Se `cliente.id` for informado, o cliente existente é vinculado diretamente.
- Se `cliente.cnpjcpf` for informado sem ID, a API busca o cliente e vincula automaticamente.
- Se o cliente não existir, é **criado automaticamente** com os dados fornecidos e vinculado ao plano informado.
- Se `rastreador.id` for informado, o rastreador existente é vinculado.
- Se `rastreador.numeroSerie` for informado sem ID, o rastreador é criado com os dados fornecidos.
- O mesmo comportamento se aplica ao `simCard` e ao `complemento`.

### `tipoEqp` — Tipos de Equipamento

| Código | Descrição                        |
|--------|----------------------------------|
| 1      | Automóvel e camioneta até 3.500kg|
| 2      | Caminhão                         |
| 3      | Camionete                        |
| 4      | Ônibus                           |
| 5      | Motocicleta                      |
| 6      | Trator                           |
| 7      | Barco                            |
| 8      | Carreta                          |
| 9      | Reboque                          |
| 10     | Colheitadeira                    |
| 11     | Bancada                          |
| 20     | Carro                            |
| 21     | Moto                             |
| 22     | Caminhão Caçamba                 |
| 23     | Caminhão Tanque                  |
| 24     | Ambulância                       |
| 25     | Ônibus (alt)                     |
| 26     | Van / Minivan                    |
| 33     | Avião                            |
| 34     | Navio                            |
| 35     | Motor Bomba                      |
| 36     | TV                               |

> A API aceita tanto o ID numérico quanto a descrição (string) para o campo `tipoEqp`.

### Resposta de Sucesso (201)

```json
{
  "status": "success",
  "data": {
    "id": 1,
    "placa": "ABC1234",
    "cliente_id": 123,
    "rastreador_id": 456,
    "simcard_id": 789,
    "complemento_id": 202,
    "data_cadastro": "2024-01-15T10:30:00",
    "objetos_processados": {
      "cliente": "Validado",
      "rastreador": "Criado",
      "simcard": "Criado",
      "complemento": "Criado/Validado"
    }
  }
}
```

---

## 2. Consultar Veículos

**GET** `/Veiculos/Consultar?key=SUA_CHAVE_API`

> ⚠️ **Endpoint com falha confirmada em teste real.** Retorna HTTP 500 (HTML) com qualquer parâmetro — sem filtros, com `placa`, com `veiculo_id` de registros reais. Para verificar existência de uma placa, use `POST /Veiculos/Cadastro` e interprete o erro 409 como "já cadastrada".

Retorna veículos com filtros opcionais. Sem filtros, retorna todos os veículos da empresa.

### Parâmetros de Query

| Campo        | Tipo   | Obrigatório | Descrição                   |
|--------------|--------|-------------|------------------------------|
| `placa`      | string | ❌          | Filtrar por placa específica |
| `veiculo_id` | int    | ❌          | Filtrar por ID específico    |

### Exemplos de URL

```
GET /Veiculos/Consultar?key=SUA_CHAVE_API
GET /Veiculos/Consultar?key=SUA_CHAVE_API&placa=ABC1234
GET /Veiculos/Consultar?key=SUA_CHAVE_API&veiculo_id=1
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "veiculos": [
      {
        "id": 1,
        "placa": "ABC1234",
        "descricao": "Fiat Palio 1.0",
        "observacoes": "Veículo para entrega",
        "observacoes_gestor": "Manter revisão em dia",
        "valor_mensalidade": 150.00,
        "status_veiculo": 0,
        "data_cadastro": "2024-01-15T10:30:00",
        "rastreador_id": 456,
        "grupo_eventos_id": 789,
        "complemento_id": 1,
        "complemento": {
          "chassi": "9BWZZZ377VT004251",
          "cor": "Prata",
          "renavam": "12345678901",
          "ano_fab": 2020,
          "ano_mod": 2021,
          "tipo_eqp": 1
        }
      }
    ],
    "total": 1,
    "filtros": {
      "placa": "ABC1234",
      "veiculo_id": null
    }
  }
}
```

---

## 3. Atualizar Veículo

**POST** `/Veiculos/Atualizar?key=SUA_CHAVE_API`

Atualiza dados de um veículo existente. Apenas os campos enviados serão alterados.

### Campos de Identificação (um obrigatório)

| Campo        | Tipo   | Descrição           |
|--------------|--------|---------------------|
| `veiculo_id` | int    | ID do veículo       |
| `placa`      | string | Placa do veículo    |

### Body (JSON)

```json
{
  "veiculo_id": 1,
  "placa": "ABC1234",
  "descricao": "Fiat Palio 1.0 Atualizado",
  "observacoes": "Veículo atualizado",
  "valor_mensalidade": 160.00,
  "status_veiculo": 0,
  "cor": "Branco",
  "ano_mod": 2022
}
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 1,
    "placa": "ABC1234",
    "descricao": "Fiat Palio 1.0 Atualizado",
    "data_atualizacao": "2024-01-15T10:30:00"
  }
}
```

---

## 4. Excluir Veículo

**POST** `/Veiculos/Excluir?key=SUA_CHAVE_API`

### Body (JSON) — informar um dos dois

```json
{ "veiculo_id": 1 }
```
```json
{ "placa": "ABC1234" }
```

> ⚠️ **Nota de teste real:** exclusão por `veiculo_id` funcionou corretamente (HTTP 200 JSON). Exclusão por `placa` retornou HTTP 400 HTML no mesmo teste. Preferir sempre `veiculo_id`.

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 1,
    "placa": "ABC1234",
    "data_exclusao": "2024-01-15T10:30:00"
  }
}
```

---

## Códigos de Erro HTTP

| Código | Descrição                                    |
|--------|----------------------------------------------|
| 400    | Bad Request — Parâmetros inválidos           |
| 401    | Unauthorized — Chave de acesso inválida      |
| 404    | Not Found — Recurso não encontrado           |
| 409    | Conflict — Conflito (ex: placa duplicada)    |
| 500    | Internal Server Error — Erro interno         |

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
