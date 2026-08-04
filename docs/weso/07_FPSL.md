# FPSL — FastAPI Proxy Service Local (WESO)

Serviço local que centraliza a chave de API da WESO e expõe endpoints limpos para consumo interno e testes.

---

## Estrutura de arquivos

```
C:\code\Bibliotecas API\WESO\proxy\
├── .env                  ← credenciais (não versionar)
├── main.py               ← app FastAPI + cliente httpx
├── requirements.txt
└── routers\
    ├── veiculos.py
    ├── clientes.py
    ├── rastreadores.py
    ├── simcards.py
    ├── motoristas.py
    └── comandos.py
```

---

## `.env`

```env
WESO_API_KEY=SUA_CHAVE_AQUI
WESO_BASE_URL=http://apirota.wesotecnologia.com.br
```

> **Atenção:** confirmar se os endpoints de gestão (`/Veiculos/`, `/Clientes/`, etc.) usam a mesma base URL dos endpoints de posição (`/Posicao/`). Se forem diferentes, adicionar `WESO_GESTAO_URL=https://...` separado.

---

## `requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
httpx==0.27.2
python-dotenv==1.0.1
pydantic-settings==2.5.2
```

> Todas as dependências já existem no projeto movichat.

---

## `main.py`

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
import httpx

from routers import veiculos, clientes, rastreadores, simcards, motoristas, comandos
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(
        base_url=settings.WESO_BASE_URL,
        timeout=30.0,
    )
    yield
    await app.state.client.aclose()


app = FastAPI(
    title="WESO Proxy API",
    description="Proxy local para a API de gestão WESO. A chave é injetada automaticamente.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(veiculos.router,     prefix="/veiculos",     tags=["Veículos"])
app.include_router(clientes.router,     prefix="/clientes",     tags=["Clientes"])
app.include_router(rastreadores.router, prefix="/rastreadores", tags=["Rastreadores"])
app.include_router(simcards.router,     prefix="/simcards",     tags=["SIM Cards"])
app.include_router(motoristas.router,   prefix="/motoristas",   tags=["Motoristas"])
app.include_router(comandos.router,     prefix="/comandos",     tags=["Comandos"])


@app.get("/health", tags=["Sistema"])
async def health():
    return {"status": "ok", "weso_base": settings.WESO_BASE_URL}
```

---

## `config.py`

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    WESO_API_KEY: str
    WESO_BASE_URL: str = "http://apirota.wesotecnologia.com.br"

    class Config:
        env_file = ".env"


settings = Settings()
```

---

## `routers/veiculos.py` (padrão replicado nos demais)

```python
from fastapi import APIRouter, Request, Query
from typing import Optional

router = APIRouter()


def _key(request: Request) -> str:
    return request.app.extra.get("settings").WESO_API_KEY  # injetado via app.state


async def _client(request: Request):
    return request.app.state.client


# ── Consultar ────────────────────────────────────────────────
@router.get("/consultar")
async def consultar(
    request: Request,
    placa: Optional[str] = Query(None, description="Filtrar por placa"),
    veiculo_id: Optional[int] = Query(None, description="Filtrar por ID"),
):
    client = await _client(request)
    params = {"key": request.app.state.settings.WESO_API_KEY}
    if placa:
        params["placa"] = placa
    if veiculo_id:
        params["veiculo_id"] = veiculo_id

    resp = await client.get("/Veiculos/Consultar", params=params)
    return resp.json()


# ── Cadastrar ────────────────────────────────────────────────
@router.post("/cadastrar", status_code=201)
async def cadastrar(request: Request, body: dict):
    client = await _client(request)
    resp = await client.post(
        "/Veiculos/Cadastro",
        params={"key": request.app.state.settings.WESO_API_KEY},
        json=body,
    )
    return resp.json()


# ── Atualizar ────────────────────────────────────────────────
@router.post("/atualizar")
async def atualizar(request: Request, body: dict):
    client = await _client(request)
    resp = await client.post(
        "/Veiculos/Atualizar",
        params={"key": request.app.state.settings.WESO_API_KEY},
        json=body,
    )
    return resp.json()


# ── Excluir ──────────────────────────────────────────────────
@router.post("/excluir")
async def excluir(request: Request, body: dict):
    client = await _client(request)
    resp = await client.post(
        "/Veiculos/Excluir",
        params={"key": request.app.state.settings.WESO_API_KEY},
        json=body,
    )
    return resp.json()
