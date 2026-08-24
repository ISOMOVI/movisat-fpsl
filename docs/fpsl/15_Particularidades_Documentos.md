# Particularidades por Tipo de Documento (Painel de Geração de OS)

> Criado 2026-07-15, a partir da auditoria de 7 documentos reais fornecidos pelo
> usuário (1 de cada perfil + variações). Motivou a reescrita de
> `pdf_extractor.py` de heurística única pra extração por perfil.

## Cliente Novo

- Tem página extra que nenhum outro tipo tem: **Ficha Cadastral** (Razão Social, CNPJ, responsável, e-mail). Usada **só** pra pré-preencher a busca de cliente na Etapa 2 — nenhum outro dado dela entra na OS.
- Tabela de item usa cabeçalho **"Qtd | Descrição | Valor Unitário | Valor Total | Tipo"**, com uma linha de título mesclada ("SISTEMA: MOVISAT MANAGER 2.0") ANTES do cabeçalho real — não dá pra assumir que a primeira linha da tabela é o cabeçalho.
- Tabela de veículo é **1 coluna mesclada** ("Veículo e Placa ou Chassis do veículo"), não 2 colunas separadas.
- Pode ter veículo(s) com nota "transferido do contrato nº X" **misturado** com veículos genuinamente novos no mesmo documento — extrator captura em `nota_transferencia` por placa.
- Pode ter mais veículos com "Bloqueio veicular" comprado do que efetivamente instalado — a marcação de **quem recebe** está no texto livre da descrição do veículo (`***...SEM BLOQUEIO***`), não é "os N primeiros da lista". Ver `sem_bloqueio` por placa + alocação em `os_router.py::_alocar_itens_por_placa`.

## Aditivo / Upgrade

- Formato **enxuto**: sem Ficha Cadastral, sem texto de contrato — só a página de item+veículo.
- Cabeçalho usa **"Documento nº"**, não "Contrato" nem "Distrato".
- Nome do cliente e CNPJ só existem no cabeçalho da própria tabela de item ("{RAZÃO SOCIAL}\nCNPJ: X | Documento nº: Y") — não há texto de contrato pra buscar "da {empresa}".
- Documentos muito enxutos (1 veículo só) às vezes não têm o cabeçalho de tabela "# | Veículo e Placa..." reconhecível — extrator tem fallback por texto solto perto de "TOTAL MENSAL POR VEÍCULO" quando a tabela não é achada.

## Substituição

- Tabela **pareada**: 2 grupos de colunas lado a lado (veículo que sai / veículo que entra), com título mesclado "VEÍCULOS QUE SAIRÃO DO CONTRATO | VEÍCULOS QUE ENTRARÃO NO CONTRATO" acima do cabeçalho real (2 ocorrências de "Placa").
- **1 termo gera 2 OS** (retirada + instalação) com **veículos DIFERENTES** — não confundir com Transferência, que são 2 OS com o MESMO veículo em clientes diferentes.
- **Veículo de ENTRADA pode vir `A DEFINIR`** (substituto ainda não escolhido no momento do termo). A partir de 2026-07-23 isso é aceito: `_placa_ou_texto` devolve a placa normalizada quando casa com o padrão, **ou o texto literal** (`A DEFINIR`) quando não casa — só descarta célula vazia. **Antes o extrator exigia as duas placas válidas e descartava o par inteiro**, perdendo junto a placa de saída válida (bug real do termo 8799 / MGA: "não reconhece placa"). Decisão do usuário: `A DEFINIR` é placa válida e vai pra descrição como está.
- **Acessórios da Substituição têm formato próprio:** bullets `▶` numa célula "Acessórios / Serviços" (ex: `▶ Bloqueio Veicular ▶ Central 24 horas`), **sem** coluna Tipo nem Valor — diferente da tabela "Descrição dos serviços" dos outros perfis. `_itens_acessorios_substituicao` quebra a célula em `itens` (split por `▶`/`►`/`•`). Como não há Tipo nem valor, `_resolver_vinculos` resolve **`comodato=False, cobrar=False`** — regra do usuário: na substituição o acessório nunca é comodato nem cobrado.
- **Materiais entram nas DUAS OS** (retirada = o que é REMOVIDO do veículo antigo; instalação = o que entra no novo) — decisão do usuário 2026-07-23. **Antes iam só pra instalação**; `_montar_operacoes` passou a usar `materiais_placa` também na retirada. (Ressalva de multi-par: a agregação de acessórios é lista global + quantidade, distribuída por ordem — se pares diferentes tiverem acessórios diferentes entre si a alocação pode desalinhar; termos reais têm o mesmo pacote em todos os pares.)
- Taxa de substituição (mesmo local vs local diferente) aparece como texto solto acima da tabela, não em célula — capturada à parte (`taxa_mesmo_local`/`taxa_local_diferente`), ainda não usada na geração da OS (fica como referência pro operador).

