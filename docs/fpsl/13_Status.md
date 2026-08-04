# 13 — Status do Projeto e Próxima Fase

**Atualizado em:** 2026-07-29

---

## Entrou em 2026-07-29

| O quê | Estado |
|---|---|
| **Cache local da base WESO** (`/home/claude/weso_cache`) | prod — 1.964 veículos, 3.748 rastreadores, 4.070 chips, 298 clientes; cron 04:15 |
| **Aba Placas** (`/painel/placas`) | prod — confere quais placas do termo existem e cria as que faltam |
| **Leitura tolerante a grafia** (`weso_lookup.py`) | prod — consulta direta e, se vazia, casa contra a base por chave normalizada |
| **Nº de série real na descrição da OS** | prod — em TODOS os perfis (antes só o agrupado; os demais mandavam o literal) |
| **Financeira embutida na rescisão** | prod — cobrança vai em cada OS de placa, sem OS agregada |
| **Antigo titular sem flags** | prod — todos os itens, sem flegar comodato nem cobrança |
| **`A_DEFINIR_<termo>` + apelido `TERMO:<termo>`** | prod — no extrator, todos os perfis |
| **Alerta de divergência em 2 níveis** | prod — erro para rastreador/chip (1:1 com placa), informativo para acessório |
| **Placa FANTASMA** (`FIAT/UNO 2019`) | corrigido |
| **110 placas normalizadas na WESO** | feito — 108 aplicadas, 2 em colisão deixadas de propósito |
| **Trava de `.bak`/`.py` no nginx** | prod — 15 arquivos estavam públicos em `/painel/static/` |


## Entrou em 2026-07-29 (segunda metade da sessão)

| O quê | Estado |
|---|---|
| **Aba Serviços Harmonit** (`/painel/harmonit-historico`) | prod — audita tempo, erro e resposta vazia de toda chamada |
| **Instrumentação do `harmonit_client`** | prod — mede no ponto único (`_executar`), retenção 30 dias |
| **Cadastro de cliente no Harmonit** (P1) | prod — `/painel/api/clientes/previa` e `/criar` |
| **Módulo de CEP** (`fpsl_weso/cep.py`) | prod — resolve IBGE e detecta fuso |
| **Financeira embutida na rescisão** | prod |
| **Antigo titular sem flags** | prod |
| **`A_DEFINIR_<termo>` + apelido `TERMO:<termo>`** | prod |
| **Motivo obrigatório com cobrança zerada** | prod — corrigido nos dois caminhos |
| **Limpeza da árvore** | 64 `.bak` e 45 scripts avulsos para `backups/` |

### Auditoria dos serviços Harmonit — a decisão que faz ela servir

Grava **toda** chamada, mas classifica em três:

```
ok      resposta boa
vazio   "OS não encontrada" — NORMAL na varredura, não conta como falha
erro    falha de verdade
```

A numeração de OS do Harmonit é global e **tem buracos**; a varredura sonda
números sequencialmente e a maioria volta vazia por natureza. Sem essa
separação o painel mostrava **76% de falha num sistema saudável** — exatamente
o ruído que se aprende a ignorar. Medido em produção:

```
OrdemServico    vazio   330x   média 185ms
OrdemServico    ok      101x   média 162ms
```

**Não há alerta por timeout isolado**, de propósito. O sinal de evento é o
**disjuntor**: quando ele abre, aconteceu algo. Ele aparece no topo da tela.

Resumo usa **mediana e p95**, não média — média esconde cauda longa, e cauda
longa é o problema do Harmonit.

### Cadastro de cliente: o que destravou

`codigoIBGE` é exigido pelo Harmonit e **não vem no termo**. Resolvido por CEP:

- **ViaCEP é primária** porque é a que tem o campo `ibge`
- **BrasilAPI v2 é reserva e NÃO tem IBGE** (conferido: devolve só
  cep/state/city/neighborhood/street)
- Sem IBGE, o endpoint **recusa** com mensagem clara em vez de mandar payload
  incompleto (Fernando de Noronha é o caso real)

**Fuso horário** sai do mesmo lookup, por decisão do usuário: cliente fora de
UTC-3 vê horário de evento diferente do nosso, e isso precisa aparecer no
cadastro. Fuso por UF, com ressalvas anotadas (sudoeste do AM é UTC-5;
Fernando de Noronha é UTC-2).

🚨 **O Harmonit responde "não encontrado" em formato DIFERENTE de "encontrado":**

```
existe      → list  [{"id": 998063, ...}]
não existe  → dict  {"errorMessage": null, "message": null, "data": []}
```

O dict de não-encontrado é *truthy*. Tratar a resposta como verdade fazia a
prévia dizer que **todo documento já existia** — inclusive um CPF inventado — e
o cadastro nunca aconteceria. O que decide é a lista: `r` ou `r["data"]`.

---

