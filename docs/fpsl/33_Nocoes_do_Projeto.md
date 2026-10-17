# 33 — Noções do projeto FPSL: o que ele é, e por que é assim

> Escrito em 14/10/2026, a pedido dele, depois da sprint que levou a aba de Contratos do nascimento à
> conciliação com a WESO. **É o documento de leitura primeira**: quem chegar aqui entende o porquê antes de
> abrir código.
>
> ⚠️ O número é **33** porque o **32 está reservado** para a `CAR_1.1` (Contas a Receber), já citada por esse
> número no doc 31 e no plano.
>
> 🚨 **Todo número aqui tem data, e número sem data não se copia.** O estado real se mede com
> `sqlite3 -readonly` e com a suíte; esta página explica o DESENHO, e os números servem de ordem de
> grandeza, não de fonte.

---

## 1. Para que o projeto existe

O FPSL não nasceu para guardar contrato. Ele nasceu para operar — ordem de serviço, técnico, equipamento,
pagamento. O que faltava era a base que responde duas perguntas de dinheiro:

- **o que este cliente tem direito a ter?**
- **o que ele deve pagar por isso?**

Sem essa base, o vazamento não é visível. Medido em 13–14/10, sobre 1.933 veículos da WESO:

| Achado | Quantos |
|---|---|
| contratada e não instalada | 1.349 |
| substituição pela metade | 364 |
| **em uso sem contrato** (serviço entregue, provavelmente não cobrado) | 322 |
| encerrada e ainda em uso | 168 |
| em uso, falta assinar | 136 |
| mesma placa em dois clientes | 83 |

E no caminho inverso, **1.005 placas assinadas não estão na WESO**. Nenhum desses números era acionável antes,
porque não havia base para dizer qual lado estava certo.

**O destino é a `CAR_1.1`**: a cobrança deixa de ser digitada e passa a ser **lida** do contrato.

---

## 2. As quatro fontes, e por que elas discordam **por desenho**

| Fonte | O que ela é | O que ela não é |
|---|---|---|
| **Clicksign** | o documento assinado: o que vale juridicamente | não cobre tudo — ~500 termos são de 2017–2019, anteriores ao uso dela |
| **Harmonit** | o índice de contratos e a cobrança | o PDF dele é **editado depois de assinado**, com troca de placa anotada em texto livre |
| **WESO** | o que está instalado e rodando | não entrega o vínculo veículo→cliente (medido: 0 de 1.932 em `/Veiculos/Consultar`) |
| **FPSL** | a operação (OS, técnico, equipamento) | não tinha o contrato |

🚨 **A edição posterior do PDF do Harmonit é a causa de origem de quase tudo.** Dela vêm os **412** termos com
"placas diferentes entre o PDF do Harmonit e o assinado", os **796** termos marcados a revisar, e a diferença
entre o que a ficha mostra e o que a planilha da auditoria apurou. **Enquanto o termo nascer fora do sistema e
puder ser editado depois, a conciliação é esteira infinita** — é por isso que gerar termo dentro do FPSL (em
PDF virtual, ligado na Operações, decisão dele de 14/10) é o único item que ataca a causa; todo o resto limpa
consequência.

---

## 3. O núcleo do modelo: evento imutável, estado derivado

A base **não guarda a situação da placa**. Ela guarda o que aconteceu, e calcula a situação.

```
contrato_termo    o documento (número, empresa, assinatura, PDF, hash)
contrato_evento   ENTRA · SAI · RESCINDE · UPGRADE · ANULA    <- IMUTÁVEL
contrato_placa    cache do resultado                          <- DERIVADA, nunca fonte
contrato_item     a placa como item de cobrança (valor, vigência)
```

Três consequências que o projeto escolheu de propósito:

1. **Corrigir é acrescentar, nunca editar.** Onde a lista do Harmonit pôs placa que o documento assinado não
   traz, entra um evento `ANULA` apontando o errado — e o errado **continua visível**. É o oposto do que o
   Harmonit faz, e é o que faz "por que esta placa está ativa?" ter um documento como resposta.
2. **A ordem é o número do termo, nunca a data.** A data do Harmonit vem `01-01-2000` quando não existe, e há
   contrato datado depois da própria rescisão.
3. **O estado envelhece sozinho.** O aviso prévio de 90 dias vence pelo calendário, sem evento nenhum — por
   isso a ficha recalcula ao abrir e o grid refaz o cache quando ele é de outro dia.

