> # ⏭️ SUPERADO EM 2026-07-24 — o gatilho virou VARREDURA DE OS. Ver `16_Historico_OS_Scan.md`.
> O desenho de "buscar OS + botão Sincronizar" deste arquivo foi substituído pelo painel
> "Histórico de OS" (scan sequencial por número, agendado). A lógica de escrita na WESO
> (`_sincronizar_evento`, `/weso/os/adicionar`, toggle `oficina_registro_ativo`) continua
> válida e será reusada na Fase 2. O resto abaixo é histórico.

# ⚠️ REESCRITO EM 2026-07-22 — LEIA ISTO ANTES DO RESTO DO ARQUIVO
>
> **A oficina é o gatilho. Decisão do usuário, fechada, não reabrir.**
> Registrar a oficina no Harmonit dispara a gravação na WESO na mesma operação,
> por `POST /weso/os/adicionar` e `/desinstalar` (`fpsl_weso/routers/os.py`).
>
> **Foi REMOVIDO nesta data:** a busca por número de OS (`GET /painel/api/oficina/buscar`)
> e a sincronização manual (`POST /painel/api/oficina/sincronizar`). Os dois retornam 404.
> Está DESCARTADO e não deve ser reproposto: varredura de estado, polling, cron de
> sincronização, busca por número de OS, webhook do Harmonit.
>
> **A aba "Oficinas" agora é só o histórico**, com `placa`, `nº de série` e `veículo`
> como colunas próprias (antes só existiam dentro do texto de `resultado`).
>
> **Novo: Resync** (`POST /painel/api/oficina/resync/{id}`). Caso de uso: a WESO estar
> fora do ar quando a oficina foi registrada. A linha fica como erro e ganha o botão.
> O resync **confere antes de refazer** — reconsulta a WESO (`_verificar_weso`) e, se o
> vínculo já estiver no estado certo, marca como resolvido sem reenviar. Isso existe
> porque a resposta da WESO não é confiável (um timeout não significa que não gravou),
> e é o que impede duplicar vínculo a cada clique.
>
> **Também mudou:** `clientes`/`rastreadores` locais viraram CACHE, não fonte
> (`fpsl_weso/services/resolucao.py`). No miss, busca ao vivo no Harmonit e grava.
> Some o erro "cadastre o cliente/equipamento antes" / "rode o seed".
>
> Os 12 testes listados mais abaixo validam o fluxo ANTIGO e **precisam ser reescritos**
> antes de rodar.

# 14 — Sincronização Oficina (Harmonit → WESO)

**Criado em:** 2026-07-16
**Reescrito em:** 2026-07-16 (mesma sessão, continuação) — aba "Registrar Oficina" removida, substituída por aba de auditoria "Oficinas"
**Status:** implementado e testado (histórico + verificação WESO), interruptor desligado (modo simulação) em produção

---

## Contexto

Objetivo: manter placa × equipamento × cliente alinhados na WESO, a partir do que é registrado nativamente na tela de Oficina do Harmonit (dentro da OS). Não existe webhook em nenhum dos dois sistemas (ver `13_Status.md` Sessão 5) -- a sincronização é por gatilho manual.

## Correção de nome (2026-07-16, continuação)

A tela original se chamava "Registrar Oficina" no menu, mas **nunca registrou nada** — ela sempre foi só sincronização (busca OS já registrada no Harmonit nativo, dispara push pra WESO). O nome confuso gerou a impressão de que existia um formulário de cadastro duplicado. Removido: `frontend/oficina.html`, rota `/painel/oficina`, link de menu. Reconstruído como **aba "Oficinas"** (`frontend/oficinas.html`, rota `/painel/oficinas`) com foco em auditoria: histórico persistente de toda tentativa (sucesso e erro), não só busca por OS.

## Fluxo

1. Operador registra a instalação/troca/desinstalação na tela **nativa do Harmonit** (não replicada no FPSL).
2. Operador abre `/painel/oficinas` no FPSL, busca a OS pelo número (mesmo comportamento de antes).
3. Tela mostra cada evento de Oficina daquela OS (`status:1`=instalação/troca, `status:2`=desinstalação), com selo: já sincronizado / pendente.
4. Operador clica "Sincronizar com WESO". Backend processa cada evento pendente:
   - `status:1` → `POST /Veiculos/Cadastro` na WESO (placa + cliente.cnpjcpf + rastreador.numeroSerie, direto do campo `equipamentoId` do evento)
   - `status:2` → `POST /Veiculos/Excluir` na WESO (via `veiculo_id` local; fallback `GET /Veiculos/Consultar?placa=X` se não achar local)
   - **Novo:** depois da escrita, o backend consulta a WESO de volta (`GET /Veiculos/Consultar?placa=X`) pra confirmar que persistiu de verdade — resultado fica marcado como `verificado_weso` (true/false), nunca bloqueia o resultado, só dá visibilidade. Motivo: achado de sessões anteriores de que `PUT /SIMCard/Atualizar` já retornou 200 sem persistir de fato.
