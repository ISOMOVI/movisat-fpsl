# Harmonit — API de Ordens de Serviço

> **Auth:** `Authorization: Bearer TOKEN`  
> O módulo mais completo da API — 17 endpoints cobrindo o ciclo inteiro de uma OS.

---

## Endpoints

| Método | Rota                                          | Ação                                   |
|--------|-----------------------------------------------|----------------------------------------|
| GET    | `/OrdemServico/ObterOrdemServico`             | Buscar OS por ID                       |
| GET    | `/OrdemServico/ObterOrdemServicoPorNumero`    | Buscar OS por número                   |
| POST   | `/OrdemServico/SalvarOrdemServico`            | Criar/atualizar OS completa            |
| POST   | `/OrdemServico/SalvarOrdemServicoBasica`      | Criar OS básica (forma simplificada)   |
| DELETE | `/OrdemServico/RemoverOrdemServico`           | Excluir OS                             |
| GET    | `/OrdemServico/ObterTimeLine`                 | Histórico de status da OS              |
| GET    | `/OrdemServico/ObterMateriaisOrdemServico`    | Listar materiais da OS                 |
| POST   | `/OrdemServico/SalvarMaterialOrdemServico`    | Adicionar/atualizar material           |
| DELETE | `/OrdemServico/RemoverMaterialOrdemServico`   | Remover material da OS                 |
| GET    | `/OrdemServico/ObterTecnicoOrdemServico`      | Listar técnicos da OS                  |
| POST   | `/OrdemServico/SalvarTecnicoOrdemServico`     | Vincular técnico à OS                  |
| DELETE | `/OrdemServico/RemoverTecnicoOrdemServico`    | Remover técnico da OS                  |
| POST   | `/OrdemServico/AgendarTecnico`                | Agendar técnico (agenda)               |
| GET    | `/OrdemServico/ObterCheckListOrdemServico`    | Listar checklist da OS                 |
| POST   | `/OrdemServico/SalvarCheckListOrdemServico`   | Adicionar item ao checklist            |
| PUT    | `/OrdemServico/AtualizarStatusCheckList`      | Marcar item como executado/não executado|
| DELETE | `/OrdemServico/RemoverCheckListOrdemServico`  | Remover item do checklist              |
| GET    | `/OrdemServico/ObterOficinas`                 | Listar equipamentos instalados na OS   |
| POST   | `/OrdemServico/AdicionarOficina`              | Registrar instalação de rastreador     |
| POST   | `/OrdemServico/DesinstalarOficina`            | Registrar desinstalação de rastreador  |

---

## 1. Buscar OS

### Por ID

**GET** `/OrdemServico/ObterOrdemServico?osId=123`

### Por Número

**GET** `/OrdemServico/ObterOrdemServicoPorNumero?numeroOs=456`

### Resposta (OrdemServicoMobile)

```json
{
  "data": {
    "id": 123,
    "empresaId": 1,
    "numeroOrdem": 456,
    "dataPrevisao": "2024-05-30T10:00:00",
    "localServico": 1,
    "situacaoId": 2,
    "tipoId": 1,
    "prioridadeId": 3,
    "problemaId": 5,
    "clienteId": 101,
    "bairro": "Centro",
    "cep": "01000-000",
    "cidade": "São Paulo",
    "endereco": "Rua das Flores, 123",
    "uf": "SP",
    "descricaoDetalhada": "Instalação de rastreador veicular",
    "solucaoTecnica": "Rastreador instalado com sucesso"
  }
}
```

---

## 2. Criar OS Básica *(forma recomendada para criação rápida)*

**POST** `/OrdemServico/SalvarOrdemServicoBasica`

Versão simplificada — mínimo de campos para abrir uma OS.

```json
{
  "id": 0,
  "descricao": "Instalação de rastreador",
  "codigoProblema": 10,
  "codigoTipoOrdemServico": 1,
  "clienteId": 101
}
```

| Campo                    | Tipo    | Descrição                                               |
|--------------------------|---------|---------------------------------------------------------|
| `id`                     | integer | `0` para criar, ID para atualizar                       |
| `descricao`              | string  | Descrição da OS                                         |
| `codigoProblema`         | integer | Código do problema (obter via `/Problema/ObterProblemas`)|
| `codigoTipoOrdemServico` | integer | Código do tipo de OS (via `/TipoOrdemServico/...`)      |
| `clienteId`              | integer | ID do cliente                                           |

**Resposta 200:**
```json
{
  "data": {
    "ordemServicoId": 789,
    "numeroOrdem": 456,
    "dataSolicitadoEm": "2024-05-22T14:00:00",
    "status": "..."
  }
}
```

---

## 3. Criar/Atualizar OS Completa