## Rescisão

- Tabela pode agrupar **vários veículos numa célula só** (texto numerado "1. ... 2. ..."), todos com o mesmo "documento referência" (contrato de origem). Uma linha da tabela ≠ um veículo.
- **Listas grandes quebram pra página seguinte numa tabela SEM cabeçalho.** Até 2026-07-23 essa continuação era ignorada (o achador de header não a via, e o fallback só disparava com ZERO placas) — sumia com metade das placas. Bug real: termo 8788 (CONSTRUCTO), 26 veículos, só 12 extraídos (era o falso "limite de 12"). Agora `_eh_continuacao_veiculo_rescisao` reconhece a continuação (mesmo nº de colunas da tabela de veículos, sem palavras de tabela de itens) e lê a lista inteira, por quantas páginas forem. **Sem teto de nº de placas.** ⚠ Só a Rescisão tem esse tratamento hoje — estender aos outros perfis é pendência.
- Descrição de veículo pode **quebrar em 2+ linhas** dentro do mesmo item numerado (linha de continuação sem prefixo "N.") — não confundir com item novo.
- Pode ter **máquina/equipamento sem placa** (perfuratriz, escavadeira, identificados só por S/N) — não vira OS automática, fica marcado `sem_placa: true` e é filtrado da geração (revisão manual).
- Geralmente **não mostra CNPJ** — nome do cliente vem só do texto "Eu {responsável}, da {razão social}...". Ausência de CNPJ é esperada aqui, não é falha de extração.
- **Pode ser, na verdade, o lado de origem de uma transferência de titularidade pra outro cliente**, formatada como Rescisão porque, do ponto de vista de quem perde o veículo, a relação termina ali (R$0,00, "será transferido para outra titularidade"). Ver seção abaixo.

## Placas duplicadas × redundância (RD) — regra de geração (2026-07-23)

**Placa repetida no termo → 1 OS só + aviso** (`os_router.py`, `_dedup_placas`). A mesma placa nunca deve gerar 2 OS (retirar/instalar o equipamento do mesmo veículo 2× é sempre errado). Achado real: a Rescisão 8788 (CONSTRUCTO) listava as mesmas 3 placas em 2 referências (8540/8560) — erro de quem montou o documento (confirmado no texto cru do PDF). O painel avisa: "Placas repetidas no termo — gerada 1 OS por placa (não duplicada): PLACA (2x); ...". Vale pra todos os perfis; roda no começo de `gerar_os`, mantendo a 1ª ocorrência.

**EXCEÇÃO — redundância (RD): 2 equipamentos no MESMO veículo = 2 OS legítimas.** O mesmo veículo pode ter 2 rastreadores, marcado com `(RD)` **antes ou depois** da placa — `CUB 0764 (RD)`, `(RD) FCL 3G18`. Na WESO são 2 registros distintos (2 seriais — ex.: `CUB 0764 (RD)` serial 739854 e `CUB 0764` serial 205746399). O extrator (`_placa_formatada`) **preserva o `(RD)`** na placa, então `CUB 0764` e `CUB 0764 (RD)` viram chaves diferentes no dedup → 2 OS, sem aviso de duplicata.
- Só conta `(RD)` **entre parênteses**, numa janela colada à placa. `DRD 4189` (RD nas letras da placa) **não** é redundância; `ERF 0325 (ERF 0D25)` (variante OCR da Substituição) também não.
- Resumo: repetida SEM `(RD)` = erro → dedup+aviso; repetida COM `(RD)` = redundância → 2 OS.
- **Não testado ainda com termo real que tenha `(RD)`** — validado contra o formato da WESO + casos sintéticos + regressão nos 9 exemplos. Confirmar na UI quando aparecer um.

## Transferência de titularidade — não é 1 documento, geralmente são 2 (de clientes diferentes)

