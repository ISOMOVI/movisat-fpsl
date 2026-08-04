# 10 — Inconsistências e Limitações do FPSL

**Status:** 📋 Documentado — 2026-06-15
**Finalidade:** Registro de comportamentos divergentes, limitações conhecidas, workarounds ativos e itens pendentes.

---

## I — Limitações da API WESO

| # | Endpoint | Problema | Workaround ativo |
|---|----------|---------|-----------------|
| W1 | `GET /Veiculos/Consultar` | ✅ **RESOLVIDO pela WESO — confirmado em amostra grande 2026-07-27**: 200 OK, devolve **1.965 veículos** com `id`+`placa` numa chamada. (Era HTTP 500.) | Não precisa mais de workaround pra ler. ⚠️ mas ver **B8** — o filtro `?placa=` casa LITERAL |
| W2 | `POST /Veiculos/Excluir` por placa | HTTP 400 — exclusão por placa não funciona | Capturar `veiculo_id` na criação; excluir sempre por ID numérico |
| W3 | `GET /SimCard/Consultar` | ✅ **RESOLVIDO pela WESO — confirmado 2026-07-27**: 200 JSON com **4.070 chips**; filtro `?iccId=` funciona. (Era HTML por anti-JSON-hijacking.) | Não precisa mais do workaround do 409. Ver **B10** |
| W4 | `situacao` do rastreador | Não é alterada automaticamente ao vincular placa — permanece `Estoque` | Campo informativo; mudança de situação é manual no painel WeFleet |

---

## II — Gaps de campo Harmonit → WESO

| # | Entidade | Campo | Problema | Ação |
|---|---------|-------|---------|------|
| G1 | Rastreador | `modeloEquipamento` | Opcional no Harmonit, **obrigatório** no WESO. Se vazio, cadastro falha com HTTP 400 | FPSL rejeita com 422 via Pydantic antes de chamar WESO |
| G2 | Cliente | `situacaoClienteDesc` | Texto livre configurável no Harmonit vs enum fixo no WESO | Tabela de-para em `translators/weso.py` (ver `09_Harmonit_WESO.md`) |
| G3 | Oficina | `rastreadorId` | ID interno Harmonit — WESO precisa do serial | ✅ Implementado: `storage.rastreadores(harmonit_id → serial)` |
| G4 | Oficina | `clienteId` | ID interno Harmonit — WESO precisa do `cnpjcpf` | ✅ Implementado: `storage.clientes(harmonit_id → cnpjcpf)` |
| G5 | Oficina | `tipoVeic` / `tipo` | É `EnumTipoEquipamento {1, 2}` — **não é** o tipo do veículo | ✅ Implementado: lookup em `GET /Veiculo/ObterVeiculos` + `tipo_veiculo()` |
| G6 | SIM Card | `operadoraId` | Sem campo equivalente no WESO | Descartado silenciosamente |
| G7 | Cliente | `emailCobranca` | WESO tem `emailCobranca` (faturamento); Harmonit tem email de contato | Semântica diferente — decisão pendente: mapear mesmo assim ou ignorar |
| G8 | Cliente | `plano` | Sem origem no Harmonit | Fica `null`; aceito pelo WESO |

---

## III — Discrepâncias doc vs código (resolvidas)

| # | Arquivo | Problema | Estado |
|---|---------|---------|--------|
| D1 | `07_Registro_Local.md` | Snippet de `storage.py` usa `asyncio.get_event_loop()` (deprecated Python 3.10+) | Código em produção usa `get_running_loop()` — doc desatualizada |
| D2 | `07_Registro_Local.md` | `remover_veiculo` no snippet usa `_connect().__enter__()` sem fechar conexão | Código em produção tem `def _run()` com `with _connect()` correto |
| D3 | `01_Cliente.md` | Implementação no doc não tem `log_req` calls | Código em produção tem `log_req` em todos os handlers |

---

## IV — Comportamentos não óbvios confirmados em teste

| # | Observação |
|---|-----------|
| B1 | ICCID totalmente fictício (ex: `000000000000001`) causa **timeout** no WESO — usar prefixo de operadora real (ex: `8955`) |
| B2 | Rastreador com serial **alfanumérico** parece ser excluído em cascata quando o veículo vinculado é deletado. Seriais puramente numéricos não apresentaram esse comportamento |
| B3 | `cnpjcpf` na consulta WESO ignora formatação — aceita com ou sem pontos/barras/hífen |
| B4 | `tipoCliente` retorna `NaoInformado` quando não informado na criação — valor padrão WESO |
| B5 | Serviço systemd parava ao encerrar sessão SSH com `Linger=no`. Corrigido com `loginctl enable-linger claude` |
| B6 | `id` do SIM Card retorna `null` quando `acao: ja_existe` — WESO não disponibiliza `GET /SimCard/Consultar` (bloqueado), impossibilitando resolução do ID em caso de duplicata |
| B7 | Datas ASP.NET com offset (`/Date(ms+HHMM)/`) eram parseadas com erro. Corrigido com regex em `_parse_date` |

---

## V — Funcionalidades implementadas (histórico de pendências)

