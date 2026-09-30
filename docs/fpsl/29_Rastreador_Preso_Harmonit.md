# 29 — Rastreador preso no Harmonit: como consultar e corrigir

> Plano de CONSULTA, não automação — decisão do usuário em 2026-09-29:
> *"só quero um plano para consultar quando eu pedir mesmo, não vamos
> automatizar isso"*. Cada escrita abaixo é feita à mão, com a palavra dele.
>
> Tudo aqui foi MEDIDO no caso do 907112547 (29/09), relendo o estado depois
> de cada chamada. O Harmonit responde 200 e ignora; a prova é sempre reler.

---

## 1. Sintoma

O equipamento não pode ser usado em instalação nova. No rastreador:

- `instalado: true`
- `veiculoId: 0` (ou um veículo que não é mais dele)
- `placa`, `veiculo` e `contato` ainda mostram o cliente antigo

Causa típica: o equipamento perdeu o vínculo com o veículo sem que a
instalação original fosse fechada por oficina de desinstalação. A OS de
correção costuma dizer isso na descrição ("não foi realizada oficina de
retirada dessa placa anteriormente").

---

## 2. O que o usuário passa

| Dado | Exemplo (caso de referência) |
|---|---|
| Número de série do rastreador | 907112547 |
| OS de correção (registra a retirada) | 16972 |
| OS nova (recebe a instalação) | 16933 |
| Placa de destino | GKD 3D08 |

⚠️ **Número da OS ≠ id da OS no Harmonit.** Sempre dizer os dois
(16972 = id 898322; 16933 = id 893362).

⚠️ **Cliente "0 - X" é o `codigoCliente`, não o id.** "0 - Moto Help Matriz"
é `clienteId` **886302**. `clienteId: 0` é aceito e ignorado.

---

## 3. Leitura antes de qualquer escrita

| O quê | Rota | Observação |
|---|---|---|
| Rastreador | `POST /Rastreador/ObterRastreadores` (corpo `{}`) | Traz a base inteira; filtrar por `equipamento` = número de série. Campos: `id`, `instalado`, `veiculoId`, `placa`, `veiculo`, `contato`, `simCardId`, `numeroChip` |
| Veículos | `GET /Veiculo/ObterVeiculos` | **Ignora todos os filtros**, lê a base inteira (~9 mil). Filtrar por placa normalizada (só A-Z0-9). Guardar o TOTAL para comparar depois |
| OS por número | `GET /OrdemServico/ObterOrdemServicoPorNumero?numeroOs=N` | Dá o `id` (osId), `statusStr`, `parceiro` (cliente), `descricao` |
| Oficinas da OS | `GET /OrdemServico/ObterOficinas?osId=ID` | `status` 1 = instalação, 2 = desinstalação |
| Materiais da OS | `GET /OrdemServico/ObterMateriaisOrdemServico?ordemServicoId=ID` | 🚨 Parâmetro é `ordemServicoId`, não `osId` — única rota de OS fora do padrão |
| Cliente | `GET /ObterCliente?Id=N` · `GET /ObterClientes?skip&take&somenteAtivos` | `take` máximo 100. Retorno `{sumario:{contador}, lista}` |
| Chip | `POST /SIMCard/ObterSIMCards` | Conferir se o `simCardId` do rastreador tem `numeroChip` |

Conferir antes de escrever:

1. A placa de destino é **um** veículo só, do cliente esperado.
2. A placa de destino **não tem outro rastreador** ligado (`veiculoId`).
3. O cliente da OS nova (`parceiro`) é o dono da placa de destino.
4. A OS nova ainda não tem oficina desse equipamento (não duplicar).

🚨 **`harmonit_get`/`harmonit_post` já tiram o envelope `data`** (`_parse` em
`harmonit_client.py`). Fazer `.get("data")` de novo dá `None`, e a busca volta
vazia **sem erro** — foi assim que o cliente Moto Help "não existia" na primeira
consulta.

---

## 4. Passos que funcionaram (29/09)

Cada passo: ler antes → escrever → **reler** → conferir total de veículos.

### 4.1 Vincular o rastreador à placa de destino

`PUT /Rastreador/Atualizar`

```json
{"id": <rastreador>, "modeloEquipamentoId": <atual>, "modeloEquipamento": "<atual>",
 "equipamento": "<série>", "simCardId": <atual>,
 "numeroChip": "<atual ou vazio>", "numeroLinha": "<atual ou vazio>",
 "veiculoId": <id do veículo de destino>,
 "placa": "<placa EXATA do veículo>", "veiculo": "<nome EXATO do veículo>"}
```

Resultado medido: `veiculoId`, `placa` e `veiculo` mudam; o painel de
rastreadores passa a mostrar o cliente do veículo. **Não criou duplicata.**
O `contato` e o `instalado` **não** mudam.

- 🚨 `veiculoId` é OBRIGATÓRIO. Sem ele o Harmonit **cria veículo** com a placa
  do texto — foram **88 veículos duplicados e 93 vínculos quebrados** em 27/07.
- 🚨 `numeroChip` e `numeroLinha` vão sempre, mesmo vazios. Omitir **apaga o
  ICCID** do SIM Card.

### 4.2 Oficina de instalação na OS nova

`POST /OrdemServico/AdicionarOficina`

```json
{"empresaId": 98, "osId": <id da OS nova>, "tipoVeic": 1, "tipo": 1,
 "idAparelho": "<série>", "idVeiculo": "<id do veículo>", "rastreadorId": <rastreador>,
 "placaVeiculo": "<placa>", "nomeVeiculo": "<nome do veículo>",
 "trocaOficinaAntigaId": 0}
```

Resultado medido: responde `{"status": false}` mas **grava** a linha
(status 1). **Não mexe no rastreador.**

- ⚠️ `trocaOficinaAntigaId`: em OS de troca, pelo nome, liga a instalação à
  desinstalação do equipamento que sai. Nunca testado — gravou-se 0.

### 4.3 Finalização

Quem finaliza a OS é o usuário, na tela. Depois, **reler o rastreador**.

---

## 5. O que NÃO fazer (medido — o Harmonit responde 200 e ignora)

| Tentativa | Resultado |
|---|---|
| `Rastreador/Atualizar` com `veiculoId: 0` e placa `" "` | ignorado |
| `Rastreador/Atualizar` com `instalado: false` | ignorado — `instalado` não é gravável por essa rota |
| `clienteId: 0` para "sem cliente" | aceito e ignorado; só 5 de 9.079 veículos têm, todos lixo |
| Criar instalação na OS de correção só para ter o `ras_ins_id` e desinstalar | encerra a instalação CRIADA, não a original. Saldo zero (OS 16972) |
| Finalizar a OS de correção esperando mudar `instalado` | não mudou nada (OS 16972) |
| Trocar o cliente do veículo antigo para "limpar" o rastreador | não mexe no rastreador e põe o veículo no cliente errado |
| Apagar veículo duplicado | **Não existe DELETE de veículo no Harmonit.** Duplicata não se desfaz pela API |

### Rota de desinstalação, para referência

`POST /OrdemServico/DesinstalarOficina` — exige `ras_ins_id` = id da oficina
de **instalação** que ela encerra. Só faz sentido com a instalação ORIGINAL
do equipamento (que costuma estar numa OS antiga).

```json
{"empresaId": 98, "osId": <id>, "ras_ins_id": "<id da instalação>",
 "idAparelho": "<série>", "idVeiculo": "<id>", "veiculoId": <id>,
 "rastreadorId": <rastreador>, "placaVeiculo": "<placa>",
 "nomeVeiculo": "<nome>", "tipo": 1}
```

---

## 6. Critério de pronto e o que ficou sem resposta

✅ **Caso de referência CONCLUÍDO em 29/09, com o OK do usuário:** *"já está
ok ... já tem meu Ok, demanda concluída"*. O critério dele foi o **painel de
rastreadores mostrar o cliente novo** — que é o efeito do passo 4.1. A
finalização da OS nova (16933) fica com outra pessoa e **não é parte da
correção**.

Conhecimento que ficou sem resposta (não é pendência — só vale se um caso
futuro exigir):

- O `contato` antigo e o `instalado: true` **não mudaram por nenhum caminho**
  testado. Origem provável do contato: a instalação original aberta (não
  provado). Não impediram o uso no painel.
- Não se mediu se finalizar a OS nova muda o `contato`. Se um caso futuro
  precisar do contato limpo: (a) procurar a instalação original lendo
  `ObterOficinas` das OS antigas e desinstalar apontando para ela; ou
  (b) suporte do Harmonit.
- Chip: no caso de referência o SIM Card 10655 estava **vazio** (sem
  `numeroChip`, `numeroLinha`, `operadoraId`). Conferir o chip sempre — sem
  ele o equipamento não comunica.

---

## 7. Caso de referência — 907112547 (29/09/2026)

| Item | Valor |
|---|---|
| Rastreador | id 10655, SUNTECH 340 RB, SIM Card 10655 (vazio) |
| Cliente antigo | Colonial Comércio de Massas e Assados, `clienteId` 60743, veículo 6251 (EPW 0I21) |
| Cliente novo | Moto Help Entregas (Matriz), `clienteId` 886302, `codigoCliente` "0" |
| Veículo de destino | 86503, GKD 3D08, "Anderson Fernandes Esporadico" |
| OS de correção | 16972 (id 898322), cliente 60743. Oficinas 210219 (instalação criada por engano) e 210220 (desinstalação dela). Finalizada pelo usuário |
| OS nova | 16933 (id 893362), cliente 886302, troca: sai 907124846 (oficina 210222), entra 907112547 (oficina **210223**) |
| Vínculo | `Rastreador/Atualizar` com `veiculoId` 86503 — funcionou |
| Base de veículos | 9.079 antes e depois de todas as escritas — nenhuma duplicata |

Scripts do dia (só referência, não são rotina): `fpsl_weso/investigar_os_16972.py`,
`desinstalar_os_16972.py`, `soltar_rastreador_10655.py`,
`desmarcar_instalado_10655.py`, `vincular_10655_gkd3d08.py`,
`oficina_16933_gkd.py`, `consultar_pelo_cliente.py`.

Precedentes: `backups/scripts_avulsos_2026-08/desinstalar_hbg.py`,
`exp_oficina.py`, `testar_hipotese_os.py`, `diag_desinstalacao.py`.
