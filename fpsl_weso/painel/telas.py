"""Registro central das telas do FPSL — fonte única de verdade.

Espelha o contrato do `movizap/telas.py`, em produção desde 12/08. Cada tela tem
um CÓDIGO IMUTÁVEL (`OSG_1.1`, `CAD_1.2`...), e é ele que aparece na conferência
e no log de auditoria.

Regras que não mudam:
  - tela que não está aqui NÃO EXISTE: rota sem código registrado não sobe;
  - o código é imutável -- título, rota e arquivo podem mudar, código não;
  - código aposentado NUNCA é reaproveitado (faria o log antigo mentir);
  - o owner enxerga tudo, independente do que estiver gravado;
  - conta nova nasce sem nenhuma tela: falha fechado.

🚨 `permissao` É O QUE JÁ ESTÁ GRAVADO EM `painel_usuarios.abas`. Os ids não
mudaram na adoção do registro (17/08) de propósito: mudar exigiria migrar a
coluna de todas as contas e reescrever as 25 chamadas de `requer_aba`, e
nenhuma das duas coisas melhora nada. O que o registro acrescenta é o CÓDIGO,
que a permissão não tinha.

Ver `docs/fpsl/27_Registro_Telas.md`.
"""

# `fase` documenta quando a tela entra. Só as de fase 1 sobem; as demais ficam
# registradas para o código já estar reservado e nunca ser reusado.
TELAS = [
    # ---- CAD: cadastro de placas ----
    # 🚨 PRIMEIRA DA LISTA DE PROPÓSITO. É a ordem do trabalho real: o termo
    # assinado vira placa na WESO e no Harmonit, e só depois vira OS. A sidebar
    # segue esta ordem, e o login manda para a primeira tela DO PERFIL.
    {
        "codigo": "CAD_1.1",
        "titulo": "Cadastro de Placas",
        "rota": "/painel/cadastro-placas",
        "icone": "bi-card-list",
        "descricao": "Cria na WESO e no Harmonit as placas do termo e os recipientes.",
        "permissao": "cadastro_placas",
        "fase": 1,
    },
    {
        # ⚠️ MESMA PERMISSÃO da CAD_1.1, de propósito. Quem cadastra precisa ver
        # o que cadastrou; uma permissão separada para "ver o que eu mesmo fiz"
        # seria burocracia sem dono. Fica fora do menu, alcançada por link.
        "codigo": "CAD_1.2",
        "titulo": "Histórico de Cadastros",
        "rota": "/painel/cadastro-placas/historico",
        "icone": "bi-clock-history",
        "descricao": "O que cada rodada cadastrou, em qual sistema, e o que falhou.",
        "permissao": "cadastro_placas",
        "fase": 1,
        "no_menu": True,
    },
    # ---- OSG: geração de OS ----
    {
        "codigo": "OSG_1.1",
        "titulo": "Gerar OS",
        "rota": "/painel/gerar-os",
        "icone": "bi-file-earmark-plus",
        "descricao": "Sobe o termo, extrai os dados e cria as OS no Harmonit.",
        "permissao": "gerar_os",
        "fase": 1,
    },
    {
        # Vínculos é submódulo do OSG e não módulo próprio: ele existe PARA a
        # geração de OS -- é o de-para entre o texto do contrato e o produto do
        # Harmonit. Sozinho não serve a nada.
        "codigo": "OSG_2.1",
        "titulo": "Vínculos",
        "rota": "/painel/vinculos",
        "icone": "bi-link-45deg",
        "descricao": "De-para entre item do contrato e produto/serviço do Harmonit.",
        "permissao": "vinculos",
        "fase": 1,
    },
    # ---- HST: históricos e auditoria ----
    {
        "codigo": "HST_1.1",
        "titulo": "Histórico de OS",
        "rota": "/painel/os-historico",
        "icone": "bi-clock-history",
        "descricao": "Varredura de OS por número e os eventos de oficina encontrados.",
        "permissao": "os_historico",
        "fase": 1,
    },
    {
        "codigo": "HST_2.1",
        "titulo": "Serviços Harmonit",
        "rota": "/painel/harmonit-historico",
        "icone": "bi-activity",
        "descricao": "Audita as chamadas ao Harmonit: tempo, erro e resposta vazia.",
        "permissao": "harmonit_historico",
        "fase": 1,
    },
    # ---- CFG: configuração ----
    {
        "codigo": "CFG_1.1",
        "titulo": "Configurações",
        "rota": "/painel/config",
        "icone": "bi-gear",
        "descricao": "Interruptores do sistema, incluindo o que libera escrita na WESO.",
        "permissao": "config",
        "fase": 1,
    },
    {
        "codigo": "CFG_2.1",
        "titulo": "Usuários",
        "rota": "/painel/usuarios",
        "icone": "bi-people",
        "descricao": "Contas do painel, e-mail de vínculo e o que cada uma enxerga.",
        "permissao": "usuarios",
        "fase": 1,
    },
    {
        # ⚠️ MESMO CÓDIGO DA CFG_9.1 DO MOVIZAP, e mesma função. Dois sistemas,
        # um vocabulário: quem entende o registro de um entende o do outro.
        "codigo": "CFG_9.1",
        "titulo": "Registro de telas",
        "rota": "/painel/config/telas",
        "icone": "bi-list-check",
        "descricao": "Este registro, para conferência e auditoria.",
        "permissao": "config",
        "fase": 1,
    },
    # ---- DMD: painel rápido, PÚBLICO ----
    # 🚨 SEM LOGIN E SEM PERMISSÃO, por decisão do usuário (05/08): quadro
    # compartilhado por link, com token na URL. Estão aqui porque o registro
    # promete ser fonte ÚNICA -- tela de fora do registro faria a promessa
    # mentir --, mas `permissao: None` as mantém fora da navegação e da trava.
    #
    # ⚠️ AS DUAS SÃO O MESMO MOTOR, vistas diferentes: `modo` escolhe. O código
    # separa porque são duas telas para quem olha, e é isso que o log registra.
    {
        "codigo": "DMD_1.1",
        "titulo": "Demandas — esteira",
        "rota": "/demandas/{token}",
        "icone": "bi-kanban",
        "descricao": "Quadro compartilhado por link, vista esteira. Sem login.",
        "permissao": None,
        "fase": 1,
        "no_menu": True,
    },
    {
        "codigo": "DMD_1.2",
        "titulo": "Demandas — planilha",
        "rota": "/demandas/{token}",
        "icone": "bi-table",
        "descricao": "O mesmo quadro na vista planilha. Sem login.",
        "permissao": None,
        "fase": 1,
        "no_menu": True,
    },
    # ---- reservados: código já ocupado, tela ainda não existe ----
    {
        # A comparação Harmonit × WESO que o cadastro de placas tornou
        # necessária: quais veículos estão só num lado, e quais divergem na
        # grafia. Proposta em 17/08, sem data.
        "codigo": "HST_3.1",
        "titulo": "Aderência",
        "rota": "/painel/aderencia",
        "icone": "bi-arrow-left-right",
        "descricao": "O que existe só no Harmonit, só na WESO, e o que diverge.",
        "permissao": "os_historico",
        "fase": 2,
    },
    {
        "codigo": "REL_1.1",
        "titulo": "Relatórios",
        "rota": "/painel/relatorios",
        "icone": "bi-file-earmark-bar-graph",
        "descricao": "Volume de OS, tempo de geração, desfecho.",
        "permissao": "config",
        "fase": 3,
    },
]

