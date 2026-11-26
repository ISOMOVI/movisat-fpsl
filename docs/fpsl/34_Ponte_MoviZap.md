# A ponte de OS com o MoviZap — as 10 rotas

> **Escrito em 29/10/2026**, por um achado da auditoria dele: *"auditou e
> validou o entregue? as rotas?"*. **A ponte existe desde 21/10 e nunca teve
> seção de rotas em `docs/fpsl/`** — nem as 8 de então, nem as 2 de hoje. O
> `10_Inconsistencias.md` a citava de passagem e nada mais.

---

## 0. O que esta ponte é, e por que ela existe

🔵 **Decisão 8 dele (19/10):** *"o FPSL expõe endpoint de OS e o MoviZap consome
pelo `FPSL_BASE_URL`"*.

As OS vivem **aqui**, em SQLite (`os_historico`, varrida do Harmonit a cada
5 min pelo `os_scan_router`); o MoviZap é Postgres. Até 21/10 nenhum dos dois
consultava o outro.

🚨 **A CHAVE DO CRUZAMENTO É O `harmonit_id`**, e nenhum campo novo de
identidade foi criado: `os_historico.cliente_id` é o id do cliente no Harmonit,
e o MoviZap tem o mesmo número em `cliente.harmonit_id` (text).

🚨 **O MOVIZAP NÃO TEM CREDENCIAL DO HARMONIT, de propósito.** Toda escrita no
ERP passa por aqui. Dar uma credencial a ele seria um segundo lugar para
rotacionar.

---

## 1. 🚨 A autenticação: `X-Ponte-Key`, e não sessão

**Estas rotas não usam `requer_aba`.** Toda rota do painel exige sessão de
pessoa (cookie), e **chamada servidor-a-servidor não tem cookie** — medido em
21/10, antes de escrever.

O que as protege é o segredo **`PONTE_FPSL_SEGREDO`**, que vive nos **dois**
`.env` e é comparado em tempo constante (`hmac.compare_digest`), como a
`verificar_chave` da API WESO faz desde a auditoria de 15/07.

| situação | resposta |
|---|---|
| sem o cabeçalho | **422** (o header é obrigatório) |
| cabeçalho errado | **401** |

🚨 **ESTE SEGREDO É A ÚNICA COISA entre quem alcança a porta e a CRIAÇÃO DE OS
NO ERP**, desde 29/10. Antes disso a pior consequência de um vazamento era
leitura e escrita de endereço; agora é abrir OS. ⚠️ Os dois `.env` têm de
andar juntos: desencontro responde 401 e a mensagem da ponte diz isso por
extenso (*"os dois .env estão iguais?"*).

---

## 2. As 10 rotas, prefixo `/api/os`

### Leitura

| rota | o que devolve | nasceu |
|---|---|---|
| `GET /por-cliente` | as OS de um cliente nos últimos N meses | 21/10 |
| `GET /clientes-com-os` | `harmonit_id` → quantas OS em aberto | 21/10 |
| `GET /placas-ativas` | a frota ativa do cliente, da WESO | 29/10 |
| `GET /tecnico-por-telefone` | o cadastro do técnico pelo telefone | 21/10 |
| `GET /tecnicos` | a lista de técnicos | 21/10 |
| `GET /endereco` | o endereço estruturado da OS, ao vivo | 21/10 |
| `GET /por-situacao` | **as OS por situação, desde uma data** | **29/10** |

### Escrita (as três que gravam no ERP)

| rota | o que grava | nasceu |
|---|---|---|
| `POST /placas-ativas/conferir` | nada — confere placa contra a WESO | 29/10 |
| `POST /agendar-tecnico` | cria o compromisso na OS | 21/10 |
| `POST /endereco` | **a OS inteira**, com só o endereço trocado | 21/10 |
| `POST /criar` | **cria a OS de análise do chamado** | **29/10** |
| `POST /situacao` | **move a OS de etapa** — escreve `situacaoId` | **29/10** |

---

## 3. `POST /criar` — a OS do chamado

🔵 **Decisão D4 dele (29/10):** *"todo chamado de suporte abrirá uma OS"*.

