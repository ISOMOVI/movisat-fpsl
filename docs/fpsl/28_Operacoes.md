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
| Menu | **dentro desde 20/08** (decisão sua). Nasceu fora porque estava pela metade |

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
| **F4** | Etapa 4 — OS, com as 14 regras | ✅ **ENTREGUE** |
| **F5** | A rotina, com os 4 casos e teto de tentativas | ✅ **ENTREGUE** |
| **F6** | Histórico de Operações (`HST_4.1`) | ✅ **ENTREGUE** |
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


---

## 🚨 O que a construção da F4 achou (2026-08-20)

**1. A alocação por placa roda só sobre os itens que vão na OPERACIONAL.** Eu
aloquei todos os itens resolvidos, e isso faria item de cobrança aparecer nas
duas OS — desfazendo a **regra 7 por outro caminho**, logo depois de ela ter
tirado o `nas_duas`. Não apareceu em teste: apareceu ao ler o ramo de
`gerar_os` do `os_router` antes de escrever o teste. É a regra M6 pagando o
aluguel — "já é assim" se mede.

**2. A regra 4 muda o CORTE, não só a listagem.** Antes, o operacional levava
tudo que não tinha `cobrar` marcado, e um item não-comodato de valor zero caía
lá. Agora o corte é por **natureza**: comodato é da operacional, o resto é do
lado financeiro — listado sempre, com `cobrar` dependendo do valor. Sem isso a
regra 4 seria só cosmética, porque o item de valor zero continuaria do lado
errado.

**3. 🚨 `teste_perfis.py` REPROVAVA DESDE 19/08 E NINGUÉM VIA.** Ele imprimia
`FALHA` e terminava com `asyncio.run(main())`, **sem `sys.exit`** — então quem
mede pelo código de saída via verde. A falha era a contagem de abas
concedíveis, que ficou em 5 quando a própria F1 criou a sexta (`operacoes`).

Duas consequências: o número "838 verificações, ZERO reprovações" de 19/08
estava medido por um placar que não conseguia ficar vermelho nesse arquivo; e
**era o único teste mudo da suíte** — os outros 27 já saíam com o código certo.
Corrigido nos dois pontos. Um teste que reprova e sai 0 é pior que um teste que
não existe, porque dá a garantia sem prestá-la.

**4. O valor da substituição vem do termo, e o serviço continua parado.** A
`financeira_substituicao` aceita o valor que a etapa 1 leu do documento
(`taxa_local_diferente` 299,90, `taxa_mesmo_local` 199,90) e só cai para o
número da regra 12 quando o termo não trouxe. O **id do serviço** continua
`None` e faz a geração PARAR com mensagem: são dois registros com nome idêntico
(`6967` e `54845`) e resolver por nome pegaria um no chute. É a decisão 0.A,
sua, ainda aberta.

### O que a F4 entregou

| Arquivo | O que é |
|---|---|
| `painel/operacoes_os.py` | a montagem, com as 6 regras que mudaram |
| `painel/operacoes_equipamentos.py` | clone de `equipamentos.py` + `chave()` e `serie_que_entra()` |
| `painel/routers/operacoes_router.py` | `/modelos`, `/os/previa` e `/os/gerar` |
| `storage.listar_modelos_produto()` | o de-para inteiro, para o seletor da regra 9 |
| `tests/teste_operacoes_f4.py` | **63 verificações**, com dublês, sem rede |

**Suíte do FPSL: 968 verificações em 28 arquivos, zero reprovações.**

⚠️ **A F4 não tem tela ainda.** As três rotas existem e estão testadas; o
`operacoes.html` continua com a etapa 4 em esqueleto. Ligar a tela é o primeiro
item da F5.


---

## 🚨 A AUDITORIA DA F4 (2026-08-20) — nove decisões vivas que não vieram junto

A primeira passada da F4 implementou as seis regras que MUDARAM e passou nos 63
testes. A auditoria comparou a etapa 4 com a geração que já existe no
`os_router` — que é **a regra que faltou em 17/08: tela nova se compara com a
tela que já existe** — e achou que o clone tinha deixado para trás decisões que
a tela velha carrega. Nenhuma delas apareceria em teste, porque o teste era meu
e media o que eu tinha pensado em testar.

