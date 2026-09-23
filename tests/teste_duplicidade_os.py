"""Duplicidade de OS, Histórico conferido e semáforo -- 2026-09-23.

Nasceu da auditoria "mostrado × real" de 23/09, nas 131 OS do registro:
  - o termo 8872 gerou 11 OS DUAS VEZES no mesmo lote (19:34 e 19:37 UTC de
    15/09), e o 8883 gerou em dois lotes, em dias seguidos;
  - 13 OS que o Histórico mostrava "criado" não existiam mais no Harmonit;
  - OS com material recusado voltava verde e era gravada `criado`.

O que este teste prende:
  C1  um lote gera UMA vez (registro e envio simultâneo);
  N1  o termo que já gerou noutro lote só gera de novo com confirmação --
      e as apagadas não travam;
  C2  "não encontrada" vira `apagada`; falha de leitura NÃO vira apagada;
  C3  o semáforo: verde, amarelo (gravado `criado_incompleto`), vermelho;
  e as duas TELAS, dirigidas num DOM de mentira.

🚨 BANCO TEMPORÁRIO. `storage.DB_PATH` é trocado por um arquivo em /tmp antes
de qualquer escrita -- lote de mentira não entra no banco de produção.
Nenhuma chamada ao Harmonit: as funções que falariam com ele viram dublês.

Roda na VPS: venv/bin/python tests/teste_duplicidade_os.py
"""
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path("/home/claude/fpsl_weso")
sys.path.insert(0, str(RAIZ))

from fastapi import HTTPException                                  # noqa: E402
from fpsl_weso import storage                                      # noqa: E402

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
PRODUCAO = storage.DB_PATH
storage.DB_PATH = pathlib.Path(_tmp.name)

from fpsl_weso.painel import operacoes_config as cfg               # noqa: E402
from fpsl_weso.painel import operacoes_os as oos                   # noqa: E402
from fpsl_weso.painel import operacoes_registro as reg             # noqa: E402
from fpsl_weso.painel.routers import operacoes_router as R         # noqa: E402

ok, achados = 0, []


def checar(nome, cond, detalhe=""):
    global ok
    if cond:
        ok += 1
        print(f"  OK   {nome}")
    else:
        achados.append(nome)
        print(f"  FALHA {nome}" + (f"  -- {detalhe}" if detalhe else ""))


def rodar(c):
    return asyncio.run(c)


def corpo(lote, termo="T-9999", perfil="aditivo", **kw):
    return oos.MontarInput(perfil=perfil, cliente_id=1, lote=lote, termo=termo,
                           produto_servico_id=6966, confirmar=True,
                           placas=[oos.PlacaOS(placa="TST 0E55")], **kw)


def recusa(c):
    try:
        rodar(c)
        return None
    except HTTPException as e:
        return e


