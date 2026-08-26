# 18 — Testes do FPSL

**Criado em 2026-07-27.** Antes disso o projeto não tinha teste automatizado nenhum:
o que existia era `test_extracao.py`, um script de 21 linhas que **imprimia JSON e não
afirmava nada** — apontando para `/tmp/testes_pdf/`, que qualquer reboot apaga. Foi
removido nesta data.

Tudo aqui é **só leitura**: nenhum teste escreve na WESO, no Harmonit, nem em produção.

---

## `tests/teste_regressao_extracao.py` — extração de termos

**45 asserções sobre os 9 documentos REAIS**, versionados em `tests/fixtures/`.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_regressao_extracao.py
```

### Por que existe

O extrator já quebrou **em silêncio** — nenhum erro, nenhum log, dado sumindo:

| Bug histórico | O que acontecia | Guarda no teste |
|---|---|---|
| Transferência roteada pro parser errado (16/07) | 14 de 28 placas sumiam; cliente nunca capturado | `[9] placas == 28` |
| Tabela em 2 colunas (16/07) | `next()` pegava só a 1ª coluna | `[2] placas == 28` |
| Continuação de página (23/07) | Rescisão lia só a 1ª página: 12 em vez de 26 | `[5] veiculos == 26` |
| Comodato × cobrar (20/07) | Item sem indicação de origem do custo | `[1] todo item tem comodato_ou_aquisicao` |
| Acessório com bullet `▶` (23/07) | Acessório não virava item de OS | `[6] acessório do bullet virou item` |
| Termo errado (rescisão que é transferência) | Gerava OS do tipo errado | `[7] alerta_transferencia` |

**Cada número travado é um bug que já aconteceu.** Não são valores arbitrários.

### Baseline (conferido a mão em 2026-07-27, não só "o que saiu")

| fixture | perfil | termo | placas | itens | observação |
|---|---|---|---|---|---|
| `cliente_novo.pdf` | cliente_novo | 8768 | 2 | 13 | FAG |
| `cliente_novo2.pdf` | cliente_novo | 8771 | 28 | 5 | 2 colunas |
| `aditivo2.pdf` | aditivo | 8782 | 1 | 8 | |
| `trz_8790_aditivo.pdf` | aditivo | 8790 | 1 | 7 | |
| `rescisao.pdf` | rescisao | 8788 | **19** | 4 | `veiculos`=26 |
| `substituicao.pdf` | substituicao | 8786 | 0 | 1 | usa `pares` |
| `termo_errado.pdf` | rescisao | 8787 | 1 | 0 | dispara alerta |
| `transferencia_existente.pdf` | transferencia | 8785 | 1 | 7 | |
| `transferencia_novo.pdf` | transferencia | 8771 | 28 | 5 | |

### Duas armadilhas de leitura (investigadas em 27/07, não são bug)

1. **Rescisão: `veiculos`=26 mas `placas`=19.** `veiculos` é a lista crua da tabela e
   inclui **7 linhas sem placa**; `placas` só as que têm (26−7=19). O teste trava os
   **dois** de propósito: se um mudar sem o outro, algo regrediu. (Ainda há 3 placas
   repetidas dentro de `veiculos` — `TTW 4C85`, `TTW 3B64`, `TUU 2I29` — que é o caso
   tratado pelo dedup na geração de OS, não erro de extração.)
2. **Substituição tem `placas`=0 e isso está certo.** Esse parser não usa `placas`: usa
   **`pares`** (`placa_saida`/`placa_entrada`/`acessorios_entrada`), porque substituição
   é sempre veículo que sai × veículo que entra.

### Quando um número mudar

**Não atualize o número para fazer passar.** Descubra primeiro se o documento mudou ou
se o extrator regrediu. `tests/dump_extracao.py` imprime o que o extrator devolve hoje,
para comparar antes de decidir.

---

## `tests/teste_perfis.py` — perfis de acesso do painel

**22 asserções**. O número de abas é travado de propósito — aba nova sem
pensar em permissão faz o teste falhar. (A aba `placas`, que entrou em
29/07, foi removida em 14/08 junto com a tela e o router.)
Owner enxerga tudo; operador só as abas marcadas; aba não concedida
dá 403; aba removida vira 403 na hora; owner não pode ser desativado. Gera o token
internamente — **nunca passa senha por linha de comando**. Cria um operador de teste e
o remove no fim. Detalhe em `17_Perfis_Acesso.md`.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_perfis.py
```