## Ganho medido

```
serial de 23 placas   antes: 15 a 90 s (WESO)      agora: ~1 ms (cache)
busca por placa suja  antes: 0 resultados          agora: acha em 4 grafias
```

## O que a WESO impõe (medido, não suposto)

- O tempo de resposta **cresce com o tamanho da consulta e tem cauda longa**:
  a base de veículos varia de 2,3s a 24s; a de rastreadores, de 11,6s ao
  timeout. Por isso o cache, e por isso o construtor dele tem timeout próprio
  de 240s com 3 tentativas — herdar o corte de 30s do client fazia o build
  falhar.
- **Não existe vínculo veículo ↔ cliente** em nenhuma das duas direções.
  `ficha()` devolve `cliente: None` com o motivo explícito.
- `/Veiculos/Consultar?placa=` é **igualdade exata** e devolve lista vazia (não
  erro) quando a grafia diverge — falha silenciosa.

---

## Estado atual

### Implementado e em produção na VPS

| Componente | Estado |
|---|---|
| Routers: clientes, simcards, rastreadores, veiculos, os, onboarding | prod |
| Auth `X-FPSL-Key` em todas as rotas | prod |
| SQLite com tabelas: veiculos + clientes + rastreadores | prod |
| `harmonit_client.py` — token Bearer, retry 401, timeout 30 s | prod |
| Translators: `situacao_cliente`, `tipo_veiculo` (mapeamento corrigido) | prod |
| Logger estruturado JSON (sem credenciais) | prod |
| `.env` com 6 vars, permissão 600 | prod |
| Serviço systemd `fpsl-weso.service` rodando como usuário `claude` na porta 8004 | prod |
| Nginx proxy reverso na porta 8005 — timeout geral 35s, `/weso/onboarding` 120s | prod |
| `POST /weso/veiculos/local` — rota de recuperação de veiculo_id perdido | prod |
| Docs 00–13 em `/home/claude/fpsl_weso/docs/fpsl/` | prod |
| Auditoria de segurança + 7 bugs corrigidos | prod |

---

## Pendente (em ordem de prioridade) — **DESATUALIZADO, ver Sessão 5 no fim do arquivo**

> Itens 1-4 abaixo foram resolvidos ou tiveram a premissa corrigida em 2026-07-16 -- mantidos aqui só como histórico de como o plano evoluiu. Não seguir esta tabela sem ler a Sessão 5.

| # | Item | Bloqueador | Status real (16/07) |
|---|---|---|---|
| 1 | Credenciais Harmonit no `.env` | Solicitar `CLIENT_ID` e `SECRET_ID` ao suporte Harmonit | ✅ Resolvido há semanas -- API Harmonit em uso ativo diário |
| 2 | HTTPS + domínio | DNS apontado + root executa certbot | ✅ Ativo, `fpsl.movisat.com.br`, cert válido até 12/10/2026 |
| 3 | Webhook URL no painel Harmonit | HTTPS ativo (item 2) | ❌ **Premissa abandonada** -- nem Harmonit nem WESO têm webhook; resolvido com sincronização manual (ver Sessão 5) |
| 4 | Teste end-to-end Harmonit→FPSL→WESO | Todos os anteriores | ✅ Feito de forma diferente do plano original -- ver Registrar Oficina na Sessão 5 |
| 5 | Rate limiting Nginx | Pós-HTTPS (ver `11_Seguranca.md` P2) | Aplicado (ver `nginx_fpsl.conf`, `limit_req zone=fpsl_login`) |
| 6 | Logrotate | Baixa urgência (ver `11_Seguranca.md` P3) | Aplicado (`/etc/logrotate.d/fpsl-weso`) |
| 7 | Integração Fulltrack | Futura — rotas `/fulltrack/...` + `services/fulltrack/` | Ainda não iniciada |

---

## Fluxo de ativação esperado

```
1. Solicitar credenciais Harmonit → preencher .env na VPS
        ↓
2. Apontar DNS do domínio → root executa: certbot --nginx -d dominio.com
        ↓
3. Cadastrar webhook no painel Harmonit:
       AdicionarOficina   → https://dominio.com/weso/os/adicionar
       DesinstalarOficina → https://dominio.com/weso/os/desinstalar
        ↓
4. Teste ponta a ponta com evento real do Harmonit
```

---

## Todos os endpoints disponíveis

```
POST   /weso/clientes               — cadastrar cliente
POST   /weso/simcards               — cadastrar SIM card
POST   /weso/rastreadores           — cadastrar rastreador
POST   /weso/veiculos               — cadastrar veículo (via placa + CNPJ + serial)
GET    /weso/veiculos/local         — listar veículos no SQLite local
POST   /weso/veiculos/local         — registrar manualmente placa→veiculo_id (recuperação)
PUT    /weso/veiculos/{id}          — atualizar veículo
DELETE /weso/veiculos/placa/{placa} — excluir veículo por placa
DELETE /weso/veiculos/{id}          — excluir veículo por ID WESO
POST   /weso/onboarding             — fluxo completo em sequência (timeout 120s)
POST   /weso/os/adicionar           — endpoint reserva (NÃO é webhook real -- ver Sessão 5), toggle oficina_registro_ativo
POST   /weso/os/desinstalar         — endpoint reserva (idem)
```

