"""Perfis da aba OPERAÇÕES (`OPR_1.1`) — os 11 tipos de operação.

🚨 ESTE ARQUIVO É UM CLONE DE `templates_config.py`, E É DE PROPÓSITO.

A aba Operações substitui Cadastro de Placas e Gerar OS, e as duas velhas vão
ser apagadas. O critério de clonar está em `docs/fpsl/28_Operacoes.md`:

    Se a regra muda entre a aba velha e a nova, CLONA.
    Se é infraestrutura sem regra, REUSA.

Os perfis carregam regra e ela mudou: 9 viraram 11, dois foram renomeados e
seis regras de montagem de OS são outras. Importar o `templates_config` aqui
obrigaria a escolher entre quebrar as abas velhas e travar esta. Quando elas
saírem (F7), este arquivo já é autossuficiente e nada some junto.

⚠️ NÃO IMPORTE `templates_config` AQUI. Nem "só uma constante".

Os ids vieram de consulta ao vivo ao Harmonit; os novos foram conferidos em
2026-08-19 e a data está ao lado de cada um. Id fixo em código apodrece em
silêncio -- foi assim que 7 das 14 OS de manutenção ficaram com `tipo = 55`,
que não existe mais. Por isso Tipo e Problema, onde há nome confiável, são
resolvidos contra a lista viva; o id fica como último recurso para quando a
lista não responder.
"""

# ── Itens fixos ───────────────────────────────────────────────────────────────
ENTREGA_OS_ID = 285367  # serviço "ENTREGA OS" -- fixo em toda OS gerada aqui

# ── Campos fixos de OS ────────────────────────────────────────────────────────
# O "Tipo" da OS é SEMPRE Contrato nos perfis de contrato: a operação vive no
# Problema + Produto/Serviço, não no tipoId. A manutenção foge disto e resolve
# pelo nome.
TIPO_CONTRATO_ID = 2
SITUACAO_NOVA_ID = 38           # "Nova sollicitação" -- OS operacional
SITUACAO_FINANCEIRO_ID = 15746  # OS financeira

FINANCEIRO_PROBLEMA_ID = 11701          # Problema "FINANCEIRO"
FINANCEIRO_PRODUTO_SERVICO_ID = 606037  # serviço "FINANCEIRO" (cabeçalho)
FINANCEIRO_TECNICO_ID = 9617            # técnico Karla Alves (só na financeira)

# 381 Baixa · 382 Normal · 383 Alta · 384 Urgente.
# A operacional usa a escolhida na tela; a FINANCEIRA é SEMPRE Normal.
PRIORIDADE_NORMAL_ID = 382

# ── Ids dos perfis novos (conferidos ao vivo em 2026-08-19) ──────────────────
RESSARCIMENTO_SERVICO_ID = 48028   # serviço "RESSARCIMENTO" -- nome bate exato
RESSARCIMENTO_PROBLEMA_ID = 7524   # problema "RESSARCIMENTO" -- nome bate exato

# 🚨 PENDENTE DO USUÁRIO, E FALHA ALTO DE PROPÓSITO.
#
# O serviço pedido foi "substituição em locais diferentes cliente". Ele NÃO
# existe com esse nome no Harmonit, e o mais próximo tem DOIS registros com o
# nome IDÊNTICO (medido em 19/08):
#
#      6967  SUBSTITUIÇÃO DIA, HORÁRIO OU LOCAL DIFERENTE - CLIENTE
#     54845  SUBSTITUIÇÃO DIA, HORÁRIO OU LOCAL DIFERENTE - CLIENTE
#     12808  SUBSTITUIÇÃO MESMO DIA, HORÁRIO OU LOCAL - CLIENTE
#     12807  SUBSTITUIÇÃO  DIA, LOCAL E HORÁRIO DIFERENTE - CAMPINAS
#      7276  SUBSTITUIÇÃO MESMO DIA, LOCAL E HORÁRIO - CAMPINAS
#
# A regra da casa é resolver por NOME, não por id -- mas aqui o nome não
# decide: `_achar_por_nome` pegaria o primeiro da lista, no chute.
#
# ✅ RESOLVIDO PELO USUÁRIO EM 21/08: é o `6967`, com valor fixo de 299,90 e
# `cobrar` marcado. A tela não pergunta nada. A alternativa apresentada -- o
# operador marcar mesmo local × local diferente e o valor vir do termo, que já
# traz os dois (199,90 e 299,90) -- foi recusada: ele preferiu o caminho
# automático.
SUBSTITUICAO_LOCAL_DIFERENTE_ID = 6967
SUBSTITUICAO_LOCAL_DIFERENTE_VALOR = 299.90

