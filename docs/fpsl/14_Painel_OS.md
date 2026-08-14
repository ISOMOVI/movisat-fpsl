# Painel de Geração de OS por Contrato

**Status:** 🟡 backend 100% testado (inclusive com documento real e fluxo HTTP completo), extração agora é por perfil (6 tipos de documento, não mais heurística única) — ver `15_Particularidades_Documentos.md`. Frontend atualizado mas **ainda não testado visualmente em navegador de verdade** (só via curl/HTTP direto). Login básico temporário — Google OAuth previsto ~20/07.

**URL:** https://fpsl.movisat.com.br/painel
**Login de teste:** admin / (senha em `.env`, `PAINEL_ADMIN_SENHA`)

---

## Por que existe

Automatizar a **abertura** de OS a partir de contrato assinado (PDF) — sem automatizar a oficina (isso continua manual, feito por quem pegar a OS). Objetivo: gerar pré-preenchida e pronta, eliminando digitação manual repetitiva.

## Arquitetura

```
fpsl_weso/painel/
  auth.py              login básico (JWT, 8h) — trocar por Google OAuth ~20/07
  templates_config.py  6 perfis de contrato → tipoId/problemaId do Harmonit
  pdf_extractor.py     extração via pdfplumber (regra, sem IA)
  routers/
    login_router.py    POST /painel/api/login
    os_router.py        /painel/api/perfis, /extrair, /clientes/buscar, /gerar-os

frontend/
  login.html
  wizard.html           3 etapas: upload+perfil → cliente+termo → resumo+gerar
```

## Regra de negócio confirmada (2026-07-14, Transferência revisada 2026-07-16)

**1 OS = 1 placa = 1 operação**, EXCETO Transferência de titularidade (ver abaixo). Perfis com 1 OS/placa: Cliente novo, Aditivo, Rescisão, Upgrade. Substituição: 2 OS/placa (retirada + instalação, veículos DIFERENTES, mesmo cliente). **Transferência de titularidade (mudança 2026-07-16): não é mais 1 par de OS por placa — é 1 OS de retirada (cliente origem) + 1 OS de instalação (cliente destino) por DOCUMENTO, juntando todas as placas do termo numa descrição só** (`perfil["agrupado"] = True` em `templates_config.py`). Formato: `TRANSFERENCIA DE CONTRATO: (placa | veículo | NUMERO DE SERIE); (placa2 | ...)`. Materiais das placas todas se somam na OS de instalação.

## Mapeamento perfil → Harmonit (ver `templates_config.py`)

IDs reais consultados ao vivo (empresaId=98). **Confirmados** (nome bate exato entre perfil e lista real): Cliente novo, Aditivo, Rescisão, Transferência, Upgrade. **Inferidos** (minha melhor leitura, não confirmados por revisão humana ainda): qual `tipoId` específico usar em cada caso, e a divisão retirada/instalação da Substituição — revisar antes de gerar OS real em produção.

`produtoServicoId` **não é fixo por perfil** — é campo livre na Etapa 2 do wizard (testado com `6966` = serviço "MANUTENÇÃO"). `SalvarOrdemServicoBasica` falha sem um produto/serviço válido — por isso o painel sempre usa `SalvarOrdemServico` (completo).

## Endereço — não precisa enviar

Confirmado com teste real: o painel do Harmonit busca e mostra o endereço do **cadastro do cliente** automaticamente, não precisa ser enviado no payload da OS.

## Descrição da OS — template simplificado

Decisão 2026-07-14: **sem o número da própria OS embutido** (eliminaria retrabalho de 2 chamadas — criar, pegar número, atualizar descrição). O operador confere o número direto no Harmonit ao abrir a OS.

```
{TIPO}: {placa} | {veiculo} | NUMERO DE SERIE | TERMO {termo}
```//
`NUMERO DE SERIE` fica como texto literal — o operador preenche na hora da instalação real (não é conhecido no momento da assinatura do contrato).

## Extração de PDF — validada contra 1 documento real

Testado contra `Distrato nº 8793` (rescisão, 3 placas) — extraiu Termo (8793) e as 3 placas com veículo completo, 100% corretos, texto nativo (sem OCR). **CNPJ nem sempre está no documento** (não estava neste exemplo) — por isso a Etapa 2 sempre permite busca manual do cliente por nome, não só por CNPJ extraído.

**Só temos exemplo real de 1 tipo de documento (Rescisão/Distrato).** Extração de Cliente novo/Aditivo/Substituição/Transferência/Upgrade ainda não foi validada contra documento real — a lógica de tabela+placa deve generalizar (mesma estrutura visual provável), mas não está confirmado.

## Testado (via curl, backend real)

- Login (admin/senha do .env) → token JWT ✅
- Extração do PDF real → Termo + 3 placas corretos ✅
- Busca de cliente por nome ("KEEVA") → achou o cliente real (id 259204) ✅ — corrigido um bug no meio do caminho: a resposta do `/ObterClientes` vem em `{sumario, lista}`, não `{data}` como eu tinha assumido
- Simulação (dry-run, `confirmar:false`) de geração de 3 OS de Rescisão com os dados reais extraídos → gerou as 3 operações certas, sem escrever no Harmonit ✅

