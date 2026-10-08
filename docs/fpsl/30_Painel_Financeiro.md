# 30 — Painel Financeiro: Conferência de Fechamento e a frente de Fechamentos

> **Criado:** 2026-10-01. Cobre a `FIN_1.1` (no ar desde 29/09, que nasceu sem
> esta etapa 4 do ciclo) e a frente nova "Conferência + Ação" proposta em 01/10.
> Plano completo da frente: `C:\Users\Lenovo\.claude\plans\organize-conforme-a-metodologia-squishy-melody.md`.
>
> Origem marcada em toda lista: 🔵 **demanda** (tem frase dele) · 🟡 **sugestão** (minha).

---

## Status

| Peça | Estado |
|---|---|
| `FIN_1.1` Conferência de Fechamento | ✅ no ar desde 29/09. Rotina de 1h **LIGADA** desde ~19:00 de 01/10 (`conferencia_fechamento_ativa = true`) |
| **E1** `os_historico` guarda `materiais_json` e `situacao_id` | ✅ no ar 01/10 — ver `16_Historico_OS_Scan.md` |
| E1b interruptor na tela | ✅ no ar 01/10 15:20 |
| Ordenar `FIN_1.1` pela data real de finalização | ✅ no ar 01/10 15:52 (`ObterTimeLine`) |
| E2 ID × modelo no Histórico de OS | ✅ no ar 01/10 ~18:00 |
| E3 quatro validações + porta 15694 + rotina | ✅ no ar 01/10 ~19:00 |
| **`FIN_2.1` Fechamento de Contas dos Técnicos** | ✅ no ar 06/10 (kanban, recibo, planilha) |
| `FIN_2.1` pass de UX/UI | ✅ no ar 07/10 (commit `e11f8b7`) — spinner/confirmação, miniatura+modal, Iniciar Conferência real, busca por e-mail |
| `FIN_2.1` trava de OS, cancelamento, registro, relatórios | ✅ no ar 07/10 (commit `4277f60`) |
| E4 Ação manual no DataScope / baixa da OS no Harmonit | 📋 especificado; depende de decisões dele |
| E5 corrigir modelo na OS | 📋 só depois de a E2 medir o volume |

⚠️ **Falta ele validar no navegador** o `FIN_2.1` e as duas rodadas de 07/10.

---

## 1. A `FIN_1.1` como está

🔵 *"saber quais OS finalizadas realmente já tiveram o serviço executado no
Datascope e WESO"*. A OS "Finalizado" no Harmonit é a alegação de quem fechou;
a rotina confere se os outros dois sistemas concordam.

| Peça | Onde |
|---|---|
| Rotina (1h, atrás de flag) | `fpsl_weso/services/conferencia_fechamento.py` |
| Cliente DataScope (só leitura, disjuntor) | `fpsl_weso/datascope_client.py` |
| Router (só leitura + "Rodar agora") | `painel/routers/conferencia_fechamento_router.py` — `GET /painel/api/conferencia-fechamento`, `POST .../rodar-agora`, aba `financeiro` |
| Tela | `frontend/conferencia_fechamento.html`, rota `/painel/conferencia-fechamento` |
| Tabelas | `conferencia_fechamento` (1 linha por OS conferida), `datascope_respostas` (cache incremental do form "Serviços Técnicos") |
| Flag | `config.conferencia_fechamento_ativa`, nasce `false`. **Hoje só liga por SQL/API** — `config.html` não tem interruptor desde 17/08 |

A cada rodada: relê o status das OS recentes ainda não `Finalizado`
(`os_nao_finalizadas_recentes`), sincroniza o DataScope incrementalmente
(`date_modified=true&order_date=true`, cursor `updated_at|form_answer_id`), e
para cada OS que virou `Finalizado` e não foi conferida, cruza:

- **DataScope**: `Finalizado` → ok; estado de problema → falha; qualquer outro
  ou sem resposta → `None` (**ainda não fechou lá, não é erro**).
- **WESO**: por linha de `oficina[]`, `status 1` espera `Instalado`, `status 2`
  espera `Estoque`. Sem oficina → `None`.

⚠️ A lista exibe por `conferido_em DESC` — **quando a rotina conferiu**, não
quando a OS finalizou. Ver seção 3.

---

## 2. API do DataScope — o que foi medido ao vivo (01/10)

Doc oficial: `https://dscope.github.io/docs/`. Base
`https://www.mydatascope.com/api/external`, header `Authorization: <chave>` sem
`Bearer`. Chave no `.env` do FPSL, nunca inline.

### Dois sistemas paralelos, não hierárquicos

| | Tarefa | Resposta de formulário |
|---|---|---|
| Endpoint | `GET /task_assigns` | `GET /v5/answers` |
| Status | campo `status`: `assigned` / `accepted` / `rejected` / `completed` / `incomplete` | campo `form_state` (estados da conta, ver abaixo) |
| Na tela do DataScope | **"Completado"** (fora do formulário) | o status **dentro** do formulário |
| Muda como | só pelo técnico no app | `change_state`, por gente ou por API |

**Provado:** depois de três trocas de `form_state` por API, a tarefa seguiu
`completed` — imune. Mostrar só um dos dois rótulos esconde o outro.

🚨 **`assign_id` da tarefa é sequência própria do DataScope**, não o número da
OS (ex.: 11179…11494 em jul-ago; 11936 na sandbox). O `description` da tarefa
traz tipo de serviço, placa, serial e modelo — ex.:
`MANUTENÇÃO COM TROCA: FKJ 0182 | SAIRÁ: 205782133 | ENTRARÁ: 90712483` —
**mas não traz o número da OS**. O único elo OS ↔ resposta é o campo de texto
livre `Nº da O.S.`, digitado pelo técnico, que erra (na sandbox: tarefa 11936,
campo digitado 16991).

### Estados (`GET /list_states`)