### As ações, e por que `ANULA` e `weso` existem
`SAI` diz que a placa saiu (substituição). `RESCINDE` diz que o contrato dela encerrou. Nenhuma das duas
servia para dizer *"esta placa nunca esteve no contrato"* — usá-las mentiria (a placa ficaria SUBSTITUIDA ou
RESCINDIDA). Daí `ANULA`. E `fonte="weso"` existe porque há um caso em que a prova não é documento, é **uso**:
rescisão sem assinatura de placa que já saiu da WESO.

---

## 4. As regras dele (são decisões, não convenções minhas)

| Quando | Regra |
|---|---|
| 13/10 | **Vale o assinado** — termo sem assinatura não conta, *a menos que falte dos dois lados* |
| 13/10 | **Troca registrada no Harmonit vale**, se o termo está assinado e o cliente pediu |
| 13/10 | **Aviso prévio conta**: rescisão assinada há até 90 dias ainda pode estar em uso |
| 13/10 | **O valor vem do termo**, e fica no `contrato_item`; a CAR calcula, não decide |
| 14/10 | **Termo antes de placas**, mas **a WESO desempata** |
| 14/10 | **Placa na WESO vence**, mesmo sem assinatura: *"se existe na WESO foi feita, o erro é não ter assinatura"* — e a falta de assinatura é **achado**, não motivo para tirar a placa |
| 14/10 | **Fora da WESO, com rescisão na linha do tempo mesmo não assinada, é rescisão mesmo** |
| 14/10 | **Primeiro os casos de 100% de aderência, margem ±1**, separados dos demais |
| 14/10 | **Clicksign é só leitura**; assinar segue fora do FPSL |
| 14/10 | **A rotina de auditoria nasce e segue desligada**, com interruptor na própria tela |

---

## 5. O cruzamento: o que já liga, e o que falta

**Já liga** (medido em 14/10):

| Ligação | Estado |
|---|---|
| placa → termo vigente | 6.812 de 6.812 |
| termo → placas | 12.132 eventos |
| cliente → termos → placas | a ficha faz |
| **histórico por placa** (a cadeia "contrato → aditivo → rescisão") | derivável para **3.811** placas |
| placa → está na WESO? | sim, por placa **e por chassi** |

**Não liga ainda:**

1. 🔴 **Equipamento dentro do contrato.** `recursos` está **vazio** nos 12.132 eventos e nos 6.463 itens —
   bloqueio, RFID e central 24h não entraram. A cadeia física existe **fora** do contrato: a WESO liga
   **1.924** veículos a rastreador e **3.099** rastreadores a chip. Falta a junção
   `contrato_item ↔ rastreador ↔ chip`.
2. 🔴 **O valor.** **1** item com valor mensal, de 6.463. E a WESO **não ajuda**: o campo
   `valor_mensalidade` dela vem **zero** nos 1.932 veículos.
3. 🔴 **O documento.** **5** termos com PDF guardado, de 4.599. Os 2.825 assinados da Clicksign esperam carga.
4. ⚠️ **O vínculo veículo→cliente da WESO**, que a API não entrega e que hoje só existe por uma exportação de
   tela feita à mão.

---

## 6. O "sinal vivo", e a condição para ligá-lo

O contrato **já é** sinal vivo: o estado sai do evento, e muda sozinho quando o calendário anda. A Contas a
Receber deve nascer do mesmo jeito — **uma leitura do contrato num mês**, com o documento atrás, e **não um
cadastro paralelo**. Recebível copiado congela, e aí o problema que estamos consertando volta com outro nome.

🚨 **A condição é a base merecer confiança.** Gerar cobrança hoje seria emitir em cima da lista do Harmonit —
exatamente o que a regra de 14/10 proíbe. Os três números que medem essa confiança são os do item 5: documento,
valor, equipamento.

---

## 7. A ordem de dependência (não é preferência)

1. **Carga dos 2.825 assinados** — documento guardado, e valor onde o termo declara.
2. **Fonte de valor para o resto** — o faturado por cliente/mês do Harmonit, em leitura. *Sugestão minha.*
3. **Equipamento no contrato** — `contrato_item` com rastreador e chip, para o recebível saber o que está
   instalado, não só qual placa.
4. **Histórico por placa na tela** — curto, porque o dado já existe.
5. **`CAR_1.1` em modo conferência** — pré-fatura comparada com o que o Harmonit faturou, **sem emitir nada**,
   até bater cliente a cliente.
6. **Gerar termo no FPSL** — fecha a entrada, para a conciliação convergir em vez de só rodar.

---

## 8. As travas que qualquer um que chegue aqui precisa saber

