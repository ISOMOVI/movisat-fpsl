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

🚨 **A aba NASCEU só para o owner** (13/10). ⚠️ **Mudou em 23/10:** `contratos` **saiu** de `PERMISSOES_SO_OWNER` por decisão dele — *"ela precisa das abas que eu quiser"* — e hoje é **concedível**. A primeira conta a recebê-la foi a da Karla (`financeiro` + `contratos`). Só `usuarios` segue fora.
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
| 1 | **`C4`** — registrar `CTR_1.1` em `telas.py`, permissão `contratos` em `PERMISSOES_SO_OWNER`, rota da página no `main.py`, e **as duas contagens**: `teste_barra_status` 11 → **12**, `teste_perfis` "9 telas do menu" → **10**. "Abas concedíveis" **não mudou** na época (ficou 5), porque permissão de owner não entra em `PERMISSOES_CONCEDIVEIS`. ⚠️ **Em 23/10 passou para 7** (entraram `contratos` e `config`) |
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

---

# `CTR_1.2` — a tela vira GRID, o input vira MODAL (14/10/2026)

**Origem:** *"a tela de gestão de contratos deverá ser para isso mesmo, então um grid para consulta interação e
etc é bem vindo, ações para contratos tbm, o modulo que inputa eles dentro da base pode ficar dentro de um
modal que abre ... use para colocar os dados dos contratos do cliente 2h"*.

**Por que mudou.** A `CTR_1.1` nasceu com a tela certa para *entrar* termo e errada para *consultar*
contrato: um assistente de quatro passos, com a consulta num campo de CNPJ no rodapé e **nenhuma rota de
listagem** — só `GET /cliente/{cnpj}`. Com 731 clientes na base, abrir a aba não respondia a pergunta que ela
existe para responder.

## Decisões dele, 14/10

| # | Decisão | O que vale |
|---|---|---|
| 1 | Escopo | **Grid + modal + piloto 2HM.** As fases futuras ficam escritas, sem código |
| 2 | Clicksign | **Só leitura.** Assinar segue fora do FPSL; a trava "não escreve na Clicksign" **continua valendo** |
| 3 | Valor mensal | **Vem do termo**, relendo o PDF — não do Harmonit nem da WESO |
| 4 | Ações obrigatórias | **confirmar quem SAI** numa troca e **ver os achados** do cliente |

## 🚨 Os quatro achados da construção

### 1. `/gravar` duplicaria o termo no primeiro upload do piloto
A carga gravou os 4.599 termos **sem hash de PDF** (ela não guarda documento), e a única defesa do endpoint
contra repetição é o `UNIQUE(hash)`. Subir o PDF assinado do 2649 da 2HM criaria um **segundo** termo 2649,
com os eventos repetidos, enquanto o primeiro seguiria contado em `sem_assinatura` — **a tela mostraria o
cliente pior por causa do próprio conserto**. Remédio: o **modo anexar** (`termo_id` no `/gravar`), que faz
`UPDATE` do termo que existe e insere **só** o evento que falta. O evento da carga que o assinado não
confirma **não é apagado**: o termo vira `revisar` com o motivo escrito, porque evento é imutável e a carga
usou a lista de placas do Harmonit.

### 2. O nome do cliente não existia em nenhuma tabela
`contrato_termo` tem só o CNPJ; a `clientes` do FPSL tem `harmonit_id` e `cnpjcpf`; o cache da WESO cobre
**304** clientes e **não tem a 2HM**. O nome estava no arquivo da carga e foi jogado fora. Entrou a tabela
`contrato_cliente` (`nome`, `nome_fonte`, autoria), com backfill idempotente do JSONL. ⚠️ Os nomes da carga
vêm do índice do Harmonit e chegam **sanitizados** (`M_ D_ G_ COMERCIO...`), por isso existe `nome_fonte`:
correção à mão é `manual` e **nenhuma carga a desfaz**.

### 3. Cache vazio não era cache velho — e o grid mostraria 0 ativas para todos
A guarda de recálculo olhava `MIN(calculado_em)`; com `contrato_placa` vazia o `MIN` vem nulo, e isso
respondia "está em dia". O grid então desenharia **0 placas ativas nos 731 clientes** com a base cheia de
eventos do lado — tela que mente, e acontece de verdade num banco restaurado. Agora cache vazio **com
evento na base** também é velho.

### 4. A busca por "2hm" devolvia a base inteira
O filtro extraía dígitos de qualquer texto: `2hm` virava o dígito `2`, que casa com quase todo CNPJ. Busca
com letra é busca por **nome**; só texto sem letra procura CNPJ (3 dígitos no mínimo). E quando nada casa, a
mesma caixa procura **placa** — comparando pela chave e mostrando o texto, porque `BUW8732` normaliza para
`BUW8H32`, que não existe.

