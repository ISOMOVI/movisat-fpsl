# 31 — Gestão de Contratos (`CTR_1.1`): o termo assinado vira a base do cliente

> **Status em 13/10/2026: `C0` a `C6` NO AR — a frente inteira.** A rotina de auditoria nasceu
> **DESLIGADA**, com interruptor na própria tela. Suíte do FPSL: **60 arquivos, 2.073 verificações**;
> as 7 da CTR somam **239, 0 falhas**.
>
> **`C0` a `C5` no ar.** A carga histórica entrou: **731 clientes, 4.599 termos,
> 12.114 eventos**. ⚠️ Os números da ficha **não** batem com a planilha da auditoria, e a razão está
> na seção da C5 — leia antes de comparar.
>
> **`C0` a `C4` no ar às 19:03.** `/painel/contratos` responde 200, as 5 rotas da
> API estão montadas, as 4 tabelas criadas, serviço reiniciado, journal limpo.
> **A suíte inteira do FPSL: 58 arquivos, 2.006 verificações.** As 5 suítes novas somam 172, 0 falhas.
> ⚠️ **Uma suíte reprova, e é anterior a esta frente:** `teste_extrair_termo` bate em
> `/painel/api/placas/extrair`, removido pelo **expurgo F7 em 02/10** (commit `cf16837`) — está
> vermelha desde então. Ver "Pendências".
> Falta: `C5` (carga histórica), `C6` (rotina de auditoria), e **abrir a tela no navegador** — `M9`:
> placar verde não vê layout.
> Plano: `enquanto-isso-localmente-na-delightful-widget.md`, aprovado por ele em 13/10.
> Código e docs em `C:\code\fpsl_weso\` — o espelho local, que estava de **14/08** e foi
> atualizado só nos arquivos que esta frente **lê**.

---

## Por que a aba existe

A auditoria de 13/10/2026 (`C:\code\termos_harmonit`, regras no README de lá) cruzou, placa por placa, as três
fontes que hoje contam a mesma história de formas diferentes:

| Fonte | O que ela é hoje | O que ela não é |
|---|---|---|
| **Harmonit** | todos os termos, assinados ou não, e o cadastro do cliente | não distingue assinado de não assinado de forma confiável, e o PDF **é editado depois de assinado** |
| **Clicksign** | o que vale juridicamente | não tem o número do contrato como dado, só no nome do arquivo; não cobre termos anteriores a 2019 |
| **WESO** | o que está em uso, e é a base da cobrança | **não liga veículo a cliente** em nenhuma das duas direções (medido na API em 29/07 e reconfirmado em 13/10) |

**Medido nas 1.930 placas da WESO** (exportação da tela de 13/10, que é a única fonte com o cliente):

| Situação | Placas |
|---|---|
| tem termo assinado no próprio cliente | 1.351 |
| citada em termo assinado (upgrade/aditivo), mas a entrada não foi assinada | 68 |
| rescisão assinada, dentro do aviso prévio de 90 dias | 94 |
| **rescisão assinada há mais de 90 dias, ainda em uso** | **48** |
| **só tem termo sem assinatura** | **151** |
| **nenhum termo do cliente cita a placa** | **124** |
| o cliente da WESO não tem nenhum termo | 23 |
| Moto Help (não usa Clicksign, tratada por último) | 71 |

E no caminho inverso: **1.005 placas** estão ativas por termo assinado e **não** estão na WESO, e **478** estão
ativas só em termo sem assinatura, fora da WESO.

Mais três números que explicam por que isto não se resolve com planilha:
- **1.184 termos sem assinatura mudam placa** na linha do tempo do Harmonit;
- **301 termos** o Harmonit marca "não assinado" e a Clicksign mostra assinados; **26** o contrário;
- **59 termos** estão assinados na Clicksign e **não têm PDF no Harmonit**.

**A aba existe para que a situação de cada placa deixe de ser reconstruída à mão.** O termo assinado entra uma vez,
vira evento, e a situação passa a ser consulta — nunca campo digitado.

---

## Identidade

```
Código      CTR_1.1          (imutável; prefixo CTR estava livre em 13/10)
Permissão   contratos        (nova, SÓ OWNER — decisão dele 13/10: "somente eu, como padrão owner inicial para FPSL")
Rota        /painel/contratos
Tela        frontend/contratos.html
```

🚨 **A aba nasce só para o owner.** `contratos` entra em `PERMISSOES_SO_OWNER`, junto de `config` e `usuarios`.
Consequência medida no registro: `pode_acessar` devolve `False` para toda conta que não seja owner, e
`PERMISSOES_CONCEDIVEIS` (que é `VALIDAS - SO_OWNER`) **não cresce** — então a trava de "abas concedíveis"
continua em 5. Abrir para outros perfis é decisão dele, depois, e é uma linha.

🚨 **A aba Operações é intocável.** A CTR **lê** `pdf_extractor.extrair_campos` (como `operacoes_extracao.py` já faz)
e **lê** `painel_vinculos_itens`. Nada em `operacoes_*` nem no `pdf_extractor` é alterado. Critério da casa:
**regra que muda clona; infraestrutura sem regra reusa.**

---

## O núcleo: evento imutável, situação derivada

Um termo assinado não "atualiza" a placa. Ele **registra um evento**, e a situação da placa é o resultado de ler
os eventos dela em ordem. É o que permite responder "por que esta placa está ativa?" com um documento na mão.

```
TERMO (assinado, com PDF e hash)
  └── EVENTO por placa      entra · sai · rescinde · substitui · upgrade · troca
        └── ITEM DE CONTRATO    placa + recursos + valor mensal + vigência
              └── SITUAÇÃO       derivada, recalculada a cada evento
