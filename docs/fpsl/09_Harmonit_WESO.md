# 09 — Integração Harmonit × WESO no FPSL

**Status:** 📋 Documentado — 2026-06-15
**Escopo:** FPSL como camada de tradução entre Harmonit (fonte única) e WESO (destino)

---

## Tabela de gatilhos

| Evento Harmonit | Rota FPSL | Endpoint WESO | Observação |
|----------------|-----------|---------------|-----------|
| `POST /Cliente/CadastrarOuAtualizar` | `POST /weso/clientes` | `POST /Clientes/Cadastro` | Ao criar/atualizar cliente no ERP |
| `POST /SIMCard/CadastrarOuAtualizar` | `POST /weso/simcards` | `POST /SimCard/Cadastro` | Ao entrar chip no estoque |
| `POST /Rastreador/Incluir` | `POST /weso/rastreadores` | `POST /Rastreadores/Cadastro` | Ao entrar equipamento no estoque |
| `POST /Veiculo/Incluir` | — | — | Só cadastra placa no ERP — sem ação na WESO |
| `POST /OrdemServico/AdicionarOficina` | `POST /weso/veiculos` | `POST /Veiculos/Cadastro` | Ao confirmar instalação física |
| `POST /OrdemServico/DesinstalarOficina` | `DELETE /weso/veiculos/placa/{placa}` | `POST /Veiculos/Excluir` | Substituição veicular (placa muda) |
| `PUT /Rastreador/Atualizar` (troca chip) | `PUT /weso/rastreadores/{id}/chip` | `POST /Rastreadores/Atualizar` | Troca de SIM Card em manutenção |

> `POST /Veiculo/Incluir` do Harmonit **não dispara ação no WESO**. O vínculo placa+equipamento é criado exclusivamente pelo `AdicionarOficina`.

> **Troca de equipamento (manutenção):** quando `trocaOficinaAntigaId != 0` no `AdicionarOficina`, o WESO sobrescreve o vínculo da mesma placa — nenhum DELETE necessário. **Atenção:** o campo não aceita `null` (usar `0`), e a troca não deixa nenhum rastro visível em `ObterOficinas` que a diferencie de uma instalação nova (ver `10_Inconsistencias.md` AA4).

> ⚠️ **Correção de arquitetura (2026-07-16): `AdicionarOficina`/`DesinstalarOficina` NÃO são webhooks do Harmonit.** São endpoints que o app de campo do Harmonit chama pra registrar a instalação -- o Harmonit não dispara nada sozinho. Confirmado: nem Harmonit nem WESO têm mecanismo de webhook de saída (busca exaustiva no Swagger + toda a documentação, zero resultado). **A tabela de gatilhos abaixo descreve o mapeamento de campos/lógica, não uma automação real.** A sincronização de fato é feita pela feature "Registrar Oficina" (`painel/routers/oficina_router.py`, ver `14_Oficina_WESO_Sync.md`) -- o operador registra a Oficina na tela nativa do Harmonit e depois aciona a sincronização manualmente no painel FPSL.

---

## Mapeamento de campos por entidade

### Cliente

| Campo Harmonit | Campo FPSL | Campo WESO | Tradução |
|----------------|-----------|------------|----------|
| `cnpj_cpf` | `cnpjcpf` | `cnpjcpf` | Direto — chave de identidade |
| `nome` | `razaoSocial` | `razaoSocial` | Direto |
| `nomeFantasia` | `nomeFantasia` | `nomeFantasia` | Direto |
| `pessoa` (`"Fisica"`/`"Juridica"`) | `tipoCliente` | `tipoCliente` | Direto — mesmos valores |
| `situacaoClienteDesc` + `bloqueado` | `situacao` | `situacao` | ⚠️ Tabela de tradução (ver abaixo) |
| `contatoPrincipal.nome` | `contato` | `contato` | Extração do objeto aninhado |
| `contatoPrincipal.telefone` | `telefone` | `telefone` | Extração do objeto aninhado |
| `contatoPrincipal.email` | `emailCobranca` | `emailCobranca` | ⚠️ Semântica diferente (ver `10_Inconsistencias.md G7`) |
| `enderecoPrincipal.logradouro` | `endereco` | `endereco` | Extração do objeto aninhado |
| `enderecoPrincipal.numero` | `numeroEnd` | `numeroEnd` | Extração do objeto aninhado |
| `enderecoPrincipal.bairro` | `bairro` | `bairro` | Extração do objeto aninhado |
| `enderecoPrincipal.cep` | `cep` | `cep` | Extração do objeto aninhado |
| `rg`, `im`, `ie`, `codigo`, `cidade`, `uf` | — | — | ❌ Sem destino no WESO — descartar |
| — | `plano` | `plano` | ❌ Sem origem no Harmonit — enviar null |
| — | `obs` | `obs` | ❌ Sem origem no Harmonit — enviar null |

---

### SIM Card

| Campo Harmonit | Campo FPSL | Campo WESO | Tradução |
|----------------|-----------|------------|----------|
| `numeroChip` (ICCID) | `iccId` | `iccId` | Direto — chave de identidade |
| `numeroLinha` | `numero` | `numero` | Direto |
| `operadoraId` (int) | — | — | ❌ WESO não tem campo de operadora — descartar |
| — | `apn` | `apn` | ❌ Sem origem no Harmonit |
| — | `situacao` | `situacao` | ❌ Sem origem no Harmonit |
| — | `valorMensalidade` | `valorMensalidade` | ❌ Sem origem no Harmonit |

---

### Rastreador

