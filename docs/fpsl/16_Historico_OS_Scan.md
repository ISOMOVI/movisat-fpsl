# 16 — Gatilho Oficina→WESO via varredura de OS ("Histórico de OS")

**Criado:** 2026-07-24
**Status:** **Fase 1 (só leitura) implementada e validada na UI.** Fase 2 (escrita na WESO) pendente.
**Substitui** o desenho de sincronização manual descrito em `14_Oficina_WESO_Sync.md` (busca de OS + botão "Sincronizar"), que fica como histórico.

---

## Problema
Manter **placa × equipamento × cliente** alinhados na WESO a partir do que é registrado na **oficina** (dentro da OS) do Harmonit. Restrição dura confirmada: **não existe webhook em nenhum dos dois sistemas** — nem para os sistemas já homologados. O usuário descartou polling genérico, cron, varredura de estado, busca por número de OS e webhook do Harmonit.

## Caminhos avaliados (2026-07-24)
1. **Hook no navegador** — dispara no clique de "Adicionar Oficina", lê `osId/placa/equipamento` do DOM (inclusive o campo **"Integração: Manual"** que a API esconde) e chama `/weso/os/adicionar`. Real-time, mas frágil (por máquina) e perde evento se o clique não disparar.
2. **Reconciliação (estado do rastreador)** — `ObterRastreadores` (1 call, 4.036) traz `instalado/placa/veiculo/contato`; diff contra o estado sincronizado. Robusta/autocorretiva, mas não dá o nº da OS e não distingue "Manual" (campo invisível na API).
3. **Varredura de OS — ESCOLHIDA.** Segue o número crescente de OS, lê a oficina embutida em cada uma. Dá o **nº da OS**, Harmonit é a **fonte da verdade**, sem diff com a WESO.

## Fatos descobertos ao vivo
- `ObterOrdemServicoPorNumero` **já traz o array `oficina` embutido**: `veiculoPlaca`, `equipamentoId` (= serial), `veiculoNome`, `status` (**1=Instalado, 2=Desinstalado**). **Sem** nº da OS no evento e **sem** timestamp/usuário (a TELA do Harmonit mostra, a API não).
- O rastreador (`ObterRastreadores`) **espelha a última oficina** (`instalado/placa/veiculo/contato`). O campo **"Integração=Manual"** NÃO volta na API — nem por endpoint de detalhe (só `ObterRastreadores/Incluir/Atualizar`).
- Nº de OS é **global** (todos os clientes) e tem **buracos** (ex.: 16527 inexistente). `ObterOrdemServico(clienteId=...)` NÃO lista por cliente.
- Financeira reconhecível por `problema=11701`.

## Decisões do usuário (fecham o desenho)
- **A oficina cai sempre em OS recente** (nunca se mexe em OS antiga) → varredura **só pra frente**. Rescisão etc. nascem pelo FPSL, a oficina vai na OS-OP da placa.
- **Sem filtro de escopo por ora** — todas as OS Harmonit → WESO. Multi-sistema é assunto de **+6 meses**.
- **RD** = placa-key própria (`CUB 0764 (RD)`), 1 serial, oficina/OS separada → o diff é sempre `placa → 1 serial`.
- **Cliente/veículo nascem na WESO ANTES da geração das OS** (cliente novo / novo titular = P1; tela de placas = P2). Isso **desarma** o "a WESO cria o cliente sozinha?" — quando a oficina sincroniza, cliente e veículo já existem.
- **Desinstalação — PENDENTE:** apagar (`/Veiculos/Excluir`, comportamento atual) vs desativar (WESO não tem `Desativar` claro; talvez `/Veiculos/Atualizar` com `situacao`, por analogia ao SimCard — a confirmar).

