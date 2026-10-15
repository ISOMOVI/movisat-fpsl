"""Tabelas da Gestão de Contratos (`CTR_1.1`). 2026-10-13.

🚨 MÓDULO PRÓPRIO, E NÃO UM BLOCO NOVO NO `storage.init_db`. O `storage.py`
tem 1.816 linhas e é lido por tudo; a aba nova precisa de 4 tabelas e nenhuma
alteração nas existentes. Então a DDL mora aqui e o `init_db` chama
`criar(conn)` -- uma linha de diff num arquivo que o painel inteiro usa.

Padrão da casa, igual ao resto do `storage.py`: `CREATE TABLE IF NOT EXISTS` +
`ALTER` idempotente conferido por `PRAGMA table_info`. Rodar duas vezes não
quebra e não perde dado.

🚨 `contrato_evento` É IMUTÁVEL. Nada de `UPDATE` nela: corrigir é lançar outro
evento. É o que permite responder "por que esta placa está ativa?" com o
documento na mão, e é o oposto do que o Harmonit faz hoje (editar o PDF do
termo depois de assinado e anotar a troca em texto livre).

🚨 `contrato_placa` É DERIVADA, NÃO FONTE. Ela é cache do que
`contratos_eventos.situacao_das_placas` calcula, para a tela não recalcular 731
clientes a cada abertura. Em caso de dúvida entre as duas, **o evento ganha** e
a derivada se refaz. Nenhuma regra lê `contrato_placa` para decidir.
"""

TABELAS = ("contrato_termo", "contrato_evento", "contrato_item", "contrato_placa",
           "contrato_achado", "contrato_cliente", "contrato_revisao",
           "contrato_carga_pdf")


