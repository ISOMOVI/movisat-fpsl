# 32 — Contas a Receber (`CAR_1.1`): a spec

> Escrita em **28/10/2026**, antes de qualquer código, no padrão da casa (spec antes de
> implementação, como a `OPR_1.1` e a `CTR_1.1`). O número **32** estava reservado desde 14/10 pelo
> `33_Nocoes_do_Projeto.md`, que já citava esta aba por este nome.
>
> 🚨 **Todo número aqui tem data, e número sem data não se copia.** Os desta página foram medidos em
> **28/10/2026** com `sqlite3 -readonly data/fpsl.db`. O estado real se mede de novo; esta página
> explica o **desenho**.
>
> Controle de progresso da frente (estado por etapa): `C:\Users\Lenovo\Desktop\CAR_1.1_Financeiro_FPSL.md`.
> Detalhe do contrato: `31_Gestao_Contratos.md`. O porquê do projeto: `33_Nocoes_do_Projeto.md`.

---

## 1. Para que esta aba existe

A `CTR_1.1`/`CTR_1.2` respondeu *"o que este cliente tem direito a ter?"*. Esta aba responde a
segunda pergunta de dinheiro do projeto: **"o que ele deve pagar por isso?"**

O pedido dele, em 28/10, textual:

> *"vamos montar o painel do financeiro que rodará no FPSL — ali vamos centralizar os contratos
> ativos assinados para inicio das atividades. o objetivo é que ali centralizemos o 'contas a
> receber'. (…) O objetivo é ter o financeiro desses contratos rodando mesmo, sendo possível saber o
> que está sendo cobrado do cliente por mês conforme contrato."*

O vazamento que ela existe para fechar, medido em 14/10 e **ainda de pé em 28/10**:

| Achado | Quantos |
|---|---|
| **em uso sem contrato** (serviço entregue, provavelmente não cobrado) | 322 |
| encerrada e ainda em uso | 168 |
| em uso, falta assinar | 136 |
| contratada e não instalada | 1.349 |
| substituição pela metade | 364 |
| mesma placa em dois clientes | 83 |

⚠️ Esses números são da rodada de **14/10** e a rotina de auditoria está **desligada** — ao usá-los,
dizer a data.

**O que esta aba NÃO é:** a `FIN_1.1` (Conferência de Fechamento) e a `FIN_2.1` (Fechamento de
Técnicos) são **contas a pagar** — conferem OS e apuram quanto pagar ao técnico (doc 30). A `CAR_1.1`
é o outro lado: **o que o cliente paga**. Nenhuma das duas é alterada por esta frente.

---

## 2. As decisões dele (28/10) — são lei

| # | Decisão | Palavra dele |
|---|---|---|
| 1 | **O valor vem do termo**, pelo caminho de input que já existe | *"pode montar com os dados que tem dos contratos atuais mesmo, será feito assim no futuro, o termo assinado será inputado tbm no mesmo formato"* |
| 2 | **FPSL é o motor; MoviZap é a esteira** | escolhido entre as três opções apresentadas |
| 3 | **Emissão fica para depois de a conferência bater**, cliente a cliente | idem |
| 4 | **Aba nova, reaproveitando o código da `CTR_1.1`** | idem |
| 5 | Ativo/inativo existe nos **dois níveis** | *"o ativo e inativo é por placa dentro do contrato e pelo contrato em si"* |
| 6 | **1 linha de mensalidade por placa + linhas variáveis** | *"1 por placa, do mensal pelo contrato e outro que soma todas as variaveis, por exemplo OS de serviços. Então minimo de 1 e maximo depende"* |
| 7 | **Aviso prévio cobra cheio, sem pro rata**, e negociação é exceção registrada | *"é o 1, mas pode ser que tenha negociação"* |

Decisões anteriores que continuam valendo (13-14/10, doc 33 §4): vale o assinado · troca registrada
no Harmonit vale · **aviso prévio de 90 dias conta** · **o valor vem do termo e fica no
`contrato_item`; a CAR calcula, não decide** · placa na WESO vence mesmo sem assinatura · Clicksign é
só leitura · rotina nasce desligada com interruptor na própria tela.

---

## 3. O que a base tem hoje, medido em 28/10

| Tabela | Linhas | Observação |
|---|---|---|
| `contrato_termo` | 4.599 | assinado=1: **3.056** · assinado=0: 1.543 · `revisar=1`: 796 · **com PDF em disco: 5** |
| `contrato_evento` | 12.132 | ENTRA 6.464 · RESCINDE 3.960 · SAI 1.275 · UPGRADE 432 · ANULA 1 |
| `contrato_placa` | 6.812 | **ATIVA 2.763 · EM_AVISO_PREVIO 189** · RESCINDIDA 2.956 · SUBSTITUIDA 904 |
| `contrato_item` | 6.463 | 🔴 **1 com `valor_mensal`** |
| `contrato_cliente` | 731 | o único lugar onde o **nome** do cliente existe |
| `contrato_achado` | 2.422 | rodada de 14/10; rotina desligada |

**O universo da cobrança são as 2.952 placas sustentadas** (ATIVA + EM_AVISO_PREVIO).

