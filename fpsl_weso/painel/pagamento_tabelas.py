# -*- coding: utf-8 -*-
"""As tabelas de **Serviço dos Técnicos** — 🔵 a aba 2 do Financeiro, 18/11.

🔵 Desenho dele: cinco colunas — Movimentação, Preparação, Validação, Procfy e
Pagamento enviado — e 🔵 *"É possível fazer tudo no FPSL com as rotas e etc, mas
o painel é aqui"*. Por isso os dados moram aqui e a tela mora no MoviZap.

🚨 **A DDL MORA NESTE ARQUIVO, e não no `storage.py`**, pelo mesmo motivo da
Gestão de Contratos (13/10) e das Contas a Receber (28/10): a frente precisa de
três tabelas e de nenhuma alteração nas existentes, então o diff no arquivo que
o painel inteiro lê são duas linhas.

---

## 🚨 A unidade é o ARTEFATO DE PAGAMENTO, e nomeá-la é o que faz as cinco
## colunas se encaixarem

Ele a chamou assim, e é isso: **um serviço pago a um técnico numa OS**.

    artefato = (técnico, OS) -> Orçamento · OS · TERMO · pagamento · km

🔵 A ordem de exibição é a dele: *"Orçamento - OS - TERMO"*, e os valores são
*"dos serviços no corpo da OS do deslocamento e pagamento do técnico"* — os dois
ids de produto que o `services/fechamento.py` já extrai do `materiais_json`
(`PAGAMENTO_TECNICO_ID = 653939` e `KM_DESLOCAMENTO_ID = 6971`).

⚠️ **O ARTEFATO ATRAVESSA AS CINCO COLUNAS; O CARD NÃO.** O card da coluna 1 é
permanente por técnico (🔵 decisão dele); os das colunas 2 a 5 são lotes. É o
artefato que se move — e é isso que faz 🔵 *"os removidos voltam para o card da
primeira coluna"* funcionar de qualquer etapa, sem caso especial.

---

## 📏 O que a medição de 18/11 disse sobre o tamanho disto

| medida | valor |
|---|---|
| OS no cache com materiais | 633 |
| OS com valor de pagamento ou de km | **79** |
| ...sem técnico de verdade (só a empresa 629 ou técnico excluído) | **21** |
| artefatos que a coluna 1 recebe | **58**, em **8** técnicos |
| o maior: Franck (`tid 14262`) | 40 OS, R$ 3.430,00 + R$ 933,10 |
| orçamentos emitidos no MoviZap, no total | **4** |

🚨 **Os 21 sem técnico são o funil que ele mandou consertar** (medido em 11/11:
70 → 16 → 8 OS). Aqui eles **não desaparecem**: ficam com `tecnico_id` nulo, que
a tela mostra num card próprio. Artefato de pagamento que some é dinheiro que
ninguém cobra nem paga.

⚠️ **E 🔵 serviço sem orçamento ENTRA** (decisão dele): `orcamento_numero` nulo
quer dizer *"sem orçamento"*, e o card diz isso em amarelo. Como só 4 orçamentos
existem, a maioria vai nascer amarela — consequência que ele aceitou sabendo.
"""

# 🔵 As quatro situações que a coluna 2 aceita, nomeadas por ele.
# 🚨 PORTA DUPLA, e é o conserto do funil: a primeira é etapa NOSSA (vive no
# MoviZap, `pipeline_etapa` 2322) e as outras três são situações do Harmonit. O
# Fechamento antigo exigia **só** a 15694, e foi isso que derrubou 70 OS para 16.
SITUACOES_QUE_LIBERAM = (15696, 16490, 15694)
ETAPA_NOSSA_SERVICO_REALIZADO = 2322

# As cinco colunas, na ordem dele.
COLUNAS = ("movimentacao", "preparacao", "validacao", "procfy", "enviado")

# 🔵 *"vamos usar logica semafórica para essas etapas"*.
# ⚠️ `laranja` é o devolvido, e é um estado dele, não meu: 🔵 *"O artefato de
# pagamento que retornou ao card da coluna 1, agora tem a cor laranja"*.
SEMAFOROS = ("verde", "amarelo", "laranja", "vermelho")


