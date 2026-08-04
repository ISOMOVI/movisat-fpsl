# API de SIM Cards

> **Rota base:** `/SimCard/`  
> **Autenticação:** `?key=SUA_CHAVE_API` em todas as requisições

---

## Endpoints

| Método | Rota                      | Ação               |
|--------|---------------------------|--------------------|
| POST   | `/SimCard/Cadastro`       | Cadastrar SIM Card |
| GET    | `/SimCard/Consultar`      | Consultar SIM Cards|
| POST   | `/SimCard/Atualizar`      | Atualizar SIM Card |
| POST   | `/SimCard/Excluir`        | Excluir SIM Card   |

---

## 1. Cadastrar SIM Card

**POST** `/SimCard/Cadastro?key=SUA_CHAVE_API`

Cadastra um novo SIM Card no sistema. Permite associar fornecedor, operadora e APN — seja vinculando a um existente por ID ou criando um novo fornecedor automaticamente.

### Body (JSON)

```json
{
  "iccId": "8955012345678901234",
  "numero": 5511987654321,
  "operadora": "Vivo",
  "apn": "vivo.zap.br",
  "situacao": "Estoque",
  "valorMensalidade": 19.90,
  "obs": "Lote novo de chips para rastreamento veicular.",
  "fornecedor": {
    "id": 22,
    "cnpjcpf": "12.345.678/0001-99",
    "razaoSocial": "Fornecedor de Chips LTDA"
  }
}
```

### Campos

| Campo              | Tipo   | Obrigatório | Descrição                                                     |
|--------------------|--------|-------------|---------------------------------------------------------------|
| `iccId`            | string | ✅          | Identificador único do chip (ICCID)                           |
| `numero`           | long   | ❌          | Número do telefone do SIM Card                                |
| `operadora`        | string | ❌          | Nome da operadora (ex: `"Vivo"`, `"Claro"`, `"TIM"`)         |
| `apn`              | string | ❌          | APN de dados (ex: `"vivo.zap.br"`)                           |
| `situacao`         | string | ❌          | Situação atual (ver tabela abaixo)                            |
| `valorMensalidade` | float  | ❌          | Valor mensal do chip                                          |
| `obs`              | string | ❌          | Observações internas                                          |
| `fornecedor`       | object | ❌          | Dados do fornecedor — por ID ou criação automática            |

### `situacao` — Valores aceitos

| Valor      | Descrição                         |
|------------|-----------------------------------|
| `Estoque`  | Chip disponível, não instalado    |
| `EmUso`    | Chip ativo em um rastreador       |
| `Inativo`  | Chip desativado                   |

### Comportamentos automáticos

- Se `fornecedor.id` for informado, o fornecedor existente é vinculado diretamente.
- Se `fornecedor.cnpjcpf` for informado sem ID, a API busca e vincula, ou **cria automaticamente** caso não exista.

### Resposta de Sucesso (201)

```json
{
  "status": "success",
  "data": {
    "id": 102,
    "iccId": "8955012345678901234",
    "data_cadastro": "2024-05-21T11:45:00"
  }
}
```

### Erro 400 — ICCID ausente

```json
{
  "status": "error",
  "error": {
    "code": 400,
    "message": "O ICCID é obrigatório.",
    "details": [
      { "field": "iccId", "issue": "Campo obrigatório" }
    ]
  }
}
```

---

## 2. Consultar SIM Cards

**GET** `/SimCard/Consultar?key=SUA_CHAVE_API`

> ⚠️ **Atualizado em 02/07/2026 — comportamento mudou desde o teste original.**
> - **SEM filtro** (`GET /SimCard/Consultar` puro): ainda impraticável — a requisição estoura timeout (30s+) sem retornar. Provável causa: retorno não paginado de todos os chips da empresa (mesmo padrão de lentidão visto em `/Rastreadores/Consultar` e `/Veiculos/Consultar`).
> - **COM filtro `iccId` específico**: **funciona normalmente**, HTTP 200, retorno estruturado completo. Testado com sucesso em 02/07/2026 (ver exemplo abaixo). O erro 500 "sensitive information could be disclosed..." documentado anteriormente não ocorre mais nesse cenário.
> - Ou seja: **não usar mais o fallback via `POST /SimCard/Cadastro` + erro 409** para checar existência de ICCID — basta `GET /SimCard/Consultar?iccId=...` diretamente, é mais simples e não corre risco de criar duplicidade.