> 🚨 **ESTA FRASE ESTÁ EM CORREÇÃO DESDE 28/10, POR DECISÃO DELE:** *"as placas ativas são somente as
> que estão na Weso ativa, conforme as documentações"*. Medido no mesmo dia, cruzando com o cache da
> WESO (que é o `/Veiculos/Consultar` **inteiro** — 1.928 veículos, 3.792 rastreadores, atualizado
> 04:15): das **2.906** placas que o contrato torna cobráveis em outubro, **1.059** têm veículo na
> WESO com rastreador `Instalado`. **36 %.** As outras **1.843 não existem como veículo na WESO** —
> contratadas e nunca instaladas, ou retiradas.
>
> E o outro lado: **803 placas com rastreador `Instalado` e sem contrato cobrável** (769 sem contrato
> algum, 36 `RESCINDIDA`, 4 `SUBSTITUIDA`) — serviço rodando sem cobrança.
>
> ⚠️ **Dois limites do cache que a régua nova tem de respeitar, medidos:** `veiculos.cliente_id` está
> **vazio em 1.928 de 1.928** linhas e `veiculos.status` é `0` em todas — então *"WESO ativa"* só se
> resolve pelo **`rastreadores.situacao`** do rastreador vinculado, e **o cliente nunca vem da
> WESO**. Faturar "pela WESO" é **cruzar** as duas bases, não trocar de base.
>
> 🔴 **A régua definitiva espera a decisão D1 dele** (contrato · WESO · a interseção com as duas
> colunas na tela), com as outras três (D2-D4) e a proposta de gestão mensal no documento de controle
> da frente, **§V2-A a §V2-C**. Até ela vir, **o código continua usando ATIVA + EM_AVISO_PREVIO** e
> esta nota existe para ninguém ler o número 2.952 como se fosse o faturável.

### 🚨 O valor: 1 de 6.463, e por quê

Não é defeito do extrator. `painel/contratos_leitura.py:109` (`valor_das_placas`) só liga valor
quando o termo tem **uma** placa que entra e **um** item de mensalidade. A regra é estreita de
propósito: confundir **equipamento** (pago uma vez) com **mensalidade** já produziu **13× o valor
certo**. Termo com 12 placas e um item "MENSALIDADE" **não diz quanto é de cada veículo**.

Consequência aceita pela decisão 1: **a aba nasce com quase tudo "sem valor"**, e o número aparece no
alto da tela, com o motivo por linha. **Ratear seria inventar, e a cobrança sairia em cima do
inventado.**

E a WESO não ajuda: o campo `valor_mensalidade` dela vem **zero** nos 1.932 veículos, e o cache
`weso.db/veiculos` **não tem a coluna**.

---

## 4. O modelo: evento imutável, estado derivado

A CAR **clona** o núcleo da CTR em tabelas próprias, em vez de acrescentar ação a
`contrato_evento` — porque as ações de lá são sobre **existência de placa** e o motor que as lê
(`contratos_eventos.py`) é **puro e travado por teste**. Regra da casa: regra que muda **clona**,
infraestrutura **reusa**.

```
contrato_termo / contrato_evento / contrato_placa / contrato_item     <- a CTR, só LIDA
          |
          v
car_evento      PRECO · CANCELA · RENOVA · EXCECAO · ANULA     <- IMUTÁVEL
car_contrato    ATIVO | INATIVO, com o MOTIVO                  <- DERIVADA, nunca fonte
car_leitura     a auditoria de uma leitura de mês              <- não é recebível
```

### 4.1 `car_evento` — o livro-razão do dinheiro

```sql
car_evento(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cnpj TEXT NOT NULL,
  termo_id INTEGER NOT NULL,        -- o fato é do CONTRATO
  placa_chave TEXT,                 -- NULL = vale para todas as placas do termo
  acao TEXT NOT NULL,               -- PRECO | CANCELA | RENOVA | EXCECAO | ANULA
  valor_mensal TEXT,                -- TEXT, pela mesma razão de contrato_item
  competencia TEXT NOT NULL,        -- 'AAAA-MM' a partir da qual o fato vale
  motivo TEXT,
  documento TEXT,                   -- hash/arquivo do termo ou aditivo que prova
  fonte TEXT NOT NULL,              -- termo | aditivo | operador
  por TEXT NOT NULL,                -- login do autor; NUNCA vazio
  criado_em TEXT NOT NULL,
  corrige_evento_id INTEGER
);
CREATE UNIQUE INDEX idx_car_evento_corrige ON car_evento(corrige_evento_id)
  WHERE corrige_evento_id IS NOT NULL;
CREATE INDEX idx_car_evento_termo ON car_evento(termo_id);
CREATE INDEX idx_car_evento_cnpj  ON car_evento(cnpj);
```

| Ação | O que é | Por que é assim |
|---|---|---|
| **`PRECO`** | *"a mensalidade passa a ser X a partir de AAAA-MM"* | **Nascer o valor e reajustar são o mesmo fato.** `fonte='termo'` quando veio do documento; `fonte='operador'` **exige** `motivo`. O histórico de preço é um `SELECT … ORDER BY competencia` |
| **`CANCELA`** | interrompe a **cobrança** a partir da competência; motivo obrigatório | 🚨 **Não mexe em placa.** Rescisão de placa é `RESCINDE`, da CTR. A tela mostra os dois lados — ver `divergencia` |
| **`RENOVA`** | nova vigência/fidelidade, com documento | `contrato_item.fidelidade_meses` já existe como base |
| **`EXCECAO`** | a negociação da decisão 7: desconto, isenção ou carência numa competência | sem ela, *"pode ser que tenha negociação"* viraria alguém editando valor no banco |
| **`ANULA`** | corrige evento da CAR apontando `corrige_evento_id` | clone de `contratos_registro.anular_evento`, com `JaAnulado`. **Nunca `UPDATE`** |

**Por que `valor_mensal` é TEXT:** a mesma razão de `contrato_item` — o termo escreve "R$ 999,90", e
valor riscado ou renegociado já enganou a leitura antes. A conversão para número acontece no momento
de somar, num lugar só, e **erro de conversão é dito, não silenciado**.

`SUSPENDE`/`RETOMA` **ficam fora**: a negociação é coberta por `EXCECAO`, e **não se escreve ação que
a tela não oferece**.

### 4.2 `car_contrato` — o status do contrato (decisão 5, nível de cima)

Derivada, como `contrato_placa` é derivada. **Nenhuma regra a lê para decidir**; na dúvida o evento
ganha e ela se refaz.

```sql
car_contrato(
  termo_id INTEGER PRIMARY KEY, cnpj TEXT NOT NULL, numero TEXT, empresa TEXT,
  situacao TEXT,                 -- ATIVO | INATIVO
  motivo TEXT,                   -- POR QUE, sempre dito
  placas_ativas INTEGER, placas_com_valor INTEGER, placas_sem_valor INTEGER,
  valor_mensal_total TEXT,       -- NULL quando nenhuma tem valor; NUNCA '0,00'
  divergencia TEXT, competencia TEXT, calculado_em TEXT
);
```

