"""Rotas da Gestão de Contratos (`CTR_1.1`) — exercitadas com PDFs REAIS.

Etapa C2: as rotas LEEM e CONFEREM, e **não gravam**. Este teste prova as duas
coisas -- o efeito que a tela vai mostrar, e que nada foi escrito.

🚨 POR QUE NÃO BASTA `py_compile`: ele não pega import faltando. Aqui o módulo
é IMPORTADO de verdade e as rotas são CHAMADAS, que é a única forma de ver
`NameError` e dependência errada. Lição de 29/07, custou um `NameError` que
passou no `py_compile`.

⚠️ A AUTENTICAÇÃO ENTRA POR `dependency_overrides`, NO PONTO CERTO. A primeira
versão trocava o módulo `fpsl_weso.painel.auth` por um dublê **só quando o
import falhava** -- o que acontece na minha máquina (`jose` mora no venv da
VPS) e NÃO acontece na VPS. Resultado: passou local e deu **401 na VPS**, que é
onde o teste tem de valer.

A correção não é um dublê melhor: é desviar a dependência FOLHA
(`get_usuario_painel`), que é por onde `requer_aba` descobre quem está
chamando. Assim o `requer_aba` real roda, com a `pode_acessar` real, e o que se
finge é só o login. A permissão em si continua verificada no `teste_perfis`.

Roda na VPS:  venv/bin/python tests/teste_contratos_router.py
Só leitura -- não toca banco, Harmonit nem WESO.
"""
import pathlib
import sys
import types

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# O módulo real precisa de `jose`, que só existe no venv da VPS. Fora dele, o
# mínimo indispensável é substituído -- mas o DESVIO do login é por
# `dependency_overrides`, igual nos dois ambientes (ver docstring).
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

from fpsl_weso.painel.routers import contratos_router                # noqa: E402

FIXTURES = RAIZ / "tests" / "fixtures"
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


app = FastAPI()
app.include_router(contratos_router.router)
# 🚨 O DESVIO É NA DEPENDÊNCIA FOLHA, e vale nos dois ambientes. `requer_aba`
# real continua rodando (com a `pode_acessar` real); o que se finge é o login.
app.dependency_overrides[_auth.get_usuario_painel] = lambda: {"login": "teste", "owner": True}
c = TestClient(app)
PREFIXO = "/painel/api/contratos"


def pdf(nome):
    return (nome, (FIXTURES / nome).read_bytes(), "application/pdf")


print(f"\n[0] import de verdade (modulo auth real: {AUTH_REAL})")
# ⚠️ ESTE NÚMERO CRESCE COM CADA ROTA, e é de propósito — mesma ideia da trava
# de telas do `teste_barra_status`. Rota nova tem de passar por aqui e ser
# deliberada. 5 na C2+C3 (/perfis · /extrair · /conferir · /gravar ·
# /cliente/{cnpj}); 9 desde a C6, que trouxe /auditoria/interruptor (GET e
# PUT), /auditoria/rodar-agora e /auditoria/achados.
checar("o router subiu com as 9 rotas", 9, len(contratos_router.router.routes))

print("\n[1] /perfis diz o que aceita E o que recusa, com motivo")
r = c.get(f"{PREFIXO}/perfis")
checar("200", 200, r.status_code)
d = r.json()
checar("8 perfis aceitos", 8, len(d["aceitos"]))
checar("4 recusados", 4, len(d["recusados"]))
checar("e todo recusado tem motivo", True, all(x["motivo"] for x in d["recusados"]))

print("\n[2] /extrair le o termo assinado")
r = c.post(f"{PREFIXO}/extrair?perfil=substituicao", files={"arquivo": pdf("substituicao.pdf")})
checar("200", 200, r.status_code)
d = r.json()
checar("termo 8786", "8786", d["numero"])
checar("um SAI e um ENTRA", [("SAI", "BZR 5B97"), ("ENTRA", "UPW 3G17")],
       [(e["acao"], e["placa"]) for e in d["eventos"]])
checar("sem versao do Harmonit, nao ha troca", None, d["troca_registrada"])

print("\n[3] /extrair com as DUAS versoes: a troca aparece")
# Maxi Confort 8872. A anotacao mora so no PDF do Harmonit.
r = c.post(f"{PREFIXO}/extrair?perfil=contrato_novo",
           files={"arquivo": pdf("assinado_8872.pdf"),
                  "arquivo_harmonit": pdf("harmonit_8872_troca.pdf")})
checar("200", 200, r.status_code)
d = r.json()
checar("a anotacao de troca veio, com a frase", True,
       "FAC 5H30" in (d["troca_registrada"] or ""))
extras = [e["placa"].replace(" ", "") for e in d["eventos_do_harmonit"]]
checar("FAC5H30 e a placa a mais da versao do Harmonit", True, "FAC5H30" in extras)
checar("e ela NAO esta no assinado", False,
       "FAC5H30" in [e["placa"].replace(" ", "") for e in d["eventos"]])