| key | identifier |
|---|---|
| 9535 | Finalizado |
| 9536 | Rejeitado pela área técnica |
| 9537 | Informações não coincidem |
| 74341 | Aprovado análise técnica |
| 74342 | Cancelado |
| 98352 | Finalizado com divergências |
| 102712 | Rejeitado pela área Financeira |
| 119610 | Duplicidade |

Não existe estado "suporte técnico" — o mais próximo é **74341 Aprovado
análise técnica**. Resposta recém-enviada tem `form_state = null`.

### Escrita — existe e funciona

`fpsl_weso/datascope_client.py` é **GET-only por decisão de projeto**, não por
limite da API.

**`POST /change_state`** — muda o `form_state` de uma resposta existente.

```
POST /api/external/change_state
form_name=Serviços Técnicos&form_code=356430079894290&form_state_id=9535

→ 200 {"status":"ok","form_answer":{"form_state_id":9535,"id":32090710,
        "form_id":455616,"code":"356430079894290","task_assign_id":4530005,...}}
```

- Funciona nos dois sentidos e repetidamente, **sem trava de prazo** (testado
  11 min depois do envio, entre estados "fechados" e intermediários).
- A tela do DataScope reflete na hora, e mudança feita na tela aparece na API
  com o `updated_at` exato.
- ⚠️ Dispara os webhooks configurados e **manda push para o técnico** que
  enviou a resposta.
- 🚨 **Não volta para `null`.** `form_state_id=""` → `400` com corpo vazio, sem
  efeito. Depois da primeira classificação, só se troca entre estados.

**`POST /change_form_answer`** — muda o valor de uma **pergunta**
(`question_name` + `question_value`, `subform_index` opcional). **Não altera
`form_state`** — a doc é explícita.

**Não existe:** criar resposta do zero por API (só o app cria); mudar status de
tarefa; listar formulários (só aparecem puxando respostas).

### Armadilhas

- `/v5/answers` **clampa a janela em ~90 dias a partir do `start`**, mesmo com
  `end` mais distante, sem erro. Histórico longo = janelar de 90 em 90.
- **Rate limit sem documentação.** `429` medido após ~15-20 chamadas em
  minutos, corpo HTML, **sem `Retry-After`**; voltou em ~15-20 s. O disjuntor
  atual (3 falhas → 600 s aberto) trataria isso como queda — corrigir junto com
  qualquer escrita (E4).
- A conta tem **9 formulários**; só "Serviços Técnicos" (455616) é usado pelo
  FPSL. Os outros: Retirada pelo cliente (529131), Transferência de
  titularidade — Migração (491806) e — Remoção (491809), Visita improdutiva
  (448819), Ressarcimento (492192), Entrega de materiais (32633), Devolução de
  materiais (490465), Upgrade (47354).

### Sandbox — feita para isso, pode escrever

🔵 *"é uma OS real criada para teste, nela podemos testar rotas e mudanças de
estado ida e volta bem como dados e etc"*:

| Sistema | Identificador |
|---|---|
| Harmonit | OS 16991 |
| WESO | placa `TESTE_DATASCOPE` |
| DataScope | tarefa `assign_id 11936` (id 4530005), resposta `code 356430079894290` |

Teste que escreve se faz **aqui**, nunca em OS de cliente.

---

## 3. Harmonit — campos que a frente usa

### Situação de OS (`situacaoId`) ≠ status (`status`/`statusStr`)

São dois campos diferentes.

- `statusStr` — valores medidos: `Nova`, `Iniciada`, `Finalizado`. É o que a
  `FIN_1.1` usa hoje.
- `situacaoId` — catálogo `GET /SituacaoOrdemServico/ObterSituacoesOS`
  (`empresaId 98`): 38 Nova sollicitação · 251 Configuração · 677 Envio dos
  Equipamentos · 890 Agendamento · 1316 Serviço Agendado · **15694 Serviço
  Realizado** · 15695 Pós Venda · 15696 Aguardando Devolução do Equipamento ·
  15746 Financeiro · 15747 Aguardando Chegada do Fornecedor · 15797 Aguardando
  aviso prévio.

O FPSL **já grava** situação ao criar OS: `SITUACAO_NOVA_ID = 38` e
`SITUACAO_FINANCEIRO_ID = 15746` (`painel/operacoes_config.py:34-35`). Nada no
projeto lê nem escreve 15694. Medido em 24 OS com oficina: só 0 (criadas por
fora) ou 38 (criadas pelo FPSL); nenhuma em 15694.

### Data real de finalização — `ObterTimeLine`

`os_historico` só guarda o status **atual**, sobrescrito a cada varredura;
`atualizado_em` é tocado por qualquer rotina. Nenhum dos dois é "quando
finalizou". A fonte é:

```
GET /OrdemServico/ObterTimeLine?osId=827955      (OS 16450)
→ [{"status":2,"statusDesc":"Nova","usuario":"Iago Santos do Ó Souza",
    "data":"01/07/2026 10:18:18", ...},
   {"status":4,"statusDesc":"Finalizado","usuario":"Karla Alves",
    "data":"30/07/2026 17:04:30", ...}]
```

Traz **quem** e **quando**. `data` vem em `dd/mm/yyyy HH:MM:SS`, não ISO.
Parâmetro é o `id` interno da OS (`osId`), não o número.

### Tipo × problema

`tipo` (catálogo `TipoOrdemServico`) é a **ação técnica**; `problema`
(catálogo `Problema`) é o **motivo de negócio** (RESCISÃO, MANUTENÇÃO…). Quem
prevê instalação/desinstalação na oficina é o `tipo`.

---

## 4. Lista de regras — tipo × oficina × WESO

🔵 *"levante a liste de regras"*. Validação **por linha de oficina**, nunca por
OS (há OS com 3 linhas).