**POST** `/OrdemServico/SalvarOrdemServico`

```json
{
  "id": 0,
  "empresaId": 1,
  "numeroOrdem": 0,
  "dataPrevisaoEntrega": "2024-06-01T10:00:00",
  "localServicoId": 1,
  "tipoId": 1,
  "prioridadeId": 2,
  "situacaoId": 1,
  "problemaId": 5,
  "produtoServicoId": 10,
  "clienteId": 101,
  "bairro": "Centro",
  "cep": "01000-000",
  "cidade": "São Paulo",
  "endereco": "Rua das Flores",
  "uf": "SP",
  "complemento": "Sala 1",
  "numero": "123",
  "descricaoDetalhada": "Instalação de rastreador veicular",
  "status": 1,
  "valorRetAlimentacao": 0.00,
  "valorRetProdutosLimpeza": 0.00,
  "valorRetValeTransporte": 0.00,
  "vendedorId": 5,
  "solucaoTecnica": ""
}
```

| Campo                    | Tipo    | Descrição                                               |
|--------------------------|---------|---------------------------------------------------------|
| `id`                     | integer | `0` para criar, ID para atualizar                       |
| `empresaId`              | integer | ID da empresa                                           |
| `localServicoId`         | integer | Local do serviço                                        |
| `tipoId`                 | integer | Tipo de OS (via `/TipoOrdemServico/...`)                 |
| `prioridadeId`           | integer | Prioridade (via `/PrioridadeAtendimento/...`)           |
| `situacaoId`             | integer | Status (via `/SituacaoOrdemServico/...`)                |
| `problemaId`             | integer | Problema/categoria (via `/Problema/...`)               |
| `produtoServicoId`       | integer | Produto ou serviço associado                            |
| `clienteId`              | integer | ID do cliente                                           |
| `vendedorId`             | integer | ID do vendedor responsável                              |
| `descricaoDetalhada`     | string  | Descrição detalhada do problema                         |
| `solucaoTecnica`         | string  | Solução técnica aplicada                                |

---

## 4. Excluir OS

**DELETE** `/OrdemServico/RemoverOrdemServico?osId=123`

---

## 5. Timeline da OS

**GET** `/OrdemServico/ObterTimeLine?osId=123`

Retorna o histórico completo de mudanças de status.

```json
[
  {
    "id": 1,
    "osId": 123,
    "numeroOs": "456",
    "status": 2,
    "statusDesc": "Em Andamento",
    "dataHora": "2024-05-22T14:30:00"
  },
  {
    "id": 2,
    "osId": 123,
    "numeroOs": "456",
    "status": 5,
    "statusDesc": "Concluída",
    "dataHora": "2024-05-22T17:00:00"
  }
]
```

---

## 6. Materiais da OS

### Listar

**GET** `/OrdemServico/ObterMateriaisOrdemServico?ordemServicoId=123`

**Resposta:**
```json
[
  {
    "id": 1,
    "produtoId": 10,
    "codigo": "PROD-001",
    "descricao": "Rastreador CRX3",
    "quantidade": 1,
    "valor": 350.00,
    "cobrar": true,
    "comodato": false
  }
]
```

### Adicionar/Atualizar Material

**POST** `/OrdemServico/SalvarMaterialOrdemServico`

```json
{
  "id": 0,
  "empresaId": 1,
  "osId": 123,
  "produtoId": 10,
  "quantidade": 1,
  "valor": 350.00,
  "cobrar": true,
  "locacao": false,
  "comodato": false,
  "quantidade_Fator": 1,
  "produtoConversaoUnidadeId": null,
  "locacaoBens": false,
  "pesoBruto": 0.5,
  "pesoLiquido": 0.45,
  "zonasParticoesId": null
}
```

### Remover Material

**DELETE** `/OrdemServico/RemoverMaterialOrdemServico?ordemServicoId=123&id=1`

---

## 7. Técnicos da OS

### Listar

**GET** `/OrdemServico/ObterTecnicoOrdemServico?osId=123`

```json
[
  {
    "id": 1,
    "osId": 123,
    "usuarioId": 50,
    "nomeTecnico": "Carlos Técnico",
    "email": "carlos@empresa.com"
  }
]
```

### Vincular Técnico

**POST** `/OrdemServico/SalvarTecnicoOrdemServico`

```json
{
  "osId": 123,
  "empresaId": 1,
  "tecnicoId": 50,
  "veiculoId": "VEI-001",
  "veiculoNome": "Fiat Uno",
  "veiculoPlaca": "ABC1234",
  "tecnicoResponsavelPelaOS": true
}
```

### Agendar Técnico

**POST** `/OrdemServico/AgendarTecnico`