⚠️ **E um texto que já era falso antes de hoje:** a tela dizia *"Comparar com a WESO ainda não acontece
aqui"* no mesmo arquivo em que o card da auditoria compara contrato × WESO desde 13/10. A frase era
verdadeira na C2 e a entrega seguinte não voltou para matá-la — é o `M12` em ato. Saiu, e a suíte agora
**falha se ela voltar**.

## O que entrou

| Arquivo | O que é |
|---|---|
| `painel/contratos_grid.py` (**novo**) | a listagem: `estado_cliente()` com enum fechado, `acoes_da_linha()`, 3 agregações, busca, CSV. **Nada se grava aqui** |
| `painel/contratos_tabelas.py` | `contrato_cliente`, `contrato_revisao`, coluna `harmonit_assinado` |
| `painel/contratos_carga.py` | `importar_nomes()` e `importar_harmonit_assinado()` |
| `painel/contratos_registro.py` | `anexar_assinado()`, `candidatos_para_anexar()`, `confirmar_saida()`, `marcar_revisado()`, `definir_nome()`, `recalcular_todos()`, `termos_de_todos()` |
| `painel/contratos_leitura.py` | `valor_das_placas()` |
| `painel/routers/contratos_router.py` | 7 rotas novas; `/gravar` ganhou `termo_id` e `cliente_nome` |
| `frontend/contratos.html` | grid + gaveta da ficha + modal de input |
| `tests/teste_contratos_grid.py` (**novo**) | 69 verificações |

### A linha é o CLIENTE, e isso tem motivo
A pergunta da tela é "como está o contrato deste cliente". Termo (4.599) e placa (6.800) são detalhe e viram
gaveta: termo como linha esconde o cliente, placa como linha repete o mesmo cliente em até 38 linhas.
**Estado** é enum fechado — `EM_DIA`, `ATIVA_SEM_ASSINATURA`, `A_REVISAR`, `SEM_PLACA_ATIVA` — num lugar só,
e é por ele que as fases futuras crescem.

### 🚨 A listagem não chama a ficha
A ficha recalcula o cliente na hora; chamá-la 731 vezes para desenhar a primeira tela era o caminho natural
e errado. São 3 agregações sobre o cache, e o recálculo em lote roda **no máximo uma vez por dia** — porque
o aviso prévio vence pelo calendário, sem evento nenhum para disparar a conta.

### O valor: o limite é do documento, não do código
O `pdf_extractor` entrega os itens de serviço (`valor_unitario`, já tratando valor riscado). **Um termo com
12 placas e um item "MENSALIDADE" não diz quanto é de cada veículo.** Então entra o que é inequívoco — uma
placa e um item, ou item que nomeia a placa — e o resto fica dito na tela, com a contagem de placas sem
valor. **Ratear o total seria inventar número, e a CAR emitiria cobrança em cima dele.**

## Verificação (14/10, local)

```
eventos 33 · leitura 32 · registro 27 · carga 24 · auditoria 30 · tela 79 · grid 69
= 294 verificações, 0 falhas
```
⚠️ `teste_contratos_router` roda **só na VPS** (`jose` não existe na máquina local) e a contagem de rotas
sobe de **9 para 16**, de propósito. `teste_extrair_termo` segue vermelha e **não é desta frente**.

## Fases futuras — cabem sem refazer, e por quê
A linha é o cliente e o termo é filho (o pipeline é por termo, e cada termo expandido ganha uma coluna de
etapa); `estado` é função única; `acoes` já vem do backend, então "gerar termo" aparece no dia em que a rota
existir.

🚨 **Uma regra dura, a registrar antes de existir rascunho:** termo em geração tem eventos e `assinado=0` —
o motor de hoje o trataria como "não assinado" e **ainda assim marcaria a placa ATIVA** na segunda passada.
`termos_do_cliente()` precisa filtrar por ciclo **antes** da primeira tela de geração; a coluna
`contrato_termo.ciclo` entra em `migrar()` quando a fase chegar.

Tarefas próprias, cada uma com o OK dele: **gerar termo** (não há gerador no FPSL — sem `reportlab`, `docx`
ou `jinja` — e numerar/escrever no Harmonit contraria a trava de escrita); **pipeline com cobrança de
etapas** (`contrato_etapa` só de inserção, no molde do `contrato_evento`, com laço desligado por
interruptor); **leitura da Clicksign** (decisão 2); **entrega ao financeiro** (idempotente por `termo_id`,
só para termo assinado e conferido) — e essa **depende de resolver a fonte do valor por placa**, que a G4 só
resolve no caso fácil.

---

# `C7` — os PDFs assinados entram na base (14/10/2026, piloto 2HM NO AR)