**Entrada** — nada de catálogo tem valor-padrão, e isso é de propósito: um
padrão aqui faria a ponte decidir regra de negócio que é do MoviZap (o `tipoId`
vem da **origem** do chamado, e a origem este lado não conhece).

| campo | obrigatório |
|---|---|
| `cliente_id` · `tipo_id` · `problema_id` · `situacao_id` · `prioridade_id` · `descricao` | **sim** |
| `produto_servico_id` · `empresa_id` (98) · `local_servico_id` (1) · `conferir` | não |

**Resposta:** `{ok, criada, numero_os, os_id, situacao_id, cliente_id, divergencias}`.

🚨 **`criada` TEM TRÊS VALORES, e o terceiro é o que importa:**

| `criada` | significa | o que quem chama faz |
|---|---|---|
| `true` | nasceu | guarda o número |
| `false` | não nasceu | pode tentar de novo |
| **`null`** | **não se sabe** — o Harmonit aceitou e não disse o número | **NÃO tenta de novo**, ou nascem duas |

⚠️ **Timeout da ponte cai em `null`** do lado do MoviZap: *"não respondeu no
tempo"* **não** quer dizer *"não gravou"*.

🚨 **A PROVA É RELER.** A rota grava, relê a OS pelo número e compara **5
campos** com o que foi pedido (`tipo`, `problema`, `situacaoId`, `prioridade`,
`parceiro`). Diferença vira `divergencias`, por extenso — e o número é
devolvido **de qualquer forma**, porque OS criada sem registro do nosso lado é
OS órfã no ERP.

⚠️ **`conferir: true` é ensaio a seco:** monta o corpo, devolve e **não
escreve**.

### O que foi medido com escrita real (OS 17056, 29/10)

`SalvarOrdemServico` com `id: 0` **devolve** `numeroOrdem` e `ordemServicoId` —
a doc deles documenta isso para a rota **básica**, não para a completa. E
`status = 2` ("Nova"), não o `1` do exemplo da doc: medido em 302 OS do cache.

---

## 4. `GET /por-situacao` — as OS do painel

🔵 **D8:** o card é a OS, de qualquer origem. 🔵 **D9:** a data matriz é
**24/10/2026** e só o owner a muda (quem cobra isso é o MoviZap).

| parâmetro | padrão |
|---|---|
| `desde` (aaaa-mm-dd) | **obrigatório**, sem padrão — um padrão aqui esconderia a D9 dentro desta rota |
| `so_abertas` | `1` |
| `teto` | 600 (1–3000) |

⚠️ **`data_previsao` É TEXTO `dd/mm/aaaa HH:MM:SS`**, e o corte usa o
`_PREVISAO_ISO`: `date()` devolve **zero linha** nesse formato — custou um plano
inteiro em 19/10.

🚨 **E O CORTE POR `dataPrevisao` TEM PRAZO DE VALIDADE.** Medido em 29/10: ela
é a data de criação em 12 de 12 OS conferidas — **mas a frente do aviso prévio
vai movê-la em +90 dias**. Nesse dia o filtro deixa de significar "criada
desde", **sem erro e sem aviso**. Quem mexer no aviso prévio volta aqui.

🚨 **`0` e `NULL` saem SEPARADOS** (`situacao_zero`, `sem_situacao`): `0` é "o
ERP gravou zero" e `NULL` é "a varredura não leu". Já custou uma coluna inteira
em 22/10.

⚠️ **A OS excluída nunca entra**, com interruptor ou sem: excluída no ERP não é
"fechada", é inexistente.

⚠️ **`so_abertas` NÃO zera o Financeiro** — medido em 29/10: 6 → **2**, não
→ 0. O plano da manhã dizia que zerava.

⚠️ **As 17 situações estão COPIADAS aqui** (`_SITUACOES_DO_PAINEL`), e a fonte é
o `movizap/paineis.py`. Há trava para a cópia não apodrecer calada; se
divergirem, quem manda é o MoviZap, e o sintoma é `tem_coluna` errado — não card
perdido, porque quem monta o quadro reconfere pela tupla dele.


---

## 4b. `POST /situacao` — mover a OS de etapa (Bloco D)

