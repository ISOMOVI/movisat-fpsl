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
           "contrato_achado")


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


def _colunas(conn, tabela) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def migrar(conn) -> list:
    """Colunas acrescentadas depois da primeira versão. Devolve o que mudou.

    Fica aqui, e não solto no `init_db`, para a aba nova não espalhar `ALTER`
    por um arquivo que o painel inteiro lê.
    """
    feitas = []
    # (nenhuma ainda — a primeira versão é esta)
    return feitas