1. 🛑 **A aba Operações é intocável**, e os testes dela contam. `pdf_extractor` e `operacoes_*` são **lidos**,
   nunca alterados — conferido por `sha256sum` antes e depois de cada entrega.
   ⚠️ **Exceção única, 16/10 (item 3, aprovado por ele):** `painel/operacoes_rotina.py` ganhou **só o carimbo
   da passada** no laço (`from .. import rotinas` + `rotinas.marcar("operacoes", resultado)`, que nunca
   levanta). A lógica da rotina não mudou — `diff` contra `operacoes_rotina.py.bak_2026-10-16_log` são 6
   linhas, todas do carimbo — e as suítes da aba ficaram verdes (tela 62, ponta a ponta 35, f1–f6 412).
   O `sha256sum` de referência passa a ser o de depois de 16/10.
2. 🚨 **Não se inventa identificador.** Placa inventada é pior que placa faltando. Em 14/10 a primeira passada
   da carga inseriu a **linha descritiva do veículo** como se fosse placa, e anulou o identificador certo —
   foi revertida pelo livro-razão, e a guarda entrou com as linhas reais como fixture.
3. 🚨 **Tela que mente é defeito**, inclusive por omissão: número sem dizer de onde vem, contador que esconde
   "não existe", coluna chamada "Em uso" quando mede presença. Os três aconteceram nesta sprint.
4. **Rotina nasce desligada, com interruptor na própria tela** (convenção do FPSL, oposta à do MoviZap) — a
   `FIN_1.1` ficou desligada de 02 a 08/10 e nada na tela dizia.
5. **Nenhuma escrita no Harmonit, na WESO ou na Clicksign.** A CTR compara e aponta.
6. **Cache velho não decide.** Acima de 48 h a rotina se recusa a comparar e **diz por quê**; a tela avisa
   quando o dado pode estar desatualizado.
7. **Publicar exige a palavra dele.** Editar local, rodar as suítes, subir e reiniciar só com autorização.
8. **O FPSL deixa rastro desde 16/10** (item 3). Antes disso não havia handler de log: o `resync-os` logava
   toda passada e **nunca deixou uma linha**, e a `logs/requests.log` está vazia desde 17/06 (o `log_req` só
   cobre `/weso/*`, que ninguém chama — aposentar ou estender é decisão dele).
   - **`/home/claude/logs/fpsl.log`**: `RotatingFileHandler` 10 MB × 5, rotação **dentro do processo** (o
     `claude-logs` não casa com o nome; dois rotacionadores brigariam pelo inode), pendurado nas raízes
     `fpsl` e `fpsl_weso`, com `MascararSegredoDaQueryString` — a chave da WESO viaja na query string. Os
     loggers do uvicorn **não** foram tocados: seguem no journal.
   - **`fpsl_weso/rotinas.py`**: os **8 laços** (inadimplência, scan-os, resync-os, operações, conferência,
     auditoria de contratos, técnicos, cartões) carimbam `rotina_<nome>_ultima_em` e `_resultado` em
     `config` **a cada passada**, inclusive a que não fez nada e a que viu a rotina desligada — *laço vivo
     com rotina desligada* não é *laço morto*. `marcar()` nunca levanta.
   - **Telas com interruptor** (`FIN_1.1` e auditoria de contratos): "Última passada: ... — resultado", com
     três estados — recente, **ATRASADA** (dobro do intervalo) e **sem registro** (serviço recém-subido,
     não é atraso).
   - **`scripts/rotinas_mudas.py`** — **só relata**, sem WhatsApp. Cron `10 18 * * *` →
     `logs/fpsl_rotinas_mudas.log`. Uma semana em arquivo; depois ele decide se vira aviso. Resumo diz
     número: *"8 laços: 6 em dia, 0 mudos, 2 sem registro"*.
   - **`tests/teste_rotinas.py`**: 28 verificações, em banco temporário.

---

## 9. Onde está cada coisa

| Assunto | Onde |
|---|---|
| A aba de Contratos, do C0 ao D4, com todos os achados | `docs/fpsl/31_Gestao_Contratos.md` |
| Contas a Receber | `docs/fpsl/32_Contas_a_Receber.md` (**a escrever**) |
| Painel Financeiro (FIN_1.1 e FIN_2.1 — pagar técnico) | `docs/fpsl/30_Painel_Financeiro.md` |
| Metodologia e o ciclo de entrega | `docs/fpsl/00_Metodologia.md` |
| Log do FPSL e a última passada de cada rotina (16/10) | `/home/claude/logs/fpsl.log` · `venv/bin/python scripts/rotinas_mudas.py` · trava 8 acima |
| A auditoria que originou tudo | `C:\code\termos_harmonit` (README com as regras dele) e `Downloads\Termos Harmonit por Cliente` |
| O miolo vivo, com o estado do dia e as pendências | `C:\Users\Lenovo\Proximos_Passos.md` |

---

## 10. O desenho do cruzamento, em uma figura