**Régua da `situacao`**, nesta ordem, com o motivo escrito:

1. `contrato_termo.assinado = 0` → **INATIVO**, *"termo não assinado"* — **1.543 termos** caem aqui, e
   é honesto
2. `CANCELA` vigente (`competencia <= a olhada`) e não anulado → **INATIVO**, *"cancelado em AAAA-MM"*
3. ≥1 placa `ATIVA`/`EM_AVISO_PREVIO` com `termo_vigente` = este termo → **ATIVO**
4. senão → **INATIVO**, *"sem placa ativa"*

O **nível de baixo** da decisão 5 já existe e **não se duplica**: é `contrato_placa.situacao`,
calculada pelo motor da CTR. A ficha mostra os dois níveis.

🚨 **`valor_mensal_total` é NULL, nunca `0,00`, quando nenhuma placa tem valor.** `0,00` afirma que o
contrato não cobra nada; `NULL` com o motivo diz a verdade — que não sabemos.

**`divergencia`** é o achado que impede a CAR e a CTR de mentirem uma para a outra:
*"cancelado na CAR com 3 placas ATIVAS na CTR"*, e o inverso.

### 4.3 Competência: a cobrança de um mês é uma **leitura**, não uma cópia

**`competencia = 'AAAA-MM'`.** A pré-fatura de um mês é uma **função**, não uma tabela:

> ⚠️ **Definição vigente no código, e em correção pela decisão D1 de 28/10 (ver §3):**
> uma placa é **cobrável** na competência C se `contratos_eventos.situacao_das_placas` a devolve
> `ATIVA` ou `EM_AVISO_PREVIO` **em qualquer dia** de C — medido nas duas pontas, o primeiro e o
> último dia do mês; o valor é o último `PRECO` não anulado com `competencia <= C`, ajustado pela
> `EXCECAO` daquela competência.

🚨 **O instante que define o mês é regra de receita, e a primeira versão desta spec errava.** Ela
dizia "o último dia de C". Medido na base real em 28/10/2026: no dia **1º de outubro** havia
**2.993** placas cobráveis e no dia **31** havia **2.946** — **47 saíram no meio do mês**, e
nenhuma entrou. Pela decisão dele de 28/10 (*"cobra cheio, sem pro rata"*), essas 47 **tiveram
serviço em outubro**: olhar só o dia 31 deixaria 1,6% da carteira de fora **sem ninguém notar**.

⚠️ **O preço desta escolha, dito:** substituição dentro do mesmo mês (uma placa sai, outra entra)
gera **duas** linhas para um veículo só. Em outubro de 2026 isso aconteceu **zero** vezes (nenhuma
placa entrou no mês), mas vai acontecer — por isso cada linha carrega `entrou_no_mes` /
`saiu_no_mes`, os totais os somam, e a tela mostra. O operador não descobre pela soma.

⚠️ **E uma prova de que a releitura é real, não enfeite:** o cache `contrato_placa`, recalculado às
11:46 de 28/10, dizia **2.952** cobráveis; a releitura de 31/10 dá **2.946**. Os 6 de diferença são
aviso prévio que vence nos últimos três dias do mês — **sem nenhum evento novo**.

O motor **já recebe `hoje` como parâmetro** (`painel/contratos_eventos.py:241`) — é isso que torna o
mês passado uma **releitura** e não um congelado. É o que o doc 33 §11 exige:

> *"Não pode ser: um cadastro paralelo de recebíveis, alimentado por cópia. Recebível copiado
> congela, e no mês seguinte ninguém sabe dizer por que aquele valor está lá — que é exatamente o
> problema que esta frente existe para consertar, só que com outro nome."*

**Zero tabela de fatura, vencimento, parcela ou boleto.** A única coisa gravada sobre um mês é a
auditoria da leitura:

```sql
car_leitura(id INTEGER PRIMARY KEY AUTOINCREMENT,
            competencia TEXT NOT NULL, cnpj TEXT,   -- cnpj NULL = a carteira inteira
            gerada_em TEXT NOT NULL, por TEXT NOT NULL,
            clientes INTEGER, placas INTEGER, sem_valor INTEGER, total TEXT,
            assinatura TEXT);                       -- sha256 do resultado normalizado
```

Serve para responder *"em 28/10 a leitura de outubro dizia X"* e para detectar que reabrir o mesmo
mês mudou o número — com a causa explicável pelos eventos. **Não é fonte de cobrança.**

### 4.4 As linhas da pré-fatura (decisão 6): mínimo 1, máximo aberto

```
mensalidade   1 por placa cobrável, valor do contrato     <- sempre existe
variável      n linhas, serviço de OS na competência      <- 0 ou mais
```

A linha variável **não se inventa nesta spec**. O que o FPSL já tem: `os_historico` (589 OS),
`painel_vinculos_itens` (89 de-para item ↔ catálogo Harmonit) e
`services/fechamento.py:_extrair_valores_materiais` — que classifica material de OS, **mas só o que
se paga ao técnico** (PAGAMENTO DE TÉCNICO, KM DESLOCAMENTO).

🔴 **Qual item do catálogo do Harmonit se cobra do cliente é decisão dele** (§8, item 2). Até ela
existir, a pré-fatura traz a mensalidade e **diz, na tela, que a parte variável ainda não entra** —
`M12`, e sem "em breve".

---

## 5. A consulta ampla — as quatro chaves que ele pediu

Pedido: *"podendo consultar os dados do contrato através da placa, do ID em uso, do contrato, do
cliente, etc."*

`painel/car_busca.py` → `resolver(conn, q)`. Degraus em **ordem fixa**; cada um só roda se o anterior
não achou; e **a resposta sempre diz por qual degrau achou**.

