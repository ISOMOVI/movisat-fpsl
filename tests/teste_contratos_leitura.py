"""Leitura do termo para a Gestão de Contratos — 7 documentos REAIS.

Trava o que a camada da `CTR_1.1` tira do PDF: qual evento cada perfil produz,
a vaga do "A DEFINIR" e a anotação de troca do Harmonit.

Por que existe: a auditoria de 13/10 errou duas vezes exatamente aqui, e as
duas aparecem travadas abaixo.
  1. procurava a expressão "a definir" no TEXTO do PDF e casava "a definição"
     das cláusulas -- 22 placas deram por assinadas sem estarem;
  2. lia a anotação de troca com padrão frouxo e pegava "Sem Alteração", que é
     rótulo de coluna.

🚨 O QUE ESTE TESTE NÃO PODE DEIXAR PASSAR: a anotação de troca existir na
versão ASSINADA. Se existir, a regra dele ("termo assinado + troca registrada
no Harmonit vale") perde o pé -- ela depende de a anotação ser posterior à
assinatura.

Roda na VPS:  venv/bin/python tests/teste_contratos_leitura.py
Só leitura -- não toca banco, Harmonit nem WESO.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel.contratos_eventos import ENTRA, RESCINDE, SAI, UPGRADE  # noqa: E402
from fpsl_weso.painel.contratos_leitura import (  # noqa: E402
    PERFIS, PERFIS_FORA, eh_vaga, ler, troca_registrada)

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


def lido(arquivo, perfil, **kw):
    return ler(str(FIXTURES / arquivo), perfil, **kw)


def acoes(r):
    return [(e["acao"], e["placa"]) for e in r["eventos"]]


print("\n[1] cada perfil produz o evento certo")
r = lido("substituicao.pdf", "substituicao")
checar("substituicao 8786: um SAI e um ENTRA", [(SAI, "BZR 5B97"), (ENTRA, "UPW 3G17")], acoes(r))
checar("e o numero do termo sai do documento", "8786", r["numero"])

r = lido("rescisao_8842.pdf", "rescisao")
checar("rescisao 8842: RESCINDE", [(RESCINDE, "EJV 3C41")], acoes(r))
# ⚠️ Medido pela Operacao nos termos 8788 e 8842: o layout da rescisao traz
# so o NOME do cliente. A tela PERGUNTA em vez de adivinhar -- cliente errado
# grava evento no contrato de outra empresa (33 casos na auditoria).
checar("rescisao nao traz CNPJ, e a tela avisa", True,
       any("não traz CNPJ" in a for a in r["avisos"]))

r = lido("upgrade_8827.pdf", "upgrade")
checar("upgrade 8827: UPGRADE, que nao muda placa", [(UPGRADE, "GGA 5B15")], acoes(r))
checar("veiculo sem placa vai para a tela, nao para o lixo", True,
       any("sem placa" in a for a in r["avisos"]))

r = lido("contrato_novo_8739.pdf", "contrato_novo")
checar("contrato 8739: 4 ENTRA", 4, len(r["eventos"]))
checar("e avisa que os identificadores sao chassi", True,
       any("não convencional" in a for a in r["avisos"]))

print("\n[2] a vaga do 'A DEFINIR' nao virou placa")
# 🚨 O extrator ja troca "A DEFINIR" por `A_DEFINIR_<termo>` e sugere o apelido
# `TERMO:<termo>`. E por isso que a WESO tem veiculos chamados `TERMO 8396`:
# sao vagas esperando placa. Dado estruturado nao confunde com "a definicao".
checar("eh_vaga reconhece a marca do extrator", "8852", eh_vaga("A_DEFINIR_8852"))
checar("e nao confunde placa de verdade", None, eh_vaga("FWF 6C16"))
checar("nem a palavra solta", None, eh_vaga("a definir"))
r = lido("aditivo_8852.pdf", "aditivo")
checar("aditivo 8852: 2 placas reais entram", [(ENTRA, "FWF 6C16"), (ENTRA, "GHL 0A32")], acoes(r))
checar("a vaga NAO gerou evento", 1, len(r["vagas"]))
checar("e o termo fica marcado a_definir", True, r["a_definir"])
checar("a vaga aponta o termo dela", "8852", r["vagas"][0]["termo"])
checar("com o apelido que a WESO usa", "TERMO:8852", r["vagas"][0]["apelido_sugerido"])

print("\n[3] anotacao de troca: so existe na versao do Harmonit")
# Maxi Confort 8872. O assinado traz DVS 2992; o PDF do Harmonit do MESMO termo
# acrescenta FAC 5H30 com a anotacao, e nao tira a antiga.
anot = troca_registrada(str(FIXTURES / "harmonit_8872_troca.pdf"))
checar("acha a anotacao no PDF do Harmonit", True, bool(anot))
checar("e devolve a frase, para a tela mostrar o motivo", True,
       "FAC 5H30" in (anot or "") and "pediu altera" in (anot or ""))
# 🚨 A REGRA DELE DEPENDE DISTO: a anotacao e POSTERIOR a assinatura. Se ela
# aparecesse no documento assinado, "assinado + troca registrada" nao provaria
# nada.
checar("NAO acha anotacao no documento ASSINADO", None,
       troca_registrada(str(FIXTURES / "assinado_8872.pdf")))
# ⚠️ Substituicao regular NAO e troca: o proprio termo ja tem as duas colunas.
checar("substituicao regular nao e lida como troca", None,
       troca_registrada(str(FIXTURES / "substituicao.pdf")))
# ⚠️ "A definir" tambem nao e troca -- sao regras diferentes.
checar("aditivo com 'a definir' nao e lido como troca", None,
       troca_registrada(str(FIXTURES / "aditivo_8852.pdf")))

print("\n[4] o assinado da Maxi Confort tem as 10 placas, sem a FAC 5H30")
r = lido("assinado_8872.pdf", "contrato_novo")
placas = sorted(e["placa"].replace(" ", "") for e in r["eventos"])
checar("10 placas no documento assinado", 10, len(placas))
checar("DVS2992 esta no assinado", True, "DVS2992" in placas)
checar("FAC5H30 NAO esta no assinado", False, "FAC5H30" in placas)
checar("e o CNPJ e o da Maxi Confort", "20480457000158", r["cnpj"])

print("\n[5] perfil que nao nasce de documento e RECUSADO, com o motivo")
# `M12`: a tela nao promete o que nao faz. Manutencao e ressarcimento sem termo
# nao tem termo para subir; a transferencia no modelo novo tem leitor proprio
# na Operacoes e ainda nao e suportada aqui.
for perfil in ("manutencao_local", "manutencao_troca", "ressarcimento_sem_termo", "transferencia_termo_novo"):
    try:
        lido("substituicao.pdf", perfil)
        checar(f"{perfil} recusado", "ValueError", "aceitou")
    except ValueError as e:
        checar(f"{perfil} recusado com motivo", True, perfil in str(e) and len(str(e)) > len(perfil) + 3)
try:
    lido("substituicao.pdf", "perfil_que_nao_existe")
    checar("perfil desconhecido recusado", "ValueError", "aceitou")
except ValueError as e:
    checar("perfil desconhecido recusado", True, "desconhecido" in str(e))

print("\n[6] os perfis suportados e os de fora nao se sobrepoem")
checar("nenhum perfil esta nas duas listas", set(), set(PERFIS) & set(PERFIS_FORA))
checar("todo perfil suportado diz o que faz com a placa", True,
       all(p.get("acao") and p.get("layout") for p in PERFIS.values()))

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