---

## `analisar_placas_weso.py` (raiz) — diagnóstico, não teste

Só leitura, sobre a base real da WESO: formato das placas (com/sem espaço × convencional
/ Mercosul / chassi), campos que o `Consultar` devolve, placas repetidas. Foi o que
fechou o **W1** e produziu o **B8** em `10_Inconsistencias.md`.

---

---

## `tests/teste_demandas.py` — o painel de demandas (14/08)

**43 verificações. TESTE DE INTEGRAÇÃO: fala HTTP com o serviço local.** Não
toca Harmonit nem WESO.

🚨 **Por que ele existe.** O painel de demandas está em uso de verdade,
compartilhado por link e **sem login**, e até 14/08 tinha zero teste. Os três
defeitos de 07/08 só apareceram porque alguém usou. Agora cada um está travado:

| Defeito de 07/08 | Guarda no teste |
|---|---|
| `pessoa_id` nulo → 422 em todo card | `[3]` card sem responsável é recusado, com código claro |
| `datetime('now')` em UTC, 3h à frente | `[5]` compara o carimbo com a hora LOCAL, e confere que local ≠ UTC |
| prazo no ano 0002, atrasado para sempre | `[4]` ano 0002 e ano 9999 recusados; a comparação de atraso é de texto |

Cobre ainda: a **esteira** (card de baixo preso até o de cima concluir), o
`CHECK` de etapa concluída sem data, o isolamento entre quadros (token de um
não alcança item de outro) e o **limitador de escrita**.

⚠️ **CRIA O PRÓPRIO QUADRO E APAGA NO FIM.** Nunca toca nos dois quadros reais.
A prova de que limpou é reler a tabela, não o retorno do `DELETE`.

🚨 **DUAS DESCOBERTAS ESCREVENDO ESTE TESTE:**

**1. Todo card nasce com uma etapa.** `criar_item` já insere uma etapa junto.
Eu tinha suposto que nascia vazio, e o teste da esteira reprovava — a esteira
estava certa, minha expectativa é que estava errada.

**2. O limitador é 60 escritas por minuto POR IP, e o teste faz ~30.** Duas
execuções seguidas no mesmo minuto estouravam o teto: o 429 na criação do card
deixava o id nulo e as chamadas seguintes viravam 422 em `/item/None` — o que
*parece* defeito de prazo e não é. O teste passou a mandar `X-Real-IP` na faixa
`203.0.113.0/24` (TEST-NET-3, RFC 5737: reservada para documentação, nunca é
gente de verdade), então não rouba a cota de ninguém nem herda a de ninguém. E
o limitador ganhou seção própria, com IP separado.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_demandas.py
```

---

## `tests/teste_roteadores_painel.py` — contrato de acesso (14/08)

**81 verificações** sobre **24 rotas** dos 8 roteadores restantes.

🚨 **Por que ele existe.** A trava de acesso é declarativa (`requer_aba(...)` no
decorador), e trava declarativa é fácil de esquecer numa rota nova: ninguém
percebe, porque a rota simplesmente funciona — para todo mundo. O teste afirma,
rota por rota: sem token → **401**; token sem a aba → **403**; token do owner →
nem um nem outro.

⚠️ **NÃO EXERCITA ROTA DE ESCRITA.** `clientes/criar` e
`oficina/resync` gravam na WESO; `os-scan/varrer` varre o Harmonit inteiro.
Dessas só se testa a tranca — abrir a porta para ver se abre estragaria dado
real. As de leitura são chamadas de verdade e têm o formato conferido.

✅ **A ÓRFÃ `placas` FOI RESOLVIDA EM 14/08 — e por remoção, não por conserto.**
A aba existia no catálogo e na barra lateral, mas rota nenhuma a exigia: o
`placas_router` sempre pediu `gerar_os`. Quem recebia só "Placas" via a aba e
**não conseguia usar**; quem tinha "Gerar OS" **criava placa na WESO sem ter
recebido "Placas"**. A aba saiu primeiro; depois, com nova autorização ("se
não usa pode tirar"), saíram também `frontend/placas.html`, a rota
`/painel/placas` e o `placas_router` inteiro — as 2 rotas de `api/placas`
deixaram a lista, e por isso a suíte caiu de 80 para **75** verificações.

🚨 **A MEDIÇÃO QUE AUTORIZOU APAGAR, para quem repetir isto:** o log do nginx
**não é legível sem root**, e `wc -l` nele devolve **0** — que parece "ninguém
usou" e não é. A prova veio do journal do próprio serviço
(`journalctl --user -u fpsl-weso.service`), onde requisição vinda pelo nginx
aparece com o **IP real** e chamada local aparece como **127.0.0.1**. De 08/08
a 14/08: **1** abertura da tela por usuário real, **zero** chamada real a
`placas/status` ou `placas/criar` — todo o resto era a suíte. Os recipientes
`-MANUT` e `-UPGRADE` nascem no sistema da WESO, não por aqui.

⚠️ **O que NÃO saiu:** o módulo `fpsl_weso/placas.py` (regra de formatação de
placa), usado por `routers/veiculos.py` e pelo onboarding, com seus 72 testes
em `tests/teste_placas.py`. Nome parecido, coisa diferente.

O conjunto de órfãs continua travado e **vazio**: se aparecer outra, é porque
nasceu permissão que não protege nada.

⚠️ Registra também que o login devolve **`access_token`**, não `token`.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_roteadores_painel.py
```

