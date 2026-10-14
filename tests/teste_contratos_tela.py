"""Contrato da tela da Gestão de Contratos (`contratos.html`).

Lê o HTML e exige dele o que o painel já exige das outras telas. É o mesmo
remédio do `teste_contrato_sidebar`: o teste LÊ O CONSUMIDOR em vez de supor.

🚨 `M13` — VARREDURA LÊ A TELA, NÃO O SELETOR. As afirmações abaixo são sobre o
TEXTO que está na página, porque é o texto que o operador lê. Seletor é
suposição minha sobre onde a coisa está.

🚨 `M12` — TELA QUE PROMETE O QUE NÃO FAZ É DEFEITO, e duas telas do painel já
mentiram. Nesta etapa a aba LÊ e CONFERE: não grava e não cruza os outros
termos do cliente. A página tem de dizer as duas coisas, com essas palavras.

⚠️ O QUE ESTE TESTE NÃO VÊ: altura, flex, quem rola e elemento cobrindo outro
(`M9`). Isso continua exigindo abrir a tela no navegador.

Roda na VPS:  venv/bin/python tests/teste_contratos_tela.py
Só leitura.
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TELA = RAIZ / "frontend" / "contratos.html"
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}: esperado {esperado!r}, obtido {obtido!r}")


html = TELA.read_text(encoding="utf-8")

print("\n[1] o esqueleto que toda tela do painel tem")
checar("a barra de status entra", True, "barra_status.js" in html)
# ⚠️ ORDEM IMPORTA, e o `teste_barra_status` cobra o mesmo das outras 11: a
# barra vem ANTES do sidebar.
checar("barra ANTES do sidebar", True, html.index("barra_status.js") < html.index("sidebar.js"))
checar("o CSS da barra entra no <head>", True,
       "barra_status.css" in html and html.index("barra_status.css") < html.index("<body"))
checar("usa a mesma chave de token do painel", True, "'fpsl_painel_token'" in html)
checar("sem token, volta para o login", True, "window.location.href = '/painel'" in html)
checar("monta o menu pela permissao da aba", True, "montarSidebar('contratos')" in html)

print("\n[2] M12 — a tela diz o que faz, e o que NAO faz")
# ⚠️ ESTA FRASE JÁ MENTIU. Enquanto a tela só conferia, ela dizia "Nada é
# gravado nesta etapa"; quando a C3 trouxe a gravação, a frase ficou falsa e o
# texto teve de mudar junto. É o `M12` em ato: entrega seguinte não pode deixar
# o texto velho vivo.
checar("declara que a CONFERENCIA nao grava", True, "A conferência não grava nada" in html)
checar("e que quem grava e o passo 4", True, "só o passo 4 grava" in html)
checar("declara que a conferencia olha so este documento", True, "só este documento" in html)
checar("diz que a ficha mostra o efeito somado", True, "efeito somado dos" in html)
checar("e que comparar com a WESO ainda nao acontece", True,
       "Comparar com a WESO ainda não acontece aqui" in html)

print("\n[2b] nenhuma funcao da tela fica orfa")
# 🚨 `prepararGravacao` FICOU DEFINIDA E NUNCA CHAMADA na primeira versão: o
# passo 4 não aparecia depois de conferir. Nenhum teste de Python vê isso, e
# `py_compile` não lê JS -- então a checagem é contar as chamadas.
for fn in ("prepararGravacao", "pintar", "pintarFicha", "gravar", "verFicha", "carregarPerfis",
           "conferir", "carregarRotina", "mudarRotina", "rodarAgora", "verAchados", "msgAud"):
    checar(f"{fn} e definida E usada", True, html.count(fn) >= 2)
# 🚨 "em breve" é a frase que ficou em duas telas e nunca foi matada.
checar("nao promete 'em breve'", False, "em breve" in html.lower())

print("\n[3] a decisao que a tela NAO toma sozinha")
# A troca diz quem entra, nunca quem sai. A tela pede; não inventa.
checar("pede quem sai, em vez de adivinhar", True, "falta dizer quem sai" in html)
checar("mostra a anotacao como motivo", True, "troca_confirmar" in html and "anotacao" in html)
checar("e avisa que o sistema nao inventa", True, "o sistema não inventa" in html)

print("\n[4] o que o documento nao resolve vai para a tela")
checar("veiculo sem placa aparece", True, "veiculos_sem_placa" in html)
checar("com a razao de aparecer", True, "em vez de desaparecer da contagem" in html)
checar("a vaga do 'a definir' aparece", True, "Vaga aguardando placa" in html)
checar("tipo de termo recusado aparece COM o motivo", True,
       "Não entram aqui" in html and "p.motivo" in html)

print("\n[4b] a rotina de auditoria (C6) na propria tela")
# 🚨 O interruptor mora na tela da rotina (convenção do FPSL, oposta à do
# MoviZap). A `FIN_1.1` ficou desligada de 02/10 a 08/10 e NADA na tela dizia.
checar("tem o interruptor da rotina", True, "chaveAuditoria" in html)
checar("diz que nasce desligada", True, "Nasce desligada" in html)
checar("e que aponta, nunca corrige", True, "aponta, nunca corrige" in html)
# ⚠️ Ligar NÃO roda na hora -- o laço relê a flag a cada volta.
checar("avisa que ligar nao roda na hora", True, "ligar não a faz rodar na hora" in html)
checar("oferece o 'Rodar agora'", True, "Rodar agora" in html)
checar("explica a recusa por cache velho", True, "dado velho acusaria problema que não existe" in html)
checar("diz que achado e retrato do momento", True, "retrato do momento" in html)
# A prova é o que o servidor RELEU, não o que mandamos gravar.
checar("rele o estado depois de mudar", True, "d.ativa ? 'true' : 'false'" in html)

print("\n[5] higiene")
checar("escapa tudo que vem do servidor", True, "function esc(" in html)
# ⚠️ Padrão visual dos quatro painéis: campo com menos de 16px faz o iOS dar
# zoom. O FPSL é só PC, mas o padrão é da casa e sai de graça.
checar("campos com 16px", True, "font-size:16px" in html)
checar("as 4 situacoes da placa tem rotulo em portugues", 4,
       sum(1 for s in ("'ATIVA'", "'EM_AVISO_PREVIO'", "'SUBSTITUIDA'", "'RESCINDIDA'") if s in html))
checar("o botao diz que esta trabalhando", True, "Lendo…" in html)

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
