# Mapa — FPSL WESO

Proxy FastAPI entre **Harmonit** (ERP, fonte única) e **WESO** (rastreamento, destino).
Toda lógica de tradução, deduplicação e workarounds de bugs da API WESO fica aqui.
Stack: Python 3.12 · FastAPI · uvicorn porta 8004 · Nginx porta 8005 · SQLite · systemd user service.
**Raiz na VPS:** `/home/claude/fpsl_weso/` — docs em `docs/fpsl/` · `docs/harmonit/` · `docs/weso/`

---

## Código

```
main.py                        entrypoint — lifespan, routers, FastAPI app
fpsl_weso/
  config.py                    pydantic-settings: lê .env (WESO_API_KEY, WESO_BASE_URL, FPSL_SECRET_KEY, HARMONIT_*)
  auth.py                      header X-FPSL-Key — Depends(verificar_chave) em todos os routers
  client.py                    cliente WESO: weso_get/weso_post, parse JSON/HTML, retry, timeout 30s
  harmonit_client.py           cliente Harmonit: Bearer token, renova token em 401 ou qualquer erro de parse, timeout 30s
  logger.py                    log_req() → logs/requests.log (JSON por linha, sem credenciais)
  storage.py                   SQLite async. Tabelas criadas por init_db(): veiculos · clientes · rastreadores (clientes+rastreadores viraram CACHE em 2026-07-22 — no miss buscam ao vivo no Harmonit, ver services/resolucao.py) · rastreadores_serials (serial↔weso_id, bidirecional) · config (chave-valor runtime) · oficinas_processadas (historico + dedup do sync; reformulada 2026-07-16, +colunas placa/equipamento_id/veiculo_nome/origem em 2026-07-22) · painel_usuarios (login do painel; +colunas abas/owner em 2026-07-27) · painel_vinculos_itens (item do contrato ↔ id do catalogo Harmonit) · os_historico (OS varridas + oficinas_json; +coluna excluida) · buscar_harmonit_rastreador_por_serial (lookup tolerante a espaço no espelho harmonit_rastreadores)
                               ⚠️ 7 tabelas do banco NAO nascem aqui — sao criadas pelos scripts de import da raiz (import_weso_base.py · import_harmonit_ativos.py · import_harmonit_clientes.py · import_rastreadores_chips.py): weso_equipamentos · weso_chips · weso_rastreadores · harmonit_clientes · harmonit_rastreadores · harmonit_simcards · harmonit_veiculos. Sao ESPELHOS de analise (cruzamentos Harmonit×WESO), nao estado do servico — mas se o fpsl.db for recriado do zero, elas nao existem ate rodar os scripts de novo.
  translators/weso.py          de-para: situacao_cliente · tipo_veiculo (moto=5, auto=1, caminhao=2, caminhonete=3, carreta=8)
  routers/clientes.py          POST /weso/clientes
  routers/simcards.py          POST /weso/simcards — deduplicação via 409 (W3)
  routers/rastreadores.py      POST · GET · PUT/chip /weso/rastreadores — GET /{id} consulta storage primeiro (acao: encontrado_local, dados: {id,serial}); fallback WESO se ausente (W7)
  routers/veiculos.py          POST · GET/local · POST/local · PUT · DELETE/placa · DELETE/id /weso/veiculos
  routers/os.py                POST /weso/os/adicionar · /weso/os/desinstalar — GRAVAM o vínculo na WESO e registram toda tentativa (sucesso/falha/simulado) no historico da aba Oficinas. Gatilho = a oficina registrada no Harmonit; o FPSL DESCOBRE a oficina por VARREDURA DE OS por numero (decisao do usuario em 2026-07-24 — ver painel "Historico de OS" e docs/fpsl/16_Historico_OS_Scan.md). Resolvem serial/cnpjcpf via services/resolucao.py; toggle oficina_registro_ativo controla real×simulado
  routers/admin.py             GET/PUT /admin/config · POST /admin/sync/inadimplencia
  services/onboarding.py       POST /weso/onboarding — fluxo completo sequencial, timeout Nginx 120s
  services/sync_inadimplencia.py  run_sync() · loop_inadimplencia() — cron interno asyncio
  services/resolucao.py        resolver_serial() · resolver_cnpjcpf() — Harmonit id -> identificador WESO (numeroSerie / cnpjcpf); CACHE local com fallback ao vivo (2026-07-22; antes devolvia 422 "rode o seed")
  painel/                      painel web do operador — auth propria por usuario (tabela painel_usuarios), separada do X-FPSL-Key das rotas /weso
    auth.py                    get_usuario_painel · get_owner_painel · requer_aba(*abas) · seed_admin_inicial (a conta semeada e o OWNER)
    abas.py                    REGISTRO CENTRAL das abas do painel (id/nome/rota/icone/sensivel/somente_owner) — fonte unica do modal de perfil e da sidebar. Ver docs/fpsl/17_Perfis_Acesso.md
    pdf_extractor.py           extracao de termo/contrato POR PERFIL (cliente_novo · aditivo · rescisao · substituicao · transferencia · upgrade), por regex+tabela, sem IA (ver docs/fpsl/14_Painel_OS.md e 15_Particularidades_Documentos.md)
    templates_config.py        PERFIS: de-para perfil -> tipoId/problemaId da OS no Harmonit; ENTREGA_OS_ID (material fixo em toda OS)
    routers/login_router.py    POST /painel/api/login · GET /painel/api/me
    routers/usuarios_router.py GET /painel/api/usuarios/abas · GET/POST /painel/api/usuarios · PATCH /painel/api/usuarios/{id} — contas do painel, EXCLUSIVO DO OWNER (2026-07-27; antes era "admin"). O owner nao pode ser alterado por aqui (400)
    routers/os_router.py       geracao de OS por contrato (prefixo /painel/api): GET /perfis · POST /extrair · GET /clientes|servicos|produtos/buscar · GET/POST /vinculos · POST /vinculos/extrair-preview · POST /gerar-os (dry-run quando confirmar:false)
    routers/oficina_router.py  POST /painel/api/oficina/resync/{id} · GET /painel/api/oficina/historico · GET/PUT /painel/api/oficina/config/ativo — aba "Oficinas" e SO historico + Resync (busca por OS/sincronizar REMOVIDOS em 2026-07-22). Ver docs/fpsl/14_Oficina_WESO_Sync.md
    routers/os_scan_router.py  POST /painel/api/os-scan/varrer · /resync · GET /painel/api/os-scan/historico · GET/PUT /painel/api/os-scan/checkpoint — VARREDURA de OS por numero (scan 5min + resync 12h agendados no lifespan do main.py) e painel "Historico de OS". E o gatilho oficina->WESO. Fase 1 SO LEITURA. Ver docs/fpsl/16_Historico_OS_Scan.md
```