# 🚨 A GUARDA QUE ACOMPANHA A ESCOLHA, E QUE NÃO A CONTRADIZ. Id fixo em código
# apodrece EM SILÊNCIO: foi assim que 7 das 14 OS de manutenção ficaram com
# `tipo = 55`, que não existe mais na lista do Harmonit e ninguém percebeu. A
# decisão de fixar é do usuário; fazer o apodrecimento APARECER é trabalho meu.
#
# Quem chama isto é a geração, com a lista viva do catálogo em mãos. Se o 6967
# tiver sumido, a OS financeira PARA com recado, em vez de sair apontando para
# um serviço que não existe -- lacuna visível é melhor que cobrança errada.
def conferir_servico_de_substituicao(servicos_vivos) -> str | None:
    """Devolve o recado do problema, ou None se está tudo certo.

    `servicos_vivos` é a lista que o Harmonit devolve; item com `id`.
    Lista vazia ou ausente NÃO acusa: não saber é diferente de saber que sumiu,
    e aviso falso treina a equipe a ignorar aviso.
    """
    if not servicos_vivos:
        return None
    ids = {str(s.get("id")) for s in servicos_vivos if isinstance(s, dict)}
    if str(SUBSTITUICAO_LOCAL_DIFERENTE_ID) in ids:
        return None
    return (f"O serviço {SUBSTITUICAO_LOCAL_DIFERENTE_ID} (substituição em "
            "local diferente) não está mais no catálogo do Harmonit. A OS "
            "financeira da substituição não sai até alguém escolher o "
            "substituto — o id está fixado em `operacoes_config.py`.")