Na prática observada, uma transferência entre clientes diferentes aparece como **2 documentos separados**, não 1:
- **Lado de origem**: um "Termo de Rescisão" com frase indicando transferência ("passará a fazer parte do contrato nº X", "outra titularidade") — ver `termo errado.pdf` (Distrato 8787) como exemplo real.
- **Lado de destino**: um Cliente Novo ou Aditivo com nota "veículo transferido do contrato nº X" num item da tabela — ver `cliente novo.pdf`/`cliente novo2.pdf`.

`pdf_extractor.py` detecta essas frases (`_detectar_transferencia`) nos dois sentidos e expõe `alerta_transferencia` no retorno — o painel mostra aviso, não bloqueia, não tenta parear automaticamente (são 2 uploads possivelmente em dias diferentes, decisão fica com o operador).

O perfil formal "Transferência de titularidade" (`os_por_placa=2`, mesmo veículo, cliente de origem + cliente de destino) continua existindo em `templates_config.py` pra quando o processo for feito assim de propósito — `os_router.py` aceita `cliente_id_destino` por placa nesse caso.

## Achado de segurança (auditoria pós-implementação, 2026-07-15)

`gerar_os.html` (e `usuarios.html`) inseriam texto extraído de PDF/Harmonit direto em `innerHTML` sem escapar — um PDF malicioso com HTML/JS numa descrição de item ou veículo executaria na sessão autenticada do admin (que tem permissão de escrita no Harmonit). Corrigido com função `escapeHtml()` aplicada em todo ponto de interpolação nos dois arquivos.

**Corrigido em 2026-07-15 (autorizado pelo usuário, aplicado com `ssh vps-root`):** `/painel/api/login` não tinha rate limiting nem no Nginx nem na aplicação. Adicionada zona `fpsl_login` (5 req/min, burst=3 nodelay) em `/etc/nginx/nginx.conf`, aplicada em `location /painel/api/login` nos dois server blocks de `fpsl.conf` (443 TLS e 8005 legado) — mesmo padrão já usado no MoviChat (`ia_login`). Backup dos arquivos originais em `/etc/nginx/nginx.conf.bak_2026-07-15` e `/etc/nginx/sites-enabled/fpsl.conf.bak_2026-07-15`. Testado ao vivo: 4 primeiras requisições passam, a partir da 5ª nginx corta com 429.

**Também corrigido na mesma auditoria:** comparação de `X-FPSL-Key` (`fpsl_weso/auth.py`) trocada de `!=` pra `hmac.compare_digest` — evita timing attack pra adivinhar a chave.

## Comodato × Cobrança na geração de OS — a coluna "Tipo" decide, não o valor (2026-07-20)

**Regra do negócio (confirmada pelo usuário):** um item **nunca** pode ir pro Harmonit com `cobrar` **e** `comodato` verdadeiros ao mesmo tempo. Pode ser um, o outro, ou nenhum — nunca os dois.

**Bug que existia:** `os_router.py` decidia `cobrar = valor_unitario > 0` e `comodato` a partir da coluna Tipo, **de forma independente**. Como contrato de comodato **lista o valor de referência/patrimonial do equipamento** (pra DANFE/seguro/inventário, não é preço), todo equipamento em comodato saía com `valor > 0` **e** Tipo=`COMODATO` → `cobrar=True` + `comodato=True`. Não era caso raro: era **sistemático** (todo rastreador/chip/bloqueio em comodato). Confirmado no `ADITIVO.pdf` real: os 3 equipamentos (R$ 999,90 / 50 / 50, todos COMODATO) colidiam.

**A causa raiz é que a coluna "Tipo" não é um liga/desliga comodato-vs-aquisição** — é um campo de anotação livre, com intenções diferentes por linha: `COMODATO`, `MENSAL`, `NÃO CONTRATADO`, `*Cobrança realizada no documento nº X`, ou vazio. Quem sabe a verdade sobre cobrar é a coluna Tipo, não o valor.