**Origem:** *"siga com o plano aprovado do FPSL"*. O plano: a base tinha **0 termos com PDF guardado** (os
4.599 vieram dos CSVs da auditoria), `valor_mensal` vazio em **100%** das linhas, e **412** termos marcados
`revisar` por "placas diferentes entre o PDF do Harmonit e o assinado" — porque a carga usou a lista do
**Harmonit**, que é editada depois da assinatura.

## O que entrou

| Arquivo | O que é |
|---|---|
| `painel/contratos_eventos.py` | ação **`ANULA`** + filtro de eventos anulados nas duas passadas |
| `painel/contratos_tabelas.py` | `contrato_evento.corrige_evento_id` (índice único parcial) e o livro-razão `contrato_carga_pdf` |
| `painel/contratos_registro.py` | `anular_evento()`, `correcoes_do_cliente()`, `id`/`corrige` nos **dois** leitores de termo, `correcoes` na ficha |
| `painel/contratos_assinados.py` (**novo**) | a carga: classifica em *anexado · documento só · fila*, corrige pelo assinado, livro-razão, retomada |
| `preparar_assinados_c7.py` (**novo**, roda no Windows) | monta o lote: só `assinado`, CNPJ do nome da pasta, manifesto com `sha256` |
| `tests/teste_contratos_anula.py` (**novo**) | 24 verificações |
| `tests/teste_contratos_assinados.py` (**novo**) | 68 verificações |

## 🚨 Por que `ANULA` teve de existir

O motor tinha `ACOES` fechado em `ENTRA · SAI · RESCINDE · UPGRADE`, os eventos chegavam **sem `id`** e
não havia coluna que apontasse um evento para outro. E **não havia atalho honesto**:

| Tentação | Por que mente |
|---|---|
| `SAI` | deixaria a placa **SUBSTITUIDA** — inventa uma saída que não houve |
| `RESCINDE` | deixaria **RESCINDIDA** — inventa uma rescisão que não houve |
| `UPDATE` no evento | viola a imutabilidade, que é o que faz "por que esta placa está ativa?" ter documento como resposta |

A verdade é outra: a placa **nunca esteve no contrato** — foi a lista do Harmonit que a pôs lá. Então entra
um evento novo apontando para o errado, e **o errado continua visível**, com autoria e motivo. O filtro roda
**antes** das duas passadas, porque a anulação pode estar num termo que vem depois na ordem.

## 🚨 O defeito que a primeira passada causou em produção — e a reversão

A primeira passada do piloto **inseriu identificador inventado**. O extrator devolveu a **linha descritiva
inteira** no lugar da placa:

```
Cod: 01-06 - Escavadeira Hidraulica- JohnDeere- 210G - Amarela- 1F9210GXKED520143 - 2014
Escavadeira PC350, Komatsu, PC350 LC-8 B10217
1BZ310KXJEC000130 (ID: 007842126)
Cod: 01-05 (ID: 205727026)
```

...e a carga criou evento com isso **e anulou o identificador correto que estava na base** (nos termos 2652,
2703 e 3520). **Identificador inventado é pior que identificador faltando** (regra 13, a família do
`RFD 2447`): a cobrança passa a apontar para um veículo que não existe.

**Revertido pelo livro-razão**, com `antes_json`: 11 eventos apagados, 1 cliente recalculado, 7 PDFs
removidos — e a base voltou **exatamente** a 4.599 / 12.114 / 6.812 / 0 com arquivo / 795 a revisar.

**A guarda que entrou** (`identificador_suspeito`): recusa texto com mais de 20 caracteres de chave,
pontuação de frase, 3+ espaços ou palavra escrita. **Um identificador ruim reprova o documento inteiro** —
metade boa não salva, porque se a leitura errou numa linha não há razão para confiar nas outras. O documento
vai para a **fila**, e decifrar a linha seria mexer no `pdf_extractor`, que é da aba Operações e é
**intocável**.

⚠️ **E um segundo defeito, pego pela contagem:** "5 termos com arquivo contra 4 PDFs em disco". O caminho
"documento só" gravava o nome do arquivo **sem copiá-lo** para a pasta de documentos — a ação "PDF" do grid
responderia *"está registrado como X, mas não está na pasta"*. Corrigido, e conferido um por um: os 5
documentos existem em disco e o `sha256` de cada um bate com o `hash` do termo.

## O piloto 2HM — o que de fato aconteceu

**A regra central do casamento, provada em produção:** os dois documentos chamados `2 - aditivo - assinado`
foram para os termos **2207** e **2224**, pelo número lido **dentro** do PDF. (A instrução anterior, de
subi-los como termos novos, estava errada e criaria dois termos falsos.)