PERFIS = {
    # ── 1 ─────────────────────────────────────────────────────────────────────
    # ⚠️ RENOMEADO (usuário, 19/08). Era "Cliente novo".
    #
    # 🚨 POR QUE TESTE DE TECNOLOGIA CABE AQUI, e não vira perfil próprio: o
    # perfil é definido pelo que a OS FAZ, não pelo motivo comercial. Um teste
    # faz exatamente isto -- placa nova, instalação, comodato, 1 OS por placa.
    # Perfil separado duplicaria template e ids idênticos.
    #
    # E só ficou possível agora: antes da regra 4 nova, a financeira de valor
    # zero ESCONDIA os itens, e o teste saía com uma financeira vazia. Com os
    # itens aparecendo e o `cobrar` desmarcado, o mesmo perfil serve contrato
    # pago e teste gratuito -- quem separa é o VALOR, não uma flag.
    "contrato_novo": {
        "label": "Contrato novo ou teste de tecnologia",
        "tipo_id": 76,
        "problema_id": 7457,   # "CONTRATO NOVO" -- nome bate exato
        "os_por_placa": 1,
        "etapa_placas": "cria",
        "modelo_origem": "placa",
        "descricao_template": "Instalação: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
    },

    # ── 2 ─────────────────────────────────────────────────────────────────────
    # ⚠️ RENOMEADO (usuário, 19/08). Era "Aditivo". Mesma razão do perfil 1.
    "aditivo": {
        "label": "Aditivo ou teste upgrade",
        "tipo_id": 76,
        "problema_id": 7372,   # "ADITIVO" -- nome bate exato
        "os_por_placa": 1,
        "etapa_placas": "cria",
        "modelo_origem": "placa",
        "descricao_template": "Instalação: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
    },

    # ── 3 ─────────────────────────────────────────────────────────────────────
    # 🚨 A RESCISÃO TEM OS OPERACIONAL **E** OS FINANCEIRA (decisão do usuário,
    # 21/08: "rescisao tera OS OP e FIN, decisão nova do pessoal"). É a regra 3
    # da spec 28, e ela REVERTE a decisão de 29/07 -- com autorização, não por
    # engano.
    #
    # ⚠️ O QUE A DECISÃO DE 29/07 PROTEGIA, E QUE VOLTA A SER RISCO. Naquela
    # data o item de cobrança (Taxa de Retirada, aviso prévio) ia embutido em
    # CADA OS de placa, com o `cobrar` preservado, "porque é mais seguro
    # assim": a cobrança ficava amarrada ao veículo que a gerou, em vez de num
    # agregado que pode ser fechado sem conferir placa a placa. Agora ela é uma
    # OS só por termo, e conferir placa a placa passa a depender da etapa 3 --
    # que a aba nova tem e a tela velha não tinha. Foi essa a mudança de
    # contexto que tornou a reversão possível.
    #
    # Reavaliar se: aparecer financeira de rescisão fechada sem que as
    # operacionais do mesmo termo tenham sido conferidas.
    "rescisao": {
        "label": "Rescisão",
        "tipo_id": 57,
        "problema_id": 7502,   # "RESCISÃO" -- nome bate exato
        "os_por_placa": 1,
        "etapa_placas": "confere",
        "desativa_apos_oficina": True,   # rotina: devolve ao estoque
        "modelo_origem": "placa",
        "descricao_template": "Retirada: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
    },

    # ── 4 ─────────────────────────────────────────────────────────────────────
    # 🚨 SUBSTITUIÇÃO TROCA O VEÍCULO. O equipamento é o MESMO e vai do veículo
    # A para o B -- os dois reais, os dois no documento. Por isso 2 OS e por
    # isso o modelo se lê da placa que SAI, também na OS de instalação.
    # (O Upgrade é o contrário: troca o EQUIPAMENTO, veículo é o mesmo.)
    #
    # 🆕 GANHA FINANCEIRA (usuário, 19/08): serviço de local diferente, valor
    # fixo, `cobrar` MARCADO -- tem valor, flega, sem exceção à regra 2.
    #
    # 🆕 `placa_entrada` passa a ser CADASTRADA nos dois sistemas. Hoje ela só
    # existia na geração de OS e nunca nascia em lugar nenhum.
    "substituicao": {
        "label": "Substituição (troca de equipamento)",
        "tipo_id_retirada": 73,
        "tipo_id_instalacao": 72,
        "problema_id_retirada": 7471,    # "SUBSTITUIÇÃO/RETIRADA"
        "problema_id_instalacao": 7472,  # "SUBSTITUIÇÃO/INSTALAÇÃO"
        "os_por_placa": 2,
        "etapa_placas": "cria_entrada",
        "modelo_origem": "placa",
        "financeira_servico_id": SUBSTITUICAO_LOCAL_DIFERENTE_ID,
        "financeira_servico_valor": SUBSTITUICAO_LOCAL_DIFERENTE_VALOR,
        "financeira_servico_cobrar": True,
        # rotina: solta do veículo antigo, confere Estoque relendo, vincula na
        # placa_entrada. É o ÚNICO perfil que vincula.
        "vincula_apos_oficina": True,
        "descricao_template_retirada": "SUBSTITUIÇÃO RETIRADA: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
        "descricao_template_instalacao": "SUBSTITUIÇÃO INSTALAÇÃO: {placa} | {veiculo} | {serie} ({modelo}) | TERMO {termo}",
    },

    # ── 5 e 6 ─────────────────────────────────────────────────────────────────
    # São 2 DOCUMENTOS separados (o antigo titular no formato Rescisão, o novo
    # no formato Contrato Novo), cada um subido no seu perfil. Fisicamente nada
    # se move: o veículo e o equipamento ficam no lugar, a transferência é
    # administrativa. Cada perfil gera OS AGREGADA -- independe do nº de placas.
    #
    # 🆕 O NOVO TITULAR VIRA DUAS OS (usuário, 19/08). Era 1 híbrida com
    # financeiro e comodato JUNTOS; a regra 7 nova proíbe item de cobrança na
    # OS de comodato, então a híbrida não pode continuar existindo. Passa a ser
    # 1 operacional de comodato + 1 financeira com o cabeçalho padrão.
    "transferencia_novo_titular": {
        "label": "Transferência — Novo titular",
        "problema_id": 7474,   # TRANSFERÊNCIA DE TITULARIDADE
        "os_por_placa": 1,     # informativo; a geração é agregada
        "etapa_placas": "confere",
        "titularidade": "novo",
        "agregada": True,
        # ⚠️ `situacao_id` e `tecnico_id` SAÍRAM daqui. Eles existiam para
        # transformar a OS única em financeira; agora a financeira é separada e
        # traz o cabeçalho dela.
        "modelo_origem": "placa",
        "descricao_prefixo": "TRANSFERENCIA TITULARIDADE (NOVO TITULAR)",
    },
    # ⚠️ O ANTIGO TITULAR NÃO MUDA, e NÃO TEM FINANCEIRA.
    # Decisão de 29/07: gera tudo numa OS só, com TODOS os itens do termo, e
    # SEM flegar financeiro nem comodato -- só insere. O contrato antigo está
    # encerrando; quem assume comodato e cobrança é o novo titular, na OS dele.
    "transferencia_antigo_titular": {
        "label": "Transferência — Antigo titular",
        "problema_id": 7474,
        "os_por_placa": 1,
        "etapa_placas": "confere",
        "titularidade": "antigo",
        "agregada": True,
        "sem_financeira": True,
        "modelo_origem": "placa",
        "descricao_prefixo": "TRANSFERENCIA TITULARIDADE (ANTIGO TITULAR)",
    },

    # ── 7 ─────────────────────────────────────────────────────────────────────
    # 🚨 UPGRADE TROCA O EQUIPAMENTO, o veículo é o mesmo -- por isso 1 OS só,
    # na placa real. A placa `-UPGRADE` é RECIPIENTE: nunca é veículo de OS,
    # entra só como chave para descobrir a série do que entra.
    #
    # 🚨 RECIPIENTE SÓ NA WESO. Ele é bancada do setor de configuração, não
    # veículo do cliente -- no Harmonit não entra.
    "upgrade": {
        "label": "Upgrade de tecnologia",
        "tipo_id": 77,
        "problema_id": 7484,   # "UPGRADE" -- nome bate exato
        "os_por_placa": 1,
        "etapa_placas": "cria",
        "placa_teste_sufixo": "-UPGRADE",
        "recipiente_so_weso": True,
        # Confere que o recipiente pertence AO TERMO SUBIDO. Placa que já passou
        # por upgrade tem recipiente VELHO com outro termo; sem isto pegaríamos
        # a série do equipamento anterior, em silêncio.
        "placa_teste_descricao": "TERMO {termo}",
        # No upgrade o modelo que interessa é o que ENTRA.
        "modelo_origem": "placa_teste",
        "libera_serie": True,
        "descricao_template": "Upgrade: {placa} | {veiculo} | SAIRÁ: {serie} ({modelo_saida}) | ENTRARÁ: {serie_entrada} ({modelo}) | TERMO {termo}",
    },

    # ── 8 e 9 — sem termo ─────────────────────────────────────────────────────
    # 🚨 NÃO NASCEM DE DOCUMENTO. Os perfis de contrato vêm de um PDF assinado;
    # a manutenção vem de um chamado. Não há extração, não há número de termo e
    # não há item de contrato -- o que existe é uma placa e um defeito.
    #
    # 🚨 TIPO E PROBLEMA VÃO POR NOME. Das 14 OS de manutenção abertas na mão,
    # 7 usam `tipo = 55`, que não está mais na lista. Os `*_id` abaixo são só o
    # último recurso para quando a lista não responder: transiente de rede não
    # pode impedir a geração, mas nome que sumiu tem de impedir.
    #
    # 🚨 MANUTENÇÃO NÃO FLEGA COBRAR NEM COMODATO em nenhum item, e não gera
    # financeira. O equipamento aparece como material para o técnico saber com
    # o que vai lidar -- não é patrimônio saindo nem cobrança entrando.
    "manutencao_local": {
        "label": "Manutenção no local",
        "tipo_nome": "Solicitação de Cliente",
        "tipo_id": 1783,
        "problema_nome": "MANUTENÇÃO",
        "problema_id": 7384,
        "produto_servico_nome": "MANUTENÇÃO",
        "os_por_placa": 1,
        "etapa_placas": "confere",
        "sem_termo": True,
        "sem_flags": True,
        "sem_financeira": True,
        "numero_na_descricao": True,
        # Sem recipiente: interessa o equipamento que JÁ ESTÁ no veículo.
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
        # 🆕 A TELA PASSA A CRIAR O RECIPIENTE (usuário, 19/08). Hoje ele nasce
        # pelo setor de configuração minutos antes da OS, e é POR ISSO que a
        # manutenção lê a WESO ao vivo (16 a 30s). Criando na tela, ela sabe o
        # que criou: a leitura ao vivo do recipiente deixa de ser necessária.
        "etapa_placas": "cria",
        "sem_termo": True,
        "sem_flags": True,
        "sem_financeira": True,
        "numero_na_descricao": True,
        "placa_teste_sufixo": "-MANUT",
        "recipiente_so_weso": True,
        # ⚠️ TRAVA MAIS FRACA QUE A DO UPGRADE, e de propósito: o upgrade
        # compara com `TERMO {termo}`, que identifica a rodada; a manutenção não
        # tem termo e todo recipiente se chama `MANUTENCAO`. Isto prova que é UM
        # recipiente de manutenção, não que é o DESTA. O que fecha o resto é
        # liberar a série no fim: recipiente usado deixa de existir.
        "placa_teste_descricao": "MANUTENCAO",
        "modelo_origem": "placa_teste",
        "libera_serie": True,
        "descricao_template": "MANUTENÇÃO COM TROCA: {placa} | {veiculo} | SAIRÁ: {serie} ({modelo_saida}) | ENTRARÁ: {serie_entrada} ({modelo})",
    },

    # ── 10 e 11 — ressarcimento (novos em 19/08) ──────────────────────────────
    # 🚨 HÍBRIDA: COBRANÇA + OFICINA, SEM COMODATO. Não confundir com a híbrida
    # que ACABOU (transferência novo titular), que era cobrança + comodato na
    # mesma OS e morreu pela regra 7. Esta não tem item de comodato nenhum,
    # então não esbarra nela.
    #
    # A oficina não é exclusiva da OS operacional (usuário, 19/08) -- é ela que
    # dispara a rotina de devolver o equipamento ao estoque.
    #
    # ⚠️ EQUIPAMENTO E CHIP NA WESO ESTÃO FORA DO ESCOPO DA TELA. Aqui se
    # cuida de placa, cliente e OS. Quem encosta em equipamento é a rotina.
    "ressarcimento_sem_termo": {
        "label": "Ressarcimento sem termo",
        "problema_id": RESSARCIMENTO_PROBLEMA_ID,
        "produto_servico_id": RESSARCIMENTO_SERVICO_ID,
        "os_por_placa": 1,
        "etapa_placas": "confere",
        "sem_termo": True,
        "agregada": True,
        "hibrida": True,          # cobrança + oficina na mesma OS
        "situacao_id": SITUACAO_FINANCEIRO_ID,
        "tecnico_id": FINANCEIRO_TECNICO_ID,
        # Valor nasce zero e o operador digita. Zero mantém `cobrar`
        # DESMARCADO, pela regra 4 -- sem exceção (usuário, 19/08).
        # 🚨 0,01 POR DECISAO DELE (21/08). O ressarcimento sem termo nao
        # nasce de documento, entao nao ha item de onde tirar valor -- e com
        # 0,00 a OS saia "SEM CUSTO", com `cobrar` desmarcado, para uma
        # operacao que por definicao e um reembolso. O centavo faz a linha de
        # cobranca existir e ser corrigida no Harmonit depois.
        "servico_valor_inicial": 0.01,
        "desativa_apos_oficina": True,
        "modelo_origem": "placa",
        "descricao_prefixo": "RESSARCIMENTO",
    },
    "ressarcimento_com_termo": {
        "label": "Ressarcimento com termo",
        "problema_id": RESSARCIMENTO_PROBLEMA_ID,
        "produto_servico_id": RESSARCIMENTO_SERVICO_ID,
        "os_por_placa": 1,
        "etapa_placas": "confere",
        "agregada": True,
        "hibrida": True,
        "situacao_id": SITUACAO_FINANCEIRO_ID,
        "tecnico_id": FINANCEIRO_TECNICO_ID,
        # Aqui o valor final vem do termo, não é digitado.
        "valor_do_termo": True,
        "desativa_apos_oficina": True,
        "modelo_origem": "placa",
        "descricao_prefixo": "RESSARCIMENTO",
    },
}

# ── Conveniências de leitura ─────────────────────────────────────────────────
# Existem para a tela e os testes não repetirem `p.get(...)` em toda parte, e
# para que uma chave escrita errada apareça aqui em vez de virar `False` calado.

ETAPA_PLACAS = ("cria", "confere", "cria_entrada")


def perfil(nome: str) -> dict:
    """O perfil, ou KeyError. Nunca devolve `{}` -- perfil inexistente é erro
    de programação, e um dicionário vazio faria toda regra virar `False`."""
    return PERFIS[nome]


def com_termo() -> list[str]:
    return [n for n, p in PERFIS.items() if not p.get("sem_termo")]


def sem_termo() -> list[str]:
    return [n for n, p in PERFIS.items() if p.get("sem_termo")]


def com_recipiente() -> list[str]:
    return [n for n, p in PERFIS.items() if p.get("placa_teste_sufixo")]
