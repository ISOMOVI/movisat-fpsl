"""Painel de demandas (painel rápido) — o roteador em uso real que não tinha teste.

🚨 POR QUE ESTE ARQUIVO EXISTE. O painel de demandas está em uso de verdade,
compartilhado por link e sem login, e até 2026-08-14 tinha ZERO teste. Os três
defeitos de 07/08 (pessoa_id nulo dando 422 em todo card, carimbo em UTC e o
card com prazo no ano 0002) só apareceram porque alguém usou. Este teste trava
cada um deles, mais a esteira, que é a regra de negócio do quadro.

⚠️ CRIA O PRÓPRIO QUADRO E APAGA NO FIM. Nunca toca nos quadros reais — o
Comercial Interno × Externo e o Cronograma de Tarefas estão em uso. O título
leva um marcador para ser reconhecível se algum dia sobrar.

Roda na VPS: venv/bin/python tests/teste_demandas.py
Não toca Harmonit nem WESO. Fala HTTP com o serviço local (porta 8004).
"""
import pathlib
import random
import sqlite3
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso import demandas  # noqa: E402

BASE = "http://127.0.0.1:8004"
# 🚨 A paleta é FECHADA. Uso a própria constante do módulo em vez de repetir os
# valores aqui -- duas listas da mesma coisa divergem, e o teste passaria a
# reprovar por causa da cópia, não do defeito.
COR_A = demandas.PALETA[0]
COR_B = demandas.PALETA[1]
MARCADOR = "zz_teste_demandas"
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def limpar():
    """Apaga tudo que este teste criou. ON DELETE CASCADE cuida dos filhos."""
    with sqlite3.connect(demandas.BANCO, timeout=10) as c:
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("DELETE FROM demanda_quadro WHERE titulo LIKE ?", (f"{MARCADOR}%",))


limpar()
q = demandas.criar_quadro(f"{MARCADOR} — apagar se sobrar", modo="esteira")
TOKEN = q["token"]
API = f"{BASE}/demandas/api/{TOKEN}"

# 🚨 O LIMITADOR É POR IP: 60 escritas por minuto. Este teste faz ~30, então
# duas execuções seguidas dentro do mesmo minuto estouravam o teto e o teste
# reprovava sozinho -- o 429 na criação do card deixava `item1` nulo e as
# chamadas seguintes viravam 422 em `/item/None`, o que parece defeito de
# prazo e não é. Descoberto rodando o teste duas vezes em 14/08.
#
# ⚠️ Faixa 203.0.113.0/24 é TEST-NET-3 (RFC 5737): reservada para
# documentação, nunca é IP de gente de verdade. Assim o teste não rouba a cota
# de ninguém nem herda a de ninguém.
IP_TESTE = f"203.0.113.{random.randint(1, 254)}"
cli = httpx.Client(timeout=15, headers={"X-Real-IP": IP_TESTE})