| Documento | Destino |
|---|---|
| 2207, 2224, 2649, 2764 | **anexado** |
| 3465 (`acordo`) | **documento só** — é renegociação, 0 placas |
| 2652, 2703, 3520 | **fila** — a leitura devolveu linha descritiva |
| 3520 `cancelado` | **não foi nem copiado** para a VPS |

**A correção funcionou:** no 2224 entrou `FJW 0B75` e o `00D6NCCCK01011` foi **anulado**, com a chave da
Clicksign e a autoria no texto. A ficha mostra a correção; o evento anulado continua lá.

### 🚨 E a consequência que precisa de decisão dele: a 2HM foi de 4 para 12 placas ativas

| | Antes | Depois |
|---|---|---|
| ATIVA | 4 | **12** |
| RESCINDIDA | 20 | 12 |

O detalhe: **10 das 12 ativas são do termo 2207, com `base = "assinado"`** — e o documento assinado do 2207
lista **3** placas, não 16. Ao marcar o termo como assinado, **a lista do Harmonit herdou a assinatura**.
A correção automática foi recusada de propósito (13 de 16 placas não confirmadas, acima da metade), então as
13 ficaram, agora como "assinadas".

Some-se o outro lado: a **rescisão 8904** (29/09/2026), que fecharia 10 dessas placas, **não tem
assinatura** — e, pela regra dele, termo sem assinatura não conta na primeira passada. É exatamente o que a
aba existe para mostrar, mas o `base = "assinado"` de placa que o documento não lista **é a base mentindo**.

**Três caminhos, e a escolha é dele:**
1. **Requalificar** (proposto): quando a correção é recusada, anular os eventos não confirmados e reinserir
   os mesmos com `fonte=harmonit` — a placa continua no contrato, e a base passa a dizer "nao assinado", que
   é a verdade da origem. Corrige sem apagar, e usa o mecanismo que já existe.
2. **Fila:** documento com divergência grande não é anexado, e o termo não é marcado assinado.
3. **Deixar como está:** a lista do Harmonit herda a assinatura do documento.

## Conferido pelo estado

```
integrity_check ok · hash duplicado 0 · anulação duplicada 0
estado proibido no livro-razão 0 · identificador suspeito entre os eventos novos 0
5 PDFs em disco = 5 termos com arquivo, e o sha256 de cada um bate com o hash
sha256 de operacoes_*.py + pdf_extractor.py: IGUAL ao da manhã
grid e ficha concordam: 12 e 12
base: 4.599 termos · 12.117 eventos · 6.812 placas · 5 com arquivo · 796 a revisar
```
**Backups:** `backups/fpsl.db.bak_pre_c7_2026-10-14` (`integrity_check` ok antes de começar).

**Placar:** as **10 suítes da CTR somam 452 verificações, 0 falhas**; travas da casa verdes
(`teste_barra_status` 89, `teste_perfis` 27, `teste_registro_telas` 43) e **Operações intacta**
(`teste_tela_operacoes` 62, `teste_aba_ponta_a_ponta` 35).

## O que falta na C7
1. 🔴 **A decisão das três opções acima** — ela vale para os **412** termos com placa divergente, não só para
   a 2HM. **Nenhum outro cliente entra antes disso.**
2. 🔴 **A fila na tela** (A7): os casos de leitura descritiva, CNPJ divergente e número ambíguo estão no
   livro-razão e **ainda não aparecem no grid**.
3. 🔴 **O valor** (A6): a regra ampliada que ele aprovou (reconhecer `PACOTE`/`FULL MANAGER` e aceitar
   `Qtd = nº de placas` como preço por veículo) **não foi implementada** — nenhum item ganhou valor no piloto.
4. ⚠️ **A 2HM tem 3 documentos na fila por leitura descritiva.** São termos de máquina pesada
   (escavadeira, trator), e o layout deles não é o que o extrator espera. Vale medir quantos dos 2.825 caem
   nisso antes de prometer cobertura.

## `C7` — A6 (o valor) e A7 (a fila na tela), 14/10 NO AR

As duas frentes que **não** dependiam da decisão dos 412 termos.

### A6 — o valor: a regra ampliada que ele aprovou, e o que ela achou de verdade

Decisão dele: reconhecer `PACOTE`/`FULL MANAGER`/`Mensal` e aceitar **`Qtd` igual ao número de placas** como
preço por veículo. **Não é rateio** — rateio dividiria um total e o número sairia de nós; aqui ele sai do
documento.

🚨 **A primeira ampliação ficou LARGA DEMAIS, e isso foi medido no termo 2207 da 2HM.** Ela passou a casar
**dois** itens:

| Item do documento | Qtd | Valor | O que é |
|---|---|---|---|
| `Equipamento rastreador telemetria avançada` | 16 | **999,90** | venda do aparelho |
| `Adesão` | 16 | 299,90 | uma vez só |
| `PACOTE FULL MANAGER` | 16 | **75,26** | **a mensalidade** |

