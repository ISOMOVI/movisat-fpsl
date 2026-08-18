"""
Perfis de contrato -> campos fixos de OS no Harmonit (tipoId, problemaId).

IDs vindos de consulta ao vivo em 2026-07-14 (empresaId=98, `/TipoOrdemServico/
ObterListaTipoOrdemServico` e `/Problema/ObterProblemas`). `produtoServicoId`
fica de fora daqui de propósito -- SalvarOrdemServico exige um produto/serviço
válido, mas qual produto depende do que está sendo feito (o teste usado até
agora foi o serviço "MANUTENÇÃO", id 6966) -- por enquanto fica um campo a
escolher na Etapa 3 do painel, não fixo por perfil.

ATENÇÃO -- mapeamentos marcados como "inferido" abaixo são meu melhor palpite
lendo a descrição das listas reais, NÃO foram confirmados por você ainda.
Revisar antes de usar em produção de verdade.

Item obrigatório em toda OS gerada por este painel, independente de perfil ou
contrato -- confirmado por você em 2026-07-14 (serviço "ENTREGA OS" real do
Harmonit, não confundir com "ENTREGA" id 7994, que é outro registro).

Cada perfil define quantas OS nascem por placa (`os_por_placa`):
  1 -> uma OS por placa (Cliente novo, Aditivo, Rescisão, Upgrade)
  2 -> duas OS por placa, uma de retirada + uma de instalação
       (Substituição -- inferido a partir dos pares SUBSTITUIÇÃO/RETIRADA
       e SUBSTITUIÇÃO/INSTALAÇÃO existirem como registros separados;
       Transferência -- confirmado por você, 1 OS por placa por cliente)
"""

ENTREGA_OS_ID = 285367  # serviço "ENTREGA OS" -- fixo em toda OS gerada por este painel

# ── Campos fixos de OS — SPEC financeiro×operacional (2026-07-24) ─────────────
# Validados ao vivo no Harmonit (empresaId=98) e por escrita real (OS nº 16532).
# A partir daqui o "Tipo" da OS é SEMPRE Contrato — a operação (instalação/
# retirada/...) passou a viver no Problema + Produto/Serviço, não mais no tipoId.
# Por isso os `tipo_id*` dos PERFIS abaixo estão SUPERSEDED (mantidos só como
# referência histórica; a geração usa TIPO_CONTRATO_ID).
TIPO_CONTRATO_ID = 2            # "Tipo" = Contrato — em toda OS do painel
SITUACAO_NOVA_ID = 38          # "Nova sollicitação" — situação padrão da OS operacional
SITUACAO_FINANCEIRO_ID = 15746  # situação da OS financeira

# OS financeira (uma por termo) — passam a ser usados a partir da E3
FINANCEIRO_PROBLEMA_ID = 11701          # Problema "FINANCEIRO"
FINANCEIRO_PRODUTO_SERVICO_ID = 606037  # serviço "FINANCEIRO" (cabeçalho da financeira)
FINANCEIRO_TECNICO_ID = 9617            # técnico Karla Alves (só na financeira)

# Prioridade da OS (campo `prioridadeId` do SalvarOrdemServico -- validado ao vivo
# 2026-07-24: 383 gravou "Alta"). Lista: 381 Baixa · 382 Normal · 383 Alta · 384
# Urgente. A operacional usa a escolhida no painel (default Normal); a FINANCEIRA é
# SEMPRE Normal (decisão do usuário 2026-07-24). Sem enviar, o Harmonit assume 382.
PRIORIDADE_NORMAL_ID = 382


