# Harmonit ↔ WESO — Pontos de Integração Completos

> Mapeamento exaustivo de todos os cruzamentos entre os dois sistemas.  
> Complementa `Harmonit_WESO_Mapeamento.md` (campos e chaves) com os **fluxos operacionais**.

---

## Categorias de integração

| Categoria | Descrição |
|-----------|-----------|
| **A — Sync de entidade** | Dado criado/atualizado num sistema deve refletir no outro |
| **B — Evento operacional** | Ação no Harmonit dispara operação no WESO |
| **C — Cascata de status** | Mudança de status num sistema propaga ação no outro |
| **D — Validação cruzada** | Consistência entre os dois sistemas |
| **E — Exclusivo WESO** | Sem contraparte no Harmonit |
| **F — Exclusivo Harmonit** | Sem contraparte no WESO (mas pode disparar ações) |

---

## A — Sync de Entidade

### A1 · Cliente

| Direção | Harmonit | WESO | Chave |
|---------|----------|------|-------|
| H → W (criar) | `POST /Cliente/CadastrarOuAtualizar` | `POST /Clientes/Cadastro` | `cnpJ_CPF` ↔ `cpfCnpj` |
| H → W (atualizar) | `POST /Cliente/CadastrarOuAtualizar` | `POST /Clientes/Atualizar` | `cnpJ_CPF` ↔ `cpfCnpj` |
| H → W (consultar) | `GET /ObterClientePorCpfCnpj` | `GET /Clientes/Consultar?cpfCnpj=` | deduplicação |

Campos sincronizados: `nome`, `tipoPessoa`→`tipoCliente`, `situacao` (com tradução), `bloqueado`→`situacao:"Bloqueado"`

---

### A2 · Veículo

| Direção | Harmonit | WESO | Chave |
|---------|----------|------|-------|
| H → W (criar) | `POST /Veiculo/Incluir` | `POST /Veiculos/Cadastro` | `placa` |
| H → W (atualizar) | `PUT /Veiculo/Atualizar` | `POST /Veiculos/Atualizar` | `placa` |
| H → W (remover) | — *(sem delete)* | `POST /Veiculos/Excluir` | via desinstalação de OS |

Campos sincronizados: `placa`, `clienteId`→`cpfCnpj` do cliente, `tipo`→`tipoEqp` (com tradução)

> **Criação composta:** `POST /Veiculos/Cadastro` no WESO aceita cliente + veículo + rastreador + chip aninhados numa única chamada — usar para cadastro completo em vez de 4 chamadas separadas.

---

### A3 · Rastreador

| Direção | Harmonit | WESO | Chave |
|---------|----------|------|-------|
| H → W (criar) | `POST /Rastreador/Incluir` | `POST /Rastreadores/Cadastro` | `equipamento` ↔ `numeroSerie` |
| H → W (atualizar) | `PUT /Rastreador/Atualizar` | `POST /Rastreadores/Atualizar` | `equipamento` ↔ `numeroSerie` |
| H → W (consultar) | `POST /Rastreador/ObterRastreadores` | `GET /Rastreadores/Consultar` | cross-check |

Campos sincronizados: `equipamento`→`numeroSerie`, `veiculoId`/`placa`, `simCardId`/`numeroChip`→`iccId`

---

### A4 · SIM Card

| Direção | Harmonit | WESO | Chave |
|---------|----------|------|-------|
| H → W (criar) | `POST /SIMCard/CadastrarOuAtualizar` | `POST /SimCard/Cadastrar` | `numeroChip` ↔ `iccId` |
| H → W (atualizar) | `PUT /SIMCard/Atualizar` | `POST /SimCard/Atualizar` | `numeroChip` ↔ `iccId` |
| H → W (consultar) | `POST /SIMCard/ObterSIMCards` | `GET /SimCard/Consultar?iccId=` | cross-check |

Campos sincronizados: `numeroChip`→`iccId`, `numeroLinha`→`numero`

---

## B — Eventos Operacionais

### B1 · Instalação de equipamento (OS → WESO)

O momento mais importante de sincronização. Quando uma OS registra instalação física:

```
Harmonit: POST /OrdemServico/AdicionarOficina
  └── OrdemServicoXOficina: { instalacaoId, equipamentoId, veiculoId, veiculoPlaca }
            ↓
  Leitura complementar:
    POST /Rastreador/ObterRastreadores (filtra por veiculoId → pega serial + ICCID + linha)
    GET /ObterClientePorCpfCnpj (pega dados completos do cliente)
            ↓
WESO: POST /Veiculos/Cadastro
  └── body completo: cliente + veiculo + rastreador + simcard
```