| # | Entrada | Como resolve | Custo |
|---|---|---|---|
| 1 | tem **letra** → nome | `contrato_cliente.nome` (731 linhas, em memória) | grátis |
| 2 | **sem letra** → CNPJ | substring nas mesmas 731 | grátis |
| 3 | → **placa** | `contratos_grid.clientes_por_placa` (normaliza: `BUW8732 → BUW8H32`) | 1 consulta, índice da PK |
| 4 | → **contrato** | varredura de `contrato_termo.numero` | ~ms |
| 5 | → **ID em uso** | `weso.db` em `mode=ro`: `rastreadores.numero_serie` → `veiculos.rastreador_id` → `veiculos.chave_placa` → `contrato_placa.placa_chave` → `cnpj` | o mais caro; por isso é o último |

🚨 **Três coisas que a medição obrigou:**

1. **A armadilha do "2hm"**, travada por teste: **letra procura nome; texto sem letra procura CNPJ**.
   Extrair dígito de `"2hm"` dava `"2"`, que casa com quase todo CNPJ, e **devolvia a base inteira**.
2. **`contrato_termo.numero` não tem índice e tem 558 números repetidos** (4.599 termos, 4.041
   números): o mesmo número existe em MOVISAT e em INSTITUTO. A busca **devolve os dois** e a tela
   diz *"2 termos com este número"*. Não se cria índice numa tabela que é da CTR, por 4.599 linhas.
3. **O "ID em uso" só existe no cache da WESO** — medido em 28/10: `rastreadores(numero_serie)` ×
   `veiculos(rastreador_id, chave_placa)`, com os três índices já prontos (`idx_rastr_serie`,
   `idx_veic_rastr`, `idx_veic_chave`). O degrau **carimba a idade do cache**, e a tela a mostra.
   ⚠️ **Distinção deliberada:** a regra das 48 h proíbe o cache **decidir** (fechar placa, apontar
   divergência), não **procurar**. A busca por ID responde com cache velho **dizendo a idade**; o que
   ela não faz é virar achado.

**Reuso, não reescrita:** `contratos_grid.listar` (0,24 s para as 731 linhas) · `clientes_por_placa` ·
`acoes_da_linha` (devolve `{ativa, motivo}` — botão desligado diz por quê) · `para_csv` ·
`_cache_velho` (**cache vazio também é cache velho** — foi isso que impediu o grid de desenhar 0
placas nos 731 clientes com a base cheia de eventos).

---

## 6. O que a tela diz, e o que ela não promete

- **Chip de abertura, obrigatório:** *"2.763 placas ativas · 1 com valor · 2.762 sem valor — o valor
  entra pelo termo (CTR_1.2) ou por `PRECO`, com autoria"*.
- **Placa sem valor** sai `null` **+ motivo**, nunca `R$ 0,00`. Os motivos vêm do vocabulário que
  `valor_das_placas` já produz: *"o termo tem valor, mas por item de serviço e não por veículo"* ·
  *"o termo não traz item de mensalidade"* · *"termo sem documento guardado"* (**4.594 de 4.599**).
- **O total é "do que tem valor"**, com o percentual ao lado. Total que soma só parte da carteira sem
  dizer é tela que mente.
- **A parte variável** (decisão 6) aparece como seção que **declara não estar ligada** e por quê.
- **Sem "em breve"** em lugar nenhum.

### Relatórios (ele pediu que já fossem pensados)

Baratos agora, só lendo o que existe:

1. **Pré-fatura da competência** (CSV) — cliente · termo · placa · situação no mês · valor · fonte ·
   motivo quando nulo
2. **Cobertura de valor** por cliente — ativas / com valor / %. A régua do doc 33 §12 aplicada a
   dinheiro
3. **Carteira** — contratos ATIVO/INATIVO **com o motivo**, placas, fidelidade
4. **Movimento do mês** — ENTRA/UPGRADE/RESCINDE/SAI por competência, de `contrato_evento`. **A única
   série histórica real que já existe**
5. **Histórico de preço** — `acao='PRECO'` por termo/placa, com autor e data. Nasce vazio **e diz que
   nasce vazio**
6. **Divergência CAR × CTR**

**Caro, e fora agora:** comparar com o **faturado do Harmonit** exige
`POST /Financeiro/ObterBoletosPorCpfCnpj` (com período) cliente a cliente — **731 chamadas**. É a
frente de conferência da decisão 3, e é tarefa própria.

---

## 7. Fora de escopo, de propósito

- **Emissão de boleto ou nota** — decisão 3. O Harmonit emite; a CAR calcula, compara e aponta.
  **Nenhuma escrita no Harmonit, na WESO ou na Clicksign**, em nenhuma fase.
- **Ler o faturado do Harmonit como FONTE do valor** — decisão 1. Para a *conferência* serve; para a
  fonte, não.
- **Rateio do valor do termo entre placas** — número inventado em cobrança é pior que número
  faltando.
- **Rotina nova** — `LACOS` fica nos 9. O recálculo de `car_contrato` segue o padrão do grid (refaz
  quando o cache é de outro dia). Rotina de vigência (aviso prévio vencendo, reajuste devido) é etapa
  seguinte e **nasce desligada, com interruptor na própria tela** (convenção do FPSL).
- **Reajuste automático por índice (IGPM/IPCA)** — exige série externa e a palavra dele sobre o
  índice.
- **Equipamento e chip dentro do contrato** — `recursos` está **vazio nos 12.132 eventos e nos 6.463
  itens**. Sem a junção `contrato_item ↔ rastreador ↔ chip`, *"o que está sendo cobrado"* só desce
  até a **placa**, e a tela diz isso.
- **A esteira do MoviZap** (`Contratual` → botão *enviar para Financeiro*) — decisão 2, frente
  própria. A porta de entrada já existe no desenho: um `POST` ao `car_router` lançando `PRECO` com
  `fonte='termo'`.
  ⚠️ **Correção de premissa, medida em 28/10:** **o MoviZap não tem aba "Operações"** — tem `PNL_1.1`
  "Operação", um painel do grupo *Painéis*; a aba Operações é a **do FPSL**, a intocável. O caminho
  que ele descreveu **já está reservado no código do MoviZap**: `movizap/paineis.py:92-94` tem
  `contratual` e `financeiro` como painéis, `PNL_1.3`/`PNL_1.4` guardados em `telas.py:131-132`, e
  **4 formulários já mapeados em cada um** (ficha cadastral, aditivo, substituição e rescisão no
  Contratual).
