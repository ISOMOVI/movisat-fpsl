"""Aba Operações — etapa 3 (F3): as placas. 2026-08-19.

  1. **A etapa 3 GARANTE, não cadastra.** Perfil `cria` cria; perfil `confere`
     aponta o que falta e NÃO cria. Se ela fosse só cadastrar, metade dos
     perfis a pularia e a corrente cliente → placa → OS se quebraria onde ela
     serve.

  2. **Harmonit antes da WESO, e falha do primeiro PARA.** Na ordem inversa
     sobraria veículo na WESO sem par -- o estrago espelhado do de 27/07.

  3. **Recipiente só na WESO**, com o complemento de bancada.

  4. **A prova é RELER.** A WESO já devolveu erro HTML e GRAVOU, e já devolveu
     timeout com a escrita acontecendo depois. Gravou e a releitura não achou
     => `falhou`, nunca `criado`.

  5. **O filtro pode ser ignorado.** `?placa=` é igualdade exata, mas se a WESO
     ignorar o parâmetro devolve a base inteira -- e qualquer placa
     "existiria". A consulta confere que o que voltou é o que se pediu.

  6. **O lote permite retomar.** O que terminou bem fica registrado; `falhou`
     não conta como resolvido, porque a graça de retomar é tentar de novo.

Roda na VPS: venv/bin/python tests/teste_operacoes_f3.py
🚨 NÃO FAZ REDE E NÃO ESCREVE EM SISTEMA EXTERNO. Grava só no registro local,
num lote próprio que ele mesmo apaga. Em 17/08 a própria suíte criou 6 veículos
permanentes no Harmonit; não se repete.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi import HTTPException  # noqa: E402
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import operacoes_registro as reg  # noqa: E402
from fpsl_weso.painel.routers import operacoes_router as opr  # noqa: E402

ok, falhas = 0, []
CNPJ = "WQ0P6GLD000108"
CLIENTE_H = 998063


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


def limpar(lote):
    with storage._connect() as c:
        c.execute("DELETE FROM operacoes_passo WHERE lote = ?", (lote,))
        c.execute("DELETE FROM operacoes_lote WHERE lote = ?", (lote,))


class Espiao:
    def __init__(self):
        self.harmonit, self.weso = [], []


def dubles(espiao, *, no_harmonit=False, na_weso=False,
           harmonit_erro=None, weso_muda=True, releitura_acha=True):
    estado = {"h": no_harmonit, "w": na_weso}

    async def _eh(texto):
        return {"id": 900001, "placa": texto, "cliente": "VELASCO",
                "clienteId": CLIENTE_H} if estado["h"] else None

    async def _ew(texto):
        return {"id": 900002, "placa": texto, "descricao": "X"} if estado["w"] else None

    async def _hpost(path, payload):
        if harmonit_erro:
            raise HTTPException(400, harmonit_erro)
        espiao.harmonit.append((path, payload))
        if releitura_acha:
            estado["h"] = True
        return {}

    async def _wpost(path, corpo, allow_409=False):
        espiao.weso.append((path, corpo))
        if weso_muda and releitura_acha:
            estado["w"] = True
        return {}

    return {"_existe_no_harmonit": _eh, "_existe_na_weso": _ew,
            "harmonit_post": _hpost, "weso_post": _wpost}


def rodar(dub, **campos):
    originais = {n: getattr(opr, n) for n in dub}
    for n, f in dub.items():
        setattr(opr, n, f)
    try:
        return asyncio.run(opr.criar_uma_placa(
            opr.PlacaInput(**campos), _=None))
    finally:
        for n, f in originais.items():
            setattr(opr, n, f)


async def abrir(perfil):
    lote = await reg.abrir_lote("zz_teste", perfil, "9999", CNPJ)
    await reg.guardar_cliente(lote, CLIENTE_H, 13562)
    return lote


# ── 1. perfil que CRIA ───────────────────────────────────────────────────────
print("\n[1] perfil `cria` — nasce nos dois, na ordem certa")
lote = asyncio.run(abrir("contrato_novo"))
try:
    e = Espiao()
    d = rodar(dubles(e), lote=lote, placa="TST9Z00", descricao="VEICULO TESTE",
              cliente_harmonit_id=CLIENTE_H, documento=CNPJ)
    checar("Harmonit criado", d["harmonit"]["acao"] == "criado", str(d["harmonit"]))
    checar("WESO criada", d["weso"]["acao"] == "criado", str(d["weso"]))
    checar("os dois conferidos relendo",
           d["harmonit"].get("verificado_relendo") and d["weso"].get("verificado_relendo"))
    checar("Harmonit recebeu o Incluir com id 0",
           e.harmonit and e.harmonit[0][0] == "/Veiculo/Incluir"
           and e.harmonit[0][1]["id"] == 0, str(e.harmonit))
    # 🚨 TRAVA: só o documento vai para a WESO, nunca os dados do cliente
    checar("a WESO recebeu só o cnpjcpf",
           e.weso[0][1]["equipamento"]["cliente"] == {"cnpjcpf": CNPJ})
    checar("a placa foi formatada", d["placa_gravada"] == "TST 9Z00", d["placa_gravada"])

    print("\n[2] já existe nos dois — informa e não cria")
    e = Espiao()
    d = rodar(dubles(e, no_harmonit=True, na_weso=True), lote=lote,
              placa="TST9Z00", cliente_harmonit_id=CLIENTE_H, documento=CNPJ)
    checar("Harmonit ja_existia", d["harmonit"]["acao"] == "ja_existia")
    checar("WESO ja_existia", d["weso"]["acao"] == "ja_existia")
    checar("nada foi enviado", (e.harmonit, e.weso) == ([], []))

    print("\n[3] o Harmonit falha → PARA")
    e = Espiao()
    d = rodar(dubles(e, harmonit_erro="500: caiu"), lote=lote, placa="TST9Z01",
              cliente_harmonit_id=CLIENTE_H, documento=CNPJ)
    checar("Harmonit falhou", d["harmonit"]["acao"] == "falhou")
    checar("WESO ignorada", d["weso"]["acao"] == "ignorado")
    checar("e a WESO não recebeu nada", e.weso == [])

    print("\n[4] gravou e a releitura não achou → falhou, nunca criado")
    e = Espiao()
    d = rodar(dubles(e, no_harmonit=True, releitura_acha=False), lote=lote,
              placa="TST9Z02", cliente_harmonit_id=CLIENTE_H, documento=CNPJ)
    checar("não vira `criado`", d["weso"]["acao"] == "falhou", str(d["weso"]))
    checar("e o erro diz da releitura", "releitura" in (d["weso"]["erro"] or ""))

    print("\n[5] recipiente — só na WESO, com bancada")
    e = Espiao()
    d = rodar(dubles(e), lote=lote, placa="TST9Z00-MANUT", recipiente=True,
              cliente_harmonit_id=CLIENTE_H, documento=CNPJ)
    checar("Harmonit ignora", d["harmonit"]["acao"] == "ignorado")
    checar("com o motivo de bancada", "bancada" in d["harmonit"]["motivo"])
    checar("o Harmonit não recebeu nada", e.harmonit == [])
    checar("a WESO recebeu o complemento de bancada",
           e.weso[0][1]["equipamento"]["complemento"]["tipoEqp"] == opr.TIPO_BANCADA)
    # 🚨 O RECIPIENTE NÃO SE FORMATA -- ganhar espaço quebraria a chave que a
    # geração de OS procura.
    checar("o recipiente não ganhou espaço", d["placa_gravada"] == "TST9Z00-MANUT",
           d["placa_gravada"])
finally:
    limpar(lote)

# ── 6. perfil que CONFERE ────────────────────────────────────────────────────
print("\n[6] perfil `confere` — aponta o que falta e NÃO cria")
lote2 = asyncio.run(abrir("rescisao"))
try:
    e = Espiao()
    d = rodar(dubles(e, no_harmonit=True, na_weso=True), lote=lote2,
              placa="TST9Z00", cliente_harmonit_id=CLIENTE_H, documento=CNPJ)
    checar("existindo, confere_ok nos dois",
           d["harmonit"]["acao"] == "confere_ok" and d["weso"]["acao"] == "confere_ok")

    e = Espiao()
    d = rodar(dubles(e), lote=lote2, placa="TST9Z03",
              cliente_harmonit_id=CLIENTE_H, documento=CNPJ)
    checar("faltando, aponta e não cria",
           d["harmonit"]["acao"] == "confere_falta" and d["weso"]["acao"] == "confere_falta",
           str(d))
    # 🚨 A VERIFICAÇÃO QUE IMPORTA: conferir NUNCA escreve.
    checar("nada foi enviado a sistema nenhum", (e.harmonit, e.weso) == ([], []))
finally:
    limpar(lote2)

# ── 7. o lote e o retomar ────────────────────────────────────────────────────
print("\n[7] o lote permite retomar")
lote3 = asyncio.run(abrir("contrato_novo"))
try:
    e = Espiao()
    rodar(dubles(e), lote=lote3, placa="TST9Z10", cliente_harmonit_id=CLIENTE_H,
          documento=CNPJ)
    rodar(dubles(e, harmonit_erro="caiu"), lote=lote3, placa="TST9Z11",
          cliente_harmonit_id=CLIENTE_H, documento=CNPJ)
    resolvidas = asyncio.run(reg.ja_resolvidas(lote3))
    checar("a que deu certo conta como resolvida",
           resolvidas.get("TST 9Z10") == {"harmonit", "weso"}, str(resolvidas))
    # 🚨 `falhou` NÃO conta: a graça de retomar é tentar de novo o que falhou.
    checar("a que falhou NÃO conta como resolvida",
           "TST 9Z11" not in resolvidas, str(resolvidas))
    r = asyncio.run(reg.resumo(lote3))
    checar("o registro guardou todos os passos", r["passos"] >= 4, str(r))
    checar("e nenhuma linha `simulado` existe",
           "simulado" not in r["por_acao"], str(r["por_acao"]))
finally:
    limpar(lote3)

# ── 8. a trava do filtro ignorado ────────────────────────────────────────────
print("\n[8] filtro ignorado pela WESO não vira 'a placa existe'")
# 🚨 `?placa=` é igualdade exata, MAS se a WESO ignorar o parâmetro devolve a
# base inteira -- e sem esta trava qualquer placa "existiria". Já aconteceu com
# `cliente_id`, que é aceito e ignorado.
async def _base_inteira(path, params=None):
    return {"veiculos": [{"id": 1, "placa": "OUTRA COISA"},
                         {"id": 2, "placa": "MAIS OUTRA"}]}

_orig = opr.weso_get
opr.weso_get = _base_inteira
try:
    achou = asyncio.run(opr._existe_na_weso("TST 9Z00"))
    checar("base inteira devolvida não faz a placa existir", achou is None, str(achou))
finally:
    opr.weso_get = _orig

print()
print("=" * 56)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
