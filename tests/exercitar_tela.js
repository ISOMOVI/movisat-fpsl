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
 * 17/08: os EVENTOS passaram a ser de verdade. `addEventListener` era uma
 * função vazia, então as 4 interações que a página liga por evento (trocar o
 * perfil, escolher o arquivo, buscar cliente, buscar serviço) nunca eram
 * exercitadas -- o exercício chamava as funções pelo nome e apagar a ligação
 * não reprovava nada. Agora o ouvinte é registrado e disparado.
 *
 * O QUE AINDA EXIGE NAVEGADOR: layout, CSS, elemento cobrindo outro, tela de
 * celular. Isso não dá para fazer aqui, e continua sendo a lacuna real.
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
      appendChild() {}, prepend() {}, remove() {},
      focus() {},
      // 🚨 `addEventListener() {}` VAZIO APROVA LIGAÇÃO QUEBRADA. Enquanto era
      // uma função vazia, este exercício chamava `aplicarPerfil()` pelo NOME e
      // a linha que LIGA o seletor à função (`sel.addEventListener('change',
      // aplicarPerfil)`) nunca era exercitada: apagá-la deixa a tela inerte ao
      // trocar de perfil, com os 448 testes verdes. Mesma família do defeito de
      // 14/08 -- a função está certa, o caminho até ela é que não existe.
      _ouvintes: {},
      addEventListener(tipo, fn) {
        (this._ouvintes[tipo] = this._ouvintes[tipo] || []).push(fn);
      },
      // Harness-only (o `_` avisa): dispara o que foi registrado e devolve
      // QUANTOS ouvintes correram. Zero = ninguém ligou este evento.
      _disparar(tipo) {
        const fns = this._ouvintes[tipo] || [];
        for (const fn of fns) fn({ target: this });
        return fns.length;
      },
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
  // ⚠️ O MOCK PRECISA TER O QUE A RESPOSTA DE VERDADE TEM. Em 14/08 a página
  // passou a ler `res.text()` (para sobreviver a resposta que não é JSON), e
  // este mock só tinha `json()` -- o teste reprovou na hora, que é o certo:
  // mock que não acompanha o contrato aprova código quebrado.
  const ok = (corpo) => ({
    ok: true, status: 200,
    json: async () => corpo,
    text: async () => JSON.stringify(corpo),
  });
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
        cliente_id: 998063, placa: "OVG7C78", veiculo: "TESTE VELASCO",
        rotulo: "Manutenção com troca",
        descricao: "MANUTENÇÃO COM TROCA: OVG7C78 | TESTE VELASCO | SAIRÁ: 007733214",
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
    // ⚠️ TROCAR O PERFIL PELO EVENTO, NÃO PELA FUNÇÃO. Antes isto chamava
    // `aplicarPerfil()` direto, o que testava a função e não a ligação dela
    // com o seletor. Agora o valor muda e o 'change' é disparado, como o
    // navegador faria -- `_disparar` devolve quantos ouvintes correram.
    elemento("perfil").value = perfil;
    resultado.ouvintes_perfil = elemento("perfil")._disparar("change");
    // Perfil sem termo não tem anexo: o fluxo pula a extração e vai à Etapa 2.
    if (!perfil.startsWith("manutencao")) {
      // Mesma ideia no anexo: escolher o arquivo é um 'change' no input, e o
      // handler da página escreve o nome no `dropLabel`. Conferir o rótulo
      // prova que o evento chegou -- antes só o `.files` era preenchido na mão.
      elemento("arquivo").files = [{ name: "termo.pdf" }];
      resultado.ouvintes_arquivo = elemento("arquivo")._disparar("change");
      resultado.rotulo_arquivo = elemento("dropLabel").textContent;
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

    // ── a busca de cliente é ligada por evento, com 400ms de espera ─────────
    // Digitar no campo NÃO chama `buscarCliente` na hora: o handler agenda com
    // `setTimeout(..., 400)`. Disparar o 'input' e esperar prova as duas coisas
    // -- que a ligação existe e que o atraso continua funcionando.
    elemento("buscaCliente").value = "VELASCO";
    resultado.ouvintes_busca = elemento("buscaCliente")._disparar("input");
    await new Promise((r) => setTimeout(r, 450));
    resultado.busca_chamou_backend = chamadas.some((u) =>
      u.includes("/clientes/buscar"));

    // ── Etapa 2 -> 3: o resumo. É onde a manutenção da Erika parou. ─────────
    // 🚨 Só chegar na Etapa 2 não prova nada: o fluxo continua, e cada passo
    // seguinte pode ter o mesmo tipo de defeito.
    selecionarCliente({ id: 998063, nome: "PASTELARIA VELASCO LTDA" }, "origem");
    selecionarServico({ id: 6966, descricao: "MANUTENÇÃO" });
    // ⚠️ `OVG7C78` era a placa oficial de teste da Velasco e NÃO EXISTE MAIS na
    // WESO: o teste de `liberar_serie` de 14/08 apagou o veículo, e o cache de
    // 17/08 mostra a Velasco (cliente WESO 13562) com zero veículos. Aqui não
    // faz diferença -- nada sai da máquina, o backend é mock --, mas quem for
    // repetir isto CONTRA A WESO precisa cadastrar um veículo antes.
    if (elemento("placaManual")) elemento("placaManual").value = "OVG7C78";
    if (elemento("veiculoManual")) elemento("veiculoManual").value = "TESTE VELASCO";

    await montarResumo();
    resultado.resumo_montado =
      (elemento("resumoTbody").innerHTML || "").includes("OVG7C78");
    resultado.resumo_info = (elemento("resumoInfo").innerHTML || "").slice(0, 90);
    resultado.botao_gerar_liberado = elemento("btnGerar").disabled === false;
    resultado.chamou_dry_run = chamadas.some((u) => u.includes("/gerar-os"));
  } catch (e) {
    resultado.erros.push(e.message);
    resultado.onde = e.stack ? e.stack.split("\n")[1] : "";
  }
  console.log(JSON.stringify(resultado, null, 2));
})();