```

> O mesmo padrão (`consultar`, `cadastrar`, `atualizar`, `excluir`) se repete em `clientes.py`, `rastreadores.py`, `simcards.py` e `motoristas.py` — apenas trocando o prefixo de rota WESO.

---

## `routers/comandos.py`

```python
from fastapi import APIRouter, Request, Query
from typing import Literal

router = APIRouter()

COMANDOS_DISPONIVEIS = Literal["BLOQUEAR", "DESBLOQUEAR"]


@router.get("/enviar")
async def enviar_comando(
    request: Request,
    placa: str = Query(..., description="Placa do veículo"),
    comando: COMANDOS_DISPONIVEIS = Query(..., description="BLOQUEAR ou DESBLOQUEAR"),
):
    client = request.app.state.client
    resp = await client.get(
        "/Comandos/EnviarComando",
        params={
            "key": request.app.state.settings.WESO_API_KEY,
            "placa": placa,
            "comando": comando,
        },
    )
    return resp.json()


@router.get("/enviados")
async def comandos_enviados(
    request: Request,
    placa: str = Query(..., description="Placa do veículo"),
):
    client = request.app.state.client
    resp = await client.get(
        "/Comandos/ComandosEnviados",
        params={
            "key": request.app.state.settings.WESO_API_KEY,
            "placa": placa,
        },
    )
    return resp.json()
```

---

## Como rodar

```bash
cd "C:\code\Bibliotecas API\WESO\proxy"

# instalar dependências (se necessário)
pip install -r requirements.txt

# subir o servidor
uvicorn main:app --reload --port 8001
```

Acesse:
- **Swagger UI:** http://localhost:8001/docs
- **Redoc:** http://localhost:8001/redoc
- **Health check:** http://localhost:8001/health

---

## Mapeamento de rotas locais → WESO

| Local (proxy)                      | WESO (real)                                        |
|------------------------------------|----------------------------------------------------|
| GET  `/veiculos/consultar`         | GET  `/Veiculos/Consultar?key=KEY`                 |
| POST `/veiculos/cadastrar`         | POST `/Veiculos/Cadastro?key=KEY`                  |
| POST `/veiculos/atualizar`         | POST `/Veiculos/Atualizar?key=KEY`                 |
| POST `/veiculos/excluir`           | POST `/Veiculos/Excluir?key=KEY`                   |
| GET  `/clientes/consultar`         | GET  `/Clientes/Consultar?key=KEY`                 |
| POST `/clientes/cadastrar`         | POST `/Clientes/Cadastro?key=KEY`                  |
| POST `/clientes/atualizar`         | POST `/Clientes/Atualizar?key=KEY`                 |
| POST `/clientes/excluir`           | POST `/Clientes/Excluir?key=KEY`                   |
| GET  `/rastreadores/consultar`     | GET  `/Rastreadores/Consultar?key=KEY`             |
| POST `/rastreadores/cadastrar`     | POST `/Rastreadores/Cadastro?key=KEY`              |
| POST `/rastreadores/atualizar`     | POST `/Rastreadores/Atualizar?key=KEY`             |
| POST `/rastreadores/excluir`       | POST `/Rastreadores/Excluir?key=KEY`               |
| GET  `/simcards/consultar`         | GET  `/SimCard/Consultar?key=KEY`                  |
| POST `/simcards/cadastrar`         | POST `/SimCard/Cadastro?key=KEY`                   |
| POST `/simcards/atualizar`         | POST `/SimCard/Atualizar?key=KEY`                  |
| POST `/simcards/excluir`           | POST `/SimCard/Excluir?key=KEY`                    |
| GET  `/motoristas/consultar`       | GET  `/Motorista/Consultar?key=KEY`                |
| POST `/motoristas/cadastrar`       | POST `/Motorista/Cadastro?key=KEY`                 |
| POST `/motoristas/atualizar`       | POST `/Motorista/Atualizar?key=KEY`                |
| POST `/motoristas/excluir`         | POST `/Motorista/Excluir?key=KEY`                  |
| GET  `/comandos/enviar`            | GET  `/Comandos/EnviarComando?key=KEY&...`         |
| GET  `/comandos/enviados`          | GET  `/Comandos/ComandosEnviados?key=KEY&...`      |

---

## Próximos passos (quando unir com Harmonit)

- Adicionar routers do Harmonit sob `/harmonit/...` com `HARMONIT_TOKEN` no `.env`
- Criar middleware de autenticação próprio (ex: `X-Internal-Key`) para proteger o proxy
- Adicionar logging centralizado de todas as chamadas para as duas APIs
