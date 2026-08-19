# Registro de telas — FPSL

**Data:** 2026-08-17 · **Fonte:** `fpsl_weso/painel/telas.py` · **Tela:** CFG_9.1

Fonte única de **navegação, permissão e auditoria**. Espelha o contrato do
`movizap/telas.py`, em produção desde 12/08.

---

## A regra que sustenta tudo

🚨 **O código é imutável e NUNCA é reaproveitado.**

Título, rota e arquivo podem mudar; código não. Código aposentado não volta —
reusar faria o **log antigo mentir**: um `CAD_1.1` gravado em agosto apontaria
para outra tela em novembro, e nenhuma auditoria sobreviveria a isso.

As demais, que não mudam:

- tela que não está no registro **não existe**: rota sem código não sobe;
- o owner enxerga tudo, independente do que estiver gravado;
- conta nova nasce **sem nenhuma tela** — falha fechado.

---

## O estado hoje

**11 ativas · 2 reservadas · fase 1**

| Código | Tela | Permissão | Menu |
|---|---|---|---|
| `CAD_1.1` | Cadastro de Placas | `cadastro_placas` | sim |
| `CAD_1.2` | Histórico de Cadastros | `cadastro_placas` | não |
| `OSG_1.1` | Gerar OS | `gerar_os` | sim |
| `OSG_2.1` | Vínculos | `vinculos` | sim |
| `HST_1.1` | Histórico de OS | `os_historico` | sim |
| `HST_2.1` | Serviços Harmonit | `harmonit_historico` | sim |
| `CFG_1.1` | Configurações | `config` (só owner) | sim |
| `CFG_2.1` | Usuários | `usuarios` (só owner) | sim |
| `CFG_9.1` | Registro de telas | `config` (só owner) | sim |
| `DMD_1.1` | Demandas — esteira | **pública** | não |
| `DMD_1.2` | Demandas — planilha | **pública** | não |

**Reservada:** `REL_1.1` Relatórios (fase 3).

🚨 **`HST_3.1` (Aderência) foi APAGADA em 19/08 e o código fica queimado.** Ela
comparava Harmonit × WESO para mostrar "o que diverge", e a premissa estava
errada: os dois sistemas têm trabalhos diferentes e **divergir é o estado
normal** — veículo do cliente sem rastreador só existe no Harmonit; recipiente
de bancada e equipamento em estoque só existem na WESO. A pergunta estreita que
de fato tem dono ("o par que o FPSL escreveu nasceu dos dois lados?") já é
respondida pelo `cadastro_placas_log`.

⚠️ **Ela nunca foi pedida** — foi proposta minha em 17/08, com uma justificativa
que eu mesmo escrevi no código. Reservar tela sem demanda queima código de tela
e devolve pendência inventada para a mesa do usuário.

### As decisões por trás dos códigos

**`CAD_1.1` é a primeira da lista de propósito.** É a ordem do trabalho real: o
termo assinado vira placa e só depois vira OS. A sidebar segue esta ordem, e o
login manda para a primeira tela **do perfil** de quem entrou.

**Vínculos é `OSG_2.1`, não módulo próprio.** Ele existe *para* a geração de OS
— é o de-para entre o texto do contrato e o produto do Harmonit. Sozinho não
serve a nada.

**`CAD_1.2` compartilha a permissão da `CAD_1.1`.** Quem cadastra precisa ver o
que cadastrou; uma permissão separada para "ver o que eu mesmo fiz" seria
burocracia sem dono.

**`CFG_9.1` tem o mesmo código no MoviZap**, e a mesma função. Dois sistemas, um
vocabulário: quem entende o registro de um entende o do outro.

**As de demandas são públicas e estão no registro assim mesmo.** O registro
promete ser fonte *única* — tela de fora faria a promessa mentir. `permissao:
None` as mantém fora da navegação e da trava, e `no_menu` fora do menu. As duas
são o mesmo motor em vistas diferentes, mas são duas telas para quem olha, e é
isso que o log registra.

---

## Códigos aposentados

Nunca voltam. A lista existe para ninguém "redescobrir" um número livre daqui a
três meses.

**`PLC_1.1`** — seria a tela de placas de julho: cadastro avulso, desligado de
qualquer fluxo. Morreu em 14/08 (`cf16837`) por ser **permissão que não protegia
nada** — as rotas dela exigiam `gerar_os`, então quem recebia "Placas" via o
link e não conseguia usar, e quem tinha "Gerar OS" criava placa sem ter recebido
a permissão. Nunca teve código, e nunca terá.

⚠️ **O Cadastro de Placas (`CAD_1.1`) é outra coisa.** Nasce do termo, tem id
próprio, e as rotas exigem esse id — que é exatamente o que faltava na outra.

**`OFC_1.1`** — seria a tela de sincronização Oficina → WESO. Removida em 17/08
com o fluxo inteiro: a tabela tinha **zero linhas em toda a vida do sistema**, o
endpoint nunca foi chamado em 30 dias, e o interruptor estava `false` desde
16/07. A documentação dela fica, porque serve para rescisão.

---

## Permissão: o que mudou e o que não

🚨 **Os ids de permissão NÃO mudaram na adoção do registro.** São os mesmos que
já estão gravados em `painel_usuarios.abas` e os mesmos das 25 chamadas de
`requer_aba`. Mudar exigiria migrar a coluna de todas as contas *e* reescrever
as chamadas, e nenhuma das duas coisas melhora nada.

**O que o registro acrescenta é o CÓDIGO**, que a permissão não tinha.

`abas.py` **deixou de ser fonte** e virou tradução: ele deriva de `telas.py` e
não tem lista própria. Há teste que reprova se ele voltar a declarar `ABAS` como
literal — duas listas seria exatamente o problema que o registro resolve.

⚠️ **Uma permissão pode ter mais de uma tela.** `cadastro_placas` tem `CAD_1.1`
e `CAD_1.2`. Por isso o modal de perfil concede **permissão**, não tela:
oferecer tela a tela sugeriria que dá para dar o histórico sem dar o cadastro, e
não dá.

### Só do owner

`config` e `usuarios`. Quem tem essas telas liga a escrita real na WESO e cria
contas, e isso não se delega (decisão do usuário, 27/07). Elas não aparecem no
modal de perfil e `normalizar` as descarta silenciosamente se vierem do
formulário.

---

## O teste, e o que ele impede

`tests/teste_registro_telas.py` — **39 verificações**.

| O que prende | O estrago que evita |
|---|---|
| código único, e nenhum colide com aposentado | log antigo passar a apontar para outra tela |
| `abas.py` sem lista própria | duas fontes divergindo |
| toda permissão é exigida por alguma rota | permissão de mentira — o que matou a `PLC_1.1` |
| reservada não sobe | tela de fase futura aparecendo antes da hora |
| só-owner não é concedível | delegar o que liga escrita na WESO |
| conta nova com menu vazio | falhar aberto |
| toda tela ativa responde | rota registrada que não existe |

⚠️ **A unidade dos contadores mudou em 17/08.** `teste_perfis` e
`teste_roteadores_painel` contavam **abas** (permissões) e passaram a contar
**telas** (códigos). O owner vê **8** no menu: as 7 de antes mais a `CFG_9.1`. A
`CAD_1.2` não entra porque é `no_menu`.

---

## Tela nova mexe em TRÊS lugares

1. **`telas.py`** — o código, imutável, com módulo e fase.
2. **A rota** — página em `main.py` e as rotas de API exigindo a permissão.
3. **Este documento**.

Faltando qualquer um, o teste reprova. Foi assim que o MoviZap parou de ter tela
órfã, e é a mesma regra aqui.