Todos os endpoints acima exigem `X-FPSL-Key: <chave>` no header.

### Rotas do painel (JWT, não `X-FPSL-Key`)

```
GET  /painel/api/oficina/buscar?numero_os=X   — lê OS + eventos de Oficina do Harmonit
POST /painel/api/oficina/sincronizar          — sincroniza eventos pendentes com a WESO
GET  /painel/api/config/ativo                 — le o toggle oficina_registro_ativo (admin)
PUT  /painel/api/config/ativo                 — altera o toggle (admin)
```

Ver `14_Oficina_WESO_Sync.md` pro desenho completo dessa feature.

---

## Variáveis de ambiente (.env na VPS)

| Var | Estado |
|---|---|
| `WESO_API_KEY` | preenchida |
| `WESO_BASE_URL` | preenchida |
| `FPSL_SECRET_KEY` | gerada com openssl rand -hex 32 |
| `HARMONIT_BASE_URL` | preenchida |
| `HARMONIT_CLIENT_ID` | preenchida (corrigido em 2026-07-16 -- doc antiga dizia vazia, mas a API já estava em uso ativo há semanas) |
| `HARMONIT_SECRET_ID` | preenchida |

---

## Catálogo WESO — dados confirmados em teste

| Item | Valor correto |
|---|---|
| Modelo Suntech ST 310 | `"Suntech ST310"` |
| tipoEqp Automóvel | `1` |
| tipoEqp Caminhão | `2` |
| tipoEqp Caminhonete | `3` |
| tipoEqp Motocicleta | `5` |

---

## Bugs corrigidos na auditoria (2026-06-15)

| # | Arquivo | Correção |
|---|---------|----------|
| 1 | `translators/weso.py` | Mapeamento `tipo_veiculo` corrigido (moto→5, caminhao→2, caminhonete→3, carreta→8) |
| 2 | `veiculos.py` | `DELETE /{id}` agora limpa o storage local |
| 3 | `client.py` | `_parse_date` suporta `/Date(ms±HHMM)/` |
| 4 | `fpsl_weso/main.py` | Arquivo órfão deletado |
| 5 | `onboarding.py` | Validação cruzada serial antes de qualquer chamada |
| 6 | `rastreadores.py` | `PUT /chip` migrado de query param para body JSON |
| 7 | `veiculos.py` | Dead code removido em `DELETE /placa/{placa}` |
| N1 | `nginx_fpsl.conf` | `/weso/onboarding` com timeout 120s (era 35s) |
| N2 | `veiculos.py` | `POST /weso/veiculos/local` para recuperar veiculo_id perdido |

---

## Verificação rápida do estado

```bash
# Como claude:
systemctl --user status fpsl-weso
curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/weso/veiculos/local
# 422 = Nginx + uvicorn OK; 000 = Nginx fora; 502 = uvicorn fora
```

---

## Sessão 2 — 2026-06-15 (fim)

### Descobertas

- **W7** — `GET /Rastreadores/Consultar` bloqueado por anti-hijacking (igual W3). `POST /Rastreadores/Consultar` retorna 404. Causa: `cadastrar_veiculo` falhava na etapa de lookup do rastreador_id.
- **W8** — `POST /Veiculos/Consultar` retorna 404 — endpoint inexistente.
- **W9** — `POST /Rastreadores/Atualizar` com payload mínimo `{"id": N}` retorna 500.
- IAG0T01 é pré-existente na WESO (não criado pelo FPSL). veiculo_id desconhecido.
- Rastreador 49175 preso em estado "em uso" — bloqueia novos veículos com esse serial.

### Código desenhado, não aplicado

Correção W7 (3 arquivos: storage.py + rastreadores.py + veiculos.py) — ver seção X de `10_Inconsistencias.md`.

---

## Sessão 3 — 2026-06-17

### Verificações

- **Rastreador 49175 liberado** — `POST /weso/rastreadores {"numeroSerie": "007559809"}` retornou `ja_existe, id: 49175`. Exclusão de IAG0T01 pelo painel WESO liberou o equipamento conforme esperado.
- **W7 — confirmado, abordagem revisada** — `GET /Rastreadores/Consultar` ainda inacessível (timeout 15s). Abordagem reformulada: solicitar ao suporte WESO exportação `serial + weso_id` para seed inicial da tabela `rastreadores_serials`; código mantém para novos cadastros. Mesma demanda para veículos (`placa + veiculo_id`).
- **WESO instável para criação nova** — `POST /Rastreadores/Cadastro` com serial inédito retornou timeout. Cadastro de rastreador já existente (`ja_existe`) funcionou normalmente.
- **Item 3 (onboarding IAG0T01) — desativado.**

