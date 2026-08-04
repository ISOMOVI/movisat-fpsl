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
