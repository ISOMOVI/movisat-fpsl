# 22 — Auditoria dos serviços Harmonit

> Criado em 2026-07-29. Pedido do usuário: *"temos muitos serviços vinculados à
> API Harmonit e preciso auditar isso no painel ou ao menos registrar atrasos,
> dados, mas não de forma desenfreada de timeout, algo sensato mesmo."*

## Onde mede

`fpsl_weso/harmonit_client._executar` — ponto único por onde passam os 4 verbos.
Instrumentar em qualquer outro lugar seria espalhar. O registro **nunca levanta
exceção**: auditoria que derruba a operação auditada é pior que auditoria
nenhuma.

## O que grava

Tabela `harmonit_chamadas` (SQLite local): momento, serviço, rota, verbo,
duração em ms, categoria, HTTP e erro. Retenção **30 dias**,
`storage.limpar_chamadas_antigas()`.

O serviço é derivado da rota (`/OrdemServico/Salvar...` → `OrdemServico`;
`/ObterClientes` → `Clientes`) e é o que vira sub-aba no painel.

## As três categorias — e por que existem

```
ok      resposta boa
vazio   "não encontrado" — resposta legítima, NÃO é falha
erro    falha de verdade
```

A numeração de OS do Harmonit é **global e tem buracos**. A varredura sonda
números sequencialmente, então a maioria volta vazia *por natureza*. Na
primeira execução da instrumentação o painel mostrou **100% de falha** no
`ObterOrdemServicoPorNumero` — e o sistema estava são.

Sem essa separação o painel grita sempre, e alerta que grita sempre é alerta
que se aprende a ignorar.

## O que NÃO existe aqui, de propósito

**Alerta por timeout isolado.** A instabilidade do Harmonit é conhecida e
documentada (`10_Inconsistencias.md`). O sinal de evento é o **disjuntor**
(`harmonit_client.estado()`): quando ele abre, aconteceu algo que merece
atenção. Ele aparece no topo da tela.

## Por que mediana e p95, não média

Média esconde cauda longa, e cauda longa é exatamente o problema — tanto do
Harmonit quanto da WESO. Uma rota com mediana de 150ms e p95 de 8s está
quebrada, e a média de 400ms não conta essa história.

## Telas

`/painel/harmonit-historico`, aba `harmonit_historico`:
- cartões (total, erros, vazias, disjuntor)
- grid por serviço com mediana / p95 / máximo
- sub-abas por serviço + detalhe filtrável

## Endpoints

```
GET /painel/api/harmonit/resumo?horas=24
GET /painel/api/harmonit/chamadas?horas=24&servico=X&so_falhas=true
```
