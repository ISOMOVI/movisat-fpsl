"""Motor de eventos da Gestão de Contratos — 5 clientes REAIS da auditoria de 13/10/2026.

Cada número travado aqui é uma regra dele, e cada cliente é um caso que a
auditoria resolveu à mão antes de existir código:

    JLM          rescisão CANCELADA na Clicksign não apaga placa de contrato assinado
    Maxi Confort troca registrada no Harmonit, em termo assinado, VALE
    Zago         substituição assinada executada pela metade na WESO
    Eco System   termo assinado com "a definir"; placa preenchida depois
    Horse        cliente que saiu sem rescisão assinada -- as placas continuam no contrato

🚨 `hoje` É FIXO EM 2026-10-13 nos casos de aviso prévio. Sem isso o teste
passa hoje e reprova em 90 dias, e um teste que muda de resposta sozinho não
trava nada.

Roda na VPS:  venv/bin/python tests/teste_contratos_eventos.py
Só leitura -- não toca banco, Harmonit, WESO nem disco.
"""
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel.contratos_eventos import (  # noqa: E402
    ATIVA, EM_AVISO_PREVIO, RESCINDIDA, SUBSTITUIDA,
    ENTRA, SAI, RESCINDE, UPGRADE, ASSINADO, HARMONIT,
    ativas, chave, situacao_das_placas)

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


def ev(acao, placa, fonte=ASSINADO, **extra):
    return dict(acao=acao, placa=placa, fonte=fonte, **extra)


def termo(numero, tipo, assinado, assinado_em, eventos, **extra):
    return dict(numero=numero, empresa="MOVISAT", tipo=tipo, assinado=assinado,
                assinado_em=assinado_em, eventos=eventos, **extra)


print("\n[1] chave: equivalencia Mercosul, chassi e (RD)")
checar("FIV9D99 e FIV9399 sao a mesma placa", chave("FIV 9399"), chave("FIV9D99"))
checar("ABC1234 vira Mercosul", "ABC1C34", chave("ABC-1234"))
checar("placa ja Mercosul nao muda", "ABC1C34", chave("ABC1C34"))
checar("(RD) e o mesmo veiculo da placa", chave("EDF 5724"), chave("(RD) EDF 5724"))
checar("prefixo CHASSI sai", "9BWKB45U8KP018607", chave("CHASSI: 9BWKB45U8KP018607"))
# ⚠️ Placas REAIS da mesma frota que diferem em 1 caractere NAO podem colidir:
# foi a regra antiga que juntou 711 placas, e ele mandou abandona-la.
checar("DTX7581 e DTX7583 continuam DIFERENTES", True, chave("DTX7581") != chave("DTX7583"))
checar("DAT0267 e DAT0262 continuam DIFERENTES", True, chave("DAT0267") != chave("DAT0262"))

print("\n[2] JLM 62702410000131 — rescisao CANCELADA nao apaga placa assinada")
# O distrato 6026 esta CANCELADO na Clicksign e o 7235 nao tem registro nenhum.
# Pela regra dele, nenhum dos dois decide: quem manda e o contrato 5029.
jlm = [
    termo(5029, "CONTRATO", True, "2021-06-28",
          [ev(ENTRA, p) for p in ("CPJ7279", "BKW9955", "BWO9236", "FIV9399", "DZH2E13", "DVT0268")]),
    termo(6026, "RESCISAO", False, None,
          [ev(RESCINDE, p) for p in ("CPJ7279", "BKW9955", "BWO9236", "FIV9399", "DZH2E13", "DVT0268")]),
    termo(7171, "RESSARCIMENTO_RESCISAO", True, "2024-10-22", [ev(RESCINDE, "FIV9399")]),
    termo(7172, "ADITIVO", True, "2024-11-11", [ev(ENTRA, "FIV9399")]),
    termo(7197, "EMPRESTIMO_TESTE", True, "2025-01-17", [ev(ENTRA, "FIV9399")]),
    # O termo traz a placa como FIV9D99 -- mesma placa, formato Mercosul.
    termo(7235, "UPGRADE", False, None, [ev(UPGRADE, "FIV9D99")]),
    termo(8564, "RESCISAO", True, "2026-07-16", [ev(RESCINDE, "FIV9399")]),
]
s = situacao_das_placas(jlm, HOJE)
checar("as 5 placas do contrato 5029 seguem ATIVAS (6026 cancelado nao conta)",
       [ATIVA] * 5, [s[chave(p)]["situacao"] for p in ("CPJ7279", "BKW9955", "BWO9236", "DZH2E13", "DVT0268")])
