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
# 🆕 `CTR_1.2` (14/10): a tela virou GRID, e dois textos do assistente tiveram
# de mudar junto -- é o mesmo `M12` que matou a frase "Nada é gravado nesta
# etapa". O que a tela afirma agora:
checar("o grid declara de onde vem o numero", True, "eventos gravados" in html)
checar("e que aviso previo ainda conta", True, "ainda conta" in html)
# 🚨 ESTA FRASE JÁ ERA FALSA ANTES DE HOJE, e ninguém a matou: a tela dizia
# *"Comparar com a WESO ainda não acontece aqui"* no mesmo arquivo em que o
# card da auditoria C6 compara contrato × WESO desde 13/10. Entrega seguinte
# deixou o texto velho vivo -- exatamente o defeito que o `M12` nomeia. Saiu.
checar("nao nega a comparacao com a WESO, que a auditoria faz", False,
       "Comparar com a WESO ainda não acontece" in html)
checar("e diz que nao escreve nos outros sistemas", True,
       "não escreve no Harmonit, na WESO nem na Clicksign" in html)

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

print("\n[6] CTR_1.2 — a tela abre em GRID, e o input mora num modal")
# 🚨 MESMA ARMADILHA DO `prepararGravacao`: função definida e nunca chamada
# deixa o recurso invisível, e `py_compile` não lê JS. A tela nova dobrou de
# tamanho, então a contagem vale para cada função dela.
for fn in ("carregarGrid", "pintarGrid", "pintarChips", "pintarEstados", "filtrarEstado",
           "filtros", "abrirGaveta", "fecharTudo", "abrirModal", "fecharModal", "msgModal",
           "acao", "pedirSaida", "revisar", "corrigirNome", "exportar", "verDestino",
           "dobrarAuditoria", "abrirPdf", "achadosDoCliente"):
    checar(f"{fn} e definida E usada", True, html.count(fn) >= 2)
checar("a tela abre carregando a lista, nao um formulario", True,
       html.rstrip().endswith("</html>") and "carregarGrid();\n</script>" in html)
checar("o assistente de input esta dentro do modal", True,
       html.index('id="modal"') < html.index('id="perfil"'))
checar("e a gaveta da ficha existe", True, 'id="gaveta"' in html and 'id="ficha"' in html)
# 🚨 A AÇÃO VEM DO BACKEND COM O MOTIVO. Botão cinza e mudo manda o operador
# procurar; botão que existe e não faz nada é defeito.
checar("acao desabilitada mostra o motivo", True, 'title="${esc(a.motivo || a.label)}"' in html)
# ⚠️ As fases futuras não aparecem como botão -- nem desligado.
for proibido in ("Gerar termo", "Enviar para assinatura", "Cobrar etapa", "Enviar ao financeiro"):
    checar(f"nao tem botao de '{proibido}'", False, proibido in html)
# 🚨 O modo anexar precisa estar na tela: sem ele, subir o assinado de um termo
# da carga cria um SEGUNDO termo com os eventos repetidos.
checar("a tela oferece anexar ao termo que existe", True, "Anexar assinado" in html)
checar("e manda o termo_id na gravacao", True, "fd.append('termo_id'" in html)
checar("dizendo que gravar como novo duplicaria", True, "duplicaria o contrato" in html)
# ⚠️ A marca do Harmonit aparece COMO MARCA, nunca como assinatura.
checar("a marca do Harmonit nao se confunde com assinatura", True,
       "não é assinatura verificável" in html)
# 🚨 Termo da carga não tem PDF: a tela diz, em vez de oferecer link que daria 404.
checar("o PDF so aparece quando existe arquivo", True, "if (t.arquivo)" in html)
checar("e o erro do PDF chega ao operador", True, "Não foi possível abrir o PDF" in html)

print("\n[7] C7 - a fila da carga dos assinados aparece na tela")
# A fila invisivel e fila que ninguem resolve: os documentos que a carga nao
# conseguiu encaixar estavam so no livro-razao do banco.
checar("filaDoCliente e definida E usada", True, html.count("filaDoCliente") >= 2)
checar("tem coluna 'Na fila' no grid", True, ">Na fila<" in html)
checar("e o chip conta os clientes com documento parado", True, "com_documento_na_fila" in html)
checar("a tela diz que nada foi gravado por eles", True, "Nada foi gravado por eles" in html)
checar("e por que nao se forca", True, "contrato errado" in html)
checar("mostra o motivo de cada documento", True, "Por que parou" in html)

print("\n[8] D4 - a aderencia com a WESO aparece na tela")
# 🚨 A PERGUNTA DELE FOI "2778 placas ativas? baseado no que?". A coluna "Em uso"
# ao lado de "Ativas" existe para responder isso dentro da tela.
# ⚠️ A COLUNA SE CHAMA "Na WESO", NAO "Em uso": a checagem e de PRESENCA no
# cadastro, e a presenca e global -- placa cadastrada na WESO de outro cliente
# tambem conta. Medido na 2HM: 6 presentes contra 2 que a auditoria apurou como
# em uso. Chamar de "em uso" seria afirmar mais do que o dado diz.
checar("tem coluna 'Na WESO' no grid", True, ">Na WESO</th>" in html)
checar("e o cabecalho avisa que e presenca, nao instalacao", True,
       "presença, não instalação" in html)
checar("celulaEmUso e definida E usada", True, html.count("celulaEmUso") >= 2)
checar("filtrarAderencia e definida E usada", True, html.count("filtrarAderencia") >= 2)
checar("aderenciaDoCliente e definida E usada", True, html.count("aderenciaDoCliente") >= 2)
checar("a ficha mostra 'Na WESO' por placa", True, ">Na WESO<" in html)
# ⚠️ `null` nao e zero: sem cache, a tela nao pode afirmar "nada em uso".
checar("sem cache, a tela diz que nao da para comparar", True,
       "nao da para comparar" in html or "não dá para comparar" in html)
checar("e a idade do cache e dita em voz alta", True, "cache de" in html)
checar("cache velho avisa que a coluna pode estar desatualizada", True,
       "desatualizada" in html)
# A placa em uso sem assinatura e trabalho (cobrar assinatura), nao defeito.
checar("a ficha marca 'falta assinar'", True, "falta assinar" in html)

print("\n" + "=" * 52)
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