print("\n[4] /conferir: o que o termo faz com cada placa")
r = c.post(f"{PREFIXO}/conferir?perfil=contrato_novo",
           files={"arquivo": pdf("assinado_8872.pdf"),
                  "arquivo_harmonit": pdf("harmonit_8872_troca.pdf")})
checar("200", 200, r.status_code)
d = r.json()
placas = {p["placa"].replace(" ", ""): p for p in d["placas"]}
checar("FAC5H30 entra pela troca registrada", "ATIVA", placas["FAC5H30"]["situacao"])
checar("e a base diz por que", "assinado (troca registrada no Harmonit)", placas["FAC5H30"]["base"])
# 🚨 A TROCA DIZ QUEM ENTRA, NUNCA QUEM SAI. A anotação nomeia só `FAC 5H30`, e
# no PDF do Harmonit as duas placas ficam na tabela, no mesmo item -- não há
# dado que diga que a `DVS 2992` é a que sai. **Não se inventa identificador**
# (regra 13): tirar a placa errada cancelaria a cobrança de um veículo rodando.
# Então a conferência fica com uma placa a mais, DECLARA isso, e pede a
# confirmação de quem sai. A auditoria conferiu na mão que a certa é 10.
checar("as duas placas seguem sustentadas até a confirmação", 11, len(d["sustentadas"]))
checar("e a conferencia PEDE qual placa sai", True, bool(d["troca_confirmar"]))
checar("mostrando a anotacao como motivo", True, "FAC 5H30" in d["troca_confirmar"]["anotacao"])
checar("quem entra pela troca", ["FAC 5H30"], d["troca_confirmar"]["entram"])
checar("e as 10 candidatas a sair", 10, len(d["troca_confirmar"]["candidatas_saida"]))
checar("com aviso explicito de que ficou uma placa a mais", True,
       any("confirme qual placa SAI" in a for a in d["avisos"]))
# 🚨 `M12`: a tela NAO pode prometer "situacao final do cliente" nesta etapa --
# a C2 nao consulta os termos que o cliente ja tem. A resposta diz isso, e a
# tela repete a frase.
checar("a resposta declara a base de comparacao", "somente este termo", d["base_de_comparacao"])

print("\n[5] /conferir recusa o que nao pode conferir")
r = c.post(f"{PREFIXO}/conferir?perfil=manutencao_local", files={"arquivo": pdf("substituicao.pdf")})
checar("manutencao: 400 com motivo", 400, r.status_code)
checar("e o motivo diz que nao nasce de documento", True,
       "não nasce de documento" in r.json()["detail"])
r = c.post(f"{PREFIXO}/extrair?perfil=nao_existe", files={"arquivo": pdf("substituicao.pdf")})
checar("perfil desconhecido: 400", 400, r.status_code)

print("\n[6] versoes de termos DIFERENTES nao se comparam")
# 🚨 A regra da troca vale no MESMO termo. Cruzar numeros diferentes
# transformaria documento de outro contrato em prova de troca.
r = c.post(f"{PREFIXO}/extrair?perfil=contrato_novo",
           files={"arquivo": pdf("assinado_8872.pdf"),
                  "arquivo_harmonit": pdf("contrato_novo_8739.pdf")})
checar("400 quando os dois arquivos sao de termos diferentes", 400, r.status_code)
checar("e a mensagem nomeia os dois numeros", True,
       "8872" in r.json()["detail"] and "8739" in r.json()["detail"])

print("\n[7] placa acrescentada SEM anotacao vira AVISO, nao contrato")
# Era assim que 256 termos "ganhavam" placa depois de assinados. O aditivo 8852
# tem vaga "a definir", entao o aviso nao se aplica a ele -- aqui o par e
# escolhido para ter placas a mais e nenhuma anotacao.
r = c.post(f"{PREFIXO}/conferir?perfil=rescisao",
           files={"arquivo": pdf("rescisao_8842.pdf"),
                  "arquivo_harmonit": pdf("rescisao_8842.pdf")})
checar("200 (mesmo termo nas duas versoes)", 200, r.status_code)
checar("sem placa a mais, nenhum aviso de placa acrescentada", False,
       any("NÃO há anotação de troca" in a for a in r.json()["avisos"]))

print("\n[8] /gravar e /cliente — em banco TEMPORARIO, nunca no fpsl.db")
# 🚨 O banco e a pasta de PDF saem do `storage.DB_PATH`. Desviar os dois é o
# que impede o teste de escrever em `data/fpsl.db` e em `data/contratos/`.
# Por isso `pasta_pdf()` é função, e não constante de módulo: constante congela
# no import e não há como desviar.
import tempfile                                                      # noqa: E402
from fpsl_weso import storage                                         # noqa: E402
from fpsl_weso.painel import contratos_registro as registro           # noqa: E402