---

### B2 · Desinstalação de equipamento (OS → WESO)

```
Harmonit: POST /OrdemServico/DesinstalarOficina
  └── equipamentoId desvinculado da placa
            ↓
WESO: POST /Veiculos/Excluir
  └── remove vínculo rastreador-veículo
```

---

### B3 · Troca de chip ou equipamento (OS → WESO)

Quando uma OS de manutenção troca o SIM Card ou o rastreador:

```
Harmonit: PUT /Rastreador/Atualizar (novo simCardId)
  ou
Harmonit: PUT /SIMCard/Atualizar (novo numeroChip/numeroLinha)
            ↓
WESO: POST /Veiculos/Atualizar (nova associação)
  + POST /SimCard/Atualizar (novos dados do chip)
```

---

### B4 · Verificação de status de comando (WESO → contexto Harmonit)

Após disparar um comando de bloqueio/desbloqueio pelo WESO, consultar resultado:

```
WESO: GET /Comandos/ComandosEnviados?placa=...
  └── { HasError, Result } → confirmação de execução
```

Útil para registrar o resultado em log interno ou atualizar a OS de manutenção no Harmonit.

---

## C — Cascata de Status

### C1 · Bloqueio financeiro (Harmonit → WESO)

```
Harmonit: Cliente.bloqueado = true
  ou
Harmonit: GET /Financeiro/ObterBoletosEmAbertoPorCpfCnpj → boletos vencidos detectados
            ↓
  [Serviço de sync]
  1. Atualizar situação no WESO:
     WESO: POST /Clientes/Atualizar → situacao: "Bloqueado"
  2. Bloquear cada veículo do cliente:
     WESO: GET /Veiculos/Consultar?cpfCnpj=... → lista de placas
     WESO: GET /Comandos/EnviarComando?placa=ABC1234&comando=BLOQUEAR  (por placa)
```

---

### C2 · Desbloqueio (Harmonit → WESO)

```
Harmonit: Cliente.bloqueado = false
  e/ou
Harmonit: situacaoCliente → Adimplente
            ↓
  [Serviço de sync]
  1. WESO: POST /Clientes/Atualizar → situacao: "Adimplente"
  2. WESO: GET /Comandos/EnviarComando?placa=...&comando=DESBLOQUEAR (por placa)
```

---

### C3 · Tradução de situação do cliente

Harmonit usa lookup configurável; WESO usa enum fixo. Tabela de tradução obrigatória na camada de integração:

| Harmonit `situacaoClienteDesc` | Harmonit `bloqueado` | WESO `situacao` |
|-------------------------------|---------------------|-----------------|
| (qualquer) | `true` | `Bloqueado` |
| Ativo / Normal / Adimplente | `false` | `Adimplente` |
| Inadimplente | `false` | `Inadimplente` |
| Teste / Trial | `false` | `Teste` |
| Em negociação | `false` | `Negociacao` |
| Cortesia / Demo | `false` | `Cortesia` |

> `bloqueado: true` tem precedência sobre qualquer `situacaoClienteDesc`.

---

## D — Validação Cruzada

### D1 · Consistência rastreador-placa-chip

Verifica se o que está no Harmonit bate com o que está no WESO:

```
Harmonit: POST /Rastreador/ObterRastreadores
  → { equipamento (serial), placa, numeroChip (ICCID), numeroLinha, instalado, ativar }

WESO:     GET /Veiculos/Consultar?placa=...
  → { placa, rastreadorId, numeroSerie, simcardId, iccId }

Divergências a checar:
  H.equipamento  == W.numeroSerie   (serial do tracker)
  H.numeroChip   == W.iccId         (ICCID do chip)
  H.numeroLinha  == W.numero        (número da linha)
  H.placa        == W.placa         (placa do veículo)
```

---

### D2 · Chip disponível × chip instalado

```
Harmonit: POST /SIMCard/ObterSIMCards (lista chips cadastrados)
WESO:     GET /SimCard/Consultar?iccId=... → { disponivel: boolean }

Se Harmonit tem chip com rastreador vinculado (simCardId != null)
  e WESO tem disponivel: true → inconsistência (chip deveria estar vinculado no WESO)
```

---

### D3 · Rastreador instalado × rastreador ativo