| tipo | descrição | oficina | WESO depois |
|---|---|---|---|
| 76 | Instalação rastreador | `1` | Instalado na placa; produto = de-para do modelo |
| 57 | Retirada | `2` | Estoque (🔵 *"tirar a placa que libera o ID para uso"*) |
| 72 | Substituição/Instalação | `1` | novo Instalado |
| 73 | Substituição/Retirada | `2` | antigo em Estoque |
| 971 | Manutenção com Troca/Entrada | `1` | novo Instalado |
| 970 | Manutenção com Troca/Saída | `2` | antigo em Estoque |
| 815 | Trans. Titularidade/Instalação | `1` | Instalado, novo titular |
| 814 | Trans. Titularidade/Retirada | `2` | Estoque |
| 55 | Manutenção | `1`, `2` ou `1`+`2` | par na mesma placa = troca |
| 77 / 78 | Upgrade / Downgrade | `1`+`2` | troca na mesma placa |
| 1037 | Ativação de backup | `1` | segundo ID Instalado |
| 75 / 574 | Entrega / Devolução de Equipamentos | nenhuma | sem mudança |
| 1785 | Teste ou Treinamento | — | fora do escopo |
| 1782 / 1783 / 1784 | Demanda Interna / Solicitação de Cliente / Ordem de Serviço | **sem regra** | aparecem com oficina em OS real — decisão pendente |

**Troca:** `1` e `2` na mesma placa = valida o par; em placas diferentes =
dois serviços.

**Modelo:** compara-se **id do produto**, nunca texto. WESO `Suntech ST310` →
de-para `painel_modelos_produto` → `harmonit_produto_id 20314`; material da OS
`ST310U` tem `idProduto 20314`. **Batem.** Comparar string acusaria falso.
Material-rastreador se reconhece por `operacoes_os.eh_rastreador()`. Modelo sem
de-para (NT2x, ST500, ST4945S, NT11, Concox GT06 — 84 unidades) é **cinza**,
não divergência.

---

## 5. Desenho da frente: Conferência e Ação

🔵 *"o painel de fechamentos terá duas funções, uma de conferencia e outra de ação"*.

**Porta de entrada:** só OS em **15694 "Serviço Realizado"**.

**Conferência (lê):** grid das OS com oficina, quatro vereditos — ação × tipo ·
situação · WESO placa×ID×modelo · DataScope. **"Ainda não aconteceu" é cinza,
nunca vermelho.**

**Ação (escreve):** uma só — `change_state` → **74341 Aprovado análise
técnica**, e só com os quatro resolvidos. 🟡 Nasce manual (botão por linha),
com trilha `conferencia_acao` (quem, quando, de, para, resultado), idempotente,
atrás de `conferencia_acao_ativa = false`.

**Interruptor:** 🔵 *"coloque interruptor nesse recurso, na propria tela
dele"* — cada rotina desta frente tem a chave **na tela dela**, não em
`/config`. ⚠️ Oposto da convenção do MoviZap (`CFG_7.1`); são projetos
diferentes.

**Sobreposição com `HST_4.1`:** a rotina de Operações também lê oficina, mas
só das OS que **ela** gerou, só desinstalação, e como gatilho para reler a
WESO. São complementares. A conferência deve **ler** `operacoes_espera` para
não contradizer a rotina de Operações.

---

## 6. Decisões

```
Objetivo:     a Ação só considera OS que uma pessoa marcou como concluída
Hoje:         situacaoId 15694 "Serviço Realizado" é a porta de entrada
Por quê:      🔵 "será feito justamente por uma pessoa mesmo, por isso que a
              rotina valida ele primeiro e parte dali" (01/10)
Reavaliar se: a equipe parar de mover a situação — a fila esvazia
```

```
Objetivo:     ligar/desligar cada rotina sem SQL
Hoje:         interruptor na tela da própria rotina, não em /config
Por quê:      🔵 "coloque interruptor nesse recurso, na propria tela dele" (01/10)
Reavaliar se: as rotinas da frente passarem de três e pedirem painel único
```

```
Objetivo:     poder testar escrita sem tocar dado de cliente
Hoje:         sandbox OS 16991 / TESTE_DATASCOPE / resposta 356430079894290
Por quê:      🔵 "é uma OS real criada para teste" (01/10)
Reavaliar se: a sandbox for apagada em algum dos três sistemas
```

---

## 7. Lacunas conhecidas

1. Nada move a situação para 15694 hoje — a Ação nasce sem fila.
2. Elo OS ↔ resposta do DataScope é texto livre digitado (`Nº da O.S.`).
3. `form_state` não volta para `null`.
4. Rate limit do DataScope sem documentação.
5. Cache da WESO (`/home/claude/weso_cache/weso.db`) atrasa até 24 h (04:15).
6. Não há cópia local de produtos do Harmonit; o de-para tem 24 linhas. O campo
   `grupo` de `/Produto/ObterProdutos` classificaria rastreador × acessório e
   nunca é usado.
7. 🚨 `painel_modelos_produto` tem 999,90 editado à mão em ST300/ST310/ST340
   que o seed não tem — **rodar `seed_modelos_produto.py` apaga**.


---

## ✅ 01/10 — E1b: interruptor na própria tela (NO AR 15:20)

🔵 *"coloque interruptor nesse recurso, na propria tela dele"*. Resolve a lacuna
de a `FIN_1.1` só poder ser ligada por SQL (`config.html` não tem interruptor
nenhum desde 17/08).

**Regra que nasce aqui, e vale para esta frente inteira:** *cada rotina que roda
sozinha nasce desligada e tem o interruptor na tela dela*. ⚠️ É o **oposto** da
convenção do MoviZap (`CFG_7.1`, interruptor em `/config` › Geral). Projetos
diferentes, decisão desta obra — não "corrigir" para o padrão do outro.

| Rota | Tranca | Faz |
|---|---|---|
| `GET /painel/api/conferencia-fechamento/interruptor` | `requer_aba("financeiro")` | `{ativa, intervalo_min}` |
| `PUT .../interruptor` | `requer_aba("config")` | grava `config.conferencia_fechamento_ativa` e **relê** antes de responder |

🚨 **A tranca do PUT é `requer_aba("config")`, não `get_owner_painel`.** As duas
barram quem não é dono — `config` está em `PERMISSOES_SO_OWNER` e
`abas.pode_acessar` devolve `False` para permissão não concedível. A diferença é
o **recado**: `get_owner_painel` responderia *"Só o proprietário do painel
gerencia usuários"* para quem tentou ligar uma rotina. Tranca certa, recado
certo. De quebra, não edita `auth.py`.