**Permissao do painel (desde 2026-07-27):** toda rota `/painel/api/*` exige a ABA correspondente
(`requer_aba`), nao mais so "estar logado". `usuarios` e `config` sao exclusivas do owner.
Detalhe em `docs/fpsl/17_Perfis_Acesso.md`.

Arquivos de suporte:
```
.env                  600 — 6 vars (HARMONIT_CLIENT_ID/SECRET_ID preenchidos; integracao Harmonit viva)
data/fpsl.db          600 — SQLite
logs/requests.log     600 — log JSON linha a linha
nginx_fpsl.conf       cópia local da config Nginx (ativa em /etc/nginx/sites-available/fpsl)
requirements.txt      fastapi · uvicorn · httpx · pydantic-settings
```

---

## Documentação — docs/fpsl/ (ler em ordem numérica)

| Arquivo | O que contém | Keywords |
|---------|-------------|---------|
| 00_Metodologia.md | **Índice geral** + ciclo spec→impl→teste→doc + status de cada aba | índice, status, ciclo, validado |
| 01_Cliente.md | POST /weso/clientes — spec, campos, testes | cliente, cnpjcpf, situacao, razaoSocial |
| 02_Chip.md | POST /weso/simcards — deduplicação via 409 | simcard, iccid, chip, ja_existe |
| 03_Equipamento.md | POST/GET/PUT /weso/rastreadores — modelo obrigatório (G1) | rastreador, serial, modelo, harmonit_id |
| 04_Placa.md | POST/DELETE /weso/veiculos — storage local, exclusão segura por placa | placa, veiculo_id, storage, excluir |
| 05_Onboarding.md | POST /weso/onboarding — fluxo completo, timeout 120s, workaround W6 | onboarding, sequência, timeout, veiculo_id |
| 06_Deploy.md | Deploy VPS — venv, systemd, portas, linger, comandos manutenção | deploy, systemd, uvicorn, porta 8004, reiniciar |
| 07_Registro_Local.md | SQLite — tabela veiculos, fluxo de exclusão segura | sqlite, placa, veiculo_id, local, buscar |
| 08_Logs.md | Formato JSON do log, campos, exemplos de cada acao | log, requests.log, json, acao, ref, ok |
| 09_Harmonit_WESO.md | Tabela de gatilhos Harmonit → rotas FPSL → endpoints WESO | webhook, gatilho, mapeamento, AdicionarOficina |
| 10_Inconsistencias.md | **Fonte autoritativa de bugs WESO** — W1–W9, gaps G1–G8, comportamentos B1–B7, código W7 pendente | bug, workaround, anti-hijacking, timeout, W7, seed |
| 11_Seguranca.md | Auditoria — SQL injection, command injection, path traversal, gaps remanescentes | segurança, injection, auditoria, HTTPS, LGPD |
| 12_Nginx.md | **Nginx do FPSL — config REAL** (reescrito 14/08): 3 server blocks, timeout por rota (`/` 180s, login 35s de propósito), regras `deny` dos backups | nginx, proxy, timeout, 504, sites-enabled, fpsl.conf |
| 13_Status.md | **Diário cronológico por sessão** — produção, pendências, fluxo de ativação, endpoints, catálogo WESO (mais recente: Sessão 8 / 2026-07-24). ⚠ é HISTÓRICO: sessões antigas descrevem rotas que já não existem; a referência viva de cada assunto é o doc numerado dele | status, pendências, produção, ativação, próxima sessão |
| 14_Oficina_WESO_Sync.md | Sincronização Oficina Harmonit -> WESO — fluxo, endpoints, interruptor, decisões de corte (aba só histórico + Resync desde 2026-07-22) | oficina, sync, weso, interruptor, resync, trocaOficinaAntigaId |
| 14_Painel_OS.md | **Painel de geração de OS por contrato** — perfis, extração, vínculos item↔catálogo, geração com dry-run (sessões 4-7). ⚠ dois arquivos começam com "14" | painel, OS, perfil, extração, vínculo, gerar, substituição, transferência, dry-run |
| 15_Particularidades_Documentos.md | **Particularidades por tipo de documento** (Substituição/`A DEFINIR`/acessórios, Rescisão, Transferência) + regra comodato×cobrar | documento, substituição, A DEFINIR, acessórios, comodato, cobrar |
| 16_Historico_OS_Scan.md | **Gatilho oficina→WESO por VARREDURA DE OS** — scan 5min/resync 12h, checkpoint, salvaguardas, painel "Histórico de OS". Fase 1 só leitura; Fase 2 (escrita) pendente | varredura, scan, checkpoint, os_historico, oficina, gatilho, resync |
| 17_Perfis_Acesso.md | **Perfis de acesso do painel** — owner + permissão por aba (`requer_aba`), modal de perfil, `abas.py` como fonte única (2026-07-27) | owner, aba, permissão, perfil, usuários, requer_aba, sidebar |
| 18_Testes.md | **Testes — 448 verificações em 11 arquivos** (14/08). Não há pytest e não são `assert`: a função é `checar()`, então `grep assert` devolve zero. Inclui o exercício da tela em node. Cada número travado é um bug que já aconteceu | teste, regressão, extração, fixtures, checar, tela, node |
| 19_Plano_Implantacao.md | **Plano de implantação (5 etapas, por dependência)** — padrão de placa → 1 escrita real → espelho diário → resolução no termo → cadastro → automático. Caminho crítico e o que está bloqueado no usuário | plano, etapas, placa, espelho, escrita, caminho crítico |
| 20_Fluxo_Oficina_e_Reconciliacao.md | **Caminho oficial da Oficina→WESO** (a oficina VINCULA, nunca CRIA — o evento não tem modelo/ICCID/cliente) + **rotinas de espelho e diff** pra manter Harmonit e WESO iguais | oficina, vínculo, reconciliação, espelho, diff, divergência, desinstalação |
| 21_Plano_Higiene_Placas.md | **Higiene da base de placas da WESO** — o que se padroniza e o que se deixa em paz | higiene, placa, padronização, WESO |
| 22_Auditoria_Servicos_Harmonit.md | **Auditoria dos serviços do Harmonit** — o que existe no catálogo e o que a OS usa | auditoria, serviço, produto, catálogo |
| 23_Manutencao.md | **Os 2 perfis que nascem de chamado, sem termo** (14/08) — no local e com troca, recipiente `-MANUT`, liberação da série, tipo/problema por NOME | manutenção, recipiente, MANUT, liberar série, sem termo |
| 24_Desempenho_e_Timeout.md | 🚨 **A medição de 29/07 envelheceu e INVERTEU** — base inteira 2,3s→16-33s, placa filtrada 6s→0,67s. Era isso o 504 do nginx que aparecia como "erro json". Orçamento de tempo, tetos e como remedir | desempenho, timeout, 504, orçamento, medição, WESO lenta |

