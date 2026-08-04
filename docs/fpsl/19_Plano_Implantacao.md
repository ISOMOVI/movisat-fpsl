# 19 — Plano de implantação (consolidado)

**Reescrito em 2026-07-27**, depois de um dia inteiro medindo a API. Substitui a versão
da manhã: metade das incógnitas caiu, e apareceram armadilhas que mudam o desenho.

Ordenado por **dependência**. Princípio: **nada escreve na WESO antes de conseguir ler e
casar corretamente** — escrever com de-para torto cria vínculo errado que ninguém percebe.

---

## O que já está resolvido (não replanejar)

| | Como ficou |
|---|---|
| ✅ **Etapa 0 — padrão de placa** | `fpsl_weso/placas.py` como fonte única; extrator alinhado; **72 asserções** |
| ✅ **Pergunta A** — a WESO cria cliente? | **SIM**, automático no `/Veiculos/Cadastro` (`cliente_id 13562`) |
| ✅ **Pergunta D** — o que a desinstalação faz? | `/Veiculos/Excluir` apaga a placa e **deixa equipamento e chip soltos** |
| ✅ Base da WESO padronizada | 5 placas sem espaço + 27 redundâncias → `(RD) ABC 1234` |
| ✅ Mapa de armadilhas | `10_Inconsistencias.md` **B8/B10/B11** |
| ✅ Caminho oficial da oficina | `20_Fluxo_Oficina_e_Reconciliacao.md` |

---

## F1 — Fechar o desenho da desinstalação
**⏱ ~30 min · risco baixo · só 1 escrita em registro de teste próprio**

Único ponto do fluxo ainda em aberto. Testar:

```
POST /Veiculos/Atualizar {veiculo_id, rastreador: {id: 0}}
```

Desvincula o equipamento **mantendo a placa**? Se sim, é a opção B — preserva histórico,
é reversível, e segue o princípio "o que já foi usado não se apaga".
Se não funcionar, a escolha vira A (excluir, irreversível) ou C (não fazer nada).

**Entrega:** o passo `[3']` do fluxo deixa de ser hipótese.

---

## F2 — Espelhos e diff (SÓ LEITURA)
**⏱ média · risco baixo · nenhuma escrita**

Hoje não existe reconciliação nenhuma: o espelho local é de **03/07**. Foi assim que o
`358899055459393` ficou divergente (excluído na WESO, ativo no Harmonit) sem ninguém ver.

**F2.1 — Espelho WESO** (tabela `weso_veiculos`: `veiculo_id`, `placa_crua`, `placa_norm`,
`tem_rd`, `rastreador_id`, `visto_em`, `sumiu_em`) + rastreadores + chips. 1 chamada/dia.
Chave de conciliação = **`rastreador_id`**, não a placa.
⚠️ `/Rastreadores/Consultar` **sem filtro dá 524** — precisa de estratégia própria.

**F2.2 — Espelho Harmonit.** Reusa `import_harmonit_ativos.py`, que já existe.
Chave `numeroSerie` ↔ `equipamento` **normalizado** (o Harmonit tem serial com espaço/tab
grudado — foi o que reduziu 44→15 no F7).

**F2.3 — Diff + relatório no painel.** Equipamento só de um lado · chip divergente · placa
renomeada (mesmo `rastreador_id`) · rastreador `Instalado` sem veículo · chip oculto.
**Relatório, sem correção automática** — o padrão que funcionou hoje: lista revisada antes
de escrever.

**Entrega:** de-para local, cache `veiculos` (0 linhas hoje) populado, divergências
visíveis. **É o P8.**

⚠️ **Paginação não funciona em nenhum dos dois sistemas** — pedir páginas devolve a base
inteira toda vez. Nunca paginar em loop.

---

## F3 — Resolução da placa no termo
**⏱ média · risco baixo · depende de F2**

Cada placa extraída ganha status **antes** de gerar OS:

| Status | Ação |
|---|---|
| ✅ encontrada | segue |
| 🆕 não existe | vai pro cadastro (F4) |
| ⚠️ ambígua (>1 registro) | **bloqueia** e mostra candidatos |
| 🔁 renomeada (mesmo `rastreador_id`) | avisa e usa a atual |

