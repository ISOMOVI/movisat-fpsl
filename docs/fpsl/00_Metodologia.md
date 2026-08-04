# FPSL — Metodologia de Desenvolvimento

> Este documento define o processo obrigatório para cada etapa do FPSL.  
> Toda aba de desenvolvimento segue este ciclo antes de avançar.

---

## Princípio

Desenvolvimento auto-dialético por etapa:  
cada parte é proposta, testada contra a realidade e validada antes de servir de base para a próxima.  
A documentação é o produto final — o código é o meio de validá-la.

---

## Ciclo por Etapa

```
┌─────────────────────────────────────────────────────┐
│  1. SPEC                                            │
│     Definir campos, modelos, rota, comportamento    │
│     esperado e casos de erro                        │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  2. IMPLEMENTAÇÃO                                   │
│     Codificar router, model e lógica de             │
│     deduplicação conforme a spec                    │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  3. TESTE                                           │
│     Chamar a rota FPSL com dados reais              │
│     Verificar resposta contra o comportamento       │
│     esperado da spec                                │
└────────────────────┬────────────────────────────────┘
                     │
              ┌──────┴──────┐
              │             │
           ÊXITO         FALHA
              │             │
              │      (até 3 tentativas)
              │             │
              │         Tentativa 1 → ajusta e retesta
              │         Tentativa 2 → ajusta e retesta
              │         Tentativa 3 → ajusta e retesta
              │             │
              │          FALHA PERSISTENTE
              │             │
              │        ┌────▼────────────────────────┐
              │        │  PARAR E REPORTAR           │
              │        │  - Descrever o que falhou   │
              │        │  - Última resposta da API   │
              │        │  - Hipótese do motivo       │
              │        │  - Não avançar              │
              │        └─────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────┐
│  4. DOCUMENTAÇÃO                                    │
│     Atualizar a aba correspondente com:             │
│     - Campos definitivos (obrigatórios / opcionais) │
│     - Comportamento real confirmado                 │
│     - Casos de erro tratados                        │
│     - Exemplo de request e response                 │
│     - Status: ✅ Validado                           │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
              AVANÇAR PARA A PRÓXIMA ABA
```

---

## Status das Abas

| Aba | Etapa | Status |
|-----|-------|--------|
| [01_Cliente.md](01_Cliente.md) | Cliente | ✅ Validado — 2026-06-12 |
| [02_Chip.md](02_Chip.md) | Chip (SIM Card) | ✅ Validado — 2026-06-12 |
| [03_Equipamento.md](03_Equipamento.md) | Equipamento (Rastreador) | ✅ Validado — 2026-06-12 |
| [04_Placa.md](04_Placa.md) | Placa (Veículo) | ✅ Validado — 2026-06-15 |
| [05_Onboarding.md](05_Onboarding.md) | Fluxo Composto | ✅ Validado — 2026-06-12 |
| [06_Deploy.md](06_Deploy.md) | Deploy VPS | ✅ Validado — 2026-06-15 |
| [07_Registro_Local.md](07_Registro_Local.md) | Registro Local SQLite | ✅ Validado — 2026-06-15 |
| [08_Logs.md](08_Logs.md) | Logs de Requisições | ✅ Validado — 2026-06-15 |
| [09_Harmonit_WESO.md](09_Harmonit_WESO.md) | Integração Harmonit × WESO | 📋 Documentado — 2026-06-15 |
| [10_Inconsistencias.md](10_Inconsistencias.md) | Inconsistências e Limitações | 📋 Documentado — 2026-06-15 |
| [11_Seguranca.md](11_Seguranca.md) | Segurança e Auditoria | ✅ Auditado — 2026-06-15 |
| [12_Nginx.md](12_Nginx.md) | Nginx — Instalação e Configuração | ✅ Validado — 2026-06-15 |
| [13_Status.md](13_Status.md) | Status do Projeto e Pendências | 🔄 Atualizado — 2026-06-17 |

---

## Regras

- Nunca avançar sem status ✅ na aba anterior.
- Nunca documentar como validado sem teste real com a API.
- Em caso de divergência entre spec e comportamento real, a realidade vence — atualizar a spec.
- Cada aba é autossuficiente: quem lê a aba entende o que a rota faz sem consultar outros arquivos.
