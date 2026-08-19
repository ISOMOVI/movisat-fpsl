# 28 — Operações: a aba única que substitui Cadastro de Placas e Gerar OS

> Especificação fechada com o usuário em 2026-08-19, antes de qualquer código.
> Escrita porque acumulamos 11 perfis, 2 renomes, 6 regras mudadas e uma rotina
> com 4 casos em quatro mensagens de conversa — e o que não vira spec vira
> interpretação minha. Foi interpretação minha que produziu três pendências
> inventadas no mesmo dia.

---

## Por que a aba existe

Não é organização. **Hoje o operador sobe o mesmo termo duas vezes**, em duas
telas, e cada uma extrai o PDF por conta própria. Pior: a corrente
**cliente → placa → OS não é imposta em lugar nenhum**. Dá para gerar OS de
placa que não existe na WESO, e o resultado é OS sem equipamento e sem chip —
que é exatamente a forma da OS 16775.

A tela única não é conveniência. É o que torna a ordem obrigatória.

---

## Identidade

| | |
|---|---|
| Código | `OPR_1.1` |
| Título | Operações |
| Rota | `/painel/operacoes` |
| Permissão | `operacoes` (nova, ninguém tem) |
| Menu | **fora**, até o usuário mandar entrar |

🚨 **NASCE AO LADO, NÃO POR CIMA.** As duas telas atuais continuam no ar e
intactas. A substituição é a última fase, e só depois de uso real. É o oposto
do que se fez com o interruptor do Cadastro de Placas em 19/08, onde a remoção
veio antes da garantia do que dependia dele.

---

## Clonar × reusar — o critério que decide o desenho

> **Se a regra muda entre a aba velha e a nova, CLONA. Se é infraestrutura sem
> regra, REUSA.**

Compartilhar o que muda obriga a escolher entre quebrar a aba velha e travar a
nova. E as duas velhas vão ser apagadas: o que a nova precisar tem de já morar
nela.

| Recurso | Decisão | Por quê |
|---|---|---|
| `client.py`, `harmonit_client.py` | reusa | fala HTTP com os fornecedores, zero regra |
| `storage.py` | reusa, **tabelas próprias** | o banco é um só; as tabelas da aba nascem com nome próprio |
| `auth.py`, `telas.py`, `abas.py` | reusa | permissão é do painel, não da aba |
| `sidebar.js`, `barra_status.*`, CSS | reusa | é o padrão visual dos quatro painéis |
| `templates_config.py` | **CLONA** | os perfis vão de 9 para 11, com 2 renomes e 6 regras mudadas |
| `equipamentos.py` | **CLONA** | carrega decisão: marcadores, limiares, `liberar_recipiente`, a regra do modelo |
| Montagem de OS | **CLONA** | é o coração das 6 regras que mudaram |
| Cadastro de placa | **CLONA** | ganha a etapa de cliente na frente e a `placa_entrada` |
| `pdf_extractor.py` | **reusa** | 931 linhas e a regra dele NÃO muda: os padrões de documento são os mesmos |

⚠️ **O `pdf_extractor` é a única exceção, e é o risco que fica de pé.** É o
único ponto que a aba nova e as velhas dividem de verdade. Se ele precisar
mudar para a aba nova antes da substituição, a mudança atinge as três telas. A
alternativa era clonar 931 linhas do componente mais testado do projeto
(57 verificações no `teste_regressao_extracao`) — escolha consciente.

### 🚨 O `os_router.py` NÃO pode ser apagado

Ele hospeda as rotas da tela de **Vínculos**, que fica:

```
/painel/api/vinculos                  requer_aba("vinculos")
/painel/api/vinculos/extrair-preview  requer_aba("vinculos")
/painel/api/perfis                    ← vinculos.html também consome
/painel/api/produtos/buscar           ← idem
/painel/api/servicos/buscar           ← idem
```

A limpeza final não é apagar dois arquivos: é **partir o `os_router` em dois**.
O que é de Vínculos fica; o que é de Gerar OS sai. 1.303 linhas hoje.

---

## Os 11 perfis