### Próxima sessão — sequência

1. Solicitar ao suporte WESO: CSV de rastreadores (`serial, id`) e veículos (`placa, id`)
2. Aplicar código W7 (3 arquivos: `storage.py` + `rastreadores.py` + `veiculos.py`) + seed via CSV
3. Retomar fila principal: Harmonit creds → HTTPS → webhook → E2E

---

## Sessao 4 — 2026-06-17

### Implementado

- **Sync inadimplencia** (Harmonit -> WESO) — `services/sync_inadimplencia.py`
  - Asyncio background task (`loop_inadimplencia`) no lifespan — nunca depende de cron externo
  - Acorda a cada 10 min; executa se hora >= 05:00 BRT e nao rodou hoje
  - Toggle ON/OFF via config SQLite (`inadimplencia_sync`); default `"false"`
  - Toggle OFF nao desfaz inadimplentes ja marcados, apenas suspende novas marcacoes
  - `grace_days = 7` (default configuravel em runtime via `inadimplencia_grace_days`)
  - Erros por CNPJ isolados — falha individual nao para o loop
  - `run_sync()` separado do loop — chamavel diretamente para teste/operacao manual

- **Router admin** — `routers/admin.py`
  - `GET /admin/config` — lista todas as chaves de config
  - `PUT /admin/config/{chave}` — altera qualquer config sem restart
  - `POST /admin/sync/inadimplencia` — disparo manual (ignora toggle e horario)

- **Storage config** — tabela `config` adicionada ao SQLite via `init_db()`
  - `get_config(chave, default)` / `set_config(chave, valor)` / `listar_config()`
  - `listar_clientes()` adicionado (iteracao no sync)

### Pendencias restantes (em ordem)

1. Credenciais Harmonit — `HARMONIT_CLIENT_ID` e `HARMONIT_SECRET_ID` no `.env` (aguardando suporte)
2. Ligar sync — `PUT /admin/config/inadimplencia_sync {"valor": "true"}` apos ter credenciais
3. HTTPS + dominio — certbot apos DNS apontado (root: `certbot --nginx -d dominio.com`)
4. Webhook URL no painel Harmonit — apos HTTPS
5. Teste E2E — Harmonit -> FPSL -> WESO
6. Rate limiting Nginx (11_Seguranca.md P2)
7. Logrotate (11_Seguranca.md P3)
8. Seed CSV WESO — aguardando CSV de rastreadores e veiculos do suporte WESO

---

## Sessao 4 (continuacao) — Auditoria 2026-06-17

### Corrigidos

**Criticos:**

- **C1** `sync_inadimplencia.py:14` — `int(grace_days_str)` envolto em try/except; fallback para 7 se valor invalido
- **C2** `clientes.py:57` — translator `situacao_cliente()` aplicado tambem no `POST /weso/clientes` (era so no PUT)
- **C3** `harmonit_client.py` — `_token = None` apos qualquer HTTPException em `harmonit_get`; token sera renovado na proxima chamada em vez de entrar em loop de falha permanente

**Moderados:**

- **M1** `client.py` — `stop_client()` agora seta `_client = None` apos fechar (alinhado com `stop_harmonit_client`)
- **M2** `veiculos.py:76` — substituido `not body.X` por `body.X is None` em 4 campos opcionais do payload; valor 0.0 e string vazia agora sao enviados corretamente
- **M3** `os.py` — removido passo 3 inteiro (buscava toda frota Harmonit para obter tipoEqp de um veiculo); `GET /Veiculo/ObterVeiculos` nao suporta filtro; tipoEqp e campo opcional na WESO
- **M4** `admin.py` — `PUT /admin/config/{chave}` agora valida: `inadimplencia_grace_days` deve ser inteiro >= 1; `inadimplencia_sync` aceita apenas "true" ou "false"
- **M5** `rastreadores.py` + `storage.py` — `GET /weso/rastreadores/{id}` agora consulta storage local primeiro (`buscar_serial_por_weso_id`); fallback WESO so se serial nao encontrado localmente (evita timeout W7)

**Baixos:**

- **L1** `client.py` — linha em branco extra removida (artefato da remocao anterior)
- **L2** `harmonit_client.py` — `harmonit_post` removido (zero usos em todo projeto)
  > ⚠️ **DESATUALIZADO (revisado 2026-07-22):** `harmonit_post` voltou e está em uso em `painel/routers/os_router.py:411` (`SalvarOrdemServico`) e `:421` (`SalvarMaterialOrdemServico`).

### Resultado dos testes