**Critério novo (em `_resolver_vinculos`, 2026-07-20):**
- Tipo começa com `COMODATO` → `comodato=True`, `cobrar=False`. **O valor é preservado** no payload (`"valor": mat["valor_unitario"]`) porque vai pra **DANFE de comodato** depois — só não cobra.
- Tipo contém `NÃO CONTRATADO` / `NAO CONTRATADO` → a linha **não vira material de OS** (descartada por LINHA do contrato, não pelo vínculo fixo `oculto` — o mesmo item pode ser contratado em outro termo). O descarte é feito **antes** do lookup de vínculo (senão viraria "pendente" e bloquearia a geração 409). Os itens descartados voltam em `avisos` (`"Itens ignorados (não contratados, fora da OS): ..."`) pro operador ver no preview.
- Qualquer outro Tipo (`MENSAL`, vazio, aquisição, `*Cobrança realizada no documento nº X`) → `comodato=False`, `cobrar = valor > 0`. **Adesão cobra normalmente** (confirmado pelo usuário — a nota "*Cobrança realizada no documento" não suprime a cobrança aqui).

`cobrar` passou a ser calculado no resolvedor e gravado no dict do material; o envio ao Harmonit (`SalvarMaterialOrdemServico`) usa `mat["cobrar"]` em vez de `valor > 0`. O material fixo "ENTREGA OS" leva `cobrar=False` explícito.

**Deploy:** aplicado no local (`C:\code\fpsl_weso`), diff conferido contra a VPS (sem drift), backup em `os_router.py.bak_2026-07-20`, subido via scp, `py_compile` OK, `fpsl-weso` reiniciado. Verificado no `ADITIVO.pdf`: nenhum item sai mais com os dois flags.

## Upgrade 4G — coluna única "VEÍCULOS A MIGRAR" (termo 8800, 2026-08-07)

Variação do Aditivo com layout próprio. Motivou três correções no
`pdf_extractor.py`, e uma delas produzia **placa que não existe** — em
silêncio, que é o pior modo de falhar.

### O layout

Uma linha por veículo. **A primeira coluna é a ÚNICA que traz veículo e
placa** — as outras (`DOCUMENTO REFERÊNCIA`, `TAXA DE MIGRAÇÃO`, `NOVO VALOR
MENSAL`, plano) não têm nada a ver com identificação. Dentro da célula a placa
pode quebrar de linha:

```
col0 = 'FIAT/STRADA - RFD\n0E02'      <- veículo + placa
col1 = '2447'                          <- DOCUMENTO REFERÊNCIA
```

### Defeito 1 — a tabela boa era descartada

O guarda exigia `PLACA` no cabeçalho, **ou** `VEICULO` **e** `CHASSIS` juntos.
Aqui a coluna se chama "VEÍCULOS A MIGRAR" e não existe coluna CHASSIS: a
tabela, que estava perfeita, era jogada fora e a extração caía no fallback de
texto corrido.

**Correção:** coluna de veículo sozinha já basta. É seguro porque a extração é
**por célula** — coluna de outro assunto simplesmente não casa com o regex.

### 🚨 Defeito 2 — o fallback INVENTAVA placa

No texto achatado da página, as colunas viram linhas intercaladas, e o número
de `DOCUMENTO REFERÊNCIA` cai **entre** as duas metades de uma placa quebrada.
O `\s` do regex atravessava a quebra e colava a metade errada:

```
top=243.0  x0=110.9  RFD      <- placa, 1ª metade
top=248.4  x0=166.8  2447     <- OUTRA COLUNA   ✗ era esta que ele pegava
top=254.4  x0= 75.6  0E02     <- placa, 2ª metade
```

Saíam `RFD 2447` e `FMS 3078`, que **não existem na WESO**, no lugar de
`RFD 0E02` e `FMS 3J88`, que existem. Sem erro, sem log, sem aviso.

**Correção:** `_PLACA_RE_MESMA_LINHA`, sem `\s`, usado **só** no fallback de
texto. Dentro de uma célula o `\n` deve unir (é a placa quebrando); no texto
corrido, nunca.

> **Placa inventada é pior que placa faltando.** A que falta alguém percebe; a
> inventada gera OS apontando para veículo que não existe — ou, com azar, para
> o veículo de outro cliente.

### Defeito 3 — cabeçalho que é parágrafo, não título

A coluna de descrição do plano começa com *"Após a migração os **veículos**
migrados passarão a operar..."* e casava como coluna de veículo, arrastando
"PLANO PRÓ Troca de equipamento 2G para 4G" para a lista.

**Correção:** `_colunas_de_veiculo` aceita cabeçalho de até 40 caracteres —
título de coluna é curto, parágrafo não é. Se o teto descartar todos os
candidatos, devolve os originais: perder a coluna certa é pior que aceitar uma
a mais.

### Máquina sem placa de Detran ENTRA no termo