**Não testado:** geração real (`confirmar:true`) — não executei pra não criar OS reais sem sua autorização explícita. Interface visual (cliques, JS no navegador) — só inspeção de código, não abri num browser de verdade.

## Pendente

- Revisar/confirmar os mapeamentos "inferidos" de tipoId antes de usar em produção
- Testar extração com exemplo real de cada outro perfil
- Trocar login básico por Google OAuth (~20/07, junto com Chatwoot)
- Testar geração real de OS (com sua autorização) e validar visualmente no navegador

---

## Atualização 2026-07-14 (sessão 2) — sidebar, usuários, extração ampliada

**Feito e testado:**
- Sidebar com navegação (Gerar OS / Usuários), inspirado no admin do MoviChat
- Gestão de contas real: tabela `painel_usuarios` (SQLite), CRUD via `/painel/api/usuarios` (só admin). Login/senha do `.env` viram só o seed do primeiro usuário admin, não mais fixo em código.
- **Bug corrigido:** `bcrypt` 5.0.0 instalado por padrão é incompatível com `passlib` 1.7.4 (erro `password cannot be longer than 72 bytes` no self-test interno, nada a ver com senha real) — fixado `bcrypt==4.0.1`.
- Etapa 2: nome do cliente já vem sugerido do PDF (heurística de regex, ver `pdf_extractor.py`) — busca de cliente e de serviço viraram modal dedicado, não mais lista inline
- Extração agora também pega a **tabela de itens/acessórios** do contrato (RASTREADOR, BLOQUEIO VEICULAR, etc — quantidade, valor unitário, comodato/aquisição), separando corretamente da tabela de condições de pagamento (heurística por cabeçalho)
- Senha do painel trocada para `FPSL424636!@`

**Testado com o documento real de novo:** nome do cliente extraído certo ("KEEVA TEIC..."), 3 itens de acessório extraídos certos (RASTREADOR R$999,90, BLOQUEIO VEICULAR R$50,00, CENTRAL 24 HORAS R$10,00), busca de serviço funcionando ("MANUTENÇÃO" e variantes).

**Pendente / proposto, não implementado ainda:** sistema de vínculo item-do-contrato ↔ produto/serviço do Harmonit (com tela de administração e fallback de "perguntar quando não reconhecido"), uso de `SalvarMaterialOrdemServico` pra anexar os itens com valor à OS, resumo de reconciliação de valores na Etapa 3 — ver proposta enviada ao usuário na conversa, aguardando aprovação antes de implementar.

---

## Atualização 2026-07-14 (sessão 3) — vínculos de itens + materiais na OS

**Feito e testado ponta a ponta (inclusive escrita real no Harmonit, depois excluída):**
- Tabela `painel_vinculos_itens` — mapeia nome do item do contrato (normalizado) → produto/serviço real do Harmonit, com flag `oculto`
- `POST /painel/api/extrair` e `/vinculos/extrair-preview` já anexam o status de vínculo de cada item extraído
- `POST /painel/api/gerar-os` agora: resolve vínculos → **bloqueia com 409 se algum item não tem vínculo** (testado: RASTREADOR sem vínculo bloqueou corretamente, BLOQUEIO VEICULAR e CENTRAL 24 HORAS com vínculo passaram) → aloca quantidade por placa em ordem → gera OS → anexa materiais via `SalvarMaterialOrdemServico` (sempre incluindo "ENTREGA OS", id 285367, fixo)
- **Bug real encontrado e corrigido em teste:** a alocação por placa inicialmente reaproveitava o mesmo dict do item (com a quantidade TOTAL do contrato, ex: 3) em vez de 1 unidade por placa — corrigido antes de qualquer geração real usar essa lógica errada. Reconfirmado: 3 rastreadores → 1 por placa nas 3; 2 bloqueios → só as 2 primeiras placas; 4 "central 24h" pra 3 placas → aviso disparado corretamente, aloca só nas 3
- **Teste real completo:** 1 OS gerada (id 837666, nº 16506) com 3 materiais anexados (ENTREGA OS + RASTREADOR + BLOQUEIO VEICULAR), zero erro — excluída depois do teste
- Vínculos de teste já cadastrados: BLOQUEIO VEICULAR→45689 (produto), CENTRAL 24 HORAS→6976 (serviço), RASTREADOR→43292 (produto genérico, só pra teste — **revisar antes de produção real**, "RASTREADOR" sozinho é ambíguo, o contrato real provavelmente deveria linkar pro modelo específico instalado)