10/10 PASS (C1 confirmou fallback; M4 rejeita valores invalidos; M5 retorna serial via storage sem chamar WESO)

---

## Ações Externas Pendentes

Itens que dependem de terceiros ou de acesso root. Nenhum bloqueia o FPSL em si — apenas a ativação completa da integração.

### 1. Credenciais Harmonit
**Responsável:** Suporte Harmonit
**Ação:** Obter `HARMONIT_CLIENT_ID` e `HARMONIT_SECRET_ID`
**Após receber:**
```bash
# Editar .env na VPS
nano /home/claude/fpsl_weso/.env
# Adicionar:
# HARMONIT_CLIENT_ID=valor
# HARMONIT_SECRET_ID=valor

systemctl --user restart fpsl-weso
# Ligar sync:
curl -X PUT http://localhost:8005/admin/config/inadimplencia_sync \
  -H "X-FPSL-Key: $FPSL_SECRET_KEY" -H 'Content-Type: application/json' \
  -d '{"valor": "true"}'
```

### 2. CSV de Seed WESO
**Responsável:** Suporte WESO
**Ação:** Solicitar exportação de rastreadores (`serial, id`) e veículos (`placa, id`)
**Após receber:**
```bash
cd /home/claude/fpsl_weso
python3 seed_csv.py rastreadores rastreadores.csv
python3 seed_csv.py veiculos     veiculos.csv
```

### 3. HTTPS + Domínio
**Responsável:** Operador (requer root)
**Pré-requisito:** DNS do domínio apontado para o IP da VPS
**Ação:**
```bash
ssh vps-root
certbot --nginx -d dominio.com
# Certbot edita o nginx automaticamente e configura renovação automática
```

### 4. Rate Limiting e Hardening Nginx
**Responsável:** Operador (requer root)
**Fazer na mesma sessão root do HTTPS**
**Referência:** `docs/fpsl/11_Seguranca.md` (itens P2 e P3)

### 5. Webhook URL no Painel Harmonit — ❌ ABANDONADO (2026-07-16)
**Motivo:** investigação exaustiva (Swagger completo + toda documentação, Harmonit e WESO) confirmou que **nenhum dos dois sistemas tem webhook de saída**. `AdicionarOficina`/`DesinstalarOficina` são endpoints que o app de campo do Harmonit CHAMA, não eventos que o Harmonit dispara pra fora.
**Resolvido de outra forma:** ver Registrar Oficina na Sessão 5 -- sincronização manual, operador busca a OS no painel FPSL depois de salvar no Harmonit e clica Sincronizar com WESO.

### 6. Teste E2E
**Pré-requisito:** Credenciais Harmonit + HTTPS + Webhook configurado
**Fluxo:** Criar OS no Harmonit → verificar veículo criado na WESO via WeFleet

---

## Sessão 5 — 2026-07-16

### Correção de premissa: webhook Harmonit→FPSL abandonado

Investigação completa (Swagger oficial, 90 endpoints + toda a documentação local, Harmonit e WESO) confirmou: **nenhum dos dois sistemas tem mecanismo de webhook de saída, nem endpoint de listagem/busca por data**. `POST /OrdemServico/AdicionarOficina` é um endpoint que o app de campo do Harmonit CHAMA pra registrar a instalação -- não é um evento que o Harmonit dispara sozinho pra avisar terceiros.

**Decisão de arquitetura:** o operador continua registrando a Oficina na tela **nativa do Harmonit** (não foi replicada). Depois de salvar lá, o operador usa o painel FPSL pra buscar a OS pelo número e clicar **Sincronizar com WESO** -- gatilho manual, sem polling, sem fila de retry com backoff (erro passageiro = clica de novo). Ver `09_Harmonit_WESO.md` (atualizado) e `14_Oficina_WESO_Sync.md` (novo) pro desenho completo.

### Feature nova: Registrar Oficina (Harmonit → WESO, sincronização manual)

Implementada e testada de ponta a ponta com dados reais (cliente/veículo/rastreador de teste `TESTEIAGO`, incluindo 1 teste real de gravação na WESO -- rejeitado corretamente por dado de teste inválido, confirmando que o tratamento de erro funciona).