| # | Item | Estado |
|---|------|--------|
| F1 | `POST /weso/os/adicionar` | ✅ Implementado em `routers/os.py` |
| F2 | `POST /weso/os/desinstalar` | ✅ Implementado em `routers/os.py` |
| F3 | `storage.rastreadores` | ✅ Implementado em `storage.py` |
| F4 | `storage.clientes` | ✅ Implementado em `storage.py` |
| F5 | `translators/weso.py` | ✅ Implementado |
| F6 | `/fulltrack/...` | ⏳ Futura — rotas e `services/fulltrack/` |
| F7 | Nginx externo | ✅ Ativo na porta 8005 (`/etc/nginx/sites-enabled/fpsl.conf`) |

---

## VI — Limitações do painel WeFleet (confirmadas em uso)

| # | Observação |
|---|-----------|
| W5 | `veiculo_id` **nunca é exibido** no painel WeFleet — impossível recuperar o ID via interface visual. A única fonte é o `requests.log` do FPSL (campo `"id"` na linha `acao: "criado"`) ou a resposta da chamada no momento da criação. |
| W6 | Quando o onboarding estoura o timeout do Nginx antes de o WESO responder, o FPSL nunca recebe o `veiculo_id` — **nem o log nem o storage são atualizados**. O veículo existe no WESO mas é irrastreável via API. Mitigação: N1 (timeout 120s no path `/weso/onboarding`) e N2 (`POST /weso/veiculos/local` para registro manual). |

---

## VII — Fluxo de recuperação de veiculo_id perdido

**Quando usar:** onboarding retornou erro/timeout e `GET /weso/veiculos/local` não mostra a placa.

**Passo 1 — Verificar se o veiculo_id está no log:**
```bash
grep ref: PLACA /home/claude/fpsl_weso/logs/requests.log | grep acao: criado
# Se aparecer com "id": 12345 → usar esse ID no passo 2
# Se não aparecer → ID foi perdido (W6); apagar o veículo manualmente no WeFleet e recriar
```

**Passo 2 — Registrar no storage via N2:**
```bash
curl -s -X POST -H "Content-Type: application/json" \
  -H "X-FPSL-Key: <chave>" \
  -d {placa: PLACA, veiculo_id: 12345} \
  http://localhost:8005/weso/veiculos/local
```

**Passo 3 — Confirmar e operar normalmente:**
```bash
# Listar storage
curl -s -H "X-FPSL-Key: <chave>" http://localhost:8005/weso/veiculos/local

# Excluir normalmente pelo placa
curl -s -X DELETE -H "X-FPSL-Key: <chave>" \
  http://localhost:8005/weso/veiculos/placa/PLACA
```


---

## VIII — Novos bloqueios WESO descobertos (2026-06-15 sessão 2)

| # | Endpoint | Problema | Workaround necessário |
|---|----------|---------|----------------------|
| W7 | `GET /Rastreadores/Consultar` | Bloqueado por anti-JSON-hijacking (igual W3) — retorna HTML com mensagem "AllowGet not set". Afeta lookup por `?numeroSerie=` e por `?id=`. `POST /Rastreadores/Consultar` retorna 404 (não existe). | ✅ **Aplicado (2026-06-17):** storage bidirecional `serial↔weso_id`; `cadastrar_veiculo` e `GET /{id}` usam lookup local. |
| W8 | `POST /Veiculos/Consultar` | Retorna HTTP 404 — endpoint não existe na API WESO | Sem workaround disponível. `veiculo_id` só obtido no momento da criação (acao: "criado") |
| W9 | `POST /Rastreadores/Atualizar` com apenas `{"id": N}` | Retorna HTTP 500 quando payload não inclui pelo menos um campo além do id | Não usar como sonda de estado. Para obter weso_id, usar o storage local |

---

## IX — Estado bloqueante: rastreador 49175 / IAG0T01

> ✅ **Resolvido em 2026-06-17 (sessão 3)**
>
> Veículo IAG0T01 foi excluído manualmente no painel WESO pelo operador, liberando o rastreador 49175 (serial `007559809`).
> Confirmado via `POST /weso/rastreadores {"numeroSerie":"007559809"}` → `acao: ja_existe, id: 49175`.
> Registro criado em `rastreadores_serials`: serial `007559809` → weso_id `49175`.


---

## X — W7 aplicado: storage bidirecional serial↔weso_id

> ✅ **Aplicado em 2026-06-17 (sessão 3)**

**Arquivos alterados:**

- `fpsl_weso/storage.py` — tabela `rastreadores_serials` + funções `salvar_rastreador_serial`, `buscar_weso_id_por_serial`, `buscar_serial_por_weso_id` (reverse lookup)
- `fpsl_weso/routers/rastreadores.py` — branches `ja_existe` e `criado` salvam `serial→weso_id`; `GET /{id}` consulta storage antes de chamar WESO
- `fpsl_weso/routers/veiculos.py` — `cadastrar_veiculo` usa `buscar_weso_id_por_serial` em vez de `GET /Rastreadores/Consultar`

**Seed:** `python3 seed_csv.py rastreadores arquivo.csv` (formato: `ID_SERIAL | ID_EQUIPAMENTO`)
**Estado:** 1 registro em `rastreadores_serials` (serial `007559809` → weso_id `49175`). Aguardando CSV do suporte WESO para importação em massa.

---

## Y — Correção da WESO confirmada ao vivo (2026-07-14): W1 parcialmente resolvido

Testado ao vivo com veículo real (placa `UGD 7B39`, cliente CAPITTUR TRANSPORTES):