**Na tela:** chave no `.painel-ctrl`, ao lado do "Rodar agora". O estado vem
**sempre do servidor** (nada memorizado no navegador: a flag pode ter sido
mudada por outra pessoa ou por SQL), e depois do `PUT` a tela pinta o que o
servidor devolveu, não o que foi clicado. Quem não é dono vê o estado com a
chave desabilitada e a legenda *"Só o proprietário liga"*.

**Dois textos trocados, por `M12`** — a tela dizia *"Rotina a cada 1h"* como se
rodasse, estando desligada:

- o subtítulo não afirma mais que roda;
- ligada, a legenda diz *"Roda sozinha a cada 60 min — ligar não roda na hora"*,
  porque o laço só relê a flag no próximo ciclo (`INTERVALO_ROTINA`);
- o "Rodar agora" ganhou *"Roda na hora, ligada ou não"* — ele é ação de gente e
  **independe do interruptor**.

**Testado ao vivo:** `GET` owner → `{ativa: false, intervalo_min: 60}` · `GET` e
`PUT` de atendente sem a aba → **403** · sem token → **401** · `PUT` do owner
ligando → `true` **e o banco com `true`** · desligando → `false` e banco `false`.
A prova é o `SELECT` na tabela `config`, não a resposta HTTP.

**Suíte:** `teste_roteadores_painel` 82 ✓ (as 4 novas linhas de tranca),
`teste_barra_status` 91 ✓, `teste_registro_telas` 44 ✓, `teste_perfis` 26 ✓.
Nenhuma tela nova nasceu, então nenhuma contagem travada mudou.

⚠️ **Navegador: falta ele.** Validei a sintaxe do JS (`node --check`) e que a
página responde 200, mas `M9` continua valendo — placar verde não vê tela.

### Baseline de integridade da Operações (Passo 0, antes de tudo)

Rodado para provar que a E1 não tocou a Operações: **453 verificações, 0 falhas**
— `teste_operacoes_f1` 57 · `f2` 96 · `f4` 116 · `f6` 41 ·
`teste_aba_ponta_a_ponta` 35 · `teste_tela_clonada` 18 · `teste_acabamento` 28 ·
`teste_tela_operacoes` 62. Os três que escrevem no banco (`f3`, `f5`, `f5b`) não
foram rodados — ficam para quando ele autorizar.


---

## ✅ 01/10 — Ordenação pela data real de finalização (NO AR 15:52)

🔵 *"exibir ordenadamente o que foi finalizado mais antiamente no topo, e assim
segue"*. A `FIN_1.1` é **fila de trabalho**, não diário.

**Por que `conferido_em` não servia:** as 76 primeiras linhas da
`conferencia_fechamento` foram gravadas **no mesmo intervalo de 16 segundos** (a
validação de 29/09). Ordenar por ela não ordenava nada.

### A fonte: `ObterTimeLine`

É o único lugar que tem a data real, e traz **quem** também:

```
GET /OrdemServico/ObterTimeLine?osId=827955        (OS 16450)
→ status 2 "Nova"       01/07/2026 10:18:18  Iago Santos do Ó Souza
  status 4 "Finalizado" 30/07/2026 17:04:30  Karla Alves
```

Códigos de `status` medidos (16450 e 16991): **1** Agendado · **2** Nova ·
**4** Finalizado · **7** Reagendado · **14** Cancelamento da Conclusão. Status
fora dessa lista é **ignorado** — supor significado para código nunca visto é o
que o `M15` cobra.

🚨 **A ARMADILHA: FINALIZAÇÃO SE DESFAZ.** A 16991 tem `Finalizado` (10:06) e
**depois** `Cancelamento da Conclusão` (11:22). Quem lesse só o último
`Finalizado` diria que ela está finalizada desde 10:06 — e **não está**. Regra:
vale o último `Finalizado` **que não foi cancelado depois**; se foi, a data é
nula e a OS entra na fila pela data da conferência.

Outros cuidados, todos com teste: a função **ordena pela data que ela mesma
lê**, não confia na ordem da API; `data` vem em Brasília sem fuso no texto
(deslocamento fixo de −3 h, o Brasil não tem horário de verão desde 2019);
data ilegível vira `None`, nunca uma data errada ordenando a fila.

### Colunas novas

| Tabela | Coluna | Para quê |
|---|---|---|
| `conferencia_fechamento` | `finalizado_em`, `finalizado_por` | a data real e quem finalizou |
| `os_historico` | **`os_id`** | o id INTERNO da OS (**≠ `numero_os`**), que é o que `ObterTimeLine` exige. A varredura já o recebia e descartava |

Ordenação: `ORDER BY COALESCE(finalizado_em, conferido_em) ASC`. Sem o
`COALESCE`, toda linha sem data iria para uma ponta só e a fila mentiria.

### 🚨 O defeito que CRESCIA com o tempo, e como se resolveu

A primeira versão deixava para a varredura preencher o `os_id`. Mas o resync
cobre as **400 OS mais recentes**, e as linhas da conferência envelhecem: toda
OS que sai dessa janela **nunca mais** receberia `os_id`, e ficaria sem data
para sempre. Medido na hora: 16450, 16551 e 16552 já estavam nesse caso, e o
número só cresceria.

Correção: `_os_id_resolvido()` busca o id no Harmonit **uma vez na vida da OS**
quando ele falta, e grava. Depois disso o backfill se cura sozinho.

### Testado

**Função pura, 9 de 9** (`finalizacao_da_timeline`): a 16450 com data certa já
convertida para UTC · a 16991 cancelada devolvendo sem data · cancelou-e-
refinalizou valendo a nova · resposta invertida dando o mesmo resultado · lista
vazia · data ilegível · evento sem data · status desconhecido ignorado ·
finalizado sem usuário.

