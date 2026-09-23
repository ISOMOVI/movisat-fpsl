/* Roda o script do Histórico de Operações num DOM de mentira. 2026-09-23.
 *
 * Existe para o C2 e o C3 da auditoria "mostrado × real": o Histórico dizia
 * "criado" para OS apagadas no Harmonit e para OS que saíram faltando
 * material. O que se mede é o que a tabela de passos DESENHA com a resposta
 * que o router dá -- e que a tela pede a conferência (`conferir=1`).
 *
 * Uso: EXERCITAR_LOTE=<json da rota /lote> node exercitar_historico.js <html>
 * Sai com JSON no stdout.
 */
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const respostaLote = JSON.parse(fs.readFileSync(process.env.EXERCITAR_LOTE, "utf8"));

/* 🚨 SÓ EXISTE O QUE O HTML DECLARA. Mock que inventa elemento para qualquer
   id aprova tela quebrada -- a lição do `exercitar_tela.js` de 14/08. */
const IDS = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]));
const els = {};
function el(chave) {
  if (!els[chave]) els[chave] = { innerHTML: "", textContent: "", style: {},
    disabled: false, scrollIntoView() {}, addEventListener() {} };
  return els[chave];
}
global.document = {
  getElementById(id) { return IDS.has(id) ? el(id) : null; },
  querySelector(sel) {
    const m = sel.match(/^#([\w-]+)\s+(thead|tbody)$/);
    return m && IDS.has(m[1]) ? el(sel) : null;
  },
  addEventListener() {},
};
global.window = { location: { href: "" }, addEventListener() {} };
/* O `sidebar.js` é carregado ANTES pela página e define `montarSidebar`. Aqui
   ele não roda -- o que se exercita é o script do Histórico, não o menu. */
global.montarSidebar = () => {};
global.localStorage = { getItem: () => "token-de-mentira", setItem() {}, removeItem() {} };
const chamadas = [];
global.fetch = async (url) => {
  chamadas.push(String(url));
  const corpo = String(url).includes("/operacoes/lote/") ? respostaLote
    : { lotes: [], pendentes: [], resumo_pendencias: {}, teto_tentativas: 28 };
  return { ok: true, status: 200, headers: { get: () => null },
           json: async () => corpo, text: async () => JSON.stringify(corpo) };
};

const src = html.split("<script>").slice(1).map((p) => p.split("</script>")[0]).join("\n");
(async () => {
  const r = { erros: [] };
  try {
    eval(src + "\nglobal.__abrirLote = abrirLote;");
    await new Promise((ok) => setTimeout(ok, 30));
    await global.__abrirLote("loteDeMentira");
    r.tbody = el("#tabelaPassos tbody").innerHTML;
    r.sub = el("detalheSub").innerHTML;
    r.chamadas = chamadas;
  } catch (e) {
    r.erros.push(String((e && e.stack) || e));
  }
  process.stdout.write(JSON.stringify(r));
})();
