# 17 — Perfis de acesso do painel (owner + abas)

**Implementado em 2026-07-27.** Substitui o controle anterior, que era só um
booleano `admin` + esconder link no navegador.

---

## Como era antes (e por que precisou mudar)

- Só existia `painel_usuarios.admin` (0/1). **Não havia "owner"**: qualquer conta
  criada com o check "Administrador" ficava idêntica à conta original — inclusive
  podendo criar outras contas e **desativar o `admin`**.
- **As abas operacionais eram abertas a qualquer usuário logado.** Só Usuários e
  Configurações checavam `admin`.
- A sidebar escondia links lendo `localStorage.fpsl_painel_admin` — ou seja, a
  permissão vivia no navegador. As páginas em `main.py` são `FileResponse` sem
  verificação, então digitar a URL abria a tela; ela só vinha vazia porque a *API*
  negava.

---

## Como é agora

### Owner
Coluna `painel_usuarios.owner`. A migração promove o usuário de menor `id` (a
conta que já existia). O owner:
- enxerga **todas** as abas, independente do que estiver gravado em `abas`;
- é o **único** que cria e edita contas (`get_owner_painel`);
- **não pode ser alterado por esta rota** — nem por ele mesmo. A rota rejeita com
  400 e o próprio `UPDATE` traz `AND owner = 0`, então não existe caminho que
  deixe o painel sem dono.

### Abas
`painel/abas.py` é a **fonte única**. Cada aba tem `id`, `nome`, `rota`, `icone`,
`descricao`, `sensivel` e `somente_owner`. Aba nova aparece sozinha no modal e na
sidebar — não se mexe no frontend.

| id | aba | concedível |
|---|---|---|
| `gerar_os` | Gerar OS | sim |
| `placas` | Placas | sim |
| `vinculos` | Vínculos | sim |
| `oficinas` | Oficinas | sim |
| `os_historico` | Histórico de OS | sim |
| `harmonit_historico` | Serviços Harmonit | sim |
| `config` | Configurações | **não** — `somente_owner` (decisão do usuário em 27/07: é onde vive o toggle que libera escrita na WESO, e isso não se delega) |
| `usuarios` | Usuários | **não** — `somente_owner` |

O perfil vai em `painel_usuarios.abas` (JSON de ids). Conta nova nasce **sem
nenhuma aba**: falhar fechado. Valor corrompido/ausente também vira lista vazia.

### Onde a permissão é aplicada de verdade
`auth.requer_aba(*ids)` — dependency em **todas as 20 rotas** do painel. Owner
passa em tudo; os demais precisam ter a aba. Aceita mais de uma porque três
lookups são compartilhados (`/perfis`, `/servicos/buscar`, `/produtos/buscar`
servem Gerar OS **e** Vínculos).

`GET /painel/api/me` devolve o perfil com as abas **já resolvidas**; o frontend só
desenha o que veio, não decide nada.

### Rotas de gestão de contas (todas exigem **owner**)

| Rota | Faz o quê |
|---|---|
| `GET /painel/api/usuarios/abas` | Catálogo das abas concedíveis — é o que alimenta o modal |
| `GET /painel/api/usuarios` | Lista as contas, com `abas` e `owner` de cada uma |
| `POST /painel/api/usuarios` | Cria conta (`login`, `senha`, `abas`) |
| `PATCH /painel/api/usuarios/{id}` | Altera `ativo`, `senha` ou `abas`. **400 se o alvo for o owner** |

`POST /painel/api/login` e `GET /painel/api/me` seguem abertos a qualquer conta ativa
(o `/me` é o que monta a sidebar — negá-lo deixaria o painel sem navegação).

---

## Frontend

- **`frontend/sidebar.js`** (novo) — `montarSidebar('aba')` monta a nav a partir
  de `/me`, marca a ativa e **redireciona** quem cair numa página fora do perfil
  (pra primeira aba que ele tem; se não tiver nenhuma, pro login). As 6 páginas
  perderam o `<nav>` escrito à mão e o controle por `localStorage`.
- **Login** manda pra primeira aba **do perfil** — antes ia sempre pra Gerar OS,
  o que jogaria num 403 quem não tem essa aba.
- **Modal de perfil** (`usuarios.html`): uma linha por aba com interruptor,
  descrição e selo "acesso sensível". Serve pra criar (`POST`) e pra editar o
  perfil de quem já existe (`PATCH`, botão "Perfil" na listagem). A listagem
  mostra as abas de cada conta como tags, e "Nenhuma aba" em vermelho.