```
GET /Veiculos/Consultar?placa=UGD 7B39   (placa EXATA como armazenada, com espaço)
→ 200 OK: {"id": 86938, "placa": "UGD 7B39", "rastreador_id": 12833, "complemento": {...chassi, cor, renavam...}}

GET /Rastreadores/Consultar?numeroSerie=007458954
→ 200 OK: {"id": 12833, "numeroSerie": "007458954", "simcard": {"iccId": "8955170000201213650", ...}}
```

Bate exatamente com o registro já espelhado em `weso_equipamentos` (placa/serial/iccid), confirmando integridade.

**W1 (`GET /Veiculos/Consultar` — 500) parece corrigido pela WESO** — retorna 200 com `id`+`rastreador_id` direto. **W7 (`GET /Rastreadores/Consultar` por `numeroSerie`) também parece corrigido** — não depende mais só do storage bidirecional local pra resolver serial→weso_id.

**Ressalvas antes de declarar resolvido, ainda não testado:**
1. **Placa precisa vir EXATAMENTE como a WESO armazena, com espaço.** Testado sem espaço (`UGD7B39`) → retornou vazio (0 resultados), não erro. Se algum código normalizar a placa antes de consultar, quebra silenciosamente.
2. Só testado com 1 veículo — recomendo testar mais 4-5 placas reais (Mercosul, chassi, "A DEFINIR") antes de remover o workaround do storage local.
3. `Veiculos/Consultar` não retorna cliente/razão social — só id/placa/rastreador_id/complemento. Pra dado de cliente completo ainda precisa de consulta separada (`harmonit_clientes` local ou módulo Clientes da WESO).

**Não fechar W1/W7 como ✅ até rodar o teste de amostra maior — deixar como 🟡 até lá.**

### ✅ Teste de amostra maior EXECUTADO em 2026-07-27 — W1 fechado

`GET /Veiculos/Consultar` sem filtro devolveu **1.965 veículos, 100% com `id` e `placa`**
(`total` do payload bate). W1 está **resolvido**, não 🟡. Script: `analisar_placas_weso.py`
(só leitura).

---

## B8 — o filtro `?placa=` casa LITERAL, e o formato na WESO é MISTO (2026-07-27)

Achado ao responder "temos como consultar o `veiculo_id` na WESO?" (Transferência,
Substituição, Rescisão — casos em que a placa **já existe** lá).

| Formato das 1.965 placas | Qtd |
|---|---|
| **com espaço** (`UGD 7B39`) | 1.905 |
| **sem espaço** (`LB113838`) | 60 — **todas chassi/série de máquina** |
| com minúscula | 23 (19 são apelido: `Móvel 1`…`Móvel 14`) |
| com marcador `(RD)` | 24 |

> ✅ **As 5 placas CONVENCIONAIS sem espaço foram corrigidas via API em 2026-07-27**
> (`MCJ0232`, `RET5662`, `RET5816`, `RET5819`, `RET6007` → com espaço). Ver seção de
> escrita abaixo. As 60 que restam sem espaço são chassi de máquina — **não são placa,
> não mexer**.

⚠️ **3 placas têm espaço nas BORDAS** (`' Ch4297335181'`, `' TL5.80 Claudio'`). Por isso
a normalização precisa de `strip()` antes de qualquer coisa — contar `" " in placa` sem
strip classifica essas como "com espaço" e erra por 3.

O filtro não normaliza nada:

```
?placa=UGD 7B39  -> 1 resultado (id 86938)
?placa=UGD7B39   -> 0 resultados     <-- mesma placa
```

**Consequência prática:** consultar placa a placa pelo filtro **perde registro** sempre
que o formato do termo/Harmonit não for idêntico ao da WESO. O caminho confiável é
**baixar a lista inteira numa chamada e casar normalizado localmente**
(`re.sub(r"[^A-Z0-9]", "", placa.upper())`) — 1 request, não N.

**Cuidado no de-para:** normalizando, **7 chaves** têm mais de um registro. São de dois
tipos, e não se tratam igual:
- **redundância real** (`(RD)`, 24 registros) — 2 equipamentos no mesmo veículo, os dois
  são válidos, ver a decisão de placa duplicada × RD;
- **lixo/apelido** — `MÓVEL 1`, `TERMO: 8396` (4 registros!), `OBD 2` não são placa.

Além dessas, 3 placas reais aparecem 2× (`GFI 3G42`, `SVS 6J23`, `EBU 1968`) — desempatar
antes de escrever, nunca pegar `[0]` cegamente.

### `POST /Veiculos/Atualizar` — FUNCIONA para renomear placa (validado 2026-07-27)

Escrita real em produção, autorizada pelo usuário. Padronização das 5 placas
convencionais sem espaço. Script: `corrigir_placas_espaco.py` (dry-run por padrão,
`--aplicar` para escrever, `--somente <id>` para uma só).

**Contrato confirmado ao vivo** — a doc era ambígua (`placa` aparece como identificador
**e** como campo alterável). O que vale:

```json
POST /Veiculos/Atualizar?key=...
{"veiculo_id": 57146, "placa": "MCJ 0232"}
→ 200 {"Status":"success","Data":{"id":57146,"placa":"MCJ 0232","data_atualizacao":...}}
```

