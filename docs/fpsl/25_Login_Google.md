# Entrada pelo Google no painel do FPSL

**Data:** 2026-08-17 · **Estado:** no ar e funcionando

Adaptado de `movizap/movizap/google_auth.py`, em produção desde 10/08. Aqui é
**mais simples de propósito**: o MoviZap também usa o Google para ler a caixa de
e-mail e a agenda, com refresh token e escopos de Gmail. O FPSL só quer login.

---

## É porta a mais, não troca

🚨 **O login por senha continua valendo para todo mundo.** Decisão do usuário em
17/08, para ninguém perder acesso no dia da mudança. Quem não tem `email`
preenchido simplesmente não usa esta porta.

Escopo: `openid email profile`. Nada de Gmail nem Calendar — nenhum
consentimento novo, nada guardado além do vínculo, e isto **não encosta na
delegação de domínio** que o MoviZap usa para outra coisa.

---

## As três travas

**1. Domínio.** Só `@movisat.com.br`. O `hd` da URL é *dica* ao Google, não
garantia — ele filtra a tela de escolha, mas quem manipular a URL passa por
cima. A trava real é a conferência em `entrar()`.

**2. A conta tem que existir.** Quem não tem linha em `painel_usuarios` é
**recusado, nunca criado**. Criar sozinho faria qualquer pessoa do domínio virar
usuário do painel sem ninguém decidir — e este painel cria OS e escreve na WESO.
Cadastrar é ato de gestão e mora na tela de Usuários, que já é `somente_owner`.

**3. `state` assinado.** JWT de 10 minutos com `tipo: fpsl_google_state`,
assinado com o `painel_jwt_secret`. Sem ele, um terceiro monta a URL de callback
e dispara a troca de código.

⚠️ **Confere o `tipo`, não só a assinatura.** Sem essa checagem, o **token de
sessão** — assinado com o mesmo segredo — serviria de `state`. Há teste
provando que não serve.

⚠️ O `id_token` vem da resposta do endpoint de token do Google, por TLS, com o
nosso client secret na requisição — não é algo que o navegador possa forjar. Por
isso o corpo é lido sem reverificar a assinatura, mas `aud` e o domínio **são**
conferidos: é o que impede um token emitido para outro aplicativo.

---

## As duas colunas, e por que não basta o e-mail

| Coluna | Papel |
|---|---|
| `email` | o **vínculo** — casa a conta Google na primeira vez |
| `google_sub` | a **identidade permanente** da conta no Google |

**E-mail muda, `sub` não.** A busca tenta o `sub` primeiro: quem trocou de
endereço no Google continua sendo reencontrado. Casar só por e-mail perderia o
vínculo em silêncio.

🚨 **Trocar o e-mail zera o `google_sub`** — é assim que a conta passa de mão.
Sem isso, a conta Google antiga continuaria entrando na conta mesmo depois de o
vínculo ter sido passado para outra pessoa. Mesma regra que o MoviZap fechou em
12/08.

As duas colunas são **anuláveis de propósito**: usuário que só entra por senha
não tem nem uma nem outra, e isso é estado válido.

---

## O token volta no fragmento

`/painel#t=...`, **não** na query.

Fragmento não é enviado ao servidor nem entra no `access_log` do nginx. Na
query, o token de sessão de todo mundo ficaria gravado em disco. A tela lê e
**limpa a barra de endereços** em seguida, para o token não ficar no histórico.

Erro volta do mesmo jeito: `/painel#erro=<motivo em português>`, e a tela mostra
em vermelho. O callback **nunca** devolve 500 — é rota pública, qualquer um
chega nela com o que quiser, e há teste provando que `state` inválido vira
redirecionamento e não erro de servidor.

---

## Credencial: o mesmo cliente OAuth do MoviZap