🔵 É o motivo que ele deu para o painel existir (22/10): *"hoje ainda não usamos
a situação da OS, por isso o painel e consulta para atualizar a situação no
painel"*. E a ordem é **livre**, por decisão dele em 29/10: *"que tal de caminho
proibido é esse??"* — **esta rota não valida transição**, e o Harmonit também
não (medido: de ""Atendimento finalizado" (situação 15694, renomeada em 29/10)" para "Agendamento" e ele aceitou).

| campo | o que faz |
|---|---|
| `numero_os` · `situacao_id` | obrigatórios |
| `situacao_esperada` | 🚨 **a trava de concorrência**: a situação que a TELA tinha. Se o ERP já estiver em outra, a rota **recusa** com `conflito: true` e **não escreve**. ⚠️ Nulo é legítimo (a OS não tinha situação) |
| `conferir_antes` | `true`. Desligar é escrever por cima do que outra pessoa fez |

**Resposta:** `{ok, gravou, numero_os, de, para, mudou, fora_da_situacao}`.

🚨 **`gravou` TEM TRÊS VALORES**, e o terceiro foi um defeito meu pego na prova
de ponta a ponta:

| `gravou` | significa |
|---|---|
| `true` | a releitura confirmou a situação nova |
| `false` | não gravou — e a mensagem diz se **pode tentar de novo** |
| **`null`** | **a escrita foi ENVIADA e aceita, e a releitura falhou**: não se sabe se mudou. Confira à mão e **não tente de novo às cegas** |

⚠️ **As duas leituras estavam sem guarda até 29/10 à noite.** A prova falhou
duas vezes com um 502 do Harmonit vindo de uma leitura sem `try`, e a chamada
direta da mesma função moveu a OS no mesmo minuto. Nas duas vezes a OS **não**
moveu (conferido no ERP) — o `gravou: false` foi honesto **por sorte, não por
desenho**.

🚨 **E ESTA ROTA ATUALIZA O CACHE**, diferente da do endereço: o card vem da
`os_historico`, varrida a cada 5 min. Sem isso, movido o card ele **voltaria
para a coluna antiga** por até 5 minutos e a pessoa moveria de novo. ⚠️ O cache
só é escrito **depois** de a releitura confirmar.

⚠️ **O registro de quem moveu fica do lado do MoviZap** (`os_passagem`, migração
083), não aqui: 🔵 *"deve ter o log de quem faz o que SEMPRE"*, e quem conhece o
atendente é o MoviZap. Esta rota não sabe quem está movendo — de propósito.
---

## 5. 🚨 A armadilha central da escrita: os nomes não batem

**Não existe "atualizar só um campo".** A única rota de escrita de OS é
`SalvarOrdemServico`, que a doc deles chama de *"criar/atualizar OS completa"*:
manda-se a OS inteira, e **o que não for mandado se perde**.

E os nomes de leitura e de escrita são diferentes (medido na OS 16991, 21/10):

| leitura | escrita |
|---|---|
| `tipo` | `tipoId` |
| `localServico` | `localServicoId` |
| `prioridade` | `prioridadeId` |
| `problema` | `problemaId` |
| `produtoId` | `produtoServicoId` |
| `descricao` | `descricaoDetalhada` |
| `dataPrevisao` (`dd/mm/aaaa HH:MM:SS`) | `dataPrevisaoEntrega` (ISO) |
| **`parceiro`** | **`clienteId`** |

⚠️ **`checkList`, `materiais`, `oficina` e `tecnico` são LISTAS e não entram no
corpo da escrita** — cada uma tem rota própria, e elas **sobrevivem** a um save
da OS (medido). Entram na conferência de depois: se uma lista encurtar por
causa de uma escrita, isso grita.

---

## 5-B. 🔵 O TERMO da OS (Área E, 05/11)

🚨 **O TERMO NÃO É CAMPO DA OS NO HARMONIT.** Ele só existe **dentro do texto**
da `descricao`, e `descricao` **não está no cache** `os_historico` — vem ao
vivo, uma chamada por OS. Procurar uma OS pelo termo lendo ficha a ficha
custaria **uma leitura do ERP por card do painel**.