- **Mexer na `CTR_1.1`** — ela continua sendo a **auditoria** do contrato (decisão 4).
- **`SUSPENDE`/`RETOMA`** — a negociação da decisão 7 é coberta por `EXCECAO`.

---

## 8. Decisões dele que esta spec NÃO tomou

1. ✅ **Permissão — DECIDIDA POR ELE EM 28/10: `contas_receber` nova.** No ar: 7 → **8
   concedíveis**, e a aba nasce **ligada em ninguém além do owner**. A Karla (`painel_usuarios`
   **526**, hoje `["financeiro","contratos"]`) **não** ganhou nada de carona — conceder é ato dele, e
   era essa a vantagem. 🚨 O motivo é medido, não estético: a aba **cancela cobrança** e lança preço
   em **335 placas num clique**, e quem tem `financeiro` confere OS e fecha pagamento de técnico.
2. 🔴 **Quais itens do catálogo do Harmonit se cobram do cliente** — é o que faz a linha variável da
   decisão 6 nascer. Hoje o único classificador que existe é o de **pagar técnico**. **Sem essa lista
   a parte variável não nasce, e a tela diz que não nasceu.**
3. **Dia de vencimento, multa e juros** — não existem em coluna nenhuma e não são deriváveis do termo
   lido hoje. Sem eles, a pré-fatura é *"o que cobrar no mês"*, não *"quando vence"*.
4. **Posição no menu** — ⚠️ **o que entrou em 28/10 NÃO foi o default escrito aqui.** A `CAR_1.1`
   ficou **logo depois da `CTR_1.1`**, antes do bloco `CFG`, e não depois dele: a ordem de `TELAS` é
   a ordem do trabalho real (o termo vira contrato na CTR, o contrato vira cobrança aqui), e
   Configurações/Usuários no fim é a convenção do menu. **Nenhuma tela existente mudou de posição
   relativa.** Reverter para o fim absoluto é mover um bloco em `telas.py` — decisão dele.

---

## 9. Como se verifica cada etapa

O detalhe por etapa (E0 a E10, mais os dois consertos de CNPJ) vive no documento de controle da
frente: `C:\Users\Lenovo\Desktop\CAR_1.1_Financeiro_FPSL.md`. **Não duplicar a lista aqui.**

O que vale para todas:

1. ✅ **As travas de contagem foram atualizadas na mesma tarefa** que criou a tela, e passaram:
   `teste_perfis` **11 → 12 telas** e **7 → 8 concedíveis** (29 OK) · `teste_barra_status`
   **13 → 14 páginas** (94 OK). A trava de **18 rotas** do `teste_contratos_router.py:104` **não
   mudou** — a CAR tem router próprio (68 OK).
   🚨 **E a matriz de roteadores entrou no MESMO passo, não no dia seguinte:**
   `tests/teste_roteadores_painel.py` ganhou 3 linhas da CAR (duas de leitura, uma de escrita com
   corpo JSON), e por isso o laço [7] continuou verde (**90 OK**). Foi exatamente esta omissão que
   deixou a matriz vermelha de 23/10 a 28/10 quando `contratos` virou concedível: `exigidas` sai
   daquela lista escrita à mão, não do app.
2. **O motor não faz I/O**, e isso é travado por teste (o fonte não contém `import sqlite3`,
   `import httpx`, `open(`), como `teste_contratos_aderencia.py:221` já faz.
3. **Nada de `UPDATE` em `car_evento`** — travado por teste no fonte.
4. **`por` nunca grava vazio.**
5. **Idempotência da DDL**: `criar`+`migrar` chamados **duas vezes** no mesmo banco temporário.
6. **A aba Operações não muda:** `sha256sum` de `painel/pdf_extractor.py` e `painel/operacoes_*.py`
   antes e depois de cada entrega.
7. **A prova é reler o estado no banco e abrir a tela**, nunca o retorno do comando.
   ✅ **Publicado em 28/10 14:24, com a palavra dele** (*"subir, se a suíte fechar"*): restart do
   `fpsl-weso`, as 3 tabelas `car_*` nasceram no `data/fpsl.db`, `sha256` do `pdf_extractor.py` e dos
   8 `operacoes_*.py` **idênticos antes e depois**, e a suíte inteira em **73 arquivos, 71 verdes** —
   os 2 vermelhos são os de antes (`teste_extrair_termo`, que espera decisão dele, e 1 falha de dado
   em `teste_higiene_placas_weso`).
   🔴 **O que ainda falta é só dele: abrir `/painel/contas-receber` no navegador.** É o único passo
   que nenhuma suíte faz (`M9`).

---

## 10. CNPJ alfanumérico — o que esta frente conserta e o que não

Auditoria completa (os três sistemas, com linha e veredito) no documento de controle da frente, §10.
Resumo do que toca o FPSL:

- 🔴 **Entra nesta frente:** `painel/routers/contratos_router.py` tem **6** `isdigit()` (l.233, 347,
  362, 378, 385, 456) que transformam `WQ0P6GLD000108` em **`000108`** e usam isso como **chave de 7
  tabelas**; `frontend/contratos.html:965,1003` descarta letras e a l.1005 reprova com a **mensagem
  errada**; mais `contratos_carga.py:37`, `contratos_assinados.py:351,490`, `contratos_grid.py:349` e
  `routers/os_router.py:112` (este **falha calado**: cai no ramo "nome" e devolve zero sem dizer
  nada).
- ⬜ **Fora, com motivo:** `painel/pdf_extractor.py:53,70` — o `_CNPJ_RE` exige dígito **e** a
  pontuação, e termo com CNPJ alfanumérico sai `cnpj=None` **em silêncio**. Mas o `pdf_extractor` é da
  **aba Operações, intocável**: conserto é **tarefa própria, com o OK dele**.
