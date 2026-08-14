# 12 — Nginx do FPSL — configuração real

> ⚠️ **Reescrito em 2026-08-14.** A versão anterior descrevia a instalação de
> junho: um server block só, na porta 8005, com HTTPS listado como "próximo
> passo". Isso deixou de ser verdade há muito tempo, e o arquivo continuava
> sendo lido como se fosse o estado. **O que vale é o que está em
> `/etc/nginx/sites-available/fpsl.conf`.**

---

## Papel do Nginx nesta arquitetura

```
navegador / Harmonit → [internet] → VPS:443 (nginx/www-data) → 127.0.0.1:8004 (uvicorn/claude)
```

- O FPSL escuta **apenas em loopback** `127.0.0.1:8004` — nunca exposto direto.
- O nginx roda como `www-data` (systemd root); o FPSL roda como `claude`
  (**systemd de usuário**, unidade `fpsl-weso`).
- ⚠️ **Unidade de usuário não aparece em `systemctl list-units` sem `--user`**, e
  o nome tem **hífen** (`fpsl-weso`), enquanto o diretório tem sublinhado
  (`fpsl_weso`). "Serviço inativo" costuma ser nome errado — a conferência que
  não mente é a porta escutando e o processo.

## Particularidades desta VPS

- `/etc/nginx/nginx.conf` usa `include sites-enabled/*.conf` — **extensão .conf
  obrigatória**; symlink sem extensão não carrega.
- `conf.d/` **não** é incluído — `log_format` customizado por ali não funciona.
- Formatos disponíveis: `main` e `cloudflare`, definidos no `nginx.conf`.

## Arquivo instalado

**`/etc/nginx/sites-available/fpsl.conf`**, com **três** server blocks:

| Block | Para quê |
|---|---|
| `listen 80` | redireciona para HTTPS e serve `/.well-known/acme-challenge/` |
| `listen 443 ssl` — `fpsl.movisat.com.br` | o painel e a API |
| `listen 8005` — `server_name _` | acesso interno por IP, mesmo proxy_pass |

Backups no mesmo diretório (`fpsl.conf.bak_*`). 🚨 Eles são servíveis se alguém
errar o `location`: há regra `deny all` para `\.bak[0-9]*_[0-9-]+[a-z]?$` e para
`.py`, `.db`, `.env` e afins — **não remover**.

## Timeouts — e por que não são iguais

| Rota | `proxy_read/send_timeout` | Motivo |
|---|---|---|
| `location /` | **180s** (desde 14/08) | a geração de OS depende da WESO, que oscila de 7s a 33s na mesma consulta |
| `/weso/onboarding` | 120s | cadeia de cadastro, sempre foi longa |
| `/painel/api/login` | **35s** | de propósito — login não fala com a WESO; teto curto ali é proteção |

`proxy_connect_timeout` continua **5s** em todas: conectar no uvicorn local é
instantâneo ou não vai acontecer.

🚨 **O 35s do `location /` derrubou produção em 14/08.** A geração levava 43s, o
nginx cortava, devolvia **página HTML de 504**, e a tela lia aquilo como JSON — o
operador via "erro json" e nenhuma pista de que era tempo. A história inteira,
com as medições, está em **`24_Desempenho_e_Timeout.md`**.

⚠️ **Timeout maior não conserta lentidão**, só impede que ela vire erro mudo.

## Mexer no arquivo (precisa de root)

```bash
cp /etc/nginx/sites-available/fpsl.conf /etc/nginx/sites-available/fpsl.conf.bak_$(date +%F)
# editar
nginx -t && systemctl reload nginx
```

🚨 **`nginx -t` ANTES do reload, sempre.** Já quebrou config aqui por heredoc
com crase e `$`. Conteúdo com aspas, crase ou `$` vai por **arquivo + scp**,
nunca inline.

## Verificar

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://fpsl.movisat.com.br/painel
systemctl --user status fpsl-weso
journalctl --user -u fpsl-weso -n 30
```

| Código | Significado |
|---|---|
| `200` em `/painel` | nginx e uvicorn de pé |
| `502` | nginx de pé, uvicorn fora |
| `504` | uvicorn vivo mas passou do timeout — ver doc 24 |
| `000` / `curl: (7)` | nginx não escuta |

⚠️ **`/` na raiz responde 404, e isso é normal** — a aplicação começa em
`/painel`.

🚨 **Log de acesso do nginx não é legível sem root** (`www-data:adm`, 640):
`grep` devolve **zero para tudo**, o que parece "ninguém usou". Para medir uso,
o journal do próprio serviço — requisição vinda pelo nginx aparece com o **IP
real**, chamada local aparece como **127.0.0.1**.

## Notas históricas

- 15/06: symlink criado sem extensão (`fpsl`) — não carregou, a VPS usa `*.conf`.
- 15/06: `log_format` customizado via `conf.d/` falhou — `conf.d` não é incluído.
- 15/06: `log_format` dentro do `server {}` — inválido, só existe em `http {}`.
- Uma versão antiga teve `$remote_addr` expandido pelo bash dentro de heredoc.
- 14/08: timeouts do `location /` de 35s para 180s, nos dois blocos.