**O caminho:** coluna `os_historico.termo` (TEXT), preenchida pela varredura
que **já lê a OS inteira** — ela tinha a `descricao` na mão e não gravava nada
dela. A extração vive em `fpsl_weso/termo_da_os.py`, com a medição que a
desenhou. A rota `GET /api/os/por-situacao` devolve `termo` em cada OS.

📏 **A medição (200 OS lidas ao vivo em 05/11):** 173 com termo · 27 sem ·
**0** descrições com mais de um termo distinto · **0** com a palavra `TERMO`
sem número ao lado. Os formatos reais:

```
FINANCEIRO — TERMO 8937 | placas: DMD 0324, ...
Retirada: BUS 0168 | ... | TERMO 8937 | O.S: 17081
SUBSTITUIÇÃO INSTALAÇÃO: A_DEFINIR_2_8927 | TERMO:8927 | ... | TERMO 8927
RESSARCIMENTO: TERMO 8924 | placas: TKZ 6A06 | O.S: 17025
```

⚠️ **OS SEM TERMO É NORMAL, não é falha** — venda, compra de cartão RFID,
entrega de chaveiro e manutenção não nascem de termo. O card do MoviZap escreve
só o número da OS; não existe *"sem termo"* escrito em tela.

🚨 **Dois termos distintos na mesma descrição devolvem `None`**, de propósito:
o caso não existe em nenhuma das 200 medidas, então é desconhecido — e escolher
o primeiro calado poria no card um termo que pode ser o errado.

🚨 **O NÚMERO É EXIGIDO** (`\d{1,10}`, não `\S+`): com `\S+`, `TERMO DE ADESÃO`
viraria o termo chamado *DE*.

**A carga inicial** é à mão, uma vez: `scripts/termo_das_os.py` — por padrão só
relata, `--um` faz uma, `--aplicar` o lote; **só toca linha com `termo IS
NULL`**, então a segunda rodada não muda nada. Medido em 05/11: **493 das 603**
OS do cache ficaram com termo, **109 não têm termo nenhum** e **1** (a 16576) o
ERP já não encontra — está no cache como não excluída e o `resync` não a
alcança, porque a janela dele é recente. ⚠️ Isso é achado de dado, **não** foi
tocado.

---

## 6. As travas

| arquivo | o que mede | quantas |
|---|---|---|
| `tests/teste_ponte_movizap.py` | as consultas da ponte | 26 |
| `tests/teste_endereco_ponte.py` | a escrita de endereço e o 2º vínculo | 20 |
| `tests/teste_criar_os_ponte.py` | o corpo da criação e o das OS por situação | 35 |
| `tests/teste_ponte_rotas_http.py` | **as rotas, por HTTP** — a chave, os códigos, a validação | **25** |
| `tests/teste_termo_da_os.py` | a extração do termo e a coluna no cache | **17** |

⚠️ **O projeto do FPSL não coleta teste por padrão** — rodar pelo nome:

```
venv/bin/python -m pytest tests/teste_ponte_movizap.py \
    tests/teste_endereco_ponte.py tests/teste_criar_os_ponte.py \
    tests/teste_ponte_rotas_http.py
```

🚨 **O `teste_ponte_rotas_http.py` nasceu da auditoria dele de 29/10**: as duas
rotas novas tinham teste de função e **nenhum teste de rota**. Testar a função
não exercita a chave da ponte, o código de estado nem a validação do corpo — e
`py_compile` não pega import faltando, o que no mesmo dia derrubou o MoviZap por
13 segundos.

---

## 7. Onde está cada peça

| peça | arquivo |
|---|---|
| as 10 rotas | `fpsl_weso/routers/os_ponte.py` |
| o cliente do Harmonit | `fpsl_weso/harmonit_client.py` |
| o cache de OS e a varredura | `fpsl_weso/painel/routers/os_scan_router.py` |
| o dicionário de tipos de OS | `fpsl_weso/services/sync_tipos_os.py` |
| o lado do MoviZap | `movizap/fpsl_ponte.py` |
| a prova de criação no ERP (cria e apaga) | `provar_criacao_os.py` |
| o plano da frente | `movizap_painel/docs/16_Pipeline_da_Operacao.md` |