def criar(conn) -> None:
    """As três tabelas. Idempotente, no padrão do resto do `storage`."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS pagamento_artefato (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            -- 🚨 NULO É LEGÍTIMO e são os 21 medidos: OS com valor de
            -- pagamento e sem técnico de verdade na linha. Elas entram, num
            -- card próprio, para o dinheiro não sair de vista.
            tecnico_id           INTEGER,
            tecnico_nome         TEXT,
            numero_os            INTEGER NOT NULL,
            -- 🔵 O orçamento é o do MoviZap (decisão dele). ⚠️ NULO = "sem
            -- orçamento", que é o caso da maioria hoje (4 emitidos no total).
            orcamento_numero     INTEGER,
            -- ⚠️ 1 de cada 7 OS não tem termo: venda, cartão RFID e manutenção
            -- não nascem de termo. Nulo é normal, e a tela não diz nada.
            termo                TEXT,
            valor_pagamento      REAL NOT NULL DEFAULT 0,
            valor_km             REAL NOT NULL DEFAULT 0,
            -- A data do SERVIÇO (a `dataPrevisao` da OS). 🔵 É por ela que o
            -- filtro do card da coluna 1 corta: *"só quero fechar de
            -- 16-18/11/26 filtro isso e flego"*. E é ela que vai ao Procfy
            -- como data de competência.
            data_os              TEXT,
            coluna               TEXT NOT NULL DEFAULT 'movimentacao',
            lote_id              INTEGER REFERENCES pagamento_lote(id),
            semaforo             TEXT,
            -- A situação lida na coluna 2, e o ciente do operador.
            situacao_do_erp      INTEGER,
            etapa_nossa          INTEGER,
            ciente_em            TEXT,
            ciente_por           TEXT,
            -- 🔵 *"abrindo um campo de justificativa com campo de texto
            -- pequeno"*. ⚠️ Sem justificativa não se devolve: devolver calado
            -- deixaria o artefato em laranja e ninguém saberia por quê.
            justificativa        TEXT,
            devolvido_em         TEXT,
            devolvido_por        TEXT,
            -- A coluna 3: o DataScope e o comprovante.
            datascope_form_state TEXT,
            datascope_lido_em    TEXT,
            comprovante_arquivo  TEXT,
            valor_do_comprovante REAL,
            -- 🔵 *"avança com os que tiveram ou arquivo enviado ou
            -- justificativa escrita na tela de envio de anexo (pode não ter)"*.
            comprovante_dispensa TEXT,
            criado_em            TEXT NOT NULL,
            atualizado_em        TEXT NOT NULL,
            -- 🚨 O MESMO SERVIÇO NÃO ENTRA DUAS VEZES. É a trava que o
            -- `listar_numeros_os_consumidas` faz hoje em código, agora no
            -- banco -- e no banco ela sobrevive a duas varreduras no mesmo
            -- minuto, que o código não garante.
            -- ⚠️ `tecnico_id` nulo participa da chave: no SQLite, NULL não
            -- colide com NULL em UNIQUE, então os 21 sem técnico NÃO são
            -- barrados entre si. Quem os impede de duplicar é a `numero_os`
            -- conferida na varredura.
            UNIQUE(tecnico_id, numero_os)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS pagamento_artefato_coluna_idx
            ON pagamento_artefato (coluna, tecnico_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS pagamento_artefato_os_idx
            ON pagamento_artefato (numero_os)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pagamento_lote (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tecnico_id      INTEGER NOT NULL,
            tecnico_nome    TEXT,
            coluna          TEXT NOT NULL DEFAULT 'preparacao',
            -- O arquivo do Procfy, quando a coluna 4 o gera.
            arquivo_procfy  TEXT,
            gerado_em       TEXT,
            gerado_por      TEXT,
            baixado_em      TEXT,
            criado_em       TEXT NOT NULL,
            criado_por      TEXT,
            atualizado_em   TEXT NOT NULL,
            encerrado_em    TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS pagamento_lote_coluna_idx
            ON pagamento_lote (coluna)
            WHERE encerrado_em IS NULL
    """)

    # 🚨 O LOG, E ELE NÃO É LUXO. Este fluxo move dinheiro e avisa gente de
    # fora da empresa: a correção no DataScope dispara os webhooks deles e
    # manda push para o técnico que enviou a resposta. 🔵 *"deve ter o log de
    # quem faz o que SEMPRE"* é régua dele desde 29/10, e aqui pesa mais que em
    # qualquer outra tela.
    # ⚠️ UMA TABELA DE EVENTOS, não colunas de carimbo espalhadas: a pergunta
    # real é *"o que aconteceu com este artefato, em ordem?"*, e carimbo não
    # responde ordem.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pagamento_evento (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            artefato_id   INTEGER REFERENCES pagamento_artefato(id),
            lote_id       INTEGER REFERENCES pagamento_lote(id),
            acao          TEXT NOT NULL,
            de            TEXT,
            para          TEXT,
            detalhe       TEXT,
            por           TEXT,
            em            TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS pagamento_evento_artefato_idx
            ON pagamento_evento (artefato_id, em)
    """)
    # 🚨 **A `config`, QUE NÃO É NOSSA, E AINDA ASSIM ENTRA AQUI.** Ela é
    # tabela do núcleo do FPSL e já existe em produção, então este `IF NOT
    # EXISTS` nunca faz nada lá. Ele existe para o BANCO DE TESTE: desde 23/11
    # a aba 2 lê `pagamento_servico_desde` dela (🔵 D6 dele), e as fixtures dos
    # testes criam só as tabelas que o pagamento declara.
    #
    # ⚠️ A alternativa era um `try/except OperationalError` dentro do `desde()`,
    # e ela é pior: mascararia em produção uma `config` que de fato faltasse,
    # que é um problema de verdade, para resolver um problema de fixture.
    # 📏 O schema é cópia do que está no `fpsl.db` (medido em 23/11).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            chave         TEXT PRIMARY KEY,
            valor         TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
    """)


def migrar(conn) -> None:
    """As alterações posteriores. Vazia hoje, e existe para o padrão ficar.

    ⚠️ Os dois vizinhos (`contratos_tabelas`, `car_tabelas`) têm `criar` e
    `migrar`, e o `init_db` chama os dois. Deixar esta função de fora faria a
    terceira frente ser a diferente -- e a primeira alteração de coluna teria
    de inventar onde morar.
    """
    return None