5. Erro passageiro (timeout, instabilidade WESO) → operador clica de novo. **Erro agora fica registrado no histórico** (antes não ficava — só sucesso era gravado); reclique funciona normalmente porque o dedup só considera tentativas de sucesso.
6. **Nova seção "Histórico geral"** na mesma tela: lista as últimas 200 tentativas de sincronização (qualquer OS), mais recente primeiro, com status sucesso/erro e selo de verificação WESO.

## Interruptor de segurança

Config `oficina_registro_ativo` (tabela `config`, chave-valor), default `"false"`.
- **Desligado:** tela simula ("[simulado] criaria/apagaria vínculo..."), não grava nada de verdade nem no Harmonit nem na WESO.
- **Ligado:** grava de verdade.
- Editável só por admin, em `/painel/config` (continua existindo, não foi tocado).
- **Confirmado desligado em produção ao final de 2026-07-16.**

## Endpoints

⚠️ **Conferido em 2026-07-27 contra o código.** A tabela abaixo listava 2 rotas que
**já não existem** e 1 com o caminho errado — contradizendo o próprio aviso no topo
deste arquivo. Corrigido: agora só o que responde de fato.

| Rota | Auth (aba exigida) | Faz o quê |
|---|---|---|
| `POST /painel/api/oficina/resync/{registro_id}` | aba `oficinas` | Reprocessa um registro do histórico |
| `GET /painel/api/oficina/historico?limit=200` | aba `oficinas` | Histórico geral (todas as OS), fonte da aba de auditoria |
| `GET /painel/api/oficina/config/ativo` | aba `config` (**só owner**) | Lê o toggle `oficina_registro_ativo` |
| `PUT /painel/api/oficina/config/ativo` | aba `config` (**só owner**) | Liga/desliga o toggle |

**Removidas em 2026-07-22, retornam 404** (estavam listadas aqui como se existissem):
`GET /painel/api/oficina/buscar` · `POST /painel/api/oficina/sincronizar`.
O caminho do toggle **não** é `/painel/api/config/ativo` — é `/painel/api/oficina/config/ativo`.

> Auth mudou em 2026-07-27: não é mais "JWT painel (+admin)", e sim **permissão por aba**
> (`requer_aba`). Ver `17_Perfis_Acesso.md`.

## Schema — tabela `oficinas_processadas` (reformulada 2026-07-16)

Antes: `evento_id PRIMARY KEY` — só gravava sucesso, `INSERT OR REPLACE` (1 linha por evento, sem histórico de tentativas anteriores).

Agora:
```sql
CREATE TABLE oficinas_processadas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evento_id       INTEGER NOT NULL,
    numero_os       INTEGER NOT NULL,
    status          INTEGER NOT NULL,
    sucesso         INTEGER NOT NULL,       -- 0/1
    verificado_weso INTEGER NOT NULL DEFAULT 0,  -- 0/1, só relevante se sucesso=1
    resultado       TEXT NOT NULL,          -- descrição (sucesso) ou erro (falha)
    processado_em   TEXT NOT NULL
)
```
Migração automática em `storage._init_oficinas_processadas()`: detecta schema antigo (falta coluna `sucesso`) e dropa a tabela antes de recriar — seguro porque a tabela sempre esteve vazia em produção (única tentativa real anterior deu erro de validação e nunca chegou a marcar sucesso).

**Dedup:** `oficina_ja_processada()` só considera bloqueio se existir alguma linha com `sucesso=1` pro `evento_id` — falha nunca bloqueia retry/reclique.

## Dependências

- Tabela local `clientes` (harmonit_id→cnpjcpf) -- seedada em 2026-07-16 (912 registros). Necessária pra resolver o cliente no push de instalação.
- Tabela local `veiculos` (placa→weso_id) -- populada incrementalmente a cada sincronização de instalação bem-sucedida. Com fallback de busca direta na WESO se não encontrar local.
- **NÃO depende da tabela local `rastreadores`** -- o serial do equipamento já vem direto no campo `equipamentoId` de cada evento de Oficina.

## O que foi cortado do desenho original (decisão consciente)