## 🚨 19/11 — A ESCRITA PERDIDA: `ok = true` sem o ERP ter ficado no valor

🔵 Ele, vendo o status errado na Operação: *"OS 17137 erro de leitura FPSL com o
status no OP, não haviamos resolvido isso já??????"* · depois:
*"valide ambos e traga situação"*.

⚠️ **Isto registra uma MEDIÇÃO, não um conserto.** Nada foi alterado: os dois
passos de ação (a varredura das escritas de 18–19/11 e o cron da fila) estão
**segurados por decisão dele** em 19/11.

### A validação das três fontes, 19/11 ~15:20

| fonte | situação da OS 17137 |
|---|---|
| nosso cache (`os_historico`) | **251** |
| ficha ao vivo do ERP (3 leituras: 0,64 s · 0,21 s · 0,20 s) | **251** |
| a coluna em que o card está, e que a tela mandou no `/checklist` | **16488** |

📏 **E uma sonda de 25 OS, duas rodadas com 35 s de intervalo, 50 leituras:**
**zero** discordância entre cache e ERP, **zero** mudança de resposta entre as
rodadas, **zero** falha.

🚨 **Conclusão que corrige a minha anterior: NÃO é a leitura que atrasa.** A
leitura do ERP está sólida. O que está errado é a **escrita**.

### A `os_passagem` da 17137, hora por hora

| hora | de → para | quem | resultado |
|---|---|---|---|
| 14:48:47 | 38 → **251** | 123 | `ok = true` |
| 14:50:42 | 251 → **16488** | 62440 | `ok = true` |
| 15:01:52 | 251 → 1316 | 123 | **`ok = false`** → foi para a **fila** |

**Aplicando a régua de 18/11** (*o valor que o ERP mostra é um que NÓS
escrevemos?*): o ERP está em **251**; 251 **é nosso**, escrito às 14:48:47; e é
**mais velho** que o 16488 de 14:50:42. Logo — **nosso + velho = ESCRITA
PERDIDA**. A passagem para 16488 foi marcada `ok = true` e **não ficou no
Harmonit**.

### Os três defeitos que isto expõe

1. 🚨 **A confirmação de escrita é falsa.** O `ok` diz que **o POST não deu
   erro** — não que o ERP ficou no valor. **Confirmar sem reler é confirmar
   nada.** 📏 Em 19/11 houve **6 passagens `ok = true`**, e não se sabe quantas
   pegaram.
2. 🚨 **A FILA NÃO TEM QUEM A PROCESSE.** 📏 `resolvida_em IS NOT NULL` =
   **zero em toda a história da tabela**. A passagem de 15:01:52 está lá com
   **0 tentativas** e vai ficar: o cron da fila nunca foi criado. **Tudo que
   entra na fila morre nela**, e quem moveu o card não é avisado.
3. 🚨 **A tela mostra a coluna da última passagem `ok = true`**, que pode não
   ser o ERP. Foi por isso que a Operação exibiu 16488 com o ERP em 251.

### ⚠️ O que FUNCIONOU, e precisa ficar escrito

A trava de 18/11 **pegou** a terceira passagem: recusou em vez de atropelar,
registrou `ok = false`, pôs na fila e escreveu a frase certa ao operador —

> *"a OS 17137 está em 'Configurar equipamentos e Sistemas' no Harmonit, e a
> tela carregou 'Entrega de materiais prontos'. Alguém mudou no meio —
> recarregue o painel antes de mover"*

O diagnóstico de 18/11 estava certo. **O que ficou pela metade foi a fila sem
processador e a confirmação sem verificação.**

### O erro da ficha não deixa rastro

📏 Quatro `502` em 19/11, **todos** na ficha da OS 17137 — 14:41:02, 14:41:29,
14:59:45 e 15:00:48 — e **zero linha no log**. A causa é o `except Exception` do
`_ficha_da_os`, que põe o erro no **corpo da resposta**
(*"não deu para ler a OS N no Harmonit agora: {e}"*) e **não registra nada**.

⚠️ **Dois dos quatro foram de restart de serviço** (14:59:45 e 15:00:48 caem na
janela do deploy da `PNL_1.6`): reiniciar derruba a ficha de quem está com um
card aberto, e não há retentativa.