### ⚠️ Limitação conhecida (aceita)
As páginas HTML continuam sendo **servidas** a qualquer requisição — o token vive
no `localStorage`, não em cookie, então o servidor não tem como autenticar o GET
da página. A proteção real é a API (403 em tudo) + o redirect do `sidebar.js`.
Quem digitar a URL de uma aba que não tem vê a tela piscar e ser redirecionado,
sem nunca receber dado. Fechar isso de verdade exige trocar o esquema de sessão
(cookie httpOnly) — candidato natural pra quando o Google OAuth entrar.

---

## Teste

`teste_perfis.py` (raiz do projeto) — 21 asserções, todas passando em 2026-07-27
(rodado de novo após `config` virar `somente_owner`).
Gera o token internamente (nunca passa senha por linha de comando), cria um
operador, confirma 200 na aba concedida e 403 nas outras, troca o perfil e
reconfirma, tenta desativar o owner (400) e remove o usuário de teste no fim.

```
venv/bin/python teste_perfis.py
```

---

## 🚨 24/08 — dois defeitos na tela de Usuários, achados por ele usando

### 1. O menu lateral sumia, e a causa era colisão de nome

Ele inseriu uma opção no perfil da Erika e **o menu lateral desapareceu**. Não
era o perfil, não era permissão, não era o backend.

A tela de Usuários declarava a **sua própria `desenharAbas`**, e o `sidebar.js`
declara uma com o **mesmo nome**. Os dois vivem no mesmo escopo global, e a
declaração da página — avaliada depois — apagava a do arquivo compartilhado.

A partir daí `montarSidebar('usuarios')` chamava a função **errada**: a da
página, que escreve na caixa de checkboxes do modal e não no `sidebarNav`, e que
ainda lê `ABAS` — um `let` declarado **abaixo** da chamada, portanto em zona
morta temporal. `ReferenceError`, promessa rejeitada, e o `/painel/api/me` nunca
chegava a ser pedido.

🚨 **COMO SE ACHOU, E VALE PARA A PRÓXIMA VEZ.** No journal a página sai `200`
e, **sozinha entre todas**, sem o `/painel/api/me` logo em seguida. Toda outra
tela do painel tem o par. **Foi a ausência que denunciou** — não havia erro
nenhum para procurar, nem no servidor nem no placar.

A colisão valia desde 19/08, quando o `sidebar.js` ganhou a `desenharAbas` do
cache (`52f47dd`); a da tela de Usuários existe desde 04/08. Cinco dias com a
sidebar de uma tela morta, com o placar verde o tempo todo: **nenhum teste
olhava a convivência entre os dois arquivos.**

**E a varredura achou mais quatro, de outra família.** `cadastro_placas`,
`cadastro_placas_historico`, `harmonit_historico` e `registro_telas` tinham um
`logout` próprio que apagava **só o token**, deixando `fpsl_painel_abas` no
navegador — o menu de quem saiu ficaria pintado para quem entrasse depois. As
quatro cópias saíram; vale a do `sidebar.js`, que apaga as duas chaves.

**Trava:** `tests/teste_colisao_de_globais.py` extrai **do próprio
`sidebar.js`** os nomes que vão para o escopo global e reprova qualquer página
que redeclare um deles no topo. A lista não é escrita no teste — escrevê-la
criaria a segunda verdade que ele existe para impedir. Conferido que **reprova
sem a correção**: 5 falhas, exatamente as cinco páginas.

### 2. O campo de e-mail existia e nunca era enviado

Ele viu na Aline: e-mail que não fica. O modal **preenchia** o campo ao abrir o
perfil, o operador digitava, e os **dois** caminhos mandavam o corpo sem ele —
`{login, senha, abas}` ao criar e `{abas}` ao editar.

O servidor sempre soube gravar (`definir_email_painel`); a tela é que jogava
fora. **Campo que aceita e descarta é pior que campo que não existe:** os quatro
usuários criados naquele dia ficaram sem vínculo, e **sem vínculo não há login
Google**.

⚠️ **E o conserto quase virou outro defeito.** Gravar e-mail **zera o
`google_sub`**, para a conta Google antiga não continuar entrando depois de o
vínculo passar de mão. Mandando o e-mail em toda edição, mexer numa permissão da
Erika **desligaria o login Google dela em silêncio**. Agora o e-mail só vai
quando o campo **muda** — o modal guarda o valor com que abriu.