checar("base das 5 e 'assinado'", {ASSINADO}, {s[chave(p)]["base"] for p in ("CPJ7279", "BKW9955")})
# 8564 assinado em 16/07/2026 + 90 dias = 14/10/2026, e hoje e 13/10.
checar("FIV9399 em aviso previo (rescisao assinada ha 89 dias)", EM_AVISO_PREVIO, s[chave("FIV9399")]["situacao"])
checar("aviso vence em 14/10/2026", "2026-10-14", s[chave("FIV9399")]["aviso_ate"])
checar("aviso previo AINDA conta como sustentada", 6, len(ativas(s)))
checar("o upgrade 7235 nao criou placa nova", 6, len(s))

print("\n[3] Maxi Confort 20480457000158 — troca registrada no Harmonit VALE")
# Contrato 8872 assinado com DVS2992; o PDF do Harmonit do MESMO termo
# acrescenta FAC5H30 com a anotacao da troca, sem tirar a antiga.
assinadas = ("CYR2B15", "DVS2992", "DVT3D81", "EJV7D20", "FLT0F07",
             "FTO3F51", "GEE7E85", "GFZ0726", "GYQ4J53", "HGO9D77")
maxi = [termo(8872, "CONTRATO", True, "2026-09-15",
              [ev(ENTRA, p) for p in assinadas] +
              [ev(ENTRA, "FAC5H30", HARMONIT), ev(SAI, "DVS2992", HARMONIT)],
              troca_registrada="FAC 5H30 - Cliente pediu alteracao da placa em 30/09/2026 via Movizap")]
s = situacao_das_placas(maxi, HOJE)
checar("FAC5H30 (a nova) esta ATIVA", ATIVA, s[chave("FAC5H30")]["situacao"])
checar("e a base diz que foi troca registrada",
       "assinado (troca registrada no Harmonit)", s[chave("FAC5H30")]["base"])
checar("DVS2992 (a antiga) saiu", SUBSTITUIDA, s[chave("DVS2992")]["situacao"])
checar("o contrato sustenta 10 placas, igual a WESO", 10, len(ativas(s)))
# ⚠️ SEM a anotacao, a placa do Harmonit NAO entra: era assim que termo
# assinado "ganhava" placa depois da assinatura (256 casos medidos).
sem_anotacao = [dict(maxi[0], troca_registrada=None)]
s2 = situacao_das_placas(sem_anotacao, HOJE)
checar("sem anotacao, FAC5H30 nao e assinada", "nao assinado", s2[chave("FAC5H30")]["base"])

print("\n[4] Zago 44213607000125 — substituicao assinada, 2 cancelados pelo caminho")
zago = [
    termo(3285, "CONTRATO", True, "2024-02-14", [ev(ENTRA, p) for p in ("ETR2C29", "DDU9873", "DPC9F69")]),
    termo(3394, "ADITIVO", True, "2024-05-07", [ev(ENTRA, "RVF5G49")]),
    termo(3510, "EMPRESTIMO_TESTE", True, "2024-08-02", [ev(ENTRA, "ETR2C29")]),
    termo(3566, "SUBSTITUICAO", True, "2024-09-26", [ev(SAI, "DDU9873"), ev(ENTRA, "FFW4925")]),
    termo(8011, "SUBSTITUICAO", True, "2025-04-14", [ev(SAI, "ETR2C29"), ev(ENTRA, "NWO4C95")]),
    termo(8590, "RESCISAO", False, None, [ev(RESCINDE, "FFW4925"), ev(RESCINDE, "RVF5G49")]),
    termo(8838, "SUBSTITUICAO", True, "2026-09-11",
          [ev(SAI, "RVF5G49"), ev(SAI, "FFW4925"), ev(ENTRA, "FUX7B86"), ev(ENTRA, "BRX9I89")]),
    termo(8853, "RESSARCIMENTO_RESCISAO", False, None, [ev(RESCINDE, "RVF5G49")]),
]
s = situacao_das_placas(zago, HOJE)
checar("o contrato sustenta 4 placas", ["BRX9I89", "DPC9F69", "FUX7B86", "NWO4C95"], ativas(s))
# 🚨 SAIR POR SUBSTITUICAO NAO E RESCISAO: nao ha aviso previo de 90 dias,
# porque o equipamento passa para o veiculo que entrou no mesmo termo. A
# planilha chamava isso de "rescindida ... (aviso previo ok)" e mentia.
checar("RVF5G49 saiu por SUBSTITUICAO, nao rescisao", SUBSTITUIDA, s[chave("RVF5G49")]["situacao"])
checar("e substituicao nao tem aviso previo", None, s[chave("RVF5G49")]["aviso_ate"])
checar("FFW4925 tambem saiu por substituicao", SUBSTITUIDA, s[chave("FFW4925")]["situacao"])
checar("ETR2C29 saiu na substituicao 8011", SUBSTITUIDA, s[chave("ETR2C29")]["situacao"])
checar("o ressarcimento 8853, cancelado, nao mexeu em RVF5G49",
       8838, s[chave("RVF5G49")]["termo_vigente"])