Com `veiculo_id` presente, **`placa` é tratada como NOVO VALOR**, não como filtro. Os 5
retornaram 200.

**Efeitos colaterais verificados (não presumidos):**
- `rastreador_id` **preservado** nos 5 — o vínculo com o equipamento não se perde ao
  renomear a placa. (É o que sustenta usar `rastreador_id` como âncora de conciliação.)
- a grafia antiga **deixa de encontrar** o registro (`?placa=MCJ0232` → 0 resultados)
- o total da base continuou **1.965** — `Atualizar` não cria registro novo

| `veiculo_id` | de | para | `rastreador_id` |
|---:|---|---|---:|
| 57146 | `MCJ0232` | `MCJ 0232` | 18221 |
| 77097 | `RET5662` | `RET 5662` | 37246 |
| 69648 | `RET5816` | `RET 5816` | 38438 |
| 69655 | `RET5819` | `RET 5819` | 38446 |
| 69652 | `RET6007` | `RET 6007` | 38439 |

Reverter é o mesmo POST com a grafia antiga.

---

## B9 — Redundância (RD): 5 grafias, padronizadas em 2026-07-27

### O que existia

O marcador de redundância (2º equipamento no mesmo veículo) era escrito de **5 jeitos
diferentes** nas 1.965 placas:

| Grafia | Qtd | Exemplo |
|---|---:|---|
| `(RD)` depois | 18 | `CUB 0764 (RD)` |
| `(RD)` antes | 6 | `(RD) FCL 3G18` |
| `RD` solto depois | 1 | `OWE 0I25 RD` |
| `RD` solto antes | 1 | `RD MRM 9A92` |
| `rd` colado, minúsculo | 1 | `rdRCJ 0D65` |

Duas ainda tinham **espaço duplo** (`FJZ 4H64  (RD)`).

### ⚠️ 16 armadilhas — placa que CONTÉM "RD" e não é redundância

```
RDM 0G81 · RDM 3C27 · RDM 3E86 · RDM 3I31 · RDM 3J08 · RDM 4G14 · RDM 4G33
RDM 5J60 · RDM 7B92 · RDM 8I35 · RDM 8J13 · RDQ 5G58 · RDS 0B93
DRD 4189 · QRD 0A53 · RRD 1C69
```

`RDM`, `RDQ`, `RDS`, `DRD`, `QRD`, `RRD` são **prefixos legítimos de placa**. Uma
normalização ingênua (`replace("RD","")`) destruiria 16 placas válidas.

**O critério que separa** — e que deve ser reusado em qualquer código que mexa nisso:
remover o marcador e verificar se **o que sobra é placa válida** (`ABC 1234` ou
`ABC 1D23`).

```
'rdRCJ 0D65' -> 'RCJ 0D65'  ✅ placa valida  -> era marcador
'RDM 0G81'   -> 'M 0G81'    ❌ invalida      -> RDM e prefixo real
```

Cuidado com a implementação: se a regex **não removeu nada**, o candidato não serve de
prova — senão toda placa "passa" e o classificador acusa 100% de redundância (aconteceu
na 1ª versão do script).

### Padrão adotado (decisão do usuário, 2026-07-27)

```
(RD) ABC 1234        <- marcador ANTES, entre parenteses, um espaco
(RD) ABC 1D23        <- idem para Mercosul
```

**As 27 redundâncias genuínas foram padronizadas** via `POST /Veiculos/Atualizar`
(21 alteradas + 6 que já estavam no formato). Script: `padronizar_rd.py`.

**Validação exigida antes de cada escrita** (e que passou em 100%):
- **duplicata**: compara `(placa_base, tem_RD)` — não a string crua, senão
  `CUB 0764 (RD)` e `(RD) CUB 0764` pareceriam registros diferentes. Zero colisões.
- **par existente**: as 27 têm o registro sem RD na base — são redundância real, nenhuma órfã.
- `rastreador_id` **intacto** nas 21, e total da base seguiu **1.965**.

---

## B10 — SIM Card e Rastreador: o que a API faz e o que ela FINGE fazer (2026-07-27)

Testado ao vivo com os dados de teste autorizados (chip `8955170220424545007`,
equip `007559809` / id 49175). Script: `teste_escrita_simcard_equip.py`.

### ✅ Funciona

| Ação | Como | Observação |
|---|---|---|
| Consultar chips | `GET /SimCard/Consultar` | 4.070 chips; `?iccId=` filtra (W3 caiu) |
| **Desativar ICCID** | `POST /SimCard/Atualizar {iccId, situacao:"Cancelado"}` | ⚠️ **oculta**, não apaga — e o valor não é documentado |
| **Desvincular chip do equipamento** | `POST /Rastreadores/Atualizar {id, simCard:{"id":0}}` | ⚠️ **só com `id:0`**, e **só por este lado** |
| **Cadastrar equipamento** | `POST /Rastreadores/Cadastro {numeroSerie, modelo:{descricao}}` | HTTP **201**; nasce `situacao:"Estoque"`, `simcard:null` |
| **Excluir equipamento** | `POST /Rastreadores/Excluir {id}` | **exclusão REAL** — libera o `numeroSerie` |
| Revincular chip | `POST /Rastreadores/Atualizar {id, simCard:{id}}` | volta como estava |
| Excluir chip | `POST /SimCard/Excluir {iccId}` ou `{simcard_id}` | documentado, **não testado** |