---

## `tests/teste_manutencao.py` — perfis sem termo (14/08)

**65 verificações.** Os dois perfis de manutenção, a chave do recipiente
`-MANUT` tolerante a espaço, o acento dobrado, os quatro motivos de descarte do
recipiente, a cópia `nas_duas` e as três provas da liberação da série.

Inclui um verificador que **varre o JavaScript das telas e reprova se alguma
função chamada não existir**. Ele nasceu de um defeito real: `extrair()` chamava
`renderPlacas()` e `validarEtapa2()`, que nunca existiram — clicar em "Gerar OS"
lançava `ReferenceError` e o fluxo parava antes de trocar de etapa. **`node
--check` não pega**: valida sintaxe, e a sintaxe estava correta.

---

---

## `tests/teste_higiene_placas_weso.py` — higiene da base WESO

**25 verificações. TESTE DE INTEGRAÇÃO: bate na WESO de verdade (~2,3s),
somente leitura.** Criado em 2026-07-29 como etapa 4 do plano 21.

Falha se aparecer placa com espaço nas pontas, espaço duplo ou **colisão nova**.
Também verifica que a leitura tolerante (`weso_lookup`) continua achando a mesma
placa em 4 grafias diferentes.

⚠️ **Na primeira execução ele já pegou dois casos reais** — uma placa cadastrada
com espaço *durante* a sessão que limpava a base, e uma ambiguidade que a nossa
própria normalização cria (`OBD 3` × `OBD 3*`). Ver `21_Plano_Higiene_Placas.md`.

### Mudança de 14/08 — a regra de minúscula ficou restrita

🚨 **MINÚSCULA SÓ É COBRADA NOS NOSSOS PADRÕES**: placa convencional (com ou sem
o marcador `(RD)`), chassi rotulado (`CHASSI: ` + 17) e placa-recipiente
(`<PLACA>-UPGRADE` / `<PLACA>-MANUT`). Decisão do usuário: a base tem
identificadores que não são placa e nunca vão ser — `Móvel 1`, `TAG
identificação`, `OBD 4G - 17`, `ISCA DE CARGA` — e cobrar caixa alta neles é
cobrar uma regra que não existe. Reprovar por causa deles treinava a ignorar a
suíte inteira.

⚠️ **O espaço continua valendo para TODOS.** Minúscula é convenção; espaço é
falha silenciosa — foi ele que tornou `' TTX 0H91'` invisível para
`/Veiculos/Consultar?placa=` no termo 8788, que é o motivo desta suíte existir.

🚨 **O filtro reusa `placas.eh_convencional`, e não um regex próprio.** O regex
que eu tinha escrito deixava **47 placas `(RD) EDF 5724` fora do escopo** — ou
seja, sem a proteção que a suíte existe para dar. A regra de "o que é placa"
mora em `fpsl_weso/placas.py` e só lá; duas definições da mesma coisa divergem.

---

## `tests/teste_tela_gerar_os.py` + `tests/exercitar_tela.js` — a tela rodando (14/08)