Retorna SIM Cards com filtros opcionais. Sem filtros, retorna todos os chips da empresa (na prática, hoje, não retorna — timeout).

### Parâmetros de Query

| Campo        | Tipo   | Obrigatório | Descrição                                |
|--------------|--------|-------------|------------------------------------------|
| `simcard_id` | int    | ❌          | Filtrar por ID do SIM Card               |
| `iccId`      | string | ❌          | Filtrar por ICCID                        |
| `numero`     | long   | ❌          | Filtrar pelo número do telefone          |

### Exemplos de URL

```
GET /SimCard/Consultar?key=SUA_CHAVE_API
GET /SimCard/Consultar?key=SUA_CHAVE_API&simcard_id=101
GET /SimCard/Consultar?key=SUA_CHAVE_API&iccId=895501
GET /SimCard/Consultar?key=SUA_CHAVE_API&numero=5511987654321
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "simcards": [
      {
        "id": 101,
        "iccId": "8955012345678901234",
        "numero": 5511987654321,
        "valor_mensalidade": 19.90,
        "situacao": "EmUso",
        "disponivel": false,
        "data_cadastro": "2024-05-20T14:00:00",
        "observacoes": "Chip ativado para rastreador",
        "operadora": "Vivo",
        "apn": "vivo.zap.br",
        "fornecedor": {
          "id": 22,
          "razao_social": "Fornecedor de Chips LTDA",
          "cnpj_cpf": "12.345.678/0001-99"
        }
      }
    ],
    "total": 1,
    "filtros": {
      "simcard_id": 101,
      "iccId": null,
      "numero": null
    }
  }
}
```

> **Nota:** O campo `disponivel` indica se o chip está livre para ser associado a um rastreador.

> ⚠️ **Inconsistência observada em 02/07/2026:** testado com ICCID real `8955170000207915365` — retornou `situacao: "Estoque"` (chip não instalado) mas `disponivel: false`. Pela descrição da API, um chip em estoque deveria ter `disponivel: true`. Exemplo real da resposta:
> ```json
> {
>   "id": 42940,
>   "iccId": "8955170000207915365",
>   "numero": 5511933332303,
>   "valor_mensalidade": null,
>   "situacao": "Estoque",
>   "disponivel": false,
>   "operadora": "ESEYE",
>   "apn": "eseye1.com",
>   "fornecedor": {
>     "id": 405,
>     "razao_social": "ESEYE DO BRASIL TECNOLOGIA DA INFORMAÇÃO - LTDA",
>     "cnpj_cpf": "13.890.755/0001-50"
>   }
> }
> ```
> Não sabemos ainda se é dado sujo desse registro específico ou se `disponivel` tem outro significado na prática (ex: talvez reflita reserva/alocação interna, não literalmente "instalado em rastreador"). Validar com mais amostras antes de confiar nesse campo para lógica de negócio.

---

## 3. Atualizar SIM Card

**POST** `/SimCard/Atualizar?key=SUA_CHAVE_API`

Atualiza dados de um SIM Card existente. Apenas os campos enviados serão alterados.

### Campos de Identificação (um obrigatório)

| Campo    | Tipo   | Descrição          |
|----------|--------|--------------------|
| `iccId`  | string | ICCID do SIM Card  |

### Body (JSON)

```json
{
  "iccId": "8955012345678901234",
  "numero": 5511912345678,
  "situacao": "EmUso",
  "valorMensalidade": 25.50
}
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 102,
    "iccId": "8955012345678901234",
    "data_atualizacao": "2024-05-21T12:30:00"
  }
}
```

---

## 4. Excluir SIM Card

**POST** `/SimCard/Excluir?key=SUA_CHAVE_API`

### Body — informar um dos dois

```json
{ "simcard_id": 102 }
```
```json
{ "iccId": "8955012345678901234" }
```

### Resposta de Sucesso (200)

```json
{
  "status": "success",
  "data": {
    "id": 102,
    "iccId": "8955012345678901234",
    "data_exclusao": "2024-05-21T13:00:00"
  }
}
```

---

## Códigos de Erro

| Código | Descrição                                     |
|--------|-----------------------------------------------|
| 400    | Bad Request — `iccId` ausente ou inválido     |
| 401    | Unauthorized — Chave de acesso inválida       |
| 404    | Not Found — SIM Card não encontrado           |
| 409    | Conflict — ICCID duplicado                   |
| 500    | Internal Server Error — Erro interno          |

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