⚠️ **Os dois renomes existem porque o perfil é definido pelo que a OS FAZ, não
pelo motivo comercial.** Teste de tecnologia faz o mesmo que contrato novo:
placa nova, instalação, comodato, 1 OS por placa. Perfis separados duplicariam
template e ids idênticos. E só ficou possível agora: antes da regra 4, a
financeira de valor zero **escondia os itens**; com eles aparecendo e o
`cobrar` desmarcado, o mesmo perfil serve contrato pago e teste gratuito — quem
separa é o valor, não uma flag.

| # | Perfil | Termo | Etapa 3 | Recipiente | OS operacional | OS financeira |
|---|---|---|---|---|---|---|
| 1 | Contrato novo ou teste de tecnologia | sim | cria | — | 1/placa | 1/termo |
| 2 | Aditivo ou teste upgrade | sim | cria | — | 1/placa | 1/termo |
| 3 | Rescisão | sim | confere | — | 1/placa | 1/termo |
| 4 | Substituição | sim | cria a `placa_entrada` | — | 2/placa | 1/termo, R$ 299,90 marcado |
| 5 | Transferência — novo titular | sim | confere | — | 1 (comodato) | 1 |
| 6 | Transferência — antigo titular | sim | confere | — | 1 agregada, sem flag nenhuma | **não tem** |
| 7 | Upgrade de tecnologia | sim | cria | `-UPGRADE`, **só WESO** | 1/placa | 1/termo |
| 8 | Manutenção no local | não | confere | — | 1/placa | **não tem** |
| 9 | Manutenção com troca | não | cria placa e recipiente | `-MANUT`, **só WESO** | 1/placa | **não tem** |
| 10 | Ressarcimento sem termo | não | confere | — | **1 híbrida/termo** | é a híbrida |
| 11 | Ressarcimento com termo | sim | confere | — | **1 híbrida/termo** | é a híbrida |

🚨 **A ETAPA 3 NÃO É "CADASTRAR" — É "GARANTIR".** Em rescisão, transferência e
ressarcimento as placas já existem: a etapa confere e casa. Em contrato novo
ela cria. Mesma etapa, mesmo desenho, decisão por perfil. Se ela fosse só
"cadastrar", metade dos perfis a pularia e a corrente se quebraria justamente
onde ela serve.

⚠️ **O recipiente `-MANUT` passa a nascer NA TELA** (decisão do usuário,
19/08). Hoje ele nasce pelo setor de configuração minutos antes da OS, e é por
isso que a manutenção lê a WESO ao vivo (16–30s). Criando na tela, ela sabe o
que criou: **a leitura ao vivo do recipiente deixa de ser necessária.**

---

## As quatro etapas

### 1 — Documento

Perfil + PDF. Nos três perfis sem termo (8, 9, 10) não há documento: a etapa
vira entrada manual de cliente e placas.

Mostra o que leu **e o que não leu**: quantos veículos, quantos sem placa
convencional, quantos sem descrição, os itens de contrato, o número do termo.

🚨 **Veículo sem placa reconhecida APARECE, não vira identificador inventado.**
É a regra 13, e ela existe porque `RFD 2447` — placa que não existe na WESO —
nasceu de texto solto no termo 8800.

### 2 — Cliente

Harmonit e WESO lado a lado.

| Situação | Ação |
|---|---|
| Existe nos dois | exibe e segue |
| Só no Harmonit | **cadastra na WESO** (`cnpjcpf` + `razaoSocial` bastam; `situacao` vem `Adimplente` sozinha) e relê |
| Não existe no Harmonit | **para** |

⚠️ Parar é regra, não limitação: o painel nunca cria cliente no Harmonit, e
termo existente implica cliente lá. Ausência ali é sinal de termo ou CNPJ
errado.

### 3 — Placas

Tabela editável Veículo | Placa, com **inversor por linha** — o erro contratual
costuma ser em algumas linhas, não no documento inteiro. Cada linha mostra em
que sistema já existe.

Grava **uma requisição por placa**, Harmonit primeiro, WESO depois, relendo
cada uma. Falhou o Harmonit, **para**: não sobra veículo na WESO sem par.

🚨 **Recipiente só na WESO.** Ele é bancada do setor de configuração, não
veículo do cliente.

