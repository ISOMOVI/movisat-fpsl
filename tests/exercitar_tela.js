/* Roda a tela de Gerar OS de verdade, sem navegador.
 *
 * 🚨 POR QUE ISTO EXISTE. Em 14/08 a extração de termo parou de funcionar para
 * TODOS os perfis de contrato e nada acusou: nem log, nem `node --check`, nem o
 * detector de chamada órfã. O erro era de TIPO de argumento (`progresso()`
 * recebendo string depois de passar a esperar lista), e só aparecia clicando.
 *
 * Aqui o script da página é carregado inteiro num DOM de mentira, com `fetch`
 * respondendo o JSON REAL da extração. Se `extrair()` estourar em qualquer
 * ponto, este arquivo reprova -- que é o que faltava.
 *
 * Uso: node exercitar_tela.js <gerar_os.html> <resposta_extracao.json> [perfil]
 *
 * Sai com JSON no stdout. `erros` vazio = a tela aguentou o fluxo inteiro.
 */
const fs = require("fs");

const html = fs.readFileSync(process.argv[2], "utf8");
const RESPOSTA = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

// ── DOM de mentira: só o que a página toca ──────────────────────────────────
//
// 🚨 O QUE NÃO EXISTE TEM DE DEVOLVER `null`. A primeira versão deste
// simulador criava elemento para qualquer id pedido, e com isso NÃO reproduziu
// o defeito real: `progresso()` só entra no caminho quebrado quando
// `getElementById('progressoCaixa')` devolve null (a caixa ainda não existe) e
// o código parte para criá-la. Mock complacente demais aprova código quebrado.
const IDS_DA_PAGINA = new Set(
  [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1])
);
const elementos = {};
function elemento(id) {
  if (!IDS_DA_PAGINA.has(id) && !(id in elementos)) return null;
  if (!elementos[id]) {
    elementos[id] = {
      id, value: "", innerHTML: "", textContent: "", disabled: false,
      files: [], style: {}, classList: { toggle() {}, add() {}, remove() {} },
      appendChild() {}, prepend() {}, remove() {}, addEventListener() {},
      focus() {},
    };
  }
  return elementos[id];
}

const panelAtivo = { prepend() {}, classList: { toggle() {} } };
global.window = { location: { href: "" } };
global.localStorage = { getItem: () => "token-de-mentira" };
global.montarSidebar = () => {};
global.alert = (m) => { global.__alertas.push(m); };
global.confirm = () => true;
global.__alertas = [];
let _criados = 0;
global.document = {
  getElementById: elemento,
  createElement: () => {
    const id = "__criado_" + (++_criados);
    elementos[id] = null;            // libera o guard do `elemento()`
    delete elementos[id];
    IDS_DA_PAGINA.add(id);
    return elemento(id);
  },
  querySelector: (s) => (s === ".panel.active" ? panelAtivo : elemento(s)),
  querySelectorAll: () => [],
};

