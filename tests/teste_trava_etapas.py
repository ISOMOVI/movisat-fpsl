"""A trava de etapas da aba Operações. 2026-08-21.

🚨 POR QUE ESTE ARQUIVO EXISTE. A trava ficou SOLTA da F1 até 21/08 e as 1.322
verificações da suíte não viram, porque nenhuma exercitava a tela: os testes da
aba liam o FONTE e o fonte estava certo. O comentário dizia

    "Aqui a etapa N só abre com a N-1 concluída."

e logo abaixo

    "Na F1 nada conclui nada, então a trava está solta de propósito."

A segunda frase sobreviveu a cinco fases. Em 21/08 o operador foi da etapa 1
direto para a 4 e a prévia devolveu 400 "Nenhuma placa foi informada" -- o erro
certo, na hora errada, depois de todo o trabalho. O registro prova: os dois
lotes daquele dia estão em `etapa 1` com ZERO placas gravadas.

⚠️ FONTE QUE DESCREVE O COMPORTAMENTO NÃO É O COMPORTAMENTO. Por isso aqui não
há nenhum `grep`: o `exercitar_operacoes.js` roda o script da página num DOM de
mentira e CLICA em Avançar, e este arquivo confere onde a tela parou.

🚨 REPROVA SEM A CORREÇÃO -- conferido em 21/08 rodando contra a versão
anterior de `operacoes.html`: `etapa_apos_salto_para_4` devolvia 4.

Roda na VPS: venv/bin/python tests/teste_trava_etapas.py
🚨 NÃO FAZ REDE. O `fetch` é de mentira e nada sai da máquina.
"""
import json
import pathlib
import shutil
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
EXERCICIO = RAIZ / "tests" / "exercitar_operacoes.js"
TELA = RAIZ / "frontend" / "operacoes.html"

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def v(chave, padrao=None):
    """Leitura tolerante do resultado.

    ⚠️ SEM ISTO O TESTE ESTOURA EM VEZ DE REPROVAR. Rodando contra a versão
    anterior da tela -- que não tem o `faltaDica` -- o `KeyError` matava o
    arquivo na terceira verificação e escondia as outras 22. Teste que quebra
    não é teste que reprova: quem lê não descobre o tamanho do estrago.
    """
    return RESULTADO.get(chave, padrao)


def rodar(caminho_tela):
    """Roda a tela no DOM de mentira e devolve o que ela fez."""
    saida = subprocess.run(
        ["node", str(EXERCICIO), str(caminho_tela)],
        capture_output=True, text=True, timeout=120)
    if saida.returncode != 0:
        raise RuntimeError(f"o exercício não rodou: {saida.stderr[:400]}")
    return json.loads(saida.stdout)


if shutil.which("node") is None:
    print("node ausente -- este teste exige node para rodar a tela")
    sys.exit(1)

print("== a tela aguenta o fluxo inteiro ==")
RESULTADO = r = rodar(TELA)
checar("nenhum erro de execução no fluxo de ponta a ponta",
       (v("erros") or []) == [], str(v("erros"))[:300])

print()
print("== etapa 1: sem termo não avança ==")
checar("o seletor de tipo está ligado a alguma função",
       (v("ouvintes_perfil") or 0) >= 1)
checar("Avançar nasce desabilitado", v("avancar_travado_sem_termo") is True)
checar("a dica diz o que falta, ANTES do clique",
       "PDF do termo" in (v("dica_sem_termo") or ""), v("dica_sem_termo"))
checar("clicar em Avançar sem termo não sai da etapa 1",
       v("etapa_apos_avancar_sem_termo") == 1,
       f"foi para a {v('etapa_apos_avancar_sem_termo')}")

print()
print("== 🚨 o salto de 1 para 4, que é o defeito de 21/08 ==")
checar("irPara(4) com nada feito NÃO abre a etapa 4",
       v("etapa_apos_salto_para_4") == 1,
       f"abriu a etapa {v('etapa_apos_salto_para_4')} -- é o defeito de 21/08")

print()
print("== etapa 1 fecha quando o termo traz placa ==")
checar("o termo de mentira trouxe 2 placas", v("placas_lidas") == 2)
checar("Avançar libera com o termo lido", v("avancar_liberado_com_termo") is True)
checar("a etapa 2 abre", v("etapa_apos_termo") == 2)
checar("entrar na etapa 2 consulta o cliente sozinho",
       v("cliente_consultado") is True)

print()
print("== etapa 3: montar não é gravar ==")
checar("com o cliente nos dois sistemas, a etapa 3 abre",
       v("etapa_apos_cliente") == 3)
checar("a etapa 3 montou as 2 linhas", v("linhas_na_etapa3") == 2)
checar("placa montada e NÃO gravada trava o Avançar",
       v("avancar_travado_sem_gravar") is True)
checar("a dica conta quantas faltam",
       "2 placa(s)" in (v("dica_sem_gravar") or ""), v("dica_sem_gravar"))
checar("não abre a etapa 4 com placa pendente",
       v("etapa_apos_placas_pendentes") == 3,
       f"abriu a {v('etapa_apos_placas_pendentes')}")

print()
print("== gravadas, a etapa 4 abre ==")
checar("Avançar libera depois de gravar",
       v("avancar_liberado_apos_gravar") is True)
checar("a etapa 4 abre", v("etapa_final") == 4)

print()
print("== 🚨 placa que FALHOU trava de novo ==")
# Sem isto a OS sairia para placa que a WESO recusou -- que é como a OS 16775
# saiu sem equipamento e sem chip.
checar("placa com falha trava o Avançar", v("avancar_travado_com_falha") is True)
checar("a dica diz que falharam",
       "falharam" in (v("dica_com_falha") or ""), v("dica_com_falha"))
checar("não abre a etapa 4 com placa falhada",
       v("etapa_com_placa_falhada") == 3,
       f"abriu a {v('etapa_com_placa_falhada')}")

print()
print("== trocar o tipo de operação zera a rodada ==")
# 🚨 Sem isto o termo lido para um perfil seguia valendo para outro: trocar de
# Aditivo para Rescisão mantinha as placas do documento anterior, que têm regra
# diferente.
checar("o termo lido é descartado", v("extraido_apos_troca") is True)
checar("as linhas de placa somem", v("linhas_apos_troca") == 0)
checar("o lote deixa de ser o da rodada anterior", v("lote_apos_troca") is True)
checar("volta para a etapa 1", v("etapa_apos_troca") == 1)

print()
print("== perfil sem termo não exige PDF ==")
# Manutenção e ressarcimento sem termo não nascem de documento: exigir o PDF
# neles seria travar o caminho certo, e trava que reprova o certo ensina a
# ignorar a trava.
checar("Avançar fica livre no perfil sem termo",
       v("avancar_liberado_sem_termo_perfil") is True)

print()
print(f"== {ok} verificações OK, {len(falhas)} falha(s) ==")
if falhas:
    for f in falhas:
        print(f"   - {f}")
    sys.exit(1)
