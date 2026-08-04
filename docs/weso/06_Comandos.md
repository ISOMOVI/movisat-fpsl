# API de Comandos

> **Rota base:** `/Comandos/`  
> **Autenticação:** `?key=SUA_CHAVE_API` em todas as requisições

---

## Endpoints

| Método | Rota                              | Ação                        |
|--------|-----------------------------------|-----------------------------|
| GET    | `/Comandos/EnviarComando`         | Enviar comando ao veículo   |
| GET    | `/Comandos/ComandosEnviados`      | Consultar histórico de comandos |

> **Atenção:** Ambos os endpoints de Comandos usam **GET com parâmetros na URL**, diferente dos demais módulos.

---

## 1. Enviar Comando

**GET** `/Comandos/EnviarComando?key=SUA_CHAVE_API&placa=ABC1234&comando=BLOQUEAR`

Envia um comando remoto para o rastreador instalado no veículo identificado pela placa.

### Parâmetros de Query

| Campo     | Tipo   | Obrigatório | Descrição                                   |
|-----------|--------|-------------|---------------------------------------------|
| `key`     | string | ✅          | Chave de API para autenticação              |
| `placa`   | string | ✅          | Placa do veículo que receberá o comando     |
| `comando` | string | ✅          | Tipo de comando (ver tabela abaixo)         |

### Comandos disponíveis

| Comando       | Descrição                                         |
|---------------|---------------------------------------------------|
| `BLOQUEAR`    | Envia sinal de bloqueio ao rastreador/veículo     |
| `DESBLOQUEAR` | Envia sinal de desbloqueio ao rastreador/veículo  |

### Exemplos de URL

```
GET /Comandos/EnviarComando?key=SUA_CHAVE_API&placa=ABC1234&comando=BLOQUEAR
GET /Comandos/EnviarComando?key=SUA_CHAVE_API&placa=ABC1234&comando=DESBLOQUEAR
```

### Resposta de Sucesso (200)

```json
{
  "Result": "Comando enviado com sucesso"
}
```

> **Nota:** A resposta de sucesso retorna apenas `"Result"` sem o wrapper padrão `status/data`.

### Erros específicos

**Placa não encontrada:**
```json
{
  "HasError": true,
  "Result": "Placa não encontrada"
}
```

**Comando não suportado pelo rastreador:**
```json
{
  "HasError": true,
  "Result": "Comando não encontrado"
}
```

---

## 2. Consultar Comandos Enviados

**GET** `/Comandos/ComandosEnviados?key=SUA_CHAVE_API&placa=ABC1234`

Retorna o histórico de todos os comandos enviados para um veículo específico, com status de entrega.

### Parâmetros de Query

| Campo   | Tipo   | Obrigatório | Descrição                                 |
|---------|--------|-------------|-------------------------------------------|
| `key`   | string | ✅          | Chave de API para autenticação            |
| `placa` | string | ✅          | Placa do veículo a ser consultado         |

### Exemplos de URL

```
GET /Comandos/ComandosEnviados?key=SUA_CHAVE_API&placa=ABC1234
```

### Resposta de Sucesso (200)

```json
{
  "Result": [
    {
      "DataEnvio": "22/05/2024 14:30",
      "DataAtualizacao": "22/05/2024 14:31",
      "Status": "Enviado com sucesso"
    },
    {
      "DataEnvio": "22/05/2024 14:25",
      "DataAtualizacao": "",
      "Status": "Aguardando"
    }
  ]
}
```

### Campos da Resposta

| Campo             | Tipo   | Descrição                                          |
|-------------------|--------|----------------------------------------------------|
| `DataEnvio`       | string | Data e hora do envio do comando (dd/MM/yyyy HH:mm) |
| `DataAtualizacao` | string | Data da última atualização de status (pode estar vazio se ainda processando) |
| `Status`          | string | Status atual do comando (ver tabela abaixo)        |

### Status dos Comandos

| Status                    | Descrição                                                   |
|---------------------------|-------------------------------------------------------------|
| `Enviado com sucesso`     | O sistema enviou o comando com sucesso ao rastreador        |
| `Aguardando`              | Aguardando confirmação de entrega pelo rastreador           |
| `Cancelado`               | O comando foi cancelado antes de ser enviado                |
| `Comando não suportado`   | O rastreador não suporta este tipo de comando               |
| `Não identificado`        | O status do comando é desconhecido                          |

---

## Observações importantes

### Formato de resposta diferenciado

Os endpoints de Comandos **não** seguem o padrão `{ "status": "success", "data": {...} }` dos demais módulos. As respostas são:

- **Sucesso:** `{ "Result": "..." }` ou `{ "Result": [...] }`
- **Erro:** `{ "HasError": true, "Result": "..." }`

### Assíncrono por natureza

O envio de um comando é uma operação **assíncrona**. Quando a API retorna `"Comando enviado com sucesso"`, significa que o sistema **enfileirou** o comando. A confirmação de execução no veículo pode levar alguns instantes, dependendo da conectividade do rastreador.

Use `/Comandos/ComandosEnviados` para verificar o status real da execução.

### Fluxo recomendado de uso

```
1. Enviar o comando
   GET /Comandos/EnviarComando?key=KEY&placa=ABC1234&comando=BLOQUEAR
   → Verificar se retornou { "Result": "Comando enviado com sucesso" }

2. Aguardar alguns segundos

3. Consultar o status
   GET /Comandos/ComandosEnviados?key=KEY&placa=ABC1234
   → Verificar o campo "Status" do último comando enviado
```