```

### Os eventos

| Evento | Vem de | Efeito na placa |
|---|---|---|
| **entra** | contrato, aditivo, empréstimo/teste | passa a ativa |
| **sai** | coluna "veículos que sairão" da substituição | deixa de ser ativa, **sem aviso prévio** |
| **substitui** | substituição (par sai/entra) | sai A, entra B. "A DEFINIR" na coluna de entrada não ativa nada |
| **rescinde** | rescisão, distrato, ressarcimento com rescisão | deixa de ser ativa **ao fim do aviso prévio de 90 dias** |
| **upgrade** | upgrade de sistema, tecnologia, acessório, funcionalidade | **não muda placa** — reflete a mesma placa |
| **troca** | anotação no termo do Harmonit, num termo assinado | a placa nova passa a ser coberta pelo termo; a antiga sai |

### As regras (todas dele, fechadas na auditoria de 13/10)

1. **Vale o assinado.** Termo não assinado aparece, mas não muda a situação — **salvo quando falta dos dois lados**:
   se nenhum termo assinado trata daquela placa, o termo sem assinatura é usado para cobrir a lacuna, e a placa
   fica marcada **"sustentada por termo não assinado"**.
2. **A ordem é o número do termo**, não a data. A data do Harmonit não é confiável (`01-01-2000` = sem data, e há
   contrato datado de 2026 rescindido por termo anterior).
3. **Mesma placa só por equivalência Mercosul** (`ABC1234` = `ABC1C34`). A regra antiga de "1 caractere diferente"
   foi abandonada: ela juntava placas reais da mesma frota.
4. **Identificador não é só placa.** Vale placa BR, chassi/série (11–17 alfanuméricos) e, por último, o que vem
   **depois de ` - `** na coluna de veículo — a mesma regra do FPSL (ver `reference_placa_identificador`).
5. **Assinado com "a definir"** (expressão exata, na tabela de veículos) + placa preenchida depois no Harmonit = **assinado**.
6. **Troca registrada vale.** Termo X assinado + anotação de troca no mesmo termo X no Harmonit ⇒ a placa nova é
   coberta pelo X e a antiga sai. Na auditoria isso resolveu 24 placas.
7. **Aviso prévio de 90 dias** após rescisão assinada: a placa pode seguir em uso até o fim do prazo.
8. **Cobrança é a WESO em uso.** Termo assinado pode estar à frente da instalação ("aguardando"), e isso não é erro
   dentro de um prazo.
9. **O Instituto migrou todo para a Movisat, e o vínculo é pela placa** — o número do termo muda na migração.
   Cadastros unificados ficam numa lista explícita (hoje: Moto Help antigos, VGS filial, Centro Logístico Helplog).

---

## Entrada do termo

**C2/C3 — upload manual**, no mesmo desenho da Operações:

1. Sobe o PDF **assinado**.
2. **Leitura imediata, sem cruzar cliente na mesma requisição.** Isto é cópia deliberada da Operações: lá,
   `/placas/extrair` lia o PDF e batia nos dois sistemas de uma vez, e quando o Harmonit ou a WESO oscilava a
   leitura do PDF — que é local e instantânea — demorava junto, sem a tela dizer nada.
3. **Tela de conferência antes de gravar**, mostrando: cliente identificado (CNPJ do PDF × cadastro do Harmonit),
   os eventos que serão aplicados placa por placa, e os alertas:
   - placa já ativa em **outro cliente**;
   - substituição que tira placa que **não está** no contrato;
   - termo cujo número **já existe** para esse cliente;
   - identificador que não é placa (chassi, código de frota) — entra, mas rotulado.
4. **Confirmar grava** o termo (arquivo + **hash**, para o mesmo PDF não entrar duas vezes), os eventos e os itens.

**R5/opcional — puxar da Clicksign.** A API já foi testada (só leitura, 13/10) e entrega o PDF assinado e a data.
Vira tarefa própria, depois que o upload manual estiver provado.

---

## A ficha do cliente

| Bloco | Conteúdo |
|---|---|
| **Cabeçalho** | dados do Harmonit, situação na WESO (Adimplente/Inadimplente, pelo `cliente_por_documento`) |
| **Placas** | uma linha por placa: situação no contrato · termo que sustenta · recursos · valor · uso na WESO · alerta quando divergem |
| **Linha do tempo** | termos em ordem de número: tipo, assinatura, PDF. Os sem assinatura aparecem à parte |
| **Pendências** | o que a auditoria aponta para esse cliente |

**Situações possíveis da placa:** ativa · ativa sustentada por termo não assinado · aguardando instalação ·
em aviso prévio · substituída · rescindida · a revisar.

---

## A auditoria contínua (C6, nasce desligada)

A planilha de hoje vira rotina. Por cliente e por placa:

| Achado | O que significa |
|---|---|
| **em uso sem contrato** | placa na WESO sem nenhum termo que a ative |
| **falta assinar** | em uso, sustentada só por termo sem assinatura |
| **assinado e não instalado há mais de X dias** | contrato sem serviço, ou cliente que saiu sem rescisão |
| **rescindido e ainda em uso após o aviso prévio** | os 48 casos medidos |
| **substituição pela metade** | entrou e não saiu, ou saiu e não entrou (caso Zago 8838) |
| **placa no cliente errado** | o termo assinado é de outro CNPJ |

🚨 **Interruptor na própria tela da rotina** (padrão do FPSL, oposto do MoviZap), **nascendo desligada**, com
`GET`/`PUT` separados: ler exige a aba, mudar exige owner — igual à `FIN_1.1`. A `FIN_1.1` provou por que isso
importa: ficou desligada de 02/10 a 08/10 e **nada na tela dizia**.

---

## Modelo de dados

Tabelas novas, prefixo `contrato_`, criadas em `storage.init_db()` no padrão existente
(`CREATE TABLE IF NOT EXISTS` + `ALTER` idempotente por `PRAGMA table_info`). **Nenhuma tabela existente é alterada.**

```
contrato_termo    id · cnpj · numero · empresa (Movisat/Instituto/cadastro antigo) · tipo · assinado_em ·
                  origem (upload/carga/clicksign) · arquivo · hash · enviado_por · enviado_em