- **Fila de retry com backoff automático** -- desnecessária com gatilho manual síncrono; o operador reclica se der erro passageiro. O histórico persistente (novo) cobre a parte de "não perder o erro de vista" sem precisar de fila.
- **Polling automático / varredura periódica** -- avaliado e descartado: nem Harmonit nem WESO têm endpoint de listagem por data.
- ~~**Reaproveitar `adicionar_oficina`/`desinstalar_oficina` de `routers/os.py`** -- assinatura não bate.~~
  > ⚠️ **DECISÃO REVERTIDA EM 2026-07-22.** A assinatura bate sim, no desenho novo: registrar a oficina dentro da OS é o gatilho, e é o FPSL que inicia (não o Harmonit por webhook). `/weso/os/adicionar` recebe `osId` + `rastreadorId` + `placaVeiculo` e já resolve serial + `cnpjcpf` + grava na WESO. **Passam a ser a base da implementação**, não reserva. O fluxo de buscar OS + sincronizar foi descartado pelo usuário.

## Comportamentos da API do Harmonit relevantes pra essa feature

Ver `10_Inconsistencias.md` seção AA (`trocaOficinaAntigaId` não aceita `null`, resposta `status:false` não confiável, `ObterOficinas` é histórico append-only, troca indistinguível de instalação nova, `ObterOrdemServicoPorNumero` já traz `oficina` embutido).

## Pendências reais

- 2 pedidos enviados ao suporte Harmonit em 2026-07-16 (formato do campo Modelo/Sistema na planilha de import de equipamento; acesso via API ao checklist com foto) -- não bloqueiam essa feature.
- **Testes de validação em produção -- AINDA NÃO INICIADOS.** A reconstrução de hoje (histórico + verificação WESO) foi testada com dados simulados via script direto (falha→retry liberado→sucesso→dedup, migração de schema confirmada) mas **nenhuma gravação real na WESO com dado válido foi feita ainda**. Lista de 12 testes abaixo continua de pé, sem alteração de conteúdo (só o caminho da UI mudou de `/painel/oficina` pra `/painel/oficinas`).

## Lista de testes pendentes

| # | Teste | O que confirma |
|---|---|---|
| 1 | Instalação nova (`status:1`) com equipamento/placa de formato **real** (não `TESTEIAGO`) e interruptor ligado | Gravação de verdade funciona -- ainda não confirmado, único teste real deu 400 por dado inválido |
| 2 | Consultar o vínculo criado direto na WESO (`Veiculos/Consultar?placa=X` ou painel WeFleet) depois do teste 1 | Dado gravado bate com o que foi enviado (placa, cliente, serial) — agora também verificável direto na aba Oficinas (`verificado_weso`) |
| 3 | Troca de equipamento (`trocaOficinaAntigaId` preenchido) num evento novo, mesma placa | WESO sobrescreve o vínculo da mesma placa em vez de duplicar |
| 4 | Desinstalação (`status:2`) de um vínculo que a própria ferramenta criou (já tem `veiculo_id` local) | `Veiculos/Excluir` remove o vínculo corretamente, storage local limpo |
| 5 | Desinstalação de uma placa que **nunca passou por essa ferramenta** (vínculo antigo, sem registro local) | Fallback `Veiculos/Consultar?placa=X` encontra o `veiculo_id` e remove mesmo assim |
| 6 | Clicar "Sincronizar" 2x seguidas no mesmo evento já processado com sucesso | Dedup funciona -- segunda vez cai em `ja_feitos`, não reenvia |
| 7 | OS com **múltiplos eventos** de Oficina (ex: 2 instalações diferentes, ou instala+desinstala na mesma OS) | Cada evento é processado independentemente e corretamente |
| 8 | Cliente sem `cnpjcpf` cadastrado localmente (não seedado) | Erro 422 claro, **e agora persistido no histórico como falha** (antes só aparecia na resposta HTTP e se perdia) |
| 9 | Reenviar uma instalação cujo vínculo **já existe** na WESO (mesma placa) | `weso_post` com `allow_409=True` trata como sucesso, não duplica |
| 10 | Interruptor desligado, clicar Sincronizar várias vezes seguidas | Nada é gravado de verdade em nenhuma tentativa |
| 11 | Usuário do painel **sem** ser admin tentando ver/alterar `/painel/config` | Bloqueado (403), só admin acessa o toggle |
| 12 | Uso pela **interface web de verdade** (`oficinas.html`/`config.html` no navegador) | Nenhum teste até agora passou pela UI real |

**Recomendação de ordem:** 12 primeiro, depois 10-11 (proteções), depois 1-2 (gravação real básica, já conferindo o selo `verificado_weso`), depois 3, 6, 9 (reprocessamento), depois 4-5 (desinstalação), depois 7-8 (casos compostos/erro — 8 agora também testa se o erro fica correto no histórico).