🚨 **CONSULTA EXATA, NUNCA A BASE INTEIRA.** Medido: base inteira 15,6s a
timeout de 30s; consulta de uma placa 0,2s. A base inteira só entra acima de
`LIMIAR_PLACA_A_PLACA`, e as barras de busca leem o **cache local**, não a WESO.

### 4 — OS

Vínculos resolvidos, operacional e financeira separadas, mostrando **o que vai
ser gravado** — não o que foi digitado.

🚨 **Seletor de modelo nas linhas sem equipamento na WESO.** Placa criada há
segundos não tem rastreador; sem rastreador não há modelo, e sem modelo não há
material nem chip — a forma da OS 16775, agora por desenho. O operador escolhe
pelo de-para (24 modelos), que entrega o produto do Harmonit e o valor
patrimonial. Não escolheu, fica em branco com aviso: **não se inventa.**

⚠️ **A série continua `NUMERO DE SERIE`** e está certo: ela só existe quando o
técnico instala.

🚨 **DOIS ESTADOS QUE HOJE PRODUZEM O MESMO TEXTO:** "ainda não vinculado,
porque a placa nasceu agora" e "não consegui ler a WESO". O primeiro é normal;
o segundo é o defeito da 16775. A tela sabe em qual está — ela mesma criou a
placa segundos antes — e tem de dizer.

---

## As 14 regras

| # | Regra | Estado |
|---|---|---|
| 1 | Comodato nunca cobra; o valor é patrimonial, não preço | mantém |
| 2 | Tem valor e não é comodato → cobra. Nunca os dois | mantém |
| 3 | Uma financeira por termo, **incluindo rescisão** | 🚨 **MUDA, e reverte decisão de 29/07** — ver abaixo |
| 4 | Financeira lista os itens de cobrança **sempre**; `cobrar` só marcado se valor > 0 | **muda** |
| 5 | Cabeçalho da financeira fixo: situação Financeiro, técnico Karla, prioridade sempre Normal | mantém |
| 6 | Ordem na operacional: Produto/Serviço sem flag → itens alocados → equipamento | mantém |
| 7 | Item de cobrança **não aparece** na de comodato. O `nas_duas` sai | **muda** |
| 8 | Manutenção não flega nada e não gera financeira | mantém |
| 9 | A WESO manda no modelo; sem equipamento, o operador escolhe pelo de-para | **muda** |
| 10 | Transferência novo titular vira **duas** OS: uma operacional de comodato + uma financeira | **muda** |
| 11 | Ressarcimento é **híbrida**: cobrança + oficina, sem comodato | **nova** |
| 12 | Substituição ganha financeira com `substituição em locais diferentes cliente`, R$ 299,90, **marcado** | **nova** |
| 13 | Não se inventa identificador: sem placa, chassi ou série, vai para decisão humana | mantém |
| 14 | "Inativar" = devolver o equipamento ao estoque. **Não se escreve `status_veiculo`** | **nova** |

### 🚨 A regra 3 reverte uma decisão de 29/07, e a razão dela está escrita

Eu afirmei na primeira versão desta spec que "uma financeira por termo,
incluindo rescisão" **já era o comportamento**. Estava errado: olhei
`sem_financeira` e não vi o `financeira_embutida`.

A rescisão **não gera financeira agregada hoje**. O comentário no
`templates_config.py` registra a decisão e o porquê:

> Decisão do usuário 2026-07-29: na RESCISÃO não se cria OS financeira
> separada. O item de cobrança (Taxa de Retirada, aviso prévio) vai em **CADA
> OS de placa**, com a flag `cobrar` preservada — *"é mais seguro assim"*: a
> cobrança fica amarrada ao veículo que a gerou, em vez de num agregado que
> pode ser fechado sem conferir placa a placa.

⚠️ **Trocar para financeira agregada devolve exatamente o risco que essa
decisão evitava.** Pode ser deliberado — a aba nova tem etapa de conferência
que a antiga não tinha, e isso muda a conta. Mas não pode passar por engano.

**Pendente de confirmação do usuário.** Enquanto isso o clone mantém
`financeira_embutida: True` na rescisão, que é o comportamento decidido.

### ⚠️ Duas coisas chamadas "híbrida", e são diferentes