| Campo Harmonit | Campo FPSL | Campo WESO | Tradução |
|----------------|-----------|------------|----------|
| `equipamento` | `numeroSerie` | `numeroSerie` | Direto — chave de identidade |
| `modeloEquipamento` | `modelo` | `modelo.descricao` | ⚠️ Obrigatório no WESO, opcional no Harmonit |
| `numeroChip` (ICCID) | `iccId` | via `Rastreadores/Atualizar` | Vinculado após criação do rastreador |
| `simCardId`, `veiculoId`, `placa`, `veiculo` | — | — | Ignorados — vínculo via AdicionarOficina |
| — | `tipo` | `tipo.descricao` | ❌ Sem origem no Harmonit |
| — | `situacao` | `situacao.descricao` | ❌ Sem origem no Harmonit |
| — | `lote`, `notaFiscal`, `valorPago` | — | ❌ Sem origem no Harmonit |

---

### Instalação (AdicionarOficina → POST /weso/veiculos)

| Campo Harmonit | Resolução FPSL | Campo WESO | Status |
|----------------|---------------|------------|--------|
| `placaVeiculo` | Direto | `placa` | ✅ Implementado |
| `rastreadorId` (ID interno Harmonit) | Storage local: `rastreadores(harmonit_id → serial)` | `serial_rastreador` | ⚠️ Pendente (`10_Inconsistencias.md F3`) |
| `osId` → `clienteId` da OS | Storage local: `clientes(harmonit_id → cnpjcpf)` | `cnpjcpf_cliente` | ⚠️ Pendente (`10_Inconsistencias.md F4`) |
| `idVeiculo` → `tipo` | Lookup `GET /Veiculo/ObterVeiculos` → tradução de-para | `tipoEqp` (int) | ⚠️ Pendente (`10_Inconsistencias.md G5`) |
| `nomeVeiculo` | Direto | `descricao` | ✅ Direto |
| `trocaOficinaAntigaId` | Se `!= null` → troca de equip (não DELETE) | — | Contexto operacional apenas |

> **Estado atual:** Harmonit chama `POST /weso/veiculos` com os campos já resolvidos (placa, cnpjcpf, serial). A resolução automática via IDs internos do Harmonit é evolução futura ao receber webhook nativo.

---

### Desinstalação (DesinstalarOficina → DELETE /weso/veiculos/placa/{placa})

| Campo Harmonit | Resolução FPSL | Ação WESO |
|----------------|---------------|-----------|
| `placaVeiculo` | Path param `{placa}` | Busca `veiculo_id` no storage local |
| `rastreadorId` | Ignorado | FPSL resolve por placa → `veiculo_id` via SQLite |

> Uso correto: apenas quando o veículo **muda de placa** (substituição veicular). Troca de equipamento no mesmo veículo usa o próximo `AdicionarOficina` com `trocaOficinaAntigaId`.

---

## Tabelas de tradução

### Situação do cliente (Harmonit → WESO)

| `bloqueado` Harmonit | `situacaoClienteDesc` Harmonit | WESO `situacao` |
|:-------------------:|-------------------------------|----------------|
| `true` | (qualquer) | `"Bloqueado"` |
| `false` | Ativo / Normal / Adimplente | `"Adimplente"` |
| `false` | Inadimplente | `"Inadimplente"` |
| `false` | Teste / Trial | `"Teste"` |
| `false` | Em negociação | `"Negociacao"` |
| `false` | Cortesia / Demo | `"Cortesia"` |

> `bloqueado: true` tem precedência — sobrescreve qualquer `situacaoClienteDesc`.
> Como `situacaoClienteDesc` é texto livre no Harmonit, esta tabela deve ser mantida no FPSL e atualizada conforme os valores configurados no ERP.

---

### Tipo de veículo (Harmonit `tipo` → WESO `tipoEqp`)

| Harmonit `tipo` | WESO `tipoEqp` |
|----------------|---------------|
| Automóvel / Carro | `1` |
| Moto / Motocicleta | `2` |
| Caminhão | `3` |
| Ônibus | `4` |
| Trator | `6` |
| Barco / Embarcação | `7` |
| Caminhonete | `8` |
| Carreta | `9` |
| Bicicleta | `11` |

---

### EnumTipoEquipamento (campo `tipoVeic`/`tipo` no AdicionarOficina)

| Valor | Significado |
|-------|-------------|
| `1` | Rastreador veicular |
| `2` | Outro tipo de ativo rastreado |

> Atenção: este enum **não é** o tipo do veículo (Carro/Moto etc.). São campos distintos.

---

## Storage local — resolução de IDs

| Tabela SQLite | Quando salvar | Para que serve |
|---------------|--------------|----------------|
| `veiculos(placa, veiculo_id, criado_em)` | `POST /weso/veiculos` com `acao: "criado"` | Resolver `veiculo_id` para `DELETE /weso/veiculos/placa/{placa}` |
| `clientes(harmonit_id, cnpjcpf)` *(pendente)* | `POST /weso/clientes` | Resolver `clienteId` → `cnpjcpf` no `AdicionarOficina` |
| `rastreadores(harmonit_id, serial)` *(pendente)* | `POST /weso/rastreadores` | Resolver `rastreadorId` → `serial` no `AdicionarOficina` |

---

## Notas de arquitetura

**Fonte única:** Harmonit é o único sistema que origina dados. WESO é exclusivamente destino.

**Sem webhooks WESO:** WESO não envia eventos. Todo fluxo é unidirecional: Harmonit → FPSL → WESO.

**Seleção de integração:** O campo "qual integração usar" no painel Harmonit configura a **URL de webhook** — não é um campo no payload da API Harmonit. A API não expõe nenhum campo `integracaoId` ou similar (confirmado no Swagger v2026.0609.2110).

**URL por destino:** FPSL expõe `/weso/...` para WESO. Quando Fulltrack for adicionado, usará `/fulltrack/...` com o mesmo payload Harmonit sendo traduzido por `services/fulltrack/`.