| # | O que faltava | Decisão que ficava desfeita |
|---|---|---|
| 1 | **Tipo e Problema por NOME** contra a lista viva | 14/08 — das 14 OS de manutenção abertas na mão, 7 usam `tipo = 55`, que não existe mais. Eu usava o id do perfil direto |
| 2 | **Conferência do recipiente** | 14/08 — "sem *entrará* plausível, não inventa". Recipiente ausente, ambíguo, de outra rodada ou sem série tem de ser descartado COM AVISO |
| 3 | **Leitura ao vivo só nos perfis sem termo** | 14/08 — eu lia ao vivo em todos, e em DUAS chamadas. Cada uma que não achasse pela consulta exata cai na base inteira (16,65s). Era o caminho de volta para os 43s que quase estouraram o nginx |
| 4 | **No upgrade o recipiente vem do CACHE** | o recipiente nasce junto com o termo; ler ao vivo ali é pagar rede à toa |
| 5 | **`numero_na_descricao`** | 14/08 — a manutenção grava `\| O.S: nnnnn` na própria descrição, igual às 14 abertas à mão |
| 6 | **Fase dupla na geração** | 24/07 — operacionais primeiro, colhendo os números; a financeira depois, citando-os na solução técnica. É o que torna a cobrança conferível placa a placa |
| 7 | **Uma linha de equipamento POR PLACA nas OS agregadas** | 13/08 — o vínculo traz UM item com a quantidade do termo, e todas as placas viravam o mesmo ST310U |
| 8 | **Aviso de cobrança zerada sem motivo** | vale nos dois caminhos; na rescisão a lista financeira é vazia por construção, então checá-la não serve — olha-se o valor dos itens de cobrança |
| 9 | **`problema_id` da tela só vence nos perfis SEM TERMO** | num contrato o problema é ditado pelo documento; eu deixava quem digita trocá-lo em qualquer perfil |

**E uma décima, achada ao corrigir:** aplicar o cabeçalho resolvido a TODAS as
operações sobrescreveria o Problema FINANCEIRO da OS financeira, transformando-a
noutra coisa. A financeira fica de fora, e há teste prendendo isso.

### O que isso ensina, e vale para a F5

**Passar nos meus próprios testes não é evidência de completude.** Os 63 testes
da primeira passada estavam certos — eles mediam as seis regras novas, e as seis
estavam certas. O que faltava era tudo o que a tela velha já sabia e eu não
tinha perguntado. A auditoria não achou bug no que eu escrevi: achou o que eu
**não** escrevi.

Na F5 o mesmo se aplica ao `_liberar_series` e ao varredor de OS: a rotina nova
tem de ser comparada com o que a geração velha já faz ao fim, não desenhada do
zero a partir da tabela da spec.

### Depois da auditoria

**`tests/teste_operacoes_f4.py`: 63 → 88 verificações.** As 25 novas prendem os
quatro motivos de descarte de recipiente (inclusive o caso do acento, que quase
derrubou a manutenção inteira), a resolução de cabeçalho por nome nos três
desfechos (resolve / lista muda / nome sumiu) e o aviso de cobrança sem motivo.

**Suíte do FPSL: 993 verificações em 28 arquivos, zero reprovações.**

⚠️ **`teste_auditoria_placas.py` oscilou uma vez** durante a auditoria e passou
nas quatro rodadas seguintes. Ele fala com o serviço vivo por HTTP
(`httpx` na 8004), então depende de o serviço estar no ar e responsivo — não é
hermético como os da aba nova. Não foi investigado além disso; fica registrado
porque teste que oscila treina a equipe a ignorar o placar.


---

## A F5 (2026-08-20) — a rotina, e o que ela obrigou a decidir

### 🚨 O `status` da oficina: medido, e o que ele NÃO prova

