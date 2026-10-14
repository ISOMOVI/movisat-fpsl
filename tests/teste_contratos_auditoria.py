"""Rotina de auditoria da Gestão de Contratos — etapa C6.

Roda em banco de MEMÓRIA, com a WESO entrando como dicionário: assim as regras
se provam sem depender do cache real nem da API, que oscila.

🚨 O QUE ESTA SUÍTE EXISTE PARA IMPEDIR:
  1. **comparar com cache velho em silêncio.** Cache de 3 dias acusaria
     "em uso sem contrato" para placa retirada ontem. Acima do teto a rotina
     NÃO roda e diz por quê;
  2. **acusar código de frota como placa sem contrato.** A WESO tem ~100
     `OBD 2`/`EGP 05`/`TERMO 8396`; enchê-los na tela é ruído que ninguém
     resolve;
  3. **julgar o aviso prévio pelo cache.** O prazo vence pelo CALENDÁRIO, sem
     evento novo — a rotina recalcula antes de comparar;
  4. **guardar achado velho.** Achado é retrato: a tabela é refeita a cada
     rodada.

Roda na VPS:  venv/bin/python tests/teste_contratos_auditoria.py
"""
import pathlib
import sqlite3
import sys
from datetime import date

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import contratos_eventos as motor      # noqa: E402
from fpsl_weso.painel import contratos_registro as reg       # noqa: E402
from fpsl_weso.painel import contratos_tabelas as tab        # noqa: E402
from fpsl_weso.services import contratos_auditoria as aud    # noqa: E402

HOJE = date(2026, 10, 13)
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


def banco():
    c = sqlite3.connect(":memory:")
    tab.criar(c)
    return c


def ev(acao, placa, fonte=motor.ASSINADO):
    return {"acao": acao, "placa": placa, "fonte": fonte}


def grava(c, cnpj, numero, tipo, assinado, quando, eventos, **kw):
    reg.gravar(c, cnpj, {"numero": numero, "perfil": tipo, "a_definir": False, "eventos": eventos},
               assinado=assinado, assinado_em=quando, origem="carga", enviado_por="teste",
               hash_arquivo=f"h-{cnpj}-{numero}", **kw)


def tipos(achados):
    return sorted({a[0] for a in achados})


def do_tipo(achados, t):
    return [a for a in achados if a[0] == t]


print("\n[1] os 4 cruzamentos basicos")
c = banco()
# ativa e em uso -> nada a dizer
grava(c, "1" * 14, "100", "CONTRATO", True, "2026-01-10", [ev(motor.ENTRA, "AAA1B11")])
# ativa so por termo SEM assinatura, e em uso -> falta assinar
grava(c, "2" * 14, "200", "CONTRATO", False, None, [ev(motor.ENTRA, "BBB1B22")])
# rescindida (ha mais de 90 dias) e ainda em uso -> encerrada em uso
grava(c, "3" * 14, "300", "CONTRATO", True, "2024-01-10", [ev(motor.ENTRA, "CCC1B33")])
grava(c, "3" * 14, "301", "RESCISAO", True, "2025-01-10", [ev(motor.RESCINDE, "CCC1B33")])
# ativa e NAO esta na WESO -> contratada e nao instalada
grava(c, "4" * 14, "400", "CONTRATO", True, "2026-02-10", [ev(motor.ENTRA, "DDD1B44")])
weso = {motor.chave("AAA1B11"): "Instalado", motor.chave("BBB1B22"): "Instalado",
        motor.chave("CCC1B33"): "Instalado",
        # na WESO e em nenhum termo -> em uso sem contrato
        motor.chave("ZZZ1B99"): "Instalado"}
a = aud._achar(c, weso, HOJE)
checar("os 4 tipos aparecem", ["CONTRATADA_NAO_INSTALADA", "EM_USO_FALTA_ASSINAR",
                               "EM_USO_SEM_CONTRATO", "ENCERRADA_EM_USO"], tipos(a))
checar("a placa ok NAO vira achado", 0, len([x for x in a if x[2] == "AAA1B11"]))
checar("falta assinar e a BBB1B22", "BBB1B22", do_tipo(a, "EM_USO_FALTA_ASSINAR")[0][2])
checar("encerrada em uso e a CCC1B33", "CCC1B33", do_tipo(a, "ENCERRADA_EM_USO")[0][2])
checar("nao instalada e a DDD1B44", "DDD1B44", do_tipo(a, "CONTRATADA_NAO_INSTALADA")[0][2])
checar("sem contrato e a ZZZ1B99", "ZZZ1B99", do_tipo(a, "EM_USO_SEM_CONTRATO")[0][2])