try:
    # ── 1. leitura e token ───────────────────────────────────────────────────
    print("\n[1] leitura e token")
    r = cli.get(API)
    checar("quadro novo responde 200", 200, r.status_code)
    checar("veio o título certo", f"{MARCADOR} — apagar se sobrar", r.json().get("titulo"))
    checar("quadro novo nasce vazio", 0, len(r.json().get("frentes") or []))

    # 🚨 TOKEN MORTO TEM DE DAR 404 NA API. Na página ele cai na esteira com
    # 200, o que faz um quadro revogado parecer "painel desativado" -- só a API
    # distingue. Registrado na memória do painel rápido.
    checar("token inexistente -> 404", 404,
           cli.get(f"{BASE}/demandas/api/naoexisteesse").status_code)

    # ── 2. pessoa: recusa COM MOTIVO ─────────────────────────────────────────
    # 🚨 "não deu" faz a pessoa tentar de novo igual. Cada recusa tem código e
    # texto próprios.
    print("\n[2] pessoa — cada recusa com o seu motivo")
    r = cli.post(f"{API}/pessoa", json={"nome": "Fulano", "cor": COR_A})
    checar("cria pessoa", 200, r.status_code)
    pessoa_id = r.json().get("id")
    checar("devolve o id da pessoa", True, isinstance(pessoa_id, int))

    checar("nome repetido -> 409", 409,
           cli.post(f"{API}/pessoa", json={"nome": "Fulano", "cor": COR_B}).status_code)
    checar("cor em uso -> 409", 409,
           cli.post(f"{API}/pessoa", json={"nome": "Beltrano", "cor": COR_A}).status_code)
    checar("cor fora da paleta -> 422", 422,
           cli.post(f"{API}/pessoa", json={"nome": "Beltrano", "cor": "#ABCDEF"}).status_code)

    # ── 3. o defeito de 07/08: pessoa_id nulo ────────────────────────────────
    # 🚨 `fecharModal()` zerava o `sel` ANTES de ler `sel.pessoa`, e o card ia
    # sem responsável -> 422 em TODO card e TODA etapa. O backend tem de
    # recusar de forma clara, não estourar.
    print("\n[3] responsável ausente não passa em silêncio")
    r = cli.post(f"{API}/frente", json={"nome": "Assunto de teste"})
    checar("cria frente", 200, r.status_code)
    frente_id = r.json().get("id")

    r = cli.post(f"{API}/item", json={"frente_id": frente_id, "titulo": "Card 1",
                                      "pessoa_id": None})
    checar("card sem responsável é recusado", True, r.status_code in (404, 422))
    r = cli.post(f"{API}/item", json={"frente_id": frente_id, "titulo": "Card 1",
                                      "pessoa_id": 999999})
    checar("responsável de outro quadro é recusado", 404, r.status_code)

    r = cli.post(f"{API}/item", json={"frente_id": frente_id, "titulo": "Card 1",
                                      "pessoa_id": pessoa_id})
    checar("card com responsável entra", 200, r.status_code)
    item1 = r.json().get("id")

    # ── 4. o defeito do ano 0002 ─────────────────────────────────────────────
    # 🚨 O prazo é comparado como TEXTO (`prazo < hoje`), então ano 0002 fica
    # atrasado para sempre e ano 9999 fica eternamente no prazo. A causa raiz
    # era o `input type="date"`, que monta os campos na ordem do idioma do
    # navegador e salva a cada tecla.
    print("\n[4] prazo — o ano tem de fazer sentido")
    def prazo(v):
        return cli.post(f"{API}/item/{item1}",
                        json={"prazo": v, "sem_prazo": False, "quem": "teste"})

    checar("prazo válido entra", 200, prazo("2026-09-30").status_code)
    checar("ano 0002 é recusado", 422, prazo("0002-08-11").status_code)
    checar("ano 9999 é recusado", 422, prazo("9999-01-01").status_code)
    checar("texto que não é data é recusado", 422, prazo("31/02/2026").status_code)
    checar("data inexistente é recusada", 422, prazo("2026-02-31").status_code)
    checar("prazo pode ser limpo", 200,
           cli.post(f"{API}/item/{item1}",
                    json={"prazo": None, "sem_prazo": True, "quem": "teste"}).status_code)

    # ── 5. o defeito do carimbo em UTC ───────────────────────────────────────
    # 🚨 `datetime('now')` do SQLite é UTC, 3h à frente. 14 carimbos foram
    # corrigidos em 07/08. A constante AGORA existe para isso.
    print("\n[5] carimbo em hora local, não UTC")
    cli.post(f"{API}/item/{item1}", json={"prazo": "2026-09-30", "sem_prazo": False,
                                          "obs": "carimbo", "quem": "teste"})
    with sqlite3.connect(demandas.BANCO, timeout=10) as c:
        gravado = c.execute("SELECT atualizado_em, atualizado_por FROM demanda_item "
                            "WHERE id=?", (item1,)).fetchone()
        agora_local = c.execute("SELECT datetime('now','localtime')").fetchone()[0]
        agora_utc = c.execute("SELECT datetime('now')").fetchone()[0]
    checar("gravou quem alterou", "teste", gravado[1])
    checar("o carimbo é a hora LOCAL", agora_local[:13], (gravado[0] or "")[:13])
    checar("e a hora local difere da UTC (senão o teste não prova nada)", True,
           agora_local[:13] != agora_utc[:13])

    # ── 6. a esteira ─────────────────────────────────────────────────────────
    # 🚨 CONFERIDA NO BACKEND. A tela trava o campo, mas quem tem o link tem o
    # endereço da rota -- desabilitar no HTML nunca impediu ninguém.
    print("\n[6] a esteira segura o card de baixo")
    r = cli.post(f"{API}/etapa", json={"item_id": item1, "descricao": "Etapa 1",
                                       "pessoa_id": pessoa_id})
    checar("cria etapa", 200, r.status_code)
    etapa1 = r.json().get("id")

    r = cli.post(f"{API}/item", json={"frente_id": frente_id, "titulo": "Card 2",
                                      "pessoa_id": pessoa_id})
    item2 = r.json().get("id")
    checar("card 2 preso pela esteira -> 409", 409,
           cli.post(f"{API}/item/{item2}",
                    json={"prazo": "2026-10-10", "sem_prazo": False,
                          "quem": "teste"}).status_code)

    # ⚠️ TODO CARD NASCE COM UMA ETAPA. Medido em 14/08 escrevendo este teste:
    # `criar_item` já insere uma etapa junto, então o card acima tem DUAS --
    # a automática e a que acabei de criar. Concluir só uma deixa a esteira
    # travada, corretamente. Eu tinha suposto que o card nascia sem nenhuma.
    def etapas_do_card(item_id):
        for fr in cli.get(API).json().get("frentes") or []:
            for it in fr.get("itens") or []:
                if it["id"] == item_id:
                    return it.get("etapas") or []
        return []

    checar("o card nasce com 1 etapa automática + a que criei", 2,
           len(etapas_do_card(item1)))
    checar("concluir só UMA das etapas não libera", 409,
           (cli.post(f"{API}/etapa/{etapa1}", json={"concluida": True, "quem": "teste"}),
            cli.post(f"{API}/item/{item2}",
                     json={"prazo": "2026-10-10", "sem_prazo": False,
                           "quem": "teste"}))[1].status_code)

    for et in etapas_do_card(item1):
        cli.post(f"{API}/etapa/{et['id']}", json={"concluida": True, "quem": "teste"})
    checar("com TODAS concluídas, o card 2 libera", 200,
           cli.post(f"{API}/item/{item2}",
                    json={"prazo": "2026-10-10", "sem_prazo": False,
                          "quem": "teste"}).status_code)

    # ── 7. o CHECK do banco ──────────────────────────────────────────────────
    # ⚠️ CHECK é contrato: etapa concluída SEM data, ou data sem concluída,
    # nao podem existir. Quem garante e o banco, nao a rota.
    print("\n[7] etapa concluída tem de ter data")
    with sqlite3.connect(demandas.BANCO, timeout=10) as c:
        et = c.execute("SELECT concluida, concluida_em FROM demanda_etapa "
                       "WHERE id=?", (etapa1,)).fetchone()
        checar("concluída = 1 e com data", True, bool(et[0]) and bool(et[1]))
        erro = None
        try:
            c.execute("UPDATE demanda_etapa SET concluida=1, concluida_em=NULL "
                      "WHERE id=?", (etapa1,))
        except sqlite3.IntegrityError as exc:
            erro = str(exc)
        checar("o banco recusa concluída sem data", True, erro is not None)

    # ── 8. renomear, trocar responsável, cancelar, apagar ────────────────────
    print("\n[8] o resto das ações")
    checar("renomeia o card", 200,
           cli.post(f"{API}/item/{item1}/titulo",
                    json={"titulo": "Card 1 renomeado", "quem": "teste"}).status_code)
    r = cli.post(f"{API}/pessoa", json={"nome": "Sicrano", "cor": COR_B})
    outra = r.json().get("id")
    checar("troca o responsável", 200,
           cli.post(f"{API}/item/{item1}/responsavel",
                    json={"pessoa_id": outra, "quem": "teste"}).status_code)
    checar("cancela o card", 200,
           cli.post(f"{API}/item/{item1}/cancelar",
                    json={"cancelado": True}).status_code)
    checar("apaga o card 2", 200,
           cli.post(f"{API}/item/{item2}/apagar").status_code)
    checar("apaga a frente", 200,
           cli.post(f"{API}/frente/{frente_id}/apagar").status_code)
    checar("a frente sumiu do quadro", 0, len(cli.get(API).json().get("frentes") or []))

    # ── 9. nada disso vaza para outro quadro ─────────────────────────────────
    # 🚨 O token identifica o quadro, e TODA consulta filtra por quadro_id. Um
    # id de item de outro quadro nao pode ser tocado com este token.
    print("\n[9] o token não alcança quadro alheio")
    outro = demandas.criar_quadro(f"{MARCADOR} vizinho", modo="planilha")
    r = cli.post(f"{BASE}/demandas/api/{outro['token']}/frente",
                 json={"nome": "Assunto do vizinho"})
    fv = r.json().get("id")
    r = cli.post(f"{BASE}/demandas/api/{outro['token']}/pessoa",
                 json={"nome": "Vizinho", "cor": COR_A})
    pv = r.json().get("id")
    r = cli.post(f"{BASE}/demandas/api/{outro['token']}/item",
                 json={"frente_id": fv, "titulo": "Card do vizinho", "pessoa_id": pv})
    item_vizinho = r.json().get("id")
    checar("item do vizinho não se altera com o meu token", 409,
           cli.post(f"{API}/item/{item_vizinho}",
                    json={"prazo": "2026-10-10", "sem_prazo": False,
                          "quem": "invasor"}).status_code)
    checar("nem se apaga", True,
           cli.post(f"{API}/item/{item_vizinho}/apagar").status_code in (403, 404, 409))
    checar("e continua lá", 1,
           len(cli.get(f"{BASE}/demandas/api/{outro['token']}")
               .json()["frentes"][0]["itens"]))

    # ── 10. o limitador de escrita ───────────────────────────────────────────
    # 🚨 O quadro é aberto por LINK, sem login. O limitador é a única coisa
    # entre ele e quem resolver fazer barulho na rota. 60 escritas por minuto
    # por IP -- aqui gasto a cota de um IP próprio, para não derrubar o resto
    # do teste nem a cota de alguém real.
    print("\n[10] o limitador de escrita protege o quadro aberto")
    ip_bruto = f"203.0.113.{random.randint(1, 254)}"
    with httpx.Client(timeout=15, headers={"X-Real-IP": ip_bruto}) as bruto:
        codigos = [bruto.post(f"{API}/frente", json={"nome": f"F{n}"}).status_code
                   for n in range(65)]
    checar("as primeiras passam", True, codigos[0] == 200)
    checar("o teto corta em 429", True, 429 in codigos)
    checar("cortou perto de 60, não muito antes", True,
           55 <= codigos.index(429) <= 62)
    # ⚠️ e o limitador NÃO contamina outro IP -- senão um abusivo derrubaria
    # o quadro para todo mundo.
    checar("outro IP continua escrevendo", 200,
           cli.post(f"{API}/frente", json={"nome": "Depois do teto"}).status_code)

finally:
    cli.close()
    limpar()
    # 🚨 A prova de que limpou é RELER, não o retorno do DELETE.
    with sqlite3.connect(demandas.BANCO, timeout=10) as c:
        sobrou = c.execute("SELECT COUNT(*) FROM demanda_quadro WHERE titulo LIKE ?",
                           (f"{MARCADOR}%",)).fetchone()[0]
    checar("nenhum quadro de teste sobrou", 0, sobrou)

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