---

## Documentação — docs/harmonit/ (referência da API Harmonit)

| Arquivo | Keywords |
|---------|---------|
| 00_VISAO_GERAL.md | visão geral, autenticação, base_url |
| 01_Autenticacao.md | bearer, token, client_id, secret_id, refresh |
| 02_Cliente.md | /Cliente/Consultar, campos cliente Harmonit |
| 03_OrdemServico.md | AdicionarOficina, DesinstalarOficina, tipoVeic, rastreadorId, clienteId |
| 04_Financeiro.md | financeiro, cobrança |
| 05_Produto.md | produto, equipamento Harmonit |
| 06_Ativos.md | /Veiculo/ObterVeiculos, placa, tipoEqp, tipo_veiculo |
| 07_Usuario.md | usuário, perfil |
| 08_Dados_Suporte.md | enums, listas de referência |
| 09_Servicos_Integrados.md | AdicionarOficina, DesinstalarOficina — payload completo |
| 10_Lacunas_e_Consultas.md | campos sem equivalente WESO, decisões pendentes, G7 emailCobranca |
| Harmonit_WESO_Integracoes.md | tabela campo a campo Harmonit ↔ WESO |
| Harmonit_WESO_Mapeamento.md | payloads reais mapeados |

---

## Documentação — docs/weso/ (referência da API WESO)