print("\n[2] aviso previo: a rotina recalcula, nao confia no cache")
# 🚨 O prazo vence pelo CALENDARIO. A mesma base, dois dias diferentes.
c = banco()
grava(c, "5" * 14, "500", "CONTRATO", True, "2026-01-01", [ev(motor.ENTRA, "EEE1B55")])
grava(c, "5" * 14, "501", "RESCISAO", True, "2026-07-16", [ev(motor.RESCINDE, "EEE1B55")])
w = {motor.chave("EEE1B55"): "Instalado"}
# Suja o cache de propósito: se a rotina confiasse nele, erraria.
c.execute("UPDATE contrato_placa SET situacao='ATIVA' WHERE placa_texto='EEE1B55'")
checar("em 13/10 (dentro dos 90 dias) NAO acusa", [], tipos(aud._achar(c, w, date(2026, 10, 13))))
checar("em 15/10 (vencido) acusa encerrada em uso",
       ["ENCERRADA_EM_USO"], tipos(aud._achar(c, w, date(2026, 10, 15))))

print("\n[3] codigo de frota NAO vira 'em uso sem contrato'")
# ⚠️ A WESO tem ~100 `OBD 2`, `EGP 05`, `TERMO 8396`. Eles não são placa, e
# acusá-los encheria a tela de ruído.
c = banco()
w = {"OBD2": "Instalado", "EGP05": "Instalado", "TERMO8396": "Instalado",
     "MOVEL13": "Instalado", motor.chave("FFF1B66"): "Instalado",
     "9BWKB45U8KP018607": "Instalado"}
a = aud._achar(c, w, HOJE)
sem = sorted(x[2] for x in do_tipo(a, "EM_USO_SEM_CONTRATO"))
checar("so a placa e o chassi entram", ["9BWKB45U8KP018607", "FFF1B66"], sem)

print("\n[4] a mesma placa ativa em dois clientes")
c = banco()
grava(c, "6" * 14, "600", "CONTRATO", True, "2026-01-10", [ev(motor.ENTRA, "GGG1B77")])
grava(c, "7" * 14, "700", "CONTRATO", True, "2026-02-10", [ev(motor.ENTRA, "GGG1B77")])
a = aud._achar(c, {motor.chave("GGG1B77"): "Instalado"}, HOJE)
checar("acusa a placa em dois clientes", 1, len(do_tipo(a, "PLACA_EM_DOIS_CLIENTES")))
checar("e nomeia o outro cliente", True, "7" * 14 in do_tipo(a, "PLACA_EM_DOIS_CLIENTES")[0][3])

print("\n[5] substituicao pela metade — o caso Zago 8838")
c = banco()
grava(c, "8" * 14, "8000", "CONTRATO", True, "2024-02-14",
      [ev(motor.ENTRA, "RVF5G49"), ev(motor.ENTRA, "FFW4925")])
grava(c, "8" * 14, "8838", "SUBSTITUICAO", True, "2026-09-11",
      [ev(motor.SAI, "RVF5G49"), ev(motor.SAI, "FFW4925"),
       ev(motor.ENTRA, "FUX7B86"), ev(motor.ENTRA, "BRX9I89")])
# Na WESO: entrou a FUX7B86, a BRX9I89 não entrou, e a RVF5G49 não saiu.
w = {motor.chave("FUX7B86"): "Instalado", motor.chave("RVF5G49"): "Instalado"}
a = aud._achar(c, w, HOJE)
meia = do_tipo(a, "SUBSTITUICAO_PELA_METADE")
checar("acusa a substituicao pela metade", 1, len(meia))
checar("diz que a RVF5G49 deveria ter saido", True, "RVF5G49 deveria ter saído" in meia[0][3])
checar("e que a BRX9I89 deveria ter entrado", True, "BRX9I89 deveria ter entrado" in meia[0][3])