// ── fetch de mentira: devolve o que o backend devolveria ────────────────────
const chamadas = [];
global.fetch = async (url) => {
  chamadas.push(String(url));
  const u = String(url);
  const ok = (corpo) => ({ ok: true, status: 200, json: async () => corpo });
  if (u.includes("/painel/api/perfis")) {
    return ok({
      rescisao: { label: "Rescisão", os_por_placa: 1, agrupado: false,
                  sem_termo: false, sem_financeira: false },
      manutencao_troca: { label: "Manutenção com troca", os_por_placa: 1,
                          agrupado: false, sem_termo: true, sem_financeira: true,
                          problema_nome: "MANUTENÇÃO",
                          produto_servico_nome: "MANUTENÇÃO" },
    });
  }
  if (u.includes("/painel/api/prioridades")) {
    return ok({ prioridades: [{ id: 382, descricao: "Normal" }], default: 382 });
  }
  if (u.includes("/painel/api/problemas")) {
    return ok({ problemas: [{ id: 7384, descricao: "MANUTENÇÃO" }] });
  }
  if (u.includes("/painel/api/extrair")) return ok(RESPOSTA);
  if (u.includes("/servicos/buscar")) {
    return ok({ resultados: [{ id: 6966, descricao: "MANUTENÇÃO" }] });
  }
  if (u.includes("/clientes/buscar")) {
    return ok({ resultados: [{ id: 998063, nome: "PASTELARIA VELASCO LTDA" }] });
  }
  if (u.includes("/painel/api/gerar-os")) {
    // resposta de dry-run como o backend devolve para manutenção
    return ok({
      simulado: true, total_os: 1, avisos: [],
      solucao_tecnica_preview: "[14/08 10:00] Contexto\n-------------\n",
      operacoes: [{
        cliente_id: 998063, placa: "GJN 8689", veiculo: "TESTE",
        rotulo: "Manutenção com troca",
        descricao: "MANUTENÇÃO COM TROCA: GJN 8689 | TESTE | SAIRÁ: 007733214",
        materiais: [{ descricao: "SERVIÇO DO CABEÇALHO (sem flag)" },
                    { descricao: "ST310U" }, { descricao: "ENTREGA OS" }],
      }],
    });
  }
  if (u.includes("/buscar")) return ok({ resultados: [] });
  return ok({});
};

// ── carrega o script da página ──────────────────────────────────────────────
const src = html.split("<script>").slice(1)
  .map((p) => p.split("</script>")[0]).join("\n");
eval(src);

// ── exercita ────────────────────────────────────────────────────────────────
(async () => {
  const resultado = { erros: [] };
  try {
    // deixa o init() (assíncrono) terminar antes de mexer na tela
    await new Promise((r) => setTimeout(r, 50));

    const perfil = process.argv[4] || "rescisao";
    elemento("perfil").value = perfil;
    // Perfil sem termo não tem anexo: o fluxo pula a extração e vai à Etapa 2.
    if (perfil.startsWith("manutencao")) {
      aplicarPerfil();
    } else {
      elemento("arquivo").files = [{ name: "termo.pdf" }];
    }

    await extrair();

    resultado.termo_na_tela = elemento("termo").value;
    resultado.placas = (typeof placasEditaveis !== "undefined")
      ? placasEditaveis.length : -1;
    resultado.mensagem = elemento("extraidoMsg").innerHTML.slice(0, 120);
    resultado.itens_html = elemento("itensRevisao").innerHTML.length > 0;
    resultado.botao = elemento("btnExtrair").textContent;
    resultado.botao_liberado = elemento("btnExtrair").disabled === false;
    resultado.chamou_extrair = chamadas.some((u) => u.includes("/extrair"));
    resultado.alertas = global.__alertas;

    // ── Etapa 2 -> 3: o resumo. É onde a manutenção da Erika parou. ─────────
    // 🚨 Só chegar na Etapa 2 não prova nada: o fluxo continua, e cada passo
    // seguinte pode ter o mesmo tipo de defeito.
    selecionarCliente({ id: 998063, nome: "PASTELARIA VELASCO LTDA" }, "origem");
    selecionarServico({ id: 6966, descricao: "MANUTENÇÃO" });
    if (elemento("placaManual")) elemento("placaManual").value = "GJN 8689";
    if (elemento("veiculoManual")) elemento("veiculoManual").value = "TESTE";

    await montarResumo();
    resultado.resumo_montado =
      (elemento("resumoTbody").innerHTML || "").includes("GJN 8689");
    resultado.resumo_info = (elemento("resumoInfo").innerHTML || "").slice(0, 90);
    resultado.botao_gerar_liberado = elemento("btnGerar").disabled === false;
    resultado.chamou_dry_run = chamadas.some((u) => u.includes("/gerar-os"));
  } catch (e) {
    resultado.erros.push(e.message);
    resultado.onde = e.stack ? e.stack.split("\n")[1] : "";
  }
  console.log(JSON.stringify(resultado, null, 2));
})();