| Arquivo | Keywords |
|---------|---------|
| 00_VISAO_GERAL.md | base_url, autenticação por ?key=, padrão de resposta HasError/Status |
| 01_Veiculos.md | /Veiculos/Cadastro, /Veiculos/Excluir, veiculo_id, W1, W2 |
| 02_Clientes.md | /Clientes/Cadastro, cnpjcpf, situacao, tipoCliente |
| 03_Rastreadores.md | /Rastreadores/Cadastro, serial, modelo, GET bloqueado W7 |
| 04_SimCards.md | /SimCard/Cadastro, iccId, GET bloqueado W3 |
| 05_Motoristas.md | motoristas — não integrado ao FPSL |
| 06_Comandos.md | comandos remotos — não integrado ao FPSL |
| 07_FPSL.md | proposta original do FPSL (referência histórica) |
| FPSL_Proposta.md | proposta inicial detalhada (referência histórica) |
| weso_inconsistencias.md | rascunho inicial — **supersedido por docs/fpsl/10_Inconsistencias.md** |

---

## Sync Inadimplência (Harmonit → WESO)

**Arquivo:** `fpsl_weso/services/sync_inadimplencia.py`

**Regra de tempo:** asyncio background task (`loop_inadimplencia`) iniciado no lifespan do FPSL.
Acorda a cada **10 min** e executa se: hora VPS >= 05:00 BRT **e** não rodou hoje.