**Pendente:** *(revisado contra o código em 2026-07-22 — 3 dos 4 itens já estavam feitos)*
- ~~Frontend da tela "Vínculos" (admin)~~ — ✅ **CONSTRUÍDO** (`frontend/vinculos.html`, 411 linhas).
- ~~Upload de Termo dentro da tela de Vínculos~~ — ✅ **CONSTRUÍDO** (`vinculos.html:131` input de arquivo, `:236` chama `/vinculos/extrair-preview`).
- ~~Resumo de reconciliação de valor na Etapa 3~~ — ✅ **CONSTRUÍDO** em 2026-07-16 (`gerar_os.html:515`, campos `valor_total_contrato`/`valor_total_anexado`).
- ⚠️ **AINDA ABERTO — vínculo "RASTREADOR" genérico.** O aviso continua válido, só mudou de alvo: era `43292` (produto de teste), hoje aponta pra **`20314`** — o **mesmo id** de `EQUIPAMENTO RASTREADOR TELEMETRIA AVANCADA`. Dois nomes de item do contrato caindo no mesmo produto Harmonit, então o modelo real instalado continua indefinido. **É o mesmo problema que o mapeamento acessório→modelo resolve** (RFID → X, button → Y, nenhum → XT40): tratar os dois juntos, não separado.

  ### 📍 Onde estão os dados para montar esse mapa (levantado em 2026-07-28)

  A base de manuais na VPS já tem a **matéria-prima**, embora não a resposta pronta.

  | Fonte | O que dá |
  |---|---|
  | `~/base_manuais/_texto/ESQUEMAS-ELETRICOS.txt` | **12 combinações reais de instalação**, por família de modelo, fio a fio |
  | `~/base_manuais/00_Matriz_Modelos.md` | I/O de cada modelo — quantas entradas/saídas, se tem 1-Wire, se tem serial |
  | `~/base_manuais/01_Ligacoes_Eletricas.md` | pinagem completa; mostra **qual acessório é fisicamente possível** em cada modelo |

  **As combinações que os esquemas cobrem:**

  | Família | Configurações documentadas |
  |---|---|
  | ST310U · ST4315U | simples · pânico+bloqueio · bloqueio |
  | ST300 · ST300H · ST300HD · ST4305 | simples · RFID · RFID+bloqueio · iButton · iButton+bloqueio |
  | ST340 · ST340RB | simples · RFID · RFID+bloqueio · simples+bloqueio |

  ⚠️ **É semente, não resposta.** Os esquemas respondem *"o modelo X aceita quais
  acessórios"*. O FPSL precisa do **inverso**: *"este item do termo corresponde a
  qual modelo"*. O mapa direto continua sendo decisão comercial/de estoque — qual
  modelo a Movisat instala em cada combinação vendida.

  **Restrições físicas que o mapa não pode violar** (saem de `00_Matriz_Modelos.md`):
  - **iButton/1-Wire** só existe em ST300H, ST4305, ST8300 e família — **não** no ST310/ST4315/ST8310UM;
  - **RS232** (leitor RFID) só em ST300R, ST300H e ST4305/ST8300;
  - **ST340LC** tem 1 entrada e 1 saída — não comporta acessório além do bloqueio;
  - **XT40-OBDII não tem saída** — não pode receber bloqueio.

  Ou seja: qualquer combinação "item do contrato → modelo" que exija acessório
  incompatível com o modelo escolhido está errada, e isso **dá para validar por código**.

---

## Atualização 2026-07-15 (sessão 4) — extração por perfil + Substituição/Transferência corretas + auditoria de segurança