Com dois candidatos, nenhuma placa recebia valor — e, pior, sem a exclusão a cobrança poderia sair com o
preço do equipamento no lugar da mensalidade: **13× o valor certo**. Entrou `_NAO_MENSAL_RE`, que tira
adesão, taxa, equipamento, instalação, aquisição, retirada, aviso prévio, multa, ressarcimento, frete e
cadastro.

**Resultado medido nos PDFs já guardados da 2HM:**
```
2207  placas=3  itens_mensais=1  com_valor=0   (qtd 16 x 3 placas lidas -> NAO atribui)
2224  placas=1  itens_mensais=1  com_valor=1   -> FJW 0B75 = 75,26
2649  itens_mensais=0  (rescisão: só aviso prévio e taxa de retirada)
2764  itens_mensais=0
3465  tipo não reconhecido -> não lido
```
**É o primeiro `valor_mensal` da base inteira** — eram 0 de 6.462 linhas.

⚠️ **E dois defeitos encadeados, o segundo silencioso:**
1. `anexar_assinado` inseria o **evento** da placa nova e **não criava o item** — e o valor mora no item
   (decisão dele, 13/10). Então a placa que entra pelo assinado não tinha onde carregar o valor.
2. `preencher_valores` ficava **calado** nesse caso: o `UPDATE` casava 0 linhas e os dois contadores
   voltavam vazios, como se o documento não tivesse valor. Entrou o contador `sem_item` — **contador que
   esconde "não existe" é número que mente**.

### A7 — a fila da carga aparece na tela

Os documentos que a carga não encaixa viviam só no livro-razão, no banco. **Fila invisível é fila que
ninguém resolve.** Agora:
- coluna **"Na fila"** na linha do cliente, e chip com quantos clientes têm documento parado;
- ação **"Documento na fila"**, que abre a gaveta no bloco novo;
- o bloco mostra termo, arquivo, estado de origem e **por que parou**, e diz em voz alta que **nada foi
  gravado por eles** — forçar anexaria o assinado ao contrato errado;
- rota `GET /painel/api/contratos/carga/fila` (owner, 401 sem token). Rotas: **16 → 17**.

⚠️ O resumo agrupa por **tipo** de problema, e para isso tira o que é do caso: o texto citado e os números.
A primeira versão cortava no `:` — e o próprio motivo tem dois-pontos (*"a leitura devolveu 'Cod: 01-05...'"*),
então cada documento virava um grupo de um. Hoje: **3x "a leitura devolveu"**.

### Conferido pelo estado
```
/painel/contratos 200, e a tela servida tem a fila
/carga/fila -> 401 sem token
fila da 2HM: 3 documentos, todos por leitura descritiva
item do 2224: FJW 0B75 = 75,26 (lido do documento assinado)
suíte do FPSL: 63 arquivos, 2.283 verificações
```
⚠️ **Dois vermelhos, nenhum desta frente:** `teste_extrair_termo` (expurgo F7, 02/10) e
`teste_higiene_placas_weso`, que **ficou vermelho hoje** — é teste de integração contra a **WESO ao vivo** e
acusa 1 placa com espaço à direita. A CTR **não escreve na WESO**, e o próprio teste registra que a WESO
recebe cadastro por fora do FPSL. **Não investiguei a fundo nem corrigi**: o conserto escreve na WESO, o que
é fora de escopo e exige a palavra dele (há `corrigir_placas_espaco.py` no projeto, de 27/07).

---

# Frente `D` — a WESO desempata, placa por placa (14/10/2026, coorte aderente NO AR)

**Origem (regras dele):** *"o criterio de desempate será quantas placas ativas ele tem na weso"* ·
*"termo antes de placas; porem, placas sem assiantura mas placa ativa, placa vence, pois se existe na weos
foi feita, o erro é não ter assinatura"* · *"primeiro os casos de 100% de aderência com margem de 1+ ou -"*
· *"usar a linha do tempo como parametro pelas datas ou entrada e saidas das placas, pois pode ser que N
placas foram recindidas mas nao assinadas, se tiverem fora da Weso, é recisão mesmo"*.

## O que eu validei antes de escrever código

1. 🚨 **A rotina do cache da WESO está SADIA — o buraco não é dela.** Rodou 04:15 (1.933 veículos, 3.803
   rastreadores, `integrity_check`, troca atômica). Ela **tenta** gravar o cliente
   (`_sub(v, "cliente", "id")`), mas `/Veiculos/Consultar` devolve 12 campos e **nenhum é de cliente** —
   medido: **0 de 1.932**. Consertar exigiria uma chamada por cliente (304+), o caminho de 15,6 s a timeout
   medido em 18/08.