🚨 **Consequência, e é a pior parte:** cada ocorrência só pode ser entendida
**reproduzindo ao vivo**. Foi o que se fez aqui. Enquanto o `except` não
registrar a causa, nenhum 502 da ficha é diagnosticável depois do fato.

---

## 25/11/2026 — o cron da varredura, o carimbo e o anexo do comprovante

### A varredura passou a ter hora, e a tela passou a dizer qual

🔵 24/11: *"o cron diário é quem traz o card da OS nova"*, e o corte segue pela
**data da OS**, nunca pelo nascimento do card.

`scripts/varrer_pagamento.py` + a linha `10 5 * * *` no `crontab` do usuário
`claude` (cópia das 79 linhas anteriores em
`/home/claude/crontab_copia_2026-11-25_antes_do_pagamento.txt`).

🚨 **O HORÁRIO É A PARTE QUE IMPORTA, NÃO O CRON.** A varredura lê
`os_historico`, que o **cache WESO escreve às 04:15** e o **Harmonit às 04:50**.
Rodar antes varreria o cache de ONTEM; rodar em cima disputaria escrita no mesmo
SQLite. **05:10 fica depois dos dois.**

🟡 **`horas=None`, decisão minha declarada:** o padrão `horas=24` filtra por
`atualizado_em`, então um dia de cron falho esconderia aquele serviço **para
sempre**. Varrer o cache inteiro custa uma passada em ~650 linhas e
`ja_existiam` protege o que já andou — artefato que já andou **não é
sobrescrito** (o operador pode já ter dado ciente, anexado comprovante ou
devolvido).

⚠️ O `cd` e o `venv/bin/python` na linha do cron não são decoração: fora de
`/home/claude/fpsl_weso` o `settings` estoura com `ValidationError:
weso_api_key`, e com o python do MoviZap falta `pydantic_settings`.

### `pagamento_servico_varrido_em` — a linha que mata a mentira (`M12`)

A varredura **carimba o `config` dentro da mesma transação** que terminou
(`_marcar_varrido`), o `quadro` devolve `varrido_em` ao lado de `desde` e
`escondidos_pela_data`, e a tela escreve *"serviço a partir de 16/11/2026 ·
varrido hoje às 05:10"*. Rodada que estourou no meio **não** carimba — e é isso
que se quer: o quadro velho se anuncia velho.
⚠️ **Nunca varrido devolve `""`** e a tela simplesmente não escreve a parte da
hora: inventar "agora" seria a mentira que o campo nasceu para matar.

E `pagamento_servico_desde` passou a existir **explícito** no `config`
(`2026-11-16`), em vez de viver do `DESDE_PADRAO` — a lição do re-pareamento de
19/11: o valor que importa fica explícito, não implícito num default que o
próximo conserto atropela sem avisar.

### O anexo do comprovante: o arquivo é do MoviZap, a referência é do FPSL

🔵 *"haverá campo para que em cada 1 dos artefatos de pagamento seja inserido
anexo que comprove o pagamento. Após o envio do anexo, abre o campo que pede o
valor inserido no documento."* 🔵 24/11: **anexo completo, não só PDF**.

| onde | o quê |
|---|---|
| MoviZap | `POST /api/paineis/servico-dos-tecnicos/anexo/{artefato_id}` → `{id, nome_original, bytes, referencia}` · `GET .../anexo/{anexo_id}` → o arquivo, **410** quando sumiu do disco |
| MoviZap | tabela `pagamento_comprovante_arquivo` (migração 119) e a pasta `/home/claude/movizap_pagamento_comprovantes` |
| FPSL | **nada de novo**: `anexo:<id>` vai no `comprovante_arquivo TEXT` que já existe, pelo `guardar_comprovante` que já existe |

🚨 **NENHUM BYTE ATRAVESSA A PONTE.** Ela é JSON servidor-a-servidor; o arquivo
fica no lado que o serve, e o FPSL guarda só a referência de texto.

🚨 **E O ARTEFATO É CONFERIDO PELO QUADRO ANTES DE GRAVAR**: o `artefato_id` é
do SQLite do FPSL e a tabela é Postgres, logo não há FK para recusar id
inventado. A recusa é da rota — 404 "não está no quadro", 502 quando o FPSL não
respondeu.