O termo tem **11 veículos**, dois deles máquinas identificadas por série e
chassi. Antes eles sumiam e a tela dizia "9 veículos" — número que parece
completo e não é.

🚨 **O campo `placa` da WESO é texto livre e é o ALVO da busca — não é placa
de Detran.** Regra do usuário (2026-08-07): *"o termo deve vir padronizado
conforme a WESO, idêntico, seja veículo antes ou placa antes, seja placa
convencional ou não."*

O rótulo **faz parte do valor** (conferido ao vivo em 07/08):

| No termo | Na WESO |
|---|---|
| `... 2023 - SERIE 16994` | `SERIE 16994` |
| `... - Chassi:1BM6115J JMD002601` | `CHASSI: 1BM6115JJMD002601` |

`_identificador_nao_convencional` extrai o trecho a partir do rótulo
(`SÉRIE`/`CHASSI`), mantendo-o, e marca `placa_convencional: False` — que a
tela usa para destacar na conferência, **nunca para excluir da geração**
(mesma regra que a Rescisão já aplicava).

⚠️ Só rótulo **explícito** autoriza: texto solto sem `SÉRIE`/`CHASSI` vai para
revisão humana em `veiculos_sem_placa`. Adivinhar identificador a partir de
texto solto é como nasceu o `RFD 2447`.

⚠️ **Ainda não é byte a byte:** o termo escreve `Chassi:1BM6115J JMD002601` e a
WESO guarda `Chassi: 1BM6115JJMD002601`. O `placas.normalizar` remove o que
não é alfanumérico, então **acha** o veículo — mas a padronização das strings
via API (junto com espaços e `(RD)`) continua pendente.

### Validado antes de implantar

- extração: **11 veículos**, nenhuma linha sobrando;
- **11 de 11 encontradas na WESO ao vivo**;
- suítes: regressão 57, continuação 11, placas 72 — zero falhas, os 9 termos
  anteriores idênticos.