def criar(conn) -> None:
    """Cria o que falta. Idempotente -- seguro em todo start do serviço."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contrato_termo (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj          TEXT    NOT NULL,
            numero        TEXT    NOT NULL,
            -- MOVISAT · INSTITUTO · CADASTRO ANTIGO. O Instituto migrou todo
            -- para a Movisat e o numero do termo MUDA na migracao, por isso o
            -- vinculo real e a placa, nunca o numero (decisao dele, 13/10).
            empresa       TEXT    NOT NULL DEFAULT 'MOVISAT',
            tipo          TEXT,
            assinado      INTEGER NOT NULL DEFAULT 0,
            assinado_em   TEXT,
            -- Anotacao de troca encontrada no PDF do Harmonit deste mesmo
            -- termo. Preenchida = a placa nova do Harmonit vale como assinada.
            troca_registrada TEXT,
            -- 1 quando o documento ASSINADO traz "a definir" na tabela de
            -- veiculos: a placa real foi preenchida depois, no Harmonit.
            a_definir     INTEGER NOT NULL DEFAULT 0,
            -- 🆕 G1: a marca de assinatura do ÍNDICE DO HARMONIT ("sim"/"nao").
            -- ⚠️ NÃO É PROVA: a regra dele é "vale o assinado", e o assinado
            -- verificável mora na Clicksign. Fica em coluna separada de
            -- `assinado` porque a diferença entre as duas é a pergunta -- na
            -- 2HM, os termos 255, 2207 e 2224 estão "sim" aqui e não têm nada
            -- na Clicksign.
            -- 🚨 Está no CREATE **e** no `migrar()`: o CREATE serve à base
            -- nova (teste, cópia), o ALTER à base que já existe. Pôr só no
            -- ALTER deixou duas suítes em `no such column` -- elas chamam
            -- `criar()` sem `migrar()`, e é o padrão da casa desde o começo.
            harmonit_assinado TEXT,
            origem        TEXT    NOT NULL,     -- upload · carga · clicksign
            arquivo       TEXT,
            -- 🚨 hash do PDF: e o que impede o mesmo documento de entrar duas
            -- vezes e dobrar os eventos. UNIQUE no indice abaixo.
            hash          TEXT,
            revisar       INTEGER NOT NULL DEFAULT 0,
            revisar_motivo TEXT,
            enviado_por   TEXT,
            enviado_em    TEXT    NOT NULL
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_contrato_termo_hash ON contrato_termo(hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_termo_cnpj ON contrato_termo(cnpj, numero)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS contrato_evento (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            termo_id    INTEGER NOT NULL REFERENCES contrato_termo(id),
            -- Identificador normalizado (Mercosul/chassi) -- para COMPARAR.
            placa_chave TEXT    NOT NULL,
            -- A placa COMO ESTA NO TERMO -- para MOSTRAR. Nunca mostrar a
            -- chave: `BUW8732` normaliza para `BUW8H32`, que nao existe.
            placa_texto TEXT    NOT NULL,
            acao        TEXT    NOT NULL,      -- ENTRA · SAI · RESCINDE · UPGRADE
            fonte       TEXT    NOT NULL,      -- assinado · harmonit
            recursos    TEXT,                  -- JSON: bloqueio, RFID, central 24h...
            valor_mensal TEXT,
            obs         TEXT,
            -- 🆕 C7: o `id` do evento que ESTE anula (ver `migrar()`). Está no
            -- CREATE **e** no ALTER: o CREATE serve à base nova (teste, cópia),
            -- o ALTER à que já existe. Pôr só no ALTER deixou duas suítes em
            -- `no such column` quando a coluna anterior entrou.
            corrige_evento_id INTEGER,
            criado_em   TEXT    NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_evento_termo ON contrato_evento(termo_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_evento_placa ON contrato_evento(placa_chave)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS contrato_item (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj        TEXT    NOT NULL,
            placa_chave TEXT    NOT NULL,
            placa_texto TEXT    NOT NULL,
            recursos    TEXT,
            -- O valor vem do TERMO (decisao dele, 13/10): a CAR calcula, nao
            -- decide. Texto, nao REAL: o termo escreve "R$ 999,90" e valor
            -- riscado/renegociado ja enganou a leitura antes.
            valor_mensal TEXT,
            inicio      TEXT,
            fim         TEXT,
            fidelidade_meses INTEGER,
            termo_id    INTEGER REFERENCES contrato_termo(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_item_cnpj ON contrato_item(cnpj, placa_chave)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS contrato_placa (
            cnpj          TEXT NOT NULL,
            placa_chave   TEXT NOT NULL,
            placa_texto   TEXT NOT NULL,
            -- ATIVA · EM_AVISO_PREVIO · RESCINDIDA · SUBSTITUIDA
            situacao      TEXT NOT NULL,
            -- assinado · assinado (troca registrada...) · assinado com 'a definir'... · nao assinado
            base          TEXT,
            termo_vigente TEXT,
            desde         TEXT,
            aviso_ate     TEXT,
            obs           TEXT,
            calculado_em  TEXT NOT NULL,
            PRIMARY KEY (cnpj, placa_chave)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_placa_situacao ON contrato_placa(situacao)")

    # 🆕 C6: o que a rotina de auditoria achou comparando contrato × WESO.
    # 🚨 APAGADA E REFEITA A CADA RODADA, de propósito. Achado é RETRATO de um
    # instante, não histórico: a placa que entrou na WESO hoje deixa de ser
    # "em uso sem contrato" amanhã, e manter o achado velho faria a tela
    # mostrar problema resolvido como se fosse atual -- tela que mente.
    # Quem guarda história é `contrato_evento`, que é imutável.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contrato_achado (
            tipo         TEXT NOT NULL,
            cnpj         TEXT,
            placa_texto  TEXT,
            detalhe      TEXT,
            rodada_em    TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_achado_tipo ON contrato_achado(tipo)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_achado_cnpj ON contrato_achado(cnpj)")

    # 🆕 G1: o NOME do cliente, que a `CTR_1.1` não guardava em lugar nenhum.
    # 🚨 ELE NÃO ESTÁ EM NENHUMA OUTRA TABELA DO FPSL. A `clientes` tem só
    # `harmonit_id` e `cnpjcpf`; o cache da WESO tem 304 clientes e não cobre
    # os 731 da carga (a 2HM, por exemplo, não está lá). O nome da carga veio
    # do índice do Harmonit e chega SANITIZADO (`M_ D_ G_ COMERCIO...`), por
    # isso existe `nome_fonte`: nome corrigido à mão (`manual`) nunca é
    # sobrescrito por carga nem por leitura de PDF.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contrato_cliente (
            cnpj          TEXT PRIMARY KEY,
            nome          TEXT NOT NULL,
            nome_fonte    TEXT NOT NULL,     -- carga · pdf · manual
            atualizado_em TEXT NOT NULL,
            atualizado_por TEXT
        )
    """)

    # 🆕 G1: quem olhou um termo marcado `revisar` e o que disse.
    # 🚨 SÓ INSERÇÃO, e o `revisar_motivo` do termo NÃO É APAGADO. O motivo
    # conta por que o termo entrou duvidoso (a carga usou a placa do Harmonit,
    # o PDF não existe, a troca não disse quem sai); apagá-lo ao revisar
    # perderia a razão e a tela passaria a dizer que nunca houve dúvida.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contrato_revisao (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            termo_id  INTEGER NOT NULL REFERENCES contrato_termo(id),
            por       TEXT    NOT NULL,
            em        TEXT    NOT NULL,
            nota      TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_revisao_termo ON contrato_revisao(termo_id)")

    # 🆕 C7: o livro-razão da carga dos PDFs assinados.
    # 🚨 É O QUE DÁ RETOMADA E REVERSÃO. A carga são ~2.825 documentos lidos um
    # por um, num banco em `journal_mode=delete` (cada escrita tranca o
    # serviço): ela precisa poder parar no meio e continuar sem reprocessar, e
    # precisa poder ser desfeita por lote. `antes_json` guarda o estado do termo
    # ANTES do anexo -- sem ele, "desfazer" seria adivinhar.
    # ⚠️ `sha256` é a chave: o mesmo documento nunca é lido duas vezes, e isso é
    # independente do nome do arquivo (que, medido, mente: o "nº 2" da 2HM é na
    # verdade o assinado dos termos 2207 e 2224).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contrato_carga_pdf (
            sha256         TEXT PRIMARY KEY,
            chave_clicksign TEXT,
            cnpj           TEXT,
            arquivo        TEXT,
            -- assinado · cancelado · rascunho · pendente, como veio do CSV da
            -- auditoria. Fica gravado para a conferência poder provar que
            -- nenhum estado proibido entrou.
            estado_origem  TEXT,
            numero_no_nome TEXT,
            numero_no_pdf  TEXT,
            -- anexado · doc_so · fila · rejeitado
            status         TEXT NOT NULL,
            motivo         TEXT,
            termo_id       INTEGER,
            lote           TEXT,
            antes_json     TEXT,
            em             TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_carga_pdf_status ON contrato_carga_pdf(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_carga_pdf_cnpj ON contrato_carga_pdf(cnpj)")


def _colunas(conn, tabela) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def migrar(conn) -> list:
    """Colunas acrescentadas depois da primeira versão. Devolve o que mudou.

    Fica aqui, e não solto no `init_db`, para a aba nova não espalhar `ALTER`
    por um arquivo que o painel inteiro lê.
    """
    feitas = []

    # 🆕 G1: a marca de assinatura do ÍNDICE DO HARMONIT, que o arquivo da
    # carga trazia (`harmonit_assinado`) e a tabela jogava fora.
    # ⚠️ NÃO É PROVA DE ASSINATURA, e por isso é coluna separada de `assinado`:
    # a regra dele é "vale o assinado", e o assinado verificável mora na
    # Clicksign. Na 2HM os termos 255, 2207 e 2224 estão "sim" aqui e não têm
    # nada na Clicksign -- é exatamente a diferença que ele precisa ver na tela
    # para decidir, e misturar as duas colunas apagaria a pergunta.
    if "harmonit_assinado" not in _colunas(conn, "contrato_termo"):
        conn.execute("ALTER TABLE contrato_termo ADD COLUMN harmonit_assinado TEXT")
        feitas.append("contrato_termo.harmonit_assinado")

    # 🆕 C7 (14/10): qual evento este evento ANULA.
    # 🚨 É O QUE PERMITE CORRIGIR SEM APAGAR. A carga de 13/10 gravou a lista de
    # placas do Harmonit (o PDF é editado depois de assinado); quando a
    # releitura do ASSINADO não traz aquela placa, o evento que a fez entrar
    # está errado -- e `contrato_evento` é imutável. Então entra um evento
    # `ANULA` apontando para o `id` do errado, que continua visível na ficha.
    if "corrige_evento_id" not in _colunas(conn, "contrato_evento"):
        conn.execute("ALTER TABLE contrato_evento ADD COLUMN corrige_evento_id INTEGER")
        feitas.append("contrato_evento.corrige_evento_id")
    # ⚠️ Índice ÚNICO parcial: o mesmo evento não pode ser anulado duas vezes.
    # Sem ele, rodar a carga de novo empilharia anulação sobre anulação e a
    # ficha mostraria a mesma correção repetida.
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_contrato_evento_corrige
                      ON contrato_evento(corrige_evento_id)
                   WHERE corrige_evento_id IS NOT NULL""")

    return feitas