- A que **acabou** (transferência novo titular): *cobrança + comodato* na mesma
  OS. Morreu pela regra 7.
- A que **nasce** (ressarcimento): *cobrança + oficina*. Não tem item de
  comodato nenhum, então não esbarra na regra 7.

São compatíveis. Não são a mesma coisa.

### O `nas_duas` sai limpo

Ele nasceu do caso 8839 / Central 24h em 14/08: fazia um item de cobrança
aparecer também na operacional, com valor zero. Decisão do usuário em 19/08:
**Central só nas OS operacionais.** Com isso cada item pertence a **um lado
só** e o conceito de "item que aparece nos dois" desaparece — não fica órfão.

### Regra 14, e por que ela contraria a sugestão anterior

> **Objetivo** — veículo de cliente encerrado para de rastrear sem perder histórico.
> **Hoje** — igual: devolver o rastreador ao estoque deixa o veículo com
> `rastreador_id: null` — não transmite, não aparece, não some.
> **Por quê** — os 1.958 veículos lidos em 17/08 estão **todos** com
> `status_veiculo = 0`. A WESO não usa esse campo; escrever nele seria nós
> inventarmos o significado, que é a mesma família da placa inventada. E
> `/Veiculos/Excluir` apaga um veículo real.
> **Reavaliar se** — alguém precisar ver "inativo" escrito na tela da WESO. Aí
> o primeiro passo é perguntar à WESO o que valem 1 e 2, não chutar.

---

## A rotina

| Caso | Gatilho | Ação, **nesta ordem** |
|---|---|---|
| Recipiente `-MANUT` / `-UPGRADE` | a cada 6 h | série apareceu na WESO → escreve na OS → devolve ao estoque → **remove** o recipiente |
| Rescisão | oficina "desinstalado" | devolve ao estoque → veículo fica sem rastreador |
| Ressarcimento | oficina na híbrida | devolve ao estoque → veículo fica sem rastreador |
| Substituição | oficina | solta do veículo antigo → confere `Estoque` relendo → **vincula** na `placa_entrada` |

🚨 **DEVOLVER AO ESTOQUE É SEMPRE O PRIMEIRO PASSO.** Excluir o veículo **não**
libera o rastreador — são duas chamadas, e `situacao` é objeto
(`{"descricao": "Estoque"}`), não texto. Medido em 14/08 na Velasco: apagado o
veículo, o rastreador continuou `Instalado` sem veículo nenhum.

🚨 **A SUBSTITUIÇÃO É A ÚNICA QUE VINCULA**, e a WESO **recusa vincular
rastreador já `Instalado`** (409 em HTML). Inverter a ordem prende o
equipamento no veículo errado.

⚠️ **Ela lê a tabela do painel, não o Harmonit.** O varredor de OS já roda a
cada 5 min e guarda a oficina em `os_historico`; a rotina consome dali.

### Os três riscos dela

1. **Precisa de um vínculo OS ↔ recipiente que hoje não existe.** Grava-se, na
   geração, qual OS ficou esperando qual recipiente. Deduzir depois pela
   descrição é frágil e falha em silêncio.
2. **Vai reescrever OS já criada.** Regravar com `id` atualiza em vez de
   duplicar, **mas é save completo**: tem de reler a OS inteira antes de
   gravar, senão apaga o que não mandou.
3. **Precisa de teto de tentativas.** Recipiente cuja série nunca aparece seria
   consultado a cada 6 h para sempre. Depois de N rodadas, vira aviso no
   Registro em vez de continuar tentando calado.

---

## Fora de escopo

🚨 **Equipamento e chip na WESO não são desta tela** (decisão do usuário,
19/08). As 4 etapas mexem em placa, cliente e OS. Criar equipamento, vincular
SIM, gerir estoque — nada disso.

A **rotina** encosta em equipamento, e só nos 4 casos acima. A única coisa na
tela que chega perto é o seletor de modelo da etapa 4, e ele **não escreve na
WESO**: só diz à OS qual produto do Harmonit anexar.

---

## Fases