print("\n[6] cache velho: a rotina NAO roda, e DIZ por que")
c = banco()
orig = aud._weso_do_cache
try:
    aud._weso_do_cache = lambda: ({motor.chave("AAA1B11"): "Instalado"}, 72.0, 1)
    r = aud.rodar(c, HOJE)
    checar("nao rodou", False, r["rodou"])
    checar("e o motivo fala da idade do cache", True, "72 h" in r["motivo"] and "velho" in r["motivo"])
    checar("nenhum achado foi gravado", 0,
           c.execute("SELECT COUNT(*) FROM contrato_achado").fetchone()[0])
    # Cache ausente também não roda.
    aud._weso_do_cache = lambda: ({}, None, 0)
    r2 = aud.rodar(c, HOJE)
    checar("cache ausente tambem nao roda", False, r2["rodou"])
    checar("com o motivo certo", True, "não foi encontrado" in r2["motivo"])
    # Cache fresco roda.
    aud._weso_do_cache = lambda: ({motor.chave("AAA1B11"): "Instalado"}, 3.0, 1)
    r3 = aud.rodar(c, HOJE)
    checar("cache fresco roda", True, r3["rodou"])
finally:
    aud._weso_do_cache = orig

print("\n[7] achado e RETRATO: a tabela e refeita a cada rodada")
c = banco()
grava(c, "9" * 14, "900", "CONTRATO", True, "2026-01-10", [ev(motor.ENTRA, "HHH1B88")])
orig = aud._weso_do_cache
try:
    # 1a rodada: a placa não está na WESO -> acusa.
    aud._weso_do_cache = lambda: ({motor.chave("XXX9Z99"): "Instalado"}, 1.0, 1)
    r = aud.rodar(c, HOJE)
    checar("1a rodada acusa a nao instalada", True, r["por_tipo"].get("CONTRATADA_NAO_INSTALADA") == 1)
    n1 = c.execute("SELECT COUNT(*) FROM contrato_achado").fetchone()[0]
    # 2a rodada: a placa entrou na WESO -> o achado tem de DESAPARECER.
    aud._weso_do_cache = lambda: ({motor.chave("HHH1B88"): "Instalado"}, 1.0, 1)
    r2 = aud.rodar(c, HOJE)
    checar("2a rodada nao acusa mais", 0, r2["por_tipo"].get("CONTRATADA_NAO_INSTALADA", 0))
    checar("e o achado velho sumiu da tabela", 0,
           c.execute("SELECT COUNT(*) FROM contrato_achado WHERE tipo='CONTRATADA_NAO_INSTALADA'").fetchone()[0])
    checar("a tabela nao acumulou", True,
           c.execute("SELECT COUNT(*) FROM contrato_achado").fetchone()[0] < n1 + 2)
finally:
    aud._weso_do_cache = orig

print("\n[7b] chave NAO e veiculo")
# 🚨 O mesmo veículo entra duas vezes no dicionário quando tem placa E chassi.
# A primeira versão devolvia `len(placas)` como "veículos na WESO", e a rodada
# real mostrou **2.146** onde a base tem **1.931**. Número inflado em tela é
# defeito, mesmo com o resto da conta certo.
c = banco()
orig = aud._weso_do_cache
try:
    # 1 veículo, 2 chaves (placa e chassi do mesmo).
    aud._weso_do_cache = lambda: ({motor.chave("III1B99"): "Instalado",
                                   "9BWKB45U8KP018607": "Instalado"}, 1.0, 1)
    r = aud.rodar(c, HOJE)
    checar("conta 1 veiculo", 1, r["veiculos_weso"])
    checar("e diz separadamente que ha 2 chaves", 2, r["chaves_weso"])
finally:
    aud._weso_do_cache = orig

print("\n[8] a rotina nao escreve em sistema nenhum, e nasce desligada")
fonte = (RAIZ / "fpsl_weso" / "services" / "contratos_auditoria.py").read_text(encoding="utf-8")
checar("nada de Harmonit/WESO/Clicksign por escrita", False,
       any(s in fonte for s in ("harmonit_post", "weso_post", "harmonit_get", "weso_get", "clicksign")))
checar("o cache da WESO abre em modo somente leitura", True, "mode=ro" in fonte)
checar("a flag tem default 'false'", True, 'get_config(FLAG, "false")' in fonte)
checar("e todo tipo de achado tem explicacao na tela", True,
       all(t in aud.TIPOS for t in ("EM_USO_SEM_CONTRATO", "EM_USO_FALTA_ASSINAR", "ENCERRADA_EM_USO",
                                    "CONTRATADA_NAO_INSTALADA", "SUBSTITUICAO_PELA_METADE",
                                    "PLACA_EM_DOIS_CLIENTES")))

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f_ in falhas:
    print("  -", f_)
sys.exit(1 if falhas else 0)
