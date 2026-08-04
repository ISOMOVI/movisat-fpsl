# Harmonit — Ativos: Rastreador, SIM Card e Veículo

> **Auth:** `Authorization: Bearer TOKEN`  
> Estes módulos gerenciam os ativos físicos no ERP Harmonit — diferente dos ativos na WESO.

---

## Rastreadores

| Método | Rota                          | Ação                        |
|--------|-------------------------------|-----------------------------|
| POST   | `/Rastreador/ObterRastreadores` | Listar rastreadores        |
| POST   | `/Rastreador/Incluir`         | Cadastrar rastreador        |
| PUT    | `/Rastreador/Atualizar`       | Atualizar rastreador        |

### Listar Rastreadores

**POST** `/Rastreador/ObterRastreadores`

> Body não documentado no spec — enviar `{}` ou body vazio em teste.

### Cadastrar Rastreador

**POST** `/Rastreador/Incluir`

```json
{
  "id": 0,
  "modeloEquipamentoId": 3,
  "modeloEquipamento": "CRX3",
  "equipamento": "SN-9876543210987",
  "simCardId": 150,
  "numeroChip": "89559988776655443322",
  "numeroLinha": "11987654321",
  "veiculoId": 10,
  "placa": "ABC1234",
  "veiculo": "Fiat Uno"
}
```

| Campo               | Tipo    | Descrição                              |
|---------------------|---------|----------------------------------------|
| `id`                | integer | `0` para criar                         |
| `modeloEquipamentoId`| integer| ID do modelo de equipamento            |
| `modeloEquipamento` | string  | Descrição do modelo                    |
| `equipamento`       | string  | Número de série / identificador        |
| `simCardId`         | integer | ID do SIM Card vinculado               |
| `numeroChip`        | string  | ICCID do SIM Card                      |
| `numeroLinha`       | string  | Número da linha do SIM Card            |
| `veiculoId`         | integer | ID do veículo vinculado                |
| `placa`             | string  | Placa do veículo                       |
| `veiculo`           | string  | Descrição do veículo                   |

### Atualizar Rastreador

**PUT** `/Rastreador/Atualizar`

Mesmos campos do Incluir, com `id` do rastreador a ser atualizado.

---

## SIM Cards

| Método | Rota                          | Ação                          |
|--------|-------------------------------|-------------------------------|
| POST   | `/SIMCard/ObterSIMCards`      | Listar SIM Cards (filtrado)   |
| GET    | `/SIMCard/ObterPorId`         | Buscar SIM Card por ID        |
| POST   | `/SIMCard/CadastrarOuAtualizar` | Criar ou atualizar SIM Card |
| PUT    | `/SIMCard/Atualizar`          | Atualizar SIM Card (PUT)      |

### Listar SIM Cards

**POST** `/SIMCard/ObterSIMCards`

| Query Param  | Tipo    | Descrição                        |
|--------------|---------|----------------------------------|
| `numeroChip` | string  | Filtrar por ICCID                |
| `numeroLinha`| string  | Filtrar por número da linha      |
| `operadoraId`| integer | Filtrar por operadora            |
| `skip`       | integer | Offset                           |
| `take`       | integer | Limite                           |

```
POST /SIMCard/ObterSIMCards?numeroChip=8955&skip=0&take=20
```

### Buscar SIM Card por ID

**GET** `/SIMCard/ObterPorId?simCardId=150`

### Cadastrar ou Atualizar SIM Card

**POST** `/SIMCard/CadastrarOuAtualizar`

```json
{
  "id": 0,
  "numeroChip": "89559988776655443322",
  "numeroLinha": "11987654321",
  "operadoraId": 3
}
```

| Campo        | Tipo    | Descrição                                        |
|--------------|---------|--------------------------------------------------|
| `id`         | integer | `0` para criar, ID para atualizar                |
| `numeroChip` | string  | ICCID do chip                                    |
| `numeroLinha`| string  | Número da linha de telefone                      |
| `operadoraId`| integer | ID da operadora (obter via `/Operadora/ObterOperadoras`) |

### Atualizar SIM Card (PUT)

**PUT** `/SIMCard/Atualizar`

Mesmos campos do CadastrarOuAtualizar.

> **Atenção:** existe tanto `POST /CadastrarOuAtualizar` quanto `PUT /Atualizar` com o mesmo schema — verificar qual é o padrão adotado pelo sistema.

---

## Veículos

| Método | Rota                       | Ação                         |
|--------|----------------------------|------------------------------|
| GET    | `/Veiculo/ObterVeiculos`   | Listar todos os veículos     |
| GET    | `/Veiculo/ObterTipoEMarca` | Listar tipos e marcas        |
| POST   | `/Veiculo/Incluir`         | Cadastrar veículo            |
| PUT    | `/Veiculo/Atualizar`       | Atualizar veículo            |

### Listar Veículos

**GET** `/Veiculo/ObterVeiculos`

Sem parâmetros — retorna todos os veículos da empresa.

### Listar Tipos e Marcas

**GET** `/Veiculo/ObterTipoEMarca`

Lookup para popular os campos `tipo` e `marca` no cadastro.

### Cadastrar Veículo

**POST** `/Veiculo/Incluir`

```json
{
  "id": 0,
  "veiculo": "Fiat Uno",
  "placa": "ABC1234",
  "cor": "Branco",
  "ano": 2022,
  "numeroChassi": "9BWZZZ377VT004251",
  "modelo": "Uno Vivace",
  "combustivel": "Flex",
  "consumo": "12km/L",
  "limiteVelocidade": "80",
  "odometro": 50000,
  "tipo": "Automóvel",
  "marca": "Fiat",
  "clienteId": 101
}
```

| Campo            | Tipo    | Descrição                                     |
|------------------|---------|-----------------------------------------------|
| `id`             | integer | `0` para criar                                |
| `veiculo`        | string  | Nome/descrição do veículo                     |
| `placa`          | string  | Placa                                         |
| `cor`            | string  | Cor                                           |
| `ano`            | integer | Ano do modelo                                 |
| `numeroChassi`   | string  | Número do chassi                              |
| `modelo`         | string  | Modelo específico                             |
| `combustivel`    | string  | Tipo de combustível                           |
| `consumo`        | string  | Consumo médio                                 |
| `limiteVelocidade`| string | Limite de velocidade configurado              |
| `odometro`       | integer | Odômetro inicial em km                        |
| `tipo`           | string  | Tipo (obter via `/Veiculo/ObterTipoEMarca`)   |
| `marca`          | string  | Marca (obter via `/Veiculo/ObterTipoEMarca`)  |
| `clienteId`      | integer | ID do cliente proprietário                    |

### Atualizar Veículo

**PUT** `/Veiculo/Atualizar`

Mesmos campos do Incluir, com `id` do veículo a ser atualizado.

---

## Diferença entre Harmonit e WESO para estes ativos

| Aspecto            | WESO                              | Harmonit                           |
|--------------------|-----------------------------------|------------------------------------|
| Rastreador         | `/Rastreadores/` (CRUD completo)  | `/Rastreador/` (sem DELETE)        |
| SIM Card           | `/SimCard/` (por ICCID)           | `/SIMCard/` (por numeroChip)       |
| Veículo            | `/Veiculos/` (com complemento)    | `/Veiculo/` (mais simples)         |
| Auth               | `?key=` na URL                    | `Bearer Token` no header           |
| Numeração          | `iccId` (padrão ICCID)            | `numeroChip` (mesmo campo)         |