- 🚨 **Na WESO, `cnpjcpf` é o identificador do `/Clientes/Atualizar`** e não está em `ClienteUpdate`
  (`routers/clientes.py:73`): **cliente criado com CNPJ numérico não pode ter o documento migrado**
  para alfanumérico — só criando registro novo. Confirmar com a WESO **antes** de a primeira migração
  aparecer, e então registrar em `10_Inconsistencias.md`.
- 🔵 **Nenhuma coluna de banco precisa mudar** (tudo `TEXT`), e **o FPSL não tem validador de DV de
  CNPJ** — o correto já existe em `movizap/bitrix_arquivo.py:20-48`, escrito para o formato novo, e
  deve ser extraído para módulo compartilhado em vez de reescrito.

---

## 11. As rotas, como ficaram (16 na E7 de 28/10; **21 desde 30/10**)

> 🆕 **As 5 de 30/10** (blocos F1 e F4, detalhe na seção 12): `GET`/`PUT /faturado/interruptor` · `POST /faturado/atualizar` · `GET /semear` · `POST /semear`.
> Todas herdam `requer_aba("contas_receber")` do `APIRouter`; o `PUT` exige **também** `config`, como o interruptor da `FIN_1.1`.

Prefixo `/painel/api/car`, todas atrás de `requer_aba("contas_receber")` declarado no próprio
`APIRouter` — `car_router.py` não tem uma única rota solta, e isso é travado por teste.

| Método | Rota | O que faz |
|---|---|---|
| GET | `/clientes` | o grid: **um contrato por linha**, lido de `car_contrato`, com situação, motivo, placas e valor |
| GET | `/clientes.csv` | o mesmo grid, mesmo filtro, `;` como separador |
| GET | `/cliente/{cnpj}` | a ficha do cliente na competência |
| GET | `/termo/{id}` | **as linhas do mês E a linha do tempo do preço juntas** |
| GET | `/termo/{id}/historico-preco` | só a linha do tempo, com os anulados marcados |
| GET | `/prefatura` · `/prefatura.csv` | o que cobrar na competência |
| GET | `/busca` | a caixa única das 4 chaves dele + o ID em uso |
| GET | `/fila-sem-valor` | a fila de trabalho do lote, do que mais pesa ao menos |
| POST | `/termo/{id}/preco` · `/cancelar` · `/renovar` · `/excecao` | as 4 ações de operador |
| POST | `/evento/{id}/anular` | a 5ª: corrige **sem apagar** |
| POST | `/lote/preco` | um `PRECO` por contrato, idempotente, teto de 2.000 por chamada |
| POST | `/prefatura/fechar` | grava `car_leitura` com autor e **assinatura sha256** da leitura |

🔵 **A 16ª rota não estava no plano**, que previa 15. `POST /prefatura/fechar` entrou porque
`car_leitura` nascia **sem nenhum escritor** — tabela que existe e ninguém preenche é promessa que a
tela não cumpre. Ela responde a uma pergunta só, e é uma que vai aparecer: *"reabri outubro e o
número mudou, por quê?"*. Com a assinatura guardada, a mudança é **fato**, e a causa se explica pelos
eventos.

🚨 **O autor sai do token, nunca do corpo.** `por` enviado pela tela é **ignorado** — travado por
teste. Autor que o cliente da tela escolhe é autor que o cliente da tela inventa, e dinheiro sem
responsável é o que esta aba existe para evitar.

🚨 **`_resolver_cnpj` desde o nascimento, e é o conserto do X1 aplicado antes do defeito existir
aqui:** o documento digitado vira o CNPJ **como a base o guarda**, comparando pela forma normalizada
(`car_busca._limpo`, que **preserva letra**). Um `isdigit()` faria `WQ0P6GLD000108` virar `000108`,
que é chave de sete tabelas — é exatamente o que a `CTR_1.1` faz hoje em 6 lugares (X1, ainda
aberto).
⚠️ **Limite conhecido, escrito no teste:** CNPJ com `/` (`12.345.678/0001-99`) **não chega na rota** —
a barra parte o caminho em dois segmentos. Ponto, traço e espaço funcionam, e a tela liga pelo CNPJ
limpo, que é como a base o guarda.

---

# 12. Fase 1 da operação de financeiro — blocos F1 a F4 (30/10/2026)

> 🔵 **Escopo decidido por ele em 30/10:** *"F1 + F2 + F3 + F4: já nascer com
> preço"*. Nada de emitir boleto (F8, espera a D8) e nada de fechar o mês (F5).
> Controle da frente: `C:\Users\Lenovo\Desktop\CAR_1.1_Financeiro_FPSL.md`.

## 12.1 O que o financeiro do Harmonit dá, e o que NÃO dá

Pergunta dele, textual: *"conseguimos via API puxar as placas que ou consultar as
que estão sendo cobradas no harmonit? e valores tbm? e outras cobranças tbm?"*.
Medido ao vivo em **30/10**, só com `GET`, em 297 lançamentos de vencimento
10/2026:

| | Resposta medida |
|---|---|
| **Placas** | 🚨 **NÃO.** Os 12 campos do lançamento são `id · pagamento · descricao · contatoId · contato · valor · categoria(Id) · centroCusto(Id) · contaCorrente(Id)`. **Zero** das 297 descrições traz placa, e o `swagger.json` **não tem nenhuma rota de contrato** (`/Contrato*`, `/Mensalidade*`, `/Parcela*`). A placa só existe do nosso lado: `contrato_placa` + cache da WESO |
| **Valores** | ✅ **Sim**, por lançamento e por cliente; os "a baixar" trazem `vencimento`, `valorFinal`, `nossoNumero`, `numeroDocumento`. A conta é **Banco Asaas** |
| **Outras cobranças** | ✅ **Sim, cinco tipos:** Mensalidades (265) · Prestação de Serviços = `Ordem de Serviço Nr. X` (23) · Venda de Produtos = `Venda Nr. X` (4) · `boleto`/sem centro (4) · Adesão (1). E aparece **`Negociação 17/24`** — parcelamento |