**15 verificações.** Carrega o script da tela **inteiro** num DOM de mentira, em
node, com o `fetch` devolvendo a **resposta real** da extração do termo 8842, e
verifica o que o operador veria: campo do termo preenchido, contagem de veículos
e itens, tabela montada, botão liberado, zero alerta. Vai até o resumo.

⚠️ **`exercitar_tela.js` recebe argumentos** (`<gerar_os.html> <resposta.json>
[perfil]`) e é dirigido pelo teste Python. Rodar solto estoura com
`ERR_INVALID_ARG_TYPE` — **não é defeito**.

🚨 **MOCK COMPLACENTE APROVA CÓDIGO QUEBRADO.** O primeiro simulador criava um
elemento para qualquer id pedido, e por isso **aprovou a versão quebrada**: o
defeito só aparece quando `getElementById('progressoCaixa')` devolve **null** —
é o null que faz o código partir para criar a caixa. Agora só existe id que
existe no HTML.

🚨 **O teste precisa REPROVAR quando o defeito volta.** A seção [3] reinjeta o
defeito no HTML e exige que o exercício acuse `etapas.map is not a function`.
Sem isso sobra um teste que só sabe dizer "está tudo bem".

⚠️ **Injeção de defeito tem de casar com o arquivo real:** o `gerar_os.html`
está em **CRLF**, e um `replace` com `\n` não casa nada — normalizar antes. E
injetar **dentro** do `try` não reproduz o original, que estourava **fora**.

⚠️ **O mock do `fetch` faz parte do contrato.** Quando a tela passou a ler a
resposta com `res.text()`, o mock que só tinha `json()` reprovou — corretamente.
Mock que não acompanha o contrato volta a aprovar código quebrado.

Isto **não substitui abrir no navegador**: não há layout, CSS nem clique.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_tela_gerar_os.py
```

---

## O que ainda NÃO tem teste

- **Geração real de OS** (`confirmar:true`) — o dry-run está coberto ponta a
  ponta; a escrita real só foi validada à mão, com OS reais criadas e apagadas
- **A tela num navegador** — desde 14/08 o JS é exercitado em node com DOM de
  mentira (15 verificações), mas **ninguém abriu no navegador**: sem layout,
  sem CSS, sem clique. Exercitado ≠ usado
- Varredura de OS (`os_scan_router`) — só a tranca de acesso
- Escrita na WESO (`/weso/os/adicionar`) — a Fase 2 vai precisar de teste próprio
- Os 12 testes de Oficina, que validavam o fluxo descartado e precisam ser reescritos

---

## Contagem atual (2026-08-19)

**804 verificações em 22 arquivos.** Verdes menos as **8 falhas esperadas** do
`teste_upgrade_8820.py` — ver abaixo.

| Arquivo | Verificações |
|---|---|
| `tests/teste_barra_status.py` | 76 |
| `tests/teste_roteadores_painel.py` | 74 |
| `tests/teste_placas.py` | 72 |
| `tests/teste_manutencao.py` | 68 |
| `tests/teste_upgrade_8820.py` | 60 (**8 falham de propósito**) |
| `tests/teste_regressao_extracao.py` | 57 |
| `tests/teste_demandas.py` | 43 |
| `tests/teste_registro_telas.py` | 39 |
| `tests/teste_contrato_sidebar.py` | 38 |
| `tests/teste_extrair_termo.py` | 29 |
| `tests/teste_google_login.py` | 27 |
| `tests/teste_tela_cadastro_placas.py` | 27 |
| `tests/teste_cadastro_placas.py` | 26 |
| `tests/teste_higiene_placas_weso.py` | 25 |
| `tests/teste_perfis.py` | 24 |
| `tests/teste_criar_uma.py` | 23 |
| `tests/teste_tela_gerar_os.py` | 23 |
| `tests/teste_cadastro_log.py` | 21 |
| `tests/teste_aviso_weso.py` | 20 |
| `tests/teste_auditoria_placas.py` | 19 |
| `tests/teste_continuacao_pagina.py` | 11 |
| `tests/teste_disjuntor_harmonit.py` | 2 |

Trilha: **448/11** (14/08) → **677/19** (17/08) → **784/21** (18/08) →
**804/22** (19/08).

⚠️ **Os roteadores caíram de 81 para 75** em 14/08 porque as 2 rotas de
`api/placas` saíram junto com o router. Número menor aqui não é regressão.

🚨 **AS 8 FALHAS DO `teste_upgrade_8820.py` SÃO ESPERADAS.** Ele lê a WESO ao
vivo e os recipientes `OOM4131-UPGRADE` e `OOM3895-UPGRADE` foram apagados de
lá. O próprio teste afirma que "ausência de recipiente NÃO bloqueia", então não
é defeito — mas **8 falhas verdes de propósito treinam a equipe a ignorar o
placar**, e isso continua aberto: ou os recipientes voltam à WESO, ou o teste
pula sozinho quando o recipiente não existe.

🚨 **PLACAR VERDE NÃO É PROVA DE QUE A TELA ABRE.** Em 17/08 as 677
verificações passaram **todas** com o painel inteiro derrubado — nenhuma olhava
o consumidor do JSON. Desde 18/08 há dois testes que leem o consumidor:
`teste_contrato_sidebar.py` (lê o `sidebar.js`) e, desde 19/08,
`teste_aviso_weso.py` (lê o `os_router.py` e o `gerar_os.html`).

---

## `tests/teste_aviso_weso.py` — a WESO que não responde vira aviso (19/08)

**20 verificações. Não faz rede:** `weso_get` e o cache local são substituídos
por dublês.

Nasceu da **OS 16775**, gerada em 17/08 sem rastreador e sem chip porque a WESO
deu timeout e `_rastreador_id_por_placa` devolveu `{}` em silêncio. Detalhe em
`24_Desempenho_e_Timeout.md`.

O que ele prende:

1. `_anotar` não repete a mesma mensagem e aceita `None` sem explodir;
2. WESO fora ⇒ `buscar_seriais` e `dados_das_placas` **anotam** a falha;
3. chamador que não passa lista continua funcionando como antes;
4. 🚨 **WESO respondendo ⇒ nenhum aviso** — aviso falso treina a ignorar aviso;
5. contrato com o `os_router`: as duas chamadas passam a lista, e ela cai em
   `avisos` **antes** de montar as operações;
6. contrato com a **tela**: o `gerar_os.html` lê `data.avisos` e escapa.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_aviso_weso.py
```