FASE_ATUAL = 1

# 🚨 CÓDIGO APOSENTADO NUNCA VOLTA. Esta lista existe para ninguém
# "redescobrir" um número livre daqui a três meses e fazer o log antigo mentir.
#
#   PLC_1.1  seria a tela de placas de julho -- cadastro avulso, desligado de
#            qualquer fluxo. Morreu em 14/08 (`cf16837`) por ser permissão que
#            não protegia nada: as rotas dela exigiam `gerar_os`. Nunca teve
#            código, e nunca terá. O Cadastro de Placas é CAD_1.1, outra coisa:
#            nasce do termo, tem id próprio e as rotas exigem esse id.
#
#   OFC_1.1  seria a tela de sincronização Oficina -> WESO. Removida em 17/08
#            com o fluxo inteiro: a tabela tinha ZERO linhas em toda a vida do
#            sistema e o endpoint nunca foi chamado. A documentação dela fica,
#            porque serve para rescisão.
CODIGOS_APOSENTADOS = {"PLC_1.1", "OFC_1.1"}

CODIGOS_VALIDOS = {t["codigo"] for t in TELAS}
# `None` (as públicas) não é permissão e não entra.
PERMISSOES_VALIDAS = {t["permissao"] for t in TELAS if t["permissao"]}