| Fase | Entrega | Estado |
|---|---|---|
| **F1** | Registro de tela, rota, permissão, esqueleto das 4 etapas, clone dos 11 perfis | ✅ **ENTREGUE** `feb24d6` |
| **F2** | Etapas 1 e 2 — documento e cliente | ✅ **ENTREGUE** `7b21e8b` |
| **F3** | Etapa 3 — placas, com lote retomável | ✅ **ENTREGUE** `df875a0` |
| **F4** | Etapa 4 — OS, com as 14 regras | falta — a mais densa |
| **F5** | A rotina, com os 4 casos e teto de tentativas | falta |
| **F6** | Registro cobrindo o fluxo novo | falta |
| **F7** | Substituição: as duas velhas saem, o `os_router` parte em dois | falta — depende de uso real aprovado |

**Dentro da F4, nesta ordem:** as 6 regras que mudaram (4, 7, 9, 10, 11, 12) ·
o seletor de modelo para placa sem equipamento na WESO · a distinção entre
"ainda não vinculado" e "não consegui ler a WESO" · as duas OS de novo titular ·
a híbrida do ressarcimento.

**Cada fase termina com teste que reprova sem ela.** De F3 em diante, com
dublês: **nenhum teste da aba nova escreve em sistema externo.** Em 17/08 a
própria suíte criou 6 veículos permanentes no Harmonit via
`POST /painel/api/placas/criar` de `127.0.0.1` — não se repete.

---

## 🚨 O que a CONSTRUÇÃO achou, e a spec não previa

Quatro coisas que só apareceram ao codar. Registradas aqui porque cada uma
mudaria a spec se tivesse sido sabida antes.

**1. A substituição não usa `placas`, usa `pares`.** O extrator devolve
`{placa_saida, veiculo_saida, placa_entrada, veiculo_entrada}` — é o único
perfil com dois veículos por linha, porque o equipamento muda de carro. Ler
`placas` nela devolvia LISTA VAZIA: a etapa 1 mostrava **0 veículos num termo
que tem 1**.

**2. A rescisão não traz o documento.** Medido nos dois fixtures (8788 e 8842):
`cnpj` e `cpf` vêm `None`; só o nome vem. E cruzar por nome é proibido — o
mesmo CNPJ é `Velasco Leite Pastelaria ME` no Harmonit e `PASTELARIA VELASCO
LTDA` na WESO. A resposta traz `documento_no_termo` explícito e o operador
informa, com o nome do termo à vista.

**3. 🚨 As duas taxas da substituição já vêm do termo:** `taxa_local_diferente`
**299,90** e `taxa_mesmo_local` **199,90**. A regra 12 manda fixar 299,90 em
código, e **valor de serviço fixado em código apodrece igual a id de tipo** —
foi assim que 7 das 14 OS de manutenção ficaram com `tipo = 55`, que não existe
mais. Talvez a pergunta certa não seja "qual id fixar", e sim "o valor vem do
termo e o operador escolhe mesmo local × local diferente".

**4. `no_menu` + permissão PRÓPRIA nunca tinha existido, e quebrava a tela.**
`do_usuario` exclui `no_menu`, e o `sidebar.js` usava essa MESMA lista para
decidir `temAba` — a aba se julgaria fora do perfil e entraria em loop de
redirecionamento, que é o defeito de 17/08. Enquanto toda tela fora do menu
dividia permissão com uma do menu, as duas perguntas coincidiam por acaso.
Separadas: **`abas` é o que desenhar; `permissoes` é o que se pode abrir.**

⚠️ **E um bug que o teste pegou antes de qualquer uso:** `harmonit_post` estava
sendo chamado sem ter sido importado. Import faltando DENTRO de função não
aparece no `py_compile` nem no import do módulo — só estouraria na primeira
placa cadastrada de verdade.

---

## Achados incidentais da auditoria

- **3 arquivos `.bak` do `os_router`** em `painel/routers/` (13/08). Não são
  importados, mas estão no diretório dos routers.
- **`LIMIAR_LOTE` definido duas vezes** em `equipamentos.py`, linhas 115 e 138,
  com o mesmo valor. Inofensivo hoje; se alguém mudar um, não muda nada.

Ver também: `23_Manutencao.md` · `24_Desempenho_e_Timeout.md` ·
`26_Cadastro_de_Placas.md` · `27_Registro_Telas.md`.
