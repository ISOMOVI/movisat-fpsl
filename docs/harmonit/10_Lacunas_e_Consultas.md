# Harmonit — Lacunas de API e Consultas Pendentes

> Funcionalidades identificadas como necessárias mas ausentes ou incompletas no spec atual (v2026.0609.2110).  
> Serve como registro de decisões arquiteturais e base para consultas formais à Harmonit.

---

## Visão geral das lacunas

| # | Área | Status na API | Criticidade |
|---|------|--------------|-------------|
| L1 | Datas de término de contrato | Ausente | Alta — necessário para renovações |
| L2 | Protesto / negativação de títulos | Ausente | Alta — necessário para cobrança |
| L3 | Módulo de ocorrências (cliente) | Ausente na API (existe na UI) | Média — pode usar OS como substituto |
| L4 | Filtro de veículo por placa | Ausente | Baixa — contornável com cache local |
| L5 | Integração ativa com operadoras de chip | Fora do escopo do ERP | Baixa — serviço externo necessário |

---

## L1 — Datas de término de contrato

### O que existe

- `FinanceiroListViewModel.dataVencimento` — data de vencimento de **boleto**, não de contrato
- `TecnicoxOrdemServico.dataFimAtendimento` — data de fim de **atendimento técnico**, não de contrato

### O que não existe

Nenhum endpoint ou schema com: `contrato`, `vigencia`, `dataFim`, `dataTermino`, `renovacao`, `planoId`. A palavra "contrato" não aparece nenhuma vez no spec completo de 90 endpoints.

### Impacto

Impossibilidade de automatizar alertas de renovação via API. Qualquer solução de notificação de vencimento de contrato precisaria de fonte de dados alternativa (tabela própria espelhando contratos, ou planilha de controle).

### Consulta enviada à Harmonit

> *"A data final dos contratos não está disponível para consulta no Swagger — somente a data de vencimento de boleto aparece nos endpoints financeiros.*
>
> *A necessidade é acessar essa data para construir um serviço próprio de notificação de renovação para a equipe interna.*
>
> *Existe endpoint de contratos/assinaturas não listado no Swagger atual? Caso sim, quais campos estariam disponíveis (dataInicio, dataFim, planoId, situação do contrato)? Se não existir, está previsto no roadmap?"*

### Alternativa enquanto não disponível

Manter tabela própria com `clienteId`, `dataFimContrato`, `planoDescricao` e sincronizar manualmente ou via importação periódica da UI do ERP.

---

## L2 — Protesto e negativação de títulos

### O que existe

- `ClienteCostumerViewModel+Data.bloqueado` — boolean de bloqueio financeiro (inadimplência ≠ protesto)
- `ClienteCostumerViewModel+Data.situacaoClienteDesc` — string configurável com a situação do cliente
- `GET /ObterSituacaoCliente` — lista as situações configuradas no ERP (lookup com `id`, `text`, `inativar`, `bloquear`)

### O que não existe

Campo tipado e confiável que indique "título em protesto" no nível de boleto/parcela. O campo `situacaoClienteDesc` depende de configuração manual do administrador e opera no nível do cliente, não do título individual.

### Impacto

Não é possível consultar sistematicamente quais títulos específicos foram enviados a protesto. Um cliente pode ter 10 boletos e apenas 2 em protesto — a API atual não permite essa granularidade.

### Consulta enviada à Harmonit

> *"Os títulos em protesto ou enviados para protesto não possuem campo fixo para consulta no spec. Existe a consulta de cliente bloqueado (`bloqueado: boolean`), mas inadimplência não garante protesto.*
>
> *A necessidade é saber quais títulos (boletos/parcelas) estão com a marcação de protesto — não executar nenhuma ação sobre eles, apenas consultar o status para controle interno.*
>
> *Existe endpoint ou campo de boleto/parcela que indique esse status? A granularidade necessária é no nível do título, não do cliente."*

### Alternativa enquanto não disponível

