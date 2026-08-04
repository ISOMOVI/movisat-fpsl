# Report de Bug — Harmonit API

**Empresa:** Movisat
**Data:** 13/07/2026
**Severidade:** Alta — bloqueia operação em produção
**Ambiente:** API produção (`api-hc.harmonit.com.br:8086`)

---

## Resumo

Não é possível criar nem atualizar um `Rastreador` que vincule um `SIM Card` (`simCardId`) através da API pública. Toda tentativa — independente do `simCardId` usado — falha com o mesmo erro de colisão de chave interna: `Duplicate entry '197878' for key 'tb000407.tb000871_id'`.

O erro está confirmado como um **contador interno travado do lado do Harmonit**, não uma peculiaridade de payload. Bloqueia cadastro de rastreadores novos e correção de vínculos existentes.

---

## Como reproduzir

Qualquer chamada a `POST /Rastreador/Incluir` ou `PUT /Rastreador/Atualizar` que informe um `simCardId` não-nulo falha. Exemplo mínimo:

```
PUT /Rastreador/Atualizar
{
  "id": 107028,
  "simCardId": 122096,
  "modeloEquipamentoId": 53,
  "modeloEquipamento": "TK 100",
  "equipamento": "864895030166597",
  "placa": " ",
  "veiculo": " "
}
```

**Resposta:**
```
500 Internal Server Error
Duplicate entry '197878' for key 'tb000407.tb000871_id'
```

O mesmo erro ocorre com `simCardId: 0` (nulo/vazio) — nesse caso o erro muda para `Object reference not set to an instance of an object` (null reference), então **não existe nenhum valor de `simCardId` que funcione**, seja um SIM Card já vinculado, um SIM Card novo e nunca usado, ou vazio.

---

## Evidências (testado em produção, 03/07/2026)

Testamos com **4 valores completamente diferentes** de `simCardId` — incluindo um SIM Card recém-criado e nunca usado — e o erro de colisão foi **sempre no mesmo valor: `197878`**:

| Tentativa | `simCardId` usado | Resultado |
|---|---|---|
| 1 | `0` (vazio) | `Object reference not set to an instance of an object` |
| 2 | `122090` (SIM Card já vinculado a outro rastreador) | `Duplicate entry '197878'` |
| 3 | `122095` (SIM Card novo, criado exclusivamente pra esse teste, nunca usado antes) | `Duplicate entry '197878'` |
| 4 | `107028` (mesmo ID do próprio rastreador — hipótese de "ID gêmeo" testada e descartada) | `Duplicate entry '197878'` |

O valor da colisão (`197878`) **nunca muda**, independente do `simCardId` enviado — isso descarta qualquer explicação ligada ao conteúdo do payload. É um contador de auto-incremento da tabela interna `tb000407` (vínculo rastreador↔SIM Card, FK `tb000871_id`) que parou de avançar.

**Confirmado também em `PUT /Rastreador/Atualizar`, não só em `Incluir`** — testado tentando apenas inativar um rastreador (`ativar: false`) sem trocar o chip, e o mesmo erro ocorreu.

**Confirmado com rastreador real de produção** (serial `007460467`, id 13685), não só com registros de teste — mesmo erro, nenhuma mudança persistida.

---

## Confirmação via Swagger oficial (`swagger.json`, baixado 03/07/2026)

O schema `RastreadoresSaveViewModel` — usado tanto por `Incluir` quanto por `Atualizar` — define `simCardId` como `int64` **não-nulável**, sem campo alternativo:

```json
"simCardId": { "type": "integer", "format": "int64" }
```

Ou seja, não existe combinação de payload documentada que evite tocar essa coluna. O bug bloqueia o fluxo inteiro de cadastro/atualização de rastreador sempre que o vínculo com SIM Card precisa mudar.

---

## O que já foi descartado como causa

- **Não é payload inválido** — testado com 4 `simCardId` diferentes, incluindo um totalmente novo e nunca usado.
- **Não é "ID gêmeo" nem coincidência de sequência** — testado passando o próprio `id` do rastreador como `simCardId`, mesmo erro.
- **Não é limitação arquitetural** — confirmado que o modelo de dados aceita rastreador sem chip (`simCardId: 0`, `numeroChip: ""`) quando criado **pelo painel web** (rastreador id `107028`, "TESTEIAGO", criado sem erro nenhum via painel). O problema é específico da API pública (`/Rastreador/Incluir` e `/Rastreador/Atualizar`), não do modelo de dados em si.
- **Não é readonly by design** — os campos `instalado`/`ativar` existem no schema de leitura mas não no de escrita (aparentemente proposital, pra forçar mudança via Ordem de Serviço), mas isso é uma limitação diferente e não explica o erro 500 de colisão de chave.