**Ao vivo, três rodadas até convergir:** 60 datas na 1ª (teto por rodada), 14 na
2ª, e **3 na 3ª — justamente as que exigiam resolver o `os_id`**. Fim:
**99 de 99 linhas com data**. Pela API, a lista sai da 16487 (06/07, Karla
Alves) à 16964 (29/09), e a sequência de datas é crescente de verdade.

**Suíte:** `roteadores` 82 ✓ · `barra_status` 91 ✓ · `registro_telas` 44 ✓ ·
`perfis` 26 ✓ · `operacoes_f1` 57 ✓ · **`operacoes_f5b` 38 ✓** (o único que
escreve em `os_historico`) · `aba_ponta_a_ponta` 35 ✓. Dados reais intactos:
536 OS, 499 com materiais e `os_id`.

⚠️ **Navegador: falta ele** (`M9`). Validei sintaxe do JS e a página em 200.

### Na tela

Coluna "Finalizada em" com a data e, abaixo, quem finalizou. Sem data vira
badge cinza **"sem data"** — e o subtítulo explica: *"A mais antiga vem
primeiro... 'Sem data' é OS cuja finalização foi cancelada ou que ainda não foi
lida; essas entram pela data da conferência."* O `rodar-agora` passou a reportar
quantas datas preencheu.


---

## ✅ 01/10 — E2: sub-aba "ID × modelo" no Histórico de OS (NO AR ~18:00)

🔵 *"verifique na rotina de historico de OS, que nas buscas dele (mesmo que seja
outra aba dento) verificar se o ID weso e modelo batem com os da OS"*.

**Só leitura, e sem nenhuma chamada de API**: sai do `os_historico` e do cache
da WESO (`/home/claude/weso_cache/`, atualizado 04:15). A tela mostra a idade
do cache sempre — serviço feito hoje aparece com a WESO de ontem.

| Peça | Onde |
|---|---|
| Regra (função pura, testável) | **novo** `fpsl_weso/services/conferencia_oficina.py` — nada importado de `painel/operacoes_*` |
| Endpoint | `GET /painel/api/os-scan/conferencia-oficina?limit=&so_divergentes=` — aba `os_historico`, a mesma |
| Tela | sub-aba "ID × modelo" em `frontend/os_historico.html`, padrão `.subabas` copiado do `harmonit_historico.html` |
| Teste | **novo** `tests/teste_conferencia_oficina.py` — **73 verificações**, todas com dublê, sem tocar banco nem cache |

Nenhuma tela nova nasceu: `telas.py` e as contagens travadas não mudam. A rota
entrou na `ROTAS` do `teste_roteadores_painel` (82 → 85).

### Três vereditos por OS

1. **Ação × `problema`** — a instalação/retirada da oficina bate com o que o
   `problema` da OS prevê.
2. **Vínculo na WESO** — a série está (instalação) ou saiu (retirada) daquela placa.
3. **Modelo** — o produto que o de-para dá para o modelo da WESO bate com o
   material lançado na OS.

### 🚨 Seis regras que os dados derrubaram ou criaram — cada uma medida

A primeira versão acusava **46 divergências de vínculo em 199 OS (23%)**. A
versão final acusa **1**. Nenhuma regra foi afrouxada para o número cair: cada
mudança tem caso real e teste que prova que o defeito de verdade continua
vermelho.

| # | Regra | Medido em | Efeito |
|---|---|---|---|
| 1 | **Quem prevê a ação é o `problema`, não o `tipo`** | 197 OS: tipo 2 "Contrato" (64) não diz ação | ele estava certo desde o começo |
| 2 | **A pergunta é "ainda está NAQUELA placa?", não "está em Estoque?"** | de 8 divergências amostradas, 5 eram reuso (série retirada e depois instalada noutra placa) | 46 → 14 |
| 3 | **Placa que SUMIU da WESO numa retirada é o caminho normal** (a retirada exclui o veículo) | 102 desinstalações com placa ausente: 73 em Estoque, 26 reusadas | era "não sei", virou confirmação |
| 4 | **O estado de hoje só julga a ÚLTIMA OS que mexeu na série** | OS posterior tocando a mesma série | vira "série mexida depois na OS N" |
| 5 | **OS ainda não finalizada não pinta de vermelho** (o motivo continua visível) | 9 das 14 acusadas estavam Nova/Iniciada | "ainda não aconteceu" |
| 6 | **Mesmo carro escrito diferente**: `CHASSI:` com e sem rótulo, `(RD)`, e o **chassi guardado na descrição** do veículo | 16712, 16517, 16900; só 250 de 1.940 veículos têm a coluna `chassi` preenchida | trava: só identificador ≥ 10 caracteres, para placa curta não casar dentro de texto livre |

E três regras de domínio, também medidas:

- **Transferência de titularidade (7474)**: o rastreador **fica no carro**, muda
  só o dono. A OS 16510 tinha 26 desinstalações "seguindo na placa" e nenhuma
  errada. Vira cinza; numa rescisão o mesmo estado continua vermelho.
- **Mesma série, mesma placa, mais de uma ação na OS: vale a de MAIOR `id`** —
  não "a saída" por suposição. A OS 16460 instalou, retirou e **instalou de
  novo** (ids 198094 → 202562 → 202563).
- **ST340 com leitor RFID é ST340RB** (regra copiada de `MODELO_COM_RFID`): a
  WESO não tem campo de acessório. A OS 16836 tem `LEITOR RFID (404)`.
- **Rastreador preso** (série fora da placa mas `Instalado` sem veículo) é
  vermelho — espelho do padrão de `29_Rastreador_Preso_Harmonit.md`.
- **Material-rastreador se reconhece pelo `idProduto` no de-para**, nunca por
  texto: `operacoes_os.eh_rastreador()` falha em 9 das 24 descrições.

### Resultado contra os dados reais (199 OS com oficina)

| Veredito | bate | — | diverge |
|---|---|---|---|
| Ação × problema | 154 | 43 | **2** (16538, 16530 — ambas Nova) |
| Vínculo na WESO | 147 | 51 | **1** (16732: identificador ` C40025013` contra uma perfuratriz `BIO400`) |
| Modelo | 144 | 39 | **16** |

