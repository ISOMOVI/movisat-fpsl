# 20 — Fluxo oficial Oficina→WESO, fila de sync e reconciliação

**Reescrito em 2026-07-27** com as decisões do usuário. Substitui a versão anterior.
Tudo aqui é baseado no que foi **medido** na API (`10_Inconsistencias.md` B10/B11), não no
que a documentação promete.

---

## O fluxo perfeito (decidido pelo usuário)

```
[1] OPERADOR, no painel HARMONIT (manual, fora do FPSL)
      cadastra o CHIP  →  cadastra o EQUIPAMENTO  →  ativa  →  vincula os dois
      ⚠️ "ativar" só dá pra fazer/conferir na TELA: a API retorna 200 e ignora

[2] FPSL, a partir do TERMO (P1/P2)
      cria o CLIENTE  e  cria a PLACA na WESO, já com os dados do termo
      (marca/modelo/cor só existem aqui — a oficina não traz isso)

[3] OPERADOR registra a OFICINA no Harmonit  (início do atendimento do técnico)

[4] FPSL varre as OS, acha o evento de oficina, e na WESO:
      garante que EQUIPAMENTO e CHIP existem  →  VINCULA à placa
      ⇒ 100% de satisfação: placa + equipamento + chip amarrados
```

**A oficina VINCULA, nunca CRIA do zero.** O evento só traz `equipamentoId` (serial),
`veiculoPlaca` e `status` — falta `modelo`, falta ICCID e falta cliente.

**A fonte do ICCID é o HARMONIT**, não a oficina: `ObterRastreadores` devolve
`numeroChip` do equipamento. Decidido em 27/07.

---

## Pré-requisito: pareamento 100% de ICCID e serial

O vínculo só funciona se os dois já existirem na WESO. Duas frentes:

- **Incremental** (daqui pra frente): a fila abaixo garante.
- **Passivo** (o que já existe torto): cruzamento de julho achou **186** equipamentos na
  WESO sem par no Harmonit, **455** no Harmonit sem par na WESO e **1.024** com chip
  diferente. ✅ **Agora dá pra corrigir** — o `tb000407` caiu em 27/07.
  **Decisão do usuário: validar com 1 de cada tipo antes de pensar em lote.**

---

## A fila de sincronização

Uma tabela de trabalho (`weso_sync_fila`) com **ordem de dependência garantida**. É o que
permite "a oficina cria em caso de inexistência" **sem quebrar a ordem**.

| Campo | Para quê |
|---|---|
| `id`, `tipo` | `chip` · `equipamento` · `vinculo_chip_equip` · `vinculo_equip_placa` |
| `chave` | `iccId` / `numeroSerie` / `placa` — é o que torna a operação idempotente |
| `depende_de` | id de outro item da fila; não processa antes dele |
| `estado` | `pendente` · `processando` · `ok` · `erro` · `bloqueado` |
| `tentativas`, `ultimo_erro`, `proxima_tentativa` | retry com backoff |
| `origem` | `oficina` (sob demanda) ou `rotina` (horária) |

### Ordem obrigatória

```
chip  →  equipamento  →  vínculo chip↔equipamento  →  vínculo equipamento↔placa
```

O chip vem primeiro porque nasce **dentro** do `/Rastreadores/Cadastro`
(`simCard:{iccId}`). A placa já existe (veio do termo, passo [2]).

### Dois gatilhos, uma fila

- **Oficina (imediato):** ao detectar o evento, resolve na hora o que der. O que faltar
  entra na fila, **respeitando `depende_de`** — nunca vincula antes de existir.
- **Rotina horária, 08–18:** drena a fila (pendências e erros com backoff vencido).
  Cobre a janela em que a oficina acontece logo após o cadastro, e o retry do que falhou.

Fora de 08–18 a fila só acumula — decisão do usuário, e é coerente: o cadastro no Harmonit
é manual e acontece em horário comercial.

### Idempotência: consultar antes de criar

Confirmado em 27/07 que a consulta pontual por numeração é barata e confiável:

| Alvo | Consulta |
|---|---|
| chip | `GET /SimCard/Consultar?iccId=` |
| equipamento | `GET /Rastreadores/Consultar?numeroSerie=` |
| placa | `GET /Veiculos/Consultar?placa=` (normalizada por `placas.py`) |

⚠️ **Sem filtro, `/Rastreadores/Consultar` dá 524** — nunca varrer a lista inteira para
checar um item. O **diff diário** continua existindo, mas como **rede de segurança**, não
como caminho principal.

### Regras que a fila precisa respeitar

1. **`500` no vínculo equipamento↔placa é ESPERADO** quando o equipamento tem chip
   (reproduzido 2/2). **Nunca decidir retry pelo HTTP** — só depois de reler.
2. **Read-after-write em toda escrita.** `200` pode não ter feito nada; `400/500` pode ter
   gravado. É a regra que vale para os dois sistemas.
3. **Erro não apaga o item da fila** — vira `erro` com backoff, e fica visível no painel.
4. **N falhas seguidas → `bloqueado` + alerta.** Não insistir para sempre.
5. **Chip `Cancelado` some da listagem** — se a consulta não achar, checar antes de recriar,
   senão duplica.

---

## Painel

Aba de sincronização (ao lado de "Histórico de OS"): fila por estado, o que está bloqueado,
último erro por item, e **retry manual**. Mesmo padrão da aba Oficinas, que já registra
sucesso **e** falha.

---

## Plano de validação — 1 de cada antes de qualquer lote

Decisão do usuário em 27/07. Ordem:

| # | Teste | Confirma |
|---|---|---|
| 1 | 1 **chip** que existe no Harmonit e falta na WESO | criação + idempotência |
| 2 | 1 **equipamento** que falta na WESA, com chip junto | `/Rastreadores/Cadastro` + `simCard` |
| 3 | 1 **vínculo** equipamento↔placa (equipamento COM chip) | o 500 esperado, e o read-after-write |
| 4 | 1 caso de **chip divergente** (dos 1.024) | correção sem quebrar vínculo |
| 5 | 1 **evento de oficina real** ponta a ponta | o fluxo inteiro |

Só depois disso, lote. É o mesmo método que funcionou hoje com as placas e o RD: **lista
revisada e 1 caso validado antes de escrever em massa** — e o que evitou repetir o
incidente dos 974 chips de julho.

---

## Reconciliação diária (rede de segurança)

Espelho WESO + espelho Harmonit → diff → **relatório, sem correção automática**.

| Divergência | Ação |
|---|---|
| equipamento só no Harmonit | entra na fila |
| equipamento só na WESO | relatório (cadastro manual lá) |
| chip diferente entre os dois | relatório → validar → corrigir |
| placa diferente, mesmo `rastreador_id` | **renomeação** — atualiza espelho, não recria |
| rastreador `Instalado` sem veículo | relatório (não dá pra corrigir: `situacao` read-only) |

⚠️ **Paginação não funciona em nenhum dos dois sistemas** — devolve a base inteira sempre.
Nunca paginar em loop; em rotina de escrita, isso duplica.

---

## Ponto em aberto

**Custo da placa ativa sem equipamento.** A placa nasce no termo e o equipamento só chega
na instalação — se a cobrança for por placa ativa, essa janela custa. Se for por
equipamento vinculado, não. Levantado pelo usuário em 27/07; **não muda o desenho**, mas
vale confirmar.