### ⚠️ Desativar o chip OCULTA o registro da listagem

`situacao: "Cancelado"` → o chip **some** de `/SimCard/Consultar`, inclusive da lista
inteira (4.070 → 4.069) **e do filtro por `iccId`**. Parece apagado, mas **não está**: o
vínculo continua visível dentro do rastreador (`simcard: {id, iccId}`), e mandar
`situacao` de volta o traz de volta à listagem. É **soft delete**, e é reversível.

**Consequência prática:** qualquer rotina que sincronize chips pela listagem vai
interpretar um chip "Cancelado" como **inexistente** e pode tentar recriá-lo. Vale
lembrar do `Duplicate entry` do Harmonit — o mesmo tipo de estrago. **Nunca tratar
"sumiu da listagem" como "foi apagado".**

Vocabulário real de `situacao` do chip (4.070 registros):
`Estoque` (2.370) · `''` (1.694) · `Cancelado` (5) · `EmUso` (1).
`disponivel` é um booleano separado e **não acompanha** a situação (há `Estoque` com
`disponivel` true e false).

### 🚨 QUATRO famílias de FALSO SUCESSO — HTTP 200 `success` sem efeito nenhum

1. **`simCard: null` não desvincula.** Retorna `{"Status":"success"}` e o chip **continua
   vinculado**. Só `{"simCard": {"id": 0}}` desvincula de verdade.
2. **`situacao` do rastreador é READ-ONLY na prática.** Testado com `Cancelado`, `Inativo`
   e `Estoque`: 200 em todos, situação **continua `Estoque`**.
3. **`situacao: "Inativo"` no CHIP não grava** — apesar de ser **valor documentado**
   (`04_SimCards.md` diz "Chip desativado"). 200 `success`, e a situação continua a
   anterior. Só `Estoque`, `EmUso` e `Cancelado` gravam de fato.
4. **Não dá pra desvincular pelo lado do ICCID.** 4 formas testadas
   (`rastreador: null`, `rastreador:{id:0}`, `rastreador_id: 0`, `numeroSerie: ""`) —
   **todas 200 `success`, nenhuma mexeu no vínculo**. O schema do SIM Card **não tem
   campo de rastreador**: o vínculo só existe do lado do rastreador, e só de lá se mexe.
   *(Nas telas do WeFleet a informação aparece dos dois lados — na API, não.)*

**Resposta a "dá pra inativar equipamento via API?": NÃO.** Confirma e amplia o **W4** (a
`situacao` do rastreador é informativa, mexida só pelo painel). O que dá é **desvincular o
chip** ou **excluir o rastreador**.

> Todos devolvem **200 com `"Status":"success"`**. Quem confiar no código de retorno acha
> que funcionou. **Sempre reler o estado depois de escrever.**

### Inversão perigosa entre doc e realidade — `situacao` do chip

| Valor | Documentado? | Grava? | Efeito real |
|---|---|---|---|
| `Estoque` | ✅ | ✅ | visível, `disponivel: true` |
| `EmUso` | ✅ | ✅ | visível, `disponivel: false` |
| `Inativo` | ✅ ("chip desativado") | ❌ **ignorado** | nenhum |
| `Cancelado` | ❌ **não documentado** | ✅ | **oculta da listagem** |

Ou seja: o valor que a doc manda usar pra desativar **não faz nada**, e o que realmente
desativa **não está na doc**. `disponivel` é **derivado** da situação, não é campo próprio.

### ✅ `POST /Rastreadores/Excluir` — exclusão REAL (não é ocultação)

Provado sem ambiguidade: excluído o id 49947 (`FPSLTESTE0001`), a consulta zerou **e o
recadastro do mesmo `numeroSerie` foi aceito**, criando **id novo (49948)**. Se fosse
ocultação como a do chip, o serial continuaria ocupado e o cadastro seria recusado.

**Contraste importante com o Harmonit**, que **não tem DELETE** para rastreador/chip/
veículo/cliente (por isso lá os registros de teste são permanentes e precisam ser
"neutralizados"). Na WESO dá pra apagar de verdade.

### ⚠️ REGRA: inativar × excluir (definida pelo usuário em 2026-07-27)

> "No Harmonit é ativo/inativo, excluir somente manual mesmo, principalmente se tiver
> sido usado e ficar preso em algum log."

| | Harmonit | WESO |
|---|---|---|
| Inativar | `ativar: true/false` — **é o padrão** | chip: `situacao:"Cancelado"` (oculta, reversível) · rastreador: **não dá** (read-only) |
| Excluir por API | **não existe** (15+ rotas testadas → 404) | **existe e é REAL** |
| Exclusão manual | pelo painel, evitada se o registro já foi usado | — |

**O perigo está na WESO.** O `Excluir` apaga sem perguntar nada: não avisa se o
equipamento tem histórico, posições, eventos ou aparece em OS antiga. **A API não protege
— a trava tem que ser nossa.** Antes de excluir: conferir vínculo (veículo, chip) e uso.
Preferir **desvincular** (`simCard:{id:0}`) a apagar.

**E apagar na WESO não apaga no Harmonit** — as bases divergem na hora. Caso real:
`358899055459393` foi excluído da WESO (id 3680) e **continua no Harmonit** (id 8814,
`ativar=True`), sem poder ser removido nem inativado até o `tb000407` ser corrigido.