```json
{
  "id": 0,
  "clienteId": 101,
  "ordemServicoId": 123,
  "ordemServicoxTecnicoId": 1,
  "inicioCompromisso": "2024-06-01T09:00:00",
  "fimCompromisso": "2024-06-01T11:00:00"
}
```

### Remover Técnico

**DELETE** `/OrdemServico/RemoverTecnicoOrdemServico?osId=123&id=1&agendaId=0`

> Se não houver `agendaId`, enviar `0`.

---

## 8. Checklist da OS

### Listar

**GET** `/OrdemServico/ObterCheckListOrdemServico?osId=123`

```json
[
  { "id": 1, "descricao": "Testar ignição", "tecnico": "Carlos", "status": false },
  { "id": 2, "descricao": "Verificar conexões", "tecnico": "Carlos", "status": true }
]
```

### Adicionar Item

**POST** `/OrdemServico/SalvarCheckListOrdemServico?osId=123&descricao=Testar GPS`

### Atualizar Status

**PUT** `/OrdemServico/AtualizarStatusCheckList?osId=123&checkListId=1&status=true`

| `status` | Significado      |
|----------|------------------|
| `true`   | Executado        |
| `false`  | Não executado    |

### Remover Item

**DELETE** `/OrdemServico/RemoverCheckListOrdemServico?osId=123&checkListId=1`

---

## 9. Oficinas (Instalações de Rastreador)

### Listar equipamentos instalados na OS

**GET** `/OrdemServico/ObterOficinas?osId=123`

```json
[
  {
    "id": 1,
    "instalacaoId": "INS-001",
    "equipamentoId": "EQP-456",
    "equipamentoDesc": "Rastreador CRX3",
    "veiculoPlaca": "ABC1234"
  }
]
```

### Registrar Instalação

**POST** `/OrdemServico/AdicionarOficina`

```json
{
  "empresaId": 1,
  "osId": 123,
  "tipoVeic": 1,
  "idAparelho": "EQP-456",
  "idVeiculo": "VEI-001",
  "rastreadorId": 501,
  "placaVeiculo": "ABC1234",
  "nomeVeiculo": "Fiat Uno",
  "trocaOficinaAntigaId": null,
  "tipo": 1
}
```

**Resposta:**
```json
{ "status": true, "message": "Instalado com sucesso" }
```

### Registrar Desinstalação

**POST** `/OrdemServico/DesinstalarOficina`

```json
{
  "empresaId": 1,
  "osId": 123,
  "ras_ins_id": "INS-001",
  "idAparelho": "EQP-456",
  "idVeiculo": "VEI-001",
  "rastreadorId": 501,
  "placaVeiculo": "ABC1234",
  "nomeVeiculo": "Fiat Uno",
  "tipo": 1,
  "veiculoId": 10
}
```

---

## Fluxo típico de uma OS

```
1. Criar OS básica
   POST /OrdemServico/SalvarOrdemServicoBasica
   → Obtém ordemServicoId

2. Vincular técnico
   POST /OrdemServico/SalvarTecnicoOrdemServico

3. Agendar técnico
   POST /OrdemServico/AgendarTecnico

4. Adicionar materiais
   POST /OrdemServico/SalvarMaterialOrdemServico

5. (Campo) Registrar instalação
   POST /OrdemServico/AdicionarOficina

6. Atualizar checklist
   PUT /OrdemServico/AtualizarStatusCheckList

7. Finalizar OS (mudar status via SalvarOrdemServico com novo situacaoId)
```

---

## Medido ao vivo em 21/10 — agendamento, vínculo e endereço

> Tudo abaixo foi medido na conta real, a maior parte só lendo. As escritas
> aconteceram na **OS 16991** (Velasco), que o usuário liberou para teste.

### `TecnicoJaAgendado` é do VÍNCULO, não do técnico

`AgendarTecnico` com `id: 0` recusa quando a linha `ordemServicoxTecnico`
escolhida **já tem** `agendamentoId`. Não é limite por técnico: lendo as 547 OS
da base, o mesmo `usuarioId` tem vários compromissos, inclusive **dois na mesma
OS** (14316 na OS 16921: agendamentos 935886 e 938166), e três no **mesmo
horário** em OS diferentes (8528, 08/10 às 08:00).

**O caminho que funciona**, provado na 16991: `SalvarTecnicoOrdemServico` cria
uma segunda linha de vínculo para o mesmo técnico, e `AgendarTecnico` com
`id: 0` nessa linha nova grava. Vínculo 1143048 → compromisso 945220.

### O endereço da OS tem oito campos, e a escrita é da OS INTEIRA

A OS devolve `cep` (8 dígitos, **sem máscara**, ao contrário do exemplo da doc
acima), `endereco` (a rua), `numero`, `bairro`, `cidade`, `uf`, `complemento` e
`localServico`.