- `fpsl_weso/painel/routers/oficina_router.py` (novo) -- `GET /painel/api/oficina/buscar`, `POST /painel/api/oficina/sincronizar`, `GET/PUT /painel/api/config/ativo`
- `fpsl_weso/storage.py` -- tabela `oficinas_processadas` (dedup), + `buscar_harmonit_rastreador_por_serial` (não usado por essa feature, mas útil como utilitário genérico)
- `fpsl_weso/routers/os.py` -- `adicionar_oficina`/`desinstalar_oficina` (endpoints antigos, mantidos intactos, agora com o toggle `oficina_registro_ativo` -- servem só como endpoint de webhook caso o Harmonit confirme essa capacidade no futuro; NÃO são reaproveitados pela feature nova, que já tem o serial direto do evento de Oficina e não precisa da tabela local `rastreadores`)
  > ⚠️ **REVISTO EM 2026-07-22:** com o desenho novo (registrar a oficina DENTRO da OS é o gatilho, decidido pelo usuário), esses endpoints passam a ser **exatamente o que serve** — `/weso/os/adicionar` já recebe `osId` + `rastreadorId` + `placaVeiculo`, resolve serial e `cnpjcpf` e grava o vínculo WESO. O que falta é o painel chamá-los e acrescentar a chamada ao `AdicionarOficina` do Harmonit (o comentário de `routers/os.py:76` diz que o Harmonit sempre recebe, mas o código nunca chama — fazia sentido como webhook, não faz mais).
- `frontend/oficina.html` + `frontend/config.html` (novos) -- nav atualizado nas 5 páginas do painel
- **Interruptor `oficina_registro_ativo`** (config, default `false`) -- protege tanto a leitura/gravação no Harmonit quanto o push pra WESO. **Confirmado desligado em produção ao final da sessão.**

### Descobertas técnicas sobre `AdicionarOficina`/`DesinstalarOficina`/`ObterOficinas` (testadas ao vivo, novas -- não estavam documentadas antes)

1. `trocaOficinaAntigaId` **não aceita `null`** (apesar do exemplo oficial da doc mostrar `null`) -- precisa `0` quando não há troca. Retorna 400 com `null`.
2. A resposta `{status: false}` de `AdicionarOficina`/`DesinstalarOficina` **não é confiável** -- a Oficina pode ter sido criada normalmente mesmo com `status: false` na resposta direta. Sempre confirmar via `ObterOficinas`/`ObterOrdemServicoPorNumero` depois.
3. `ObterOficinas` é um **histórico de eventos, não um estado mutável**. `DesinstalarOficina` não altera o registro original -- cria um **novo** registro (`status:2`, com `instalacaoId` apontando pro registro original).
4. **Troca e instalação nova são estruturalmente idênticas** na resposta -- `trocaOficinaAntigaId` preenchido não deixa nenhum rastro visível em `ObterOficinas` que diferencie do caso de instalação nova (ambos só `status:1`).
5. `GET /OrdemServico/ObterOrdemServicoPorNumero` **já retorna o array `oficina` embutido**, idêntico em estrutura ao de `ObterOficinas` -- 1 chamada só resolve tudo, não precisa de uma segunda chamada separada.

### Correção de dado: 44 → 15 equipamentos genuinamente ausentes no Harmonit

Ao tentar montar a planilha de import (`equipamento.xls`) pros 44 equipamentos WESO de frente sem correspondência no Harmonit (número fechado em 03/07), a validação do próprio Harmonit rejeitou várias linhas com `IDEquipamento já encontrado`. Causa raiz: **19 desses 44 já existiam no Harmonit**, só que com espaço em branco (ou até um caractere de tabulação) grudado no valor do campo `equipamento` de um cadastro antigo -- sujeira nos dados do próprio Harmonit, não nossa. Mais 5 já tinham o rastreador criado (só faltava o chip), 3 eram lixo/teste sem dado real, 1 tinha modelo sem ID mapeado, 1 não tinha nenhum dado de chip. **Número real de ausentes: 15** (lista completa em `REPORT_HARMONIT_tb000407.md` não -- ver memória de sessão ou pedido enviado ao suporte).

### Outras conclusões da sessão

- Seed das tabelas locais `clientes` (912) e `rastreadores` (4031) -- executado, com backup prévio do banco.
- Reconciliação de valor na Etapa 3 do wizard `gerar_os.html` -- implementada e testada (não documentada em doc própria ainda, ver `09_Harmonit_WESO.md`).
- 2 pedidos formais enviados ao suporte Harmonit: formato do campo Modelo/Sistema na planilha de import; acesso via API ao checklist com foto (`OrdemDeServicoCheckListViewModel`/`ArquivoViewModel`, existem no Swagger mas sem rota pública associada).
- Report da WESO (`Motorista/Consultar`, `Comandos/ComandosEnviados`) e report do Harmonit (`tb000407`) -- ambos com reteste/evidência atualizada, mas **usuário decidiu não enviar nenhum dos dois ao suporte**.


---

## Sessão 6 — 2026-07-16 (continuação, mesma sessão longa)

### Bugs reais corrigidos (achados usando a interface pela primeira vez)