## B11 — CICLO placa × equipamento × chip: o que a WESO faz de verdade (2026-07-27)

Responde as 3 perguntas do usuário sobre a **oficina → WESO** (é a pergunta **D** do
plano). Script: `teste_ciclo_placa_equip_chip.py`.

### 1. Mandando o serial, a WESO cadastra o rastreador sozinha? **NÃO**

A doc do `/Veiculos/Cadastro` promete: *"Suporta criação automática de clientes,
rastreadores, SIM cards e complementos em uma única requisição"* e *"se
`rastreador.numeroSerie` for informado sem ID, o rastreador é criado"*.

**Não é o que acontece.** Bissecção (`bisseccao_cadastro_veiculo.py`), 5 tentativas:

| Payload | Resultado |
|---|---|
| placa + cliente | ✅ **201** (cliente criado junto — isso funciona) |
| \+ `rastreador.numeroSerie` + `modelo` STRING | ❌ 400 |
| \+ `rastreador.numeroSerie` + `modelo` OBJETO | ❌ 400 |
| \+ `rastreador` + `simCard` | ❌ 400 |
| \+ `rastreador` só com `numeroSerie` | ❌ 400 |
| **`rastreador: {id: N}`** (já existente) | ✅ **201**, `"rastreador": "Validado"` |

**Qualquer tentativa de CRIAR rastreador pelo cadastro de veículo dá 400** — o formato do
`modelo` não é a causa. Só **referenciar por `id`** funciona.

⇒ **A Fase 2 tem que criar o rastreador ANTES**, em 2 passos:
`POST /Rastreadores/Cadastro` (→ pega o `id`) e depois `/Veiculos/Cadastro` com
`rastreador: {id}`.

**O chip, esse sim, é criado automaticamente** — mas dentro do
`/Rastreadores/Cadastro` (`simCard: {iccId}` → devolve `simcard_id`), não pelo veículo.

### 2 e 3. Excluindo a PLACA, o que acontece com equipamento e chip? **SOBREVIVEM**

```
antes : veiculo TST 1A11 (87628) -> rastreador 49951 -> chip 56895
POST /Veiculos/Excluir {veiculo_id: 87628}  -> 200
depois: veiculo SUMIU
        rastreador 49951  CONTINUA  (situacao 'Instalado', ainda com o chip)
        chip       56895  CONTINUA  ('EmUso')
```

**Nem apaga, nem inativa: ficam soltos no acervo.** E o rastreador **continua marcado
`Instalado`** mesmo sem veículo — coerente com o W4 (a `situacao` não se atualiza
sozinha) e com a `situacao` ser read-only por API.

⇒ **Consequência para a Fase 2:** a desinstalação via `/Veiculos/Excluir` deixa
equipamento e chip órfãos, com estado mentiroso (`Instalado` sem veículo). Se o objetivo
for devolver o equipamento ao estoque, **excluir a placa não basta** — e como a `situacao`
do rastreador não é gravável, **não há como marcá-lo como disponível pela API**.

### 🚨🚨 O caso NORMAL de campo devolve 500 — e FUNCIONA (reproduzido 2/2)

O mais perigoso de tudo. Vincular rastreador existente na criação da placa:

| Rastreador | HTTP | Resultado real |
|---|---|---|
| **sem** chip | **201** | veículo criado e vinculado |
| **com** chip | **500** | **veículo criado e vinculado do mesmo jeito** |

Testado 2× seguidas, resultado idêntico — **não é instabilidade, é comportamento**. E
equipamento **com chip é o caso normal em campo**: na prática, a operação que a Fase 2
mais vai executar é justamente a que sempre devolve erro apesar de funcionar.

> **Se o código tratar 500 como falha e retentar, cria veículo DUPLICADO.**

### 🚨 Escrita PARCIAL: erro que grava metade

| Chamada | Retorno | Mas… |
|---|---|---|
| `/Veiculos/Cadastro` com `rastreador.numeroSerie` | **400 Bad Request** | **criou o chip** do bloco `simCard` |
| `/Veiculos/Cadastro` com `rastreador:{id}` (rastreador com chip) | **500** | **criou o veículo** e vinculou |

**Não é atômico.** Depois de um 4xx/5xx da WESO, é obrigatório **reler o estado** — pode
ter gravado parte. Tratar erro como "não aconteceu nada" gera duplicata na retentativa.

### 📌 Regra geral que sai de tudo isso

**O código de retorno da WESO não é confiável nos DOIS sentidos:**

```
200 "success"  -> pode não ter feito nada    (4 famílias de falso sucesso)
400 / 500      -> pode ter gravado tudo      (escrita parcial + o 500 do caso normal)
```

⇒ **A única fonte de verdade é reler o estado depois de escrever.** Toda escrita da
Fase 2 precisa de *read-after-write* — que, felizmente, já é o padrão que o
`oficina_router` usa (campo `verificado_weso`). Manter e estender.

### 🚨 `/SimCard/Excluir` por `iccId` é NÃO CONFIÁVEL

Chip que **já esteve vinculado** a um rastreador resiste:

