---

## Usuário

**Função:** Cadastrar usuário de acesso à plataforma WeFleet (e-mail + senha)

**Erro:** Endpoint não existe na API. O formulário existe no painel web com os campos `email`, `senha`, `status`, `nomeCompleto`, `telefone`, `endereco`, `observacoes`, mas nenhuma rota correspondente foi encontrada em `apirota.wesotecnologia.com.br`. Testadas variações: `/Usuario/Cadastro`, `/Usuarios/Cadastro`, `/Acesso/Cadastro`, `/Gestor/Cadastro`, `/Operador/Cadastro`, `/Clientes/AdicionarUsuario` e outras.

**Retorno:**
```
HTTP 404 — The resource cannot be found.
(todas as variações testadas)
```

---

## Chip

**Função:** Verificar se ICCID já existe via `GET /SimCard/Consultar`

**Status ATUALIZADO em 02/07/2026:** o bloqueio original (`HTTP 500 sensitive information`) **não ocorre mais quando a consulta é filtrada por `iccId`**. Testado com ICCID real `8955170000207915365` → `HTTP 200`, retorno completo e estruturado (ver `docs/weso/04_SimCards.md`).

**O que continua quebrado:** `GET /SimCard/Consultar` **sem nenhum filtro** (tentando listar todos os chips da empresa) ainda estoura timeout — mesmo padrão de lentidão de `/Rastreadores/Consultar` e `/Veiculos/Consultar` (provável causa: resposta não paginada, volume grande demais).

**Recomendação atualizada:** usar `GET /SimCard/Consultar?iccId=...` diretamente para checar existência — não precisa mais do fallback via `POST /SimCard/Cadastro` + interpretar erro 409. Isso evita o risco (mesmo que pequeno) de side-effects num endpoint de escrita usado só pra leitura.

**Retorno — cadastro com ICCID já existente (ainda válido como alternativa, mas não mais necessário):**
```json
{ "Status": "error", "Error": { "Code": 409, "Message": "ICCID já cadastrado.", "Details": [{ "Field": "iccId", "Issue": "Este ICCID já existe no sistema para sua empresa." }] } }
```

---

## Equipamento

**Função:** Cadastrar rastreador e vincular chip via `POST /Rastreadores/Cadastro`

**Erro:** Campo `modelo` é obrigatório mas não estava documentado como tal. Confirmado em dois testes: serial `007559809` (existente) e serial `997559809` (novo). Sem `modelo` → 400. Com `modelo` → 201. O endpoint composto `POST /Veiculos/Cadastro` não exige `modelo` ao referenciar rastreador pelo serial.

**Retorno — sem modelo (falhou):**
```json
{ "Status": "error", "Error": { "Code": 400, "Message": "Modelo do rastreador é obrigatório.", "Details": [{ "Field": "modelo", "Issue": "Campo obrigatório" }] } }
```

**Retorno — com modelo (sucesso):**
```json
{ "Status": "success", "Data": { "id": 49128, "numeroSerie": "997559809", "simcard_id": null } }
```

**Solução no fluxo real:** rastreador localizado via compound `POST /Veiculos/Cadastro` pelo serial. Chip vinculado depois via `POST /Rastreadores/Atualizar`.

---

## Placa

**Função:** Criar veículo e vincular cliente + rastreador via `POST /Veiculos/Cadastro`

**Erro:** `GET /Veiculos/Consultar` retorna HTTP 500 com qualquer parâmetro — não é possível verificar se a placa já existe antes de criar. A deduplicação depende de tratar o 409 na tentativa de cadastro.

**Retorno — consulta (quebrada):**
```
HTTP 500 — text/html
500 - Internal server error.
```

**Retorno — cadastro (sucesso):**
```json
{ "Status": "success", "Data": { "id": 86395, "placa": "XXX9C99", "cliente_id": 13458, "rastreador_id": 14008, "simcard_id": null } }
```

---

## Veículo — Exclusão por Placa

**Função:** Excluir veículo usando a placa como identificador, conforme documentado em `POST /Veiculos/Excluir`.

**Erro:** A documentação afirma que `{"placa": "ABC1234"}` é aceito. Na prática, retorna HTTP 400 com body vazio — sem mensagem de erro. Mesmo comportamento para `POST /Veiculos/Atualizar` com placa como identificador.

**Impacto:** Sem `GET /Veiculos/Consultar` (quebrado) e sem exclusão por placa, é impossível obter ou usar o `veiculo_id` numérico via API. O painel WeFleet não exibe o ID numérico. **Exclusão de veículos via API exige que o `veiculo_id` seja capturado no momento do cadastro** (`POST /Veiculos/Cadastro` retorna o ID na resposta).

**Retorno — exclusão por placa (falha):**
```
HTTP 400 — body vazio
```

**Solução no FPSL:** capturar e persistir o `veiculo_id` retornado no `POST /weso/veiculos` para uso futuro em `DELETE /weso/veiculos/{id}`.

---