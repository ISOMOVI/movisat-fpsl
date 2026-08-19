/* Sidebar do painel, montada a partir do PERFIL do usuário.
 *
 * Antes de 2026-07-27 cada página trazia o <nav> escrito à mão e escondia
 * Usuários/Configurações lendo `fpsl_painel_admin` do localStorage -- ou seja,
 * a permissão vivia no navegador e o link sumia, mas a tela continuava
 * acessível pela URL. Agora quem manda é o backend: /painel/api/me devolve as
 * abas já resolvidas, esta função desenha só o que veio, e quem cair numa
 * página fora do perfil é redirecionado.
 *
 * Uso: <nav class="sidebar-nav" id="sidebarNav"></nav> + montarSidebar('id_da_aba').
 *
 * 🚨 O `id` DE CADA ABA É A PERMISSÃO, NÃO O CÓDIGO DA TELA. As 9 páginas
 * passam permissão (`'cadastro_placas'`, `'config'`), e é o que `/painel/api/me`
 * tem de devolver em `id`. Em 17/08 `do_usuario` passou a devolver só
 * `codigo`/`titulo`: `a.id` virou `undefined`, `temAba` virou `false` em TODA
 * página e o painel entrou em loop de redirecionamento -- piscando na tela do
 * usuário, sem erro nenhum no servidor (786 chamadas, todas 200). O teste
 * `teste_contrato_sidebar.py` agora lê ESTE arquivo e prende os campos.
 */
const CHAVE_ABAS = 'fpsl_painel_abas';

/* Desenha o <nav> e devolve o índice do item ativo. Separado de
   `montarSidebar` porque roda DUAS vezes: uma com o que estava no cache e
   outra com o que o /me acabou de responder. */
function desenharAbas(abasDoPerfil) {
  /* Quem fica em negrito é a ROTA, não a permissão. `config` cobre duas telas
     (Configurações e Registro de Telas) e comparar por permissão acenderia as
     duas ao mesmo tempo. Exato ganha de prefixo, para o Registro de Telas não
     acender junto com Configurações; o prefixo existe para a página filha sem
     link próprio (o Histórico de Cadastros) acender a mãe dela. */
  const caminho = window.location.pathname.replace(/\/+$/, '') || '/';
  let ativo = abasDoPerfil.findIndex((a) => a.rota === caminho);
  if (ativo < 0) {
    let melhor = 0;
    abasDoPerfil.forEach((a, i) => {
      if (caminho.startsWith(a.rota + '/') && a.rota.length > melhor) {
        melhor = a.rota.length; ativo = i;
      }
    });
  }
  const nav = document.getElementById('sidebarNav');
  if (nav) {
    nav.innerHTML = abasDoPerfil.map((a, i) => (
      `<a href="${a.rota}"${i === ativo ? ' class="active"' : ''}>` +
      `<i class="bi ${a.icone}"></i> ${a.nome}</a>`
    )).join('');
  }
  return { caminho, ativo };
}

/* 🚨 O CACHE PINTA, O /me MANDA. A sidebar nascia vazia e só aparecia quando o
   /me respondia -- resquício de 27/07, quando a permissão passou a ser
   resolvida no backend. Os links surgiam um instante depois da página, e
   quanto mais lento o /me, mais visível.
 *
 * ⚠️ NÃO DÁ PARA O SERVIDOR ENTREGAR A SIDEBAR PRONTA NO HTML. O token vive no
 * localStorage e vai como header `Bearer`; a requisição da PÁGINA não carrega
 * credencial nenhuma, então o servidor não sabe quem está pedindo. Fazer
 * aquilo exigiria trocar o modelo de autenticação para cookie.
 *
 * 🚨 O CACHE NÃO DECIDE PERMISSÃO -- ele só PINTA. A trava de "esta aba é
 * minha?" continua rodando apenas sobre a resposta do /me, mais abaixo. Se
 * alguém mexer no perfil de um usuário, ele vê o menu antigo pelo tempo do
 * /me e depois ele se corrige; e mesmo enquanto o link está na tela, a rota
 * continua barrando no backend. É cosmético, não é furo.
 *
 * ⚠️ O CACHE É POR USUÁRIO. Guardar o menu de quem saiu e pintá-lo para quem
 * entrou seria mostrar a estrutura do painel de outra pessoa -- por isso o
 * `logout` apaga a chave, junto com o token. */
