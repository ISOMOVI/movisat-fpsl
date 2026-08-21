/* Roda a aba Operações de verdade, sem navegador. 2026-08-21.
 *
 * 🚨 POR QUE ISTO EXISTE. A trava de etapas ficou SOLTA da F1 até 21/08 e
 * nenhuma das 1.322 verificações viu. O motivo é estrutural: os testes da aba
 * liam o FONTE da tela (`grep` por texto) e o fonte estava certo -- o
 * comentário dizia que a etapa N só abre com a N-1 concluída. Faltava a linha
 * que faz isso. Fonte que descreve o comportamento não é o comportamento.
 *
 * Em 21/08 o operador foi da etapa 1 direto para a 4 e a prévia devolveu 400
 * "Nenhuma placa foi informada". Os dois lotes daquele dia estão no registro
 * em `etapa 1` com ZERO placas gravadas.
 *
 * Aqui o script da página roda inteiro num DOM de mentira, com `fetch`
 * devolvendo o JSON que o router devolve. O exercício CLICA em Avançar, como
 * gente faz, e o Python confere onde a tela parou.
 *
 * Uso: node exercitar_operacoes.js <operacoes.html>
 * Sai com JSON no stdout.
 */
const fs = require("fs");

const html = fs.readFileSync(process.argv[2], "utf8");

/* 🚨 O QUE NÃO EXISTE NO HTML DEVOLVE `null`. Mock complacente que inventa
   elemento para qualquer id aprova tela quebrada -- foi a lição do
   `exercitar_tela.js` em 14/08. */
const IDS_DA_PAGINA = new Set(
  [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1])
);
const elementos = {};
let _criados = 0;

function novoElemento(id) {
  return {
    id, value: "", innerHTML: "", textContent: "", disabled: false, title: "",
    files: [], style: {},
    _classes: new Set(),
    classList: {
      _dono: null,
      toggle(c, ligado) {
        if (ligado === undefined) ligado = !this._dono._classes.has(c);
        if (ligado) this._dono._classes.add(c); else this._dono._classes.delete(c);
      },
      add(c) { this._dono._classes.add(c); },
      remove(c) { this._dono._classes.delete(c); },
      contains(c) { return this._dono._classes.has(c); },
    },
    appendChild() {}, prepend() {}, remove() {}, focus() {},
    _ouvintes: {},
    addEventListener(tipo, fn) {
      (this._ouvintes[tipo] = this._ouvintes[tipo] || []).push(fn);
    },
    /* Harness-only: dispara o que a página ligou e devolve QUANTOS correram.
       Zero = ninguém ligou este evento. */
    _disparar(tipo) {
      const fns = this._ouvintes[tipo] || [];
      for (const fn of fns) fn({ target: this });
      const direto = this["on" + tipo];
      if (typeof direto === "function") { direto({ target: this }); return fns.length + 1; }
      return fns.length;
    },
  };
}

function elemento(id) {
  if (!IDS_DA_PAGINA.has(id) && !(id in elementos)) return null;
  if (!elementos[id]) {
    elementos[id] = novoElemento(id);
    elementos[id].classList._dono = elementos[id];
  }
  return elementos[id];
}

/* querySelector devolve um elemento anônimo: a página escreve em
   `#tabelaPlacas tbody`, que não é id. Devolver null aqui estoura na tela e
   esconde o que se quer medir. */
const anonimos = {};
function anonimo(sel) {
  if (!anonimos[sel]) {
    anonimos[sel] = novoElemento("__sel_" + (++_criados));
    anonimos[sel].classList._dono = anonimos[sel];
  }
  return anonimos[sel];
}

global.window = { location: { href: "" } };
global.localStorage = { getItem: () => "token-de-mentira" };
global.montarSidebar = () => {};
global.alert = (m) => { global.__alertas.push(m); };
global.confirm = () => true;
global.__alertas = [];
global.document = {
  getElementById: elemento,
  createElement: () => {
    const id = "__criado_" + (++_criados);
    IDS_DA_PAGINA.add(id);
    return elemento(id);
  },
  querySelector: anonimo,
  querySelectorAll: () => [],
};

/* ── fetch de mentira ──────────────────────────────────────────────────────
   Os valores são os que o router devolve de verdade, e o TERMO é fixture.
   🚨 Nenhuma chamada sai da máquina: teste da aba não escreve em sistema
   externo, decisão de 17/08 depois de a própria suíte criar 6 veículos
   permanentes no Harmonit. */
const chamadas = [];
let clienteSituacao = "ok";
let placasFalham = false;