📏 **Medido em 25/11, depois da primeira varredura em produção:** 646 OS no
cache, 619 anteriores ao corte, **27 de 16/11 em diante** — 10 com valor de
pagamento ou km (9 cards novos + 1 que já existia) e **17 sem nenhuma das duas
linhas no corpo do material**, que a varredura descarta. Das 17, **nenhuma** tem
a linha `PAGAMENTO DE TECNICO` (653939) nem `KM DESLOCAMENTO` (6971): não é
filtro da tela, é que no ERP não há valor a pagar nelas.

---

## 25/11/2026 — a OS não nasce duas vezes quando o técnico aparece depois

🔵 Ele, olhando o painel: *"OS 17131 aparece sem tecnico no painel, mas não tem
agendamento no harmonit corretamente?"* — e tinha: `agendamentoId 970805`,
início 18/11 09:00, `usuarioId 14262` (Franck), situação 15694.

🚨 **O DEFEITO ERA MEU, da varredura de 25/11 11:07.** A trava de duplicidade é
pelo par `(numero_os, tecnico_id)` e, no SQLite, **NULL não colide com nada** —
nem no `UNIQUE`. A OS 17131 entrou em 18/11 **sem técnico** (o cache ainda não o
trazia) e, quando ele apareceu, a varredura tratou como OS nova: duas linhas,
`79` sem dono e `81` com o Franck. **Cada linha é dinheiro a pagar** — duas
linhas da mesma OS em dois cards é pagar duas vezes o mesmo serviço.

**A regra que entrou, conservadora de propósito:**

| caso | o que a varredura faz |
|---|---|
| linha sem dono que **não andou** (`movimentacao`, sem lote, sem ciente, sem comprovante, sem dispensa, sem justificativa) | **ADOTA** o técnico: mesmo `id`, mesmos eventos — ela só passa a ter dono. Conta em `adotados` e grava evento `adotar_tecnico` |
| linha sem dono que **já andou** | **não é tocada E o segundo não nasce**. Conta em `conflito`, com `log.warning` nomeando a OS — duplicar dinheiro é pior que esperar alguém resolver à mão |
| OS que já tinha técnico | segue com uma linha só (`ja_existiam`) |

⚠️ `adotados` e `conflito` nascem no resumo **valendo zero**: chave que só
aparece quando acontece faz quem lê o log concluir que a versão velha está
rodando.

📏 **O estado consertado em produção, medido:** a linha `81` (a que eu criei) foi
apagada sob guarda — só se fosse ela, da OS 17131, sem lote, sem ciente, sem
comprovante e com **zero eventos** — e a varredura seguinte devolveu
`adotados=1`: a linha `79` ficou com o Franck, com o evento da adoção. O quadro
foi de 88 para **87 artefatos**, e a consulta de OS com mais de uma linha
devolve **nenhuma**.

🚨 **4 travas novas** (`tests/teste_pagamento_duplicidade.py`), vermelhas antes
reproduzindo as duas linhas: a OS não nasce duas vezes · a adoção mantém o mesmo
`id` · a terceira rodada não mexe em nada · e o que já andou não é adotado nem
duplicado.

---

## 25/11/2026 — tres rotas novas na ponte do pagamento

| rota | o que faz |
|---|---|
| GET/POST /datascope-escrita | o interruptor da ESCRITA no DataScope. Nasce DESLIGADO, e ausente = desligado |
| POST /datascope-aprovar | poe a resposta do DataScope da OS em 74341 Aprovado analise tecnica |

E o /previa e o /montar-arquivo passam a devolver **colunas** (as 14 do modelo,
na ordem lida dele): a REGRA atravessa a ponte como DADO, porque quem escreve o
.xlsx e o MoviZap e antes ele montava o cabecalho pela ordem de insercao do
primeiro dicionario -- reordenar o dicionario aqui mudaria o arquivo em silencio.

O change_state LE a resposta deles antes de escrever, porque o nosso cache NAO
guarda o form_code; e a chamada dispara os webhooks deles e manda push para o
tecnico, o que e a razao do interruptor e da modal.
