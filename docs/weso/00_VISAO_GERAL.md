# WESO API — Visão Geral

## O que é

A WESO API é uma API REST de **gestão de frotas e rastreamento veicular** da WESO Tecnologia. Permite criar, consultar, atualizar e excluir entidades do sistema: veículos, clientes, rastreadores, SIM cards, motoristas e envio de comandos remotos.

---

## Autenticação

Todas as requisições exigem uma **API Key** passada como query parameter:

```
?key=SUA_CHAVE_API
```

> A chave é única por empresa. Sem ela ou com chave inválida, a API retorna `401 Unauthorized`.

**Exemplo:**
```
GET /Veiculos/Consultar?key=SUA_CHAVE_API
POST /Veiculos/Cadastro?key=SUA_CHAVE_API
```

---

## Formato

- **Requisições:** `Content-Type: application/json` (para endpoints com body)
- **Respostas:** JSON com estrutura padronizada `{ "status": "success"|"error", "data": {...} }`
- **Exceção:** Comandos retornam `{ "Result": "..." }` ou `{ "HasError": true, "Result": "..." }`

---

## Módulos disponíveis

| Módulo        | Rota base          | Operações              |
|---------------|--------------------|------------------------|
| Veículos      | `/Veiculos/`       | Cadastro, Consulta, Atualização, Exclusão |
| Clientes      | `/Clientes/`       | Cadastro, Consulta, Atualização, Exclusão |
| Rastreadores  | `/Rastreadores/`   | Cadastro, Consulta, Atualização, Exclusão |
| SIM Cards     | `/SimCard/`        | Cadastro, Consulta, Atualização, Exclusão |
| Motoristas    | `/Motorista/`      | Cadastro, Consulta, Atualização, Exclusão |
| Comandos      | `/Comandos/`       | Enviar Comando, Consultar Enviados         |

---

## Padrão de Resposta

A API possui **dois formatos de envelope** distintos, dependendo do módulo:

### Formato A — Módulos de gerenciamento (Clientes, Veiculos, SimCard, Rastreadores, Motorista)

Chaves capitalizadas (`Status`, `Data`, `Error`). Confirmado em testes reais.

```json
{ "Status": "success", "Data": { ... } }
```
```json
{ "Status": "error", "Error": { "Code": 400, "Message": "...", "Details": [...] } }
```

### Formato B — Comandos e Posicionamento (legado)

Chaves `HasError` / `Result`. Usado pelos módulos mais antigos da API.

```json
{ "Result": "Comando enviado com sucesso" }
```
```json
{ "HasError": true, "Result": "Placa não encontrada" }
```

> **Atenção:** os campos de data retornam no formato legado `/Date(milissegundos)/` do ASP.NET — não ISO 8601. Converter com `datetime.fromtimestamp(ms / 1000)` em Python.

---

## Códigos HTTP

| Código | Status                 | Quando ocorre                                              |
|--------|------------------------|------------------------------------------------------------|
| 200    | OK                     | Consulta, atualização ou exclusão bem-sucedida             |
| 201    | Created                | Cadastro criado com sucesso                                |
| 400    | Bad Request            | Campos obrigatórios ausentes, formato inválido             |
| 401    | Unauthorized           | API key ausente, inválida ou expirada                      |
| 404    | Not Found              | Recurso não encontrado (ID, CPF, placa inexistente)        |
| 409    | Conflict               | Conflito de dados (ex: CPF/placa duplicados)               |
| 500    | Internal Server Error  | Erro interno — tentar novamente ou contatar suporte        |

---

## Comportamentos inteligentes da API

A API possui lógicas automáticas que facilitam o cadastro:

- **Busca e vinculação automática de entidades:** ao cadastrar um veículo ou motorista, o sistema pode localizar e vincular clientes, fornecedores, planos e municípios automaticamente pelo nome ou CNPJ/CPF.
- **Criação automática:** se um cliente ou fornecedor informado não existir, a API pode criá-lo automaticamente com os dados fornecidos.
- **Busca priorizada:** nos endpoints de atualização e exclusão, há prioridade de busca: primeiro por ID, depois por CNPJ/CPF (ou placa/número de série).
- **Campos opcionais:** a maioria dos campos nos endpoints de atualização é opcional — apenas envie o que deseja alterar.

---

## Arquivos desta documentação

| Arquivo                       | Conteúdo                          |
|-------------------------------|-----------------------------------|
| `01_Veiculos.md`              | API de Veículos                   |
| `02_Clientes.md`              | API de Clientes                   |
| `03_Rastreadores.md`          | API de Rastreadores               |
| `04_SimCards.md`              | API de SIM Cards                  |
| `05_Motoristas.md`            | API de Motoristas                 |
| `06_Comandos.md`              | API de Comandos Remotos           |
| `weso_inconsistencias.md`     | Inconsistências confirmadas em teste real |