🚨 **NÃO SÃO `assert`.** Os testes usam uma função `checar()` própria — um
`grep assert` no projeto devolve **zero** e engana quem for medir cobertura.

🚨 **NÃO HÁ PYTEST** instalado nem configurado. Cada arquivo roda como script
solto:

```bash
cd /home/claude/fpsl_weso
for t in tests/*.py; do echo "== $t"; venv/bin/python "$t" | tail -1; done
```

⚠️ **Os 3 testes soltos na raiz saíram em 14/08.** Dois eram exploratórios de
27/07 que **escreviam na WESO** e cujas perguntas já estão documentadas —
apagados. O `teste_perfis.py` foi para `tests/` porque a trava que ele exercita
está em uso real; ao mudar de pasta precisou do `sys.path` que os outros já
tinham.

---

## Lições que os testes deixaram
🚨 **`py_compile` NÃO substitui rodar os testes — isso aconteceu QUATRO
vezes em um dia (2026-07-29):** import faltando (`placas`), chamada na
função errada (`NameError: veiculos`), `timedelta` sem import, e
`_conectar` em vez de `_connect`. Os quatro compilaram.
Sempre conferir o **símbolo no namespace do módulo**, não só compilar.

🚨 **Resultado absurdo é sinal, não ruído.** A prévia de cliente dizia
que um CPF inventado já existia. Foi isso que revelou que o Harmonit
responde "não encontrado" em formato diferente de "encontrado".

**Nota original:** Em 2026-07-29, duas mudanças
compilaram e quebrariam em produção: um `placas.formatar()` sem o import (a
âncora do patch tinha os nomes em ordem invertida) e uma chamada inserida na
função errada (`NameError: veiculos`). Nos dois casos só o teste pegou.

---

## `tests/teste_aviso_previo.py` — o encargo que sumiu no termo 8848