**Os 16 de modelo são a lista de trabalho da E5** — quase todos exatamente o
caso que ele descreveu: a OS lança `20314` (ST310U) e a WESO diz `7006` (ST300)
para a série, ou lança `338502` (XT40) e a WESO diz outro 4G. Só 1 deles está
Finalizado (16581); os demais são OS em andamento — dá tempo de corrigir antes
de fechar.

⚠️ **Navegador: falta ele** (`M9`). Validei sintaxe do JS e a página em 200.

### De quebra

`.badge-red` era **usada** na tela (OS excluída) e **nunca definida** no CSS — o
vermelho de "excluída" nunca aparecia. Definida junto.


---

## ✅ 01/10 — E3: a porta "Serviço Realizado", 30 dias, e a rotina LIGADA (~19:00)

🔵 *"pode seguir com a recomendação e fazer a E3 e o 'Rodar Agora' bem como
acionar a rotina, deve varrer somente a partir dos ultimos 30 dias"*.

### O que mudou na Conferência de Fechamento

| Antes (29/09) | Agora |
|---|---|
| Entrava OS cujo **status** virou "Finalizado" | Entra OS com oficina cuja **situação** é **15694 "Serviço Realizado"** |
| Relia as ~400 OS mais recentes não finalizadas | Relê as **OS com oficina dos últimos 30 dias** (63 em 01/10) |
| Conferia cada OS **uma vez** | Reconfere **toda a fila a cada passada** — WESO e DataScope mudam |
| WESO: só a situação do rastreador, por série | Regra da oficina inteira (a mesma da sub-aba "ID × modelo"), com a **WESO ao vivo** |
| Colunas Harmonit · DataScope · WESO | **Ação × problema · Vínculo · Modelo · DataScope** (+ data e quem finalizou) |

A janela usa o `visto_em` do `os_historico` — a varredura roda a cada 5 min
desde 24/07, então é a criação da OS com atraso de minutos.

**Uma regra só, duas telas.** A Conferência chama
`conferencia_oficina.conferir_os`, a mesma função da sub-aba do Histórico de OS.
Os insumos comuns (`de_para_do_banco`, `ultima_os_por_serial`) também moram lá.

### 🚨 WESO ao vivo: a base inteira de veículos, não a consulta por placa

`/Veiculos/Consultar?placa=` compara por **igualdade exata** e devolve **vazio,
não erro**, quando a placa difere por espaço — documentado em
`painel/equipamentos.py` (29/07: 110 placas com espaço nas pontas). Numa
retirada, "placa não achada" seria lida como "placa excluída" e viraria um OK
falso. Então a rotina busca a **base inteira uma vez por rodada** (medido 2,3 s
em 29/07) e casa por placa normalizada; de quebra ganha o caminho inverso (onde a
série está agora) e o chassi do `complemento`. Séries: uma consulta cada.

Isso só acontece quando há OS na fila. WESO fora = vereditos de oficina ficam
"—", nunca chutados.

### DataScope na porta

🔵 *"a situação de 'Serviço Realizado' só acontece depois que OS datascope
existe"*. Então, numa OS que já passou pela porta, **faltar a resposta é
anomalia** — mas continua **cinza**, com o motivo *"confira o Nº da O.S.
digitado"*: não se sabe qual lado errou.

### O que não foi apagado (e por quê)

- As **99 linhas antigas** da `conferencia_fechamento` (porta velha) ficam no
  banco; saem da tela porque a lista agora faz `JOIN` com o `os_historico` e
  filtra `situacao_id = 15694`. Uma OS que **sair** de 15694 também sai da lista
  sem precisar apagar nada.
- `_checar_weso`, `os_nao_finalizadas_recentes` e `os_finalizadas_sem_conferencia`
  ficam no código: o **`verificar_conferencia.py`** (raiz, a validação de 29/09)
  ainda usa `_checar_weso` — conferido por `grep` antes (`M2`).

### Sub-aba "ID × modelo"

Ganhou o filtro **"só Serviço Realizado"** (parâmetro `so_servico_realizado`),
como recomendado e aceito: a sub-aba segue mostrando **todas** as OS com oficina
por padrão, porque 15 das 16 divergências de modelo estão em OS ainda abertas —
e é antes de fechar que se corrige.

### Testado

- **Função pura nova** (`tests/teste_conferencia_e3.py`, 17 ✓): placa com espaço
  nas pontas é achada, caminho inverso, chassi do `complemento`, série com
  espaço, DataScope ausente é cinza e não vermelho, porta = 15694, janela = 30.
- **"Rodar agora" ao vivo:** 200 em 25 s; 63 OS relidas; **1 na porta** (a sandbox
  16991, a única do banco em 15694); conferida com a WESO ao vivo — ação bate
  (retirada líquida), vínculo bate, **modelo diverge** (a OS lança ST310U, a WESO
  diz ST340 e XT40-TM — verdade nos dados de teste), DataScope "Aprovado análise
  técnica" (cinza: ainda não finalizou lá).
- Conferido que esse estado do DataScope é o **real**: cache local e API ao vivo
  batem (alterado às 14:46 UTC, depois do "Finalizado" manual das 13:18).
- **Suíte: 827 verificações em 15 testes, 0 falhas** — inclusive os 10 da
  Operações e o `f5b`.

### A rotina está LIGADA

`conferencia_fechamento_ativa = true` desde ~19:00 de 01/10, ligada pelo próprio
interruptor da tela (owner). O laço confere a flag a cada hora a partir do último
restart (18:59), então a **primeira passada automática é ~20:00**, depois de hora
em hora. Tudo o que ela escreve é **local** (o banco do FPSL): não há escrita em
Harmonit, WESO nem DataScope até a E4.

⚠️ **Navegador: falta ele** (`M9`). As duas telas responderam 200 e o JS passou
no `node --check`.

---