## Fase 1 — implementado (SÓ LEITURA, nada escreve na WESA)
- **Tabela `os_historico`** (storage.py): `numero_os` PK, `tipo, problema, produto_id, cliente_id, data_previsao, oficinas_json, n_oficinas, excluida, visto_em, atualizado_em`. Checkpoint em `config: os_scan_checkpoint`.
- **`painel/routers/os_scan_router.py`:**
  - `varrer_os(desde=None)` — scan pra frente do checkpoint; para em **`LIMITE_BURACOS=10`** inexistentes seguidos; cap `MAX_LEITURAS=3000`; grava histórico + avança checkpoint + `os_scan_ultima_nova_em`.
  - `resync_os(janela=RESYNC_JANELA=400)` — re-lê a janela recente (pega oficina adicionada depois e **detecta exclusão** → `excluida=1`).
  - Loops agendados no `lifespan`: **scan 5 min** (`INTERVALO_SCAN=300`), **resync 12 h** (`INTERVALO_RESYNC=43200`).
  - **Alerta** se >1 dia sem OS nova (`ALERTA_SEM_OS_SEG=86400`).
  - Endpoints (prefixo `/painel/api/os-scan`, **todos exigem a aba `os_historico`** desde 27/07 — ver `17_Perfis_Acesso.md`):

| Rota | Faz o quê |
|---|---|
| `POST /painel/api/os-scan/varrer?desde=` | Varredura sob demanda (`desde` opcional força o ponto de partida) |
| `POST /painel/api/os-scan/resync` | Re-lê a janela recente; detecta exclusão |
| `GET /painel/api/os-scan/historico?limit=&apenas_com_oficina=` | Alimenta a tela |
| `GET /painel/api/os-scan/checkpoint` | Lê o checkpoint |
| `PUT /painel/api/os-scan/checkpoint` | Ajusta o checkpoint |
- **Painel `/painel/os-historico`** (`frontend/os_historico.html`): contadores (total + checkpoint), "Varrer agora" (+ `desde`), "Resync janela", ajustar checkpoint (editável, p/ exclusão em massa), filtro "só com oficina", auto-refresh 60s, marca "excluída" e banner de alerta. *(Desde 27/07 o link só aparece pra quem tem a aba `os_historico` — a sidebar é montada do perfil, não é mais fixa em todas as telas.)*
- **Populado de 16450:** em 2026-07-27 são **98 OS, 48 com oficina**, checkpoint **16549**. O scan sobreviveu ao reboot da VPS de 27/07 e retomou do checkpoint gravado.

## Salvaguardas (auditoria feita)
- **Lock** serializando scan × resync × varredura manual (SQLite não gosta de escrita concorrente).
- **Exclusão só no "não encontrada" explícito** — timeout/502 conta como erro e reprova no próximo resync, **nunca** marca exclusão falsa (testado).
- Loops em `try/except` (falha transitória não mata o agendador). Baseline de alerta no boot. Migração de `excluida` por PRAGMA-check. `visto_em` preservado no re-save; re-achar OS desmarca `excluida`.

## Pendente
- **Fase 2 — escrita na WESO** por trás do toggle `oficina_registro_ativo` (reusa `/weso/os/adicionar` + `_sincronizar_evento`): dispara `status 1 → /Veiculos/Cadastro`, `status 2 → /Veiculos/Excluir`. **Dedup por evento** (o histórico do FPSL vira o livro-caixa — cada evento vai à WESO uma vez).
- **1 escrita real na WESO** pra confirmar a cadeia (cliente/veículo/vínculo) e resolver o **D** (apagar vs desativar).
- **Custo ocioso:** ~10 sondagens a cada 5 min quando não há OS nova (~2.880 chamadas/dia). Afinável (intervalo/limiar).
- **Nº da OS** só existe via scan (o evento de oficina da API não carrega).


---

## 01/10 — `materiais_json` e `situacao_id` (E1 da frente de Fechamentos)

**Status:** ✅ no ar desde 2026-10-01 13:35 (restart autorizado). Contexto da
frente em `30_Painel_Financeiro.md`.