**43 verificações.** Criado em 2026-08-26.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_aviso_previo.py
```

O vínculo casa por **texto exato** e o termo negocia o prazo: o modelo traz
`90 DIAS DE AVISO PRÉVIO DE CANCELAMENTO` e o 8848 trouxe
`(90) 30 DIAS DE AVISO PRÉVIO DE CANCELAMENTO`. A grafia nova virava pendente,
pendente bloqueia a geração, e a saída rápida era marcar **OCULTO** — que era
mudo. Resultado real: **R$ 131,74 fora da financeira 16805**.

| O que prende | Por quê |
|---|---|
| as duas redações procuram o mesmo vínculo (16033) | é o defeito do 8848 |
| a **descrição do termo** é preservada no item resolvido | senão toda rescisão diria "90 dias", inclusive as de 30 |
| `MULTA POR 90 DIAS DE AVISO…` **não** é este item | `M7`: mede o sufixo **e** o prefixo, não a ocorrência da palavra |
| o prazo entra acima do traço na solução técnica | decisão do usuário, 26/08 |
| item **oculto** vira aviso na prévia | era o único jeito de um item sumir sem rastro |
| os 3 termos de rescisão reais resolvem | 8848, 8842 e `rescisao.pdf` |

⚠️ O dublê é um **recorte** do catálogo, não o catálogo: as asserções falam só
do aviso prévio. `rescisao.pdf` traz `LEITOR RFID`, que não está no recorte —
exigir "nenhum pendente" mediria o dublê, não a correção.

---

## `tests/teste_central_nas_duas.py` — a Central nas duas OS, sem flag

**63 verificações.** Criado em 2026-08-26.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_central_nas_duas.py
```

Decisão do usuário: a Central aparece nas duas OS quando o termo diz
`CONTRATADO` ou `DESATIVAR NO SISTEMA`, em nenhuma quando diz `NÃO POSSUI` ou
`NÃO CONTRATADO`, e **nunca** com `cobrar` ou `comodato`, sempre com valor zero.

🚨 **O bloco 1 percorre `cfg.PERFIS` INTEIRO.** Perfil novo que nasça sem tratar
a Central reprova aqui. Na auditoria a transferência **novo titular** escapou —
ela monta a OS a partir de `resolvidos`, sem passar por `separar_itens` — e o
placar teria ficado verde.

| O que prende | Por quê |
|---|---|
| zerada e sem flags nos **11** perfis | a regra não pode depender de eu lembrar do caminho |
| presença, não contagem: 1 no termo, 3 placas, entra nas 3 | alocar por quantidade deixaria o 2º técnico sem o recado |
| `NÃO POSSUI` com valor **não** vira cobrança | a palavra não existia no código até 26/08 |
| desmarcar `nas_duas` devolve a Central a item comum | quem decide é o **vínculo**, não o nome no código |
| comodato marcado `nas_duas` **não** é zerado | zeraria o valor patrimonial e a DANFE de comodato |
| 8848 e 8842 ponta a ponta | o efeito completo: Central fora da cobrança, aviso prévio dentro |

---

## `tests/teste_taxa_migracao.py` — a cobrança que o Upgrade nunca fez

**33 verificações.** Criado em 2026-08-26.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_taxa_migracao.py
```

Toda financeira de upgrade saía `SEM CUSTO` — 8820, 8844, 8834 e 8827 — porque
o layout não tem tabela de itens e `itens` voltava vazio.

🚨 **A trava mais cara deste arquivo:** o total vem **riscado** em 2 dos 3
termos reais. Ler o primeiro valor da célula cobraria **R$ 2.300,00** de dois
clientes que o documento isentou.

| Termo | Célula do total | Resultado |
|---|---|---|
| 8827 | `R$ 200,00` + "Boleto a vista" | cobra R$ 200,00 |
| 8820 | `R$ 100,00` / `R$ 0,00*` | não vira item |
| 8800 | `R$ 2.200,00 - R$ 0,00` | não vira item |

Prende também: o rótulo dobrado (`TTOOTTAALL…`) reconhecido **sem** que o
desdobramento vire dado; nenhum dos outros 10 perfis lê a taxa; o item resolve
pelo **id fixo** `79746` sem depender de vínculo nenhum (decisão do usuário,
26/08), enquanto qualquer item fora da tabela `ITENS_COM_ID_FIXO` continua
dependendo do vínculo.

🚨 **A guarda do id é exercitada, não procurada por `grep`.** O teste dubla o
`harmonit_get`, chama `_conferir_ids_fixos()` e exige o recado quando o id
sumiu — e silêncio quando o catálogo está fora do ar. A guarda irmã, a do
`6967`, passou de 21/08 a 26/08 testada e sem nenhum chamador em produção.