Não existe rota de "atualizar endereço": é `SalvarOrdemServico`, a OS completa.
🚨 **Os nomes de leitura e de escrita não batem** — `tipo`→`tipoId`,
`localServico`→`localServicoId`, `prioridade`→`prioridadeId`,
`problema`→`problemaId`, `produtoId`→`produtoServicoId`,
`descricao`→`descricaoDetalhada`, `dataPrevisao`→`dataPrevisaoEntrega` (e de
`dd/mm/aaaa HH:MM:SS` para ISO).

⚠️ **`parceiro` é o `clienteId`** — 998063 na 16991. A nota antiga de que a OS
não traz o cliente valia para a chave `clienteId`, que de fato não existe no
retorno.

⚠️ `checkList`, `materiais`, `oficina` e `tecnico` são listas e **não vão** no
corpo da escrita; cada uma tem rota própria. Uma escrita no-op na 16991 (gravar
o mesmo endereço de volta) deixou as quatro intactas.

### Não há consulta de CEP no Harmonit

Conferido nas 17 rotas de OS e nas de dados de suporte. Quem precisa de CEP usa
fonte externa — o MoviZap usa o ViaCEP, pelo backend.

### Tipos de OS: 5 na lista, e nove ids fora dela

`/TipoOrdemServico/ObterListaTipoOrdemServico` devolve **lista crua** (sem
embrulho `data`) com 5 tipos, que cobrem **374 das 547** OS não excluídas. Os
outros **173** estão em nove ids que não constam da lista — 57, 76, 73, 72, 55,
77, 75, 576, 814 — tipos removidos ou renomeados. O caso do 55 já estava
registrado desde 14/08 em `os_router._resolver_cabecalho_por_nome`.

### Os compromissos de teste que existem hoje na OS 16991

🚨 Lista para não se confundirem com serviço real, e para serem apagados quando
ele mandar:

| agendamentoId | vínculo | técnico | janela | origem |
|---|---|---|---|---|
| 930447 | 1126373 | Iago | 05/10 15:22 | dele, antes desta frente |
| 944767 | 1126522 | Aline | 23/10 09:00 | meu, teste da escrita (21/10 manhã) |
| 944780 | 1130133 | Franck | 25/10 14:00 | meu, teste da escrita (21/10 manhã) |
| 945219 | 1143047 | Iago | 29/10 08:00 | meu, teste da barreira (21/10 tarde) |
| 945220 | 1143048 | Iago | 29/10 08:00 | meu, teste da barreira pela ponte |

Os vínculos **1143047** e **1143048** também foram criados por esses testes.
A OS teve o `numero` mudado de `S/N` para **26** (pedido dele) e o
`solucaoTecnica` passou de `null` para `""` numa escrita no-op minha, antes de
a causa ser corrigida.

### 21/10, noite — o que passou a ter teste, e o que continua só medido

🚨 **A auditoria do dia achou que as duas coisas mais delicadas desta página
não tinham teste**: a escrita de endereço (que é escrever a OS inteira) e o
segundo vínculo. As duas estavam provadas **ao vivo na OS 16991** — prova real,
mas que não se repete sozinha: uma regressão passaria verde.

`tests/teste_endereco_ponte.py` (20 testes, nenhum fala com o Harmonit) guarda
agora:

| O que | Por que estava em risco |
|---|---|
| `solucaoTecnica` vai **como está** | foi o `or ""` trocando `null` por `""` que o ensaio a seco pegou — e só pegou porque a escrita no-op comparou os 39 campos |
| `dataPrevisao` → ISO, e **formato desconhecido grita** | devolver `None` em silêncio apagaria a previsão, que é 100% preenchida e é o prazo que a aba Operações mede |
| `parceiro` ≠ `clienteId` | os nomes de leitura e de escrita não batem; usar o `parceiro` lido trocaria o cliente da OS |
| CEP sem máscara | a doc do Harmonit mostra `"01000-000"`, o dado real vem `"19013180"` — duas formas na mesma coluna |
| campo não enviado **não apaga** o que a OS tem | `None` no pedido é "não mexe" |
| `_diferencas` acusa campo **fora** do endereço | é o que permite dizer `fora_do_endereco` por extenso |
| o **segundo vínculo** é provado por **reler a OS** | o POST devolve um `osxTecId`, e confiar nele seria confiar no retorno em vez do estado |

⚠️ **O que continua só medido, e não testado:** que o Harmonit aceita o corpo
de escrita. Isso só a OS de verdade diz, e está registrado acima — por isso a
rota tem o `conferir` (ensaio a seco), que é o jeito de medir de novo sem
gravar.
