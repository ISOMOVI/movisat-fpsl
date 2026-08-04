# Report de Bugs — WESO API

**Empresa:** Movisat
**Data:** 13/07/2026
**Ambiente:** API produção (`apirota.wesotecnologia.com.br` / API de gestão de frotas WESO)

---

## Bug 1 — `GET /Comandos/ComandosEnviados` quebra com exceção não tratada

**Severidade:** Média — endpoint fica inutilizável nesse cenário, sem mensagem de erro útil

### Como reproduzir

```
GET /Comandos/ComandosEnviados?key=<KEY>&placa=IAG0T01
```
onde `IAG0T01` é uma placa que existe/existiu no sistema mas **não tem rastreador ativo vinculado no momento**.

### Resposta obtida

```
HTTP 502 / erro de servidor
"Object reference not set to an instance of an object."
```

Isso é uma `NullReferenceException` do .NET vazando direto da API — não é uma mensagem de erro tratada (tipo "placa sem comandos" ou "rastreador não encontrado"), é uma falha interna não capturada.

### Impacto

Qualquer integração que consulte histórico de comandos por placa quebra sem aviso claro quando a placa não tem rastreador vinculado no momento da consulta — cenário comum (veículo desinstalado, rastreador em manutenção, etc.).

### Pedido

Tratar o caso de "placa sem rastreador vinculado" com uma resposta estruturada (ex: lista vazia ou mensagem clara), em vez de deixar a exceção subir crua.

---

## Bug 2 — `GET /Motorista/Consultar` sem filtro quebra por tamanho de resposta

**Severidade:** Baixa/Média — só afeta quem tenta listar todos os motoristas sem filtro (uso incomum, mas sem alternativa de paginação real)

### Como reproduzir

```
GET /Motorista/Consultar?key=<KEY>
```
(sem nenhum parâmetro de filtro)

### Resposta obtida

Erro determinístico do lado do servidor IIS/ASP.NET:
```
"the length of the string exceeds the value set on the maxJsonLength property"
```

### Detalhes já confirmados

- Parâmetros de paginação testados (`skip`, `take`, `page`) são **ignorados** pelo endpoint — não existe paginação real disponível.
- Não existe filtro por `numero` da tag identificadora (`iButton`/`Cartão`) do motorista — só é possível filtrar por `id` ou `cpf` individualmente, o que não resolve o caso de uso de listagem.
- Esse mesmo comportamento já foi confirmado de forma independente em outro sistema nosso (MoviChat, que também consome essa API) — não é specific a um único cliente/chave, é uma limitação do endpoint em si quando a base de motoristas é grande o suficiente pra estourar o limite de serialização do IIS.

### Pedido

Aumentar o `maxJsonLength` do lado do servidor **ou** implementar paginação real (`skip`/`take` funcionais) nesse endpoint, para permitir listar motoristas em bases grandes sem estourar o limite de resposta.

---

## Observação positiva (não é bug, é confirmação de melhoria)

`POST /Rastreadores/Atualizar` com payload mínimo (só `{"id": N}`, sem nenhum campo adicional) estava documentado desde 15/06/2026 como retornando **HTTP 500 garantido** nesse cenário. Testamos novamente hoje (13/07/2026) no mesmo rastreador de teste e o endpoint **funcionou normalmente** (200 OK, `data_atualizacao` atualizada). Parece que foi corrigido do lado de vocês — não é necessário nenhuma ação aqui, só registrando pra referência caso seja útil pro time de vocês rastrear quando a correção entrou.

---

## Contexto adicional (limitações já conhecidas, sem necessidade de ação agora)

Os endpoints `GET /Veiculos/Consultar`, `GET /SimCard/Consultar` e `GET /Rastreadores/Consultar` **sem nenhum filtro** continuam instáveis (timeout ou bloqueio por proteção anti-JSON-hijacking, dependendo do dia). As versões **filtradas** (por `placa`, `iccId`, `numeroSerie` respectivamente) funcionam bem e são o que já usamos em produção — não é um bloqueio ativo pra nós, só registrando o estado atual caso ajude a equipe de vocês a identificar o padrão (parece relacionado a listar a base inteira sem filtro).

---

## Reteste (16/07/2026) — confirmação para relatório definitivo

- **Bug 1 (`Comandos/ComandosEnviados`)**: CONFIRMADO, sem mudança. Mesmo erro exato (`Object reference not set to an instance of an object`, HTTP 502) na mesma placa de teste (IAG0T01).
- **Bug 2 (`Motorista/Consultar` sem filtro)**: CONFIRMADO, mas comportamento ficou **mais instável/imprevisível** do que documentado em 13/07. Testado 3 vezes: uma vez retornou rápido (7,7s) com página HTML de erro genérica (não mais o JSON com `maxJsonLength` explícito); duas vezes seguintes **nem chegou a responder, timeout total em 30s e depois 60s**. Ou seja, o endpoint não só quebra como agora nem sempre retorna dentro de um tempo razoável — piorou, não é mais só um erro determinístico rápido.
- **Observação positiva sobre `Rastreadores/Atualizar` payload mínimo**: RECONFIRMADO, continua funcionando (200 OK) no mesmo rastreador de teste (id 49175). A correção do lado da WESO se mantém.
- **Contexto (`Veiculos`/`SimCard`/`Rastreadores` `Consultar` sem filtro)**: `Veiculos/Consultar` e `SimCard/Consultar` funcionaram normalmente hoje (sem instabilidade). `Rastreadores/Consultar` sem filtro deu timeout (30s) — continua sendo o mais consistentemente instável dos três.