`os_historico` tem só dois valores de `status` (medido em 20/08: **1** com 87
ocorrências, **2** com 99) e o significado não está em nenhum lugar do código.
A investigação de agosto em
`backups/scripts_avulsos_2026-08/testar_hipotese_os.py` identifica os dois —
**2 é desinstalação, 1 é instalação** — e levanta uma hipótese que muda o
desenho desta rotina:

> "o registro de oficina numa OS é uma **INTENÇÃO**. Quem executa (fecha a
> instalação e vira o 'instalado' do rastreador) é a **FINALIZAÇÃO** da OS."

Não há registro de que ela tenha sido confirmada. Se valer, agir só porque a
oficina existe seria agir **antes de o trabalho acontecer** — e esta rotina
mexe em equipamento de cliente.

**Decisão:** a rotina não age sobre o registro. A oficina é o **gatilho para ir
olhar**; quem decide é o estado que ela mesma relê na WESO. Já em `Estoque`,
conclui sem escrever. Ainda `Instalado`, faz e confere relendo. O desenho vale
com a hipótese verdadeira e com ela falsa — que é o único possível enquanto
ninguém mediu.

⏸️ **Fica em aberto para você:** medir se a hipótese vale. Se valer, o gatilho
certo pode ser a OS finalizada, e não a oficina — o que tornaria a rotina mais
cedo ou mais tarde, não mais certa ou errada.

### Os três riscos da rotina, e como ficaram

| Risco da spec | Como ficou |
|---|---|
| Precisa de um vínculo OS ↔ recipiente que não existe | Tabela `operacoes_espera`, gravada **na geração**. Quem sabe é quem gerou; a rotina, 6 h depois, não |
| Vai reescrever OS já criada, e é save completo | Relê a OS inteira, troca só o marcador da série no texto e devolve o payload todo. Confere relendo |
| Precisa de teto de tentativas | `TETO_TENTATIVAS`; `desistiu` sai da fila mas **fica** na tabela com o último erro |

### 🚨 A AUDITORIA DA F5 — a terceira prova tinha ficado para trás

O `_liberar_series` da geração velha exige **três provas** antes de soltar a
série: a OS foi criada, a série está na descrição, e **o equipamento foi mesmo
anexado aos materiais**.

A F5 nasceu cobrindo as duas primeiras e não a terceira. E o caso dela é
justamente o inverso do caso velho: quando o recipiente não estava pronto na
geração, `conferir_recipientes` o descartou, não houve modelo, e **a OS nasceu
sem a linha do equipamento nos materiais**. Completar só a descrição deixaria a
OS parecendo pronta, com a série no texto e sem o equipamento — que é
exatamente o defeito achado auditando o termo 8820.

**Corrigido:** a rotina anexa o equipamento aos materiais antes de liberar, e
confere relendo `ObterMateriaisOrdemServico`. Modelo sem produto no de-para
(TK-100, ST500, NT2x, Concox) **não libera**: vira pendência visível no
Registro em vez de série solta numa OS incompleta.

### Uma distinção que o código faz e o teste prende

**"A OS ainda não foi varrida" não é "não há oficina".** As duas esperam, com
mensagens diferentes. Tratar como a mesma coisa faria a rotina desistir de
trabalho que só não tinha sido lido ainda — a OS pode ter nascido minutos antes
e o varredor ainda não ter chegado nela.

### O que a F5 entregou

| Arquivo | O que é |
|---|---|
| `painel/operacoes_espera.py` | a tabela `operacoes_espera` e a API dela |
| `painel/operacoes_rotina.py` | os quatro casos e o laço de 6 h |
| `main.py` | o laço no lifespan, **depois** do varredor que a alimenta |
| rotas | `/pendencias` e `/rotina/rodar` (a mesma função do laço) |
| `tests/teste_operacoes_f5.py` | 29 verificações — o vínculo |
| `tests/teste_operacoes_f5b.py` | 38 verificações — a rotina |

**Suíte do FPSL: 1.103 verificações em 31 arquivos, zero reprovações.**

⚠️ **A rotina está inerte hoje**, e isso é fato e não suposição: ela só age
sobre pendências criadas pela etapa 4, e a etapa 4 ainda não tem tela. Nenhuma
pendência existe. O laço acorda, encontra a fila vazia e volta a dormir.