```
Harmonit: Rastreador.instalado == true AND Rastreador.ativar == true
  → deve existir veículo correspondente no WESO com tracker vinculado

Harmonit: Rastreador.instalado == false OR Rastreador.ativar == false
  → veículo pode existir no WESO mas sem tracker ativo
```

---

### D4 · Auditoria de timeline

Cruzar histórico de operações de ambos os sistemas para rastrear a linha do tempo completa:

```
Harmonit: GET /OrdemServico/ObterTimeLine  → histórico de status da OS
WESO:     GET /Comandos/ComandosEnviados?placa=...  → histórico de comandos enviados
```

---

## E — Exclusivo WESO (sem contraparte no Harmonit)

| Módulo WESO | Endpoints | Relevância |
|-------------|-----------|-----------|
| **Posicionamento** | `GET /Posicao/UltimaPosicao` `GET /Posicao/ConsultaVeiculo` | GPS em tempo real — não existe no Harmonit |
| **Motoristas** | CRUD completo | Operadores de veículos — Harmonit tem técnicos mas não motoristas de frota |
| **Comandos (resposta)** | `GET /Comandos/ComandosEnviados` | Resultado dos comandos BLOQUEAR/DESBLOQUEAR |

---

## F — Exclusivo Harmonit (sem contraparte direta no WESO)

| Módulo Harmonit | Relação com WESO |
|-----------------|-----------------|
| **Financeiro** (boletos, movimentação) | Indireta — boletos vencidos → `situacao:"Bloqueado"` + comando BLOQUEAR |
| **OrdemServico** (lifecycle completo) | Indireta — `AdicionarOficina` → `Veiculos/Cadastro`; `DesinstalarOficina` → `Veiculos/Excluir` |
| **Produto / Serviço** | Sem relação com WESO |
| **Operadora** (Vivo, Claro, TIM) | Sem contraparte — WESO não tem campo de operadora |
| **ZonasParticoes** | Sem relação com WESO |
| **EstoqueLocal** | Sem relação com WESO |
| **Contratos** *(ausente na API)* | Seria relevante para `situacao` do cliente no WESO |

---

## Mapa visual de integrações

```
HARMONIT                                    WESO
══════════════════════════════════════════════════════════════════
Cliente ──────────────────────────────────► Cliente
  cnpJ_CPF ────────────────────────────────► cpfCnpj  (chave)
  tipoPessoa ──────────────────────────────► tipoCliente
  situacaoClienteDesc ─[tradução]──────────► situacao
  bloqueado: true ─────────────────────────► situacao: "Bloqueado"
                                             + Comandos: BLOQUEAR ◄──┐
Financeiro/boletos vencidos ─[cascade]────────────────────────────────┘

Veiculo ──────────────────────────────────► Veiculo
  placa ───────────────────────────────────► placa    (chave)
  tipo ────────────────[tradução]──────────► tipoEqp
  clienteId → cnpJ_CPF ────────────────────► cpfCnpj do cliente

Rastreador ───────────────────────────────► Rastreador
  equipamento ─────────────────────────────► numeroSerie (chave)
  veiculoId/placa ─────────────────────────► via placa
  simCardId/numeroChip ────────────────────► via iccId

SIMCard ──────────────────────────────────► SimCard
  numeroChip (ICCID) ──────────────────────► iccId    (chave)
  numeroLinha ─────────────────────────────► numero

OrdemServico
  AdicionarOficina ───[evento]─────────────► Veiculos/Cadastro (completo)
  DesinstalarOficina ─[evento]─────────────► Veiculos/Excluir

                                             Posicao ──────────── (exclusivo WESO)
                                             Motoristas ────────── (exclusivo WESO)
                                             Comandos/resultado ─── (exclusivo WESO)
══════════════════════════════════════════════════════════════════
```

---

## Contagem de pontos de integração

| Categoria | Quantidade |
|-----------|-----------|
| A — Sync de entidade | 4 entidades × criar/atualizar/consultar = **12 pontos** |
| B — Eventos operacionais | Instalação, desinstalação, troca, verificação = **4 eventos** |
| C — Cascata de status | Bloqueio, desbloqueio, tradução de status = **3 fluxos** |
| D — Validação cruzada | Consistência, disponibilidade, instalação, auditoria = **4 validações** |
| **Total de pontos ativos** | **23** |
| E — Exclusivo WESO (leitura) | 3 módulos |
| F — Exclusivo Harmonit (sem ação WESO) | 5 módulos |
