# -*- coding: utf-8 -*-
import asyncio
import sys
import sqlite3
sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso import harmonit_client as hc

DB_PATH = "/home/claude/fpsl_weso/data/fpsl.db"


async def main():
    await hc.start_harmonit_client()
    try:
        # esquenta o token
        await hc.harmonit_get("/ObterSituacaoCliente")

        print("Buscando rastreadores do Harmonit...")
        r = await hc._client.post("/Rastreador/ObterRastreadores", json={}, headers=hc._headers())
        rastreadores = r.json().get("data") or []
        print(f"  total: {len(rastreadores)}")

        print("Buscando SIM Cards do Harmonit...")
        # NOTA (02/07/2026): skip/take documentados mas ignorados pelo servidor -- sempre retorna tudo numa chamada so.
        r = await hc._client.post(
            "/SIMCard/ObterSIMCards",
            params={"skip": 0, "take": 5000},
            json={},
            headers=hc._headers(),
        )
        body = r.json()
        data = body.get("data")
        simcards = data if isinstance(data, list) else (data.get("lista") if isinstance(data, dict) else None) or []
        print(f"  total simcards: {len(simcards)}")

    finally:
        await hc.stop_harmonit_client()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS harmonit_rastreadores")
    cur.execute("""
    CREATE TABLE harmonit_rastreadores (
        id INTEGER PRIMARY KEY,
        equipamento TEXT,
        instalado INTEGER,
        ativar INTEGER,
        simcard_id INTEGER,
        numero_chip TEXT,
        numero_linha TEXT,
        modelo_equipamento_id INTEGER,
        modelo_equipamento TEXT,
        veiculo_id INTEGER,
        veiculo TEXT,
        placa TEXT,
        contato TEXT
    )
    """)
    for x in rastreadores:
        cur.execute(
            "INSERT OR REPLACE INTO harmonit_rastreadores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                x.get("id"), x.get("equipamento"), int(bool(x.get("instalado"))), int(bool(x.get("ativar"))),
                x.get("simCardId"), x.get("numeroChip"), x.get("numeroLinha"),
                x.get("modeloEquipamentoId"), x.get("modeloEquipamento"),
                x.get("veiculoId"), x.get("veiculo"), x.get("placa"), x.get("contato"),
            ),
        )

    cur.execute("DROP TABLE IF EXISTS harmonit_simcards")
    cur.execute("""
    CREATE TABLE harmonit_simcards (
        id INTEGER PRIMARY KEY,
        numero_chip TEXT,
        numero_linha TEXT,
        operadora_id INTEGER
    )
    """)
    for x in simcards:
        cur.execute(
            "INSERT OR REPLACE INTO harmonit_simcards VALUES (?,?,?,?)",
            (x.get("id"), x.get("numeroChip"), x.get("numeroLinha"), x.get("operadoraId")),
        )

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM harmonit_rastreadores")
    print("\nharmonit_rastreadores salvos:", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM harmonit_simcards")
    print("harmonit_simcards salvos:", cur.fetchone()[0])
    conn.close()


asyncio.run(main())
