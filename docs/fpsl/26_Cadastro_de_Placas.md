# Cadastro de Placas pelo termo

**Data:** 2026-08-17 · **Estado:** no ar, **escrita desligada** (`placas_registro_ativo`)

A aba entre o termo assinado e a OS. Antes dela, alguém digitava as placas na
WESO uma a uma e o Harmonit recebia por outro caminho — o mesmo documento era
lido duas vezes, uma por pessoa e outra pela máquina.

---

## Quem escreve o quê

| | Harmonit | WESO |
|---|---|---|
| Cliente | **só leitura** | cria se faltar |
| Veículo | cria | cria |
| Recipiente | **não entra** | cria |

🚨 **O painel nunca cria cliente no Harmonit** (decisão do usuário, 17/08). O
cliente já está lá por definição, porque é de lá que os termos vêm. Corolário:
**termo existe ⇒ cliente existe no Harmonit** — a busca por CNPJ acontece só
para pegar o `clienteId`, que o `/Veiculo/Incluir` exige e o termo não traz.
Falhar ali é erro a reportar, **não caminho alternativo**.

🚨 **O recipiente não vai ao Harmonit.** Ele é bancada do setor de configuração,
não veículo do cliente — lá só entra o que roda na rua.

---

## As travas

### Só `/Veiculo/Incluir`, com `id: 0` explícito

`PUT /Veiculo/Atualizar` tem os **mesmos campos** e, sem `id`, **cria em vez de
atualizar**. Foi ele que fez **88 veículos** por engano em 27/07 e quebrou **93
vínculos**, que continuam quebrados por decisão do usuário.

Deixando-o fora, o erro fica impossível **por construção**. O teste extrai a
lista de endpoints de escrita realmente chamados e exige que seja exatamente
`{/Veiculo/Incluir}` — comentar sobre o `Atualizar` continua livre, chamá-lo
reprova.

### Harmonit antes da WESO, e falha do primeiro para

Na ordem inversa sobraria veículo na WESO sem par — o estrago espelhado do de
27/07.

### Já existe → informa, não cria

Comparando **sem espaço e em caixa alta**. A WESO grava a placa convencional
COM espaço e a consulta dela é igualdade exata; o Harmonit grava como veio.
Comparar texto cru diria "não existe" para placa que existe — foi assim que a
`TTX 0H91` do termo 8788 sumiu em julho.

### Nada grava sem passar pela tabela editável

E a descrição é **obrigatória**: sem ela a WESO grava a própria placa como
descrição (medido no `TST 0F66`), que é dado inventado entrando em produção.

### Interruptor próprio, desligado

`placas_registro_ativo` cobre os dois sistemas. Não reaproveita o
`oficina_registro_ativo`, que controlava outra coisa e saiu do sistema em 17/08.

---

## Uma requisição por placa

🚨 **Não é lote.** Gravar custa ~10 a 16s por placa, porque cada criação é
seguida de releitura. Um termo de 11 placas em lote passaria de 2 minutos —
perto demais do teto de 180s do nginx. Mexer no teto trataria o sintoma.

Uma requisição por placa resolve a causa e **isola o erro**: falhou a sétima, as
seis anteriores estão gravadas E PROVADAS, e o histórico mostra onde parou.

A tela mostra progresso linha a linha, com relógio a partir de 5s.

---

## Os dois espelhos, e por que são diferentes

🚨 **NENHUM DOS DOIS SISTEMAS FILTRA POR CLIENTE OU POR PLACA.** Medido em 17/08:

| | Filtro funciona? | Base inteira |
|---|---|---|
| `/Veiculo/ObterVeiculos` (Harmonit) | **não** — `?placa=` e `?clienteId=` devolvem os 9.107 igual | **1,9s** |
| `/Veiculos/Consultar` (WESO) | `?placa=` sim (igualdade exata); `?cliente_id=` **é ignorado** e devolve a base | **18,6s** |

A WESO é **dez vezes mais lenta com cinco vezes menos registros**. Por isso:

