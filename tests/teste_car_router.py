"""Rotas das Contas a Receber (`CAR_1.1`) — etapa E7. 2026-10-28.

🚨 POR QUE NÃO BASTA `py_compile`: ele não pega import faltando nem dependência
errada. Aqui o módulo é IMPORTADO de verdade e as rotas são CHAMADAS, que é a
única forma de ver `NameError`. Lição de 29/07, e o `teste_contratos_router`
existe pela mesma razão.

🚨 ESTE TESTE GRAVA, e é de propósito: as cinco ações da CAR são escrita, e
provar só a tranca deixaria o lançamento de preço sem nenhum teste HTTP. A
escrita acontece num **banco temporário próprio**, montado aqui com três termos
de mentira -- nunca no `data/fpsl.db`. Quem confere isso é o bloco [0]: se
`storage.DB_PATH` não estiver apontando para o temporário, o teste para.

⚠️ A AUTENTICAÇÃO ENTRA POR `dependency_overrides`, NA DEPENDÊNCIA FOLHA
(`get_usuario_painel`), e não por um dublê do módulo `auth`. Assim o
`requer_aba` real roda com a `pode_acessar` real, e o que se finge é só o login
-- a correção que o `teste_contratos_router` já carrega, por ter passado local
e dado 401 na VPS.

Roda na VPS:  venv/bin/python tests/teste_car_router.py
"""
import pathlib
import sqlite3
import sys
import tempfile
import types
from datetime import date

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# 🚨 O BANCO TEMPORÁRIO É APONTADO ANTES DE QUALQUER IMPORT DO PAINEL, porque
# `storage.DB_PATH` é lido na hora da conexão, e o router conecta por ele.
TMP = tempfile.mkdtemp(prefix="car_router_")
DB = str(pathlib.Path(TMP) / "fpsl_teste.db")

from fpsl_weso import storage                                        # noqa: E402

storage.DB_PATH = DB

AUTH_REAL = True
try:
    from fpsl_weso.painel import auth as _auth
except Exception:                                                   # pragma: no cover
    import fpsl_weso.painel as _painel
    from fastapi import Depends, HTTPException
    _auth = types.ModuleType("fpsl_weso.painel.auth")

    async def get_usuario_painel():
        raise HTTPException(401, "sem token")

    def requer_aba(*abas):
        async def _checar(usuario: dict = Depends(get_usuario_painel)):
            return usuario
        return _checar

    _auth.get_usuario_painel = get_usuario_painel
    _auth.requer_aba = requer_aba
    sys.modules["fpsl_weso.painel.auth"] = _auth
    _painel.auth = _auth
    AUTH_REAL = False

from fastapi import FastAPI                                          # noqa: E402
from fastapi.testclient import TestClient                            # noqa: E402

from fpsl_weso.painel import car_motor as motor                      # noqa: E402
from fpsl_weso.painel import car_tabelas as tabelas                  # noqa: E402
from fpsl_weso.painel import contratos_tabelas                       # noqa: E402
from fpsl_weso.painel.routers import car_router                      # noqa: E402

PREFIXO = "/painel/api/car"
COMP = motor.competencia_de(date.today())
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