## 12.2 `car_faturado` — o espelho (F1)

Espelho, **não fonte**: nada aqui decide cobrança. O que a CAR afirma sai de
`car_evento` (preço) e da CTR (placas).

- **A chave é o `id` do Harmonit**, e é isso que torna reler um mês idempotente
  (`INSERT OR REPLACE`): o lançamento que era `a_baixar` e virou `baixado`
  **muda de estado**, não vira duas linhas.
- **`competencia` sai do TEXTO** (`"... ref. período 09/2026"`) e é **NULA**
  quando o texto não diz. 🚨 Nunca cai no mês de vencimento: das 261
  mensalidades baixadas em outubro, 233 eram de referência 09/2026. ⚠️ A **v2**
  da rota, que traria `competencia` como campo, **recusa esta empresa**.
- **`tipo` sai do TEXTO**, não do `centroCusto`: 4 mensalidades chegam com
  centro `boleto`. O centro de custo fica gravado cru, e é ele que separa
  recorrente de avulso na tela.
- **`venc_ano_mes`** guarda de que mês de vencimento a linha veio. É
  proveniência, e serve para a tela dizer se a conta do mês está completa.
- **A amarração é (cliente, número do contrato)**, nunca o número solto. Medido
  em 30/10 nos vencimentos 09 e 10: dos **544** lançamentos com número,
  **537 (98,7%)** acham termo **do próprio cliente**; 2 números não existem e 5
  lançamentos têm `contatoId` fora de `clientes`. O desempate entre homônimos é
  o `resolver_termo` da pré-fatura (**MOVISAT vence**).

🚨 **A JANELA DE VENCIMENTO ERA CURTA E SUBESTIMAVA A RECEITA EM SILÊNCIO.**
Medido em 30/10: a competência **2026-09** tem lançamento em **sete** meses de
vencimento (04 a 10/2026) — **282 lançamentos, R$ 185.234,14** — e **5 de
vencimento abril** somam R$ 15.678,03. Com a janela de 6 meses a conta de
setembro fechava em R$ 163.666,05, e **nada dizia**. A passada varre **10 meses**
(6 atrás, 3 à frente, mais o corrente = 20 `GET`, ~1,5 min), e a pré-fatura
**declara de quantos meses de vencimento aquela competência foi lida**, nas duas
pontas da janela.

## 12.3 A rotina e o botão (F1)

🚨 **Nasce DESLIGADA** (`faturado_sync_ativa`), interruptor **na tela dela**.
Ler o interruptor exige `contas_receber`; **mudar exige `config`** — a mesma
régua da `FIN_1.1` e da auditoria da CTR. É o **10º laço** do FPSL
(`rotinas.LACOS["faturado"]`, 1×/dia).

🔵 **A régua do botão, frase dele:** *"nasce desligada mas tbm pode ser feita
pelo botão, até que decidam deixar ligada, aí o botão esmaece ou só pode ser
usado mais 1 vez no dia 4hrs após a automática, quando ligada"*. Implementada em
`car_faturado.pode_atualizar_agora`, **pura**, com 4 casos travados por teste. A
recusa é **429 com o motivo escrito**, e a tela esmaece o botão **dizendo por
quê** e a que hora libera.

## 12.4 As três colunas, no CLIENTE (F2)

`deveria cobrar × cobrado × recebido`, com o termo como detalhe de dentro.

🚨 **A unidade é o CLIENTE, porque é dele que sai o boleto.** Medir por termo foi
erro de 28/10: a XOMV é faturada no termo 306 e usa 53 placas nos termos
8531/8754/8802, e a conta por termo a acusava de "cobra sem usar" **e** "usa sem
cobrar" ao mesmo tempo.

Duas listas, nunca uma (defeito meu achado com dado real em 30/10):
- `nao_amarrados` — lançamentos **desta** competência sem cliente ou sem
  contrato conhecido. **7** em 2026-09.
- `sem_competencia` — o que não pertence a mês nenhum pelo texto: OS, venda,
  adesão sem período, parcelamento. **333 lançamentos, R$ 281.795,87**. Misturar
  os dois dava uma lista de 340 linhas numa pré-fatura de setembro.

Com `car_faturado` vazia a resposta traz `faturado.lido = false` **com o motivo**
e a tela diz isso, em vez de desenhar R$ 0.

## 12.5 A régua dele, portada (F3)

🔵 Decisão de 30/10: **interseção, com as duas colunas visíveis**. A cobrança é
pela WESO **em uso** (`Instalado`), e a tela mostra ao lado o que o contrato
prevê, com a diferença por cliente.

- O mapa `{placa: situação}` vem do **cache diário** da WESO
  (`/home/claude/weso_cache/weso.db`, cron 04:15), pelo leitor que já existia
  (`services.contratos_auditoria._weso_do_cache`). A **idade do cache** aparece
  na resposta e na tela.
- ⚠️ **Injetado, não lido pela pré-fatura**: `montar(conn, comp, weso=..., idade_weso=...)`.
  Sem o mapa, `em_uso_weso` é **`None`** em toda linha — nunca `False`, que
  afirmaria "não está instalada".
- Situação intermediária (Estoque, Bancada, Manutenção, Comodato) **não é uso** e
  aparece **com o nome** (`situacao_weso`), não como um "não" sem causa.
- **A fila reordena:** primeiro quem tem placa em uso e **nenhuma mensalidade
  cobrada** no mês. É o conserto do achado **A1** — a ordem velha punha a Horse
  na frente, com 356 placas cobráveis e **zero** instaladas.

Medido na produção em 30/10, competência 2026-09: **3.033 placas cobráveis ·
1.606 em uso na WESO · 1.427 contratadas e não instaladas · 26 clientes usando
sem faturar**. O primeiro da fila nova é a **CONSTRUCTO** (21 placas, 18 em uso,
nada cobrado) — a mesma empresa que o levantamento `F0` apontou.

## 12.6 Semear preço (F4)