2. 🚨 **E o desempate dele NÃO precisa da planilha.** O vínculo que falta é veículo→cliente; a regra usa o
   **inverso** — "esta placa do contrato existe na WESO?" — e isso o cache responde hoje, por placa **e por
   chassi**. A planilha da auditoria ficou como conferência, não como fonte.
3. ⚠️ **`valor_mensalidade` vem no payload da WESO e está ZERO nos 1.932.** Não é fonte de valor.

## As regras, como entraram

**Precedência: o termo define o que existe.** A WESO não cria contrato — ela desempata.

| Caso | Regra | Medido |
|---|---|---|
| **Placa na WESO** | **vence: fica ativa**, mesmo sem assinatura. A falta de assinatura é **achado** | **1.643** em uso; **150** delas sem assinatura |
| **Fora da WESO + rescisão na linha do tempo**, mesmo não assinada | **é rescisão mesmo**: fecha | 84 ainda a fechar (ver abaixo) |
| **Fora da WESO sem rescisão** | nada a fechar: fica como está | 1.244 |

🚨 **A proposta de "requalificar" caiu**, e a regra 2 dele é melhor: requalificação cega puniria exatamente o
veículo que está rodando. Quem está em uso não perde nada.

### Como a prova entra sem o motor perder a pureza
Fonte nova **`weso`** em `contratos_eventos.py`. Um `RESCINDE` com `fonte="weso"` **vale mesmo em termo sem
assinatura** — é a única fonte com esse poder, porque ela não afirma o que foi assinado, afirma o que **está
instalado**. A base da placa passa a dizer `"rescisao confirmada pelo uso (fora da WESO)"`.
⚠️ **Quem consulta a WESO é `contratos_aderencia.py`, nunca o motor** (que segue sem I/O, travado por teste),
e o evento aponta em `corrige_evento_id` a rescisão que ele confirma — **nada de `UPDATE`**. A mesma guarda
de 48 h da rotina C6 vale aqui: fechar placa por ausência com dado velho é pior que não decidir.

## 🚨 A primeira rodada real mostrou DUAS imprecisões na minha regra

Das 32 primeiras confirmações, só **15** mudaram algo:

| O que aconteceu | Quantas | Por que a regra não devia disparar |
|---|---|---|
| Placa **já em aviso prévio** | **12** | a rescisão **já está valendo** e o prazo corre pelo calendário, sozinho |
| Placa **reativada por termo posterior** | **5** | ali "fora da WESO" não é saída, é **ainda não instalada** (a `SWL1I23`, reativada pelo termo 8708) |

As duas entraram como guarda, com teste, e os **17 eventos inertes foram removidos** (17 clientes
recalculados). Com a regra apertada, o universo a fechar caiu de 246 para **84**.

⚠️ **E um número meu que estava inflado:** eu havia medido "549 placas com rescisão na linha do tempo". A
consulta casava placa **entre clientes diferentes**; comparando por `(cliente, placa)`, como o módulo faz,
são **246** — e **84** depois das duas guardas.

## Estado final (coorte aderente aplicada)

```
ATIVA 2.778 -> 2.763      RESCINDIDA 2.922 -> 2.937      aviso 208 (inalterado)
eventos 12.117 -> 12.132  |  fonte=weso: 15, TODAS em placa RESCINDIDA
termos 4.599 e itens inalterados  |  integrity_check ok
coortes: 347 aderentes (a de 359 menos os já resolvidos) e 132 contrato maior que o uso
sha256 de operacoes_*.py + pdf_extractor.py: IGUAL ao da manhã
```
**Backup:** `backups/fpsl.db.bak_pre_d_2026-10-14` (96 MB, `integrity_check` ok, contagens conferidas antes
de qualquer escrita).
**Placar:** as **11 suítes da CTR somam 513 verificações, 0 falhas**; `teste_barra_status` 89,
`teste_perfis` 27, `teste_tela_operacoes` 62.

## O que falta na frente D
1. 🔴 **Os 84 que sobraram**, quase todos na coorte "contrato maior que o uso" (132 clientes) — pela regra
   dele, cada um pede a linha do tempo lida. **Não rodei**: é a coorte que ele mandou separar.
2. 🔴 **D4, a tela:** a aderência por cliente (sustentadas × em uso) e o motivo por placa ainda não
   aparecem no grid nem na ficha.
3. ⚠️ **150 placas em uso sem assinatura** — pela regra 2 elas ficam ativas, e o que falta é a assinatura.
   Hoje isso só aparece como achado da C6; merece ser ação na tela.

## `D4` — a aderência com a WESO na tela (14/10 NO AR)

**Origem:** a pergunta dele, olhando o grid: *"como assim 2778 placas ativas? isso seria baseado no que?"*.
A resposta estava fora da tela — o número é o que os **termos sustentam**, e não o que está em uso.