```
POST /SimCard/Excluir {iccId: "8955000000000099901"}
  -> 200 {"Data":{"id":56893, ...}}     <- id de OUTRO chip, apagado antes!
  chip 56895 continua existindo (só mudou pra 'Estoque')

POST /SimCard/Excluir {simcard_id: 56895}
  -> 200  -> apagado de verdade
```

A resposta trouxe **id de um registro diferente** — a API identificou o alvo errado.
**Sempre excluir chip por `simcard_id`, nunca por `iccId`.**

Chip **órfão** (nunca vinculado) apaga normal pelos dois caminhos. Isso conversa com a
regra do usuário: *"principalmente se tiver sido usado e ficar preso em algum log"* — o
que já foi usado resiste à exclusão, e vira `Estoque` em vez de sumir.

### `GET /Rastreadores/Consultar` IGNORA paginação

`?pagina=N&limite=1000` devolve **os 3.748 inteiros** em toda chamada — testado com
5 páginas seguidas, sempre o mesmo total. Mesmo comportamento do `ObterRastreadores` e
`ObterSIMCards` do Harmonit. **Quem escrever paginação achando que funciona vai processar
a base inteira N vezes sem perceber.**

### `GET /Rastreadores/Consultar` sem filtro estoura

HTTP **524** (timeout) ao pedir a lista inteira (3.749). **Com filtro** (`?numeroSerie=`)
responde 200 normalmente. Diferente da consulta de veículos, que devolve os 1.965 numa vez.

---

## Identificadores: `rastreador_id` × `numeroSerie` (confirmado ao vivo 2026-07-27)

Confusão fácil, e não estava escrita em lugar nenhum:

| Campo | O que é | Onde aparece |
|---|---|---|
| `rastreador_id` | **ID interno** do rastreador no sistema WESO | `/Veiculos/Consultar` (campo do veículo), `id` em `/Rastreadores/Consultar` |
| `numeroSerie` | **Serial do equipamento FÍSICO** | `/Rastreadores/Consultar`, obrigatório em `/Rastreadores/Cadastro` |

```
veiculo 'LB113838'  rastreador_id=1505   -> numeroSerie='205620436'
veiculo 'CRW 0440'  rastreador_id=2987   -> numeroSerie='205281794'
veiculo 'EER 1318'  rastreador_id=39711  -> numeroSerie='1610036765'
```

**Por que importa:** o `rastreador_id` é a **âncora estável** de conciliação — provado em
27/07, quando 26 placas foram renomeadas e nenhum `rastreador_id` mudou. O `numeroSerie` é
o que casa com o Harmonit (campo `equipamento`) e com o que o técnico lê no aparelho.

---

## Z — Seed de `clientes`/`rastreadores` locais — ✅ CONCLUÍDO (2026-07-16)

As tabelas locais `clientes` (harmonit_id→cnpjcpf) e `rastreadores` (harmonit_id→serial) — que `adicionar_oficina`/`desinstalar_oficina` em `routers/os.py` exigem populadas (senão retorna 422) — foram seedadas a partir de dados já importados:

- `clientes` ← `harmonit_clientes` (943 registros, reimportado fresco em 2026-07-16 via `GET /ObterClientes?somenteAtivos=true`): `INSERT OR IGNORE INTO clientes (harmonit_id, cnpjcpf, criado_em) SELECT id, cnpj_cpf, datetime('now') FROM harmonit_clientes WHERE cnpj_cpf IS NOT NULL AND cnpj_cpf != ''`
- `rastreadores` ← `harmonit_rastreadores` (4.031 registros, reimportado fresco em 2026-07-16 via `POST /Rastreador/ObterRastreadores`): `INSERT OR IGNORE INTO rastreadores (harmonit_id, serial, criado_em) SELECT id, equipamento, datetime('now') FROM harmonit_rastreadores WHERE equipamento IS NOT NULL AND equipamento != ''`

**Resultado: `clientes` 1→912, `rastreadores` 1→4031** (`INSERT OR IGNORE` preservou os registros de teste harmonit_id=99001 intactos). Backup do banco feito antes (`data/fpsl.db.bak_pre_seed_20260716`).

**Nota importante (correção de premissa, 2026-07-16):** esse seed NÃO era mais bloqueador de webhook Harmonit→FPSL — confirmamos que esse webhook não existe em nenhum dos dois sistemas (ver `13_Status.md` Sessão 5 e `09_Harmonit_WESO.md`). O seed continua útil pros endpoints `/weso/os/adicionar`/`/weso/os/desinstalar` de `routers/os.py` (mantidos como estão, caso um webhook real venha a existir), mas a feature ativa hoje ("Registrar Oficina", `painel/routers/oficina_router.py`) **não depende da tabela `rastreadores`** -- o serial já vem direto no campo `equipamentoId` de cada evento de Oficina retornado pelo Harmonit.

**Regra de escopo (reforçada, já documentada em outras sessões):** placa vazia/NULL é o único caso a excluir — "A DEFINIR", chassi, ou qualquer formato não-convencional (ex: futuro `8989-1` = número do termo + índice do contrato, usado como placeholder até a placa real ser definida via oficina) conta como placa válida se estiver no campo placa.

---

## AA — Comportamentos reais de `AdicionarOficina`/`DesinstalarOficina`/`ObterOficinas` (testados ao vivo, 2026-07-16)

Descobertos ao implementar a sincronização manual Oficina→WESO (ver `13_Status.md` Sessão 5 e `14_Oficina_WESO_Sync.md`).