**Chaves de config** (tabela `config` no SQLite):

| Chave | Default | Descrição |
|---|---|---|
| `inadimplencia_sync` | `"false"` | `"true"` liga · `"false"` desliga (não reverte inadimplentes existentes) |
| `inadimplencia_grace_days` | `"7"` | Dias de tolerância após vencimento |
| `sync_last_run_date` | `""` | Data ISO da última execução (ex: `"2026-06-17"`) |

**Lógica por cliente:**
1. `GET /Financeiro/v2/ObterBoletosEmAbertoPorCpfCnpj` no Harmonit
2. Tem boleto com `dataVencimento < (hoje − grace_days)`?
   - Sim e WESO `!= Inadimplente` → `PUT /Clientes/Atualizar {"situacao": "Inadimplente"}`
   - Não e WESO `== Inadimplente` → `PUT /Clientes/Atualizar {"situacao": "Adimplente"}` (restaura)
3. Erros por CNPJ são isolados — falha de um não para o restante

**Validação de config** (`PUT /admin/config/{chave}` rejeita 422 se):
- `inadimplencia_grace_days` não for inteiro ≥ 1
- `inadimplencia_sync` não for `"true"` ou `"false"`

**Controle via API:**
```bash
# Ligar sync
PUT /admin/config/inadimplencia_sync     {"valor": "true"}
# Desligar sync
PUT /admin/config/inadimplencia_sync     {"valor": "false"}
# Ver estado
GET /admin/config
# Disparo manual (ignora toggle e horário)
POST /admin/sync/inadimplencia
```

---

## Estado atual — snapshot 2026-06-17 (estado VIVO em docs/fpsl/13_Status.md, Sessão 7 / 2026-07-23)

| Item | Estado |
|------|--------|
| Serviço FPSL | em produção — porta 8005 |
| Sync inadimplência | implementado — toggle OFF por default |
| HARMONIT_CLIENT_ID / SECRET_ID | **preenchidos** — integração Harmonit em uso (90 endpoints validados ao vivo em 2026-07-22) |
| W7 (GET /Rastreadores/Consultar) | **aplicado** — storage lookup bidirecional (serial↔weso_id) em rastreadores.py, veiculos.py e GET /{id} |
| Seed WESO CSV | aguardando CSV do suporte WESO; script seed_csv.py pronto |
| Rastreador 49175 / serial 007559809 | livre — em uso no sistema (1 registro em rastreadores_serials) |
| Audit de código | concluído (2026-06-17) — 10 issues corrigidos; ver 13_Status.md |
| Logrotate | configurado — `/etc/logrotate.d/fpsl-weso` · daily · 30 rotações · copytruncate |
| Próximo passo | Substituição: gerar OS reais (confirmar:true); Oficina→WESO com placa controlada OVG7C78; ver 13_Status.md Sessão 7 |
| Ações externas | detalhadas em `docs/fpsl/13_Status.md` — seção "Ações Externas Pendentes" |

---

## Comandos rápidos

```bash
# Estado do serviço
systemctl --user status fpsl-weso

# Health check (422=OK · 502=uvicorn fora · 000=nginx fora)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/weso/veiculos/local

# Log em tempo real
tail -f /home/claude/fpsl_weso/logs/requests.log

# Listar storage de placas
sqlite3 /home/claude/fpsl_weso/data/fpsl.db "SELECT * FROM veiculos;"

# Reiniciar serviço
systemctl --user restart fpsl-weso

# Listar config runtime
curl -s http://localhost:8005/admin/config -H "X-FPSL-Key: $FPSL_SECRET_KEY"

# Ligar sync inadimplência
curl -s -X PUT http://localhost:8005/admin/config/inadimplencia_sync \
  -H "X-FPSL-Key: $FPSL_SECRET_KEY" -H 'Content-Type: application/json' \
  -d '{"valor": "true"}'

# Disparo manual do sync
curl -s -X POST http://localhost:8005/admin/sync/inadimplencia \
  -H "X-FPSL-Key: $FPSL_SECRET_KEY"
```
