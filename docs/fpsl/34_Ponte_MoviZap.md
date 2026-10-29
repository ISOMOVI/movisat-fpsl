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
não (medido: de "Serviço Realizado" para "Agendamento" e ele aceitou).

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

## 6. As travas

| arquivo | o que mede | quantas |
|---|---|---|
| `tests/teste_ponte_movizap.py` | as consultas da ponte | 26 |
| `tests/teste_endereco_ponte.py` | a escrita de endereço e o 2º vínculo | 20 |
| `tests/teste_criar_os_ponte.py` | o corpo da criação e o das OS por situação | 35 |
| `tests/teste_ponte_rotas_http.py` | **as rotas, por HTTP** — a chave, os códigos, a validação | **25** |

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