try:
    checar("o banco é o temporário, não o de produção",
           storage.DB_PATH != PRODUCAO and str(storage.DB_PATH).startswith("/tmp"))

    # ── o registro ───────────────────────────────────────────────────────────
    print("\n== o registro ==")
    A = rodar(reg.abrir_lote("t", "aditivo", "T-9999", "1"))
    B = rodar(reg.abrir_lote("t", "aditivo", "T-9999", "1"))
    rodar(reg.registrar(A, 4, "harmonit", "criado", placa_gravada="TST 0E55", id_externo=111))
    rodar(reg.registrar(A, 4, "harmonit", "criado_incompleto", placa_gravada="TST 0G78",
                        id_externo=222, erro="materiais recusados: X"))
    rodar(reg.registrar(A, 4, "harmonit", "falhou", placa_gravada="TST 0H99"))
    checar("`criado_incompleto` é ação aceita (não vira `desconhecido`)",
           [p["acao"] for p in rodar(reg.passos(A))][1] == "criado_incompleto")
    checar("as OS do lote: criada e incompleta contam, falhou não",
           [o["os_id"] for o in rodar(reg.os_criadas(lote=A))] == [111, 222])
    checar("as OS do termo, fora do lote atual",
           len(rodar(reg.os_criadas(termo="T-9999", exceto_lote=B))) == 2
           and rodar(reg.os_criadas(termo="T-9999", exceto_lote=A)) == [])
    lista = {l["lote"]: l for l in rodar(reg.listar_lotes(10))}
    checar("a lista do Histórico conta a incompleta como OS criada",
           lista[A]["os_criadas"] == 2, lista[A]["os_criadas"])

    # ── C2: o que o Harmonit diz ─────────────────────────────────────────────
    print("\n== C2: existe, apagada, não conferida ==")
    original_get = R.harmonit_get

    async def _get(path, params=None):
        i = (params or {}).get("osId")
        if i == 111:
            return {"data": {"numeroOrdem": 16001, "statusStr": "Nova"}}
        if i == 222:
            raise HTTPException(502, "Harmonit: Ordem de Serviço não encontrada")
        raise HTTPException(502, "Harmonit: timeout")
    R.harmonit_get = _get
    try:
        e1, e2, e3 = (rodar(R._os_no_harmonit(i)) for i in (111, 222, 333))
        l = rodar(R.ler_lote(A, conferir=True))
        l_sem = rodar(R.ler_lote(A, conferir=False))
    finally:
        R.harmonit_get = original_get
    checar("existe, com o número", e1 == {"estado": "existe", "numero": 16001, "status": "Nova"})
    checar("'não encontrada' vira apagada", e2["estado"] == "apagada")
    checar("timeout NÃO vira apagada", e3["estado"] == "nao_conferida")
    etapa4 = [p for p in l["passos"] if p["etapa"] == 4]
    checar("/lote?conferir=1 marca cada OS",
           [(p.get("no_harmonit"), p.get("numero_os")) for p in etapa4]
           == [("existe", 16001), ("apagada", None), (None, None)],
           [(p.get("no_harmonit"), p.get("numero_os")) for p in etapa4])
    checar("sem `conferir`, não pergunta ao Harmonit (a retomada fica rápida)",
           not any("no_harmonit" in p for p in l_sem["passos"]))

    # ── N1: o termo que já gerou ─────────────────────────────────────────────
    print("\n== N1: o termo que já gerou noutro lote ==")
    orig_os = R._os_no_harmonit
    estados = {111: {"estado": "existe", "numero": 16001, "status": "Nova"},
               222: {"estado": "apagada", "numero": None, "status": None}}

    async def _os(i):
        return estados[i]
    R._os_no_harmonit = _os
    try:
        j = rodar(R._ja_gerado(corpo(B), cfg.PERFIS["aditivo"]))
        checar("trava, com a OS que existe e a apagada só contada",
               j["trava"] and [e["numero"] for e in j["existentes"]] == [16001]
               and j["apagadas"] == 1, j)
        estados[111] = {"estado": "apagada", "numero": None, "status": None}
        j = rodar(R._ja_gerado(corpo(B), cfg.PERFIS["aditivo"]))
        checar("todas apagadas: informa, NÃO trava", j and not j["trava"] and j["apagadas"] == 2, j)
        estados[111] = {"estado": "nao_conferida", "numero": None, "status": None}
        j = rodar(R._ja_gerado(corpo(B), cfg.PERFIS["aditivo"]))
        checar("não conferida conta como existente (trava)", j and j["trava"], j)
        checar("perfil sem termo não se aplica",
               rodar(R._ja_gerado(corpo(B, perfil="manutencao_local"),
                                  cfg.PERFIS["manutencao_local"])) is None)
        checar("termo novo não se aplica",
               rodar(R._ja_gerado(corpo(B, termo="T-7777"), cfg.PERFIS["aditivo"])) is None)
        estados[111] = {"estado": "existe", "numero": 16001, "status": "Nova"}

        # A rota inteira, com a gravação trocada por dublê.
        orig_prep, orig_grav = R._preparar, R._gravar_as_os

        async def _prep(body):
            return {"perfil": cfg.PERFIS[body.perfil], "pendentes": []}

        gravou = []

        async def _grav(body, pre):
            gravou.append(body.lote)
            checar("durante a gravação o lote está marcado 'gerando'", body.lote in R._gerando)
            return {"gravado": True}
        R._preparar, R._gravar_as_os = _prep, _grav
        try:
            e = recusa(R.gerar_os(corpo(B), None))
            checar("sem confirmar: 409, e diz o número da OS",
                   e is not None and e.status_code == 409 and "16001" in e.detail,
                   e and e.detail)
            r = rodar(R.gerar_os(corpo(B, confirmar_duplicado=True), None))
            checar("com confirmar_duplicado: grava", r == {"gravado": True} and gravou == [B])
            checar("e solta o lote no fim", B not in R._gerando)

            # ── C1 ───────────────────────────────────────────────────────────
            print("\n== C1: um lote gera uma vez ==")
            e = recusa(R.gerar_os(corpo(A, confirmar_duplicado=True), None))
            checar("lote que já gerou: 409, e manda começar outra rodada",
                   e is not None and e.status_code == 409 and "já gerou 2 OS" in e.detail,
                   e and e.detail)
            C = rodar(reg.abrir_lote("t", "aditivo", "T-8888", "1"))
            R._gerando.add(C)
            e = recusa(R.gerar_os(corpo(C, termo="T-8888"), None))
            R._gerando.discard(C)
            checar("envio simultâneo do mesmo lote: 409 'já está gerando'",
                   e is not None and e.status_code == 409 and "já está gerando" in e.detail)
            checar("nenhuma das recusas chegou a gravar", gravou == [B])
        finally:
            R._preparar, R._gravar_as_os = orig_prep, orig_grav
    finally:
        R._os_no_harmonit = orig_os

    # ── C3: o semáforo ───────────────────────────────────────────────────────
    print("\n== C3: o semáforo ==")
    D = rodar(reg.abrir_lote("t", "aditivo", "T-6666", "1"))
    salvos = (R._montar_tudo, R._criar_uma_os, R._gravar_pendencias,
              R._corrigir_tipos_veiculo)
    ops = [{"placa": p, "rotulo": "X", "materiais": []} for p in ("P1", "P2", "P3")]
    respostas = iter([
        ({"placa": "P1", "rotulo": "X", "ok": True, "os_id": 1, "numero_ordem": 1, "materiais_erro": []}, 1),
        ({"placa": "P2", "rotulo": "X", "ok": True, "os_id": 2, "numero_ordem": 2,
          "materiais_erro": ["ST310U: produto inativo"]}, 2),
        ({"placa": "P3", "rotulo": "X", "ok": False, "erro": "Harmonit fora"}, None)])

    async def _criar(op, sol, num=False):
        return next(respostas)

    async def _nada(*a, **k):
        return []
    R._montar_tudo = lambda body, pre: ops
    R._criar_uma_os = _criar
    R._gravar_pendencias = _nada
    R._corrigir_tipos_veiculo = _nada
    try:
        pre = {"perfil": cfg.PERFIS["aditivo"], "resolvidos": [], "avisos": [],
               "ctx": {"falhas": []}}
        r = rodar(R._gravar_as_os(corpo(D, termo="T-6666"), pre))
    finally:
        (R._montar_tudo, R._criar_uma_os, R._gravar_pendencias,
         R._corrigir_tipos_veiculo) = salvos
    checar("verde, amarelo, vermelho", [c["semaforo"] for c in r["criadas"]]
           == ["verde", "amarelo", "vermelho"])
    checar("a resposta conta a incompleta e o erro separados",
           r["com_incompleto"] == 1 and r["com_erro"] == 1)
    passos = [p for p in rodar(reg.passos(D)) if p["etapa"] == 4]
    checar("o registro grava criado, criado_incompleto, falhou",
           [p["acao"] for p in passos] == ["criado", "criado_incompleto", "falhou"])
    checar("a incompleta leva os materiais recusados",
           passos[1]["erro"] == "materiais recusados: ST310U: produto inativo", passos[1]["erro"])

    # ── as telas ─────────────────────────────────────────────────────────────
    print("\n== a aba: o termo já gerado e o semáforo ==")
    s = subprocess.run(["node", str(RAIZ / "tests" / "exercitar_operacoes.js"),
                        str(RAIZ / "frontend" / "operacoes.html")],
                       capture_output=True, text=True, timeout=120,
                       env={**os.environ, "EXERCITAR_DUP": "1"})
    t = json.loads(s.stdout or "{}")
    checar("o exercício rodou sem erro", not t.get("erros"), (t.get("erros") or [""])[0][:300])
    checar("o aviso aparece", t.get("dup_aparece") == "block", t.get("dup_aparece"))
    checar("e diz número, quem e a apagada",
           "16880" in (t.get("dup_texto") or "") and "Erika" in (t.get("dup_texto") or "")
           and "1 OS desse termo já foram apagadas" in (t.get("dup_texto") or ""),
           (t.get("dup_texto") or "")[:300])
    checar("Gerar preso até marcar", t.get("dup_gerar_preso") is True)
    checar("sem marcar, o payload vai sem a confirmação", t.get("dup_payload_sem") is False)
    checar("marcou: Gerar solto e o payload confirma",
           t.get("dup_gerar_solto") is True and t.get("dup_payload_com") is True)
    checar("resultado: a OS amarela aparece como 'incompleta'",
           "badge-ambar" in (t.get("sem_tabela") or "") and "incompleta" in (t.get("sem_tabela") or ""))
    checar("a mensagem de cima assume o amarelo, não o verde",
           t.get("sem_msg_classe") == "msg aviso" and "1 com material recusado" in (t.get("sem_msg") or ""),
           (t.get("sem_msg_classe"), (t.get("sem_msg") or "")[:120]))

    print("\n== o Histórico: apagada, incompleta, não conferida ==")
    resposta = {"lote": {"perfil": "aditivo", "termo": "T-9999", "criado_em": "2026-09-15T19:34:00+00:00",
                         "usuario": "Erika"},
                "passos": [
                    {"criado_em": "2026-09-15T19:34:00+00:00", "etapa": 4, "sistema": "harmonit",
                     "acao": "criado", "placa_gravada": "TST 0E55", "id_externo": 111,
                     "no_harmonit": "apagada", "numero_os": None},
                    {"criado_em": "2026-09-15T19:34:00+00:00", "etapa": 4, "sistema": "harmonit",
                     "acao": "criado_incompleto", "placa_gravada": "TST 0G78", "id_externo": 222,
                     "erro": "materiais recusados: X", "no_harmonit": "existe", "numero_os": 16002},
                    {"criado_em": "2026-09-15T19:34:00+00:00", "etapa": 4, "sistema": "harmonit",
                     "acao": "criado", "placa_gravada": "TST 0H99", "id_externo": 333,
                     "no_harmonit": "nao_conferida", "numero_os": None}],
                "resumo": {}, "resolvidas": {}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(resposta, f)
    try:
        s = subprocess.run(["node", str(RAIZ / "tests" / "exercitar_historico.js"),
                            str(RAIZ / "frontend" / "operacoes_historico.html")],
                           capture_output=True, text=True, timeout=60,
                           env={**os.environ, "EXERCITAR_LOTE": f.name})
    finally:
        os.unlink(f.name)
    h = json.loads(s.stdout or "{}")
    tb = h.get("tbody") or ""
    checar("o exercício do Histórico rodou sem erro", not h.get("erros"),
           (h.get("erros") or [s.stderr[-300:]])[0][:300])
    checar("a tela pede a conferência", any("conferir=1" in c for c in h.get("chamadas") or []),
           h.get("chamadas"))
    checar("apagada aparece cinza, e não como 'criado'",
           "badge-cinza" in tb and "apagada no Harmonit" in tb, tb[:300])
    checar("incompleta aparece âmbar, com o número da OS",
           "badge-ambar" in tb and "criada incompleta" in tb and "16002" in tb)
    checar("não conferida mantém a ação, com a ressalva", "(não conferida)" in tb)
finally:
    storage.DB_PATH = PRODUCAO
    os.unlink(_tmp.name)

for a in achados:
    print("  FALHOU:", a)
print(f"\n{ok} OK, {len(achados)} falha(s)")
sys.exit(1 if achados else 0)