function abasDoCache() {
  try {
    const cru = localStorage.getItem(CHAVE_ABAS);
    if (!cru) return null;
    const abas = JSON.parse(cru);
    /* Só aceita o formato que `desenharAbas` sabe ler. Cache de uma versão
       antiga do contrato desenharia `undefined` em cada link -- que é
       exatamente a cara do defeito de 17/08. */
    if (!Array.isArray(abas) || !abas.length) return null;
    if (!abas.every((a) => a && a.id && a.nome && a.rota && a.icone)) return null;
    return abas;
  } catch (e) {
    return null;
  }
}

async function montarSidebar(abaAtual) {
  const token = localStorage.getItem('fpsl_painel_token');
  if (!token) { window.location.href = '/painel'; return null; }

  // pinta na hora com o que já se sabia; o /me confirma logo abaixo
  const doCache = abasDoCache();
  if (doCache) desenharAbas(doCache);

  let perfil;
  try {
    const res = await fetch('/painel/api/me', { headers: { Authorization: 'Bearer ' + token } });
    if (res.status === 401) { logout(); return null; }
    perfil = await res.json();
  } catch (e) {
    // rede fora do ar: não desloga (perderia a sessão por um soluço de conexão),
    // só deixa a sidebar vazia e a própria página trata o erro dela.
    return null;
  }

  /* A barra de status desenha usuario, owner e o codigo da tela. Ela NAO
     chama /me por conta propria: o perfil ja esta aqui, e duas chamadas para
     o mesmo dado e a semente de duas verdades. */
  if (window.barraStatusRecebePerfil) window.barraStatusRecebePerfil(perfil);

  const abasDoPerfil = perfil.abas || [];

  // repinta com a verdade do servidor (se o cache já acertou, não muda nada)
  const { caminho } = desenharAbas(abasDoPerfil);

  /* Guarda para a próxima página. Só o que `desenharAbas` consome -- nada de
     jogar o perfil inteiro no localStorage. */
  try {
    localStorage.setItem(CHAVE_ABAS, JSON.stringify(abasDoPerfil.map((a) => ({
      id: a.id, nome: a.nome, rota: a.rota, icone: a.icone,
    }))));
  } catch (e) { /* localStorage cheio ou bloqueado: só perde o atalho */ }

  /* 🚨 A TRAVA LÊ `permissoes`, NÃO `abas`. `abas` é o que vai para o menu e
     exclui as telas `no_menu`; usar essa lista aqui faz uma página fora do
     menu se julgar fora do perfil e redirecionar -- o loop de 17/08. Enquanto
     toda tela fora do menu dividia permissão com uma do menu, os dois
     caminhos davam o mesmo resultado por acaso.
     ⚠️ O `||` mantém compatível com um /me antigo em cache do navegador: sem
     o campo novo, cai no comportamento anterior em vez de trancar todo mundo
     para fora. */
  const permitidas = perfil.permissoes || abasDoPerfil.map((a) => a.id);
  const temAba = permitidas.includes(abaAtual);
  if (!temAba) {
    // sem acesso a esta aba: manda pra primeira que ele tem, ou pro login se
    // o perfil estiver vazio (usuário criado sem nenhuma aba marcada).
    const destino = abasDoPerfil[0];
    /* 🚨 NUNCA REDIRECIONAR PARA A PÁGINA EM QUE JÁ SE ESTÁ. Era o que fechava
       o loop de 17/08: o destino era a própria URL, o navegador recarregava do
       cache e nada aparecia no log do servidor. Se o destino é aqui, o dado
       está errado -- para, e deixa a página aberta em vez de piscar. */
    if (destino && destino.rota.replace(/\/+$/, '') !== caminho) {
      window.location.href = destino.rota;
      return null;
    }
    if (!destino) { window.location.href = '/painel?sem_acesso=1'; return null; }
    console.error('sidebar: aba "' + abaAtual + '" nao veio em /painel/api/me', abasDoPerfil);
    return perfil;
  }
  return perfil;
}

function logout() {
  localStorage.removeItem('fpsl_painel_token');
  localStorage.removeItem('fpsl_painel_admin');
  // 🚨 o menu sai junto: pintar o menu de quem saiu para quem entra depois
  // mostraria a estrutura do painel de outra pessoa
  localStorage.removeItem(CHAVE_ABAS);
  window.location.href = '/painel';
}