⏸️ **`TETO_TENTATIVAS = 28`** (7 dias a cada 6 h) — escolhido para o laço não
ser infinito, **não** por saber que 7 dias é o prazo certo. Teto, limite e filtro
são decisão sua; o teste prende o número de propósito.


---

## A tela da etapa 4, o menu e a F6 (2026-08-20)

### 🚨 Dois defeitos que só apareceram ao LIGAR a tela

**1. As três rotas de apoio exigiam `gerar_os`.** Problemas, prioridades e
busca de serviço vivem no `os_router` com `requer_aba("gerar_os")` — quem tem
só `operacoes` tomaria **403 nas três**. Resolvido pelo que esta spec já
mandava: prefixo próprio. Nasceram sob `/painel/api/operacoes/`, e quando as
telas velhas saírem nenhuma rota da aba muda de endereço.

**2. O `/extrair` não devolvia os itens do CONTRATO.** O campo `itens` dele são
os **veículos** — colisão de nome dentro da própria resposta. Sem os itens do
contrato não há vínculo, sem vínculo não há material, e a OS sairia só com o
serviço do cabeçalho e o ENTREGA OS: **completa na aparência e vazia no
conteúdo**. Agora vai `itens_contrato`, com nome próprio.

Os dois só apareceriam ao usar. O teste que ficou (`teste_tela_operacoes.py`)
lê o fonte da tela e o do router e cruza os dois — a lição de 18/08 aplicada:
**contrato de JSON se testa pelo lado de quem consome**.

### A aba entrou no MENU

Decisão do usuário, 20/08. Ela nasceu `no_menu` com motivo escrito aqui —
estava pela metade — e o motivo caducou quando o fluxo passou a fechar de ponta
a ponta.

⚠️ **A permissão não mudou, e não era ela que escondia.** `pode_acessar`
devolve `True` para owner **sempre**; quem tirava do menu era a flag `no_menu`,
que o `do_usuario` filtra para todo mundo. Conferido: quem tem só `operacoes`
vê só ela; quem não tem, não vê.

Ela é a **primeira** do menu, e isso é coerente: faz numa tela só o que Cadastro
de Placas e Gerar OS fazem em duas, e o login manda para a primeira tela do
perfil.

### 🚨 A F6 NÃO se chama "Registro"

Já existe **`CFG_9.1 Registro de telas` no menu**, e `operacoes_registro.py` é o
registro de lote e passos da própria aba. "Registro" seria a terceira coisa com
o mesmo nome, e a primeira é um item que a pessoa vê.

**`HST_4.1 — Histórico de Operações`**, na família que já existe: Histórico de
OS, Histórico de Placas. ⚠️ `HST_3.1` continua **queimado** (era a Aderência,
apagada em 19/08). Há teste prendendo que nenhum título e nenhum código se
repetem — é o que teria pegado a colisão antes de ela existir.

**Mesma permissão da aba principal**, como `CAD_1.1`/`CAD_1.2` já fazem: quem
opera precisa ver o que operou.

**O que ela mostra, e a ordem importa:** as pendências da rotina vêm PRIMEIRO.
`desistiu` significa que a rotina tentou até o teto e parou — há recipiente
preso ou equipamento que não voltou ao estoque, e ninguém descobre sozinho. Sem
esta tela é linha morta numa tabela que ninguém abre. Abaixo, cada rodada e o
passo a passo dela.

⚠️ **`ignorado` não é pintado de vermelho.** Descartar de propósito é
comportamento certo; pintar de vermelho ensinaria a equipe a ignorar o vermelho.

### Dois achados menores da construção

`listar_lotes` nasceu com `ORDER BY l.id` e **a tabela de lote não tem `id`** —
a chave é o `lote`, texto. E é **uma consulta só**: o resumo sai do próprio SQL,
senão seriam 101 idas ao banco para desenhar 100 linhas.

O banner da aba principal ainda dizia "Em construção (F3)" com a aba completa.

## 🚨 21/08 — A PRIMEIRA RODADA DE USO REAL, E O QUE ELA ACHOU