---

## Impacto em produção (Movisat)

- **44 rastreadores** que existem na WESO mas faltam no Harmonit não podem ser cadastrados (sempre que têm chip real vinculado).
- **Correções de vínculo rastreador↔chip** em registros já existentes ficam bloqueadas sempre que a mudança precisa tocar `Rastreador/Atualizar` (troca de chip, reativação, etc.) — só é possível contornar quando a correção pode ser feita batendo direto no `SIMCard/Atualizar` sem tocar o rastreador, o que **não cobre todos os casos**.

---

## Pedido

Verificar e destravar o contador de auto-incremento (ou sequência equivalente) da tabela interna `tb000407` (chave `tb000871_id`). Ficamos à disposição para reproduzir o erro ao vivo com o time de suporte, se for útil.

**Registros de teste usados durante a investigação** (podem ser ignorados/limpos, não representam dados reais de cliente):
- Rastreador id `107028` ("TESTEIAGO")
- SIM Cards id `122090`, `122095`, `122096` ("TESTEIAGO")

---

# ✅ RESOLVIDO — reteste em 2026-08-03

O Harmonit avisou que corrigiu e pediu reteste. Retestado em produção, **os dois
cenários que falhavam voltaram**. O erro `Duplicate entry '197878' for key
'tb000407.tb000871_id'` **não ocorreu nenhuma vez**.

| Cenário | 2026-07-03 | 2026-08-03 |
|---|---|---|
| `PUT /Rastreador/Atualizar` trocando `simCardId` | `Duplicate entry '197878'` | ✅ 200, gravado e conferido no estado (122090→122095, revertido) |
| `POST /Rastreador/Incluir` criando rastreador | bloqueado (nem em 27/07 criou) | ✅ 200, criou id **109715**, base 4040→4041 |

⇒ **Criar rastreador por API deixou de ser impossível.** Destrava os 15
equipamentos genuinamente ausentes e o passo `POST /Rastreadores/Cadastro` da
Fase 2 do fluxo oficina→WESO.

**ICCID conferido intacto** nas duas escritas (armadilha do `numeroChip`
propagado pro SIM Card).

## O que NÃO foi resolvido junto

**`ativar: false` continua sem efeito** — `200 OK` e ignora, tanto no 109715
recém-criado quanto no 107028 travado desde 03/07. **Não é o `tb000407`**: é a
limitação separada já descrita neste report (`ativar`/`instalado` existem no
schema de leitura, não no de escrita — mudança só por Ordem de Serviço).
Mais um caso de "o retorno HTTP mente": 200 sem gravar nada.

## Resíduo permanente (Harmonit não tem DELETE)

- Rastreador **109715** `FPSLSEMCHIP001` — criado no reteste de hoje
- Rastreador **107028** `TESTEIAGO` — de 03/07, segue ativo e não inativável
- SIM Cards **122090**, **122095**, **122096** `TESTEIAGO`

## 🚨 O CSV de correção dos 50 casos ficou DEFASADO

`CASOS_tb000407_2026-07-27.csv` — os 50 continuam pendentes (44 com `simCardId`
igual ao próprio id do rastreador, dado auto-referente). Mas os **destinos** já
não valem:

- **47 de 50** apontam para SIM Cards cujo `numeroChip` hoje é `DUPLICADO-<iccid>`
  — foi a **nossa própria** neutralização de 27/07 (1.020 chips → Pós-Auditoria 855).
- **3 de 50** apontam para chip **já vinculado a outro rastreador**
  (15789→11193 · 15821→33954 · 10753→8155): aplicar rouba o chip do outro veículo.

⇒ **Não aplicar este CSV.** O remapeamento tem que ser recalculado do estado
atual da base antes de qualquer lote. Decisão do usuário em 03/08: nada escrito
em produção por enquanto.

Scripts do reteste: `backups/scripts_avulsos_2026-08/` (`recon_tb000407.py`,
`reteste_tb000407.py`, `analise_50_casos.py`, `inativar_residuo.py`).
