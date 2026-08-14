#!/usr/bin/env python3
"""De-para modelo da WESO -> produto do Harmonit. Cria e popula a tabela.

🚨 POR QUE EM TABELA E NAO NO CODIGO: e cadastro, muda sem deploy, e o usuario
precisa editar sem depender de mim. Mesmo padrao de `painel_vinculos_itens`.

Valores confirmados pelo usuario em 2026-08-13.
⚠️ O valor e PATRIMONIAL (comodato), nao preco -- vai para a DANFE de comodato.
R$ 1.100 e o valor do 4G: 8300, 8310, 4410, 4315, FMC130, 4305 e a linha XT40.
"""
import sqlite3
from datetime import datetime, timezone

BANCO = "/home/claude/fpsl_weso/data/fpsl.db"
V4G = 1100.0

# (modelo_weso, produto_id, descricao_harmonit, valor_patrimonial)
MAPA = [
    # ── 4G ──
    ("XT40",              338502, "XT40 - RASTREADOR VEICULAR 4G CAT1",          V4G),
    ("XT40 OBDII",        327139, "XT40 - OBDII",                                V4G),
    ("XT40 Portatil",     600266, "RASTREADOR PORTÁTIL (XT40-PORT) - CAT1 - 4G/2G", V4G),
    ("XT40-TM",           600267, "RASTREADOR VEICULAR COM TELEMETRIA (XT40-TM)", V4G),
    ("Suntech ST8300",    499910, "ST8300 (SKD)",                                V4G),
    ("Suntech ST8310UM",  320056, "ST8310UM",                                    V4G),
    ("Suntech ST4315U",   249778, "ST4315U (SKD)",                               V4G),
    ("Suntech ST4305",    233870, "ST4305 (SKD)",                                V4G),
    ("FMC130",            338497, "RASTREADOR 4G TELT FMC1304OXW01",             V4G),
    # ── 2G / demais: valor nao informado pelo usuario ──
    ("Suntech ST310",      20314, "ST310U",                                      None),
    ("Suntech ST310U",     20314, "ST310U",                                      None),
    ("Suntech ST340",       7004, "RASTREADOR ST340",                            None),
    ("Suntech ST340RB",    27241, "ST340RB",                                     None),
    ("Suntech ST300",       7006, "RASTREADOR ST300HD",                          None),
    ("Suntech ST300HD",     7006, "RASTREADOR ST300HD",                          None),
    ("Suntech ST215",       7003, "RASTREADOR ST215",                            None),
    ("Suntech ST350 LC4",   7001, "RASTREADOR ST350 LC4 4 FIOS",                 None),
    ("RST-Mini",           27296, "RST-MINI",                                    None),
    ("J16",               191322, "RASTREADOR 4G J16",                           None),
    # ── Confirmados pelo usuario em 2026-08-14 ──
    # ST940 -> RASTREADOR MOVEL, e nao "BASE IMANTADA ST940" (6987), que e o
    # acessorio. O que sustenta: os 5 ST940 instalados estao todos em placas
    # chamadas `Movel 1`, `MOVEL 2`, `MOVEL 3`, `MOVEL 4`, e o catalogo tem a
    # familia toda nesse padrao (RASTREADOR SEMI-MOVEL ST310U / ST340).
    ("Suntech ST940",       7007, "RASTREADOR MÓVEL",                            None),
    # ⚠️ APROXIMACOES, escolhidas pelo usuario por falta de produto exato:
    # ST8310 nao existe no catalogo -- vai no vizinho de cima (o UM).
    ("Suntech ST8310",    320056, "ST8310UM",                                    V4G),
    # ST340UR nao existe -- vai no RB, que e a variante com leitor.
    ("Suntech ST340UR",    27241, "ST340RB",                                     None),
    # Estes dois ja existiam no catalogo e so faltava a linha aqui. O TK-100
    # esta gravado `TK 100`, com espaco -- foi por isso que a busca por
    # "TK-100" nao achou nada e eu cheguei a dizer que nao existia.
    ("TK-100",             13644, "TK 100",                                      None),
    ("Concox CRX1",         6995, "RASTREADOR CRX1",                             None),
]

# ⚠️ DE PROPOSITO SEM PRODUTO -- nao existe equivalente no catalogo do Harmonit
# (conferido em 2026-08-14 com busca solta, nao so pelo nome exato):
#   NT2x (11 na base, 10 INSTALADOS) · Suntech ST500 (69, 3 instalados)
#   Suntech ST4945S (2, 0) · NT11 (1, 0) · Concox GT06 (1, 0)
# Sem produto a OS sai com o equipamento so na descricao -- nunca bloqueia.
#
# 🚨 COMO ACRESCENTAR UM MODELO AQUI (o caminho todo):
#   1. o produto precisa existir no Harmonit. Cadastrar la e pratica de
#      rotina, fora deste projeto (decisao do usuario, 14/08).
#   2. achar o id: `/Produto/ObterProdutos?search=<termo>` -- BUSQUE SOLTO.
#      O catalogo grava `TK 100`, `RASTREADOR MÓVEL`, `ST8310UM`; procurar
#      pelo nome que a WESO usa devolve zero e leva a concluir errado.
#   3. o nome da esquerda e o modelo COMO A WESO ESCREVE, exato -- e por ele
#      que `produto_do_modelo` casa. Conferir em:
#      sqlite3 ~/weso_cache/weso.db "SELECT DISTINCT modelo FROM rastreadores"
#   4. `valor_patrimonial` so nos 4G (V4G). Nos 2G fica None e a OS herda o
#      valor do item do contrato que esta sendo substituido.
#   5. rodar este script (e idempotente, faz UPSERT) e conferir a listagem
#      que ele imprime no fim.

con = sqlite3.connect(BANCO)
con.execute("""
CREATE TABLE IF NOT EXISTS painel_modelos_produto (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    modelo_weso         TEXT UNIQUE NOT NULL,
    harmonit_produto_id INTEGER,
    harmonit_descricao  TEXT,
    valor_patrimonial   REAL,
    criado_em           TEXT NOT NULL
)""")
con.execute("CREATE INDEX IF NOT EXISTS idx_modelo_produto "
            "ON painel_modelos_produto(modelo_weso)")

agora = datetime.now(timezone.utc).isoformat()
for modelo, pid, desc, valor in MAPA:
    con.execute("""
        INSERT INTO painel_modelos_produto
            (modelo_weso, harmonit_produto_id, harmonit_descricao, valor_patrimonial, criado_em)
        VALUES (?,?,?,?,?)
        ON CONFLICT(modelo_weso) DO UPDATE SET
            harmonit_produto_id = excluded.harmonit_produto_id,
            harmonit_descricao  = excluded.harmonit_descricao,
            valor_patrimonial   = excluded.valor_patrimonial
    """, (modelo, pid, desc, valor, agora))
con.commit()

print(f"{con.execute('SELECT COUNT(*) FROM painel_modelos_produto').fetchone()[0]} modelos no de-para\n")
for r in con.execute("SELECT modelo_weso, harmonit_produto_id, harmonit_descricao, "
                     "valor_patrimonial FROM painel_modelos_produto "
                     "ORDER BY valor_patrimonial DESC NULLS LAST, modelo_weso"):
    v = f"R$ {r[3]:.2f}" if r[3] else "—"
    print(f"  {r[0]:20s} -> {r[1]:<8} {r[2][:44]:46s} {v}")
con.close()
