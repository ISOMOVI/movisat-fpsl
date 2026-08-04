# Harmonit — Autenticação

> **Base URL:** `https://api-hc.harmonit.com.br:8086`

---

## Obter Token

**GET** `/Account/Token`

```
GET https://api-hc.harmonit.com.br:8086/Account/Token?clientId=SEU_ID&secretId=SEU_SECRET
```

### Parâmetros de Query

| Campo      | Tipo   | Obrigatório | Descrição            |
|------------|--------|-------------|----------------------|
| `clientId` | string | ❌*         | ID do cliente da API |
| `secretId` | string | ❌*         | Chave secreta        |

> *Marcados como não obrigatórios no spec, mas na prática são necessários.

### Resposta 200

```json
{
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "errorMessage": null,
  "message": null
}
```

### Resposta 400

```json
{
  "data": null,
  "errorMessage": "Credenciais inválidas",
  "message": "Não foi possível autenticar"
}
```

---

## Uso do Token

Incluir em **todas** as requisições autenticadas:

```
Authorization: Bearer SEU_TOKEN_AQUI
```

---

## Implementação recomendada

```python
import httpx
from datetime import datetime, timedelta

class HarmonitAuth:
    def __init__(self, client_id: str, secret_id: str, base_url: str):
        self.client_id = client_id
        self.secret_id = secret_id
        self.base_url = base_url
        self._token: str | None = None
        self._expires_at: datetime | None = None

    async def get_token(self) -> str:
        if self._token and self._expires_at and datetime.now() < self._expires_at:
            return self._token

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/Account/Token",
                params={"clientId": self.client_id, "secretId": self.secret_id},
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["data"]["token"]
            self._expires_at = datetime.now() + timedelta(hours=1)  # ajustar conforme TTL real
            return self._token

    async def headers(self) -> dict:
        token = await self.get_token()
        return {"Authorization": f"Bearer {token}"}
```

---

## `.env` para o proxy local

```env
HARMONIT_BASE_URL=https://api-hc.harmonit.com.br:8086
HARMONIT_CLIENT_ID=SEU_CLIENT_ID
HARMONIT_SECRET_ID=SEU_SECRET_ID
```