global.fetch = async (url, opcoes) => {
  const u = String(url);
  chamadas.push(u);
  const ok = (corpo) => ({
    ok: true, status: 200,
    json: async () => corpo,
    text: async () => JSON.stringify(corpo),
  });

  if (u.includes("/operacoes/perfis")) {
    return ok({ perfis: [
      { id: "aditivo", label: "Aditivo ou teste upgrade", sem_termo: false,
        etapa_placas: "cria", recipiente: null, sem_financeira: false },
      { id: "manutencao_troca", label: "Manutenção com troca", sem_termo: true,
        etapa_placas: "cria", recipiente: "-MANUT", sem_financeira: true },
    ] });
  }
  if (u.includes("/operacoes/extrair")) {
    return ok({
      termo: "8840", documento: "32020313000106", documento_no_termo: true,
      nome_no_termo: "PASTELARIA VELASCO LTDA",
      resumo: { veiculos: 2, com_entrada: 0, nao_convencionais: 0, sem_descricao: 0 },
      sem_placa: [],
      recipiente_sufixo: null,
      itens: [
        { veiculo: "FIAT UNO", placa: "TST 0E55", placa_gravada: "TST0E55",
          convencional: true },
        { veiculo: "VW GOL", placa: "TST 0G78", placa_gravada: "TST0G78",
          convencional: true },
      ],
      itens_contrato: [],
    });
  }
  if (u.includes("/operacoes/cliente/criar-na-weso")) {
    clienteSituacao = "ok";
    return ok({ acao: "criado", id: 13624, verificado_relendo: true });
  }
  if (u.includes("/operacoes/cliente")) {
    if (clienteSituacao === "sem_harmonit") {
      return ok({ harmonit: null, weso: null, situacao: "sem_harmonit",
                  recado: "Não existe no Harmonit." });
    }
    if (clienteSituacao === "falta_na_weso") {
      return ok({ harmonit: { id: 998063, nome: "Velasco Leite Pastelaria ME" },
                  weso: null, situacao: "falta_na_weso",
                  recado: "Falta na WESO." });
    }
    return ok({ harmonit: { id: 998063, nome: "Velasco Leite Pastelaria ME" },
                weso: { id: 13624, nome: "PASTELARIA VELASCO LTDA" },
                situacao: "ok", recado: "Existe nos dois." });
  }
  if (u.includes("/operacoes/lote/")) {
    return ok({ lote: {}, passos: [], resumo: {}, resolvidas: {} });
  }
  if (u.includes("/operacoes/lote")) return ok({ lote: "loteDeMentira01" });
  if (u.includes("/operacoes/placas/uma")) {
    if (placasFalham) {
      return ok({ harmonit: { acao: "criado", id: 1 },
                  weso: { acao: "falhou", erro: "timeout" } });
    }
    return ok({ harmonit: { acao: "criado", id: 1 },
                weso: { acao: "criado", id: 2 } });
  }
  if (u.includes("/operacoes/modelos")) return ok({ modelos: [] });
  if (u.includes("/operacoes/prioridades")) {
    return ok({ prioridades: [{ id: 382, descricao: "Normal" }], default: 382 });
  }
  if (u.includes("/operacoes/problemas")) {
    return ok({ problemas: [{ id: 7384, descricao: "MANUTENÇÃO" }] });
  }
  if (u.includes("/servicos/buscar")) {
    return ok({ resultados: [{ id: 6967, descricao: "SUBSTITUIÇÃO" }] });
  }
  if (u.includes("/operacoes/os/previa")) {
    return ok({ operacoes: [], avisos: [], estado_placas: [] });
  }
  return ok({});
};

/* ── carrega o script da página ────────────────────────────────────────────
   ⚠️ `let` DECLARADO DENTRO DE `eval` NÃO ESCAPA do escopo do eval, ao
   contrário de `var`. Ler `etapaAtual` daqui de fora dá ReferenceError e
   pareceria defeito da tela. O epílogo abaixo é acrescentado ao fonte e
   fecha sobre as variáveis de lá dentro -- é a única forma de olhar o estado
   sem alterar a página para ser testável, que seria testar outra coisa.

   ⚠️ As FUNÇÕES não precisam de epílogo: `function` declarada dentro de eval
   vai para o escopo que chamou, então `irPara`, `lerTermo` e `processarPlacas`
   já são visíveis aqui -- e declarar `const irPara` faria colisão de nome. */
const EPILOGO = `
global.__estado = () => ({ etapaAtual, extraido, cliente, lote, linhasPlacas });
`;
const src = html.split("<script>").slice(1)
  .map((p) => p.split("</script>")[0]).join("\n");
