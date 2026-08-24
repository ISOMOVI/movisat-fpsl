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
    appendChild() {}, prepend() {}, remove() {},
    /* 🚨 `focus()` VAZIO APROVA MODAL QUE NAO FOCA. Ele passou a registrar
       quem recebeu o foco -- e assim "o campo recebe foco ao abrir" vira algo
       que se mede, nao que se afirma. */
    focus() { global.__foco = this; },
    /* O modal procura o `input` dentro de si. Devolver null aqui faria o
       exercicio aprovar uma tela que nao acha o campo. */
    querySelector(sel) {
      if (sel !== 'input') return null;
      return this._campo || null;
    },
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
/* 🚨 UM `localStorage` DE VERDADE. Um mock que so devolve o token nao
   exercita a retomada -- e a retomada e justamente o que a tela nunca teve. */
const _store = { fpsl_painel_token: "token-de-mentira" };
global.localStorage = {
  getItem: (k) => (k in _store ? _store[k] : null),
  setItem: (k, v) => { _store[k] = String(v); },
  removeItem: (k) => { delete _store[k]; },
};
global.montarSidebar = () => {};
global.alert = (m) => { global.__alertas.push(m); };
/* 🚨 CONTA AS CONFIRMACOES. `confirm` que devolve true e sempre silencioso
   aprova tela que nao pergunta nada -- e foi assim que a aba perdeu, sem
   ninguem ver, a trava que o `gerar_os.html` tem desde sempre. */
global.__confirms = [];
global.confirm = (m) => { global.__confirms.push(String(m)); return true; };
global.__alertas = [];
global.__foco = null;
global.__ouvintesDoc = {};
global.document = {
  getElementById: elemento,
  createElement: () => {
    const id = "__criado_" + (++_criados);
    IDS_DA_PAGINA.add(id);
    return elemento(id);
  },
  /* O `Esc` e ligado no DOCUMENTO, um ouvinte so para todos os modais. Sem
     isto aqui, o exercicio nao ve a ligacao existir. */
  addEventListener(tipo, fn) {
    (global.__ouvintesDoc[tipo] = global.__ouvintesDoc[tipo] || []).push(fn);
  },
  get activeElement() { return global.__foco; },
  querySelector: (sel) => {
    /* `.modal-bg.open` procura QUAL modal esta aberto -- e a pergunta que o
       Esc faz. Responder com um anonimo faria o Esc fechar um modal que nao
       existe e o teste passar sem nada acontecer. */
    if (sel === '.modal-bg.open') {
      /* 🚨 A LISTA VEM DO HTML, NAO DE UM ARRAY ESCRITO AQUI. Ela era fixa em
         ['modalCliente','modalServico'], entao o primeiro modal novo da tela
         ficaria fora do exercicio sem ninguem notar -- exatamente o defeito
         que o proprio Esc evita ao ter UM ouvinte no documento. O modal do
         fim da rodada (24/08) foi o primeiro a cair nisso. */
      for (const id of IDS_DA_PAGINA) {
        if (id.indexOf('modal') !== 0) continue;
        const m = elemento(id);
        if (m && m._classes.has('open')) return m;
      }
      return null;
    }
    return anonimo(sel);
  },
  querySelectorAll: () => [],
};

