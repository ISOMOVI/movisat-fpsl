"""Dump compacto da extração dos 9 termos reais — base do teste de regressão.

Roda na VPS: venv/bin/python tests/dump_extracao.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel.pdf_extractor import extrair_campos  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

CASOS = [
    ("cliente_novo.pdf", "cliente_novo"),
    ("cliente_novo2.pdf", "cliente_novo"),
    ("aditivo2.pdf", "aditivo"),
    ("trz_8790_aditivo.pdf", "aditivo"),
    ("rescisao.pdf", "rescisao"),
    ("substituicao.pdf", "substituicao"),
    ("termo_errado.pdf", "rescisao"),
    ("transferencia_existente.pdf", "transferencia"),
    ("transferencia_novo.pdf", "transferencia"),
]

print(f"{'arquivo':30s} {'termo':6s} {'placas':>6s} {'itens':>6s}  cliente / cnpj")
for arquivo, perfil in CASOS:
    c = extrair_campos(str(FIXTURES / arquivo), perfil)
    placas = c.get("placas") or []
    itens = c.get("itens") or []
    print(f"{arquivo:30s} {str(c.get('termo')):6s} {len(placas):6d} {len(itens):6d}  "
          f"{str(c.get('cliente_nome_sugerido'))[:34]:34s} {c.get('cnpj') or c.get('cpf')}")
    primeiras = [p.get("placa") for p in placas[:3] if isinstance(p, dict)]
    if primeiras:
        print(f"{'':30s} 1as placas: {primeiras}")