🔵 Decisão dele, 30/10: *"faça o 2 [o lote], mas deixe as regras do 1 tbm, para
quando alguem alterar os demais"*.

- `car_faturado.propor_precos` é **puro** e devolve `propostas · conflitos ·
  sem_termo`. **Conflito não entra no lote**: contrato que já tem preço vigente
  diferente, ou dois valores no mesmo mês, pede decisão.
- `POST /painel/api/car/semear` grava. 🚨 **O corpo diz QUAIS, nunca QUANTO**: o
  valor, a competência e o documento saem do espelho desta base — aceitar valor
  do corpo deixaria quem chama a rota escolher preço. O autor sai do **token**.
- O `documento` é o lançamento de origem (`"mov. financeira 10396439"`), e o
  motivo padrão é *"preço adotado do que o Harmonit já fatura neste contrato"*.
- **Idempotente** por (termo, competência, valor); **recusado não derruba o
  lote**. `POST /termo/{id}/preco` continua sendo o "adotar" de uma linha.
- Medido na produção em 30/10, competência 2026-09: **274 propostas,
  R$ 167.684,06, ZERO conflitos**, 6 lançamentos de mensalidade sem contrato
  nesta base.

🚨 **Nada foi semeado na produção**: `car_evento` segue com 0 linhas. O lançamento
é ato dele, no botão.

## 12.7 O defeito de dinheiro que o teste pegou antes de valer nada

O Harmonit manda `200.53` (número JSON, ponto decimal) e **todo dinheiro desta
casa é texto em convenção brasileira** — `car_prefatura._centavos` lê o ponto
como **separador de milhar**. Guardar o número cru fazia R$ 200,53 virar
**R$ 20.053,00** na soma, cem vezes mais. E o valor do espelho é **copiado** para
`car_evento` pela semeadura, onde é imutável. `car_faturado.valor_texto`
normaliza na entrada, num lugar só, com teste.

## 12.8 As 21 rotas (eram 16)

As 5 novas: `GET`/`PUT /faturado/interruptor` · `POST /faturado/atualizar` ·
`GET /semear` · `POST /semear`. Todas herdam `requer_aba("contas_receber")` do
`APIRouter`; o `PUT` exige **também** `config`.

## 12.9 Travas

`teste_car_faturado.py` (**72**) · `teste_car_semear.py` (**42**) · e os
ampliados `teste_car_tabelas` (44, com a 4ª tabela), `teste_car_prefatura` (53,
com o CSV de 14 colunas), `teste_car_router` (106, com as 21 rotas e a exceção
do `config` nomeada), `teste_roteadores_painel` (102, com as 5 rotas novas na
matriz escrita à mão — a armadilha `X0`).

**Suíte inteira em 30/10: 77 arquivos, 76 verdes, 1 vermelho** (`teste_extrair_termo`, que espera decisão dele). A baseline do dia, antes de qualquer alteração, era 75/74/1 — o `teste_higiene_placas_weso`, 2º vermelho desde 28/10, passou a verde sozinho.

## 12.10 ⚠️ O limite da coluna "em uso", declarado (medido em 30/10)

Das **2.946 placas sustentadas** (`ATIVA` ou `EM_AVISO_PREVIO`), **1.625 casam** com alguma chave do
cache da WESO. As outras aparecem como **não em uso** — e isso é o limite, não a verdade:

- **338 têm chave com cara de chassi** (mais de 8 caracteres) e **só 39 dessas casam**. O mecanismo
  cobre chassi (`_weso_do_cache` indexa `chave_placa` **e** `chassi`, e o cache tem 327 chaves de
  chassi), então o que falta é o veículo, não a regra.
- **E parte nem é identificador:** há **nome de pessoa na coluna de placa** — `MARTONE2009`,
  `NAILZASILVA986`. Isso é higiene de `contrato_placa.placa_chave`, e pertence à `CTR_1.1`.

🚨 **Consequência que a tela tem de respeitar:** `em_uso` é **piso**. Chave que não casa empurra o
cliente para *"usa e não fatura"* ou o tira de lá — então o número vem sempre ao lado do **previsto
no contrato** (a interseção que ele pediu em 30/10), e nunca sozinho.

## 12.11 ⚠️ A decisão D6, encurtada — mas não extinta

O achado de 30/10 (`cobrar` por item, provado contra o faturado) **resolve o mecanismo**: não há lista
de itens do catálogo a levantar. **Mas continua sendo decisão dele** uma pergunta de uma linha:
**a CAR adota o `cobrar` do Harmonit como régua da parte variável?** Enquanto ela não vier, o espelho
**guarda e mostra** os lançamentos de serviço e a CAR **não** calcula variável.

## 12.12 O que foi exercitado ao vivo em 30/10, e o que não

| Exercitado | Como |
|---|---|
| o espelho inteiro | botão **Atualizar agora**: 3.070 lançamentos, 10 meses, 20 `GET`, ~1min15, zero falhas |
| a conferência do espelho | competência 2026-09 fechou em **282 lançamentos / R$ 185.234,14**, igual ao medido ao vivo no Harmonit |
| o `PUT` do interruptor | ligado e desligado com token de owner; corpo sem `ativa` → **400** |
| 🔵 **a régua do botão** | com a rotina **ligada** ele recusou dizendo *"vale uma vez por dia, e já foi usado hoje às 12:17 UTC"* |
| as propostas de preço | **274 propostas, R$ 167.684,06, zero conflitos** (`GET /semear`) |
| o CSV da pré-fatura | 14 colunas, com `em_uso_weso` e `situacao_weso` |

| **NÃO** exercitado | Por quê |
|---|---|
| a passada **automática** da rotina | ela nasce desligada; o laço só carimbou *"desligada"* (12:10 e 12:19) |
| o **lançamento** de preço | são 274 eventos de dinheiro com autor — é o clique dele |
| o `POST /prefatura/fechar` | não tem botão na tela (achado **A2**), e `car_leitura` segue vazia |
| **a tela no navegador** | `M9`: nenhuma suíte vê tela quebrada |