/* Harness-only: dispara uma tecla no documento, como o navegador faria. */
global.__tecla = (key) => {
  let n = 0;
  (global.__ouvintesDoc.keydown || []).forEach((fn) => { fn({ key }); n += 1; });
  return n;
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
  /* 🚨 O MOCK PRECISA TER `headers`. A tela passou a ler `X-Request-Id` de
     toda resposta de erro, e mock sem cabecalho aprovaria uma tela que nao le
     -- exatamente o tipo de complacencia que a lição de 14/08 proibe. */
  const cab = (id) => ({ get: (k) => (k === 'X-Request-Id' ? id : null) });
  const ok = (corpo) => ({
    ok: true, status: 200, headers: cab('req-ok'),
    json: async () => corpo,
    text: async () => JSON.stringify(corpo),
  });
  const erro = (status, detail) => ({
    ok: false, status, headers: cab('a3f1'),
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  });
  if (u.includes("__forcar_erro__")) return erro(422, "Não foi possível ler o PDF");

  if (u.includes("/operacoes/perfis")) {
    return ok({ perfis: [
      { id: "aditivo", label: "Aditivo ou teste upgrade", sem_termo: false,
        etapa_placas: "cria", recipiente: null, sem_financeira: false },
      { id: "manutencao_troca", label: "Manutenção com troca", sem_termo: true,
        etapa_placas: "cria", recipiente: "-MANUT", sem_financeira: true },
      { id: "substituicao", label: "Substituição (troca de equipamento)",
        sem_termo: false, etapa_placas: "cria_entrada", recipiente: null,
        sem_financeira: false },
    ] });
  }
  if (u.includes("/operacoes/extrair")) {
    /* 🚨 O TERMO DE SUBSTITUICAO TEM DOIS VEICULOS POR LINHA, e eles sao
       DIFERENTES -- medido no fixture substituicao.pdf: "FIAT FIORINO
       2020/2021" sai e "FIAT/FIORINO ENDURANCE" entra. E exatamente essa
       diferenca que quebrava o pareamento por texto. */
    if (u.includes("perfil=substituicao")) {
      return ok({
        termo: "9001", documento: "32020313000106", documento_no_termo: true,
        nome_no_termo: "PASTELARIA VELASCO LTDA",
        resumo: { veiculos: 1, com_entrada: 1, nao_convencionais: 0, sem_descricao: 0 },
        sem_placa: [], recipiente_sufixo: null, itens_contrato: [],
        itens: [{ veiculo: "FIAT FIORINO 2020/2021", placa: "BZR 5B97",
                  placa_gravada: "BZR 5B97", convencional: true,
                  veiculo_entrada: "FIAT/FIORINO ENDURANCE",
                  placa_entrada: "UPW 3G17",
                  placa_entrada_gravada: "UPW 3G17" }],
      });
    }
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
    return ok({ lote: { lote: "loteDeMentira01", termo: "8840", etapa: 3 },
                passos: [], resumo: {},
                resolvidas: { "TST0E55": ["harmonit", "weso"] } });
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
  if (u.includes("/operacoes/placas/do-cliente")) {
    return ok({ veiculos: [
      { placa: "TST 0E55", veiculo: "FIAT UNO" },
      { placa: "TST 0G78", veiculo: "VW GOL" },
    ], total: 2 });
  }
  if (u.includes("/operacoes/clientes/buscar")) {
    return ok({ resultados: [
      { id: 998063, nome: "Velasco Leite Pastelaria ME",
        documento: "32020313000106" },
    ], por_documento: false });
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
  if (u.includes("/operacoes/os/gerar")) {
    /* 🚨 `numero_ordem` FALTAVA NO DUBLE, e a tela le ele -- nao o `os_id`.
       O router devolve os DOIS (`operacoes_router.py:985`); o mock so mandava
       o id, entao a tabela de resultado renderizava numero VAZIO e o
       exercicio aprovava. Duble incompleto aprova tela quebrada, que e a
       licao do `exercitar_tela.js` de 14/08. */
    return ok({ criadas: [{ ok: true, os_id: 17001, numero_ordem: 16901,
                            placa: "TST 0E55", rotulo: "Instalação" }],
                avisos: [], pendencias: [], falhas_de_leitura: [],
                total: 1, com_erro: 0 });
  }
  if (u.includes("/operacoes/os/previa")) {
    return ok({
      pode_gerar: true, estado_placas: [],
      /* 🚨 O FORMATO NOVO: {texto, placa}. `placa: null` e a marca de "isto e
         do lote". Se o mock mandasse string, o exercicio aprovaria a tela
         lendo o formato velho. */
      avisos: [
        { texto: "sem equipamento nos materiais", placa: "TST 0E55" },
        { texto: "aviso que nao cita placa nenhuma", placa: null },
      ],
      operacoes: [
        { rotulo: "Instalação", placa: "TST 0E55", eh_financeira: false,
          descricao: "INSTALAÇÃO: TST 0E55", materiais: [] },
        { rotulo: "Instalação", placa: "TST 0G78", eh_financeira: false,
          descricao: "INSTALAÇÃO: TST 0G78", materiais: [] },
        { rotulo: "Financeira", placa: "(financeira)", eh_financeira: true,
          descricao: "FINANCEIRO", materiais: [] },
      ],
    });
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
global.__estado = () => ({ etapaAtual, extraido, cliente, lote, linhasPlacas,
                           placasDoCliente, servicoSelecionado });
global.__corpoOS = corpoOS;
global.__retomada = () => ({ retomando, lote });
global.__oferecer = oferecerRetomada;
global.__retomar = retomarLote;
global.__descartar = descartarLote;
`;
const src = html.split("<script>").slice(1)
  .map((p) => p.split("</script>")[0]).join("\n");
eval(src + EPILOGO);
const estado = () => global.__estado();

/* O `input` que cada modal contem, como o navegador acharia pelo DOM. */
elemento("modalCliente")._campo = elemento("buscaCliente");
elemento("modalServico")._campo = elemento("buscaServico");

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

    /* ── 7. placa que FALHOU trava, e PODE ser repetida ──────────────────
       🚨 A FALHA TEM DE ACONTECER NA PRIMEIRA TENTATIVA. Antes este bloco
       reprocessava placas que ja tinham gravado com sucesso -- e a tela,
       certa, se recusa a reescrever o que ja esta la. O cenario e que estava
       errado: media a recusa de regravar, nao a falha. */
    await escolherPerfil("aditivo");
    await espera(20);
    placasFalham = true;
    elemento("arquivo").files = [{ name: "t.pdf" }];
    await lerTermo();
    await espera(20);
    irPara(2); await espera(60);
    irPara(3); await espera(60);
    registrarCelulas(estado().linhasPlacas.length);
    await processarPlacas();
    await espera(30);
    r.avancar_travado_com_falha = elemento("btnAvancar").disabled;
    r.dica_com_falha = elemento("faltaDica").textContent;
    irPara(4);
    await espera(10);
    r.etapa_com_placa_falhada = estado().etapaAtual;

    /* a placa que falhou PODE ser tentada de novo -- e a razao do retomar */
    placasFalham = false;
    const antes = chamadas.filter((u) => u.includes("placas/uma")).length;
    await processarPlacas();
    await espera(30);
    const depois = chamadas.filter((u) => u.includes("placas/uma")).length;
    r.retentou_a_que_falhou = depois > antes;
    r.gravadas_apos_retentar =
      estado().linhasPlacas.filter((l) => l.situacao && !placaFalhou(l.situacao)).length;

    /* ── 8. trocar o perfil zera a rodada ────────────────────────────────── */
    await escolherPerfil("manutencao_troca");
    await espera(20);
    r.extraido_apos_troca = estado().extraido === null;
    r.linhas_apos_troca = estado().linhasPlacas.length;
    r.lote_apos_troca = estado().lote === null;
    r.etapa_apos_troca = estado().etapaAtual;

    /* ── 9. perfil sem termo não exige PDF na etapa 1 ────────────────────── */
    r.avancar_liberado_sem_termo_perfil = elemento("btnAvancar").disabled === false;

    /* ── 10. 🚨 O CAMINHO SEM TERMO, que até 21/08 morria na etapa 3 ────── */
    // manutencao_troca ja esta escolhido pelo passo 8. Etapa 1 nao pede PDF.
    irPara(2);
    await espera(30);
    r.st_etapa2 = estado().etapaAtual;
    r.st_recado_pede_cliente =
      elemento("msgEtapa2").innerHTML.includes("Buscar");
    r.st_avancar_travado_sem_cliente = elemento("btnAvancar").disabled;

    // escolher o cliente pelo modal, como gente faz
    abrirModalCliente();
    await espera(30);
    escolherCliente({ id: 998063, nome: "Velasco Leite Pastelaria ME",
                      documento: "32020313000106" });
    await espera(60);
    r.st_cliente_resolvido = !!estado().cliente;
    r.st_campo_cliente = elemento("clienteCampo").value;

    irPara(3);
    await espera(60);
    r.st_etapa3 = estado().etapaAtual;
    r.st_bloco_adicionar = elemento("addPlacaWrap").style.display;
    r.st_placas_do_cliente = (estado().placasDoCliente || []).length;
    r.st_linhas_antes = estado().linhasPlacas.length;
    r.st_avancar_travado_sem_placa = elemento("btnAvancar").disabled;

    // adicionar a primeira: vem a placa E o recipiente -MANUT
    elemento("placaDoCliente").value = "0";
    adicionarPlaca();
    await espera(10);
    r.st_linhas_apos_1 = estado().linhasPlacas.length;
    r.st_tem_recipiente = estado().linhasPlacas.some((l) => l.recipiente);
    r.st_sufixo_recipiente =
      (estado().linhasPlacas.find((l) => l.recipiente) || {}).placa;

    // a mesma de novo nao duplica
    adicionarPlaca();
    await espera(10);
    r.st_linhas_apos_repetida = estado().linhasPlacas.length;

    // uma segunda placa: "mesmo adicionando mais de uma"
    elemento("placaDoCliente").value = "1";
    adicionarPlaca();
    await espera(10);
    r.st_linhas_apos_2 = estado().linhasPlacas.length;

    // remover a segunda leva o recipiente dela junto
    const iSegunda = estado().linhasPlacas.findIndex(
      (l) => !l.recipiente && l.placa === "TST 0G78");
    removerPlaca(iSegunda);
    await espera(10);
    r.st_linhas_apos_remover = estado().linhasPlacas.length;

    // gravar e chegar na etapa 4
    registrarCelulas(estado().linhasPlacas.length);
    const _antesConf = global.__confirms.length;
    await processarPlacas();
    r.st_confirm_manut = global.__confirms.slice(_antesConf)[0] || "";
    r.st_linhas_reais = estado().linhasPlacas.filter((l) => !l.recipiente).length;
    r.st_linhas_recipiente = estado().linhasPlacas.filter((l) => l.recipiente).length;
    await espera(30);
    irPara(4);
    await espera(60);
    r.st_etapa_final = estado().etapaAtual;
    r.st_lote_aberto = !!estado().lote;

    /* ── 11. o serviço se ESCOLHE, nao se digita ─────────────────────────── */
    abrirModalServico();
    await espera(60);
    selecionarServico({ id: 6967, descricao: "SUBSTITUICAO" });
    r.sv_campo = elemento("servicoCampo").value;
    r.sv_selecionado = (estado().servicoSelecionado || {}).id;

    /* ── 12. voltar uma etapa e retornar: o trabalho sobrevive? ─────────── */
    // Reconstroi um fluxo COM termo do zero.
    await escolherPerfil("aditivo");
    await espera(20);
    elemento("arquivo").files = [{ name: "t.pdf" }];
    await lerTermo();
    await espera(20);
    irPara(2); await espera(60);
    irPara(3); await espera(60);
    registrarCelulas(estado().linhasPlacas.length);
    await processarPlacas();
    await espera(30);
    r.vt_gravadas = estado().linhasPlacas.filter((l) => l.situacao).length;
    r.vt_avancar_liberado = elemento("btnAvancar").disabled === false;

    // o operador volta para conferir o cliente e retorna
    irPara(2); await espera(40);
    irPara(3); await espera(60);
    r.vt_gravadas_depois = estado().linhasPlacas.filter((l) => l.situacao).length;
    const _tab = document.querySelector("#tabelaPlacas tbody").innerHTML;
    r.linha_gravada_sem_input = !_tab.includes("data-campo=");
    r.vt_avancar_liberado_depois = elemento("btnAvancar").disabled === false;
    r.vt_dica_depois = elemento("faltaDica").textContent;

    /* ── 13. 🚨 SUBSTITUICAO: a placa de ENTRADA chega ao payload? ──────── */
    await escolherPerfil("substituicao");
    await espera(20);
    elemento("arquivo").files = [{ name: "sub.pdf" }];
    await lerTermo();
    await espera(20);
    irPara(2); await espera(60);
    irPara(3); await espera(60);
    const linhas = estado().linhasPlacas;
    r.sub_linhas = linhas.length;
    r.sub_tem_entrada_na_tela = linhas.some((l) => l.entrada);
    const payload = global.__corpoOS(false);
    r.sub_placas_no_payload = payload.placas.length;
    r.sub_placa_saida = (payload.placas[0] || {}).placa;
    r.sub_placa_entrada = (payload.placas[0] || {}).placa_entrada;
    r.sub_veiculo_entrada = (payload.placas[0] || {}).veiculo_entrada;

    /* ── 13b. a previa e a geracao, ate o fim ───────────────────────────── */
    // volta ao fluxo do aditivo, que ja tem placas gravadas
    await escolherPerfil("aditivo");
    await espera(20);
    elemento("arquivo").files = [{ name: "t.pdf" }];
    await lerTermo();
    await espera(20);
    irPara(2); await espera(60);
    irPara(3); await espera(60);
    registrarCelulas(estado().linhasPlacas.length);
    await processarPlacas();
    await espera(30);
    irPara(4); await espera(60);
    await conferirOS();
    await espera(30);
    r.previa_liberou_gerar = elemento("btnGerar").disabled === false;

    /* 🚨 MEDE A PREVIA ANTES DE GERAR. Depois do `gerarOS` o `previaOS` e
       substituido pelo RESULTADO -- medir la dava tudo falso, e a falha era do
       exercicio, nao da tela. */
    const _p = elemento("previaOS").innerHTML;
    r.prev_tem_moldura = _p.includes("previa-moldura");
    r.prev_titulo = /3 OS serão[\s\S]{0,60}?Harmonit/.test(_p);
    r.prev_aviso_na_os = _p.includes("aviso-na-os");
    r.prev_aviso_generico_em_cima =
      _p.indexOf("aviso que nao cita") < _p.indexOf("aviso-na-os");
    await gerarOS();
    await espera(30);
    r.gerou = chamadas.some((u) => u.includes("/operacoes/os/gerar"));
    r.rotulo_gerar = elemento("btnGerar").textContent;
    r.osinfo_apos_previa = elemento("osInfo").innerHTML;

    /* ── 14. as duas escritas perguntam antes? ──────────────────────────── */
    r.confirms = global.__confirms;
    r.confirmou_placas = global.__confirms.some(
      (m) => /Harmonit e na WESO/i.test(m));
    r.confirmou_os = global.__confirms.some((m) => /Gerar \d+ OS/i.test(m));

    /* ── 15. 🚨 RETOMADA: a chave sobrevive e o gravado nao se refaz ────── */
    /* A chave saiu de proposito quando as OS foram geradas no passo 13b:
       rodada terminada nao se retoma. Isso e comportamento, nao falta. */
    r.rt_chave_apos_gerar = global.localStorage.getItem("fpsl_operacoes_lote");

    // simula reabrir a tela: o operador volta e a barra pergunta
    zerarRodada();
    await espera(10);
    // zerarRodada esquece de proposito; recria a chave como se fosse outra sessao
    global.localStorage.setItem("fpsl_operacoes_lote", JSON.stringify({
      lote: "loteDeMentira01", perfil: "aditivo", termo: "8840",
      documento: "32020313000106", quando: Date.now(),
    }));
    await global.__oferecer();
    await espera(20);
    r.rt_barra_visivel = elemento("barraRetomar").style.display !== "none";
    r.rt_barra_texto = elemento("retomarTexto").innerHTML;

    global.__retomar();
    await espera(20);
    r.rt_perfil_restaurado = elemento("perfil").value;

    // sobe o MESMO termo: o lote tem de ser reusado, nao criado outro
    elemento("arquivo").files = [{ name: "8840.pdf" }];
    await lerTermo();
    await espera(20);
    r.rt_lote_reusado = estado().lote === "loteDeMentira01";
    /* Retomar renova o carimbo: a rodada continua AGORA. Sem isto uma rodada
       retomada perto das 24h expiraria no meio dela. */
    const guardado = JSON.parse(
      global.localStorage.getItem("fpsl_operacoes_lote") || "{}");
    r.rt_chave_renovada = guardado.lote === "loteDeMentira01"
      && (Date.now() - (guardado.quando || 0)) < 5000;
    irPara(2); await espera(60);
    irPara(3); await espera(60);
    r.rt_ja_resolvidas = estado().linhasPlacas.filter((l) => l.situacao).length;
    r.rt_recado = elemento("msgEtapa3").innerHTML;

    // e descartar limpa a chave
    global.localStorage.setItem("fpsl_operacoes_lote", "{\"lote\":\"x\"}");
    global.__descartar();
    r.rt_descartou = global.localStorage.getItem("fpsl_operacoes_lote") === null;

    /* ── 16. todo erro leva a referencia da requisicao ──────────────────── */
    try {
      await lerResposta(await global.fetch("/painel/api/__forcar_erro__"));
      r.erro_com_ref = "*** nao levantou ***";
    } catch (e) {
      r.erro_com_ref = e.message;
    }

    /* ── 17. as secoes carregam o VALOR, e a trava vale no clique ────────── */
    await escolherPerfil("aditivo");
    await espera(20);
    elemento("arquivo").files = [{ name: "t.pdf" }];
    await lerTermo();
    await espera(20);
    irPara(2); await espera(60);
    irPara(3); await espera(60);
    registrarCelulas(estado().linhasPlacas.length);
    await processarPlacas();
    await espera(30);
    irPara(4); await espera(60);
    r.sec_valor_1 = elemento("valor-1").textContent;
    r.sec_valor_2 = elemento("valor-2").textContent;
    r.sec_valor_3 = elemento("valor-3").textContent;
    r.sec_marca_1 = elemento("marca-1").textContent;
    r.sec_marca_4 = elemento("marca-4").textContent;
    r.sec_aberta_4 = elemento("sec-4")._classes.has("aberta");
    r.sec_pronta_1 = elemento("sec-1")._classes.has("pronta");

    /* clicar no cabecalho usa o MESMO irPara -- entao a trava vale nele */
    zerarRodada();
    pintarEtapa(1);
    await espera(20);
    irPara(4);
    await espera(10);
    r.sec_clique_travado = estado().etapaAtual;
    r.sec_trancada_3 = elemento("sec-3")._classes.has("trancada");

    /* ── 18. os modais pelo teclado ──────────────────────────────────────── */
    r.mod_esc_ligado = (global.__ouvintesDoc.keydown || []).length;

    const botao = elemento("btnBuscarCliente");
    global.__foco = botao;                     // como se ele tivesse clicado
    abrirModalCliente();
    await espera(20);
    r.mod_abriu = elemento("modalCliente")._classes.has("open");
    r.mod_focou_campo = global.__foco === elemento("buscaCliente");

    r.mod_disparos = global.__tecla("Escape");
    r.mod_fechou_com_esc = !elemento("modalCliente")._classes.has("open");
    r.mod_foco_voltou = global.__foco === botao;

    // tecla que nao e Esc nao fecha nada
    abrirModalServico();
    await espera(20);
    global.__tecla("a");
    r.mod_outra_tecla_nao_fecha = elemento("modalServico")._classes.has("open");
    global.__tecla("Escape");
    r.mod_servico_fechou = !elemento("modalServico")._classes.has("open");

    /* ── 19. 🚨 A RODADA TEM FIM: Concluir → resumo → volta ao inicio ─────
       Ate 24/08 as OS saiam e a tela ficava parada no resultado: comecar
       outra rodada era recarregar a pagina ou trocar o tipo de operacao --
       que zera por efeito colateral. Aqui o exercicio CLICA no Concluir e
       confere onde a tela parou, que e a licao de 21/08: fonte que descreve
       o comportamento nao e o comportamento. */
    await escolherPerfil("aditivo");
    await espera(20);
    elemento("arquivo").files = [{ name: "t.pdf" }];
    await lerTermo();
    await espera(20);
    irPara(2); await espera(60);
    irPara(3); await espera(60);
    registrarCelulas(estado().linhasPlacas.length);
    await processarPlacas();
    await espera(30);
    irPara(4); await espera(60);
    await conferirOS();
    await espera(30);
    /* Antes de gerar o botao NAO existe: rodada sem OS nao tem o que concluir. */
    r.fim_botao_antes = elemento("btnConcluir").hidden;
    await gerarOS();
    await espera(30);
    r.fim_botao_apareceu = elemento("btnConcluir").hidden === false;

    global.__foco = elemento("btnConcluir");    // como se ele tivesse clicado
    abrirConcluir();
    await espera(10);
    r.fim_modal_abriu = elemento("modalConcluir")._classes.has("open");
    r.fim_resumo = elemento("resumoConcluir").innerHTML;
    r.fim_focou_ok = global.__foco === elemento("okConcluir");

    concluirRodada();
    await espera(20);
    r.fim_modal_fechou = !elemento("modalConcluir")._classes.has("open");
    r.fim_etapa = estado().etapaAtual;
    r.fim_lote = estado().lote;
    r.fim_linhas = estado().linhasPlacas.length;
    r.fim_botao_sumiu = elemento("btnConcluir").hidden === true;
    r.fim_tabela_limpa =
      document.querySelector("#tabelaPlacas tbody").innerHTML === "";
    r.fim_previa_limpa = elemento("previaOS").innerHTML === "";
    r.fim_marca_1 = elemento("marca-1").textContent;
    r.fim_contador = elemento("contadorEtapa").textContent;

    r.chamadas = chamadas;
  } catch (e) {
    r.erros.push(String((e && e.stack) || e));
  }
  process.stdout.write(JSON.stringify(r, null, 1));
})();