**Por quê:** a varredura já lia `materiais[]` e `situacaoId` na mesma chamada
`ObterOrdemServicoPorNumero` e descartava os dois. O material é o **único**
lugar onde o modelo do equipamento da OS existe — sem ele não há como comparar
com o que a WESO diz do rastreador. `situacaoId` é a "Situação de Ordem de
Serviço" (catálogo `SituacaoOrdemServico`), campo **diferente** de
`status`/`status_str`.

**O que mudou:**

| Arquivo | Mudança |
|---|---|
| `storage.py` (init) | `ALTER TABLE os_historico ADD COLUMN materiais_json TEXT` e `situacao_id INTEGER`, padrão `PRAGMA table_info` |
| `storage.salvar_os_historico` | dois parâmetros opcionais, `materiais` e `situacao_id`; uma leitura só da linha anterior (antes eram duas) |
| `os_scan_router.varrer_os` / `resync_os` | repassam `d.get("materiais")` e `d.get("situacaoId")` — nenhuma chamada nova à API |

🚨 **A guarda do `None`.** `materiais=None` (ou `situacao_id=None`) **preserva**
o que já está gravado — quem não tem o dado não sobrescreve quem tem. Existe um
**terceiro chamador**, `services/conferencia_fechamento.py:87`, que grava sem
esses campos; sem a guarda, a rotina de 1h zeraria o material que a varredura
acabou de gravar. `oficinas` **não** ganhou essa proteção de propósito: lista
vazia ali é informação (OS sem oficina). `situacao_id = 0` grava `0` — é valor
real do Harmonit ("sem situação"), não ausência.

**Teste com dado real (5 OS):**

| OS | tipo | situacao_id | status_str | oficinas | materiais |
|---|---|---|---|---|---|
| 16450 | 55 Manutenção (troca) | 0 | Finalizado | 2 | 2 |
| 16934 | 2 | 15746 (financeira) | Finalizado | 1 | 2 |
| 16961 | 57 Retirada | 38 | Nova | 1 | 4 |
| 16962 | 57 Retirada | 38 | Nova | 1 | 4 |
| 16976 | 76 Instalação | 38 | Iniciada | 1 | 5 |

Guarda provada: regravar a 16962 sem `materiais` manteve os 4 materiais e o 38.

⚠️ **Incidente no teste, corrigido:** o teste da guarda gravou valores falsos em
problema/cliente/oficina da 16962. Restaurada na hora a partir do Harmonit e
conferida (problema 7502, cliente 330795, serial 007786380). Teste de escrita se
faz na sandbox (OS 16991), não em OS de cliente.

`listar_os_historico` **não** devolve `materiais` — a tela do Histórico de OS
segue com o mesmo payload.

---

---

## 01/10 — `os_id`, o id interno da OS

A varredura passou a guardar também o **`os_id`**, o id INTERNO da OS no
Harmonit, que **não é** o `numero_os`. Motivo: `ObterTimeLine` só aceita o id, e
sem guardá-lo aqui toda leitura de linha do tempo gastaria uma chamada a mais só
para descobri-lo. Vem na mesma resposta que a varredura já lê, de graça.

⚠️ **O resync cobre as 400 OS mais recentes**, então uma OS que sai dessa janela
não recebe `os_id` por aqui. Quem precisa dele resolve na hora e grava (ver
`_os_id_resolvido` em `services/conferencia_fechamento.py`) — a varredura não é
o único caminho, de propósito.

Detalhe do uso em `30_Painel_Financeiro.md` (ordenação da `FIN_1.1`).


---

## 01/10 — sub-aba "ID × modelo"

A tela ganhou duas sub-abas: **Varredura** (o que já existia) e **ID × modelo**,
que confere cada linha de oficina contra a WESO. Só leitura, sem chamada de API.
Regra, medições e números em `30_Painel_Financeiro.md` (seção E2).

⚠️ A sub-aba **não** entra no recarregamento de 60 s da tela: ela lê todas as OS
com oficina a cada vez, e o cache da WESO só muda uma vez por dia. Recarrega ao
abrir a aba ou pelo botão.