**Motivo:** usuário forneceu 7 documentos reais (`C:\Users\Lenovo\Downloads\exe fpsl\`), 1 de cada perfil + variações. `pdf_extractor.py` só tinha sido validado contra 1 Distrato simples — os outros 5 tipos tinham formato de tabela genuinamente diferente. Detalhamento completo por tipo em `15_Particularidades_Documentos.md`.

**`pdf_extractor.py` reescrito pra extração por perfil** (`extrair_campos(fonte, perfil)`, dispatch por chave de `PERFIS`):
- Cliente Novo/Aditivo/Upgrade: cabeçalho de tabela ("{RAZÃO}\nCNPJ: X | Contrato/Documento nº: Y") como fonte de cliente/CNPJ, mais confiável que regex em prosa. Ficha Cadastral (só Cliente Novo) só alimenta a busca de cliente, nada mais.
- Substituição: tabela pareada (2 colunas "Placa"), extrai os 2 lados.
- Rescisão/Transferência: `findall` em vez de `search` pra não perder veículo em célula com vários agrupados; junta linha de continuação (sem prefixo numerado) no item anterior em vez de tratar como item novo.
- Corrigido bug estrutural comum a 3 dos parsers: várias tabelas têm uma linha de título mesclada (ex: "SISTEMA: MOVISAT MANAGER 2.0", "VEÍCULOS QUE SAIRÃO DO CONTRATO") ANTES do cabeçalho real — o código assumia que a primeira linha da tabela sempre era o cabeçalho. Novo helper `_achar_linha_header` escaneia as primeiras linhas.
- Detector de frase de transferência de titularidade disfarçada de Rescisão (`alerta_transferencia`) e de marcação "SEM BLOQUEIO" no texto do veículo (`sem_bloqueio`), usado na alocação de material.
- Testado contra os 7 documentos reais — todos corretos, incluindo o caso mais complexo (rescisão com 27 veículos/máquinas agrupados em 10 linhas, múltiplos contratos de origem).

**`os_router.py` — Substituição e Transferência tratadas explicitamente, não mais com a mesma lógica genérica de "os_por_placa==2":**
- Substituição: 2 OS com veículos DIFERENTES (retirada do que sai, instalação do que entra), mesmo cliente. Materiais vão pra instalação (o veículo novo que recebe o equipamento), não pra retirada — a versão anterior colocava tudo na primeira OS pras duas situações, o que está certo pra Transferência mas errado pra Substituição. **⚠ Superado em 2026-07-23:** materiais passaram a entrar nas DUAS OS da Substituição (ver seção "Atualização 2026-07-23" no fim).
- Transferência: 2 OS com o MESMO veículo, clientes diferentes (`cliente_id_destino` por placa) — a versão anterior só aceitava 1 `cliente_id` pro request inteiro.
- Alocação de item (`_alocar_itens_por_placa`) passou a respeitar `sem_bloqueio`: item de bloqueio só aloca nas placas elegíveis, não nos "N primeiros da lista".
- **Bug real achado no meio do caminho:** o frontend nunca mandava `itens` no payload de `/gerar-os` — só no preview visual. Na prática, nenhum material além do "ENTREGA OS" fixo era anexado nas OS geradas pelo wizard (mesmo com a lógica de vínculos/alocação já implementada e testada por curl em sessões anteriores). Corrigido junto com o resto.
- `solucaoTecnica` agora recebe contexto automático da extração (transferência detectada, etc.) com timestamp + separador `-------------`, orientando o técnico a preencher o resultado do serviço abaixo — não sobrescreve o uso real do campo (preenchido depois do atendimento).

**`gerar_os.html` — Etapa 3 virou um dry-run real do backend:** antes, o resumo mostrado na Etapa 3 era recalculado no JS, desconectado do que de fato seria enviado (era esse o motivo do bug dos itens nunca serem mandados). Agora `montarResumo()` chama `/gerar-os` com `confirmar:false`, mostra o resultado real (materiais alocados, avisos, preview do `solucaoTecnica`), guarda o payload exato e `gerarOs()` reenvia o mesmo payload só trocando `confirmar:true` — WYSIWYG entre o que se vê e o que é gerado. Também ganhou: revisão de itens x vínculo já na Etapa 1, aviso de transferência disfarçada, campo de cliente destino (Transferência), suporte a par saída/entrada (Substituição).

**Auditoria de segurança pós-implementação (pedido explícito do usuário):**
- **Achado e corrigido:** `gerar_os.html` e `usuarios.html` inseriam texto de PDF/Harmonit direto em `innerHTML` sem escapar — XSS real numa sessão autenticada com permissão de escrita no Harmonit. Função `escapeHtml()` adicionada e aplicada em todo ponto de interpolação nos dois arquivos.
- **Achado, não corrigido:** `/painel/api/login` sem rate limiting (nem Nginx, nem aplicação) — sem proteção a força bruta. MoviChat tem esse padrão (5 req/min via Nginx); FPSL não. Precisa de root pra mexer no Nginx, não fiz sem autorização.
- `auth.py`/`usuarios_router.py` revisados: bcrypt, JWT com expiração e claim de tipo, admin-gating — sem achado.

**Testado ponta a ponta via HTTP real** (login → extrair → gerar-os dry-run) pro caso de Substituição — 2 OS corretas, `solucaoTecnica` formatado certo, vínculos já cadastrados reconhecidos.

**Não testado ainda (até sessão 4):** interface visual num navegador de verdade.

---

## Atualização 2026-07-16 (sessão 6, continuação) — bug real de extração da Transferência + mudança de arquitetura + limpeza

**Contexto:** usuário usou a interface real pela primeira vez (Vínculos → Testar extração) e reportou "não deu" pros perfis Substituição e Transferência. Investigado com PDFs reais (`transferecia de cliente que ja existe.pdf` / `...que nao existe.pdf`, na pasta `C:\Users\Lenovo\Downloads\exe fpsl`).

**Bug real encontrado e corrigido — extração de Transferência estava completamente errada:** o perfil "transferencia" roteava pro parser de Rescisão (`_extrair_rescisao`), mas os documentos reais de Transferência (lado destino) são sempre **formato Cliente Novo/Aditivo** (coluna única "Veículo e Placa"), nunca Rescisão. Consequências do roteamento errado:
- Nome do cliente nunca era capturado (Rescisão usa padrão de prosa "Eu Fulano, da Empresa", que não existe nesses documentos)
- Tabela de itens não era reconhecida (Rescisão só procura cabeçalho "ACESSORIO"/"ITEM", mas o cabeçalho real é "Descrição")
- **Em documento com veículos listados em 2 colunas lado a lado (28 veículos), só a 1ª coluna era lida — 14 de 28 placas sumiam silenciosamente** (`idx_veic`/`idx_placa` em `_extrair_rescisao` usam `next()`, que só pega o primeiro índice)

**Fix:** `pdf_extractor.py::extrair_campos` — perfil "transferencia" agora roteia pro mesmo parser de Cliente Novo/Aditivo (`_extrair_item_veiculo`, com `tem_ficha_cadastral=True`, seguro mesmo quando o documento não tem essa página). Testado com os 2 PDFs reais: 28/28 placas (antes 14), cliente certo, CNPJ certo, itens com comodato certos. Rescisão (perfil próprio) e o caso disfarçado ("termo errado.pdf") continuam funcionando sem mudança — reconferido contra os 9 documentos completos da pasta de exemplos.

**Bug real corrigido em `os_router.py::buscar_cliente`:** `/ObterClientePorCpfCnpj` da Harmonit devolve uma **lista**, não um objeto único (apesar do nome do endpoint ser singular) — código fazia `r.get(...)` assumindo dict, quebrava com `AttributeError: 'list' object has no attribute 'get'` toda vez que alguém buscava cliente por CNPJ/CPF na Etapa 2 do wizard. Corrigido pra tratar lista e dict.

**Mudança de arquitetura confirmada pelo usuário — Transferência agrupada:** ver seção "Regra de negócio" no topo deste arquivo. `_montar_operacoes` em `os_router.py` ganhou um branch dedicado (`perfil.get("agrupado")`) que roda ANTES do loop por placa, construindo as 2 operações (retirada + instalação) de uma vez só, juntando todas as placas na descrição e somando os materiais.

**Formato de descrição da Substituição também ajustado:** `SUBSTITUIÇÃO RETIRADA: ...` / `SUBSTITUIÇÃO INSTALAÇÃO: ...` (antes: `Substituição/Retirada:` / `Substituição/Instalação:`).

**Comodato/Compra agora visível na UI:** campo `comodato_ou_aquisicao` (já extraído desde a sessão 4, mas nunca exibido) agora aparece como badge "Tipo" em Vínculos (Testar extração) e em Gerar OS (Etapa 1, revisão de itens).

**Aba "Registrar Oficina" removida, substituída por "Oficinas"** (auditoria + histórico + verificação pós-escrita na WESO) — detalhe completo em `docs/fpsl/14_Oficina_WESO_Sync.md`.

**Limpeza de infraestrutura local:** `C:\code\fpsl_weso` (mirror local) estava desatualizado em relação à VPS — `oficina.html`/`config.html`/`oficina_router.py` só existiam na VPS, `storage.py`/3 HTMLs estavam com conteúdo antigo. Sincronizado via scp (VPS é sempre a fonte viva). `C:\code\Bibliotecas API` (cópia duplicada de toda a doc Harmonit/WESO/FPSL, idêntica ao que já está na VPS) apagada.

**Ainda não testado:** interface visual num navegador de verdade (segue pendência desde a sessão 4) — nenhuma mudança de hoje foi clicada na UI real, só via script/API direta.

## Atualização 2026-07-23 (sessão 6) — Substituição exercitada na UI real (termo 8799 / MGA)

**Primeira vez que um fluxo do FPSL rodou na tela de verdade.** Usuário subiu um Termo de Substituição real (MGA, documento nº 8799) no perfil Substituição e caiu em 3 bugs — os 3 corrigidos e no ar (padrão de deploy validado; backups `pdf_extractor.py.bak_2026-07-23` e `os_router.py.bak_2026-07-23`). Detalhe de documento em `docs/fpsl/15_Particularidades_Documentos.md` (seção Substituição).

1. **`A DEFINIR` zerava o par (`pdf_extractor.py`).** O veículo de ENTRADA de uma substituição pode vir `A DEFINIR` (substituto ainda não escolhido). O código exigia as duas placas casando com o regex e descartava a linha inteira — perdia junto a placa de SAÍDA válida (`ERF 0325`), e a UI dizia "não reconhece placa". Novo helper `_placa_ou_texto`: aceita placa normalizada OU texto literal; só descarta célula vazia. **Decisão do usuário: `A DEFINIR` é placa válida e vai pra descrição como está.**

2. **Acessórios da Substituição nunca entravam na OS (`pdf_extractor.py`).** O perfil devolvia `itens: []`; os acessórios só saíam como texto em `pares[].acessorios_entrada`. Resultado: as 2 OS nasciam só com o `ENTREGA OS` fixo. Novo `_itens_acessorios_substituicao` quebra a célula de bullets `▶` em `itens`, **sem Tipo nem valor** → `_resolver_vinculos` resolve `comodato=False, cobrar=False` (regra do usuário: na substituição o acessório nunca é comodato nem cobrado). Vínculos já existiam: `BLOQUEIO VEICULAR`→45689 (produto), `CENTRAL 24 HORAS`→6976 (serviço). Nenhuma mudança de front foi necessária — `gerar_os.html:466` já manda `extraido.itens` pra todos os perfis.

3. **Materiais só na instalação → agora nas DUAS OS (`os_router.py`, `_montar_operacoes`).** A retirada nascia com `materiais: []`. **Decisão do usuário 2026-07-23:** a retirada também lista o equipamento (o que é REMOVIDO do veículo antigo); a instalação, o que entra no novo. Trocado o `[]` da retirada por `materiais_placa` (mesma referência de lista das duas OS — ninguém muta os dicts, `gerar_os` monta um `todos_materiais` novo por OS).

**Verificado na UI:** extração (1/1 placa, `ERF 0325` sai + `A DEFINIR` entra) e simulação (2 OS, 2 itens cada — Bloqueio Veicular + Central 24 horas — ambos sem comodato/cobrar). **Ainda falta gerar as OS reais** (`confirmar:true`) pra fechar o ciclo.

**Ressalva registrada (multi-par):** a agregação de acessórios usa lista global + quantidade, distribuída por ordem em `_alocar_itens_por_placa`. Se um termo tiver vários pares com acessórios DIFERENTES entre si, a alocação pode desalinhar. Os termos reais vistos têm o mesmo pacote em todos os pares, então não afeta hoje — fica a fronteira anotada.

## Atualização 2026-07-23 (continuação) — Rescisão grande, dedup de placa e redundância (RD) — termo 8788

Usuário testou uma Rescisão real (CONSTRUCTO, termo 8788, 26 veículos) e só saíam 12 OS — o "limite de 12" que ele reportou. Não era limite nenhum: a geração cria fielmente 1 OS por placa que recebe, e só 12 placas chegavam. Três correções, no ar (backups `pdf_extractor.py.bak2/bak3_2026-07-23`, `os_router.py.bak2_2026-07-23`). Documento em `15_Particularidades_Documentos.md`.

1. **Continuação de página no parser de Rescisão** (`pdf_extractor.py`) — a lista de veículos quebra pra página 2+ numa tabela SEM cabeçalho, que era ignorada (o fallback por texto só disparava com ZERO placas). `_eh_continuacao_veiculo_rescisao` reconhece a continuação (mesmo nº de colunas da tabela de veículos, sem palavras de tabela de itens) e `_processar_linhas_veiculo_rescisao` lê tudo. 8788: 12 → 26 veículos (19 com placa + 7 máquinas sem placa). Sem teto de placas. **Só a Rescisão tem esse tratamento hoje** — estender aos demais perfis é pendência.
2. **Dedup de placa repetida na geração** (`os_router.py`, `_dedup_placas`) — placa igual → 1 OS + aviso. Roda no começo de `gerar_os`, colapsa `body.placas` mantendo a 1ª ocorrência; o aviso entra em `avisos` e aparece no painel. Vale pra todos os perfis. (8788 listava 3 placas em 2 refs — erro do documento; 19 → 16 OS.)
3. **Marcador `(RD)` de redundância** (`pdf_extractor.py`, `_placa_formatada`) — mesmo veículo com 2 rastreadores vem marcado `(RD)` (antes/depois da placa) e na WESO são 2 registros. O extrator preserva o `(RD)` pra que o dedup NÃO junte os 2 equipamentos legítimos: `CUB 0764` ≠ `CUB 0764 (RD)` → 2 OS. Só conta `(RD)` entre parênteses colado à placa (`DRD 4189` não é redundância). **Não testado ainda com termo real que tenha RD** — validado contra o formato da WESO + regressão nos 9 exemplos.

## Atualização 2026-07-24 — reestruturação financeiro×operacional (E0/E1 + auditoria)

Início da reestruturação em que cada termo passa a gerar **N OS operacionais + 1 OS
financeira** (spec completa em `Movisat_canais/FPSL_SPEC_OS_financeiro_operacional.md`,
vira doc 16 quando validada ponta a ponta). Feito e validado até aqui:

- **E0 — geração real validada.** Primeira OS criada de verdade no Harmonit pelo padrão
  novo (nº **16532**, osId 845792, Pastelaria Velasco). Travou empiricamente: campo da
  situação = **`situacaoId`**; `SalvarOrdemServico` grava os **IDs da API** (não os
  números da tela); `SalvarMaterialOrdemServico` aceita **id de serviço** como `produtoId`;
  técnico via `SalvarTecnicoOrdemServico {id,empresaId,osId,tecnicoId}`. **Corrige o status
  antigo "geração real não testada".** Números guardados em `Movisat_canais/OS_validacao_tipos.md`
  (não excluir — servem pra validar Oficina→WESO).
- **E1 — Tipo passa a ser sempre Contrato.** `tipoId` deixa de ser por perfil (era
  Instalação 76 / Retirada 57 / ...) e vira fixo **Contrato = 2** em toda OS; a operação
  agora vive no **Problema + Produto/Serviço**. Payload ganha **`situacaoId`** (Nova
  sollicitação = 38 na operacional). Constantes em `templates_config.py`
  (`TIPO_CONTRATO_ID`, `SITUACAO_*`, bloco `FINANCEIRO_*`). **Os `tipo_id*` dos PERFIS
  ficam SUPERSEDED** (mantidos só como referência; a seção "Mapeamento perfil → Harmonit"
  acima está desatualizada nesse ponto). Override aplicado em `os_router.gerar_os`.
- **Auditoria + A-1 (rótulo do resumo).** O rótulo "Retirada/Instalação" da Etapa 3
  (`gerar_os.html`) estava morto desde antes (comparava `op.tipo_id` com
  `PERFIS[perfil].tipo_id_retirada`, que o endpoint `/perfis` nunca devolveu → sempre caía
  no label genérico). Corrigido: `_montar_operacoes` emite **`rotulo`** por operação
  ("Retirada"/"Instalação"/label do perfil) e o front consome `op.rotulo`.

**Ainda pendente:** E3 (builder da financeira + fase dupla + campo "motivo" de saldo 0) e
E4 (encargos da rescisão). Enquanto isso **não gerar OS real** — a financeira ainda não é
gerada (só os perfis de titularidade já saem completos, ver E5 abaixo).

### E2 — Split de itens (validado em dry-run)

`gerar_os` passou a separar os itens resolvidos: **operacional** recebe só o que NÃO é
cobrança (comodato + itens sem-flag) **+** a linha do Produto/Serviço do painel **sem flag**
**+** ENTREGA OS; os itens de **cobrança** (`cobrar=True`) são coletados à parte e devolvidos
no dry-run como `financeiro_itens_preview` (a OS financeira em si vem na E3). Regra:
`cobrar=True` → financeira; senão → operacional. Helpers `_material_fixo` /
`_materiais_operacional`. O envio de material virou **WYSIWYG** (dry-run == real): a lista
final — serviço + alocados + ENTREGA OS — é a mesma montada no dry-run e gravada no Harmonit
(antes o ENTREGA OS só era prepended na geração real). `quantidade` passou a respeitar
`mat["quantidade"]`. **Validado:** cliente novo com rastreador/chip/bloqueio (COMODATO) +
adesão (Mensal, R$150) → operacional com os 3 comodatos + serviço + ENTREGA OS, e a adesão
sozinha no `financeiro_itens_preview`.

### E5 — Transferência de titularidade: 2 perfis (validado com 8580/8581 reais)

O perfil único `transferencia` (agrupado) foi **removido** e substituído por dois, porque na
prática são **2 documentos separados**:
- **`transferencia_novo_titular`** (documento formato Cliente Novo, ex.: 8580) → **1 OS
  híbrida**: financeiro + comodato JUNTOS na mesma OS (sem split), qtd acompanhando os itens,
  independe do nº de placas. Situação **Financeiro (15746)** + técnico **Karla (9617)**.
  Descrição cita o **termo anterior**.
- **`transferencia_antigo_titular`** (documento formato Rescisão, ex.: 8581) → **1 OS, só
  comodato, SEM financeira e SEM técnico**. Situação Nova sollicitação (38). Descrição cita o
  **termo posterior**.

`pdf_extractor.extrair_campos` roteia novo→`_extrair_item_veiculo` (com ficha),
antigo→`_extrair_rescisao`. Novo campo **`termo_relacionado`**: o nº do contrato do OUTRO
lado, lido de dentro da frase de transferência. **2 bugs reais achados na validação e
corrigidos:** (1) a nota do novo titular fica numa **célula de tabela** (coluna Tipo do item),
fora do `extract_text` — passei a varrer também os `comodato_ou_aquisicao` dos itens; (2) o
regex da frase exigia "n" antes do número, mas a nota vem "contrato 3622" sem "nº" — "n"
virou opcional. **Validado:** 8580→`termo_relacionado` 3622, 8581→8580; geração das 2 OS com
os campos certos; **regressão** conferida em cliente novo / rescisão (19 placas) /
substituição (1 par) — sem quebra. Builders `_montar_novo_titular` / `_montar_antigo_titular`;
front passa `termo_relacionado`.

> ⚠ O branch `agrupado` em `_montar_operacoes` ficou **órfão** (nenhum perfil usa `agrupado`
> agora) — inofensivo (guardado por `perfil.get("agrupado")`), remover numa limpeza futura.

### E3 — OS financeira + fase dupla (validado com OS reais 16533/16534)

Nos perfis padrão (cliente novo, aditivo, upgrade, rescisão, substituição) `gerar_os` passou a
montar **1 OS financeira por termo** (`_montar_financeira`): Tipo Contrato (2), Problema
**FINANCEIRO 11701**, Situação **Financeiro 15746**, Produto/Serviço **FINANCEIRO 606037**,
técnico **Karla 9617**; corpo = itens de cobrança (flag Cobrar) + ENTREGA OS; descrição =
termo + placas + todos os itens (referência). **Saldo 0** (sem cobrança): gera mesmo assim —
só ENTREGA OS — e a descrição informa o **motivo** (campo novo `motivo_financeira_zero` no
painel: "por conta do técnico / acordo interno / liberado pela gestão"); se saldo 0 e motivo
vazio, sai um aviso.

**Geração real virou fase dupla:** fase 1 cria as operacionais colhendo os `numeroOrdem`;
fase 2 cria a financeira com esses números na `solucaoTecnica`. Técnico é anexado por
`SalvarTecnicoOrdemServico` (financeira e novo titular). Helper único `_criar_uma_os` (OS +
materiais + técnico, sem derrubar as outras se uma falhar); `produto_servico_id` e
`situacao_id` passaram a ser por-OS. **Validado real** (Pastelaria Velasco): 16533 operacional
+ 16534 financeira; a financeira leu de volta `situacaoId=15746`, `problema=11701`,
`produtoId=606037`, técnico Karla, e `solucaoTecnica="...1 OS de instalação/serviço geradas
neste termo: nº 16533"`. OS mantidas (registro em `OS_validacao_tipos.md`).

### E4 — Encargos da rescisão → financeira (validado com 8788 real)

O parser de Rescisão passou a ler a **tabela de encargos** (`DESCRIÇÃO` + `CONDIÇÃO DE
PAGAMENTO`/`TOTAL GERAL`), que antes era pulada de propósito — é ela que gera o financeiro
(a tabela de acessórios é toda comodato, volta). `_extrair_encargos_rescisao`: descrição +
valor = **TOTAL GERAL** pegando o **valor ATIVO** (`_valor_ativo`, último valor da célula —
trata o riscado, ex.: taxa "R$ 299,00 R$ 0,00*" → 0,00); qtd=1 (o total geral já é do termo);
só emite encargo com **valor > 0** (taxa zerada/assumida pelo cliente é descartada).
`comodato_ou_aquisicao=None` → `_resolver_vinculos` resolve `cobrar=valor>0` → financeira.

**Vínculos criados** (`painel_vinculos_itens`): `90 DIAS DE AVISO PRÉVIO DE CANCELAMENTO`→
**16033** (serviço AVISO PRÉVIO), `TAXA DE RETIRADA`→**7277** (RETIRADA CLIENTE). ⚠ Vínculo é
**exato-normalizado**: outra redação de aviso prévio (ex.: "AVISO PRÉVIO DE CANCELAMENTO" sem
"90 DIAS") precisa do seu vínculo — o painel avisa (409) quando aparecer um não mapeado.

**Validado** (8788, Pastelaria Velasco, dry-run): a financeira recebeu `90 DIAS DE AVISO
PRÉVIO DE CANCELAMENTO` (16033, cobrar, R$ 6.447,48) + ENTREGA OS; os comodatos
(rastreador/chip/leitor) ficaram nas OS de retirada; a TAXA DE RETIRADA (R$ 0) foi descartada.

---

### Prioridade da OS (2026-07-24, validado com OS reais)

Antes o painel **não** enviava prioridade — o Harmonit assumia 382 (Normal) sozinho. Agora há
um **seletor de prioridade na Etapa 2** (endpoint `/painel/api/prioridades` → proxy de
`/PrioridadeAtendimento/ObterPrioridades`: 381 Baixa · 382 Normal · 383 Alta · 384 Urgente),
default **Normal**. Campo do payload = **`prioridadeId`** (não `prioridade` — esse é ignorado;
confirmado ao vivo). **Só as OS operacionais** usam a prioridade escolhida; **a financeira sai
sempre Normal** (decisão do usuário). Validado real: cliente novo prioridade Alta → operacional
16536 gravou 383, financeira 16537 gravou 382.

## Estado após E1–E5 (2026-07-24)

Pipeline financeiro×operacional **completo e validado** (E1 Tipo Contrato + situação; E2 split;
E3 financeira + fase dupla + saldo 0/motivo; E4 encargos rescisão; E5 titularidade). Falta:
**gerar o conjunto "1 por tipo" real** na Pastelaria Velasco (só o par cliente novo 16533/16534
existe) e **E6 — Oficina→WESO** (com o rastreador `356354872124749` / linha
`8955170220424545007F`). O branch `agrupado` órfão em `_montar_operacoes` fica pra limpeza.

---

## Atualização 2026-08-14 (tarde) — quatro defeitos que só o uso encontrou

🚨 **Todos os quatro foram achados pelo usuário clicando, não por teste meu.**
Três eram invisíveis: nenhum log, nenhuma mensagem, nenhum sinal.

### 1. A extração morreu em todos os 7 perfis de contrato

Ao trocar a caixa de progresso para receber uma **lista de etapas**, ficou uma
chamada passando **texto**. String tem `.length` mas não tem `.map`, então
estourava `TypeError` **antes do `fetch` e fora do `try`**: sem alerta, sem log,
botão travado, tela parada. O termo 8842 (rescisão de **uma placa só**, caso que
não existia entre os 9 exemplos) virou fixture do projeto.

🚨 **Teste que confere se a função EXISTE não pega argumento do tipo errado.** A
função existia; errado era o que se passava para ela. Ver `18_Testes.md`.

### 2. "Manutenção dá erro" era o 504 do nginx

Não era o fluxo, era tempo: 43s contra `proxy_read_timeout 35s`. História
completa e medições em **`24_Desempenho_e_Timeout.md`**.

### 3. "Erro json" era a página HTML do 504

A tela chamava `res.json()` na página de erro do nginx. Agora a resposta é lida
como **texto** e só então convertida, e cada código vira mensagem útil — com a
frase que importa: **"Nenhuma OS foi criada"**.

⚠️ `gerarOs()` não conferia `res.ok`. Num erro, o operador ficava sem saber se
alguma OS tinha sido criada.

### 4. Comodato saindo com valor patrimonial R$ 0,00

`produto_do_modelo` devolve `row[2] or 0.0`, então de-para **sem valor** — que é
o caso de **todos os modelos 2G** — chegava como `0.0` e não como `None`. A
herança do valor do contrato testava `is not None` e nunca disparava.

🚨 **Zero ali não é "vale nada", é "não sei"** — e esse número vai para a
**DANFE de comodato**. Valia para Cliente novo, Aditivo, Rescisão e Substituição,
não só para o perfil onde apareceu. Corrigido e travado por teste: o ST310U
volta a sair com R$ 1.100,00 nas duas OS.

### E a tela de placas saiu

Aba, `frontend/placas.html`, rota `/painel/placas` e `placas_router` removidos
(`cf16837`). Era permissão que não protegia nada — o router sempre pediu
`gerar_os`. Medido antes de apagar: **1 abertura por usuário real e zero criação
de placa em 6 dias**; os recipientes `-MANUT`/`-UPGRADE` nascem no sistema da
WESO. Continua existindo `fpsl_weso/placas.py`, que é **regra de formatação de
placa** — outra coisa, com 72 testes.