1. **`os_router.py::buscar_cliente`** — `/ObterClientePorCpfCnpj` da Harmonit devolve uma lista, não objeto único; código assumia dict e quebrava com `AttributeError` toda vez que alguém buscava cliente por CNPJ na Etapa 2 do wizard. Corrigido.
2. **Extração da Transferência estava completamente errada** — roteava pro parser de Rescisão, mas documentos reais de Transferência (lado destino) são sempre formato Cliente Novo/Aditivo. Em documento de teste com 28 veículos em 2 colunas lado a lado, só a 1ª coluna era lida (`next()` pegando só o primeiro índice) — **14 de 28 placas sumiam silenciosamente**, nome do cliente nunca era capturado, itens nunca eram reconhecidos. Corrigido roteando "transferencia" pro parser de Cliente Novo/Aditivo. Testado com 2 documentos reais fornecidos pelo usuário + reconferido contra os 9 documentos completos de `exe fpsl/`. Detalhe completo em `14_Painel_OS.md`.

### Mudança de arquitetura confirmada pelo usuário

**Transferência de titularidade deixou de gerar 1 par de OS por placa — agora gera 1 OS de retirada + 1 OS de instalação por DOCUMENTO**, juntando todas as placas do termo numa descrição só (`TRANSFERENCIA DE CONTRATO: (placa|veículo|NUMERO DE SERIE); (...)`). Materiais das placas somados na OS de instalação. Formato da Substituição também ajustado (`SUBSTITUIÇÃO RETIRADA:`/`SUBSTITUIÇÃO INSTALAÇÃO:`, maiúsculo, sem barra).

### Aba "Registrar Oficina" removida, virou "Oficinas"

Nome antigo confundia — a tela nunca registrou nada (Harmonit continua sendo o registro nativo), sempre foi sincronização. Reconstruída como aba de auditoria: histórico persistente de toda tentativa (sucesso E erro, antes só sucesso ficava gravado), verificação pós-escrita direto na WESO (`verificado_weso`), retry natural (falha não bloqueia dedup). Detalhe completo em `14_Oficina_WESO_Sync.md`.

### Outros achados/ações

- Comodato/Compra (`comodato_ou_aquisicao`, extraído desde sessão 4 mas nunca exibido) agora aparece na UI (Vínculos + Gerar OS Etapa 1).
- Chatwoot do MoviZap: título da aba corrigido em produção (config `INSTALLATION_NAME` tinha revertido pro default "Chatwoot" — causa provável, reset de volume Postgres durante limpeza grande da VPS em julho). Reaplicado + cache Redis (`GlobalConfig`) limpo, confirmado ao vivo.
- `C:\code\fpsl_weso` (mirror local) estava desatualizado vs. VPS (arquivos da feature Oficina só existiam remotamente) — sincronizado. `C:\code\Bibliotecas API` (cópia duplicada de toda doc, idêntica à VPS) apagada. `C:\code\suntech-diag` (script solto, projeto real é `D:\SERVER_SUNTECH`) apagada.

### Ainda em aberto

- Lista de 12 testes reais da feature Oficina→WESO (agora "Oficinas") — nenhum ainda executado, ver `14_Oficina_WESO_Sync.md`.
- Interface visual no navegador — nenhuma mudança de hoje foi clicada na UI real ainda.
- Auditoria de criação de OS (painel próprio pra isso, item discutido mas não construído).
- 2 pedidos formais ao suporte Harmonit (planilha de import, checklist com foto) — sem resposta ainda.

---

## Sessão 7 — 2026-07-23

### Substituição exercitada na UI real pela primeira vez (termo 8799 / MGA)

Usuário subiu um Termo de Substituição real no perfil Substituição e caiu em 3 bugs — os 3 corrigidos e no ar. **É a primeira vez que um fluxo do FPSL rodou na tela de verdade** (até aqui tudo era script/API direta). Backups na VPS: `pdf_extractor.py.bak_2026-07-23`, `os_router.py.bak_2026-07-23`. Detalhe técnico completo em `14_Painel_OS.md` (Atualização 2026-07-23) e `15_Particularidades_Documentos.md` (seção Substituição).

1. **`A DEFINIR` era rejeitado como placa** — o veículo de ENTRADA pode vir `A DEFINIR` (substituto ainda não escolhido); o extrator exigia as duas placas válidas e descartava o par inteiro, perdendo a placa de saída válida (`ERF 0325`) e mostrando "não reconhece placa". Novo `_placa_ou_texto`: aceita placa OU texto literal. **Decisão: `A DEFINIR` é placa válida, vai pra descrição como está.**
2. **Acessórios da Substituição nunca entravam na OS** — perfil devolvia `itens: []`; os acessórios (bullets `▶`) só saíam como texto. Novo `_itens_acessorios_substituicao` os transforma em `itens` sem Tipo/valor → `comodato=False, cobrar=False` (regra do usuário). Vínculos já existiam (`BLOQUEIO VEICULAR`→45689, `CENTRAL 24 HORAS`→6976).
3. **Materiais só na instalação → agora nas DUAS OS** — decisão do usuário: a retirada também lista o equipamento removido do veículo antigo. `_montar_operacoes` passou a usar `materiais_placa` na retirada também.

