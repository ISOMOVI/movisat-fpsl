# 11 — Segurança do FPSL

## Auditoria executada em 2026-06-15

### Vetores inspecionados

| Vetor | Resultado | Evidência |
|---|---|---|
| SQL injection | OK | Todas as 9 queries SQLite usam `?` parameterizado; sem concatenação |
| Command injection | OK | Nenhum `subprocess`, `os.system`, `shell=True`, `eval`, `exec` |
| Path traversal | OK | `DB_PATH` e `LOG_PATH` derivados de `__file__` em deploy time, nunca de input do usuário |
| Header injection | OK | FastAPI/Pydantic valida tipos antes de qualquer uso |
| Vazamento em logs | OK | `logger.py` nunca grava chaves, tokens ou CNPJs |
| WESO key em Nginx | OK | Chave WESO só existe em chamadas Python→WESO (invisível ao Nginx) |
| X-FPSL-Key em log | OK | Formato de log Nginx não inclui headers customizados |
| Tunelização | OK | Destinos fixos no `.env`; sem redirect controlado pelo caller |
| Tamanho de payload | OK | `client_max_body_size 1m` no Nginx |
| Isolamento de processo | OK | FPSL = usuário `claude`; Nginx = `www-data`; nenhum roda como root |

### Permissões de arquivo verificadas

| Arquivo | Permissão |
|---|---|
| `.env` | 600 OK |
| `data/fpsl.db` | 600 OK |
| `logs/requests.log` | 600 OK |

### Auth em todas as rotas

`X-FPSL-Key` via `Depends(verificar_chave)` aplicado no nível do router em todos os 6 routers:
`clientes`, `simcards`, `rastreadores`, `veiculos`, `os`, `onboarding/services`.

Guard adicional: `not settings.fpsl_secret_key` bloqueia startup com chave vazia.
Docs/Swagger desabilitados: `docs_url=None, redoc_url=None`.

---

## Pendências antes de produção

### P1 — TLS/HTTPS (CRÍTICO)

**Problema:** sem HTTPS, o header `X-FPSL-Key` e os bodies com CNPJ/placa/serial trafegam
em plaintext entre os servidores da Harmonit e a VPS. Viola LGPD Art. 46.

**Solução** (como root, após DNS apontado para o IP da VPS):
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d seu.dominio.com
```

O certbot reconfigura o Nginx automaticamente e agenda renovação via cron.

**Impacto se ignorado:** Harmonit pode rejeitar URLs HTTP por política de webhook.
A chave capturada em plaintext permite impersonação total das chamadas.

### P2 — Rate Limiting

**Problema:** com a chave em mãos, abuso pode floodar a WESO API sem limitação.

**Solução:** adicionar em `/etc/nginx/conf.d/fpsl_log_format.conf`:
```nginx
limit_req_zone $binary_remote_addr zone=fpsl:10m rate=30r/m;
```

E dentro do bloco `server {}` em `/etc/nginx/sites-available/fpsl`:
```nginx
limit_req zone=fpsl burst=10 nodelay;
```

### P3 — Rotação de Logs

**Problema:** `logs/requests.log` cresce indefinidamente; dados de produção acumulando em disco.

**Solução** — criar `/etc/logrotate.d/fpsl` (como root):
```
/home/claude/fpsl_weso/logs/requests.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    create 600 claude claude
}
```

---

## Segredo na query string do log de acesso (2026-08-19)

**O que acontecia.** O `code` do OAuth do Google ia inteiro para o journal do
serviço. Medido em 18/08: **37 entradas**; em 19/08 ainda havia 31 no journal
vivo — o resto saiu na rotação. A linha era assim:

```
GET /painel/api/auth/google/callback?code=4/0AVMBsJi... HTTP/1.1" 302
```

É a mesma classe do incidente de 12/08 no MoviZap, onde o segredo do webhook do
Evolution foi ao disco **2.527 vezes em 24 h**. A diferença é onde o segredo
mora: lá no **caminho**, aqui na **query string**.

⚠️ **O risco aqui é menor, e vale dizer por quê.** O `code` é de **uso único** e
expira em ~10 minutos, então journal antigo não autentica ninguém. O que
justifica o filtro não é o dano provável — é o hábito. Segredo em log só se
conserta antes de acontecer.

**A correção.** `MascararSegredoDaQueryString`, em `main.py`, registrada em
`uvicorn.access` e `gunicorn.access`. Mascara o **valor** de `code`, `state`,
`id_token`, `access_token` e `refresh_token`, e deixa o resto da linha intacta.

🚨 **POR QUE UM FILTRO DE LOG E NÃO UM MIDDLEWARE.** Quem escreve essa linha é o
`uvicorn.access`, que **não passa pelo middleware da aplicação**. Em 12/08
tentou-se resolver no middleware e o segredo continuou saindo.

🚨 **O FILTRO REESCREVE `record.args`, NÃO A MENSAGEM FORMATADA.** O
`uvicorn.access` guarda os campos separados (`%s - "%s %s HTTP/%s" %d`) e só os
junta na hora de escrever. Mexer na mensagem final não pega nada — e um teste
que olhasse a mensagem final passaria com o filtro errado. Por isso
`tests/teste_segredo_no_log.py` monta um `LogRecord` no formato real do uvicorn
e confere `record.args`.

🚨 **A VERIFICAÇÃO QUE MAIS IMPORTA É A DO `addFilter`.** O erro mais provável é
escrever a classe certinha e esquecer de registrá-la: aí todo teste de
mascaramento passa e o segredo continua indo para o disco. O teste confere que
o filtro está **na lista de filtros** dos dois loggers.

⚠️ **O FILTRO NÃO ALCANÇA O `access.log` DO NGINX**, que registra a mesma linha
e exige root para calar. Hoje isso não é um buraco no FPSL: a entrada pelo
Google chega pelo nginx do MoviZap, que já tem `log_format` **mascarado** desde
12/08. Se algum dia o FPSL ganhar um callback pelo nginx dele, o `log_format`
tem de ser mascarado lá também.

⚠️ **Isto não desfaz a exposição** das 31 entradas que já estão no journal. Elas
saem sozinhas na rotação, e como o `code` já expirou, não há rotação de segredo
a fazer.