Mesmo padrão do aviso de vínculo (409), que já provou valor: o operador vê o problema
antes, não depois.

---

## F4 — Cadastro de cliente, veículo e equipamento (P1/P2)
**⏱ grande · risco médio · depende de F3**

É a **pré-condição do fluxo oficial**: a oficina vincula, nunca cria.

- **Cliente** — `/Cliente/CadastrarOuAtualizar`. ⚠️ `codigoIBGE` obrigatório e ausente no
  termo (lookup por CEP/cidade). A WESO cria sozinha, mas com **os dados que enviarmos** —
  cadastrar direito antes é qualidade de dado.
- **Veículo** — `/Veiculo/Incluir`. ⚠️ `marca` tem que bater com `ObterTipoEMarca`, e vários
  valores lá **têm espaço no fim** (`"renault "`). `renavam` não existe no schema.
- **Equipamento com chip** — `/Rastreadores/Cadastro` com `simCard:{iccId}`; o chip nasce
  junto **aqui**, não pelo veículo.
- **`A DEFINIR` + nº do termo** — ⛔ **pendente de definição do usuário** (formato exato; e
  se a placa real renomeia o registro — recomendado, `Atualizar` preserva `rastreador_id` —
  ou cria outro).

---

## F5 — Fase 2 da oficina: escrita real
**⏱ média · risco ALTO · depende de F1 + F4**

O fluxo de `20_Fluxo_Oficina_e_Reconciliacao.md`, por trás do toggle
`oficina_registro_ativo`, com **dedup por evento** e **read-after-write** em toda escrita.

**As armadilhas que este passo precisa respeitar** (todas medidas em 27/07):

| # | Armadilha | Estrago |
|---|---|---|
| 1 | Rastreador **com chip** → `/Veiculos/Cadastro` devolve **500 e GRAVA** (2/2). É o caso normal de campo | retentativa cria **veículo duplicado** |
| 2 | `400` do bloco `rastreador` **cria o chip** assim mesmo | chip órfão por tentativa |
| 3 | `simCard: null` não desvincula (só `{id:0}`) | acha que desvinculou |
| 4 | `situacao` do rastreador é **read-only** | equipamento `Instalado` sem veículo |
| 5 | `situacao:"Inativo"` no chip não grava (é o valor **documentado**) | acha que inativou |
| 6 | `/SimCard/Excluir` por `iccId` pega registro **errado** | usar `simcard_id` |
| 7 | `"Cancelado"` **oculta** o chip da listagem | rotina recria → duplica |

> **A WESO mente no código de retorno nos dois sentidos:** `200 success` pode não ter feito
> nada; `400/500` pode ter gravado tudo. **A única fonte de verdade é reler o estado.**

**Fazer 1 escrita real primeiro**, conferir, e só então ligar o automático.

---

## F6 — Automação e alertas
**⏱ pequena · depende de F5**

Varredura sincroniza sozinha; alertas para equipamento ausente, divergência nova de chip em
ativo de campo, e crescimento anormal do diff.

---

## Caminho crítico

```
F1 (desinstalação)  ─┐
                     ├─>  F5 (escrita)  ─>  F6 (automático)
F2 (espelho+diff) ─> F3 (resolução) ─> F4 (cadastro) ─┘
```

**F1, F2 e F3 são independentes de qualquer decisão pendente** — dá pra fazer já.
F2 e F3 são **100% leitura**.

## Bloqueado no usuário

| # | O quê | Trava |
|---|---|---|
| 1 | Formato exato do `A DEFINIR` + nº do termo | F4 |
| 2 | Placa real: renomeia o registro ou cria novo? | F4 |
| 3 | As 3 duplicadas sem RD (`GFI 3G42`, `SVS 6J23`, `EBU 1968`) — corrigir na base ou regra de desempate? | F2/F3 |
| 4 | Ok para a escrita real em produção | F5 |
| 5 | Destino dos 3 veículos de teste da Velasco (87621/87622/87623) | — |

## Fora deste plano, de propósito

Transferência → tipos 814/815 (*aguarda ok*) · mapa acessório→modelo (*usuário vai enviar*)
· reescrita dos 12 testes de Oficina · encargo de rescisão com redação alternativa · P5
(continuação de página nos outros parsers) · 16 docstrings de módulo.
