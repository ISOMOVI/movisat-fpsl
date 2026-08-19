/* Roda o sidebar.js de verdade, sem navegador, com o /me lento de propósito.
 *
 * 🚨 POR QUE ISTO EXISTE. A sidebar nascia VAZIA e só era preenchida quando o
 * `/painel/api/me` respondia -- os links apareciam um instante depois da
 * página, em todas as 9 telas. Em 19/08 ela passou a pintar do cache local e
 * reconciliar. O que este script prova é justamente o que nenhum teste de
 * Python alcança: **o que está na tela ANTES de o /me responder**.
 *
 * O truque é o `/me` de mentira ficar pendente: o script inspeciona o `nav`
 * nesse intervalo, e só então solta a resposta.
 *
 * O QUE ISTO NÃO PEGA: CSS, largura, o menu cobrindo outra coisa. Mesma
 * lacuna do exercitar_tela.js e do exercitar_barra.js -- continua exigindo
 * olho humano.
 *
 * Uso: node exercitar_sidebar.js <sidebar.js>
 * Sai com JSON no stdout; `erros` vazio = passou.
 */
const fs = require("fs");
const vm = require("vm");

const fonte = fs.readFileSync(process.argv[2], "utf8");
const erros = [];
const anotar = (m) => erros.push(m);

const ABAS = [
  { id: "gerar_os", nome: "Gerar OS", rota: "/painel/gerar-os", icone: "bi-file" },
  { id: "config", nome: "Configurações", rota: "/painel/config", icone: "bi-gear" },
];

// ── localStorage de mentira ─────────────────────────────────────────────────
function criarStorage(inicial) {
  const dados = { ...inicial };
  return {
    dados,
    getItem: (k) => (k in dados ? dados[k] : null),
    setItem: (k, v) => { dados[k] = String(v); },
    removeItem: (k) => { delete dados[k]; },
  };
}

function criarNav() {
  return { innerHTML: "" };
}

/* Monta o ambiente e devolve o contexto. `soltarMe` é chamado à mão para
   liberar a resposta do /me -- é isso que permite olhar a tela no meio. */
function ambiente(storage, nav) {
  let soltar;
  const meRespondeu = new Promise((r) => { soltar = r; });
  const ctx = {
    localStorage: storage,
    document: { getElementById: (id) => (id === "sidebarNav" ? nav : null) },
    window: { location: { pathname: "/painel/gerar-os", href: "" } },
    console: { error: () => {} },
    fetch: async () => {
      await meRespondeu;
      return { status: 200, json: async () => ({ abas: ABAS, login: "x" }) };
    },
  };
  ctx.window.localStorage = storage;
  vm.createContext(ctx);
  vm.runInContext(fonte, ctx);
  return { ctx, soltar };
}

// ── 1. sem cache: a sidebar nasce vazia (o comportamento antigo) ────────────
{
  const nav = criarNav();
  const { ctx, soltar } = ambiente(criarStorage({ fpsl_painel_token: "t" }), nav);
  const p = ctx.montarSidebar("gerar_os");
  if (nav.innerHTML !== "") {
    anotar("sem cache, o nav devia estar vazio antes do /me");
  }
  soltar();
  p.then(() => {
    if (!nav.innerHTML.includes("Gerar OS")) {
      anotar("sem cache, o nav devia ter sido preenchido depois do /me");
    }
    etapa2();
  });
}

// ── 2. COM cache: a sidebar já nasce pintada ────────────────────────────────
function etapa2() {
  const nav = criarNav();
  const storage = criarStorage({
    fpsl_painel_token: "t",
    fpsl_painel_abas: JSON.stringify(ABAS),
  });
  const { ctx, soltar } = ambiente(storage, nav);
  const p = ctx.montarSidebar("gerar_os");

  // 🚨 A VERIFICAÇÃO QUE IMPORTA: aqui o /me ainda NÃO respondeu.
  if (!nav.innerHTML.includes("Gerar OS")) {
    anotar("com cache, o nav devia estar pintado ANTES do /me responder");
  }
  if (!nav.innerHTML.includes('class="active"')) {
    anotar("o item da rota atual devia estar ativo já na pintura do cache");
  }
  const antes = nav.innerHTML;

  soltar();
  p.then(() => {
    if (nav.innerHTML !== antes) {
      anotar("com o mesmo perfil, o /me nao devia mudar o desenho");
    }
    etapa3(storage);
  });
}

// ── 3. o /me manda: cache divergente é corrigido ────────────────────────────
function etapa3() {
  const nav = criarNav();
  const storage = criarStorage({
    fpsl_painel_token: "t",
    // menu antigo, com uma aba que o usuário perdeu
    fpsl_painel_abas: JSON.stringify([
      { id: "usuarios", nome: "Usuários", rota: "/painel/usuarios", icone: "bi-people" },
      ...ABAS,
    ]),
  });
  const { ctx, soltar } = ambiente(storage, nav);
  const p = ctx.montarSidebar("gerar_os");
  if (!nav.innerHTML.includes("Usuários")) {
    anotar("o cache antigo devia ter sido pintado");
  }
  soltar();
  p.then(() => {
    if (nav.innerHTML.includes("Usuários")) {
      anotar("o /me devia ter tirado a aba que o usuario perdeu");
    }
    const guardado = JSON.parse(storage.getItem("fpsl_painel_abas"));
    if (guardado.length !== 2) {
      anotar("o cache devia ter sido reescrito com o que o /me respondeu");
    }
    etapa4();
  });
}

// ── 4. cache corrompido ou de outro formato é IGNORADO ──────────────────────
function etapa4() {
  // 🚨 Cache de uma versão antiga do contrato desenharia `undefined` em cada
  // link -- que é exatamente a cara do defeito de 17/08. Tem de ser ignorado.
  const casos = {
    "json quebrado": "{{{",
    "lista vazia": "[]",
    "nao e lista": '{"abas":[]}',
    "faltando campo": '[{"id":"x","nome":"X"}]',
  };
  let pendentes = Object.keys(casos).length;
  for (const [rotulo, valor] of Object.entries(casos)) {
    const nav = criarNav();
    const { ctx, soltar } = ambiente(
      criarStorage({ fpsl_painel_token: "t", fpsl_painel_abas: valor }), nav);
    const p = ctx.montarSidebar("gerar_os");
    if (nav.innerHTML !== "") {
      anotar(`cache invalido (${rotulo}) foi pintado em vez de ignorado`);
    }
    soltar();
    p.then(() => {
      if (!nav.innerHTML.includes("Gerar OS")) {
        anotar(`cache invalido (${rotulo}): o /me devia ter salvado o desenho`);
      }
      if (--pendentes === 0) etapa5();
    });
  }
}

// ── 5. logout apaga o menu junto com o token ────────────────────────────────
function etapa5() {
  const storage = criarStorage({
    fpsl_painel_token: "t",
    fpsl_painel_admin: "1",
    fpsl_painel_abas: JSON.stringify(ABAS),
  });
  const { ctx } = ambiente(storage, criarNav());
  ctx.logout();
  if (storage.getItem("fpsl_painel_abas") !== null) {
    anotar("logout devia apagar o menu do cache");
  }
  if (storage.getItem("fpsl_painel_token") !== null) {
    anotar("logout devia apagar o token");
  }
  console.log(JSON.stringify({ erros }, null, 2));
  process.exit(erros.length ? 1 : 0);
}
