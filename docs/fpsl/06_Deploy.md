# Aba 06 — Deploy na VPS

**Status:** ✅ Validado — 2026-06-15  
**Servidor:** VPS Ubuntu 22.04 — `ssh vps` — usuário `claude`  
**Diretório:** `/home/claude/fpsl_weso/`  
**Porta interna:** `8004` (nginx proxeia para fora)

---

## Ambiente confirmado (2026-06-15)

| Item | Valor |
|------|-------|
| OS | Ubuntu 22.04, kernel 6.8.0 |
| Python | 3.12.3 |
| pip | 24.0 |
| Disco disponível | 69 GB |
| RAM disponível | 5.9 GB |
| uvicorn instalado | Não — instalar via venv |
| Portas em uso | 8001, 8002 (uvicorn interno), 8003 (nginx) |
| Porta escolhida | **8004** (livre) |

---

## Estrutura na VPS

```
/home/claude/fpsl_weso/
├── main.py
├── requirements.txt
├── .env                          ← criado manualmente na VPS, nunca subido do local
├── data/                         ← criado automaticamente no primeiro start
│   └── fpsl.db                   ← SQLite — registro local de veículos
├── logs/                         ← criado automaticamente no primeiro start
│   └── requests.log              ← JSON Lines — log de requisições
├── docs/
│   ├── weso/                     ← documentação da API WESO
│   └── fpsl/                     ← documentação do FPSL (este projeto)
├── fpsl_weso/
│   ├── __init__.py
│   ├── config.py
│   ├── client.py
│   ├── storage.py
│   ├── logger.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── clientes.py
│   │   ├── simcards.py
│   │   ├── rastreadores.py
│   │   └── veiculos.py
│   └── services/
│       ├── __init__.py
│       └── onboarding.py
└── venv/
```

> `.env` **nunca sobe do local** — criado manualmente na VPS após o deploy.

---

## Sequência de Deploy

### 1. Criar estrutura na VPS

```bash
ssh vps "mkdir -p /home/claude/fpsl_weso/fpsl_weso/routers /home/claude/fpsl_weso/fpsl_weso/services /home/claude/fpsl_weso/docs/weso /home/claude/fpsl_weso/docs/fpsl"
```

### 2. Subir código via scp

```bash
scp main.py requirements.txt vps:/home/claude/fpsl_weso/
scp fpsl_weso/__init__.py fpsl_weso/config.py fpsl_weso/client.py fpsl_weso/storage.py fpsl_weso/logger.py vps:/home/claude/fpsl_weso/fpsl_weso/
scp fpsl_weso/routers/*.py vps:/home/claude/fpsl_weso/fpsl_weso/routers/
scp fpsl_weso/services/*.py vps:/home/claude/fpsl_weso/fpsl_weso/services/
```

### 3. Subir documentação via scp

```bash
# Documentação da API WESO
scp "Bibliotecas API/WESO/"*.md vps:/home/claude/fpsl_weso/docs/weso/

# Documentação do FPSL
scp "Bibliotecas API/WESO/FPSL/"*.md vps:/home/claude/fpsl_weso/docs/fpsl/
```

### 4. Criar venv e instalar dependências

```bash
ssh vps "cd /home/claude/fpsl_weso && python3 -m venv venv && venv/bin/pip install -r requirements.txt"
```

### 5. Criar `.env` na VPS

> 🚨 **A chave NUNCA passa pela linha de comando.** O `ssh vps "cat > .env
> << EOF"` que estava aqui colocava o valor no comando, no histórico do shell
> e — como se descobriu em 05/08 — dentro deste documento versionado.

Monte o arquivo **localmente**, envie por `scp` e destrua o original:

```bash
# conteudo do arquivo temporario  env_fpsl.txt
WESO_API_KEY=<cole a chave aqui>
WESO_BASE_URL=http://apirota.wesotecnologia.com.br
```

```powershell
scp env_fpsl.txt vps:/home/claude/fpsl_weso/.env
Remove-Item env_fpsl.txt
```

```bash
ssh vps "chmod 600 /home/claude/fpsl_weso/.env"
```

### 6. Testar inicialização

```bash
ssh vps "cd /home/claude/fpsl_weso && venv/bin/uvicorn main:app --host 127.0.0.1 --port 8004 --workers 1"
```

**Esperado:** `Application startup complete. Uvicorn running on http://127.0.0.1:8004`

### 7. Criar serviço systemd (nível de usuário)

> `claude` não tem `sudo` — usar systemd ao nível do usuário.

Arquivo: `~/.config/systemd/user/fpsl-weso.service`

```ini
[Unit]
Description=FPSL WESO
After=network.target

[Service]
WorkingDirectory=/home/claude/fpsl_weso
ExecStart=/home/claude/fpsl_weso/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8004 --workers 1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
# Criar e ativar
ssh vps "mkdir -p ~/.config/systemd/user"
ssh vps "cat > ~/.config/systemd/user/fpsl-weso.service << 'EOF'
[Unit]
Description=FPSL WESO
After=network.target

[Service]
WorkingDirectory=/home/claude/fpsl_weso
ExecStart=/home/claude/fpsl_weso/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8004 --workers 1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF"

ssh vps "systemctl --user daemon-reload && systemctl --user enable fpsl-weso && systemctl --user start fpsl-weso"

# Verificar
ssh vps "systemctl --user status fpsl-weso"
```

> Para sobreviver a logout: `ssh vps "loginctl enable-linger claude"`

### 8. Configurar nginx (acesso externo)

Bloco a adicionar no nginx:

```nginx
server {
    listen 8005;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

> Porta externa sugerida: **8005** (livre). Confirmar com admin do nginx antes de aplicar.

---

## Limpeza local antes do deploy

Remover antes de subir:

| Arquivo/Diretório | Motivo |
|-------------------|--------|
| `__pycache__/` (todos) | Bytecode compilado — desnecessário na VPS |
| `uvicorn_err.txt` | Log de sessão local |
| `uvicorn_out.txt` | Log de sessão local |
| `.env` | Nunca versionar — contém chave de API |

---

## Verificação pós-deploy

```bash
# health check interno
ssh vps "curl -s http://127.0.0.1:8004/docs | head -5"

# teste real — cliente existente
ssh vps "curl -s 'http://127.0.0.1:8004/weso/clientes?cnpjcpf=11222333000181' | python3 -m json.tool"
```

**Esperado:** `acao: "encontrado"`, id 13458.