- **Harmonit:** espelho em memória, 120s de validade. Sem ele seriam 1,9s por placa.
- **WESO:** o cache local (`weso_cache/weso.db`, cron 04:15) resolve em ~1ms o
  que já existia ontem; só o que falta cai no espelho em memória.

### Dois defeitos que o ponta a ponta revelou

**1. A releitura pós-gravação custava 15 a 36s.** Usava `buscar_veiculo`, que
tenta o exato e, falhando, baixa a base inteira. Só que logo depois de criar o
exato **acha** — 0,2s medidos. O caminho caro nunca precisava ser alcançado, e
quando era, chegava perto do timeout de 30s do cliente. Agora a releitura é a
consulta exata e ponto: **não achou = não gravou**.

**2. O espelho não sabia das placas que ele mesmo criava.** Depois de criar
quatro, a prévia respondeu `criar: 4` para as mesmas quatro — num segundo
clique tentaria duplicar. Agora toda criação confirmada é acrescentada ao
espelho na hora.

⚠️ **O timeout do cliente WESO é 30s e a base leva 18,6s.** Sobram 11s de folga.
Teto é decisão do usuário; se a folga encurtar, é preciso avisar.

---

## O registro

`cadastro_placas_log` — construída **antes** do código que escreve, de
propósito: é com ela que a própria escrita foi verificada durante o
desenvolvimento. Mesmo raciocínio do expurgo da oficina, onde os testes vieram
antes da remoção.

**Uma linha por (placa, sistema)**, não por placa. A mesma placa produz duas
tentativas e elas podem terminar diferente — e foi exatamente o que aconteceu no
ponta a ponta: a `CHASSI: 9BD281AJPTYBM7701` nasceu no Harmonit (`108714`) e
**não** na WESO. O log contou; sem ele, seria preciso comparar as bases inteiras
para descobrir.

**`lote` amarra a rodada** — um termo subido é um lote. Sem ele o histórico é
lista solta e não dá para ver "o 8800 gerou estas 11, e 2 falharam".

**Ação desconhecida grava, não derruba.** Sem `CHECK` na tabela de propósito:
registro que se recusa a gravar perde o caso que ninguém previu, que é o único
que interessa descobrir depois. Valor estranho vira `desconhecido` com o
original preservado no erro.

**Simulação é registrada** e fica fora da listagem padrão.

### A tela de histórico

`/painel/cadastro-placas/historico` — **mesma aba**, fora da sidebar, alcançada
por link. Não é aba nova: quem cadastra precisa ver o que cadastrou, e uma
permissão separada para "ver o que eu mesmo fiz" seria burocracia sem dono.

**Só leitura.** Reprocessar escreve, e botão que escreve merece rodada própria —
placa que falhou pode ser refeita subindo o mesmo termo.

---

## As duas origens

| | Com termo | Sem termo (manutenção) |
|---|---|---|
| Placas vêm de | PDF | digitadas |
| Cliente | pode ser novo na WESO | sempre existe |
| A aba cria | veículos + recipiente | **só o recipiente** |
| Vai ao Harmonit? | sim | não |

O caminho digitado **não foi substituído** — os dois perfis de manutenção têm
`sem_termo`, e sem ele a manutenção pararia de funcionar.

### A tabela editável

Colunas **Veículo | Placa**, na ordem do documento, com **⇄ por linha**.

Inverter é por linha e não global: o erro contratual costuma ser em algumas
linhas, não no documento inteiro. É essa edição que resolve chassi,
identificador estranho e erro de extração — em vez de o sistema adivinhar.

🚨 **Chassi e série entram COMO ESTÃO.** Provado em 17/08 nos dois sistemas:
`CHASSI: 9BD281AJPTYBM9001`, `CHASSI:1BM6115J JMD009001` (sem espaço após os
dois-pontos, com espaço no meio) e `SERIE 99001` foram gravados sem mutilação.
`convencional` é **rótulo para a tela destacar**, não tratamento diferente.