Fixture de regressão: `tests/fixtures/upgrade_4g_8800.pdf`, com asserções que
travam explicitamente **"não inventa RFD 2447"** e **"não inventa FMS 3078"`.

---

## Upgrade — a placa-recipiente de teste (termo 8820, 2026-08-13)

### 🚨 UPGRADE NÃO É SUBSTITUIÇÃO

A diferença é o que muda, e ela decide o desenho inteiro:

| | Substituição | Upgrade |
|---|---|---|
| O que muda | o **veículo** | o **equipamento** |
| O equipamento | sai do veículo A e vai para o veículo B | sai e entra **no mesmo veículo** |
| A placa que "entra" | outra placa **real**, que vem no documento | placa **genérica de teste**, que **não** vem no documento |
| É o destino? | sim, permanente | **não** — é bancada |
| OS | 2 por placa (retirada + instalação) | **1**, na placa real |

No Upgrade o setor de configuração cria na WESO uma placa derivada e vincula
nela o equipamento novo, **para testar antes de ir a campo**. Conferido ao vivo
em 13/08:

| Placa real | Rastreador hoje (SAI) | Recipiente | Descrição | Rastreador novo (ENTRA) |
|---|---|---|---|---|
| OOM 3895 | `356354872585899` — XT40 | ` OOM3895-UPGRADE` | TERMO 8820 | `356354871410958` — XT40 Portátil |
| OOM 4131 | `356354872583936` — XT40 | `OOM4131-UPGRADE` | TERMO 8820 | `356354871411980` — XT40 Portátil |

`XT40 → XT40 Portátil` é exatamente a "migração do rastreador fixo para
rastreador móvel" do cabeçalho do termo.

⚠️ **O RECIPIENTE NUNCA VIRA VEÍCULO DA OS.** Se virar, a OS sai mandando
instalar em veículo que não existe — mesma família do `RFD 2447`: dado
plausível apontando para lugar nenhum. Ele entra só como **chave** para
descobrir a série do equipamento que entra, e é descartado depois.

### A regra de derivação

```
placa_teste("OOM 4131", "-UPGRADE")  ->  "OOM4131-UPGRADE"
```

Tira espaço, sobe a caixa, acrescenta o sufixo. O sufixo mora em
`templates_config.PERFIS["upgrade"]["placa_teste_sufixo"]` — não está
espalhado no código.

⚠️ **O ` OOM3895-UPGRADE` está gravado na WESO com espaço na frente** (erro de
digitação de quem cadastrou; `chave_placa` saiu limpo). Não quebra nada porque
a busca normaliza, mas some de qualquer consulta por `placa` exata.

### 🚨 A conferência de termo

Pedido do usuário em 13/08, e é a trava que importa:

> **placa que já passou por upgrade antes tem um recipiente VELHO na WESO**,
> com a descrição do termo anterior. Sem conferir, a OS sairia com a série do
> equipamento **passado** — plausível, errada e silenciosa.

`_conferir_placas_teste` compara a `descricao` do recipiente com
`TERMO {termo}` do documento subido.

⚠️ **AUSÊNCIA NÃO BLOQUEIA, CONTRADIÇÃO BLOQUEIA.** `descricao_da_placa`
devolve `None` para "não sei" — cache fora do ar, ou recipiente que o setor de
configuração ainda não criou. Aí vale o best-effort da casa: a descrição sai
com o marcador de série não localizada e a OS é gerada. Só descrição
**divergente**, que é prova positiva de recipiente errado, devolve 400.

Provado no teste: `GCW9H80-UPGRADE` devolve `TERMO 8824` — recipiente de outro
termo é reconhecido como outro.

### A descrição resultante

```
Upgrade: OOM 4131 | SR/FACCHINI SRF CA, DIESEL, 2015/2016, CINZA | SAIRÁ: 356354872583936 | ENTRARÁ: 356354871411980 | TERMO 8820
```

O "id do equipamento" é o **número de série** do rastreador — mesma convenção
já usada no perfil agrupado da Transferência (`14_Painel_OS.md`).

### Onde mexeu

- `painel/equipamentos.py` — `placa_teste()` e `descricao_da_placa()`
- `painel/templates_config.py` — perfil `upgrade`: sufixo, modelo de descrição
  do recipiente e template com SAIRÁ/ENTRARÁ
- `painel/routers/os_router.py` — `_serie_que_entra()`, `_conferir_placas_teste()`,
  o recipiente entra na busca de seriais, e **`import re`**, que faltava

🚨 **O `import re` faltava e o `py_compile` passou.** Só pegou porque o deploy
manda importar de verdade. É a 5ª vez que esse defeito aparece no projeto.

### Validado antes de implantar

- teste novo `tests/teste_upgrade_8820.py`: **26 verificações**, fixture
  `tests/fixtures/upgrade_8820.pdf`;
- suítes existentes sem regressão: regressão 57, continuação 11, placas 72,
  disjuntor 2, higiene de placas;
- descrição montada ponta a ponta com dado real das duas placas.


### Padronização do rótulo de chassi — 2026-08-13

🚨 **O rótulo agora é `CHASSI: ` em caixa alta, com dois pontos e um espaço.**
Decisão do usuário. Antes a base tinha cinco grafias: `Chassi:`, `CHASSI `,
`CHASSI:` sem espaço, `CHSS:` e nenhuma.

**41 registros alterados** na WESO (`POST /Veiculos/Atualizar`), sendo 32
chassis que estavam **crus, sem rótulo nenhum** — esses veículos nunca eram
reconhecidos automaticamente num termo, porque a regra de 07/08 só aceita
identificador não convencional com rótulo explícito. Agora são.

**Regra: chassi é 17 alfanuméricos.** Sem exceção, e por um motivo medido: a
primeira versão do levantamento usou "9 a 20 caracteres, token único" e teria
transformado em chassi os recipientes `-UPGRADE`, a `TAG identificação` e os
códigos `OBD 4G`. Duas armadilhas de coincidência apareceram e as duas foram
pegas pela lista de convenções intocáveis:

| Valor | Normalizado | Por que NÃO é chassi |
|---|---|---|
| `TRATOR MF3147165M1` | 17 chars | "TRATOR" é a palavra; o apelido já é MASSEY FERGUSON |
| `A DEFINIR TERMO 8831` | 17 chars | é o placeholder de termo |

⚠️ **Ficaram de fora, por decisão:** 4 registros já rotulados mas com número de
6 a 9 caracteres (`CHASSI 806587`, `CHASSI:17100057`, `CHSS: NAAH22440`,
`CHASSI 9B03414GW`), e os 70 códigos internos de frota (`EGP NN`, `MH0N`,
`RP 0N`, `TC55`).

⚠️ **A chave normalizada MUDOU** nesses 41: `9BWKB45U8KP018607` virou
`CHASSI9BWKB45U8KP018607`. Não quebra o casamento com o termo porque o termo
**também escreve o rótulo** (`Chassi:1BM6115J JMD002601`), e o
`placas.normalizar` sobe a caixa — os dois lados chegam em
`CHASSI1BM6115JJMD002601`. Foi justamente a WESO que estava sem o rótulo.

**Ferramenta:** `rotular_chassi_weso.py`, irmão do `normalizar_espacos_placas.py`
(29/07) e do `corrigir_placas_espaco.py` (27/07) — mesma disciplina: dry-run por
padrão, `--somente <id>` para validar um antes do lote, relê o estado depois de
cada escrita, aborta se o `rastreador_id` mudar, exclui colisões e imprime o
comando de reversão.

🚨 **Erro que quase passou em silêncio:** a primeira versão lia `veiculos` na
raiz da resposta, mas o envelope é `{"Data": {"veiculos": [...]}}`. Resultado:
**base vazia, zero registros, nenhum erro** — o dry-run disse "0 a alterar" e
parecia sucesso. Mesma família do `{sumario, lista}` do Harmonit. O script agora
aborta se a base vier vazia.

## Placa que não parece placa — a regra do traço (termo 8846, 2026-08-20)

**A Erika não conseguiu gerar o 8846, seis vezes.** O termo traz
`NISSAN, 2022, DIESEL - RZL H405`, e `RZL H405` é uma **placa chilena** (4
letras + 2 dígitos, `RZ.LH40.5`) adaptada à força ao padrão Mercosul por quem
escreveu o documento. Não casava com nenhum padrão brasileiro, ia para "não
reconhecida", e a geração morria em `400 Nenhuma placa informada`.

⚠️ **A tela velha avisava e não oferecia nenhuma forma de corrigir** — daí as
seis tentativas.

### 🚨 A REGRA (decisão do usuário, 20/08)

> Na coluna **"Veículo e Placa ou Chassis do veículo"**, o que vem **depois do
> traço é a placa**, não importa o formato.

Corrigido no `pdf_extractor`, que é o **único arquivo que as três telas
dividem** — Gerar OS, Cadastro de Placas e a aba Operações foram atendidas de
uma vez. É também o único ponto do sistema em que a regra "clona × reusa" abre
exceção, e por isso o risco de mexer nele é sempre triplo.

### A guarda não mede FORMATO, mede se é linha de veículo

Aceitar qualquer coisa depois do traço abriria a porta para texto corrido virar
placa. A guarda que ficou exige: **até 2 blocos, 3 a 15 caracteres, ao menos um
dígito e uma letra, sem vírgula nem parênteses.**

🚨 **Sem ela, duas linhas de texto corrido do `transferencia_novo.pdf` viravam
a placa `la também no contrato principal de`** — que é o `RFD 2447` renascendo.
A regra foi medida nos **14 fixtures ANTES** de ser escrita, não depois.

### ⚠️ A primeira hipótese estava errada, e medir salvou

Achei que fossem o `4` e o `H` trocados de lugar. **`RZL4H05` não existe na
WESO; `RZL H405` existe** — id `88440`, rastreador `48114`, cadastrado no mesmo
dia às 09:10. Hipótese plausível não é fato medido.

### 🚨 E a pergunta seguinte era "a OS sai completa?"

Depois de desbloquear a geração, o defeito tinha só mudado de lugar: **o cache
da WESO atualiza às 04:15 e o veículo nasceu às 09:10.** Não havia modelo, não
havia produto no de-para, e a OS sairia **sem o equipamento nos materiais** —
completa na aparência, vazia no conteúdo. Eu tinha trocado um bloqueio visível
por uma OS incompleta e plausível.

Corrigido em `a08fd9e`: **placa fora do cache é lida ao vivo.**

⚠️ **A lição de método, e ela vale além deste caso:** depois de consertar,
perguntar o que acontece **DEPOIS** do que foi consertado. Metade dos achados
das seis auditorias de 20/08 veio dessa pergunta; a outra metade veio de
comparar com a tela que já existe.

### ⏸️ O que ficou com o usuário

**A grafia oficial do veículo WESO `88440`.** O rastreador está vinculado a uma
placa cuja grafia veio do mesmo termo, e o `chassi` é **nulo** — não há nada no
cadastro que confirme qual das duas é a certa. Se a oficial for `RZ.LH40.5`, o
cadastro na WESO precisa ser corrigido à mão.