eval(src + EPILOGO);
const estado = () => global.__estado();

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

async function escolherPerfil(id) {
  elemento("perfil").value = id;
  return elemento("perfil")._disparar("change");
}

/* As células `sit-N` nascem quando `desenharPlacas` escreve o `innerHTML` da
   tabela -- num navegador elas existem, aqui não, porque o mock não faz parse
   de HTML. Registrá-las é modelar o que o navegador teria, não afrouxar o
   teste: se o id mudar de nome na tela, `processarPlacas` volta a estourar. */
function registrarCelulas(quantas) {
  for (let n = 0; n < quantas; n++) IDS_DA_PAGINA.add("sit-" + n);
}

(async () => {
  const r = { erros: [] };
  try {
    await espera(50);

    /* ── 1. sem nada feito, Avançar não pode andar ───────────────────────── */
    r.ouvintes_perfil = await escolherPerfil("aditivo");
    await espera(10);
    r.etapa_inicial = estado().etapaAtual;
    r.avancar_travado_sem_termo = elemento("btnAvancar").disabled;
    r.dica_sem_termo = elemento("faltaDica").textContent;

    /* O clique de verdade, não a função: é assim que o operador anda. */
    irPara(estado().etapaAtual + 1);
    await espera(10);
    r.etapa_apos_avancar_sem_termo = estado().etapaAtual;

    /* ── 2. o salto direto para a 4, que foi o que aconteceu em 21/08 ────── */
    irPara(4);
    await espera(10);
    r.etapa_apos_salto_para_4 = estado().etapaAtual;

    /* ── 3. com termo lido, a etapa 1 fecha ──────────────────────────────── */
    elemento("arquivo").files = [{ name: "termo8840.pdf" }];
    await lerTermo();
    await espera(10);
    r.placas_lidas = (estado().extraido.itens || []).length;
    r.avancar_liberado_com_termo = elemento("btnAvancar").disabled === false;

    irPara(2);
    await espera(60);
    r.etapa_apos_termo = estado().etapaAtual;
    r.cliente_consultado = chamadas.some((u) => u.includes("/operacoes/cliente"));

    /* ── 4. cliente ok deixa passar; a etapa 3 ainda não ─────────────────── */
    r.avancar_liberado_com_cliente = elemento("btnAvancar").disabled === false;
    irPara(3);
    await espera(60);
    r.etapa_apos_cliente = estado().etapaAtual;
    r.linhas_na_etapa3 = estado().linhasPlacas.length;

    /* ── 5. placas montadas mas NÃO gravadas: não passa ──────────────────── */
    r.avancar_travado_sem_gravar = elemento("btnAvancar").disabled;
    r.dica_sem_gravar = elemento("faltaDica").textContent;
    irPara(4);
    await espera(10);
    r.etapa_apos_placas_pendentes = estado().etapaAtual;

    /* ── 6. gravadas com sucesso: agora passa ────────────────────────────── */
    registrarCelulas(estado().linhasPlacas.length);
    await processarPlacas();
    await espera(20);
    r.avancar_liberado_apos_gravar = elemento("btnAvancar").disabled === false;
    irPara(4);
    await espera(60);
    r.etapa_final = estado().etapaAtual;

    /* ── 7. placa que FALHOU trava de novo ───────────────────────────────── */
    placasFalham = true;
    irPara(3);
    await espera(20);
    await processarPlacas();
    await espera(20);
    r.avancar_travado_com_falha = elemento("btnAvancar").disabled;
    r.dica_com_falha = elemento("faltaDica").textContent;
    irPara(4);
    await espera(10);
    r.etapa_com_placa_falhada = estado().etapaAtual;
    placasFalham = false;

    /* ── 8. trocar o perfil zera a rodada ────────────────────────────────── */
    await escolherPerfil("manutencao_troca");
    await espera(20);
    r.extraido_apos_troca = estado().extraido === null;
    r.linhas_apos_troca = estado().linhasPlacas.length;
    r.lote_apos_troca = estado().lote === null;
    r.etapa_apos_troca = estado().etapaAtual;

    /* ── 9. perfil sem termo não exige PDF na etapa 1 ────────────────────── */
    r.avancar_liberado_sem_termo_perfil = elemento("btnAvancar").disabled === false;

    r.chamadas = chamadas;
  } catch (e) {
    r.erros.push(String((e && e.stack) || e));
  }
  process.stdout.write(JSON.stringify(r, null, 1));
})();