Usar `bloqueado: true` no cliente como proxy de restrição severa (pode incluir protesto, mas não é exclusivo). Para rastrear protestos com precisão, cruzar com fonte externa (cartório, Serasa integração própria).

---

## L3 — Módulo de ocorrências (cliente)

### O que existe na UI (não na API)

Campos visíveis no browser do Harmonit: `ocorrencias`, `tipo de atendimento`, `canal de soluções`, `base de conhecimento`. Estes são recursos da interface web do ERP, **sem endpoint correspondente no Swagger**.

### O que está disponível na API como substituto

O módulo `OrdemServico` cobre parcialmente o fluxo:

| Conceito desejado | Campo disponível na OS | Schema |
|------------------|----------------------|--------|
| Descrição da ocorrência | `descricaoDetalhada` | `OrdemServicoSave` |
| Tipo de atendimento | `tipoId` (lookup `TipoOrdemServico`) | `OrdemServicoSave` |
| Canal de origem | `origem` (string) | `OrdemServicoMobile` |
| Solução aplicada | `solucaoTecnica` | `OrdemServicoSave` |
| Status / andamento | `situacaoId` (lookup `SituacaoOrdemServico`) | `OrdemServicoSave` |
| Prioridade / SLA | `prioridadeId` (lookup `PrioridadeAtendimento`) | `OrdemServicoSave` |
| Base de conhecimento | **Não disponível via API** | — |

> **Atenção:** `origem` existe em `OrdemServicoMobile` mas não em `OrdemServicoSave`. Testar se a Harmonit aceita o campo no payload de `SalvarOrdemServico`.

### Decisão arquitetural

Duas opções viáveis:

**Opção A — Usar OS como backend de ocorrências**  
Mapear conceitos internos ("ocorrência", "canal", "solução") para campos da OS. Configurar `TipoOrdemServico` e `SituacaoOrdemServico` com os valores do vocabulário do negócio.

**Opção B — Banco próprio + sincronização parcial**  
Manter ocorrências em banco próprio com schema completo. Usar a Harmonit API apenas para leitura de dados de contexto (cliente, veículo) e, opcionalmente, criar uma OS espelho para registro formal no ERP.

---

## L4 — Filtro de veículo por placa

### O que existe

`GET /Veiculo/ObterVeiculos` — sem parâmetros de filtro documentados. Retorna todos os veículos da empresa.

### Contorno

Carregar a lista completa e filtrar por `placa` na aplicação. Para volumes grandes, manter índice local (cache ou tabela própria) atualizado periodicamente.

Testar se a Harmonit aceita `?placa=ABC1234` como parâmetro não documentado — ERPs .NET frequentemente aceitam query params extras sem documentá-los no Swagger.

---

## L5 — Integração ativa com operadoras de chip

### O que existe

Cadastro interno: `/SIMCard/` com `numeroChip` (ICCID), `numeroLinha`, `operadoraId`.  
Lookup de operadoras: `/Operadora/` com `id` e `descricao` (ex: "Vivo", "Claro", "TIM").

### O que não existe

Qualquer integração com portais ou APIs das operadoras. A Harmonit gerencia o **catálogo interno** de chips, não o **status na operadora**.

### Posição

Fora do escopo da API Harmonit por design — é responsabilidade de serviço externo. Ver `09_Servicos_Integrados.md` para o padrão de implementação recomendado.

---

## Resumo de encaminhamentos

| Lacuna | Ação | Responsável |
|--------|------|-------------|
| L1 — datas de contrato | Consulta formal enviada à Harmonit | Aguardando resposta |
| L2 — protesto de títulos | Consulta formal enviada à Harmonit | Aguardando resposta |
| L3 — módulo ocorrências | Decisão interna: Opção A ou B | Equipe |
| L4 — filtro por placa | Implementar cache local | Dev |
| L5 — operadoras | Implementar serviço externo | Dev (ver `09_Servicos_Integrados.md`) |