### O que a tela passou a mostrar
1. **Coluna "Na WESO"** ao lado de "Ativas", com o selo de aderência: *bate* (margem ±1), *contrato maior*,
   *uso maior*, *sem placa sustentada*.
2. **Chips que filtram** por "contrato bate com o uso" (347) e "contrato maior que o uso" (132), e um chip
   que diz **de quando é o dado**: *"1.643 das sustentadas estão na WESO · cache de 15h"*.
3. **Na ficha, o motivo por placa** — porque *"ativa" não distingue a placa que está rodando da que nunca
   foi instalada*: **em uso** · **saiu (rescindida)** · **nunca instalada**, mais a marca *falta assinar*.
4. **Rota nova** `GET /cliente/{cnpj}/aderencia` (owner, 401 sem token). Rotas: **17 → 18**.

### 🚨 Duas coisas que eu tive de corrigir para a tela não afirmar demais

1. **A coluna NÃO podia se chamar "Em uso".** A checagem é de **presença no cadastro da WESO**, e a presença
   é **global**: placa cadastrada na WESO de outro cliente conta aqui — é a família dos **84** achados
   "mesma placa em dois clientes". Medido na 2HM: **6 presentes** contra **2** que a auditoria apurou como
   em uso. Virou **"Na WESO"**, e o cabeçalho diz *"é presença, não instalação"*.
2. **"Sem dado da WESO" culpava a fonte errada em 252 clientes.** Eles não têm placa sustentada — não é o
   cache que falta. Virou rótulo próprio (`SEM_PLACA_SUSTENTADA`), e agora as coortes **fecham**:
   347 + 132 + 252 = **731**, com *sem dado da WESO* em **zero**.

### Custo, medido
A listagem lê o cache com uma consulta de **presença** (`chaves_do_cache`), não com a leitura caríssima da
rotina C6 — que faz uma consulta de rastreador **por veículo** porque precisa da situação de cada um. Com
isso o grid continua em **0,05–0,09 s** para as 731 linhas, 2.148 chaves da WESO lidas.
⚠️ Sem cache, `em_uso` fica **nulo** e a tela mostra "—" dizendo por quê: zero seria a afirmação falsa
"nada em uso". Cache acima do teto de 48 h faz a ficha avisar que a coluna pode estar desatualizada — a
rotina se recusa a decidir nessa situação, e a tela não pode afirmar onde a rotina recusaria.

### Conferido pelo estado
```
/painel/contratos 200, e a tela servida tem a coluna "Na WESO"
/cliente/{cnpj}/aderencia -> 401 sem token          rotas: 18
coortes: 347 aderentes + 132 contrato maior + 252 sem placa sustentada = 731
1.643 das 2.971 sustentadas estao na WESO    |    cache de 15 h
2HM: 12 ativas, 6 na WESO -> CONTRATO_MAIOR_QUE_USO
ficha da 2HM, por placa: em uso / fora com rescisao / nunca instalada
sha256 de operacoes_*.py + pdf_extractor.py: IGUAL ao da manha
```
**Placar:** as **11 suítes da CTR somam 533 verificações, 0 falhas** (tela 95, grid 78, router 68);
travas da casa verdes (89 + 27) e **Operações intacta** (62 + 35).

---

# Fechamento de 14/10/2026 — pendências VERIFICADAS pelo estado

Não é lista de lembrança: cada linha abaixo foi medida no banco, no serviço ou na suíte, hoje.

## O que ficou de pé

```
suíte do FPSL            64 arquivos, 2.342 verificações
as 11 suítes da CTR      533 verificações, 0 falhas
/painel/contratos        200, servindo a tela nova (grid + coluna "Na WESO")
rotas do router          18, todas sob a tranca de owner
integrity_check          ok    ·  hash duplicado 0  ·  anulação dupla 0
placas                   ATIVA 2.763 · aviso 208 · RESCINDIDA 2.937 · SUBSTITUIDA 904
clientes com nome        731 de 731
termos com PDF           5      (de 4.599)
itens com valor mensal   1      (de 6.463)
eventos ANULA            1      ·  eventos fonte=weso  15
livro-razão da carga     4 anexado · 1 documento só · 3 fila
rotina de auditoria      DESLIGADA (sem linha na config), como ele decidiu
```

## 🚨 Três inconsistências que a própria verificação achou — e que eu causei

1. **O livro-razão tinha perdido a linha do 3465.** Eu a apaguei no ciclo de reparo do "documento só", e
   ficaram 5 termos com PDF contra 7 linhas no livro. Reposta, com o motivo escrito dentro da própria linha.
   Agora fecha: 4 anexados + 1 documento só = os 5 termos com PDF.