print("\n[5] Eco System 02067846000174 — assinado com 'a definir'")
# O documento assinado traz "A DEFINIR" na coluna de entrada; a placa real
# (SIF0C19) foi preenchida depois, no PDF do Harmonit do mesmo termo.
eco = [termo(3085, "SUBSTITUICAO", True, "2023-08-31",
             [ev(SAI, "GFH1E39"), ev(ENTRA, "A DEFINIR"), ev(ENTRA, "SIF0C19", HARMONIT)],
             a_definir=True)]
s = situacao_das_placas(eco, HOJE)
checar("SIF0C19 esta ATIVA", ATIVA, s[chave("SIF0C19")]["situacao"])
checar("a base diz que veio de 'a definir'",
       "assinado com 'a definir'; placa preenchida no Harmonit", s[chave("SIF0C19")]["base"])
checar("'A DEFINIR' NAO virou placa", False, chave("A DEFINIR") in s)
checar("o contrato sustenta 1 placa", ["SIF0C19"], ativas(s))

print("\n[6] Horse 23076958000161 — saiu sem rescisao assinada")
# O distrato 698, que tirava as placas, esta CANCELADO na Clicksign. Pela regra
# dele as placas CONTINUAM no contrato -- e e por isso que 351 placas da Horse
# aparecem como assinadas e nao instaladas, o maior caso da auditoria.
horse = [
    termo(765, "CONTRATO", True, "2019-11-26", [ev(ENTRA, "BUW8732"), ev(ENTRA, "BVT0745")]),
    termo(698, "RESCISAO", False, None, [ev(RESCINDE, "BUW8732"), ev(RESCINDE, "BVT0745")]),
]
s = situacao_das_placas(horse, HOJE)
checar("as placas seguem no contrato (distrato cancelado)", ["BUW8732", "BVT0745"], sorted(ativas(s)))

print("\n[7] a excecao da regra: falta dos dois lados")
# Regra dele: *"termo nao assinado nao conta -- a menos que falte em ambos os
# lados"*. Placa que NENHUM termo assinado menciona e sustentada pelo termo sem
# assinatura, e sai MARCADA. Sao 229 placas medidas em uso assim.
so_harmonit = [termo(9001, "CONTRATO", False, None, [ev(ENTRA, "GHU6727")])]
s = situacao_das_placas(so_harmonit, HOJE)
checar("placa sem nenhum termo assinado fica ATIVA", ATIVA, s[chave("GHU6727")]["situacao"])
checar("mas a base denuncia que nao ha assinatura", "nao assinado", s[chave("GHU6727")]["base"])
checar("e a observacao diz por que",
       True, "nenhum termo assinado trata desta placa" in (s[chave("GHU6727")]["obs"] or ""))

print("\n[8] ordem e pelo NUMERO do termo, nunca pela data")
# A JLM prova por que: o contrato 5029 esta datado de 2026 e foi rescindido
# pelo 6026, que e posterior em numero e anterior em data.
fora_de_ordem = [
    termo(8000, "RESCISAO", True, "2020-01-01", [ev(RESCINDE, "AAA1234")]),
    termo(1000, "CONTRATO", True, "2026-06-01", [ev(ENTRA, "AAA1234")]),
]
s = situacao_das_placas(fora_de_ordem, HOJE)
checar("rescisao de numero maior vence o contrato de data maior",
       RESCINDIDA, s[chave("AAA1234")]["situacao"])

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