contrato_evento   termo_id · placa_chave · placa_texto · acao · recursos · obs   (imutável)
contrato_item     cnpj · placa_chave · recursos · valor_mensal · inicio · fim · fidelidade
contrato_placa    cnpj · placa_chave · situacao · termo_vigente · desde · aviso_ate   (derivada)
```

Cliente e uso vêm por **leitura** de `harmonit_cache` e `weso_cache`. A CTR não copia cadastro: **evento referencia,
nunca copia** — foi copiar que quebrou o `HBG 8442`.

---

## Fora de escopo (de propósito)

1. **Não escreve no Harmonit, na WESO nem na Clicksign.** A CTR compara e aponta. Toda escrita nesses sistemas
   continua pela Operações, que é quem já tem a regra.
2. **Não emite cobrança.** Mensalidade, avulso e boleto são a `CAR_1.1` (doc 32), que consome `contrato_item`.
3. **Não gera termo.** Quem gera é a Operações.
4. **Não decide valor.** O valor vem do termo; mudar valor é reajuste, e reajuste é da CAR.

---

## Fases

| Fase | Entrega | Como se prova |
|---|---|---|
| **C0** | esta spec | ele aprova |
| **C1** | tabelas + motor de eventos, **sem tela** | suíte com fixtures reais: Maxi Confort 8872 (troca registrada), Zago 8838 (substituição pela metade), JLM (rescisão cancelada), Eco System 3085 ("a definir"), Horse (saiu sem rescisão) |
| **C2** | upload + leitura + conferência, **sem gravar** | `py_compile`, import de verdade, suítes; tela exercitada em DOM de mentira |
| **C3** | gravação + ficha do cliente | **reler o estado**, nunca o HTTP |
| **C4** | registro da tela `CTR_1.1` | as **três contagens** atualizadas na mesma tarefa (ver abaixo); suíte da Operações sem nenhuma mudança |
| **C5** | carga histórica dos 731 clientes | amostra conferida à mão contra os CSVs da auditoria |
| **C6** | rotina de auditoria, desligada | interruptor na tela; religar só com o OK dele |

### 🚨 As três contagens que travam tela nova

Elas existem para que tela nova seja **deliberada**, e os próprios testes dizem isso
(`teste_barra_status`: *"ESTE NUMERO CRESCE COM CADA TELA NOVA, e é de propósito"*):

| Teste | Trava hoje | Com a `CTR_1.1` |
|---|---|---|
| `teste_barra_status` | "achou as 11 paginas do painel" | **12** |
| `teste_perfis` | "owner enxerga as 9 telas do menu" | **10** |
| `teste_perfis` | "catalogo tem 5 abas concediveis" | **5, não muda** — a permissão é de owner |

---

## Decisões dele — FECHADAS em 13/10, não reabrir

| # | Decisão | O que vale |
|---|---|---|
| 1 | **Carga histórica (C5)** | **Entra.** A CTR nasce com os 731 clientes da auditoria; o que não fechou vem marcado "a revisar" |
| 2 | **Termo do Instituto** | **Entra**, como origem — 639 PDFs, 73 clientes, 369 placas migradas explicadas |
| 3 | **Valor mensal** | **Fica aqui**, no `contrato_item`. É o termo que diz o valor; a CAR calcula, não decide |
| 4 | **Quem acessa** | **Só ele (owner)**, como padrão de aba nova no FPSL. Abrir para outros perfis é decisão posterior |

## Lacunas conhecidas (medidas, não suposições)

1. **A Clicksign não cobre tudo.** ~500 termos de número abaixo de 1.000 são de 2017–2019, anteriores ao uso dela.
   Para eles não existe assinatura verificável, e isso não quer dizer que não foram assinados.
2. **O grupo Moto Help / Centro Logístico não tem nada na Clicksign** (71 placas na WESO). Decisão dele:
   tratar por último.
3. **61 veículos da WESO não tinham cliente** antes da exportação da tela; com ela, todos passaram a ter.
   A API não entrega esse vínculo — se a exportação deixar de existir, a CTR perde a atribuição.
4. **333 contratos do Harmonit não têm PDF** (vieram vazios, de 1.229 bytes, ou com erro). A Clicksign recupera 59.
5. **26 "(RD)"** são um segundo cadastro da mesma placa na WESO, com outro rastreador. Decisão dele: são placas
   com termo próprio, em geral no mesmo termo da placa original.

---

# O que a CONSTRUÇÃO achou, e a spec não previa (13/10/2026)

Esta parte vale mais que o resto do documento: são as quatro coisas que só
apareceram ao escrever o código, e três delas **contrariam** o que a spec dizia.

## 1. 🚨 O extrator já resolve o "a definir" — e melhor que a auditoria

A spec dizia que a regra do `a_definir` se provava lendo a expressão **"a definir"**
na tabela de veículos. Está errado: o `pdf_extractor` **já faz isso**, e de forma
estruturada. O `_aplicar_placeholder_termo` troca "A DEFINIR" por
`A_DEFINIR_<termo>`, marca `placa_convencional: False` e sugere o apelido
`TERMO:<termo>`.

**E isso fecha um mistério da auditoria:** os veículos chamados **`TERMO 8396`**,
`TERMO 7096` e outros que apareceram na WESO são exatamente essas vagas — foi o
próprio FPSL que os criou, esperando placa. A auditoria os tratou como
identificador estranho e quase os classificou como "sem termo".

A auditoria procurava a expressão no TEXTO do PDF e por isso casava
"a definição" das cláusulas: deu **22 placas por assinadas sem estarem**,
inclusive a `FAC 5H30` da Maxi Confort, que é troca e não "a definir".
**Dado estruturado não erra onde o texto erra.** A `eh_vaga()` lê a marca do
extrator, e a vaga **não vira placa no contrato**.

## 2. 🚨 A troca diz quem ENTRA, nunca quem SAI — e isso não se adivinha

A regra dele ("termo assinado + troca registrada no Harmonit vale") estava
escrita como se o motor resolvesse sozinho. Não resolve, e o teste do router
provou: na Maxi Confort 8872 o resultado dava **11 placas** onde a auditoria
conferiu **10**.

A causa: a anotação é *"FAC 5H30 - Cliente Fernanda Rodrigues pediu alteração
da placa"* — nomeia **só a placa que entra**. No PDF do Harmonit as duas ficam
na tabela, **no mesmo item**, e o extrator não devolve a posição. Inferir por
ausência também não serve: a `DVS 2992` está presente nas duas versões.

⚠️ **E eu escrevi um teste que validava o comportamento errado como certo.** No
teste do motor eu havia alimentado o `SAI` à mão, então a cadeia inteira passou
sem a lacuna aparecer. Ela só apareceu quando a leitura real alimentou o motor.

**Remédio, pela regra 13 (não se inventa identificador):** a conferência mostra
a anotação, lista as candidatas e **pede a confirmação**; a saída entra como
evento com a **autoria de quem confirmou**. Sem a confirmação, o termo **grava**
e fica marcado `a_revisar` com o motivo escrito — travar faria o operador perder
a leitura por uma decisão que talvez dependa do cliente, e gravar calado
deixaria uma placa a mais sem ninguém saber.

## 3. ⚠️ A anotação de troca só existe na versão do Harmonit — e a regra depende disso

Conferido nos dois PDFs da Maxi Confort: `troca_registrada` acha a anotação no
PDF do Harmonit e **não acha** no documento assinado. É isso que sustenta a
regra dele — a anotação é **posterior** à assinatura. Se ela aparecesse no
assinado, "assinado + troca registrada" não provaria nada.

Virou verificação travada (`teste_contratos_leitura`, bloco 3), junto com duas
que separam regras parecidas: **substituição regular não é troca** (o próprio
termo já tem as duas colunas) e **"a definir" não é troca**.

Por isso a rota `/extrair` aceita **as duas versões** do PDF e devolve **400**
quando os arquivos são de termos diferentes: a regra vale no mesmo termo, e
cruzar números diferentes transformaria documento de outro contrato em prova.

## 4. ⚠️ O que os testes pegaram antes de chegar à tela

| O que estava errado | Como apareceu |
|---|---|
| `ativas()` devolvia a **chave normalizada**: `BUW8732` saía como `BUW8H32`, placa que não existe | suíte do motor. Se tivesse chegado à tela, seria placa inventada — a família do `RFD 2447` |
| A observação "entrou pela troca" era posta em **todas** as placas do termo, inclusive nas assinadas | exercício da gravação: a ficha mentia sobre a origem da placa |
| `prepararGravacao` ficou **definida e nunca chamada**: o passo 4 não aparecia depois de conferir | contagem de chamadas no HTML. Nenhum teste de Python vê isso, e `py_compile` não lê JS |
| O texto "Nada é gravado nesta etapa" **ficou falso** quando a C3 trouxe a gravação | o próprio `M12`. Entrega seguinte não pode deixar texto velho vivo |
| `PASTA_PDF` era constante de módulo, congelada no import: o teste gravaria na pasta de dados **de verdade** | ao escrever o teste do router. Virou `pasta_pdf()`, resolvida na hora |

E uma que o teste pegou **melhor do que eu havia pensado**: o `hash` do PDF é
UNIQUE no banco todo, não por cliente. Então **o mesmo documento não entra em
dois clientes** — proteção direta contra os 33 documentos que a auditoria achou
com CNPJ divergente do cliente que o Harmonit aponta.

---

# O que foi construído

## Arquivos (todos NOVOS — nenhum existente foi alterado)

| Arquivo | O que é |
|---|---|
| `painel/contratos_eventos.py` | **Motor.** Lógica pura, sem I/O: entra termo, sai a situação de cada placa |
| `painel/contratos_tabelas.py` | As 4 tabelas, em módulo próprio para o gancho no `storage.py` ser **uma linha** |
| `painel/contratos_leitura.py` | Converte o que o `pdf_extractor` devolve em eventos por placa |
| `painel/contratos_registro.py` | Gravação, recálculo e ficha. Núcleo síncrono, superfície assíncrona |
| `painel/routers/contratos_router.py` | `/perfis` `/extrair` `/conferir` `/gravar` `/cliente/{cnpj}` |
| `frontend/contratos.html` | A tela: 4 passos + ficha do cliente |

## Suítes

| Suíte | Verificações | O que trava |
|---|---|---|
| `teste_contratos_eventos` | 33 | as 9 regras dele, com 5 clientes reais |
| `teste_contratos_leitura` | 32 | o que cada perfil tira de 7 PDFs reais |
| `teste_contratos_registro` | 27 | gravação, ficha, idempotência, aviso prévio pelo calendário |
| `teste_contratos_router` | 50 | as 5 rotas, exercitadas de verdade |
| `teste_contratos_tela` | 30 | o contrato da tela, lendo **o texto** dela (`M13`) |
| **total** | **172** | **0 falhas** |

🚨 **Toda suíte termina em `sys.exit(1 if falhas else 0)`.** O `teste_perfis`
imprimia FALHA e saía 0, e reprovou em silêncio desde 19/08 — teste que reprova
e sai 0 é pior que teste que não existe.

## Decisões de desenho, com a razão

1. **Motor sem I/O.** As regras se provam contra termos reais em qualquer
   máquina, sem banco, sem Harmonit, sem WESO.
2. **Duas passadas** no motor, porque "vale o assinado" **tem exceção**: a
   segunda cobre a placa que nenhum assinado menciona, e ela sai marcada
   `base="nao assinado"` — nunca em silêncio. Uma passada só não expressa isso:
   com o não assinado junto, a rescisão cancelada da JLM apagaria 5 placas que
   o contrato assinado sustenta; sem ele, 229 placas medidas em uso ficariam
   sem base nenhuma.
3. **Núcleo síncrono / superfície assíncrona**, no padrão do `storage.py`.
4. **Mapa de perfis próprio**, com as **mesmas chaves** da Operações: o que
   muda é a regra (lá gera OS, aqui decide se a placa entra), o vocabulário do
   operador não.
5. **Ordem pelo número do termo, nunca pela data.** A data vem `01-01-2000`
   quando não existe, e o contrato 5029 da JLM está datado de 2026 tendo sido
   rescindido pelo 6026.
6. **`contrato_evento` é imutável**; corrigir é lançar outro evento.
   `contrato_placa` é **cache**: em caso de divergência o evento ganha. A ficha
   **recalcula na hora**, porque o aviso prévio vence pelo calendário, sem
   nenhum evento novo para disparar a conta (travado no teste: a mesma base dá
   `EM_AVISO_PREVIO` em 13/10 e `RESCINDIDA` em 15/10).
7. **CNPJ vem do formulário, não do PDF.** O documento sugere; quem confirma é
   o operador. A rescisão não traz CNPJ nenhum (medido nos termos 8788 e 8842).

## Pendências desta frente

| # | Pendência |
|---|---|
| 1 | **`C4`** — registrar `CTR_1.1` em `telas.py`, permissão `contratos` em `PERMISSOES_SO_OWNER`, rota da página no `main.py`, e **as duas contagens**: `teste_barra_status` 11 → **12**, `teste_perfis` "9 telas do menu" → **10**. "Abas concedíveis" **não muda** (fica 5), porque permissão de owner não entra em `PERMISSOES_CONCEDIVEIS` |
| 2 | **Gancho de uma linha** no `storage.init_db`: `contratos_tabelas.criar(conn)`. Tem de ser feito sobre o `storage.py` **vivo** (1.816 linhas na VPS contra 837 no espelho local de 14/08) |
| 3 | **`C5`** — carga histórica dos 731 clientes, com "a revisar" no que não fechou |
| 4 | **`C6`** — rotina de auditoria CTR × WESO × Harmonit, **nascendo desligada**, com interruptor na própria tela |
| 5 | **Abrir a tela no navegador** (`M9`): nenhum teste meu vê altura, flex, quem rola nem elemento cobrindo outro |
| 6 | Levar os 2 fixtures novos (`assinado_8872.pdf`, `harmonit_8872_troca.pdf`) para a VPS junto com as suítes |
| 7 | `transferencia_termo_novo` ficou **fora**, com o motivo na tela: tem leitor próprio na Operações e junta rescisão com entrada no mesmo papel |
| 8 | **Nada disto foi publicado.** Subir e reiniciar exige a palavra dele (`M16`) |

---

# ✅ C4 — NO AR em 13/10/2026 19:03

## O que entrou

| Arquivo | Mudança |
|---|---|
| `painel/telas.py` | entrada `CTR_1.1` (antes do bloco CFG) + `contratos` em `PERMISSOES_SO_OWNER` |
| `storage.py` | **uma linha** no `init_db`: `contratos_tabelas.criar(conn)` + `migrar(conn)` |
| `main.py` | import do router, `include_router`, e a rota `GET /painel/contratos` |
| `tests/teste_perfis.py` | "9 telas do menu" → **11**, e verificação nova: `contratos` **não** é concedível |
| `tests/teste_barra_status.py` | "11 páginas" → **13** |

Backups na VPS: `*.bak_pre_ctr_2026-10-13` nos 5. Conferido por `diff` que **nenhuma linha
foi perdida** — as 4 linhas substituídas são exatamente as 4 que eu queria mudar.

## Conferido pelo ESTADO, não pelo HTTP de uma chamada só

```
GET /painel/contratos                        -> 200, <title>Gestão de Contratos — FPSL</title>
GET /painel/api/contratos/perfis (sem token) -> 401   (a aba é só do owner)
OpenAPI                                      -> as 5 rotas + a página
init_db                                      -> contrato_termo · contrato_evento · contrato_item · contrato_placa
registro de telas                            -> 13 ativas, 11 no menu, concedíveis ainda 5
pode_acessar(owner)                          -> True;  não-owner COM TODAS as abas -> False
journal desde o restart                       -> 285 linhas, nenhum traceback
```

## 🚨 Duas armadilhas conhecidas dispararam, e as duas são documentadas aqui

### 1. As travas de contagem estavam vermelhas desde 06/10, e ninguém olhou

A **baseline, antes de eu tocar em nada**, já reprovava:

| Suíte | Dizia | Real |
|---|---|---|
| `teste_perfis` | "owner enxerga as **9** telas do menu" | 10 |
| `teste_barra_status` | "achou as **11** paginas" | 12 |

A `FIN_2.1` (Fechamento dos Técnicos, 06/10) nasceu no menu e trouxe
`fechamento_tecnicos.html` **sem atualizar os dois números**. As duas suítes saem com
**`exit=1`** — então a trava funcionou e o placar denunciou por 7 dias. **Quem falhou foi a
leitura do placar, não a trava.** É a mesma família do `teste_perfis` que saía 0 em 19/08, com
a diferença de que agora o exit code está certo e ainda assim passou batido.

### 2. Teste que bate por HTTP não vê o disco

Depois de subir os arquivos e **antes** de reiniciar, três suítes reprovaram:
`teste_registro_telas` (3 falhas), `teste_perfis` e `teste_barra_status`. Eu quase julguei a
mudança por elas. Elas consultam o **servidor**, que ainda tinha o `telas.py` velho na memória.
Depois do `systemctl --user restart fpsl-weso`: **43/43, 27/27 e 89/89**. A ordem certa é
reiniciar e só então julgar.

## ⚠️ A leitura errada que eu quase reportei

Comparei `grep -c 'api/placas\|placas_router' main.py` (1 ocorrência) com
`git show HEAD:main.py | grep -c placas` (5) e por um instante achei que o deploy tinha
derrubado linhas. **Eram dois padrões de busca diferentes.** O `diff` contra o backup mostrou
só as minhas 3 adições. A pergunta que eu fiz tinha resposta fácil; a que importava era outra —
a mesma forma do `M15`.

## Pendências

| # | Pendência |
|---|---|
| 1 | 🔴 **`teste_extrair_termo` reprova desde 02/10, e não é desta frente.** Ele chama `/painel/api/placas/extrair`, que o **expurgo F7** removeu junto com o `placas_router` (commit `cf16837`, "Remove a tela de placas, o placas_router e a rota /painel/placas"). O `grep` pelo que ia sair não alcançou este teste. **Decisão dele:** apagar a suíte, ou reescrevê-la contra `/painel/api/operacoes/extrair`. Enquanto existir, o placar do FPSL nunca fecha verde |
| 2 | **Abrir `/painel/contratos` no navegador** (`M9`): nenhum teste vê altura, flex, quem rola ou elemento cobrindo outro |
| 3 | **`C5`** carga histórica dos 731 clientes · **`C6`** rotina de auditoria CTR × WESO × Harmonit, nascendo desligada |
| 4 | **Uso real.** A aba está no ar e **nunca recebeu um termo de verdade pela tela** — o que foi provado é a cadeia, com PDFs reais, em teste |

---

# ✅ C5 — carga histórica NO AR em 13/10/2026

**731 clientes, 4.599 termos, 12.114 eventos, 6.812 placas, 6.462 itens de contrato.**
Rodou em **0,6 s**. Decisão dele em 13/10: *"carga histórica entra"*.

## Como foi feita, e por que não releu PDF

A auditoria já leu os 4.266 documentos e aplicou as regras. Reler na VPS levaria horas para
chegar ao mesmo lugar. Então:

```
local   exportar_para_ctr.py   CSVs da auditoria  ->  carga_ctr.jsonl (731 linhas, 1,6 MB)
VPS     contratos_carga.py     JSONL              ->  contrato_termo / _evento / _item / _placa
```

O arquivo fica em `data/carga/carga_ctr_2026-10-13.jsonl`. Tudo entra com **`origem="carga"`**,
sem PDF e sem hash — nunca se confunde com o que subiu pela tela.

🚨 **SEM HASH, A CHAVE É `(cnpj, numero, empresa)`.** O `UNIQUE(hash)` não protege a carga. Sem
essa checagem, rodar duas vezes **dobraria 12.114 eventos** — e evento dobrado dobra placa no
contrato. Travado no teste: a segunda passada pula os 8 termos e não muda uma placa.

⚠️ **O número do termo repete entre Instituto e Movisat**, e por isso a empresa entra na chave.
A JLM tem dois `5029`, um de cada — e são termos distintos.

## 🚨 Os números do CTR NÃO são iguais aos da planilha, e isso tem explicação

| | Placas sustentadas |
|---|---|
| **CTR (ficha)** | **2.979** = 2.770 `ATIVA` + 209 `EM_AVISO_PREVIO` |
| Planilha da auditoria ("EXPECTATIVA FINAL") | 2.811 |

**126 clientes divergem**, nas duas direções, e cada direção tem causa própria:

### 1. CTR tem MAIS: o aviso prévio conta (209 placas)
Regra dele: *rescisão assinada há até 90 dias ainda pode estar em uso*. O CTR conta essas placas
como sustentadas; a planilha deixava o aviso prévio num arquivo separado e **não** as somava.
Exemplo: XOMV (Mundivox) — CTR 81, planilha 11. As 70 de diferença são placas rescindidas pelo
termo **8802**, assinado dentro dos 90 dias. **Aqui o CTR está certo e a planilha subcontava.**

### 2. CTR tem MENOS: a carga usa a lista de placas do HARMONIT (480 termos marcados)
A planilha calculou a expectativa dos assinados lendo **o PDF assinado**; a carga usa a lista do
**Harmonit** com a *marca* de assinatura. Onde o PDF do Harmonit foi editado depois de assinado —
os **408 termos** com "placas diferentes" —, a carga carrega placas que não foram assinadas. Numa
rescisão isso faz o CTR **rescindir mais** do que o documento assinado manda.

Exemplo: L Orsa Modas — o ressarcimento 2624 lista **22 placas** no Harmonit, e o assinado tem
menos. CTR: 9 ativas; planilha: 29.

⚠️ **Esta é uma limitação da carga rápida, não uma regra.** Em vez de esconder, ela ficou
**visível**: os 480 termos (408 da auditoria × as duas empresas, porque o número repete) foram
marcados `a_revisar` com o motivo *"placas diferentes entre o PDF do Harmonit e o documento
assinado; a carga usou a lista do Harmonit"*. A ficha do cliente mostra isso em "Termos a revisar".

**Total a revisar: 795 termos** — 333 sem PDF no Harmonit, 480 com placas divergentes, ~30 com
tipo não reconhecido, 5 substituições sem par legível (alguns somam dois motivos).

**Como fechar de verdade:** reler o PDF assinado de cada um dos 408 termos e lançar um evento de
correção (o evento é imutável; corrigir é acrescentar). É tarefa própria, não cabe na carga.

## Estado depois da carga

```
suíte do FPSL      59 arquivos, 2.030 verificações
GET /painel/contratos  -> 200
contrato_placa     ATIVA 2.770 · RESCINDIDA 2.929 · SUBSTITUIDA 904 · EM_AVISO_PREVIO 209
termos sem assinatura  1.545
```

Conferido contra a auditoria num cliente de controle: a **2HM** dá as mesmas 4 máquinas
(`ASC100`, `B10217`, `B32635`, `BW212D-40`) que a planilha apurou à mão.

⚠️ **Uma suíte continua vermelha, e não é desta frente:** `teste_extrair_termo`, do expurgo F7
(02/10). Ver "Pendências".

---

# ✅ C6 — rotina de auditoria NO AR em 13/10/2026 (DESLIGADA)

`services/contratos_auditoria.py` compara o que os termos sustentam com o que está em uso na
WESO. **Aponta, nunca corrige:** não escreve no Harmonit, na WESO nem na Clicksign.

## Nasce desligada, e o interruptor mora na própria tela

Convenção do FPSL, **oposta à do MoviZap** (onde o interruptor fica em `/config` › Geral). A
`FIN_1.1` provou por que ela importa: ficou desligada de 02/10 a 08/10 e **nada na tela dizia**.

```
flag            contratos_auditoria_ativa = false   (conferido depois do restart)
ler o estado    GET  /painel/api/contratos/auditoria/interruptor   -> requer a aba
mudar           PUT  /painel/api/contratos/auditoria/interruptor   -> requer_aba("config")
rodar na hora   POST /painel/api/contratos/auditoria/rodar-agora
ver achados     GET  /painel/api/contratos/auditoria/achados
laço            a cada 6 h, relendo a flag a cada volta
```

⚠️ **Ligar não faz rodar na hora**, e a tela diz isso: o laço relê a flag na volta seguinte. Para
rodar já existe o "Rodar agora". A tranca do PUT é `requer_aba("config")`, igual à da `FIN_1.1` e
pelo mesmo motivo: barra quem não é dono **e dá o recado certo** (`get_owner_painel` responderia
"só o proprietário gerencia usuários", mentira para quem tentou ligar uma rotina).

## Lê o cache da WESO, e recusa cache velho

A base inteira ao vivo levou de **15,6 s a TIMEOUT** nas medições de 18/08, com o teto do cliente
em 30 s. A rotina lê `/home/claude/weso_cache/weso.db` (cron 04:15) **em modo somente leitura**.

🚨 **Acima de 48 h ela NÃO roda, e diz por quê.** Cache de 3 dias acusaria "em uso sem contrato"
para placa retirada ontem, e "contratada e não instalada" para placa instalada hoje. Comparação
silenciosa com dado velho é pior que nenhuma comparação.

## Os 6 tipos de achado

| Tipo | O que é |
|---|---|
| `EM_USO_SEM_CONTRATO` | em uso na WESO e nenhum termo a coloca em contrato |
| `EM_USO_FALTA_ASSINAR` | em uso, sustentada só por termo sem assinatura |
| `ENCERRADA_EM_USO` | encerrada no contrato e ainda em uso na WESO |
| `CONTRATADA_NAO_INSTALADA` | sustentada pelo contrato e ausente na WESO |
| `SUBSTITUICAO_PELA_METADE` | substituição assinada executada só de um lado |
| `PLACA_EM_DOIS_CLIENTES` | a mesma placa ativa em mais de um cliente |

🚨 **A tabela `contrato_achado` é refeita a cada rodada**, de propósito: achado é **retrato de um
instante**, não histórico. A placa que entrou na WESO hoje deixa de ser "em uso sem contrato"
amanhã, e manter o achado velho faria a tela mostrar problema resolvido como atual. Quem guarda
história é `contrato_evento`, que é imutável.

⚠️ **Código de frota não vira achado.** A WESO tem ~100 `OBD 2`, `EGP 05`, `TERMO 8396`, `MOVEL 13`
— não são placa, e acusá-los encheria a tela de ruído que ninguém resolve. Só entra o que tem
forma de placa BR ou de chassi.

🚨 **A rotina RECALCULA antes de comparar.** O aviso prévio vence pelo **calendário**, sem nenhum
evento novo para disparar a conta: comparar sobre o cache de `contrato_placa` acusaria como
"encerrada em uso" uma placa ainda dentro do prazo. Travado no teste — a mesma base dá nada em
13/10 e `ENCERRADA_EM_USO` em 15/10.

## Primeira rodada real (13/10, cache de 18 h)

```
1.931 veículos na WESO (2.146 chaves) · 2.438 achados · 0,5 s
  CONTRATADA_NAO_INSTALADA   1.362
  SUBSTITUICAO_PELA_METADE     364
  EM_USO_SEM_CONTRATO          320
  ENCERRADA_EM_USO             173
  EM_USO_FALTA_ASSINAR         135
  PLACA_EM_DOIS_CLIENTES        84
