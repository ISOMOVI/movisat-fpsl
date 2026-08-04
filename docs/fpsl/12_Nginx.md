# 12 — Nginx — Instalação e Configuração

## Papel do Nginx nesta arquitetura

```
Harmonit → [internet] → VPS:8005 (Nginx/www-data) → 127.0.0.1:8004 (uvicorn/claude)
```

- Nginx serve como proxy reverso na porta pública 8005 (futura: 443 HTTPS)
- FPSL escuta apenas em loopback `127.0.0.1:8004` — nunca exposto diretamente
- Nginx roda como `www-data` via systemd root
- FPSL roda como `claude` via systemd user — sem alteração

## Particularidades desta VPS

- `/etc/nginx/nginx.conf` usa `include sites-enabled/*.conf` — **com extensão .conf obrigatória**
- `conf.d/` **não** é incluído nesta VPS — log_format customizado não funciona via conf.d
- Log formats disponíveis: `main` e `cloudflare` (definidos diretamente no nginx.conf)
- O FPSL usa o formato `main` para access log

## Arquivo de configuração instalado

**Fonte:** `/home/claude/fpsl_weso/nginx_fpsl.conf`
**Instalado em:** `/etc/nginx/sites-available/fpsl`
**Symlink:** `/etc/nginx/sites-enabled/fpsl.conf` → `sites-available/fpsl`

```nginx
# FPSL WESO — server block
# Esta VPS usa include sites-enabled/*.conf (com extensão)
# log_format 'main' já definido no nginx.conf principal
server {
    listen 8005;
    server_name _;

    client_max_body_size 1m;
    access_log /var/log/nginx/fpsl_access.log main;
    error_log  /var/log/nginx/fpsl_error.log warn;

    location / {
        proxy_pass         http://127.0.0.1:8004;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_read_timeout 35s;
        proxy_connect_timeout 5s;
        proxy_send_timeout 35s;
    }
}
```

## Comandos de instalação (executar como root)

```bash
# 1. Instalar Nginx se ausente
apt install -y nginx

# 2. Instalar server block em sites-available
cp /home/claude/fpsl_weso/nginx_fpsl.conf /etc/nginx/sites-available/fpsl

# 3. Criar symlink com extensão .conf (obrigatório nesta VPS)
ln -sf /etc/nginx/sites-available/fpsl /etc/nginx/sites-enabled/fpsl.conf

# 4. Testar sintaxe e recarregar
nginx -t && systemctl reload nginx

# 5. Verificar — deve retornar HTTP 422
curl -s -o /dev/null -w HTTP %{http_code}n http://localhost:8005/weso/veiculos/local
```

## Notas históricas (bugs encontrados e corrigidos)

- Versão inicial: `log_format` dentro do `server {}` — inválido, só funciona em `http {}`
- Versão anterior: variáveis `$remote_addr` etc. expandidas pelo bash no heredoc — corrigido com single-quote
- Instalação 2026-06-15: symlink criado sem extensão (`fpsl`) — não carregado pois VPS usa `*.conf`
- Instalação 2026-06-15: log_format customizado via `conf.d/` falhou — `conf.d` não incluído nesta VPS

## Interpretação dos códigos de verificação

| Código | Significado |
|---|---|
| `HTTP 422` | Nginx OK + uvicorn OK — falta só o header de auth (`X-FPSL-Key`) |
| `HTTP 000` / `curl: (7)` | Nginx não iniciou ou não escuta na 8005 |
| `HTTP 502` | Nginx ok mas uvicorn fora — verificar `systemctl --user status fpsl-weso` |

## Verificação do serviço FPSL (como usuário claude)

```bash
systemctl --user status fpsl-weso
journalctl --user -u fpsl-weso -n 30
```

## Próximo passo: HTTPS

Após DNS do domínio apontando para o IP da VPS:
```bash
# Como root:
apt install -y certbot python3-certbot-nginx
certbot --nginx -d seu.dominio.com
```

O certbot:
1. Edita `sites-available/fpsl` automaticamente para porta 443
2. Redireciona 80 → 443
3. Cria cron job de renovação automática

Após HTTPS ativo, atualizar URL do webhook no painel Harmonit:
- De: `http://IP:8005/weso/os/adicionar`
- Para: `https://seu.dominio.com/weso/os/adicionar`
