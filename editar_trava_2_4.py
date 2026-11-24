# -*- coding: utf-8 -*-
"""Tarefa 2.4, as travas — e PELA ROTA, nunca pela função.

⚠️ Régua da casa: rota nova pede teste HTTP. Chamar `pagamento_servico` por
dentro deixaria a rota, o corpo e a chave sem prova.
"""
import pathlib

q = pathlib.Path("tests/teste_pagamento_rotas.py")
bq = q.read_bytes()
CRLF = b"\r\n" in bq
u = bq.decode("utf-8").replace("\r\n", "\n")

VELHO = '''    def test_auditar_lote_que_nao_existe(self, cliente):'''

NOVO = '''    def test_devolver_LOTE_sem_justificativa(self, cliente):
        """🔵 *"com justificativa unica"* -- e sem ela nao se devolve, igual ao
        de um item: os itens ficariam laranjas e mudos na coluna 1."""
        cliente.post("/api/pagamento/varrer", json={"horas": None},
                     headers=CAB)
        aid = _id_do_artefato()
        lote = cliente.post("/api/pagamento/preparar", headers=CAB,
                            json={"artefatos": [{"id": aid}]}
                            ).json()["lotes"][0]
        r = cliente.post("/api/pagamento/devolver-lote", headers=CAB,
                         json={"lote_id": lote, "justificativa": "  "})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert "justificativa" in r.json()["motivo"]

    def test_devolver_LOTE_que_nao_existe(self, cliente):
        r = cliente.post("/api/pagamento/devolver-lote", headers=CAB,
                         json={"lote_id": 999999, "justificativa": "zz"})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert "nao existe" in r.json()["motivo"]

    def test_devolver_LOTE_vazio_diz_que_esta_vazio(self, cliente):
        """⚠️ Nao e erro, e nao e "ok" tambem: um "ok" que nao mexeu em nada
        faria o operador achar que devolveu."""
        cliente.post("/api/pagamento/varrer", json={"horas": None},
                     headers=CAB)
        aid = _id_do_artefato()
        lote = cliente.post("/api/pagamento/preparar", headers=CAB,
                            json={"artefatos": [{"id": aid}]}
                            ).json()["lotes"][0]
        cliente.post("/api/pagamento/devolver", headers=CAB,
                     json={"artefato_id": aid, "justificativa": "zz um"})
        r = cliente.post("/api/pagamento/devolver-lote", headers=CAB,
                         json={"lote_id": lote, "justificativa": "zz dois"})
        assert r.json()["ok"] is False
        assert r.json()["devolvidos"] == 0
        assert "nao tem item" in r.json()["motivo"]

    def test_auditar_lote_que_nao_existe(self, cliente):'''

assert VELHO in u and u.count(VELHO) == 1
u = u.replace(VELHO, NOVO, 1)
print("  ok: as 3 travas de recusa da 2.4")

# E o caminho feliz, no fluxo que ja atravessa as cinco colunas.
VELHO2 = '''        assert cliente.post("/api/pagamento/enviar", headers=CAB,
                            json={"lote_id": lote}).json()["ok"] is True
        q = cliente.get("/api/pagamento/quadro", headers=CAB).json()
        assert q["colunas"][4]["total"] == 1'''

NOVO2 = '''        assert cliente.post("/api/pagamento/enviar", headers=CAB,
                            json={"lote_id": lote}).json()["ok"] is True
        q = cliente.get("/api/pagamento/quadro", headers=CAB).json()
        assert q["colunas"][4]["total"] == 1

        # ---- TAREFA 2.4: excluir o card inteiro, da ULTIMA coluna
        # 🔵 *"Excluir o card inteiro devolvendo tudo a coluna 1, com
        # justificativa unica"*.
        # 🚨 Daqui, da coluna 5, de proposito: e o caso mais duro -- o arquivo
        # ja foi montado e marcado como enviado, e e onde um "sempre para a
        # anterior" estragaria tudo. 🔵 Dele: *"nao retorna para a anterior e
        # sim para o 1"*.
        r = cliente.post("/api/pagamento/devolver-lote", headers=CAB, json={
            "lote_id": lote, "justificativa": "zz lote inteiro de volta",
            "por": "Zz Teste"})
        assert r.json()["ok"] is True, r.json()
        assert r.json()["devolvidos"] == 1, r.json()
        assert r.json()["para"] == "movimentacao"
        q = cliente.get("/api/pagamento/quadro", headers=CAB).json()
        # O lote SAI do quadro sozinho: os cards vem dos artefatos.
        assert q["colunas"][4]["total"] == 0, q["colunas"][4]
        assert q["colunas"][0]["total"] == 1, q["colunas"][0]
        # 🚨 A JUSTIFICATIVA VAI NO ITEM, e o semaforo fica laranja: e o que o
        # card da coluna 1 mostra. Guardar so no lote deixaria o item mudo.
        item = q["colunas"][0]["cards"][0]["artefatos"][0]
        assert item["semaforo"] == "laranja", item
        assert item["justificativa"] == "zz lote inteiro de volta", item
        # ⚠️ E o ciente SAI: o artefato volta ao comeco, e herdar um ciente
        # dado sobre outro estado seria confirmar o que ninguem olhou.
        assert not item.get("ciente_em"), item'''

assert VELHO2 in u and u.count(VELHO2) == 1
u = u.replace(VELHO2, NOVO2, 1)
print("  ok: o caminho feliz da 2.4, da coluna 5")

saida = u.replace("\n", "\r\n") if CRLF else u
q.write_bytes(saida.encode("utf-8"))
print("gravado:", q, len(saida), "bytes")