```
                    CLIENTE  (contrato_cliente: cnpj, nome, nome_fonte)
                       |
                       |  1..n
                       v
   DOCUMENTO  ----> TERMO  (contrato_termo: numero, empresa, assinado, hash, arquivo)
   (PDF assinado,      |
    guardado pelo      |  gera 1..n
    hash)              v
                    EVENTO  (contrato_evento: ENTRA | SAI | RESCINDE | UPGRADE | ANULA)
                       |            IMUTAVEL — corrigir e acrescentar, apontando `corrige_evento_id`
                       |
         +-------------+--------------+
         |                            |
         v                            v
      PLACA                         ITEM
 (contrato_placa:              (contrato_item: valor_mensal,
  situacao, base,               inicio, fim, recursos)
  termo_vigente)                        |
         |   DERIVADA                   |  e daqui que a CAR le
         |                              v
         |                      [ CAR_1.1 ]  competencia do mes
         |
         |  cruzamento com o mundo real
         v
   WESO (cache 04:15)  ->  esta instalada?  ->  rastreador  ->  chip
   HARMONIT            ->  o que foi faturado?   (ainda nao lido)
```

**Como se lê a figura, nos dois sentidos:**

- **de placa até termo:** `contrato_placa.termo_vigente` dá o termo que a sustenta **hoje**, e os eventos
  dela, em ordem de número de termo, dão a **cadeia inteira** — "contrato 255 → aditivo 2224 → rescisão
  8904". Derivável hoje para **3.811** placas.
- **de termo até placa:** os eventos do termo, e cada um diz a **fonte** (assinado · harmonit · weso) e,
  quando houve correção, qual evento ele anula.
- **de placa até equipamento:** existe na WESO (**1.924** veículos com rastreador, **3.099** rastreadores com
  chip) e **ainda não** dentro do contrato — é a junção que falta.
- **de contrato até dinheiro:** pelo `contrato_item`, que hoje tem **1** valor em 6.463.

---

## 11. O que "sinal vivo" quer dizer aqui — e o que ele NÃO pode ser

**É:** o estado sai do evento e muda sozinho quando o mundo anda. A placa não é "atualizada"; ela é
recalculada. O aviso prévio de 90 dias vence pelo calendário, sem ninguém mexer. A rescisão sem assinatura
passa a valer no dia em que a placa some da WESO. **A cobrança de um mês é uma leitura do contrato naquele
mês**, com o documento atrás.

**Não pode ser:** um cadastro paralelo de recebíveis, alimentado por cópia. Recebível copiado congela, e no
mês seguinte ninguém sabe dizer por que aquele valor está lá — que é exatamente o problema que esta frente
existe para consertar, só que com outro nome.

🚨 **A condição para ligar o sinal na cobrança é a base merecer confiança.** Os três números que medem isso,
em 14/10: **5** termos com PDF (de 4.599), **1** item com valor (de 6.463), **0** eventos com recursos
(de 12.132). Enquanto estiverem assim, emitir cobrança seria faturar em cima da lista do Harmonit — o
oposto da regra dele de 14/10.

---

## 12. Como saber se o projeto está avançando

Três réguas, e nenhuma delas mede esforço:

| Régua | Hoje (14/10) | O que ela responde |
|---|---|---|
| **% das placas em uso com documento assinado guardado** | perto de zero (1.643 em uso × 5 termos com PDF) | a base é confiável? |
| **% dos termos nascidos dentro do FPSL** | 0 — todos nascem no Harmonit | a conciliação converge, ou é esteira? |
| **achados da auditoria** | 2.422 | o contrato e o mundo real estão se aproximando? |

⚠️ A terceira sozinha engana: ela cai quando o problema é resolvido **e** quando a regra é afrouxada. Por
isso ela vem acompanhada das outras duas.

---

## 13. Para quem chegar aqui amanhã

1. Leia este arquivo e o **`31_Gestao_Contratos.md`** — o 31 tem o detalhe de cada etapa, com os achados e os
   defeitos que a construção produziu e consertou.
2. **Não confie em número desta página.** Meça: `sqlite3 -readonly data/fpsl.db`, a suíte, e o `Proximos_Passos`.
3. **Antes de mexer em regra, leia a seção 4.** Cada linha ali é decisão dele, com a data — e o que não está
   lá é sugestão minha, que não vale como regra.
4. **O erro mais caro deste projeto não é bug: é afirmar além do dado.** Em 14/10 foram cinco em um dia —
   "Em uso" medindo presença, "sem dado da WESO" culpando o cache, 549 virando 246, a lista do Harmonit
   herdando assinatura, e um contador calado. Nenhum derrubou o sistema; todos teriam feito alguém decidir
   errado.
