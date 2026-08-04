# Harmonit — API Financeira

> **Auth:** `Authorization: Bearer TOKEN`

---

## Endpoints

| Método | Rota                                              | Ação                                       |
|--------|---------------------------------------------------|--------------------------------------------|
| GET    | `/Financeiro/ObterBoletosEmAberto`                | Boletos em aberto por mês/ano              |
| GET    | `/Financeiro/ObterBoletosEmAbertoPorCpfCnpj`      | Boletos em aberto por CPF/CNPJ (v1)        |
| GET    | `/Financeiro/v2/ObterBoletosEmAbertoPorCpfCnpj`   | Boletos em aberto por CPF/CNPJ (v2)        |
| POST   | `/Financeiro/ObterBoletosEmAbertoPorDemanda`       | Boletos em aberto paginados (demanda)       |
| POST   | `/Financeiro/ObterBoletosPorCpfCnpj`              | Boletos por CPF/CNPJ + período             |
| POST   | `/Financeiro/ObterBoleto`                         | Detalhes de um boleto por ID               |
| POST   | `/Financeiro/ImprimirBoleto`                      | Imprimir/gerar boleto por parcela          |
| GET    | `/Financeiro/v1/ObterMovimentacaoFinanceiraABaixar` | Movimentação a baixar (v1)                |
| GET    | `/Financeiro/v1/ObterMovimentacaoFinanceiraBaixados`| Movimentação baixada (v1)                 |
| GET    | `/Financeiro/v2/ObterMovimentacaoFinanceiraABaixar` | Movimentação a baixar (v2)                |
| GET    | `/Financeiro/v2/ObterMovimentacaoFinanceiraBaixados`| Movimentação baixada (v2)                 |

> **Atenção:** Existem endpoints v1 e v2 para Movimentação Financeira. Usar **v2** para novos desenvolvimentos.

---

## 1. Boletos em Aberto

### Por mês/ano

**GET** `/Financeiro/ObterBoletosEmAberto`

| Campo           | Tipo    | Descrição                  |
|-----------------|---------|----------------------------|
| `anoVencimento` | integer | Ano do vencimento (ex: 2024)|
| `mesVencimento` | integer | Mês do vencimento (1-12)   |

```
GET /Financeiro/ObterBoletosEmAberto?anoVencimento=2024&mesVencimento=5
```

---

### Por CPF/CNPJ — v1

**GET** `/Financeiro/ObterBoletosEmAbertoPorCpfCnpj`

| Campo              | Tipo    | Descrição         |
|--------------------|---------|-------------------|
| `anoVencimento`    | integer | Ano               |
| `mesVencimento`    | integer | Mês               |
| `cpfCnpjCliente`   | string  | CPF ou CNPJ       |

---

### Por CPF/CNPJ — v2 *(sem filtro de data)*

**GET** `/Financeiro/v2/ObterBoletosEmAbertoPorCpfCnpj?cpfCnpjCliente=12345678901`

Retorna todos os boletos em aberto do cliente, sem filtro de data.

---

### Por Demanda (paginado)

**POST** `/Financeiro/ObterBoletosEmAbertoPorDemanda`

| Campo           | Tipo    | Descrição                  |
|-----------------|---------|----------------------------|
| `anoVencimento` | integer | Ano do vencimento           |
| `mesVencimento` | integer | Mês do vencimento           |
| `skip`          | integer | Offset                      |
| `take`          | integer | Limite                      |

```
POST /Financeiro/ObterBoletosEmAbertoPorDemanda?anoVencimento=2024&mesVencimento=5&skip=0&take=50
```

---

## 2. Boletos por CPF/CNPJ e Período

**POST** `/Financeiro/ObterBoletosPorCpfCnpj`

```json
{
  "cnpjCpf": "12.345.678/0001-99",
  "vencimentoInicial": "2024-01-01",
  "vencimentoFinal": "2024-12-31"
}
```

---

## 3. Detalhes de um Boleto

**POST** `/Financeiro/ObterBoleto?id=5001`

Retorna os dados completos de uma parcela/boleto específico.

---

## 4. Imprimir Boleto

**POST** `/Financeiro/ImprimirBoleto?parcelaId=5001`

Retorna os dados para impressão/envio do boleto (provavelmente URL ou base64).

**Resposta (RetornoBoletoViewModel):**
```json
{
  "data": {
    "url": "https://...",
    "codigoBarras": "...",
    "linhaDigitavel": "..."
  }
}
```

---

## 5. Movimentação Financeira

### A Baixar (pendente)

**GET** `/Financeiro/v2/ObterMovimentacaoFinanceiraABaixar`

| Campo           | Tipo | Descrição                          |
|-----------------|------|------------------------------------|
| `anoVencimento` | int  | Ano                                |
| `mesVencimento` | int  | Mês                                |
| `tipo`          | enum | `1` = Receita \| `2` = Despesa    |

```
GET /Financeiro/v2/ObterMovimentacaoFinanceiraABaixar?anoVencimento=2024&mesVencimento=5&tipo=1
```

### Já Baixados (liquidados)

**GET** `/Financeiro/v2/ObterMovimentacaoFinanceiraBaixados`

Mesmos parâmetros que o endpoint acima.

---

## Observações analíticas

- **v1 vs v2 de Movimentação:** Existem dois schemas diferentes (`MovimentacaoFinanceiraABaixarV1ViewModel` e `V2ViewModel`). Usar v2 para novos desenvolvimentos — v1 provavelmente existe por compatibilidade retroativa.
- **`ImprimirBoleto` é POST:** incomum para uma operação de leitura — provável que gere/registre um log de acesso ao boleto.
- **`ObterBoleto` é POST:** mesmo padrão. Verificar se há side-effects (ex: marcar como visualizado).