## ✅ 06/10 — FIN_2.1: Fechamento de Contas dos Técnicos (NO AR)

Tela nova (`/painel/fechamento-tecnicos`, aba `financeiro`, `telas.py` FIN_2.1)
que apura quanto pagar a cada técnico por período, a partir das OS em **15694
"Serviço Realizado"** conferidas pela E1-E3. Arquivos:
`services/sync_tecnicos.py` (sync diário de técnicos), `services/fechamento.py`
(geração de cards, semáforo, máquina de estados), `painel/routers/fechamento_router.py`,
`frontend/fechamento_tecnicos.html` (kanban de 5 colunas).

**Tabelas:** `tecnicos`, `fechamento_cartoes`, `fechamento_os`, coluna
`tecnicos_json` em `os_historico`. **IDs medidos ao vivo (OS 16991):**
`PAGAMENTO_TECNICO_ID = 653939`, `KM_DESLOCAMENTO_ID = 6971`. **Exclusão de
técnicos:** 2 camadas (ID × `ObterUsuarios` + e-mail × `painel_usuarios`) → 170
reais, 9 excluídos.

## ✅ 07/10 (manhã) — Pass de UX/UI (commit `e11f8b7`)

Pedido dele depois de usar a tela. Backend em `fechamento_router.py` /
`sync_tecnicos.py` / `storage.py`; frontend no `fechamento_tecnicos.html`.

- **"Iniciar Conferência" deixou de mentir (`M12`).** A transição
  `aberto → conferencia` passou a chamar `atualizar_semaforo` (relê a conferência
  de cada OS e recalcula o semáforo), como o "Marcar Preparado". Antes só trocava
  o card de coluna. 1 linha no router: `if novo in ("conferencia","preparado")`.
  As transições `pagamento`/`pago` seguem só andando o card — é o andamento
  humano, não ação em Harmonit/DataScope/WESO.
- **Feedback de ação.** Botão clicado desabilita e vira "Conferindo…/Preparando…"
  com `.spinner` (do `estilo.css`); ao concluir, o card ganha destaque
  `.just-moved` (1,4 s) e a coluna de destino abre sozinha. Downloads com spinner.
  Descartado o overlay bloqueante com ampulheta (padrão da casa evita piscar
  spinner em ação rápida).
- **Miniatura + modal.** O card no kanban é miniatura; clique abre
  `#modalDetalhe` (largo) com Calculado × Recibo lado a lado (divergência em
  vermelho), tabela de OS inteira e lista de divergências; ações da etapa no
  rodapé.
- **Busca de técnico por nome OU e-mail.** Coluna `email` em `tecnicos` (migração
  guardada no `init_db`), gravada pelo sync (o `ObterTecnicos` já a devolvia);
  `salvar_tecnico(email=...)`, `listar/buscar` devolvem. Combobox type-ahead no
  lugar do `<select>`. Sync populou **170/170 reais com e-mail**.

Suítes vivas: roteadores 67, ponta-a-ponta 35, `operacoes_f*` 406 — 0 falhas.

## ✅ 07/10 (tarde) — Trava de OS, cancelamento, registro permanente e relatórios (commit `4277f60`)

🚨 **Bug achado nos logs (causa-raiz).** Ele levou o card 11 até **pago** (gravou
certo às 15:31:31) e às **15:31:39 clicou "Gerar Cards" de novo** → o
`gerar_cartoes` chamava `deletar_cartao_fechamento_por_periodo` e **apagou o card
pago**, recriando em "aberto" (card 12). Era o "zerou e voltou ao início". O
`atualizar_estado_cartao` sempre esteve correto; o vilão era o delete+recria.

### `gerar_cartoes` não apaga mais nada

Regra nova: "pegue as OS em 15694 conferidas do período que **ainda não estão em
nenhum card ativo** e coloque num card **'aberto'** do técnico — criando o card ou
**completando** o 'aberto' existente". Reclicar é idempotente. O total é
recalculado a partir de **todas** as OS do card. `deletar_cartao_fechamento_por_periodo`
ficou sem uso.

### Trava de OS (decisão dele: trava dura, não "avisar")

`storage.listar_numeros_os_consumidas()` = toda OS presa a um card com estado
**≠ `cancelado`**. `gerar_cartoes` exclui as consumidas, então **gerar a mesma
semana de novo traz 0 OS** — "uma OS não vive em dois cards". A liberação é
automática ao cancelar (não há flag manual nem baixa no Harmonit).

### Cancelamento

Estado novo **`cancelado`** (fica no histórico, com `cancelado_em`/`cancelado_por`).
`POST /cartoes/{id}/cancelar` (`storage.cancelar_cartao`), botão no modal
disponível em qualquer estado ativo **inclusive pago** (é o caso que o travou).
O card cancelado sai do kanban e aparece só no Relatório; seus `fechamento_os`
ficam para o histórico. `listar_cartoes_fechamento_ativos` e `atualizar_semaforo`
passam a ignorar `cancelado` além de `pago`.

### Registro permanente

O **card é o registro durável** — nunca mais apagado. Colunas novas em
`fechamento_cartoes` (migração guardada): `pago_em`, `pago_por`, `cancelado_em`,
`cancelado_por`. O `api_avancar_estado` injeta `usuario = Depends(requer_aba(
"financeiro"))` e grava quem pagou (`_quem` = login ou e-mail). Sem tabela-ledger
separada.

### Relatórios

Aba **"Relatórios"** dentro da própria tela (alternador no topo; decisão dele, não
página nova). `storage.listar_cartoes_relatorio(periodo_de, periodo_ate,
tecnico_id, numero_os, estado)` — faixa de datas por **sobreposição**, OS via
`JOIN fechamento_os`. `GET /relatorio` (cada card já traz suas OS) e
`GET /relatorio/planilha` (CSV `;` / `utf-8-sig`, uma linha por OS + totais).
Combobox de técnico generalizado (`criarCombo`), reusado no filtro.

### ⚠️ Fora de escopo — decisão dele pendente