```

⚠️ **Estes números herdam a limitação da C5** (a carga usa a lista de placas do Harmonit, não a do
PDF assinado). Os 480 termos marcados `a_revisar` são justamente os que podem produzir achado
falso em `ENCERRADA_EM_USO` e `CONTRATADA_NAO_INSTALADA`. Ler a seção da C5 antes de agir sobre a
lista.

## ⚠️ O defeito que a primeira rodada mostrou

A rodada disse **2.146 veículos na WESO**, e a base tem **1.931**. Eu estava contando **chaves**:
o mesmo veículo entra duas vezes no dicionário quando tem placa **e** chassi — são duas formas de
achá-lo. Corrigido: `veiculos_weso` conta veículos, `chaves_weso` vai separado. **Número inflado
em tela é defeito, mesmo com o resto da conta certo.** Virou verificação travada.

E a trava de rotas do próprio router disparou na minha mudança: eram 5, a C6 fez **9**. Atualizada
com o histórico — mesma disciplina da trava de telas.

## Estado final de 13/10

```
suíte do FPSL      60 arquivos, 2.073 verificações
as 7 suítes da CTR 239 verificações, 0 falhas
GET /painel/contratos  -> 200
contratos_auditoria_ativa = false   (nasceu desligada e segue desligada)
```

⚠️ `teste_extrair_termo` segue vermelha, e **não é desta frente** (expurgo F7, 02/10).
