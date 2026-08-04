# Harmonit ↔ WESO — Mapeamento de Entidades e Fluxo de Sincronização

> Análise da relação entre os dois sistemas: o que é espelhado, quais campos se correspondem,
> onde estão as traduções necessárias e qual é o fluxo de registro ideal.

---

## Visão Geral da Relação

Os dois sistemas são complementares e compartilham as mesmas entidades físicas:

| Sistema | Papel | Fonte de verdade |
|---------|-------|-----------------|
| **Harmonit** | ERP — clientes, contratos, OS, financeiro | Dados comerciais e operacionais |
| **WESO** | Plataforma GPS — rastreamento, posições, comandos | Dados de rastreamento em tempo real |

Quando um cliente tem um rastreador instalado:
- **Harmonit** sabe: quem é o cliente, qual veículo, qual equipamento foi instalado, qual OS gerou a instalação
- **WESO** sabe: qual placa está sendo rastreada, qual tracker, qual chip, e emite as posições

**A ponte entre os dois é o cadastro:** cliente + veículo + rastreador + SIM Card precisam existir nos dois sistemas com os mesmos dados-chave.

---

## Mapeamento de Entidades

### Cliente

| Campo Harmonit | Campo WESO | Tipo | Observação |
|---------------|-----------|------|------------|
| `cnpJ_CPF` | `cpfCnpj` | string | **Chave de vínculo** |
| `nome` | `nome` | string | Direto |
| `nomeFantasia` | — | string | Harmonit tem, WESO não expõe |
| `tipoPessoa` (Fisica/Juridica) | `tipoCliente` (Fisica/Juridica/NaoInformado) | enum | Mapeamento direto |
| `situacaoClienteDesc` | `situacao` | string/enum | Requer tradução (ver tabela abaixo) |
| `bloqueado: true` | `situacao: "Bloqueado"` | bool→enum | Mapeamento direto |
| `ativo: false` | `situacao: "Bloqueado"` | bool→enum | Inativo no ERP = bloqueado no WESO |

#### Tradução de situação (Harmonit → WESO)

Harmonit usa lookup configurável; WESO usa enum fixo. Tradução necessária:

| Harmonit `situacaoClienteDesc` (exemplo) | WESO `situacao` |
|------------------------------------------|-----------------|
| Ativo / Normal | `Adimplente` |
| Inadimplente | `Inadimplente` |
| Bloqueado / `bloqueado: true` | `Bloqueado` |
| Teste / Trial | `Teste` |
| Em negociação | `Negociacao` |
| Cortesia / Demo | `Cortesia` |

> Como `situacaoClienteDesc` é texto livre configurável no Harmonit, a tradução precisa de uma tabela de-para mantida na camada de integração.

---

### Veículo

| Campo Harmonit | Campo WESO | Tipo | Observação |
|---------------|-----------|------|------------|
| `placa` | `placa` | string | **Chave de vínculo** |
| `clienteId` → `cnpJ_CPF` | via `cpfCnpj` do cliente | ref | Vínculo indireto via cliente |
| `tipo` (string: "Automóvel", "Caminhão"…) | `tipoEqp` (int ou string — 20+ tipos) | string/int | Requer tradução (ver tabela abaixo) |
| `marca` | — | string | Harmonit tem, WESO agrupa em `tipoEqp` |
| `modelo` | — | string | Harmonit tem, não mapeado no WESO |
| `ano` | — | integer | Harmonit tem, não mapeado no WESO |
| `numeroChassi` | — | string | Harmonit tem, não mapeado no WESO |
| `odometro` | — | integer | Harmonit tem, não mapeado no WESO |

#### Tradução de tipo de veículo (Harmonit → WESO tipoEqp)

| Harmonit `tipo` | WESO `tipoEqp` | int |
|----------------|---------------|-----|
| Automóvel / Carro | Carro | 1 |
| Moto / Motocicleta | Moto | 2 |
| Caminhão | Caminhão | 3 |
| Ônibus | Ônibus | 4 |
| Caminhonete | Caminhonete | 8 |
| Carreta | Carreta | 9 |
| Trator | Trator | 6 |
| Barco / Embarcação | Barco | 7 |
| Bicicleta | Bicicleta | 11 |

> Lista completa de `tipoEqp` documentada em `WESO/01_Veiculos.md`.

---

### Rastreador

| Campo Harmonit | Campo WESO | Tipo | Observação |
|---------------|-----------|------|------------|
| `equipamento` (número de série) | `numeroSerie` | string | **Chave de vínculo** |
| `modeloEquipamento` (ex: "CRX3", "GV75") | — | string | Modelo do tracker — WESO não armazena modelo separado |
| `veiculoId` / `placa` | via `placa` do veículo | ref | Vínculo via placa |
| `simCardId` / `numeroChip` | via `iccId` do simcard | ref | Vínculo via ICCID |
| `instalado` | — | boolean | Status físico — sem equivalente direto no WESO |
| `ativar` | — | boolean | Ativação no ERP — sem equivalente direto no WESO |

> **Atenção:** `modeloEquipamento` em Harmonit (modelo do tracker: CRX3, GV75…) é diferente de `tipoEqp` em WESO (tipo do veículo: Carro, Moto…). Não são o mesmo campo — não mapear entre si.

---

### SIM Card