O usuário abriu a aba e rodou dois termos de verdade. Nenhuma das 1.322
verificações tinha visto nada disso. **Todos os achados vieram do uso, nenhum
de teste meu** — pela quarta vez desde 14/08.

O journal do dia, com o IP real:

```
08:52:42  extrair?perfil=aditivo   200   termo 8800
08:53:10  cliente?documento=...    200
08:53:23  lote                     200
08:56:19  modelos/prioridades      200   <- etapa 4 aberta
08:58:02  os/previa                400   <- "Nenhuma placa foi informada"
09:00:26  os/previa                200   (segunda rodada, termo 8840)
```

Os dois lotes ficaram gravados em `etapa 1`, com **zero passos**.

### 1. A trava de etapas nunca existiu — só o comentário existia

O `irPara(n)` pintava a bolinha de `locked` e trocava o painel. Nada mais. Logo
acima dela, desde a F1:

> Aqui a etapa N só abre com a N-1 concluída.
> **Na F1 nada conclui nada, então a trava está solta de propósito.**

A segunda frase sobreviveu a cinco fases. Foi por ela que o operador foi da
etapa 1 direto para a 4 e a prévia devolveu 400 — **o erro certo, na hora
errada**, depois de todo o trabalho.

🚨 **Por que nenhum teste pegou:** os testes da aba liam o FONTE da tela, e o
fonte estava certo — o comentário descrevia o comportamento. Faltava a linha
que o executa. **Fonte que descreve o comportamento não é o comportamento.**
Agora há `tests/exercitar_operacoes.js`, que roda o script da página num DOM de
mentira e CLICA em Avançar.

### 2. O registro nunca acompanhou o fluxo

`guardar_cliente` foi escrita na F3 e **nunca chamada** — `grep` no projeto
devolvia só a definição. Toda rodada ficava com cliente nulo e `etapa = 1` para
sempre, e o `HST_4.1` lê essas colunas: ele mostrava toda rodada morrendo no
começo. Agora `abrir_lote` recebe os ids do cliente, `marcar_etapa` anda com
`MAX` e `encerrar` fecha quando as OS saem.

### 3. Os três perfis SEM TERMO morriam na etapa 3

A etapa 1 prometia, na própria tela, que *"a entrada digitada entra na F3"*. A
F3 montava `linhasPlacas` **só** a partir de `extraido.itens`: sem PDF a lista
nascia vazia, a tabela renderizava sem corpo e **não havia botão de adicionar
linha em lugar nenhum**. Manutenção no local, manutenção com troca e
ressarcimento sem termo — 3 dos 11 perfis — não completavam.

Decisão do usuário: lista suspensa da base local, **só nesses perfis**, "só de
placas que já existem na base a mais de 24 horas", e "mesmo adicionando mais de
uma". A rota é `/operacoes/placas/do-cliente`, lendo `harmonit_veiculos`.

🚨 **Da base local e não ao vivo porque nenhum dos dois filtra por cliente:**
`ObterVeiculos` ignora `clienteId` e o `Consultar` da WESO ignora `cliente_id`,
devolvendo a base inteira com cara de resposta válida.

### 4. A etapa 2 não deixava trocar o cliente, e ficava em branco

Era só a tabela do cruzamento, que só aparece depois de a resposta voltar — nos
perfis sem termo, nunca. Clonado o bloco do `gerar_os.html`: campo
somente-leitura, botão, modal com 3 caracteres e 400 ms. **A troca volta pelo
mesmo caminho do termo** — grava o documento e refaz o cruzamento, para o
cruzamento continuar sendo por documento.

### 5. A busca de serviço era um `<select>` em que ninguém escolhia

Um `<input>` repovoava um `<select>` a cada tecla: o valor era o que calhasse
de ficar em primeiro, o id nunca aparecia, e a lista mudava sob o dedo. **O id
não é enfeite: dois serviços do Harmonit têm o nome idêntico** (6967 e 54845).
Clonado o modal do Gerar OS.

### 6. "Está tudo torto" — e é medível

