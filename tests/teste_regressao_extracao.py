"""Teste de REGRESSÃO da extração de termos — 9 documentos REAIS.

Criado em 2026-07-27 para substituir o `test_extracao.py`, que só imprimia JSON
e não afirmava nada (e apontava para `/tmp`, que o reboot limpa).

Por que existe: o extrator já quebrou **em silêncio**. O bug da Transferência
engolia 14 de 28 placas sem erro nenhum, e a Rescisão lia só a 1ª página
(12 em vez de 26) — os dois só apareceram porque alguém conferiu na mão. Cada
número travado aqui é um bug que já aconteceu.

Roda na VPS:  venv/bin/python tests/teste_regressao_extracao.py
Só leitura — não toca banco, Harmonit nem WESO.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel.pdf_extractor import extrair_campos  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


def extrair(arquivo, perfil):
    campos = extrair_campos(str(FIXTURES / arquivo), perfil)
    campos.pop("texto_bruto", None)
    return campos


def n_placas(c):
    return len(c.get("placas") or [])


def n_itens(c):
    return len(c.get("itens") or [])


print("\n[1] Cliente novo — 8768 (FAG)")
c = extrair("cliente_novo.pdf", "cliente_novo")
checar("termo", "8768", c.get("termo"))
checar("cnpj", "66.994.515/0001-62", c.get("cnpj"))
checar("cliente", "FAG ENGENHARIA E SOLUCOES LTDA", c.get("cliente_nome_sugerido"))
checar("placas", 2, n_placas(c))
checar("itens", 13, n_itens(c))
checar("1a placa", "TZW 1A93", (c["placas"][0] or {}).get("placa"))
# fix do comodato (20/07): todo item traz de onde vem o custo
checar("todo item tem comodato_ou_aquisicao", True,
       all("comodato_ou_aquisicao" in i for i in c["itens"]))

print("\n[2] Cliente novo 2 — 8771 (ELVINO, 28 veículos em 2 colunas)")
c = extrair("cliente_novo2.pdf", "cliente_novo")
checar("termo", "8771", c.get("termo"))
# GUARDA do bug de 2 colunas: lia só a 1a, 14 de 28 sumiam em silêncio
checar("placas (bug das 2 colunas)", 28, n_placas(c))
checar("itens", 5, n_itens(c))
checar("sem_bloqueio detectado na 1a placa", True, (c["placas"][0] or {}).get("sem_bloqueio"))

print("\n[3] Aditivo — 8782")
c = extrair("aditivo2.pdf", "aditivo")
checar("termo", "8782", c.get("termo"))
checar("placas", 1, n_placas(c))
checar("placa", "EHH 7B35", (c["placas"][0] or {}).get("placa"))
checar("itens", 8, n_itens(c))

print("\n[4] Aditivo TRZ — 8790")
c = extrair("trz_8790_aditivo.pdf", "aditivo")
checar("termo", "8790", c.get("termo"))
checar("cnpj", "11.287.456/0003-62", c.get("cnpj"))
checar("placas", 1, n_placas(c))
checar("itens", 7, n_itens(c))

print("\n[5] Rescisão — 8788 (continuação de página)")
c = extrair("rescisao.pdf", "rescisao")
checar("termo", "8788", c.get("termo"))
checar("cliente", "CONSTRUCTO CONSTRUCOES SA", c.get("cliente_nome_sugerido"))
# GUARDA do bug de continuação: lia só a 1a página e dava 12
checar("veiculos, lista crua (bug da 1a pagina)", 26, len(c.get("veiculos") or []))
# `placas` exclui os 7 sem placa -> 26-7=19. Travado dos DOIS lados de proposito:
# se um mudar sem o outro, alguma coisa regrediu.
checar("placas (so as que tem placa)", 19, n_placas(c))
checar("sem placa", 7, sum(1 for v in c["veiculos"] if not v.get("placa")))
checar("itens", 4, n_itens(c))
# encargo de rescisao tem que sobreviver (vai pra OS financeira)
checar("encargo de aviso previo presente", True,
       any("AVISO PRÉVIO" in (i.get("descricao") or "").upper() for i in c["itens"]))

print("\n[6] Substituição — 8786 (estrutura de PARES, não `placas`)")
c = extrair("substituicao.pdf", "substituicao")
checar("termo", "8786", c.get("termo"))
checar("pares", 1, len(c.get("pares") or []))
par = (c.get("pares") or [{}])[0]
checar("placa que sai", "BZR 5B97", par.get("placa_saida"))
checar("placa que entra", "UPW 3G17", par.get("placa_entrada"))
# acessorio marcado com bullet vira item (fix de 23/07)
checar("acessorio do bullet virou item", True,
       any("Central 24" in (i.get("descricao") or "") for i in (c.get("itens") or [])))
checar("taxa mesmo local", "199,90", c.get("taxa_mesmo_local"))
checar("taxa local diferente", "299,90", c.get("taxa_local_diferente"))

print("\n[7] Termo errado — 8787 (rescisão que é transferência)")
c = extrair("termo_errado.pdf", "rescisao")
checar("termo", "8787", c.get("termo"))
checar("placas", 1, n_placas(c))
# o alerta e o que impede gerar OS de rescisao a partir de uma transferencia
checar("alerta de transferencia disparado", True, bool(c.get("alerta_transferencia")))

print("\n[8] Transferência (cliente existente) — 8785")
c = extrair("transferencia_existente.pdf", "transferencia")
checar("termo", "8785", c.get("termo"))
checar("cliente", "A.L.O TRANSPORTES LTDA", c.get("cliente_nome_sugerido"))
checar("placas", 1, n_placas(c))
checar("placa", "PGT 6726", (c["placas"][0] or {}).get("placa"))
checar("itens", 7, n_itens(c))

print("\n[9] Transferência (cliente novo) — 8771")
c = extrair("transferencia_novo.pdf", "transferencia")
checar("termo", "8771", c.get("termo"))
# GUARDA: transferencia roteava pro parser de rescisao e perdia tudo (bug 16/07)
checar("placas (bug de roteamento do parser)", 28, n_placas(c))
checar("itens", 5, n_itens(c))
checar("cnpj", "55.524.605/0001-73", c.get("cnpj"))

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