tmp = pathlib.Path(tempfile.mkdtemp(prefix="fpsl_contratos_"))
storage.DB_PATH = tmp / "teste.db"
checar("a pasta de PDF seguiu o desvio", str(tmp), str(registro.pasta_pdf().parent))

MAXI = "20480457000158"
r = c.post(f"{PREFIXO}/gravar?perfil=contrato_novo",
           data={"cnpj": "20.480.457/0001-58", "assinado_em": "2026-09-15",
                 "saida_confirmada": '["DVS 2992"]'},
           files={"arquivo": pdf("assinado_8872.pdf"),
                  "arquivo_harmonit": pdf("harmonit_8872_troca.pdf")})
checar("gravou", 200, r.status_code)
d = r.json()
checar("o PDF assinado foi guardado", True, bool(d["gravado"]["arquivo"]))
checar("e o arquivo existe em disco", True, (registro.pasta_pdf() / d["gravado"]["arquivo"]).is_file())
checar("com a saida confirmada, o contrato fica com 10 placas", 10, len(d["ficha"]["sustentadas"]))
checar("e nada ficou pendente de revisao", False, d["a_revisar"])

r2 = c.get(f"{PREFIXO}/cliente/{MAXI}")
checar("a ficha responde", 200, r2.status_code)
checar("com as mesmas 10 placas", 10, len(r2.json()["sustentadas"]))

# ⚠️ O MESMO PDF DUAS VEZES É 409, NÃO UM SEGUNDO TERMO. Clicar duas vezes em
# confirmar já duplicou card no Painel Financeiro.
r3 = c.post(f"{PREFIXO}/gravar?perfil=contrato_novo",
            data={"cnpj": MAXI}, files={"arquivo": pdf("assinado_8872.pdf")})
checar("PDF repetido: 409", 409, r3.status_code)
checar("e a mensagem aponta o termo que ja existe", True, "8872" in r3.json()["detail"])

# 🚨 CNPJ VEM DO FORMULARIO, e invalido e recusado: gravar no cliente errado
# cria ou cancela cobranca no lugar errado (33 documentos divergentes na auditoria).
r4 = c.post(f"{PREFIXO}/gravar?perfil=substituicao",
            data={"cnpj": "123"}, files={"arquivo": pdf("substituicao.pdf")})
checar("CNPJ invalido: 400", 400, r4.status_code)

# 🚨 O MESMO PDF NÃO ENTRA EM DOIS CLIENTES. O `hash` é único no banco todo, e
# não por cliente -- um documento pertence a um cliente só. A auditoria achou
# 33 documentos cujo CNPJ divergia do cliente que o Harmonit aponta, e arquivar
# o mesmo termo em duas empresas duplicaria a cobrança do mesmo veículo.
r5 = c.post(f"{PREFIXO}/gravar?perfil=contrato_novo",
            data={"cnpj": "33333333333333"}, files={"arquivo": pdf("assinado_8872.pdf")})
checar("o mesmo PDF em OUTRO cliente tambem e 409", 409, r5.status_code)

print("\n[8b] troca registrada SEM dizer quem sai: grava e fica 'a revisar'")
# ⚠️ Travar a gravação faria o operador perder a leitura por uma decisão que
# talvez dependa do cliente; gravar calado deixaria uma placa a mais no
# contrato sem ninguém saber. O meio é gravar com o motivo escrito.
tmp2 = pathlib.Path(tempfile.mkdtemp(prefix="fpsl_contratos2_"))
storage.DB_PATH = tmp2 / "teste.db"
r6 = c.post(f"{PREFIXO}/gravar?perfil=contrato_novo",
            data={"cnpj": MAXI},
            files={"arquivo": pdf("assinado_8872.pdf"),
                   "arquivo_harmonit": pdf("harmonit_8872_troca.pdf")})
checar("grava mesmo sem a confirmacao da saida", 200, r6.status_code)
checar("mas marcada 'a revisar'", True, r6.json()["a_revisar"])
checar("com o motivo escrito", True, "qual placa sai" in r6.json()["revisar_motivo"])
checar("e o contrato fica com 11 placas, declaradamente", 11, len(r6.json()["ficha"]["sustentadas"]))
checar("a ficha tambem lista o termo a revisar", 1, len(r6.json()["ficha"]["a_revisar"]))

print("\n[9] /extrair e /conferir continuam sem gravar")
# ⚠️ A prova aqui e estrutural: nenhuma rota do router importa `storage`.
fonte = (RAIZ / "fpsl_weso" / "painel" / "routers" / "contratos_router.py").read_text(encoding="utf-8")
checar("extrair/conferir nao chamam o registro", False,
       "registro.gravar" in fonte.split("async def gravar(")[0])
checar("o router nao usa INSERT/UPDATE", False,
       any(s in fonte.upper() for s in ("INSERT INTO", "UPDATE ", "DELETE FROM")))
checar("e nao escreve arquivo", False, any(s in fonte for s in ("open(", ".write(", "shutil")))

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