| Campo Harmonit | Campo WESO | Tipo | Observação |
|---------------|-----------|------|------------|
| `numeroChip` (ICCID) | `iccId` | string | **Chave de vínculo** |
| `numeroLinha` | `numero` | string | Número de telefone — direto |
| `operadoraId` | — | integer | Operadora — WESO não tem este campo |
| — | `disponivel` | boolean | Apenas WESO — indica se o chip está livre |

---

## Fluxo de Registro

### Cadastro completo (novo cliente + veículo + rastreador + chip)

O WESO tem um endpoint único que cria tudo em uma chamada — ideal para sincronização:

```
POST /Veiculos/Cadastro (WESO)
{
  "equipamento": {
    "placa":     ← Harmonit: Veiculo.placa
    "tipoEqp":   ← Harmonit: Veiculo.tipo (traduzido)
    "cliente": {
      "cpfCnpj":     ← Harmonit: Cliente.cnpJ_CPF
      "nome":        ← Harmonit: Cliente.nome
      "tipoCliente": ← Harmonit: Cliente.tipoPessoa (mapeado)
      "situacao":    ← Harmonit: Cliente.situacaoClienteDesc (traduzido)
    },
    "rastreador": {
      "numeroSerie": ← Harmonit: Rastreador.equipamento
    },
    "simcard": {
      "iccId":   ← Harmonit: SIMCard.numeroChip
      "numero":  ← Harmonit: SIMCard.numeroLinha
    }
  }
}
```

> Este endpoint também auto-cria fornecedor e associações internas no WESO se não existirem.

---

### Gatilho natural de sincronização

O momento ideal para disparar o cadastro no WESO é após a conclusão da **Oficina de instalação** no Harmonit:

```
Harmonit: POST /OrdemServico/AdicionarOficina
  → instalacaoId vinculada, equipamentoId vinculado, veiculoId + placa confirmados
       ↓
  [Serviço de sync]
       ↓
WESO: POST /Veiculos/Cadastro  ← cria/atualiza tudo
```

E para desinstalação:
```
Harmonit: POST /OrdemServico/DesinstalarOficina
       ↓
  [Serviço de sync]
       ↓
WESO: POST /Veiculos/Excluir  ← remove vínculo
```

---

## Verificação de Existência Antes de Criar

Para evitar duplicatas ao sincronizar, o fluxo de cada entidade deve ser:

### Cliente
```
1. GET /ObterClientePorCpfCnpj (Harmonit) → confirma dados
2. GET /Clientes/Consultar?cpfCnpj=... (WESO) → verifica existência
   → existe: atualizar se divergência
   → não existe: criará automaticamente via /Veiculos/Cadastro
```

### Veículo / Placa
```
1. GET /Veiculo/ObterVeiculos (Harmonit) → confirma placa
2. GET /Veiculos/Consultar?placa=... (WESO) → verifica existência
   → existe: atualizar se divergência
   → não existe: criará automaticamente via /Veiculos/Cadastro
```

### Rastreador
```
1. POST /Rastreador/ObterRastreadores (Harmonit) → confirma serial + vínculo
2. GET /Rastreadores/Consultar?numeroSerie=... (WESO) → verifica existência
   → existe: verificar se placa e chip batem
   → não existe: criará automaticamente via /Veiculos/Cadastro
```

### SIM Card
```
1. POST /SIMCard/ObterSIMCards (Harmonit) → confirma ICCID + linha
2. GET /SimCard/Consultar?iccId=... (WESO) → verifica existência
   → disponivel: false → já vinculado
   → disponivel: true  → livre, será vinculado via /Veiculos/Cadastro
```

---

## Gaps e Pontos de Atenção

| # | Ponto | Detalhe |
|---|-------|---------|
| G1 | Tradução de status | `situacaoClienteDesc` Harmonit (texto livre) → `situacao` WESO (enum fixo). Precisa de tabela de-para na camada de integração |
| G2 | Tradução de tipo de veículo | `tipo` Harmonit (string) → `tipoEqp` WESO (int ou string). Mesmos valores mas representações diferentes |
| G3 | Campos exclusivos Harmonit | `modelo`, `marca`, `ano`, `chassi`, `odômetro`, `operadoraId` — não têm equivalente no WESO |
| G4 | Campo exclusivo WESO | `simcard.disponivel` — status de disponibilidade do chip, não existe no Harmonit |
| G5 | `ativar` / `instalado` | Harmonit tem flags de ativação/instalação do rastreador sem equivalente direto no WESO |
| G6 | Exclusão de veículo | WESO tem `POST /Veiculos/Excluir`, Harmonit não tem DELETE de veículo — exclusão só ocorre via desinstalação de OS |
| G7 | Sincronização reversa | Posições e comandos WESO → Harmonit: **sem caminho** — WESO não tem webhooks; Harmonit não tem endpoints de posição |

---

## Resumo dos Vínculos-Chave

```
Harmonit                    WESO
─────────────────────────────────────────────────────
Cliente.cnpJ_CPF        ←→  Cliente.cpfCnpj
Veiculo.placa           ←→  Veiculo.placa
Rastreador.equipamento  ←→  Rastreador.numeroSerie
SIMCard.numeroChip      ←→  SimCard.iccId
SIMCard.numeroLinha     ←→  SimCard.numero
```

Esses cinco campos são as **âncoras de identidade** entre os dois sistemas. Qualquer serviço de sync ou validação deve operar por eles.