Decisão do usuário. `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e
`GOOGLE_DOMINIO` são os mesmos, copiados para o `.env` do FPSL (600, fora do
git). `GOOGLE_REDIRECT` é próprio:

```
https://fpsl.movisat.com.br/painel/api/auth/google/callback
```

🚨 **UM CLIENTE OAUTH ACEITA VÁRIAS URIs DE REDIRECIONAMENTO.** O comentário no
`movizap/main.py` que diz "o Google só aceita uma por cliente" **está errado** —
foi o que quase levou a criar um cliente separado à toa. As duas URIs convivem
no mesmo cliente:

```
URI 1  https://movizap.movisat.com.br/api/auth/google/callback
URI 2  https://fpsl.movisat.com.br/painel/api/auth/google/callback
```

Caminho no console: **APIs e serviços → Credenciais → IDs do cliente OAuth 2.0**
(ou **Plataforma de autenticação do Google → Clientes**, na interface nova).

⚠️ **Leva alguns minutos para propagar.** Enquanto não propaga, o Google
responde `Error 400: redirect_uri_mismatch` com a URI recebida no corpo — dá
para conferir da VPS, sem navegador, seguindo o redirecionamento de
`/painel/api/auth/google/inicio` e procurando `redirect_uri_mismatch` na
resposta.

⚠️ **A tela de consentimento mostra o nome do aplicativo do MoviZap** para quem
entra pelo FPSL. Consequência de compartilhar o cliente.

Sem credencial, `configurado()` devolve `False`, a tela **não mostra o botão** e
o painel segue inteiro por senha. Botão que não funciona é pior que botão
ausente: rende chamado.

---

## A tela

Espelha `movizap/frontend/src/telas/Login.vue`: botão **acima** do cartão, fora
dele, com a nota "Contas @movisat.com.br já cadastradas" e o separador "ou"
**depois** do botão. SVG do G oficial, `viewBox 0 0 18 18`, inline.

🚨 **A primeira versão foi desenhada sem abrir a referência** e saiu diferente em
quatro coisas: botão abaixo do formulário, "ou" antes, sem a nota, e um SVG
escrito à mão. O usuário viu na hora. **Tela nova se compara com a tela que já
existe** — não se desenha do zero e se declara igual.

⚠️ 48px de altura e 16px de fonte não são estética: abaixo disso o iOS dá zoom
sozinho ao focar. Régua do padrão visual de 05/08, a mesma dos campos.

⚠️ **São duas bases.** O MoviZap é Vue com tokens de design; o FPSL é HTML puro
com classes próprias. Os valores foram copiados, mas nada mantém os dois em
sincronia — se um mudar a paleta, o outro não acompanha.

---

## Cadastro do vínculo

Campo **E-mail de vínculo** no modal de Usuários, e coluna **Vínculo Google** na
listagem, que distingue "tem e-mail cadastrado" de "já entrou alguma vez"
(`google_ligado`).

Validação de domínio no **cadastro**, além da que existe na **entrada**. Não é
repetição boba: lá protege quem chega, aqui protege o que se grava. Sem esta,
alguém cadastraria `fulano@gmail.com`, o campo ficaria lá parecendo válido, e a
pessoa nunca conseguiria entrar — falha que só aparece no dia em que ela tenta.

🚨 **O owner não se altera pelo `PATCH /usuarios/{id}`**, de propósito. Para o
e-mail dele existe `PATCH /painel/api/usuarios/meu-email`, que faz uma coisa só.

⚠️ **Rota literal antes de rota com parâmetro:** `/meu-email` é declarada antes
de `/{usuario_id}`. Na ordem inversa, o FastAPI tentaria ler `"meu-email"` como
inteiro e devolveria 422.

### E-mails definidos em 17/08

`admin` → `iago@movisat.com.br` · `Erika` → `erika@movisat.com.br` ·
`Caio` → `caio@movisat.com.br`

⚠️ Se `caio@` não existir no Workspace, a porta do Google não abre para ele — a
senha continua.

---

## Defeito meu, corrigido em auditoria

**`buscar_usuario_painel_por_id` não devolvia o `email`.** A busca por login já
devolvia; esta não. Quem lesse por id concluiria que a conta não tem vínculo,
sem nada acusar. Pego pelo teste, não por mim.

---

## Teste

`tests/teste_google_login.py` — **27 verificações**, sem falar com o Google.

O handshake real não cabe em suíte (exige navegador e consentimento humano), e o
que se testa é tudo o que acontece **antes e depois** dele, que é onde moram as
decisões de segurança: degradação sem credencial, `state` forjado/vencido/de
outro tipo, a busca que nunca cria, o `sub` tendo prioridade sobre o e-mail, a
troca de e-mail zerando o `sub`, e o domínio no cadastro.

⚠️ A checagem "sem credencial dá 503" **só roda quando não há credencial** — com
o `.env` preenchido ela é pulada, e o total cai de 28 para 27. É esperado.