PERFIS = {
    "cliente_novo": {
        "label": "Cliente novo",
        "tipo_id": 76,       # "Instalação rastreador" -- inferido
        "problema_id": 7457,  # "CONTRATO NOVO" -- confirmado (nome bate exato)
        "os_por_placa": 1,
        "modelo_origem": "placa",
        "descricao_template": "Instalação: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
    },
    "aditivo": {
        "label": "Aditivo",
        "tipo_id": 76,       # "Instalação rastreador" -- inferido
        "problema_id": 7372,  # "ADITIVO" -- confirmado (nome bate exato)
        "os_por_placa": 1,
        "modelo_origem": "placa",
        "descricao_template": "Instalação: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
    },
    "rescisao": {
        "label": "Rescisão",
        "tipo_id": 57,        # "Retirada" -- inferido
        "problema_id": 7502,  # "RESCISÃO" -- confirmado (nome bate exato)
        "os_por_placa": 1,
        # Decisao do usuario 2026-07-29: na RESCISAO nao se cria OS financeira
        # separada. O item de cobranca (Taxa de Retirada, aviso previo) vai em
        # CADA OS de placa, com a flag `cobrar` preservada -- "e mais seguro
        # assim": a cobranca fica amarrada ao veiculo que a gerou, em vez de
        # num agregado que pode ser fechado sem conferir placa a placa.
        "financeira_embutida": True,
        "modelo_origem": "placa",
        "descricao_template": "Retirada: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
    },
    "substituicao": {
        "label": "Substituição (troca de equipamento)",
        "tipo_id_retirada": 73,     # "Substituição/Retirada" -- inferido
        "tipo_id_instalacao": 72,   # "Substituição/Instalação" -- inferido
        "problema_id_retirada": 7471,    # "SUBSTITUIÇÃO/RETIRADA"
        "problema_id_instalacao": 7472,  # "SUBSTITUIÇÃO/INSTALAÇÃO"
        "os_por_placa": 2,
        # O equipamento e o MESMO nos dois lados -- ele muda de veiculo. Por isso
        # o modelo se le da placa que SAI, tambem na OS de instalacao.
        "modelo_origem": "placa",
        "descricao_template_retirada": "SUBSTITUIÇÃO RETIRADA: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
        "descricao_template_instalacao": "SUBSTITUIÇÃO INSTALAÇÃO: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
    },
    # Transferência de titularidade (E5, SPEC 2026-07-24): são 2 DOCUMENTOS
    # separados (o antigo titular = formato Rescisão; o novo = formato Cliente
    # Novo), cada um subido no seu perfil. Substituem o antigo perfil único
    # `transferencia` (agrupado origem+destino no mesmo upload), que foi removido.
    # Física: o veículo e o equipamento ficam no lugar -- a transferência é
    # administrativa. Cada perfil gera 1 OS agregada (independe do nº de placas).
    "transferencia_novo_titular": {
        "label": "Transferência — Novo titular",
        "problema_id": 7474,                     # TRANSFERÊNCIA DE TITULARIDADE
        "os_por_placa": 1,                        # informativo; geração é 1 OS agregada
        "titularidade": "novo",                   # 1 OS híbrida: financeiro + comodato JUNTOS, sem split
        "situacao_id": SITUACAO_FINANCEIRO_ID,    # a OS híbrida entra como Financeiro
        "tecnico_id": FINANCEIRO_TECNICO_ID,      # técnico Karla (anexado na E3)
        "modelo_origem": "placa",
        "descricao_prefixo": "TRANSFERENCIA TITULARIDADE (NOVO TITULAR)",
    },
    "transferencia_antigo_titular": {
        "label": "Transferência — Antigo titular",
        "problema_id": 7474,
        "os_por_placa": 1,
        "titularidade": "antigo",                 # 1 OS, só comodato, SEM financeira e SEM técnico
        "modelo_origem": "placa",
        "descricao_prefixo": "TRANSFERENCIA TITULARIDADE (ANTIGO TITULAR)",
    },
    "upgrade": {
        "label": "Upgrade de tecnologia",
        "tipo_id": 77,        # "Upgrade" -- confirmado (nome bate exato)
        "problema_id": 7484,  # "UPGRADE" -- confirmado (nome bate exato). Existe também 7612 "UPGRADE 4G" mais específico.
        "os_por_placa": 1,
        # 🚨 UPGRADE NAO E SUBSTITUICAO. Na Substituicao muda o VEICULO (o
        # equipamento vai do veiculo A para o B, os dois reais, os dois no
        # documento) e sao 2 OS. No Upgrade muda o EQUIPAMENTO e o veiculo e o
        # mesmo -- por isso 1 OS so, na placa real.
        #
        # A placa `-UPGRADE` e um RECIPIENTE DE TESTE que o setor de
        # configuracao cria na WESO para vincular o equipamento novo antes de
        # ele ir a campo. NAO entra como veiculo da OS: entra so como chave
        # para descobrir a serie do que entra.
        "placa_teste_sufixo": "-UPGRADE",
        # Confere que o recipiente pertence AO TERMO SUBIDO. Placa que ja
        # passou por upgrade antes tem recipiente VELHO com outro termo; sem
        # esta conferencia pegariamos a serie do equipamento anterior, em
        # silencio. Pedido do usuario em 13/08.
        "placa_teste_descricao": "TERMO {termo}",
        # 🚨 No upgrade o modelo que interessa e o que ENTRA -- por isso o
        # `modelo_origem` aponta para o recipiente de teste, nao para a placa.
        "modelo_origem": "placa_teste",
        # 🚨 ENTROU EM 17/08. O upgrade usava recipiente desde 13/08 e NUNCA o
        # devolvia: a serie ficava `Instalado` numa placa `-UPGRADE` que nao e
        # veiculo nenhum -- fora do estoque e fora de campo ao mesmo tempo. So
        # a `manutencao_troca` liberava, e a diferenca entre as duas era esta
        # linha. Os recipientes do TERMO 8820 (OOM3895 e OOM4131) sao dessa
        # epoca. Mecanismo identico, ja coberto pelas 3 provas de
        # `_liberar_series`: OS criada, serie na descricao, material aceito.
        "liberar_serie": True,
        "descricao_template": "Upgrade: {placa} | {veiculo} | SAIRÁ: {serie} ({modelo_saida}) | ENTRARÁ: {serie_entrada} ({modelo}) | TERMO {termo}",
    },

    # ── Manutencao (2026-08-14) — os dois primeiros perfis SEM TERMO ──────────
    # 🚨 NAO NASCEM DE DOCUMENTO. Os 7 perfis acima vem de um PDF assinado; a
    # manutencao vem de um chamado. Nao ha extracao, nao ha numero de termo e
    # nao ha item de contrato -- o que existe e uma placa e um defeito.
    #
    # 🚨 TIPO E PROBLEMA VAO POR NOME, NAO POR ID. Medido em 14/08: das 14 OS
    # de manutencao que a casa ja abriu na mao, 7 usam `tipo = 55`, que NAO
    # ESTA MAIS na lista do Harmonit. ID fixo em codigo apodrece em silencio;
    # o nome e resolvido contra a lista viva na hora de gerar (ver
    # `resolver_tipo_e_problema` em os_router.py). Os `*_id` abaixo sao so o
    # ultimo recurso para quando a lista nao responder -- transiente de rede
    # nao pode impedir a geracao, mas nome que sumiu tem de impedir.
    #
    # 🚨 MANUTENCAO NAO FLEGA COBRAR NEM COMODATO EM NENHUM ITEM (decisao do
    # usuario, 14/08). O equipamento aparece como material para o tecnico
    # saber com o que vai lidar -- nao e patrimonio saindo nem cobranca
    # entrando. Por isso `sem_flags` e `sem_financeira` andam juntos.
    "manutencao_local": {
        "label": "Manutenção no local",
        "tipo_nome": "Solicitação de Cliente",
        "tipo_id": 1783,
        "problema_nome": "MANUTENÇÃO",
        "problema_id": 7384,
        "produto_servico_nome": "MANUTENÇÃO",
        "os_por_placa": 1,
        "sem_termo": True,
        "sem_flags": True,
        "sem_financeira": True,
        # As 14 OS de manutencao abertas na mao terminam com `O.S: nnnnn`.
        # Custa uma SEGUNDA chamada (criar, ler o numero, regravar) -- por isso
        # os perfis de contrato nao fazem, decisao de 14/07. Aqui o usuario
        # pediu igual a mao, aceitando a demora com a caixa de progresso.
        "numero_na_descricao": True,
        # Sem recipiente: o equipamento que interessa e o que JA ESTA no
        # veiculo, entao o modelo se le da propria placa.
        "modelo_origem": "placa",
        "descricao_template": "MANUTENÇÃO NO LOCAL: {placa} | {veiculo} | {serie} ({modelo})",
    },
    "manutencao_troca": {
        "label": "Manutenção com troca",
        "tipo_nome": "Solicitação de Cliente",
        "tipo_id": 1783,
        "problema_nome": "MANUTENÇÃO",
        "problema_id": 7384,
        "produto_servico_nome": "MANUTENÇÃO",
        "os_por_placa": 1,
        "sem_termo": True,
        "sem_flags": True,
        "sem_financeira": True,
        # As 14 OS de manutencao abertas na mao terminam com `O.S: nnnnn`.
        # Custa uma SEGUNDA chamada (criar, ler o numero, regravar) -- por isso
        # os perfis de contrato nao fazem, decisao de 14/07. Aqui o usuario
        # pediu igual a mao, aceitando a demora com a caixa de progresso.
        "numero_na_descricao": True,
        # Mesmo mecanismo do Upgrade, com outro sufixo: o setor de
        # configuracao cria `<PLACA>-MANUT` na WESO e vincula nela o
        # equipamento novo. Medido em 14/08: 5 recipientes existem, todos com
        # a descricao `MANUTENCAO`.
        "placa_teste_sufixo": "-MANUT",
        # ⚠️ AQUI A TRAVA E MAIS FRACA QUE A DO UPGRADE, e de proposito. O
        # upgrade compara com `TERMO {termo}`, que identifica a rodada; a
        # manutencao nao tem termo e todo recipiente se chama `MANUTENCAO`.
        # Entao isto prova que e UM recipiente de manutencao, nao que e o
        # DESTA manutencao. O que fecha o resto e liberar a serie no fim
        # (`liberar_serie`): recipiente usado deixa de existir.
        "placa_teste_descricao": "MANUTENCAO",
        "modelo_origem": "placa_teste",
        # Depois da OS criada com serie e material, devolve o equipamento ao
        # estoque e apaga o recipiente -- nessa ordem.
        "liberar_serie": True,
        "descricao_template": "MANUTENÇÃO COM TROCA: {placa} | {veiculo} | SAIRÁ: {serie} ({modelo_saida}) | ENTRARÁ: {serie_entrada} ({modelo})",
    },
}
