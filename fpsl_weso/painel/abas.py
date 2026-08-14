"""Registro central das abas do painel — fonte única de verdade.

Antes de 2026-07-27 não havia permissão por aba: as 4 abas operacionais eram
abertas a qualquer usuário logado, e o único controle era o booleano `admin`
(que só protegia Usuários e Configurações). A sidebar "escondia" links no JS,
mas as páginas em si não eram verificadas.

Agora cada aba tem id próprio, o usuário guarda a lista de ids que pode ver
(`painel_usuarios.abas`) e o backend exige a aba no router correspondente.

Regras que não mudam:
  - `somente_owner=True`  -> nunca aparece no modal de perfil; só o owner acessa.
  - `sensivel=True`       -> aparece no modal, mas com aviso na UI.
  - o owner enxerga tudo, independente do que estiver gravado em `abas`.
"""

ABAS = [
    {
        "id": "gerar_os",
        "nome": "Gerar OS",
        "rota": "/painel/gerar-os",
        "icone": "bi-file-earmark-plus",
        "descricao": "Sobe o termo, extrai os dados e cria as OS no Harmonit.",
        "sensivel": False,
        "somente_owner": False,
    },
    # 🚨 A ABA `placas` FOI REMOVIDA EM 2026-08-14, a pedido do usuário: "não
    # tem motivo para existir, nunca pedi ela". Ela era permissão que não
    # protegia nada -- nenhuma rota a exigia, porque o `placas_router` sempre
    # pediu `gerar_os`. Na prática: quem recebia só "Placas" via a aba e não
    # conseguia usar; quem tinha "Gerar OS" criava placa na WESO sem ter
    # recebido "Placas". Aba que ninguém exige é permissão de mentira.
    #
    # ⚠️ A TELA `/painel/placas` e o `placas_router` CONTINUAM DE PÉ, agora sem
    # link na barra lateral. Quem tem `gerar_os` alcança pela URL. Não apaguei
    # por conta própria -- apagar tela é outra decisão.
    {
        "id": "vinculos",
        "nome": "Vínculos",
        "rota": "/painel/vinculos",
        "icone": "bi-link-45deg",
        "descricao": "De-para entre item do contrato e produto/serviço do Harmonit.",
        "sensivel": False,
        "somente_owner": False,
    },
    {
        "id": "oficinas",
        "nome": "Oficinas",
        "rota": "/painel/oficinas",
        "icone": "bi-tools",
        "descricao": "Histórico de sincronização de oficina para a WESO.",
        "sensivel": False,
        "somente_owner": False,
    },
    {
        "id": "os_historico",
        "nome": "Histórico de OS",
        "rota": "/painel/os-historico",
        "icone": "bi-clock-history",
        "descricao": "Varredura de OS por número e os eventos de oficina encontrados.",
        "sensivel": False,
        "somente_owner": False,
    },
    {
        "id": "harmonit_historico",
        "nome": "Serviços Harmonit",
        "rota": "/painel/harmonit-historico",
        "icone": "bi-activity",
        "descricao": "Audita as chamadas aos serviços do Harmonit: tempo, erro e resposta vazia.",
        "sensivel": False,
        "somente_owner": False,
    },
    {
        "id": "config",
        "nome": "Configurações",
        "rota": "/painel/config",
        "icone": "bi-gear",
        "descricao": "Interruptores do sistema, incluindo o que libera escrita na WESO.",
        "sensivel": True,
        # decisão do usuário em 2026-07-27: exclusiva do owner. É onde vive o
        # toggle `oficina_registro_ativo` -- quem tem essa aba pode ligar a
        # escrita real na WESO, e isso não se delega.
        "somente_owner": True,
    },
    {
        "id": "usuarios",
        "nome": "Usuários",
        "rota": "/painel/usuarios",
        "icone": "bi-people",
        "descricao": "Criação e perfil de acesso das contas do painel.",
        "sensivel": True,
        "somente_owner": True,
    },
]

IDS_VALIDOS = {a["id"] for a in ABAS}
IDS_CONCEDIVEIS = {a["id"] for a in ABAS if not a["somente_owner"]}


def normalizar(ids) -> list[str]:
    """Filtra o que veio da UI: só ids que existem e que podem ser concedidos.

    Silenciosamente descarta desconhecido/`somente_owner` em vez de estourar --
    a lista chega de um formulário, e um id a mais não deve derrubar o cadastro.
    Preserva a ordem de ABAS pra sidebar sair sempre na mesma sequência.
    """
    if not ids:
        return []
    pedidos = {str(i) for i in ids}
    return [a["id"] for a in ABAS if a["id"] in pedidos and a["id"] in IDS_CONCEDIVEIS]


def para_frontend() -> list[dict]:
    """As abas concedíveis, no formato que o modal de perfil consome."""
    return [
        {
            "id": a["id"],
            "nome": a["nome"],
            "icone": a["icone"],
            "descricao": a["descricao"],
            "sensivel": a["sensivel"],
        }
        for a in ABAS
        if not a["somente_owner"]
    ]


def do_usuario(usuario: dict) -> list[dict]:
    """As abas que ESTE usuário vê na sidebar. Owner vê tudo."""
    if usuario.get("owner"):
        permitidas = {a["id"] for a in ABAS}
    else:
        permitidas = set(usuario.get("abas") or [])
    return [
        {"id": a["id"], "nome": a["nome"], "rota": a["rota"], "icone": a["icone"]}
        for a in ABAS
        if a["id"] in permitidas
    ]


def pode_acessar(usuario: dict, aba_id: str) -> bool:
    if usuario.get("owner"):
        return True
    if aba_id not in IDS_CONCEDIVEIS:
        return False
    return aba_id in set(usuario.get("abas") or [])
