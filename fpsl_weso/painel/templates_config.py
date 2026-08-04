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
        "descricao_template": "Instalação: {placa} | {veiculo} | {serie} | TERMO {termo}",
    },
    "aditivo": {
        "label": "Aditivo",
        "tipo_id": 76,       # "Instalação rastreador" -- inferido
        "problema_id": 7372,  # "ADITIVO" -- confirmado (nome bate exato)
        "os_por_placa": 1,
        "descricao_template": "Instalação: {placa} | {veiculo} | {serie} | TERMO {termo}",
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
        "descricao_template": "Retirada: {placa} | {veiculo} | {serie} | TERMO {termo}",
    },
    "substituicao": {
        "label": "Substituição (troca de equipamento)",
        "tipo_id_retirada": 73,     # "Substituição/Retirada" -- inferido
        "tipo_id_instalacao": 72,   # "Substituição/Instalação" -- inferido
        "problema_id_retirada": 7471,    # "SUBSTITUIÇÃO/RETIRADA"
        "problema_id_instalacao": 7472,  # "SUBSTITUIÇÃO/INSTALAÇÃO"
        "os_por_placa": 2,
        "descricao_template_retirada": "SUBSTITUIÇÃO RETIRADA: {placa} | {veiculo} | {serie} | TERMO {termo}",
        "descricao_template_instalacao": "SUBSTITUIÇÃO INSTALAÇÃO: {placa} | {veiculo} | {serie} | TERMO {termo}",
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
        "descricao_prefixo": "TRANSFERENCIA TITULARIDADE (NOVO TITULAR)",
    },
    "transferencia_antigo_titular": {
        "label": "Transferência — Antigo titular",
        "problema_id": 7474,
        "os_por_placa": 1,
        "titularidade": "antigo",                 # 1 OS, só comodato, SEM financeira e SEM técnico
        "descricao_prefixo": "TRANSFERENCIA TITULARIDADE (ANTIGO TITULAR)",
    },
    "upgrade": {
        "label": "Upgrade de tecnologia",
        "tipo_id": 77,        # "Upgrade" -- confirmado (nome bate exato)
        "problema_id": 7484,  # "UPGRADE" -- confirmado (nome bate exato). Existe também 7612 "UPGRADE 4G" mais específico.
        "os_por_placa": 1,
        "descricao_template": "Upgrade: {placa} | {veiculo} | {serie} | TERMO {termo}",
    },
}
