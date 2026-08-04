"""Teste do módulo de regra de placa (fpsl_weso/placas.py).

Casos tirados da base REAL da WESO em 2026-07-27, não inventados.
Roda: venv/bin/python tests/teste_placas.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import placas  # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
    else:
        falhas.append(f"{nome}: esperado {esperado!r}, obtido {obtido!r}")


print("[1] formatação básica")
checar("antiga sem espaco", "MCJ 0232", placas.formatar("MCJ0232"))
checar("antiga com espaco", "CUB 0764", placas.formatar("CUB 0764"))
checar("mercosul", "OVG 7C78", placas.formatar("OVG7C78"))
checar("minuscula", "RCJ 0D65", placas.formatar("rcj 0d65"))
checar("espaco nas bordas", "RDM 0G81", placas.formatar("  RDM 0G81  "))
checar("espaco duplo", "FJZ 4H64", placas.formatar("FJZ  4H64"))
checar("hifen", "ABC 1234", placas.formatar("ABC-1234"))

print("[2] redundância — as 5 grafias que existiam na base")
for entrada in ["CUB 0764 (RD)", "(RD) CUB 0764", "CUB 0764 RD", "RD CUB 0764", "rdCUB 0764"]:
    checar(f"grafia {entrada!r}", "(RD) CUB 0764", placas.formatar(entrada))
checar("espaco duplo + RD", "(RD) FJZ 4H64", placas.formatar("FJZ 4H64  (RD)"))
checar("separar_rd base", ("CUB 0764", True), placas.separar_rd("CUB 0764 (RD)"))
checar("separar_rd sem marcador", ("CUB 0764", False), placas.separar_rd("CUB 0764"))

print("[3] ARMADILHA — 'RD' que faz parte da placa (16 casos reais)")
# se algum destes virar '(RD) ...' o modulo esta destruindo placa legitima
for p in ["RDM 0G81", "RDM 3C27", "RDM 3E86", "RDM 3I31", "RDM 3J08", "RDM 4G14",
          "RDM 4G33", "RDM 5J60", "RDM 7B92", "RDM 8I35", "RDM 8J13",
          "RDQ 5G58", "RDS 0B93", "DRD 4189", "QRD 0A53", "RRD 1C69"]:
    checar(f"{p} intacta", p, placas.formatar(p))
    checar(f"{p} sem rd", (p, False), placas.separar_rd(p))

print("[4] não convencional — chassi NÃO se normaliza")
for chassi in ["CAT0318DLSGB30031", "9BWKB45U8KP018607", "HCCZTL80ANCJ48061", "CHASSI:17100057"]:
    checar(f"{chassi} preservado", chassi, placas.formatar(chassi))
    checar(f"{chassi} nao convencional", False, placas.eh_convencional(chassi))
checar("convencional e convencional", True, placas.eh_convencional("ABC 1234"))
checar("mercosul e convencional", True, placas.eh_convencional("OVG7C78"))
# o marcador nao pode desqualificar a placa -- se desse False aqui, um chamador
# trataria '(RD) ABC 1234' como chassi e deixaria de normalizar
checar("com RD ainda e convencional", True, placas.eh_convencional("(RD) ABC 1234"))
checar("com RD colado ainda e convencional", True, placas.eh_convencional("ovg7c78 (rd)"))
checar("RDM e convencional (prefixo legitimo)", True, placas.eh_convencional("RDM 0G81"))

print("[5] chave de comparação — grafias diferentes, mesma chave")
checar("chave com RD depois", ("CUB0764", True), placas.chave("CUB 0764 (RD)"))
checar("chave com RD antes", ("CUB0764", True), placas.chave("(RD) CUB 0764"))
checar("chave sem RD", ("CUB0764", False), placas.chave("CUB0764"))
checar("as 2 grafias batem",
       placas.chave("CUB 0764 (RD)"), placas.chave("(RD) CUB 0764"))
checar("base != RD (nao colidem)",
       True, placas.chave("CUB 0764") != placas.chave("(RD) CUB 0764"))
checar("RDM nao vira RD", ("RDM0G81", False), placas.chave("RDM 0G81"))

print("[6] montar")
checar("montar com rd", "(RD) ABC 1234", placas.montar("ABC1234", True))
checar("montar sem rd", "ABC 1234", placas.montar("ABC1234", False))
checar("montar idempotente", "(RD) ABC 1234", placas.montar("(RD) ABC 1234", True))

print("[7] bordas")
checar("vazio", "", placas.formatar(""))
checar("None", "", placas.formatar(None))
checar("separar_rd vazio", (None, False), placas.separar_rd(""))

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