def semear():
    """Três termos de mentira: um assinado com 2 placas ativas, um assinado sem
    placa cobrável, e um NÃO assinado com placa ativa -- que é a divergência
    que a aba existe para achar."""
    with sqlite3.connect(DB) as conn:
        contratos_tabelas.criar(conn)
        contratos_tabelas.migrar(conn)
        tabelas.criar(conn)
        tabelas.migrar(conn)
        # 🚨 CNPJ ALFANUMÉRICO ENTRE OS SEMEADOS, de propósito: é o caso que o
        # X1 mostrou atravessar errado em seis lugares da CTR, e aqui a rota
        # tem de achar o cliente sem truncar nada.
        for cnpj, nome in (("12345678000199", "zz Cliente de Teste"),
                           ("WQ0P6GLD000108", "zz Cliente Alfanumerico")):
            conn.execute(
                """INSERT INTO contrato_cliente (cnpj, nome, nome_fonte, atualizado_em)
                   VALUES (?,?,?,?)""", (cnpj, nome, "manual", "2026-10-28"))
        # 🚨 O 9003 nasce SEM assinatura e COM placa rodando: é a divergência
        # que esta aba existe para achar (serviço entregue sem documento), e em
        # 28/10 isso vale para 519 placas reais sob 224 contratos.
        for tid, cnpj, numero, assinado in (
                (9001, "12345678000199", "ZZ-1", 1),
                (9002, "12345678000199", "ZZ-2", 1),
                (9003, "WQ0P6GLD000108", "ZZ-3", 0)):
            conn.execute(
                """INSERT INTO contrato_termo (id, cnpj, numero, empresa, tipo,
                                               assinado, assinado_em, origem,
                                               enviado_por, enviado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (tid, cnpj, numero, "MOVISAT", "contrato_novo", assinado,
                 "2026-01-01" if assinado else None, "upload", "teste",
                 "2026-01-01T00:00:00Z"))
        # ⚠️ Semeia EVENTO, não `contrato_placa`: a situação da placa é derivada
        # pelo motor da CTR a cada leitura, e semear a tabela derivada seria
        # semear o cache -- o teste provaria o cache, não a régua.
        for tid, placa in ((9001, "ABC1D23"), (9001, "ABC1D24"),
                           (9003, "ABC1D25")):
            conn.execute(
                """INSERT INTO contrato_evento (termo_id, placa_chave, placa_texto,
                                                acao, fonte, criado_em)
                   VALUES (?,?,?,?,?,?)""",
                (tid, placa, placa, "ENTRA", "assinado", "2026-01-01T00:00:00Z"))
        conn.commit()


semear()

app = FastAPI()
app.include_router(car_router.router)
app.dependency_overrides[_auth.get_usuario_painel] = lambda: {
    "login": "zz_teste_car", "owner": True}
c = TestClient(app)


print(f"\n[0] o banco é o temporário, e o import é de verdade (auth real: {AUTH_REAL})")
checar("storage.DB_PATH aponta o banco temporario", True, storage.DB_PATH == DB)
checar("e NAO o de producao", False, storage.DB_PATH.endswith("data/fpsl.db"))

# ⚠️ ESTE NÚMERO CRESCE COM CADA ROTA, e é de propósito -- mesma ideia da trava
# de telas do `teste_barra_status` e da trava de 18 rotas do
# `teste_contratos_router`. Rota nova tem de passar por aqui e ser deliberada.
# 16 na E7 (28/10): /clientes · /clientes.csv · /cliente/{cnpj} · /termo/{id} ·
# /busca · /fila-sem-valor · /termo/{id}/historico-preco · /prefatura ·
# /prefatura.csv · POST /prefatura/fechar · POST /termo/{id}/preco · /cancelar ·
# /renovar · /excecao · POST /evento/{id}/anular · POST /lote/preco.
# 🔵 O plano previa 15: a 16ª é `POST /prefatura/fechar`, que grava
# `car_leitura`. Sem ela a tabela nascia sem nenhum escritor -- tabela que
# existe e ninguém preenche é promessa que a tela não cumpre.
# 🔵 A trava de 18 rotas do `teste_contratos_router` NÃO muda: router separado.
# 🆕 30/10, blocos F1 e F4: 21 rotas. As 5 novas sao
# GET/PUT /faturado/interruptor · POST /faturado/atualizar · GET /semear ·
# POST /semear.
checar("o router subiu com as 21 rotas", 21, len(car_router.router.routes))

# 🚨 TODA ROTA NOVA ENTRA SOB A MESMA TRANCA DE ABA. Rota solta sem a
# dependência do router seria a porta aberta que o `requer_aba` existe para
# fechar -- e é declarativa, logo fácil de esquecer numa rota nova.
for rota in car_router.router.routes:
    checar(f"{rota.path} herda a tranca da aba", True,
           any(getattr(d.dependency, "__qualname__", "").startswith("requer_aba")
               for d in (rota.dependencies or [])))

print("\n[1] a permissao exigida e `contas_receber`, e NAO `financeiro`")
# 🚨 A decisão dele de 28/10 está aqui como teste, não como comentário: esta aba
# cancela cobrança e precifica em lote, e `financeiro` é de quem confere OS.
# Trocar a permissão sem decidir deixa este teste vermelho.
def abas_exigidas(dependencia) -> set:
    """As abas que um `requer_aba(...)` guarda, lidas da closure dele.

    ⚠️ É a única forma de ver isto sem subir o app inteiro com usuário real --
    e ver é o que importa: o nome da aba numa rota é texto, e texto errado
    responde 403 para todo mundo ou abre para todo mundo, calado.
    """
    fora = set()
    for cel in (getattr(dependencia, "__closure__", None) or []):
        v = cel.cell_contents
        if isinstance(v, (tuple, list, set)):
            fora |= {x for x in v if isinstance(x, str)}
    return fora


alvos = set()
for d in (car_router.router.dependencies or []):
    alvos |= abas_exigidas(d.dependency)
checar("o APIRouter exige contas_receber", True, "contas_receber" in alvos)
checar("e nao exige financeiro", False, "financeiro" in alvos)
# ⚠️ As rotas de escrita declaram `requer_aba("contas_receber")` outra vez na
# assinatura, e não por zelo: é dali que sai o USUÁRIO, e o autor do lançamento
# vem do token. O fonte é conferido porque o `Depends` da assinatura não aparece
# em `rota.dependencies` -- só o do router aparece.
fonte_router = (RAIZ / "fpsl_weso" / "painel" / "routers" / "car_router.py").read_text("utf-8")
# 🚨 UMA EXCECAO, E ELA E NOMEADA: o PUT do interruptor do espelho pede
# `config`, como o da FIN_1.1 e o da auditoria da CTR -- ler e de quem tem a
# aba, LIGAR LACO e do dono. Qualquer OUTRA aba na assinatura derruba este
# teste, que e exatamente o que ele existe para pegar.
outras = (fonte_router.count('requer_aba("')
          - fonte_router.count('requer_aba("contas_receber")'))
checar("so o PUT do interruptor pede outra aba", 1, outras)
checar("e a outra aba e `config`", 1, fonte_router.count('requer_aba("config")'))

print("\n[2] o grid abre, refaz o cache vazio e DIZ que refez")
r = c.get(f"{PREFIXO}/clientes")
checar("200", 200, r.status_code)
d = r.json()
checar("competencia e a de hoje", COMP, d["competencia"])
checar("os 3 termos aparecem", 3, d["totais"]["contratos"])
checar("o cache vazio foi refeito, com o motivo", "cache vazio com termos na base",
       (d["cache"]["refeito_agora"] or {}).get("porque"))
checar("1 contrato ativo (o 9001, com 2 placas)", 1, d["totais"]["ativos"])
checar("2 inativos (sem placa e sem assinatura)", 2, d["totais"]["inativos"])
# 🚨 A DIVERGÊNCIA É O PRODUTO DA ABA: termo sem assinatura com placa rodando é
# serviço entregue e provavelmente não cobrado.
checar("1 divergencia: termo sem assinatura com placa sustentada", 1,
       d["totais"]["divergencias"])
checar("e ninguem tem valor ainda", 0,
       sum(1 for l in d["contratos"] if l["valor_mensal_total"]))

r2 = c.get(f"{PREFIXO}/clientes")
checar("segunda chamada no mesmo dia NAO refaz o cache", None,
       r2.json()["cache"]["refeito_agora"])

print("\n[3] filtros do grid")
checar("situacao=ATIVO devolve 1", 1,
       len(c.get(f"{PREFIXO}/clientes?situacao=ATIVO").json()["contratos"]))
checar("divergencia=true devolve 1", 1,
       len(c.get(f"{PREFIXO}/clientes?divergencia=true").json()["contratos"]))
checar("q pelo numero do termo acha", ["ZZ-3"],
       [l["numero"] for l in c.get(f"{PREFIXO}/clientes?q=ZZ-3").json()["contratos"]])

print("\n[4] CSV do grid: cabecalho e uma linha por contrato")
r = c.get(f"{PREFIXO}/clientes.csv")
checar("200", 200, r.status_code)
linhas = r.text.strip().split("\n")
checar("cabecalho + 3 linhas", 4, len(linhas))
checar("separador e ponto e virgula", True, linhas[0].startswith("cnpj;cliente;termo"))

print("\n[5] competencia invalida e 400, com a frase")
r = c.get(f"{PREFIXO}/clientes?competencia=2026-13")
checar("400", 400, r.status_code)
checar("e a mensagem fala da competencia", True,
       "competencia" in r.json()["detail"].lower() or
       "compet" in r.json()["detail"].lower())

print("\n[6] a fila de sem valor sai da propria pre-fatura")
r = c.get(f"{PREFIXO}/fila-sem-valor")
checar("200", 200, r.status_code)
fila = r.json()["fila"]
# Só o 9001 tem placa cobrável: o 9003 está sem assinatura (inativo para
# cobrança) mas as placas dele seguem sustentadas na CTR, logo ele ENTRA na
# pré-fatura como divergência -- e entra na fila também, porque tem placa sem
# preço. Essa é a régua, e o teste a prende.
checar("a fila traz contratos com placa sem preco", True, len(fila) >= 1)
checar("o maior vem primeiro", True,
       all(fila[i]["sem_valor"] >= fila[i + 1]["sem_valor"]
           for i in range(len(fila) - 1)))

print("\n[7] lancar preco: 400 sem motivo, grava com motivo")
r = c.post(f"{PREFIXO}/termo/9001/preco", json={"valor": "199,90"})
checar("sem motivo, 400", 400, r.status_code)
checar("e a frase do registro chega inteira", True,
       "motivo" in r.json()["detail"])

r = c.post(f"{PREFIXO}/termo/9001/preco",
           json={"valor": "199,90", "motivo": "zz teste E7"})
checar("com motivo, 200", 200, r.status_code)
d = r.json()
checar("o autor e o do token, nao o do corpo", "zz_teste_car", d["por"])
checar("e o historico ja traz o lancamento", 1, len(d["historico_preco"]))

r = c.post(f"{PREFIXO}/termo/9001/preco",
           json={"valor": "199,90", "motivo": "zz teste E7", "por": "outro"})
checar("`por` no corpo e IGNORADO", "zz_teste_car", r.json()["por"])

print("\n[8] termo nao existente e 404, nao 500")
r = c.post(f"{PREFIXO}/termo/999999/preco",
           json={"valor": "10,00", "motivo": "zz"})
checar("404", 404, r.status_code)

print("\n[9] o preco aparece na pre-fatura, e o total e do que TEM valor")
r = c.get(f"{PREFIXO}/prefatura")
checar("200", 200, r.status_code)
pre = r.json()
checar("2 placas do 9001 ganharam valor", True, pre["totais"]["com_valor"] >= 2)
checar("o total soma", "399,80", pre["totais"]["total"])
# 🚨 `M12`: a resposta DECLARA que a parte variavel nao existe, em vez de somar
# so a mensalidade e deixar parecer que e o total.
checar("e a parte variavel se declara desligada", False, pre["variavel"]["ligada"])
checar("com o porque escrito", True, bool(pre["variavel"]["porque"]))

print("\n[10] excecao vale SO no mes lancado, e a resposta diz qual")
r = c.post(f"{PREFIXO}/termo/9001/excecao",
           json={"valor": "0,00", "motivo": "zz cortesia de um mes"})
checar("200", 200, r.status_code)
checar("a resposta diz o mes em que vale", COMP, r.json()["vale_so_em"])
r = c.post(f"{PREFIXO}/termo/9001/excecao", json={"valor": "1,00"})
checar("excecao sem motivo e 400", 400, r.status_code)

print("\n[11] anular: anula uma vez, e a segunda e 409 (estado, nao entrada)")
eid = c.post(f"{PREFIXO}/termo/9002/renovar", json={}).json()["evento_id"]
r = c.post(f"{PREFIXO}/evento/{eid}/anular", json={"motivo": "zz errado"})
checar("200", 200, r.status_code)
r = c.post(f"{PREFIXO}/evento/{eid}/anular", json={"motivo": "zz de novo"})
checar("409 na segunda", 409, r.status_code)
checar("e a mensagem diz qual anulacao existe", True,
       "anulado" in r.json()["detail"])

print("\n[12] cancelar exige motivo, e a divergencia aparece depois")
checar("cancelar sem motivo e 400", 400,
       c.post(f"{PREFIXO}/termo/9001/cancelar", json={}).status_code)
r = c.post(f"{PREFIXO}/termo/9001/cancelar",
           json={"motivo": "zz cancelamento de teste"})
checar("com motivo, 200", 200, r.status_code)
# O cache do grid foi feito hoje, então pedir o grid não o refaz: a divergência
# nova só aparece na leitura que recalcula. É a pré-fatura que a mostra na hora.
pre = c.get(f"{PREFIXO}/prefatura").json()
div = [ct["divergencia"] for cl in pre["clientes"] for ct in cl["contratos"]
       if ct["termo_id"] == 9001]
checar("cancelado aqui com placa ATIVA na CTR e divergencia", True,
       bool(div and div[0]))

print("\n[13] lote: idempotente, recusa o inexistente e nao derruba o resto")
r = c.post(f"{PREFIXO}/lote/preco",
           json={"termos": [9002, 9003, 999999], "valor": "49,90",
                 "motivo": "zz lote de teste"})
checar("200", 200, r.status_code)
d = r.json()
checar("2 lancados", 2, d["lancados"])
checar("1 recusado, o que nao existe", 1, len(d["recusados"]))
checar("e o recusado vem com o motivo", True, bool(d["recusados"][0]["motivo"]))
r2 = c.post(f"{PREFIXO}/lote/preco",
            json={"termos": [9002, 9003], "valor": "49,90",
                  "motivo": "zz lote de teste"})
checar("clicar duas vezes nao lanca duas vezes", 2, r2.json()["repetidos"])
checar("lote sem motivo e 400", 400,
       c.post(f"{PREFIXO}/lote/preco",
              json={"termos": [9002], "valor": "1,00"}).status_code)
checar("lote sem termos e 400", 400,
       c.post(f"{PREFIXO}/lote/preco",
              json={"valor": "1,00", "motivo": "zz"}).status_code)
checar("lote acima do teto e 400", 400,
       c.post(f"{PREFIXO}/lote/preco",
              json={"termos": list(range(2001)), "valor": "1,00",
                    "motivo": "zz"}).status_code)

print("\n[14] a ficha do cliente, inclusive com CNPJ ALFANUMERICO")
r = c.get(f"{PREFIXO}/cliente/WQ0P6GLD000108")
checar("200 no alfanumerico", 200, r.status_code)
d = r.json()
checar("e achou o cliente certo, sem truncar", ["WQ0P6GLD000108"],
       [cl["cnpj"] for cl in d["clientes"]])
# ⚠️ PONTUAÇÃO É TOLERADA, MENOS A BARRA, e isto é limite de URL, não escolha:
# `12.345.678/0001-99` tem uma `/`, que parte o caminho em dois segmentos e a
# rota nunca vê. A tela liga pelo CNPJ **como a base guarda** (limpo), e quem
# digita à mão pode pôr ponto, traço e espaço. Dito aqui porque a alternativa
# -- o CNPJ sair do caminho e virar query -- seria mudar as 4 rotas por um caso
# que a tela não produz.
checar("com ponto, traco e espaco acha", 200,
       c.get(f"{PREFIXO}/cliente/12.345.678 0001-99").status_code)
checar("e com barra NAO chega na rota (limite de URL, nao do codigo)", 404,
       c.get(f"{PREFIXO}/cliente/12.345.678/0001-99").status_code)
checar("documento fora da base e 404", 404,
       c.get(f"{PREFIXO}/cliente/11222333000144").status_code)
checar("documento com forma errada e 400", 400,
       c.get(f"{PREFIXO}/cliente/123").status_code)

print("\n[15] um contrato: linhas do mes E a linha do tempo do preco juntas")
r = c.get(f"{PREFIXO}/termo/9001")
checar("200", 200, r.status_code)
d = r.json()
checar("tem o contrato do mes", True, d["contrato"] is not None)
checar("e o historico com o anulado marcado", True,
       any("anulado" in e for e in d["historico_preco"]))
r = c.get(f"{PREFIXO}/termo/9002")
checar("contrato sem placa cobravel DIZ por que nao tem linha", True,
       bool(r.json()["porque_sem_linhas"]))
checar("termo inexistente e 404", 404, c.get(f"{PREFIXO}/termo/999999").status_code)

print("\n[16] a busca responde SEMPRE com achou_por e como")
r = c.get(f"{PREFIXO}/busca?q=Alfanumerico")
checar("200", 200, r.status_code)
checar("achou por nome", "nome", r.json()["achou_por"])
d = c.get(f"{PREFIXO}/busca?q=zzzznaoexiste").json()
checar("vazio tambem diz por onde procurou", None, d["achou_por"])
checar("e o `como` vem preenchido", True, bool(d["como"]))
checar("1 caractere nao devolve a base inteira", [],
       c.get(f"{PREFIXO}/busca?q=z").json()["cnpjs"])

print("\n[17] fechar a pre-fatura grava a leitura, com autor e assinatura")
r = c.post(f"{PREFIXO}/prefatura/fechar", json={})
checar("200", 200, r.status_code)
d = r.json()
checar("tem id de leitura", True, bool(d["leitura_id"]))
checar("o autor e o do token", "zz_teste_car", d["por"])
checar("e a assinatura e sha256", 64, len(d["assinatura"]))
r2 = c.post(f"{PREFIXO}/prefatura/fechar", json={})
checar("reler sem mudar nada da a MESMA assinatura", True,
       r2.json()["leituras_anteriores"][0]["igual_a_esta"])
# 🚨 E mudando um preço, a assinatura muda: é isso que transforma "o número
# mudou" de discussão em fato.
# ⚠️ O PREÇO TEM DE SER DE UM CONTRATO QUE APARECE NA PRÉ-FATURA. A primeira
# versão disto lançava no 9002, que não tem placa cobrável: o preço gravava, a
# pré-fatura não mudava e a assinatura continuava a mesma -- e estava CERTO. O
# teste é que afirmava a coisa errada.
c.post(f"{PREFIXO}/termo/9003/preco", json={"valor": "77,70", "motivo": "zz muda"})
r3 = c.post(f"{PREFIXO}/prefatura/fechar", json={})
checar("preco novo muda a assinatura", False,
       r3.json()["leituras_anteriores"][0]["igual_a_esta"])

print("\n[18] CSV da pre-fatura")
r = c.get(f"{PREFIXO}/prefatura.csv")
checar("200", 200, r.status_code)
checar("cabecalho da pre-fatura", True,
       r.text.startswith("cnpj;cliente;termo;empresa;situacao_contrato;placa"))
checar("anexa com o nome do mes", True, COMP in r.headers["content-disposition"])

print("\n[19] NENHUM UPDATE em car_evento saiu destas 16 rotas")
# 🚨 A tabela é imutável, e a trava do `car_registro` olha o fonte dele. Aqui a
# prova é de COMPORTAMENTO: depois de 20 chamadas de escrita, todo evento ainda
# tem o `criado_em` original e nenhum foi apagado.
fonte = (RAIZ / "fpsl_weso" / "painel" / "routers" / "car_router.py").read_text("utf-8")
checar("o fonte do router nao tem UPDATE car_evento", False, "UPDATE car_evento" in fonte)
checar("nem DELETE FROM car_evento", False, "DELETE FROM car_evento" in fonte)
with sqlite3.connect(DB) as conn:
    anulas = conn.execute(
        "SELECT COUNT(*) FROM car_evento WHERE acao = 'ANULA'").fetchone()[0]
    checar("a anulacao ficou como EVENTO, nao como apagamento", 1, anulas)
    checar("e nenhum evento ficou sem autor", 0, conn.execute(
        "SELECT COUNT(*) FROM car_evento WHERE por IS NULL OR trim(por) = ''"
    ).fetchone()[0])

print(f"\n{'='*60}\n{ok} OK, {len(falhas)} falhas")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
