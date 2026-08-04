# Harmonit API — Visão Geral

> **Sistema:** Customers (ERP FrgFull)  
> **Versão:** 2026.0609.2110  
> **Base URL:** `https://api-hc.harmonit.com.br:8086`  
> **Spec:** `/swagger/v1/swagger.json`

---

## O que é

A Harmonit API é um ERP de gestão de serviços de campo. Cobre o ciclo completo de uma empresa de instalação/manutenção de rastreadores: clientes, ordens de serviço, técnicos, produtos, estoque, financeiro e ativos (veículos, rastreadores, SIM cards).

---

## Autenticação

**Tipo:** Bearer Token (JWT)  
**Endpoint:** `GET /Account/Token`

```
GET /Account/Token?clientId=SEU_CLIENT_ID&secretId=SEU_SECRET_ID
```

| Parâmetro  | Tipo   | Descrição               |
|------------|--------|-------------------------|
| `clientId` | string | ID do cliente da API    |
| `secretId` | string | Chave secreta da API    |

**Resposta:**
```json
{
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "errorMessage": null,
  "message": null
}
```

**Uso do token em todas as requisições:**
```
Authorization: Bearer SEU_TOKEN_AQUI
```

> O token tem validade limitada. Implementar renovação automática quando receber `401`.

---

## Padrão de Resposta

Todos os endpoints retornam o envelope `RetornoAPI<T>`:

```json
{
  "data": { ... },
  "errorMessage": null,
  "message": null
}
```

| Campo          | Tipo   | Descrição                                            |
|----------------|--------|------------------------------------------------------|
| `data`         | T      | Payload da resposta (objeto, lista, etc.)            |
| `errorMessage` | string | Mensagem de erro técnico (null em caso de sucesso)   |
| `message`      | string | Mensagem amigável (null em caso de sucesso)          |

**Erro 400:**
```json
{
  "data": null,
  "errorMessage": "Descrição técnica do erro",
  "message": "Mensagem para o usuário"
}
```

---

## Paginação

Endpoints de listagem suportam paginação via query params:

| Param          | Tipo    | Descrição                              |
|----------------|---------|----------------------------------------|
| `skip`         | integer | Registros a pular (offset)             |
| `take`         | integer | Registros a retornar (limit)           |
| `search`       | string  | Filtro de texto livre                  |
| `somenteAtivos`| boolean | Retornar apenas registros ativos       |

---

## Módulos disponíveis (90 endpoints)

| Módulo                   | Endpoints | Descrição                                        |
|--------------------------|-----------|--------------------------------------------------|
| `Account`                | 1         | Autenticação — geração de token                  |
| `Cliente`                | 8         | CRUD de clientes + zonas/partições               |
| `OrdemServico`           | 17        | Ciclo completo de OS (materiais, técnicos, etc.) |
| `Financeiro`             | 9         | Boletos em aberto e movimentação financeira      |
| `Produto`                | 10        | Produtos e serviços com checklist                |
| `Rastreador`             | 3         | Rastreadores do ERP                              |
| `SIMCard`                | 4         | SIM Cards e operadoras                           |
| `Veiculo`                | 4         | Veículos do ERP                                  |
| `Usuario`                | 4         | Usuários, técnicos e vendedores                  |
| `EstoqueLocal`           | 4         | Locais de estoque                                |
| `Operadora`              | 4         | Operadoras de telefonia                          |
| `GrupoUsuario`           | 1         | Grupos de usuários                               |
| `SituacaoOrdemServico`   | 4         | Status de OS                                     |
| `TipoOrdemServico`       | 2         | Tipos de OS                                      |
| `PrioridadeAtendimento`  | 2         | Níveis de prioridade                             |
| `Problema`               | 4         | Categorias de problema                           |
| `UnidadeMedida`          | 4         | Unidades de medida                               |

---

## Arquivos desta documentação

| Arquivo                        | Conteúdo                              |
|--------------------------------|---------------------------------------|
| `01_Autenticacao.md`           | Token e segurança                     |
| `02_Cliente.md`                | API de Clientes                       |
| `03_OrdemServico.md`           | API de Ordens de Serviço              |
| `04_Financeiro.md`             | API Financeira                        |
| `05_Produto.md`                | API de Produtos e Serviços            |
| `06_Ativos.md`                 | Rastreador, SIM Card, Veículo         |
| `07_Usuario.md`                | Usuários, Técnicos, Vendedores        |
| `08_Dados_Suporte.md`          | Tabelas de apoio (status, tipos, etc.)|