2. **Um arquivo órfão que eu criei:** `fpsl_weso/painel/contratos_router.py`, **fora** de `routers/` — erro de
   destino num `scp` meu. Era uma cópia **velha** (versão de 17 rotas), ninguém a importava
   (`main.py` importa de `painel.routers`), e foi apagada. Painel conferido depois: 200 e 18 rotas.
3. **Dois `grep` meus deram falso negativo hoje**, e em nenhum dos dois o código estava errado: o seletor
   `[data-v-...]` no meio da regra do MoviZap, e um parêntese a mais na busca do `correcoes_do_cliente`.
   ⚠️ **Conferência que falha por padrão mal escrito é pior que conferência nenhuma** — ela convida a
   "consertar" o que está certo.

## A auditoria, rodada hoje por "Rodar agora" (a rotina segue desligada)

| Tipo | 13/10 | 14/10 | |
|---|---|---|---|
| CONTRATADA_NAO_INSTALADA | 1.362 | **1.349** | −13 |
| SUBSTITUICAO_PELA_METADE | 364 | 364 | 0 |
| EM_USO_SEM_CONTRATO | 320 | **322** | +2 |
| ENCERRADA_EM_USO | 173 | **168** | −5 |
| EM_USO_FALTA_ASSINAR | 135 | **136** | +1 |
| PLACA_EM_DOIS_CLIENTES | 84 | **83** | −1 |
| **total** | **2.438** | **2.422** | **−16** |

⚠️ **A queda é pequena, e eu não prometi mais que isso:** só 15 placas fecharam e 5 termos ganharam PDF. O
movimento grande espera a carga dos 2.825 assinados.
⚠️ **E o delta tem DUAS causas, não uma:** além do meu trabalho, o cache da WESO é de **14/10** e a rodada
anterior comparava com o de **13/10** — um dia de cadastro novo entra na conta. Conferido: **nenhuma** das 15
placas que a frente D fechou, e nem a placa que a C7 anulou, aparece entre os achados.

## Pendências, verificadas uma a uma

### 🔴 Dele (nada avança sem isso)
1. **Abrir no navegador:** `/painel/contratos` (grid, chips, modal, gaveta e a coluna "Na WESO" dentro da
   ficha, que agora tem 7 colunas) e o **botão Ficha do MoviZap** em nome curto, nome longo e conversa sem
   cadastro. Nenhum teste vê largura, recorte ou elemento cobrindo outro.
2. **Os 84 que a frente D deixou**, na coorte "contrato maior que o uso" (132 clientes) — é a coorte que ele
   mandou separar, e cada caso pede a linha do tempo lida.
3. **A carga dos 2.825 assinados** segue parada por decisão dele. Hoje são **5** termos com PDF.
4. **`teste_extrair_termo`** (vermelho desde 02/10, expurgo F7): apagar a suíte ou reescrevê-la contra
   `/painel/api/operacoes/extrair`. Enquanto existir, o placar do FPSL não fecha verde.
5. **`teste_higiene_placas_weso`** ficou vermelho **hoje**: 1 placa com espaço à direita na **WESO ao vivo**.
   Não é da CTR, que não escreve na WESO; o conserto escreve, e há `corrigir_placas_espaco.py` no projeto.

### 🟡 Medido e à espera de vez
6. **As 150 placas em uso sem assinatura** aparecem marcadas na ficha, mas **não têm ação própria** — cobrar
   assinatura é trabalho, não defeito de cadastro.
7. **Os 3 documentos na fila da 2HM** (leitura descritiva em termo de máquina pesada). **Falta medir quantos
   dos 2.825 caem nisso** antes de prometer cobertura.
8. **O valor:** 1 item com valor mensal, de 6.463. A `CAR_1.1` depende disto, e a WESO **não ajuda** — o
   campo `valor_mensalidade` dela vem **zero** nos 1.932 veículos.
9. **O vínculo veículo→cliente no cache da WESO** não existe porque a API não o entrega
   (0 de 1.932 em `/Veiculos/Consultar`). Consertar custa uma chamada por cliente; só vale se ele quiser.

### ✅ Fechadas hoje, e por isso saem da lista
- A **fila da carga invisível** → coluna, chip e bloco na ficha, com o motivo (A7).
- A **regra do valor quase inerte** → ampliada e com o "paga uma vez só" excluído (A6).
- A **decisão dos 412 termos** → substituída pelas regras dele, e a coorte aderente aplicada (frente D).
- O **nome do cliente ausente** → 731 de 731.
- O **`/gravar` que duplicaria termo** → modo anexar, provado em produção.

## Versionamento
19 arquivos modificados no `fpsl_weso` e 3 no `movizap_painel`, todos esperando o **autocommit das 23:30**.
⚠️ Árvore limpa não significa sincronizado — é a regra da casa, e vale aqui.
