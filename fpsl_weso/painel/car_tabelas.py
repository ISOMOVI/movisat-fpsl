"""Tabelas das Contas a Receber (`CAR_1.1`). 2026-10-28.

Spec: `docs/fpsl/32_Contas_a_Receber.md`. Controle da frente:
`C:\\Users\\Lenovo\\Desktop\\CAR_1.1_Financeiro_FPSL.md`.

🚨 MÓDULO PRÓPRIO, no mesmo molde de `contratos_tabelas.py`, e por motivo igual:
o `storage.py` é lido pelo painel inteiro, e esta aba precisa de 3 tabelas e de
**nenhuma alteração** nas existentes. A DDL mora aqui e o `init_db` chama
`criar(conn)` + `migrar(conn)` -- duas linhas de diff naquele arquivo.

🚨 A CAR LÊ A CTR, NÃO A ALTERA. Nenhum `ALTER` nas 8 tabelas `contrato_*`.
Regra da casa: regra que muda **clona**, infraestrutura **reusa**. É também por
isso que as ações financeiras NÃO entraram em `contrato_evento`: as ações de lá
(ENTRA · SAI · RESCINDE · UPGRADE · ANULA) são sobre **existência de placa**, e
o motor que as interpreta (`contratos_eventos.situacao_das_placas`) é puro e
travado por teste. Acrescentar ação financeira ali mudaria regra sob trava.

🚨 `car_evento` É IMUTÁVEL. Nada de `UPDATE` nela: corrigir é lançar um `ANULA`
apontando o errado, que **continua visível**. É o que permite responder "por que
este cliente pagou isto neste mês?" com o documento e o autor na mão.

🚨 `car_contrato` É DERIVADA, NÃO FONTE. Cache de uma régua que roda sobre os
eventos (os da CTR e os daqui). Em caso de dúvida entre as duas, **o evento
ganha** e a derivada se refaz. Nenhuma regra lê `car_contrato` para decidir.

🚨 NÃO EXISTE TABELA DE FATURA, VENCIMENTO, PARCELA OU BOLETO, e isso é
desenho, não falta. A cobrança de um mês é uma **leitura** do contrato naquele
mês -- `contratos_eventos.situacao_das_placas(termos, hoje=fim da competência)`
mais o último `PRECO` vigente. Recebível copiado congela, e no mês seguinte
ninguém sabe dizer por que aquele valor está lá (doc 33 §11). `car_leitura`
guarda a AUDITORIA de uma leitura, não o recebível.

⚠️ SEM `CHECK` em `acao` nem em `situacao`, de propósito. A CTR aprendeu isso:
`ACOES` ficou fechado **no código**, e quando a `ANULA` precisou nascer, em
14/10, bastou mudar o motor -- com `CHECK` no SQLite teria sido reconstrução de
tabela com 12 mil linhas. O conjunto válido vive em `car_motor.py` e é travado
por teste.

Padrão da casa: `CREATE TABLE IF NOT EXISTS` + `ALTER` idempotente conferido
por `PRAGMA table_info`. Rodar duas vezes não quebra e não perde dado.
"""

TABELAS = ("car_evento", "car_contrato", "car_leitura", "car_faturado")