### O recipiente vem do perfil

`upgrade` traz `-UPGRADE`, `manutencao_troca` traz `-MANUT`, os sete de contrato
não trazem nenhum. **Não há seletor** — seria uma chance a mais de escolher
errado.

A descrição é **derivada**, nunca digitada: `TERMO {n}` ou `MANUTENCAO`. É
contrato com o gerador de OS, que confere esse texto para reconhecer o
recipiente. **Upgrade sem número de termo é recusado**, em vez de gravar
`TERMO ` pela metade.

---

## O risco que esta tela cria

Antes dela, extração errada gerava **OS errada** — visível, corrigível. Agora
cria **veículo fantasma**, invisível no meio de 9.107 no Harmonit e 1.969 na
WESO. Já aconteceu: no termo 8800 o extrator inventou a placa `RFD 2447`,
corrigido em 07/08.

As defesas são três: a tabela editável (o operador vê antes), o registro (dá
para achar depois) e o teste que exige **11 de 11 no 8800 sem a `RFD 2447`**.

---

## Os três termos reais

Guardados como fixture, com os números medidos antes de existir código:

| Termo | Perfil | O que exercita |
|---|---|---|
| `contrato_novo_8739.pdf` | `cliente_novo` | 4 veículos, **todos por chassi**, nenhum com placa |
| `aditivo_8840.pdf` | `aditivo` | 1 placa convencional |
| `upgrade_4g_8800.pdf` | `upgrade` | 11 veículos: placas, série, chassi grudado, e **uma linha sem descrição** |

⚠️ O 8800 **já era fixture** desde 07/08 — o mesmo arquivo, md5 idêntico.

⚠️ As placas dos três **existem na WESO sob os donos verdadeiros** (FCV, FISCCO,
REMOVERDE). Nos testes o miolo é trocado mantendo a forma, e tudo vai para a
Pastelaria Velasco.

---

## Dados de teste

| O quê | Onde |
|---|---|
| Velasco 1 | WESO `13562` · Harmonit `998063` · CNPJ `WQ0P6GLD000108` |
| **Velasco 2** | WESO `13624` · CNPJ `WQ0P6GLD000280` · **não existe no Harmonit** |
| Concox em estoque | ids `2335`, `3681`, `3690`, `3691`, `3700`, `8791`, `10169` |

A Velasco 2 existe para exercitar "criar cliente na WESO": as duas fixtures de
cliente novo têm o cliente **já cadastrado** lá (FAG `13488`, ELVINO `13534`).
Criar cliente na WESO exige só `cnpjcpf` e `razaoSocial` — o par que o termo
entrega. `situacao` vem `Adimplente` sozinha.

---

## Suíte

**804 verificações em 22 arquivos** (medido em 19/08). As deste trabalho:

| Arquivo | O que prende |
|---|---|
| `teste_cadastro_log.py` | o registro: duas linhas por placa, lote, ação desconhecida, corte pelo lado certo |
| `teste_extrair_termo.py` | os três termos, com os números medidos |
| `teste_tela_cadastro_placas.py` | os dois caminhos convivem, inverter por linha, descrição obrigatória, escape |
| `teste_criar_uma.py` | só o `Incluir`, ordem Harmonit→WESO, recipiente fora do Harmonit, simulação não escreve |

⚠️ **Falhas conhecidas e aceitas** em `teste_upgrade_8820.py`: são **8**, não
1, e os recipientes que sumiram da WESO são `OOM4131-UPGRADE` e
`OOM3895-UPGRADE` — **não** o `GCW9H80-UPGRADE` que este texto afirmava. O
próprio teste diz que "ausência de recipiente NÃO bloqueia", então não é
defeito. Corrigido em 19/08.

---

## Limpeza das placas de teste (2026-08-19)

As **7 placas** criadas por esta tela em 17/08 foram apagadas da WESO. Os ids
não vieram de lista escrita à mão: vieram do próprio `cadastro_placas_log`,
filtrando `acao IN ('criado','ja_existia')` — que é a razão de o registro
existir.

