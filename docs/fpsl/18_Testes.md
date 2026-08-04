# 18 — Testes do FPSL

**Criado em 2026-07-27.** Antes disso o projeto não tinha teste automatizado nenhum:
o que existia era `test_extracao.py`, um script de 21 linhas que **imprimia JSON e não
afirmava nada** — apontando para `/tmp/testes_pdf/`, que qualquer reboot apaga. Foi
removido nesta data.

Tudo aqui é **só leitura**: nenhum teste escreve na WESO, no Harmonit, nem em produção.

---

## `tests/teste_regressao_extracao.py` — extração de termos

**45 asserções sobre os 9 documentos REAIS**, versionados em `tests/fixtures/`.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_regressao_extracao.py
```

### Por que existe

O extrator já quebrou **em silêncio** — nenhum erro, nenhum log, dado sumindo:

| Bug histórico | O que acontecia | Guarda no teste |
|---|---|---|
| Transferência roteada pro parser errado (16/07) | 14 de 28 placas sumiam; cliente nunca capturado | `[9] placas == 28` |
| Tabela em 2 colunas (16/07) | `next()` pegava só a 1ª coluna | `[2] placas == 28` |
| Continuação de página (23/07) | Rescisão lia só a 1ª página: 12 em vez de 26 | `[5] veiculos == 26` |
| Comodato × cobrar (20/07) | Item sem indicação de origem do custo | `[1] todo item tem comodato_ou_aquisicao` |
| Acessório com bullet `▶` (23/07) | Acessório não virava item de OS | `[6] acessório do bullet virou item` |
| Termo errado (rescisão que é transferência) | Gerava OS do tipo errado | `[7] alerta_transferencia` |

**Cada número travado é um bug que já aconteceu.** Não são valores arbitrários.

### Baseline (conferido a mão em 2026-07-27, não só "o que saiu")

| fixture | perfil | termo | placas | itens | observação |
|---|---|---|---|---|---|
| `cliente_novo.pdf` | cliente_novo | 8768 | 2 | 13 | FAG |
| `cliente_novo2.pdf` | cliente_novo | 8771 | 28 | 5 | 2 colunas |
| `aditivo2.pdf` | aditivo | 8782 | 1 | 8 | |
| `trz_8790_aditivo.pdf` | aditivo | 8790 | 1 | 7 | |
| `rescisao.pdf` | rescisao | 8788 | **19** | 4 | `veiculos`=26 |
| `substituicao.pdf` | substituicao | 8786 | 0 | 1 | usa `pares` |
| `termo_errado.pdf` | rescisao | 8787 | 1 | 0 | dispara alerta |
| `transferencia_existente.pdf` | transferencia | 8785 | 1 | 7 | |
| `transferencia_novo.pdf` | transferencia | 8771 | 28 | 5 | |

### Duas armadilhas de leitura (investigadas em 27/07, não são bug)

1. **Rescisão: `veiculos`=26 mas `placas`=19.** `veiculos` é a lista crua da tabela e
   inclui **7 linhas sem placa**; `placas` só as que têm (26−7=19). O teste trava os
   **dois** de propósito: se um mudar sem o outro, algo regrediu. (Ainda há 3 placas
   repetidas dentro de `veiculos` — `TTW 4C85`, `TTW 3B64`, `TUU 2I29` — que é o caso
   tratado pelo dedup na geração de OS, não erro de extração.)
2. **Substituição tem `placas`=0 e isso está certo.** Esse parser não usa `placas`: usa
   **`pares`** (`placa_saida`/`placa_entrada`/`acessorios_entrada`), porque substituição
   é sempre veículo que sai × veículo que entra.

### Quando um número mudar

**Não atualize o número para fazer passar.** Descubra primeiro se o documento mudou ou
se o extrator regrediu. `tests/dump_extracao.py` imprime o que o extrator devolve hoje,
para comparar antes de decidir.

---

## `teste_perfis.py` (raiz) — perfis de acesso do painel

**22 asserções** (2026-07-29: entrou a aba `placas`, e o número de abas é
travado de propósito — aba nova sem pensar em permissão faz o teste falhar).
Owner enxerga tudo; operador só as abas marcadas; aba não concedida
dá 403; aba removida vira 403 na hora; owner não pode ser desativado. Gera o token
internamente — **nunca passa senha por linha de comando**. Cria um operador de teste e
o remove no fim. Detalhe em `17_Perfis_Acesso.md`.

```bash
cd /home/claude/fpsl_weso && venv/bin/python teste_perfis.py
```

---

## `analisar_placas_weso.py` (raiz) — diagnóstico, não teste

Só leitura, sobre a base real da WESO: formato das placas (com/sem espaço × convencional
/ Mercosul / chassi), campos que o `Consultar` devolve, placas repetidas. Foi o que
fechou o **W1** e produziu o **B8** em `10_Inconsistencias.md`.

---

## O que ainda NÃO tem teste

- Geração de OS (`os_router.gerar_os`) — o caminho crítico, hoje só validado a mão com OS reais
- Varredura de OS (`os_scan_router`) — sem cobertura
- Escrita na WESO (`/weso/os/adicionar`) — a Fase 2 vai precisar de teste próprio
- Os 12 testes de Oficina, que validavam o fluxo descartado e precisam ser reescritos

---

## `tests/teste_higiene_placas_weso.py` — higiene da base WESO

**11 asserções. TESTE DE INTEGRAÇÃO: bate na WESO de verdade (~2,3s), somente
leitura.** Criado em 2026-07-29 como etapa 4 do plano 21.

Falha se aparecer placa com espaço nas pontas, espaço duplo, minúscula ou
**colisão nova**. Também verifica que a leitura tolerante (`weso_lookup`)
continua achando a mesma placa em 4 grafias diferentes.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_higiene_placas_weso.py
```

⚠️ **Na primeira execução ele já pegou dois casos reais** — uma placa cadastrada
com espaço *durante* a sessão que limpava a base, e uma ambiguidade que a nossa
própria normalização cria (`OBD 3` × `OBD 3*`). Ver `21_Plano_Higiene_Placas.md`.

---

## Contagem atual (2026-07-29)

| Arquivo | Asserções |
|---|---|
| `tests/teste_regressao_extracao.py` | 45 |
| `tests/teste_placas.py` | 72 |
| `tests/teste_continuacao_pagina.py` | 11 |
| `tests/teste_higiene_placas_weso.py` | 11 |
| `tests/teste_disjuntor_harmonit.py` | 9 |
| `teste_perfis.py` *(raiz — fora do padrão)* | 22 |
| **Total** | **170** |

⚠️ `teste_perfis.py` está na raiz e não em `tests/`, ao contrário de todos os
outros. Passa despercebido em varredura por diretório.

🚨 **`py_compile` NÃO substitui rodar os testes — isso aconteceu QUATRO
vezes em um dia (2026-07-29):** import faltando (`placas`), chamada na
função errada (`NameError: veiculos`), `timedelta` sem import, e
`_conectar` em vez de `_connect`. Os quatro compilaram.
Sempre conferir o **símbolo no namespace do módulo**, não só compilar.

🚨 **Resultado absurdo é sinal, não ruído.** A prévia de cliente dizia
que um CPF inventado já existia. Foi isso que revelou que o Harmonit
responde "não encontrado" em formato diferente de "encontrado".

**Nota original:** Em 2026-07-29, duas mudanças
compilaram e quebrariam em produção: um `placas.formatar()` sem o import (a
âncora do patch tinha os nomes em ordem invertida) e uma chamada inserida na
função errada (`NameError: veiculos`). Nos dois casos só o teste pegou.