### Ainda em aberto (Substituição)

- **Gerar as OS reais** (`confirmar:true`) — só a simulação rodou; falta confirmar no Harmonit as 2 OS com materiais certos e sem comodato/cobrar.
- Ressalva multi-par: acessórios agregados por lista global + quantidade (distribuída por ordem) — pares com acessórios diferentes entre si podem desalinhar a alocação. Termos reais têm o mesmo pacote em todos os pares.

### Rescisão + geração: continuação de página, dedup de placa, marcador (RD) — termo 8788 (CONSTRUCTO)

Usuário testou uma Rescisão real de 26 veículos e só saíam 12 OS ("limite de 12"). Três correções, todas no ar (backups `pdf_extractor.py.bak2/bak3_2026-07-23`, `os_router.py.bak2_2026-07-23`). Detalhe em `14_Painel_OS.md` e `15_Particularidades_Documentos.md`.

1. **Continuação de página sumia com metade das placas** (`pdf_extractor.py`) — quando a lista de veículos passa de 1 página, a continuação vem numa tabela SEM cabeçalho, que o achador de header ignorava (o fallback só disparava se ZERO placas fossem achadas). Novos `_processar_linhas_veiculo_rescisao` + `_eh_continuacao_veiculo_rescisao`: reconhecem a continuação por mesmo nº de colunas + ausência de palavras de tabela de itens, e leem a lista inteira. 8788: 12 → 26 veículos (19 com placa + 7 máquinas sem placa). **Não há teto de nº de placas** — o "limite de 12" era isso. Só a Rescisão tem esse tratamento hoje.
2. **Placa repetida gerava OS duplicada** (`os_router.py`, `_dedup_placas`) — o 8788 listava as MESMAS 3 placas em 2 referências (8540/8560), erro do documento. Placa repetida agora vira 1 OS só + aviso no painel ("Placas repetidas no termo — gerada 1 OS por placa: ..."). Vale pra todos os perfis.
3. **Marcador `(RD)` de redundância preservado** (`pdf_extractor.py`, `_placa_formatada`) — mesmo veículo com 2 rastreadores vem marcado `(RD)` antes ou depois da placa (`CUB 0764 (RD)`), e na WESO são 2 registros. O extrator jogava fora o `(RD)`, o que faria o dedup juntar 2 equipamentos legítimos. Agora preserva: `CUB 0764` ≠ `CUB 0764 (RD)` → 2 OS. Só conta `(RD)` ENTRE PARÊNTESES numa janela colada à placa (`DRD 4189` não é redundância). Validado contra o formato real da WESO + regressão nos 9 exemplos; **não testado ainda com termo real que tenha RD**.

Interação: placa repetida SEM (RD) = erro → dedup+aviso; placa repetida COM (RD) = 2 equipamentos → 2 OS.

Pendente: estender a continuação de página aos outros perfis (hoje só rescisão).

---

# Sessão 8 (2026-07-24) — geração OS financeiro×operacional (E1–E5) + prioridade + painel "Histórico de OS"

**1. Reestruturação da geração de OS — financeiro × operacional (E1–E5), tudo no ar e validado com OS reais.** Cada termo passa a gerar **N OS operacionais + 1 OS financeira**. Tipo agora é sempre **Contrato (2)**; a operação vive no **Problema + Produto/Serviço**; `situacaoId` passou a ser enviado. Split: operacional = não-cobrança (comodato + linha do serviço sem flag) + ENTREGA OS; financeira = cobrança (Karla técnico, Produto FINANCEIRO 606037, Situação Financeiro 15746). **Fase dupla:** operacionais primeiro, nºs na solução técnica da financeira. Saldo 0 → financeira com motivo. **Titularidade virou 2 perfis** (Antigo = 1 OS sem financeira; Novo = 1 OS híbrida financeiro+comodato). **Rescisão:** extrator passou a ler a tabela de encargos (AVISO PRÉVIO 16033 / RETIRADA CLIENTE 7277) → financeira. Detalhe completo em `14_Painel_OS.md` (seções E0–E5). Conjunto "1 por tipo" gerado real na Pastelaria Velasco (nºs em `Movisat_canais/OS_validacao_tipos.md`).

**2. Prioridade da OS operacional** — seletor na Etapa 2 (default Normal), campo `prioridadeId` (validado: 383=Alta gravou). Financeira sempre Normal.

**3. Painel "Histórico de OS" (gatilho da oficina→WESO, Fase 1 só leitura)** — ver **`16_Historico_OS_Scan.md`**. Varredura sequencial de OS por número (5 min), resync 12 h, alerta de data, painel novo. Substitui o desenho de sync manual de `14_Oficina_WESO_Sync.md`. **Fase 2 (escrita WESO) pendente.**

**Fonte única de próximos passos:** `C:\Users\Lenovo\Proximos_Passos.md`.
