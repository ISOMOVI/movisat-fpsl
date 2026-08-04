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