| tela | `style="` inline |
|---|---|
| `cadastro_placas.html` | 13 |
| `vinculos.html` | 17 |
| `gerar_os.html` | 26 |
| **`operacoes.html`, antes** | **57** |
| `operacoes.html`, depois | 12, **todos estado** (`display`/`visibility`) |

### 7. O botão que ele não entendeu

*"botão conferir faz o que?"* — chamava `/os/previa`, e era ele que habilitava o
Gerar, sem isso estar escrito. Virou **Ver prévia**, com a dependência à vista.
O outro "Conferir", da etapa 2, virou **Usar este documento**.

---

## Decisões do usuário em 21/08

| # | Decisão | O que muda |
|---|---|---|
| 1 | **Rescisão passa a ter OS operacional E financeira** | implementa a regra 3 e **reverte a decisão de 29/07**. O que mudou de contexto: a aba nova tem etapa de conferência de placa, que a velha não tinha |
| 2 | **Serviço de substituição: id `6967` fixo**, 299,90, `cobrar` marcado, sem pergunta na tela | recusada a alternativa de o operador marcar mesmo local × local diferente com o valor vindo do termo |
| 3 | **Timeout do cliente WESO: 30 s → 60 s** | com barra de progresso passando de 15 s |
| 4 | **Cliente pode ser trocado no painel** | o termo manda, mas não é infalível |
| 5 | **F7 só depois de 100% do painel novo rodando** | e as rodadas de teste terminaram |

🚨 **A GUARDA QUE ACOMPANHA A DECISÃO 2, e não a contradiz.** Id fixo em código
apodrece **em silêncio** — foi assim que 7 das 14 OS de manutenção ficaram com
`tipo = 55`, que não existe mais. `conferir_servico_de_substituicao()` faz o
apodrecimento virar recado em vez de OS errada. Decidir é dele; fazer o
apodrecimento aparecer é trabalho meu.

---

## ✅ O nginx, e a decisão que tinha ficado no papel

🚨 **A DECISÃO DE 14/08 NUNCA TINHA CHEGADO AO SERVIDOR.** Ela registra que o
`proxy_read_timeout` do `location /` foi de 35 s para 180 s. O arquivo no ar era
de **12/08 — anterior à decisão — e estava em 35 s nos DOIS server blocks**.
Enquanto isso o teto de 60 s do cliente WESO não existia na prática: o nginx
cortava antes e devolvia uma **página HTML de 504**, que a tela lê como JSON.

⚠️ **DECISÃO REGISTRADA NÃO É DECISÃO APLICADA.** O doc dizia 180 s por sete
dias e o servidor dizia 35 s. Ninguém tinha lido o arquivo no ar.

**Aplicado em 21/08**, com autorização dele: `location /` a **90 s** nos dois
server blocks. O que **não** mudou, de propósito:

| Rota | Teto | Por quê |
|---|---|---|
| `location /` | **90 s** | acomoda o cliente WESO de 60 s com folga |
| `/painel/api/login` | 35 s | login que demora meio minuto é login quebrado |
| `/weso/onboarding` | 120 s | faz 5-6 chamadas WESO em sequência |

🚨 **A ORDEM É O DESENHO: 60 s no cliente < 90 s no nginx.** O nosso timeout
dispara PRIMEIRO, e o operador recebe erro nosso em JSON, com explicação, em vez
de uma página do nginx que a tela não sabe ler. Invertido, o defeito de 14/08
voltaria.

Conferido relendo o arquivo no ar, e os quatro sites vizinhos continuam
respondendo (`nginx -t` antes do `reload`, backup em `/root/`).

---

### Estado

**F1 a F6 no ar. Falta a F7.**

🚨 **A F7 tem condição escrita e ela não é minha:** *"depende de uso real
aprovado por você"*. Apagar Cadastro de Placas e Gerar OS antes de alguém rodar
um termo de verdade pela aba nova é o erro de 19/08 outra vez, quando o
interruptor foi removido antes da garantia do que dependia dele.

**Suíte do FPSL: 1.227 verificações em 34 arquivos, zero reprovações.**
