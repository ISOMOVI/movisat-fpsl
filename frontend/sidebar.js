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

  const nav = document.getElementById('sidebarNav');
  if (nav) {
    nav.innerHTML = (perfil.abas || []).map((a) => (
      `<a href="${a.rota}"${a.id === abaAtual ? ' class="active"' : ''}>` +
      `<i class="bi ${a.icone}"></i> ${a.nome}</a>`
    )).join('');
  }

  const temAba = (perfil.abas || []).some((a) => a.id === abaAtual);
  if (!temAba) {
    // sem acesso a esta aba: manda pra primeira que ele tem, ou pro login se
    // o perfil estiver vazio (usuário criado sem nenhuma aba marcada).
    const destino = (perfil.abas || [])[0];
    window.location.href = destino ? destino.rota : '/painel?sem_acesso=1';
    return null;
  }
  return perfil;
}

function logout() {
  localStorage.removeItem('fpsl_painel_token');
  localStorage.removeItem('fpsl_painel_admin');
  window.location.href = '/painel';
}