# Permissões que o owner concede a outra conta. As de owner ficam de fora --
# quem tem essas telas liga a escrita real na WESO e cria contas, e isso não
# se delega (decisão do usuário, 27/07).
PERMISSOES_SO_OWNER = {"config", "usuarios"}
PERMISSOES_CONCEDIVEIS = PERMISSOES_VALIDAS - PERMISSOES_SO_OWNER


class CodigoDeTelaInvalido(Exception):
    """Levantada quando uma rota referencia um código que não existe.

    É erro de programação, não de uso: por isso estoura em vez de degradar.
    """


def por_codigo(codigo: str) -> dict:
    for t in TELAS:
        if t["codigo"] == codigo:
            return t
    raise CodigoDeTelaInvalido(
        f"{codigo!r} não está no registro. Tela sem código registrado não sobe -- "
        f"ver docs/fpsl/27_Registro_Telas.md"
    )


def ativas() -> list[dict]:
    """Só as telas da fase atual. As reservadas existem, mas não sobem."""
    return [t for t in TELAS if t["fase"] <= FASE_ATUAL]


def pode_acessar(usuario: dict, codigo: str) -> bool:
    if usuario.get("owner"):
        return True
    tela = por_codigo(codigo)
    if tela["permissao"] is None:
        return True                      # pública, por token na URL
    if tela["permissao"] in PERMISSOES_SO_OWNER:
        return False
    return tela["permissao"] in set(usuario.get("abas") or [])


def do_usuario(usuario: dict) -> list[dict]:
    """As telas que ESTE usuário vê no MENU. Owner vê tudo que está ativo.

    ⚠️ `no_menu` sai daqui e continua acessível: são telas alcançadas por link
    (o histórico do cadastro) ou por token (as de demandas). Registro completo,
    menu enxuto.
    """
    return [
        {
            "codigo": t["codigo"],
            "titulo": t["titulo"],
            "rota": t["rota"],
            "icone": t["icone"],
            # 🚨 `id` E `nome` NAO SAO DUPLICATA -- SAO O CONTRATO DO sidebar.js.
            # Ele compara `a.id` com a PERMISSAO que a pagina passa em
            # `montarSidebar('cadastro_placas')` e escreve `a.nome` no link.
            # Em 17/08 este dicionario passou a sair so com `codigo`/`titulo`:
            # `a.id` virou undefined, nenhuma pagina se reconheceu e o painel
            # entrou em loop de redirecionamento. Nao remover sem trocar as 9
            # paginas -- `tests/teste_contrato_sidebar.py` reprova se sumir.
            "id": t["permissao"],
            "nome": t["titulo"],
        }
        for t in ativas()
        if not t.get("no_menu") and t["permissao"] is not None
        and pode_acessar(usuario, t["codigo"])
    ]


def para_frontend() -> list[dict]:
    """O catálogo que o modal de perfil consome: uma linha por PERMISSÃO
    concedível, com as telas que ela destrava.

    🚨 POR PERMISSÃO, NÃO POR TELA. O que se concede é a permissão; mostrar
    tela a tela sugeriria que dá para dar o Histórico de Cadastros sem dar o
    Cadastro de Placas, e não dá -- é a mesma permissão.
    """
    fora = []
    for p in sorted(PERMISSOES_CONCEDIVEIS):
        telas = [t for t in ativas() if t["permissao"] == p]
        if not telas:
            continue
        fora.append({
            "id": p,
            "nome": telas[0]["titulo"],
            "icone": telas[0]["icone"],
            "descricao": telas[0]["descricao"],
            "codigos": [t["codigo"] for t in telas],
            "sensivel": False,
        })
    return fora


def normalizar(ids) -> list[str]:
    """Filtra o que veio da UI: só permissões que existem e são concedíveis.

    Silenciosamente descarta desconhecido/só-owner em vez de estourar -- a
    lista chega de um formulário, e um id a mais não deve derrubar o cadastro.
    Preserva a ordem de TELAS para a sidebar sair sempre na mesma sequência.
    """
    if not ids:
        return []
    pedidos = {str(i) for i in ids}
    vistos, fora = set(), []
    for t in TELAS:
        p = t["permissao"]
        if p and p in pedidos and p in PERMISSOES_CONCEDIVEIS and p not in vistos:
            vistos.add(p)
            fora.append(p)
    return fora
