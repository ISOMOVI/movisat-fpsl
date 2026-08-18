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
async function montarSidebar(abaAtual) {
  const token = localStorage.getItem('fpsl_painel_token');
  if (!token) { window.location.href = '/painel'; return null; }

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

  const temAba = abasDoPerfil.some((a) => a.id === abaAtual);
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
  window.location.href = '/painel';
}
