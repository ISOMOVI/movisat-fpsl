# Harmonit — Usuários

> **Auth:** `Authorization: Bearer TOKEN`

---

## Endpoints

| Método | Rota                       | Ação                                 |
|--------|----------------------------|--------------------------------------|
| GET    | `/Usuario/ObterUsuarios`   | Listar todos os usuários             |
| GET    | `/Usuario/ObterUsuario`    | Buscar usuário por ID                |
| GET    | `/Usuario/ObterTecnicos`   | Listar usuários técnicos             |
| GET    | `/Usuario/ObterVendedores` | Listar usuários vendedores           |

---

## 1. Listar Usuários

**GET** `/Usuario/ObterUsuarios`

| Campo   | Tipo    | Descrição                  |
|---------|---------|----------------------------|
| `search`| string  | Filtro por nome ou e-mail  |
| `skip`  | integer | Offset                     |
| `take`  | integer | Limite                     |

---

## 2. Buscar por ID

**GET** `/Usuario/ObterUsuario?usuarioId=50`

**Resposta (UsuarioListaDTO):**
```json
{
  "data": {
    "id": 50,
    "codigo": 12,
    "nome": "Carlos Técnico",
    "email": "carlos@empresa.com",
    "phoneNumber": "(11) 99999-9999",
    "tecnico": true,
    "vendedor": false
  }
}
```

---

## 3. Listar Técnicos

**GET** `/Usuario/ObterTecnicos?search=Carlos`

Retorna apenas usuários com `tecnico: true`.

**Resposta (UsuarioDTO):**
```json
{
  "data": [
    {
      "id": 50,
      "codigo": 12,
      "nome": "Carlos Técnico",
      "email": "carlos@empresa.com",
      "tecnico": true,
      "vendedor": false
    }
  ]
}
```

> Usar este endpoint para popular o campo `tecnicoId` ao vincular técnicos em Ordens de Serviço.

---

## 4. Listar Vendedores

**GET** `/Usuario/ObterVendedores?search=Ana`

Retorna apenas usuários com `vendedor: true`.

> Usar para popular o campo `vendedorId` na criação de OS completa.

---

## Grupos de Usuário

**GET** `/GrupoUsuario/ObterGruposUsuarios`

Retorna todos os grupos de usuários cadastrados.

```json
[
  {
    "id": 1,
    "codigo": 100,
    "descricao": "Técnicos de Campo",
    "admin": false,
    "tecnico": true,
    "vendedor": false
  }
]
```