| # | Comportamento | Evidência |
|---|---|---|
| AA1 | `trocaOficinaAntigaId` **não aceita `null`**, apesar do exemplo oficial da doc do Harmonit mostrar `null` | Testado ao vivo: `null` → 400 `"Error converting value {null} to type 'System.Int64'"`. Usar `0` quando não há troca. |
| AA2 | Resposta `{"status": false}` de `AdicionarOficina`/`DesinstalarOficina` **não é confiável** | Testado ao vivo: Oficina foi criada normalmente (`id` real em `ObterOficinas`) mesmo com `status: false` na resposta direta da chamada. Sempre confirmar via `ObterOficinas` depois, nunca confiar no `status` da resposta imediata. |
| AA3 | `ObterOficinas` é histórico de eventos, não estado mutável | `DesinstalarOficina` não altera o registro de instalação original -- cria um registro **novo** (`status:2`, `instalacaoId` apontando pro `id` do registro de instalação). |
| AA4 | "Troca" (`trocaOficinaAntigaId` preenchido) é indistinguível de instalação nova | Testado ao vivo: os dois casos geram um registro novo idêntico em estrutura (`status:1`), sem nenhum campo que aponte pro que foi substituído. |
| AA5 | `GET /OrdemServico/ObterOrdemServicoPorNumero` já retorna o array `oficina` embutido | Mesma estrutura de `GET /OrdemServico/ObterOficinas?osId=X` -- não precisa de uma segunda chamada separada pra ler os eventos de Oficina de uma OS. |

**Como aplicar:** qualquer código que crie/leia Oficina deve: (a) sempre mandar `trocaOficinaAntigaId: 0` quando não for troca, nunca `null`; (b) nunca decidir sucesso/falha pelo `status` da resposta direta, sempre reconsultar; (c) tratar `status:1`/`status:2` como eventos append-only, deduplicando por `id`, não como um único estado por placa/equipamento.

---

## B12 — Queda do Harmonit e o disjuntor (2026-07-28)

### O que aconteceu

Em 28/07, das ~02:07 até pelo menos 16:40, `GET /Account/Token` devolveu
**HTTP 400** com:

> *"An exception has been raised that is likely due to a transient failure...
> **Connect Timeout expired. All pooled connections are in use.**"*

É exaustão do pool de conexões MySQL **do lado deles** — a mensagem é o stack
interno do EF Core vazando na resposta.

**Confirmado pela própria Harmonit** no mesmo dia: *"a causa da instabilidade em
nossa plataforma já foi identificada... atualizações executadas após as 18h"*.

### Nosso volume — medido, não estimado

| | |
|---|---|
| Varredura | `LIMITE_BURACOS=10` a cada `INTERVALO_SCAN=300s` |
| Durante a queda | **~120 requisições/hora**, sempre sequenciais |
| Resync | até `RESYNC_JANELA=400`, 1× a cada 12 h |

**2 requisições por minuto não derrubam pool de ninguém**, e a primeira falha
ocorreu antes de qualquer insistência nossa. Não fomos a causa.

### Mas dois padrões nossos amplificavam

1. **`_token = None` em QUALQUER erro.** O erro deles não tinha nada a ver com
   token, mas descartávamos assim mesmo — e a chamada seguinte batia no
   `/Account/Token`, justamente o endpoint que sofria. **Cada leitura de OS
   virava uma autenticação.**
2. **Nenhum recuo.** A varredura reinsistia a cada 5 min, indefinidamente.

E um desperdício que só apareceu na conta: **mesmo com a API saudável**, se não há
OS nova a varredura consulta 10 números inexistentes a cada 5 min —
~2.880 requisições/dia, todas em vão.

### O disjuntor

`fpsl_weso/harmonit_client.py`:

| Parâmetro | Valor |
|---|---|
| `FALHAS_PARA_ABRIR` | 3 falhas seguidas de autenticação |
| `ESPERA_ABERTO_SEG` | 600 s (10 min) sem tocar a rede |

- Token só é descartado em **401** — o único erro que realmente fala de token.
- Aberto, responde **503** (não 502) com os segundos restantes.
- `estado()` expõe aberto/falhas/último erro — **torna a queda visível**, que era
  o outro achado: com `except HTTPException: d = None`, "API fora" ficava
  indistinguível de "buraco na numeração".

### Efeito medido (teste contra a API real caída)

| | Antes | Depois |
|---|---|---|
| Requisições/hora na queda | ~120 | **~18** |
| 20 chamadas com API fora | 20 requisições | **0,000 s, zero rede** |
| Diagnóstico | 502 genérico | 503 + motivo real guardado |

Teste: `tests/teste_disjuntor_harmonit.py` — **9/9**, validado contra a
indisponibilidade real, não contra mock.

### ✅ Nenhum dado foi perdido

`varrer_os` só avança o checkpoint em leitura bem-sucedida (`ultima` só se move
no caminho de sucesso, e grava `if ultima > checkpoint`). Com a API fora, o
checkpoint fica parado e a varredura **retoma do mesmo ponto**.

Confirmado na prática: a última OS local é a **16549**, e o usuário verificou no
painel do Harmonit que 16549 é de fato a última real.

**É por isso que recuar não custa nada** — não há dado sensível a tempo, então
esperar é estritamente melhor que insistir.
