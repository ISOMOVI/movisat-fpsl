"""E3 da Conferência de Fechamento (01/10): as peças puras, com dublê.

Não toca banco, cache nem rede. O que a E3 tem de próprio -- o resto é a regra
da oficina, testada em `teste_conferencia_oficina.py`:

  - `mapas_weso`: a WESO ao vivo vira as três buscas que a regra precisa;
  - `_datascope_na_porta`: faltar resposta do DataScope, numa OS que JÁ está em
    "Serviço Realizado", é anomalia -- cinza, não "ainda não".

    venv/bin/python tests/teste_conferencia_e3.py
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.services import conferencia_fechamento as cf   # noqa: E402
from fpsl_weso import storage                                  # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


# Formato real de `/Veiculos/Consultar` (docs/weso/01_Veiculos.md): o chassi
# mora em `complemento`, não no topo.
VEICULOS = [
    {"id": 1, "placa": "DOT 0C95", "descricao": "GOL", "rastreador_id": 10,
     "complemento": {"chassi": "9BWAAAAAAAAAAAAAA"}},
    {"id": 2, "placa": " RDM 3E86 ", "descricao": "SIENA", "rastreador_id": None,
     "complemento": None},
    {"id": 3, "placa": "UEX 5E41", "descricao": "CHASSI: 9BM951500TB474833",
     "rastreador_id": 20, "complemento": {}},
]
RASTREADORES = [
    {"id": 10, "numeroSerie": "007933269", "modelo": "Suntech ST310", "situacao": "Instalado"},
    {"id": 20, "numeroSerie": "905555555", "modelo": "Suntech ST300", "situacao": "Instalado"},
]

m = cf.mapas_weso(VEICULOS, RASTREADORES)

print("\n[1] placa: casa NORMALIZADA, nunca por igualdade exata")
# 🚨 `/Veiculos/Consultar?placa=` compara exato e devolve VAZIO com espaço
# (equipamentos.py, 29/07). Numa retirada, "não achei a placa" viraria OK falso.
checar("placa com espaço nas pontas na WESO é achada", " RDM 3E86 ",
       (m["veiculo_por_placa"]("RDM 3E86") or {}).get("placa"))
checar("e sem o espaço do meio também", "DOT 0C95",
       (m["veiculo_por_placa"]("DOT0C95") or {}).get("placa"))
checar("placa que não existe -> None", None, m["veiculo_por_placa"]("ZZZ9Z99"))

print("\n[2] o caminho inverso: onde a série está AGORA")
checar("rastreador 10 está na DOT 0C95", "DOT 0C95",
       (m["placa_do_rastreador"](10) or {}).get("placa"))
checar("e traz o chassi do complemento", "9BWAAAAAAAAAAAAAA",
       (m["placa_do_rastreador"](10) or {}).get("chassi"))
checar("e a descrição (onde a WESO guarda chassi às vezes)", "CHASSI: 9BM951500TB474833",
       (m["placa_do_rastreador"](20) or {}).get("descricao"))
checar("rastreador em nenhum veículo -> None", None, m["placa_do_rastreador"](999))
checar("complemento nulo não quebra", None,
       (m["veiculo_por_placa"]("RDM 3E86") or {}).get("chassi"))

print("\n[3] série")
checar("acha pela série", 10, (m["rastreador_por_serial"]("007933269") or {}).get("id"))
checar("tolera espaço na série", 10, (m["rastreador_por_serial"](" 007933269 ") or {}).get("id"))
checar("série desconhecida -> None", None, m["rastreador_por_serial"]("000"))

print("\n[4] DataScope NA PORTA: faltar resposta é anomalia cinza")
ds_ok, estado, motivo = cf._datascope_na_porta(None)
checar("sem resposta -> None (cinza), nunca False", None, ds_ok)
checar("e o motivo manda conferir o Nº da O.S.", True, "Nº da O.S." in motivo)
ds_ok, estado, _ = cf._datascope_na_porta({"form_state": "Finalizado"})
checar("Finalizado no DataScope -> True", True, ds_ok)
ds_ok, estado, _ = cf._datascope_na_porta({"form_state": "Cancelado"})
checar("estado de problema -> False", False, ds_ok)

print("\n[5] a porta e a janela, como constantes")
checar("porta = 15694 Serviço Realizado", 15694, storage.SITUACAO_SERVICO_REALIZADO)
checar("janela = 30 dias (decisão dele)", 30, cf.JANELA_DIAS)

print("\n" + "=" * 62)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
