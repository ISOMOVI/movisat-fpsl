/* Barra de status do rodapé — o mesmo contrato da barra do MoviZap
 * (`frontend/src/componentes/BarraStatus.vue`, em produção desde 12/08):
 *
 *     código da tela · usuário · duração da sessão ···· req · data e hora
 *
 * 🚨 O `req` É O MOTIVO DE ELA EXISTIR. A pessoa lê `req a3f9` na tela e o
 * journal da VPS tem `req=a3f9` naquela requisição exata. Sem isso, o que se
 * procura no log é "a tela de placas, por volta das 14h" -- e foi assim que o
 * loop de 17/08 passou uma manhã inteira parecendo saúde: 786 chamadas, todas
 * 200, e nada ligando o que a pessoa via ao que o servidor registrava.
 *
 * Carregar ANTES do sidebar.js: o interceptador de `fetch` precisa estar de pé
 * antes da primeira chamada da página, senão a barra nasce sem `req`.
 * `tests/teste_barra_status.py` reprova se alguma página do painel não o
 * carregar, ou carregar na ordem errada.
 */
(function () {
  'use strict';

  const estado = {
    reqId: '', emVoo: 0, codigo: '—', titulo: '',
    usuario: '', owner: false, desde: null,
  };

  /* ── 1. interceptar fetch: req id e "carregando" ──────────────────────── */
  const fetchOriginal = window.fetch;
  window.fetch = function (...args) {
    estado.emVoo += 1;
    pintar();
    return fetchOriginal.apply(this, args).then(
      function (res) {
        estado.emVoo -= 1;
        const id = res.headers.get('X-Request-Id');
        if (id) estado.reqId = id;
        pintar();
        return res;
      },
      function (err) {
        estado.emVoo -= 1;
        pintar();
        throw err;
      },
    );
  };

  /* ── 2. quando a sessão começou, direto do token ──────────────────────── */
  function inicioDaSessao(token) {
    /* O `iat` do próprio JWT. Ler do token e não do localStorage porque quem
       tem o relógio bom é o servidor -- e storage limpo não deve zerar a
       conta. Token emitido antes de 18/08 não tem o campo: mostra travessão. */
    try {
      const meio = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      const corpo = JSON.parse(atob(meio));
      return corpo.iat ? new Date(corpo.iat * 1000) : null;
    } catch (e) {
      return null;
    }
  }

  function duracao() {
    if (!estado.desde) return '—';
    const seg = Math.max(0, Math.floor((Date.now() - estado.desde.getTime()) / 1000));
    const h = Math.floor(seg / 3600);
    const m = Math.floor((seg % 3600) / 60);
    if (h) return h + 'h ' + String(m).padStart(2, '0') + 'min';
    if (m) return m + 'min ' + String(seg % 60).padStart(2, '0') + 's';
    return seg + 's';
  }

  function agora() {
    return new Date().toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  }

  /* ── 3. o desenho ─────────────────────────────────────────────────────── */
  /* 🚨 O CSS NÃO MORA MAIS AQUI. Ele está em `barra_status.css`, ligado no
     <head> de cada página. A primeira versão injetava um <style> no
     `DOMContentLoaded`, e como três regras mexem em layout (padding do body e
     altura da sidebar), a página pintava inteira e só então encolhia 30px --
     um salto visível a cada troca de aba. O navegador pinta com o CSS que tem
     na hora; regra que chega depois não corrige, remonta. */

  /* Mesma função das telas: a barra escreve login e título vindos do servidor,
     e o painel inteiro escapa desde 15/07. Não é porque é rodapé que muda. */
  function esc(s) {
    const mapa = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return String(s === null || s === undefined ? '' : s)
      .replace(/[&<>"']/g, function (c) { return mapa[c]; });
  }

  let elemento = null;

  function pintar() {
    if (!elemento) return;
    const partes = [];
    partes.push(
      '<span class="barra-status__item barra-status__codigo" title="Código da tela: '
      + esc(estado.codigo) + '"><i class="bi bi-window"></i>'
      + '<span class="barra-status__mono">' + esc(estado.codigo) + '</span></span>',
    );
    if (estado.titulo) {
      partes.push('<span class="barra-status__item barra-status__opcional">'
        + esc(estado.titulo) + '</span>');
    }
    partes.push('<span class="barra-status__sep">·</span>');
    partes.push(
      '<span class="barra-status__item barra-status__opcional"><i class="bi bi-person"></i>'
      + esc(estado.usuario || '—')
      + (estado.owner ? '<span class="barra-status__owner">owner</span>' : '')
      + '</span>',
    );
    partes.push('<span class="barra-status__sep">·</span>');
    partes.push(
      '<span class="barra-status__item barra-status__opcional" '
      + 'title="Tempo desde o início desta sessão"><i class="bi bi-hourglass-split"></i>'
      + 'sessão ' + esc(duracao()) + '</span>',
    );
    partes.push('<span class="barra-status__espaco"></span>');
    if (estado.emVoo > 0) {
      partes.push('<span class="barra-status__item"><span class="barra-status__girando"></span></span>');
    }
    partes.push(
      '<span class="barra-status__item" title="Última requisição respondida pelo servidor">'
      + '<i class="bi bi-hash"></i><span class="barra-status__mono">req '
      + esc(estado.reqId || '—') + '</span></span>',
    );
    partes.push('<span class="barra-status__sep">·</span>');
    partes.push('<span class="barra-status__item barra-status__mono">' + esc(agora()) + '</span>');
    elemento.innerHTML = partes.join('');
  }

  function criar() {
    elemento = document.createElement('footer');
    elemento.className = 'barra-status';
    document.body.appendChild(elemento);
    /* Já nasce escrita. O espaço dela é reservado pelo CSS antes da primeira
       pintura, então isto preenche uma faixa que já existe -- não empurra
       nada. */
    pintar();
    setInterval(pintar, 1000);
  }

  /* ── 4. o perfil, que o sidebar.js já buscou -- a barra não pede de novo ── */
  window.barraStatusRecebePerfil = function (perfil) {
    if (!perfil) return;
    estado.usuario = perfil.login || '';
    estado.owner = !!perfil.owner;
    const caminho = window.location.pathname.replace(/\/+$/, '') || '/';
    const tela = (perfil.codigos || {})[caminho];
    if (tela) {
      estado.codigo = tela.codigo;
      estado.titulo = tela.titulo;
    }
    pintar();
  };

  function arrancar() {
    const token = localStorage.getItem('fpsl_painel_token');
    if (!token) return;            // a tela de login não tem barra
    estado.desde = inicioDaSessao(token);
    criar();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', arrancar);
  } else {
    arrancar();
  }
})();
