/* Desenha a barra de status de verdade, sem navegador.
 *
 * 🚨 POR QUE ISTO EXISTE. Em 17/08 as 677 verificações passaram com o painel
 * inteiro quebrado, porque nenhuma exercitava o que o navegador executa. O
 * `exercitar_tela.js` resolveu isso para a tela de Gerar OS; este faz o mesmo
 * para a barra, que agora roda em TODAS as 9 páginas -- se ela estourar, o
 * painel inteiro estoura junto.
 *
 * O script é carregado num DOM de mentira, recebe um perfil como o `sidebar.js`
 * entrega, e o HTML que ele produz é conferido.
 *
 * O QUE ISTO NÃO PEGA: CSS, altura, a barra cobrindo o rodapé de uma tela.
 * Continua exigindo olho humano -- é a mesma lacuna do exercitar_tela.js.
 *
 * Uso: node exercitar_barra.js <barra_status.js>
 * Sai com JSON no stdout; `erros` vazio = a barra aguentou.
 */
const fs = require("fs");
const vm = require("vm");

const fonte = fs.readFileSync(process.argv[2], "utf8");
const erros = [];

// ── DOM de mentira: só o que a barra toca ───────────────────────────────────
function criarElemento(tag) {
  return {
    tagName: tag, className: "", textContent: "", innerHTML: "",
    filhos: [], appendChild(f) { this.filhos.push(f); return f; },
  };
}

const head = criarElemento("head");
const body = criarElemento("body");
const document = {
  readyState: "complete",
  head, body,
  createElement: criarElemento,
  addEventListener() {},
};

// token com `iat` de 90 segundos atrás, no formato que o painel emite
const agora = Math.floor(Date.now() / 1000);
const payload = Buffer.from(JSON.stringify({ sub: "owner", iat: agora - 90, exp: agora + 3600 }))
  .toString("base64").replace(/=+$/, "");
const token = "cabecalho." + payload + ".assinatura";

const guardado = { fpsl_painel_token: token };
const localStorage = {
  getItem: (k) => (k in guardado ? guardado[k] : null),
  setItem: (k, v) => { guardado[k] = v; },
  removeItem: (k) => { delete guardado[k]; },
};

let respostaDoFetch = {
  headers: { get: (h) => (h === "X-Request-Id" ? "a3f9" : null) },
};
const janela = {
  document, localStorage,
  location: { pathname: "/painel/cadastro-placas/historico" },
  fetch: () => Promise.resolve(respostaDoFetch),
  setInterval: () => 0,
  atob: (s) => Buffer.from(s, "base64").toString("binary"),
  Date, JSON, Math, String, Number, Boolean, Object, Array, Promise, console,
};
janela.window = janela;

// ── executa a barra ─────────────────────────────────────────────────────────
try {
  vm.createContext(janela);
  vm.runInContext(fonte, janela, { filename: "barra_status.js" });
} catch (e) {
  erros.push("a barra estourou ao carregar: " + e.message);
}

function barraDesenhada() {
  const achado = body.filhos.filter((f) => f.className === "barra-status");
  return achado.length ? achado[0] : null;
}

if (!erros.length) {
  const barra = barraDesenhada();
  if (!barra) {
    erros.push("a barra nao foi inserida no body");
  } else {
    // 1. o perfil chega pelo sidebar.js, como em produção
    try {
      janela.barraStatusRecebePerfil({
        login: "owner", owner: true,
        codigos: {
          "/painel/cadastro-placas/historico": { codigo: "CAD_1.2", titulo: "Histórico de Placas" },
          "/painel/gerar-os": { codigo: "OSG_1.1", titulo: "Gerar OS" },
        },
      });
    } catch (e) {
      erros.push("barraStatusRecebePerfil estourou: " + e.message);
    }

    const html = barra.innerHTML;
    const exigir = (o_que, condicao) => { if (!condicao) erros.push("faltou: " + o_que); };
    exigir("o codigo da tela atual (CAD_1.2)", html.includes("CAD_1.2"));
    exigir("o titulo da tela", html.includes("Histórico de Placas"));
    exigir("NAO mostrar o codigo de outra tela", !html.includes("OSG_1.1"));
    exigir("o login", html.includes("owner"));
    exigir("a duracao da sessao (1min, do `iat`)", /1min/.test(html));
    exigir("o campo req", html.includes("req "));
    exigir("a data de hoje", html.includes(new Date().toLocaleDateString("pt-BR")));

    // 2. o interceptador de fetch alimenta o req id
    janela.fetch("/painel/api/me").then(() => {
      const depois = barra.innerHTML;
      if (!depois.includes("req a3f9")) {
        erros.push("o X-Request-Id da resposta nao chegou na barra");
      }
      // 3. rota desconhecida nao pode estourar nem inventar codigo
      janela.location.pathname = "/painel/rota-que-nao-existe";
      try {
        janela.barraStatusRecebePerfil({ login: "x", owner: false, codigos: {} });
      } catch (e) {
        erros.push("rota desconhecida estourou: " + e.message);
      }
      // 4. quem tenta injetar HTML pelo login sai escapado
      try {
        janela.barraStatusRecebePerfil({
          login: '<img src=x onerror=alert(1)>', owner: false, codigos: {},
        });
        if (barra.innerHTML.includes("<img src=x")) {
          erros.push("login com HTML entrou CRU na barra");
        }
      } catch (e) {
        erros.push("login com HTML estourou: " + e.message);
      }
      console.log(JSON.stringify({ erros }, null, 2));
      process.exit(erros.length ? 1 : 0);
    });
  }
}

if (erros.length) {
  console.log(JSON.stringify({ erros }, null, 2));
  process.exit(1);
}