| Placa | WESO | Harmonit |
|---|---|---|
| `TST 0G77` | `88362` apagada | `108713` **fica** |
| `CHASSI: 9BD281AJPTYBM7701` | `88368` apagada | `108714` **fica** |
| `CHASSI: 9BD281AJPTYBM7711` | `88365` apagada | `108715` **fica** |
| `CHASSI: 9BD281AJPTYBM7721` | `88366` apagada | `108716` **fica** |
| `CHASSI: 9BD281AJPTYBM7731` | `88367` apagada | `108717` **fica** |
| `CHASSI: 9BD281AJPTYBM7741` | `88369` apagada | `108718` **fica** |
| `CHASSI: 9BD281AJPTYBM7751` | `88370` apagada | `108719` **fica** |

Base da WESO: **1972 → 1965**, conferido relendo, e o cache local foi
atualizado na hora (não esperou as 04:15). Nenhuma tinha rastreador vinculado,
então nenhum equipamento ficou órfão.

### 🚨 O Harmonit não tem como apagar veículo

`/Veiculo/` expõe `ObterVeiculos`, `ObterTipoEMarca`, `Incluir` e `Atualizar`
(`docs/harmonit/06_Ativos.md`). **Não há DELETE.** Os 7 registros continuam lá,
sob o cliente `998063` (Pastelaria Velasco), sem rastreador e sem chassi.

Não se tentou contornar com `PUT /Veiculo/Atualizar`: em 27/07 um `PUT` sem
`veiculoId` **criou 88 veículos**, e `ativar: false` e `clienteId: 0` são
aceitos e ignorados. Chutar verbo de exclusão em ERP de produção com 9.114
veículos não se faz sem decisão de quem responde pelo sistema.

### 🚨 Existem 9 outras placas de teste na WESO — e NÃO se apagam

Levantadas na mesma varredura, fora do escopo das 7:

| Placa | id | Nota |
|---|---|---|
| `TST 0A11` · `TST0A11-MANUT` | `88341` · `88342` | **fixture viva**: `teste_cadastro_placas.py:144` exige que existam, para conferir a ação `ja_existe` |
| `TST 0B22` · `TST0B22-UPGRADE` | `88344` · `88345` | de 17/08, sem rastreador |
| `TST 0D44` · `TST0D44-UPGRADE` | `88349` · `88350` | de 17/08, sem rastreador |
| `TST 0E55` | `88357` | **fixture viva**: `teste_criar_uma.py` exige que exista nos DOIS (Harmonit `108711`) |
| `TST 0F66` | `88358` | de 17/08, sem rastreador. Existe nos dois (Harmonit `108712`) — é a reserva se a `TST 0E55` cair |
| `TESTE-RFID` | `88407` | ⚠️ **criada em 19/08 13:19 UTC**, com rastreador real `40907` (ST4305, série `1610038792`, situação Instalado, com SIM). Não é resto de teste antigo — é uso corrente |

Apagar `88341`/`88342` quebraria a suíte. Apagar `88407` deixaria um rastreador
**Instalado** órfão, porque excluir o veículo na WESO não libera o rastreador —
são duas chamadas. As outras 6 aguardam decisão do usuário.

### 🚨 A lição: apagar exige `grep`, inclusive no que você mesmo criou

A limpeza das 7 quebrou o `teste_criar_uma.py`. Ele usava `TST 0G77` como
fixture "existe nos DOIS" — e a dependência não estava escrita em lugar nenhum
além daquela linha. Antes de apagar, foi feito `grep` pelas **9 placas que
ficariam**, e não pelas **7 que sairiam**: conferiu-se o lado errado.

A fixture passou a ser `TST 0E55`, com um comentário no próprio teste dizendo
que ela não pode ser apagada. O `grep` que faltava era de um segundo:

```bash
cd /home/claude/fpsl_weso && grep -rn "TST 0G77" --include='*.py' .
```