A "baixa" da OS é **local** (consumo no domínio do Fechamento). **Não** escreve o
estado da OS no Harmonit/DataScope — isso é a frente **E4 "Ação"** (gated à
sandbox) e pode colidir com o controle de duplicidade da rotina de Operações
(`operacoes_rotina.py:200`). Se ele quiser a baixa real no Harmonit ao pagar, é
outra frente, a planejar à parte.

### Testado

Isolado (cópia do pacote + banco temp): colunas de auditoria criadas; trava
consome enquanto ativo e **libera ao cancelar**; auditoria pago/cancelado gravada;
card cancelado fica no histórico com suas OS; relatório por técnico/OS/estado e
por **faixa de datas** (sobreposição pega, fora não); endpoints `cancelar` e
`relatorio[/planilha]` registrados. `node --check` do JS OK. Suítes vivas após o
deploy: roteadores **67**, ponta-a-ponta **35**, `operacoes_f*` **406** — **0
falhas**, Operação intacta.

⚠️ **Navegador: falta ele.** O card 12 (aberto, OS 16991) ficou em produção como
estava — serve de ponto de partida para o teste de ponta a ponta.


## ✅ 08/10 — Auditoria antes da demo e correções A-D (commit `e966c6d`)

🔵 *"audite ele e sua relação com as demais telas, amanhã vou demonstrá-lo"* → *"proponha então"* → plano aprovado.

### A. O quadro mostra card que cruza o período
`listar_cartoes_fechamento` filtrava `inicio >= ? AND fim <= ?`, ou seja, só mostrava card que coubesse **inteiro** no período. A tela abre na semana atual, e o card 12 (01–11/10) sumia na semana de 05–11/10. Agora a regra é sobreposição, a mesma que o `listar_cartoes_relatorio` já usava. O único chamador é `GET /cartoes`.

### B. Um card ABERTO por técnico e período
O `UNIQUE(tecnico_id, periodo_inicio, periodo_fim)` da tabela contava o card cancelado e o já avançado. Dava **500** em dois casos:
1. Cancelar e depois gerar o mesmo período (provado numa cópia do banco).
2. OS atrasada de um técnico cujo card daquele período já estava em conferência ou adiante.

O SQLite não remove constraint de tabela. A **migração guardada no `init_db`** reconstrói `fechamento_cartoes` preservando os ids (`fechamento_os` aponta para eles; `foreign_keys` não está ligado) e cria o índice parcial `ux_cartao_aberto ... WHERE estado = 'aberto'`. Ela só roda se o SQL da tabela ainda tiver `UNIQUE(tecnico_id`. Foi ensaiada duas vezes numa cópia: mesmas linhas, mesmos ids, e a segunda rodada não mudou nada.

**Efeito:** cancelar e gerar de novo cria um card novo, e o cancelado fica no relatório. OS atrasada vira um **card complementar** aberto. A trava de OS não mudou: uma OS continua num só card ativo.

### C. A mensagem do "Gerar" diz a verdade (`M12`)
O `gerar_cartoes` descartava em silêncio OS sem técnico real e OS sem linha de conferência, e a tela dizia "todas as OS do período já estão em cards". Agora o retorno traz `os_no_periodo`, `ignoradas_sem_tecnico`, `ignoradas_sem_conferencia` e `conferencia_ativa`. A tela monta a frase a partir desses números:
- "Nenhuma OS em Serviço Realizado com previsão neste período";
- "N OS ficaram de fora: sem conferência (16993)";
- "a rotina da Conferência está desligada".

### D. Card nasce com semáforo
`atualizar_semaforo` roda em cada card criado ou completado. Antes o card ficava `null`, sem bolinha, até o "Iniciar Conferência" ou a rodada horária.

### Testado
- Roteiro de 24 verificações numa cópia isolada (código + banco em `/tmp`, TestClient), sem falha: transições, recibo vermelho, pago, cancelar e regerar, card complementar, índice barrando um segundo aberto, trava de OS, relatório, planilhas, 403.
- Suítes de produção: roteadores 67 · ponta a ponta 35 · `operacoes_f1..f6` 406, **0 falhas**. Operações intacta.
- Produção depois do restart: card 12 igual (aberto, amarelo, R$ 137,55, OS 16991). O quadro de 05–11/10 devolve o card 12. Backup em `data/fpsl.db.bak_pre_fin21_2026-10-08`.

### Achados da auditoria que ficam com ele (mudam regra)
1. **A rotina da FIN_1.1 está DESLIGADA desde 02/10 10:55** (PUT no interruptor pela conta admin). Sem ela, OS nova em Serviço Realizado não ganha linha de conferência e fica de fora do Fechamento. Agora a tela do Gerar diz isso.
2. DataScope em "Aprovado análise técnica" conta como "ainda não finalizou" (`ESTADO_OK = "Finalizado"`). É o estado para onde a E4 vai mandar a OS, então depois da Ação toda OS ficaria amarela no Fechamento.
3. O OK do Fechamento (harmonit + datascope + weso) ignora Ação e Modelo, que a FIN_1.1 mostra.
4. Vermelho não trava o "Marcar Pago".
5. O recibo pode ser trocado em card Pago ou Cancelado, sem trilha.
6. O período segue `data_previsao`, não a finalização.
7. Popover "conferência pendente" sem o motivo (que existe em `conferencia_fechamento.detalhe`).

**Dados (não é código):** só 9 de 546 OS têm PAGAMENTO DE TÉCNICO (653939) lançado e 7 têm KM. Técnico aparece em 188 OS (34%); 85 têm só usuários internos. Só a conta admin tem a aba `financeiro`. A matriz `teste_roteadores_painel.py` não cobre `/painel/api/fechamento`.

**08/10 18:20 — rotina da FIN_1.1 RELIGADA** com o OK dele (*"pode ligá-la"*). `conferencia_fechamento_ativa = true`, confirmado relendo o banco. Ficou desligada de 02/10 10:55 a 08/10. Ligar não roda na hora: o laço relê a chave a cada 1h, e o "Rodar agora" da tela adianta.
