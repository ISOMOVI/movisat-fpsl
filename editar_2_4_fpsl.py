# -*- coding: utf-8 -*-
"""Tarefa 2.4, lado FPSL — excluir o card inteiro com justificativa ÚNICA.

🔵 DELE: *"Excluir o card inteiro devolvendo tudo à coluna 1, com justificativa
única"*.

🚨 A REGRA NÃO SE REESCREVE: o que cada artefato sofre é exatamente o que o
`devolver` de um já faz -- volta para a coluna 1, fica laranja, guarda a
justificativa e **perde o ciente**. Um segundo UPDATE com a mesma intenção
divergiria do primeiro na primeira mudança. Então o laço chama a mesma função.

⚠️ UM EVENTO POR ARTEFATO, e mais um do LOTE: o histórico de cada artefato tem
de dizer por que ele voltou (é ele que carrega a justificativa), e o evento do
lote é o que permite responder depois *"quem esvaziou este lote?"*.

⚠️ O LOTE NÃO É APAGADO. Ele fica como registro e **sai do quadro sozinho**,
porque o quadro monta os cards a partir dos ARTEFATOS (`colunas()`): lote sem
artefato não aparece. Apagar a linha perderia o rastro de que ele existiu.
"""
import pathlib

ALVOS = {}


def abrir(rel):
    p = pathlib.Path(rel)
    bruto = p.read_bytes()
    ALVOS[rel] = {"p": p, "crlf": b"\r\n" in bruto,
                  "t": bruto.decode("utf-8").replace("\r\n", "\n")}
    return rel


def troca(rel, velho, novo, rotulo):
    d = ALVOS[rel]
    assert velho in d["t"], "NAO ACHOU (%s)" % rotulo
    assert d["t"].count(velho) == 1, "AMBIGUO %dx (%s)" % (
        d["t"].count(velho), rotulo)
    d["t"] = d["t"].replace(velho, novo, 1)
    print("  ok:", rotulo)


# ===========================================================================
# 1. O SERVIÇO
# ===========================================================================
SV = abrir("fpsl_weso/services/pagamento_servico.py")

troca(SV,
      '''def auditar(lote_id: int, *, por: str | None = None) -> dict:''',
      '''def devolver_lote(lote_id: int, justificativa: str, *,
                  por: str | None = None) -> dict:
    """🔵 *"Excluir o card inteiro devolvendo tudo à coluna 1, com
    justificativa única"* -- tarefa 2.4.

    🚨 **CHAMA O `devolver` DE UM, ARTEFATO POR ARTEFATO**, e isto é o ponto:
    o que acontece com cada um (coluna 1, laranja, justificativa, ciente
    apagado) é regra dele, já escrita e já travada. Repetir o UPDATE aqui
    criaria uma segunda verdade que divergiria na primeira mudança -- foi
    exatamente o que o `operacoes_retirada` do FPSL existe para evitar.

    ⚠️ **A JUSTIFICATIVA É UMA, e vai em TODOS:** é o pedido dele. Cada
    artefato guarda o mesmo texto, porque é o artefato que o mostra laranja no
    card da coluna 1 -- guardar só no lote deixaria os itens laranjas e mudos.

    ⚠️ **O LOTE FICA**, como registro, e sai do quadro sozinho: `colunas()`
    monta os cards a partir dos artefatos, então lote sem artefato não
    aparece. Apagar a linha perderia o rastro de que ele existiu.
    """
    texto = (justificativa or "").strip()
    if not texto:
        return {"ok": False,
                "motivo": "excluir o card exige a justificativa: ela vai em "
                          "todos os itens, e laranja sem motivo e cor sem "
                          "informacao"}
    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        lote = conn.execute(
            "SELECT id, coluna FROM pagamento_lote WHERE id = ?",
            (lote_id,)).fetchone()
        if not lote:
            return {"ok": False, "motivo": "lote nao existe"}
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM pagamento_artefato "
            " WHERE lote_id = ? AND coluna <> 'movimentacao' "
            " ORDER BY id", (lote_id,)).fetchall()]
        de = lote[1]
    if not ids:
        # ⚠️ Não é erro: o card já está vazio, e dizer isso é melhor que um
        # "ok" que não mexeu em nada.
        return {"ok": False, "devolvidos": 0,
                "motivo": "este lote nao tem item para devolver"}

    devolvidos, recusados = [], []
    for artefato_id in ids:
        r = devolver(artefato_id, texto, por=por)
        (devolvidos if r.get("ok") else recusados).append(
            artefato_id if r.get("ok") else (artefato_id, r.get("motivo")))

    with storage._connect() as conn:
        pagamento_tabelas.criar(conn)
        # 🚨 O EVENTO DO LOTE, além do de cada artefato: é o que responde
        # depois *"quem esvaziou este lote, e por quê?"*. Sem ele, a resposta
        # estaria espalhada em N linhas de artefato.
        _evento(conn, artefato_id=None, lote_id=lote_id,
                acao="devolver_lote", de=de, para="movimentacao",
                detalhe="%d item(ns): %s" % (len(devolvidos), texto), por=por)
        conn.commit()
    return {"ok": bool(devolvidos), "devolvidos": len(devolvidos),
            "recusados": recusados, "de": de, "para": "movimentacao"}


def auditar(lote_id: int, *, por: str | None = None) -> dict:''',
      "1. o servico devolver_lote")


# ===========================================================================
# 2. A ROTA DA PONTE
# ===========================================================================
PT = abrir("fpsl_weso/routers/pagamento_ponte.py")

troca(PT,
      '''class UmLote(BaseModel):
    lote_id: int = Field(..., ge=1)
    por: str | None = None''',
      '''class UmLote(BaseModel):
    lote_id: int = Field(..., ge=1)
    por: str | None = None


class DevolverLote(UmLote):
    # ⚠️ Mesma regra do artefato: sem justificativa não se devolve, e quem
    # decide isso é o serviço -- aqui só se transporta.
    justificativa: str = ""''',
      "2a. o corpo da rota nova")

troca(PT,
      '''@router.post("/auditar")''',
      '''@router.post("/devolver-lote")
def devolver_lote(entrada: DevolverLote):
    """🔵 *"Excluir o card inteiro devolvendo tudo à coluna 1, com
    justificativa única"* -- tarefa 2.4. 🚨 Sempre para a coluna 1, e a mesma
    justificativa em todos os itens."""
    return pagamento_servico.devolver_lote(
        entrada.lote_id, entrada.justificativa, por=entrada.por)


@router.post("/auditar")''',
      "2b. POST /devolver-lote")


for rel, d in ALVOS.items():
    saida = d["t"].replace("\n", "\r\n") if d["crlf"] else d["t"]
    d["p"].write_bytes(saida.encode("utf-8"))
    print("gravado:", rel, len(saida), "bytes")