def criar(conn) -> None:
    """Cria o que falta. Idempotente -- seguro em todo start do serviço."""

    # ─────────────────────────────────────────────────────────────────────
    # car_evento — o livro-razão do dinheiro
    # ─────────────────────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS car_evento (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj          TEXT    NOT NULL,
            -- O fato é do CONTRATO, não da placa: é o termo que dá o preço, a
            -- vigência e a fidelidade. `termo_id` aponta `contrato_termo.id`,
            -- sem FOREIGN KEY por simetria com a CTR (que também não usa).
            termo_id      INTEGER NOT NULL,
            -- NULO = o fato vale para TODAS as placas do termo. É o caso
            -- comum: o termo dá um preço de mensalidade, não um por veículo.
            -- Preenchido = o fato é de uma placa só (reajuste individual,
            -- isenção de uma, troca de plano de uma).
            placa_chave   TEXT,
            -- PRECO · CANCELA · RENOVA · EXCECAO · ANULA. Enum no código
            -- (`car_motor`), não em CHECK -- ver o aviso do topo.
            acao          TEXT    NOT NULL,
            -- 🚨 TEXT, NÃO REAL, pela mesma razão de `contrato_item`: o termo
            -- escreve "R$ 999,90", e valor riscado ou renegociado já enganou a
            -- leitura antes. A conversão para número acontece num lugar só, na
            -- hora de somar, e erro de conversão é DITO, não silenciado.
            valor_mensal  TEXT,
            -- 'AAAA-MM' a partir do qual o fato passa a valer. É o eixo do
            -- tempo desta aba: a pré-fatura de um mês lê o último PRECO com
            -- competencia <= aquele mês.
            competencia   TEXT    NOT NULL,
            -- Obrigatório quando `fonte` = 'operador' (quem valida é o
            -- registro, não o banco): sem motivo, meses depois ninguém sabe
            -- por que o valor mudou, e era essa a pergunta.
            motivo        TEXT,
            -- O que PROVA o fato: hash/arquivo do termo ou do aditivo. Vazio
            -- em evento de operador, e a tela mostra essa diferença.
            documento     TEXT,
            fonte         TEXT    NOT NULL,     -- termo · aditivo · operador
            -- 🚨 NUNCA VAZIO. Dinheiro sem autor é dinheiro sem responsável; é
            -- a mesma régua do `finalizado_por` da FIN_1.1.
            por           TEXT    NOT NULL,
            criado_em     TEXT    NOT NULL,
            -- Qual evento DESTA tabela este anula. É o que permite corrigir
            -- sem apagar: o errado continua na linha do tempo, marcado.
            corrige_evento_id INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_car_evento_termo ON car_evento(termo_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_car_evento_cnpj  ON car_evento(cnpj)")
    # ⚠️ Índice ÚNICO parcial: o mesmo evento não pode ser anulado duas vezes.
    # Sem ele, repetir uma correção empilharia anulação sobre anulação e o
    # histórico de preço mostraria a mesma correção repetida. É o mesmo remédio
    # de `idx_contrato_evento_corrige`.
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_car_evento_corrige
                      ON car_evento(corrige_evento_id)
                   WHERE corrige_evento_id IS NOT NULL""")

    # ─────────────────────────────────────────────────────────────────────
    # car_contrato — o status ativo/inativo do CONTRATO, derivado
    # ─────────────────────────────────────────────────────────────────────
    # Decisão dele, 28/10: "o ativo e inativo é por placa dentro do contrato e
    # pelo contrato em si". O nível de BAIXO já existe e não se duplica aqui: é
    # `contrato_placa.situacao`, calculada pelo motor da CTR. Esta tabela é só o
    # nível de CIMA.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS car_contrato (
            termo_id      INTEGER PRIMARY KEY,
            cnpj          TEXT    NOT NULL,
            numero        TEXT,
            empresa       TEXT,
            situacao      TEXT,                 -- ATIVO · INATIVO
            -- 🚨 O POR QUÊ, SEMPRE. "INATIVO" sozinho faz o operador abrir o
            -- contrato para descobrir se foi cancelado, se não tem placa ou se
            -- o termo nunca foi assinado -- três coisas diferentes. Tela que
            -- mostra estado sem causa é tela que mente por omissão.
            motivo        TEXT,
            placas_ativas     INTEGER,
            placas_com_valor  INTEGER,
            placas_sem_valor  INTEGER,
            -- 🚨 NULO quando nenhuma placa tem valor, NUNCA '0,00'. "0,00"
            -- afirma que o contrato não cobra nada; nulo com motivo diz a
            -- verdade, que é "não sabemos". Em 28/10 isto vale para quase toda
            -- a base: 1 item com valor, de 6.463.
            valor_mensal_total TEXT,
            -- Preenchida quando a CAR e a CTR discordam: "cancelado na CAR com
            -- 3 placas ATIVAS na CTR", e o inverso. É o achado que impede as
            -- duas abas de mentirem uma para a outra.
            divergencia   TEXT,
            -- A competência em que esta linha foi calculada. Sem ela, o status
            -- seria afirmado sem prazo -- a mesma razão do `situacao_em` do
            -- MoviZap e do `calculado_em` de `contrato_placa`.
            competencia   TEXT,
            calculado_em  TEXT    NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_car_contrato_cnpj ON car_contrato(cnpj)")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_car_contrato_situacao
                      ON car_contrato(situacao)""")

    # ─────────────────────────────────────────────────────────────────────
    # car_leitura — a auditoria de UMA leitura de mês. Não é recebível.
    # ─────────────────────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS car_leitura (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            competencia   TEXT    NOT NULL,
            -- NULO = a carteira inteira. Preenchido = a leitura foi de um
            -- cliente só.
            cnpj          TEXT,
            gerada_em     TEXT    NOT NULL,
            por           TEXT    NOT NULL,
            clientes      INTEGER,
            placas        INTEGER,
            sem_valor     INTEGER,
            total         TEXT,
            -- sha256 do resultado normalizado. Serve para uma pergunta só, e é
            -- uma pergunta que vai aparecer: "reabri outubro e o número mudou,
            -- por quê?". Com a assinatura, a mudança é FATO; sem ela, é
            -- discussão. A causa se explica pelos eventos.
            assinatura    TEXT
        )
    """)
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_car_leitura_comp
                      ON car_leitura(competencia)""")

    # ─────────────────────────────────────────────────────────────────────
    # car_faturado — o espelho do que o Harmonit JÁ cobra (bloco F1, 30/10)
    # ─────────────────────────────────────────────────────────────────────
    # 🚨 ESPELHO, NÃO FONTE: toda linha daqui é cópia de leitura do Harmonit, e
    # nada nesta tabela decide cobrança. O que a CAR afirma sai de `car_evento`
    # (o preço) e da CTR (as placas). Confundir os dois faria a CAR "cobrar o
    # que o Harmonit cobrou", e aí ela não substituiria nada -- repetiria.
    #
    # 🚨 A CHAVE É O `id` DO HARMONIT, e é isso que torna reler um mês
    # idempotente: a passada seguinte faz `INSERT OR REPLACE` da mesma linha, em
    # vez de empilhar cópia (foi o defeito das 11/22/21 cópias por caminho novo
    # na Operações).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS car_faturado (
            id            INTEGER PRIMARY KEY,
            -- mensalidade · servico · venda · adesao · negociacao · outro.
            -- Enum em `car_faturado.py` (o módulo), não em CHECK -- ver o topo.
            tipo          TEXT    NOT NULL,
            estado        TEXT    NOT NULL,     -- a_baixar · baixado
            -- 🚨 'AAAA-MM' LIDA DA DESCRIÇÃO, e NULA quando o texto não diz.
            -- O mês de vencimento NÃO serve de substituto: das 261 mensalidades
            -- baixadas em outubro/2026, 233 eram de referência 09/2026.
            competencia   TEXT,
            vencimento    TEXT,
            pagamento     TEXT,
            -- TEXT pela mesma razão de `car_evento.valor_mensal`.
            valor         TEXT,
            valor_final   TEXT,
            -- O cliente no Harmonit. `cnpj` é o nosso, resolvido por
            -- `clientes.harmonit_id`, e fica NULO quando não resolve (3 de 246
            -- em 30/10) -- nulo com a lista na tela, nunca chute.
            contato_id    INTEGER,
            contato       TEXT,
            cnpj          TEXT,
            -- O número do contrato vem no TEXTO; `termo_id` é o que ele resolve
            -- nesta base, NULO quando não resolve (77 de 268 em 30/10).
            termo_numero  TEXT,
            termo_id      INTEGER,
            numero_os     INTEGER,
            numero_venda  TEXT,
            parcela       TEXT,                 -- "17/24", da Negociação
            centro_custo  TEXT,
            categoria     TEXT,
            conta_corrente TEXT,
            nosso_numero  TEXT,
            -- 🚨 A DESCRIÇÃO CRUA FICA SEMPRE. É a única prova do que o texto
            -- dizia, e o que permite reclassificar sem reler o Harmonit.
            descricao     TEXT,
            -- 🚨 DE QUE MES DE VENCIMENTO esta linha veio ('AAAA-MM'). E
            -- proveniencia, e serve para uma pergunta que a tela precisa
            -- responder: "a competencia 09/2026 foi lida de quantos meses?".
            -- Medido em 30/10: aquela competencia tem lancamento em SETE meses
            -- de vencimento, e uma janela curta subestimava R$ 21 mil sem dizer.
            venc_ano_mes  TEXT,
            lido_em       TEXT    NOT NULL
        )
    """)
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_car_faturado_comp
                      ON car_faturado(competencia)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_car_faturado_cnpj ON car_faturado(cnpj)")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_car_faturado_termo
                      ON car_faturado(termo_id)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_car_faturado_os
                      ON car_faturado(numero_os)""")


def _colunas(conn, tabela) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def migrar(conn) -> list:
    """Colunas acrescentadas depois da primeira versão. Devolve o que mudou.

    Nasce vazia, de propósito: em 28/10 as 3 tabelas são novas e o `criar()`
    já as põe completas. A função existe desde o começo porque a da CTR não
    existia, e quando a primeira coluna nova precisou nascer o `ALTER` foi
    escrito solto -- e duas suítes quebraram em `no such column`, porque elas
    chamam `criar()` sem `migrar()`.

    🚨 Daí a regra desta casa, aprendida ali: coluna nova entra no `CREATE`
    **e** no `migrar()`. O `CREATE` serve à base nova (teste, cópia); o `ALTER`
    serve à base que já existe.
    """
    feitas = []
    # 30/10: `venc_ano_mes` nasceu depois da primeira versao da `car_faturado`
    # (no mesmo dia, mas em bancos que ja tinham a tabela criada).
    if "car_faturado" in {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}             and "venc_ano_mes" not in _colunas(conn, "car_faturado"):
        conn.execute("ALTER TABLE car_faturado ADD COLUMN venc_ano_mes TEXT")
        feitas.append("car_faturado.venc_ano_mes")
    return feitas
