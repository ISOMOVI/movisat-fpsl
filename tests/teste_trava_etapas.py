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
checar("a dica conta quantas falharam",
       "com falha" in (v("dica_com_falha") or ""), v("dica_com_falha"))
# 🚨 REPETIR A QUE FALHOU E A RAZAO DO RETOMAR EXISTIR. Uma guarda que escrevi
# em 21/08 contava como pendente so `!l.situacao` -- e placa que falhou TEM
# situacao, entao a tela se recusava a tentar de novo. O proprio servidor diz
# isso no `ja_resolvidas`: "falhou nao entra, a graca e tentar de novo".
checar("a placa que falhou PODE ser tentada outra vez",
       v("retentou_a_que_falhou") is True)
checar("e na segunda tentativa ela grava",
       v("gravadas_apos_retentar") == 2, v("gravadas_apos_retentar"))
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
print("== 🚨 os TRÊS PERFIS SEM TERMO, que morriam na etapa 3 ==")
# Manutenção no local, manutenção com troca e ressarcimento sem termo -- 3 dos
# 11 perfis. A etapa 1 prometia na tela que "a entrada digitada entra na F3", e
# a F3 montava `linhasPlacas` SÓ a partir de `extraido.itens`: sem PDF a lista
# nascia vazia, a tabela renderizava sem corpo e não havia botão de adicionar
# linha em lugar nenhum. Promessa escrita na interface que o código não cumpria.
checar("a etapa 2 abre mesmo sem termo", v("st_etapa2") == 2)
checar("e diz para escolher o cliente, em vez de ficar em branco",
       v("st_recado_pede_cliente") is True)
checar("sem cliente escolhido, não avança",
       v("st_avancar_travado_sem_cliente") is True)
checar("escolher pelo modal resolve o cliente",
       v("st_cliente_resolvido") is True)
checar("e o campo mostra quem é, com o id",
       "998063" in (v("st_campo_cliente") or ""), v("st_campo_cliente"))
checar("a etapa 3 abre", v("st_etapa3") == 3)
checar("o bloco de adicionar placa aparece",
       v("st_bloco_adicionar") == "block")
checar("a lista traz os veículos do cliente, da base local",
       v("st_placas_do_cliente") == 2)
checar("a etapa 3 começa vazia e travada",
       v("st_linhas_antes") == 0 and v("st_avancar_travado_sem_placa") is True)

print()
print("== adicionar placa, e o recipiente que vem junto ==")
# 🚨 O recipiente `-MANUT` acompanha a placa, igual ao caminho do termo. Ele
# nasce NA TELA desde 19/08 -- é o que tirou a leitura ao vivo da WESO do
# caminho crítico da manutenção.
checar("adicionar 1 placa gera 2 linhas (placa + bancada)",
       v("st_linhas_apos_1") == 2)
checar("a linha de bancada existe", v("st_tem_recipiente") is True)
checar("e leva o sufixo do perfil",
       v("st_sufixo_recipiente") == "TST0E55-MANUT", v("st_sufixo_recipiente"))
checar("a mesma placa de novo NÃO duplica",
       v("st_linhas_apos_repetida") == 2)
# "mesmo adicionando mais de uma" -- pedido do usuário, 21/08.
checar("dá para adicionar mais de uma", v("st_linhas_apos_2") == 4)
checar("remover a placa leva o recipiente dela junto",
       v("st_linhas_apos_remover") == 2,
       "o recipiente não existe sozinho")
checar("gravadas, a etapa 4 abre", v("st_etapa_final") == 4)
checar("e o lote foi aberto mesmo sem termo", v("st_lote_aberto") is True)

print()
print("== o serviço se ESCOLHE, e o id aparece ==")
# 🚨 Dois serviços do Harmonit têm o nome IDÊNTICO (6967 e 54845). Sem o número
# na tela o operador não tem como saber qual pegou -- e era esse o defeito do
# `<select>` repovoado a cada tecla, em que ninguém selecionava nada.
checar("o campo mostra nome e id",
       "(#6967)" in (v("sv_campo") or ""), v("sv_campo"))
checar("e o que vai para a OS é o selecionado", v("sv_selecionado") == 6967)

print()
print("== 🚨 VOLTAR UMA ETAPA NAO APAGA O QUE JA FOI GRAVADO ==")
# Medido em 21/08: gravava 2 placas nos dois sistemas, voltava para a etapa 2,
# retornava para a 3 -- `situacao` zerada, 0 gravadas, botao travado e a dica
# mandando gravar de novo. O `prepararPlacas` fazia `linhasPlacas = []` e
# reconstruia TODA vez que a etapa abria. O operador clicaria em Cadastrar e
# tentaria RECRIAR placa que existe: 409 no Harmonit, duplicata na WESO se a
# escrita der timeout. E o botao Voltar esta ali, convidando.
checar("grava 2 placas", v("vt_gravadas") == 2)
checar("volta para a etapa 2 e retorna: as 2 continuam gravadas",
       v("vt_gravadas_depois") == 2,
       f"sobraram {v('vt_gravadas_depois')} -- o trabalho foi perdido")
checar("e o Avancar continua liberado",
       v("vt_avancar_liberado_depois") is True, v("vt_dica_depois"))

print()
print("== 🚨 SUBSTITUICAO: a placa de ENTRADA chega ao payload ==")
# 1 dos 11 perfis estava morto. A tela casava a linha de entrada com a de saida
# pelo TEXTO do veiculo, e na substituicao os dois sao diferentes por
# definicao -- o equipamento muda de carro. Medido no fixture: "FIAT FIORINO
# 2020/2021" sai, "FIAT/FIORINO ENDURANCE" entra. O `find` nunca achava, a tela
# mandava `placa_entrada: null` e o servidor barrava com "a Substituicao exige
# a placa de entrada" -- uma placa VISIVEL na tela.
checar("a tela monta as duas linhas", v("sub_linhas") == 2)
checar("e a de entrada existe", v("sub_tem_entrada_na_tela") is True)
checar("a placa que SAI vai no payload",
       v("sub_placa_saida") == "BZR 5B97", v("sub_placa_saida"))
checar("a placa que ENTRA vai junto",
       v("sub_placa_entrada") == "UPW 3G17",
       f"veio {v('sub_placa_entrada')!r} -- era o defeito de 21/08")
checar("com o veiculo de destino",
       v("sub_veiculo_entrada") == "FIAT/FIORINO ENDURANCE",
       v("sub_veiculo_entrada"))

print()
print("== 🚨 AS DUAS ESCRITAS PERGUNTAM ANTES ==")
# A aba tinha perdido uma trava que o `gerar_os.html` tem desde sempre. Decisao
# dele em 21/08: as duas confirmam.
checar("criar placa pergunta antes", v("confirmou_placas") is True,
       str(v("confirms"))[:200])
checar("gerar OS pergunta antes", v("confirmou_os") is True)

print()
print("== 🚨 A CAIXA DA MANUTENCAO NAO PROMETE ESCRITA NO HARMONIT ==")
# Achado dele em 24/08, usando a tela: "ao cadastrar placa de manutenção
# (recipiente) a caixa de diálogo ainda induz ao erro, por informar Harmonit".
# Na manutenção com troca NADA nasce no Harmonit -- a placa real saiu da BASE
# do Harmonit (o `<select>` da etapa 3 é ela, e por isso a linha vem com
# `daBase`) e o recipiente é bancada, que só existe na WESO.
#
# ⚠️ A TRAVA MEDE O QUE A FRASE PROMETE, NAO A PALAVRA "Harmonit". Dizer "o
# Harmonit não recebe nada" é a CORREÇÃO do engano, não o engano: travar na
# palavra reprovaria justamente o texto certo. É o M7, que já voltou cinco
# vezes desde 19/08.
conf_manut = v("st_confirm_manut") or ""
checar("a caixa da manutenção aparece", bool(conf_manut))
checar("ela NÃO promete criação no Harmonit",
       "cria no Harmonit" not in conf_manut, conf_manut)
checar("e NÃO traz o alerta de exclusão do Harmonit",
       "exclusão de veículo" not in conf_manut, conf_manut)
checar("a placa vinda da base é CONFERIDA, não criada",
       "confere lá" in conf_manut, conf_manut)
checar("e o recipiente diz para onde vai e para onde não vai",
       "SÓ na WESO" in conf_manut and "não recebe nada" in conf_manut,
       conf_manut)
# 🚨 O CONTRAPESO. Sem isto a trava acima seria satisfeita apagando o alerta de
# todo lugar -- e o alerta EXISTE por um motivo: o Harmonit não tem DELETE de
# veículo, e placa criada lá por engano fica. No perfil que cria, ele continua.
checar("mas no perfil que CRIA, o alerta continua de pé",
       any("exclusão de veículo" in c for c in (v("confirms") or [])),
       str(v("confirms"))[:300])
checar("e a pergunta da OS traz o NUMERO",
       any("Gerar 3 OS" in m for m in (v("confirms") or [])),
       "o numero e a ultima chance de ver que sao 3 e deveriam ser 2")
checar("a previa libera o Gerar", v("previa_liberou_gerar") is True)
checar("e a geracao chega ao servidor", v("gerou") is True)

# 🚨 O NUMERO VAI NO BOTAO. Ele dizia "Gerar as OS" e o `osInfo` narrava, em
# duas frases, o que o botao diz em duas palavras. E o numero e a ultima chance
# de o operador ver que sao 3 e deveriam ser 2, com a mao ja indo clicar.
checar("o botao diz QUANTAS OS vai gerar",
       v("rotulo_gerar") == "Gerar 3 OS", v("rotulo_gerar"))
checar("e o texto que narrava saiu",
       (v("osinfo_apos_previa") or "") == "", v("osinfo_apos_previa"))

print()
print("== 🚨 RETOMAR: o que ja foi gravado nao se refaz ==")
# O `lote` foi criado exatamente para isto, e esta escrito no proprio codigo:
# "um termo de 11 placas leva mais de um minuto so nesta etapa, e a WESO oscila
# entre 6s e timeout. Se cair no meio, o operador NAO PODE recomecar do PDF --
# metade ja nasceu, e recriar devolve 409 ou duplica."
#
# O servidor tinha `GET /lote/{id}` com `passos`, `resumo` e `ja_resolvidas`.
# A tela nao chamava NENHUM, e o `lote` vivia so numa variavel JS: um F5 no
# meio de 11 placas perdia a chave.
checar("rodada terminada NAO se oferece para retomar",
       v("rt_chave_apos_gerar") is None,
       "as OS sairam, entao a chave sai junto")
checar("com lote pendente, a barra pergunta",
       v("rt_barra_visivel") is True)
checar("e diz de qual termo e quantas ja foram",
       "8840" in (v("rt_barra_texto") or "")
       and "1</strong> placa" in (v("rt_barra_texto") or ""),
       v("rt_barra_texto"))
checar("Continuar restaura o tipo de operação",
       v("rt_perfil_restaurado") == "aditivo", v("rt_perfil_restaurado"))
checar("subir o MESMO termo reusa o lote, nao abre outro",
       v("rt_lote_reusado") is True)
checar("e o carimbo se renova — rodada retomada continua AGORA",
       v("rt_chave_renovada") is True,
       "sem isto uma rodada longa expiraria no meio dela")
checar("a placa ja resolvida entra marcada, e nao sera reescrita",
       v("rt_ja_resolvidas") == 1, v("rt_ja_resolvidas"))
checar("Descartar limpa a chave", v("rt_descartou") is True)

print()
print("== 🚨 TODO ERRO LEVA A REFERENCIA DA REQUISICAO ==")
# Em 21/08 ele viu um erro ao ler um termo e nao conseguiu me dizer qual: a
# mensagem passou e a rodada seguiu. Pedir "me diga a mensagem exata" poe o
# diagnostico na mao de quem esta tentando trabalhar. O `req_id` ja existia no
# middleware e ia no cabecalho -- faltava a tela le-lo QUANDO DA ERRO.
checar("a mensagem de erro traz a referência",
       "(ref a3f1)" in (v("erro_com_ref") or ""), v("erro_com_ref"))
checar("e o texto do erro continua lá",
       "PDF" in (v("erro_com_ref") or ""), v("erro_com_ref"))

print()
print("== 🚨 AS SECOES CARREGAM O VALOR, e nada some da vista ==")
# 🚨 A CAUSA DE EU TER ESCRITO 19 TEXTOS. No wizard cada etapa ocupava a tela e
# as outras sumiam: na etapa 4 nao se via mais termo, cliente nem quantas
# placas -- as tres coisas que decidem se a OS esta certa. A prosa compensava o
# contexto que a propria tela tirava. Agora cada etapa resolvida colapsa numa
# LINHA com o valor.
checar("a seção 1 mostra o tipo e o termo",
       "Aditivo" in (v("sec_valor_1") or "") and "8840" in (v("sec_valor_1") or ""),
       v("sec_valor_1"))
checar("a seção 2 mostra o cliente e os DOIS ids",
       "Harmonit #998063" in (v("sec_valor_2") or "")
       and "WESO #13624" in (v("sec_valor_2") or ""), v("sec_valor_2"))
checar("a seção 3 mostra quantas placas fecharam",
       v("sec_valor_3") == "2 de 2", v("sec_valor_3"))
# 🚨 O CIRCULO MOSTRA O NUMERO DA ETAPA (24/08, pedido dele: "deixe as etapas
# mais destacadas"). Antes eram quatro glifos -- ●, ✓, ○, · -- que dizem
# ESTADO e nao dizem QUAL etapa e. Agora o numero fica a vista o tempo todo e
# so a etapa concluida o troca pelo ✓; o resto do estado e cor, no CSS.
checar("etapa concluída troca o número pelo ✓",
       v("sec_marca_1") == "✓" and v("sec_pronta_1") is True)
checar("a etapa aberta mostra o próprio número",
       v("sec_marca_4") == "4" and v("sec_aberta_4") is True,
       v("sec_marca_4"))

print()
print("== 🚨 E A TRAVA VALE NO CLIQUE DO CABECALHO ==")
# O cabecalho chama o MESMO `irPara`. Se houvesse um segundo caminho de
# navegacao, seria um caminho que alguem esqueceria de proteger -- que e
# exatamente como a trava ficou solta da F1 ate 21/08.
checar("clicar na seção 4 sem nada feito não sai da 1",
       v("sec_clique_travado") == 1,
       f"foi para a {v('sec_clique_travado')}")
checar("e a seção inalcançável aparece trancada",
       v("sec_trancada_3") is True)

print()
print("== 🚨 A PREVIA DOMINA, e o aviso vai na OS a que pertence ==")
# A previa e a razao da aba existir -- a ultima coisa antes de escrever em
# producao -- e era uma `div` solta no fim de um formulario, com o mesmo peso
# do campo de observacao.
checar("a prévia tem moldura própria", v("prev_tem_moldura") is True)
checar("com o número de OS no título", v("prev_titulo") is True)
# ⚠️ LIMITE HONESTO: os avisos sao texto, sem vinculo com a OS. O casamento e
# pela PLACA citada, e SO quando ela aparece em exatamente uma operacao --
# inventar vinculo poria o aviso na OS errada, que e pior que po-lo em cima.
checar("aviso que cita UMA placa vai na OS dela",
       v("prev_aviso_na_os") is True)
checar("e o que não cita placa fica no bloco geral, acima",
       v("prev_aviso_generico_em_cima") is True)

print()
print("== 🚨 LINHA GRAVADA NAO E MAIS EDITAVEL ==")
# Depois de escrever nos dois sistemas os campos continuavam editaveis -- a
# tela sugeria que dava para corrigir o que ja tinha sido gravado. Campo
# editavel depois da escrita e mentira. Linha que FALHOU continua editavel,
# porque ela vai ser tentada de novo.
checar("os campos somem depois de gravar",
       v("linha_gravada_sem_input") is True)

print()
print("== 🚨 OS MODAIS FUNCIONAM PELO TECLADO ==")
# Tres coisas, e as tres sao do mesmo problema: o modal abria e a mao tinha de
# voltar para o mouse.
#
# ⚠️ O `gerar_os.html` tambem nao tem nenhuma das tres -- e lacuna
# compartilhada, nao regressao da aba. Quem tem e a tela nova.
checar("há UM ouvinte de tecla, no documento",
       v("mod_esc_ligado") == 1,
       "um por modal divergiria no primeiro modal novo que alguém acrescentasse")
checar("o modal abre", v("mod_abriu") is True)
checar("e o campo de busca recebe o foco",
       v("mod_focou_campo") is True,
       "abrir e não poder digitar é um clique desperdiçado, toda vez")
checar("Esc fecha o modal", v("mod_fechou_com_esc") is True)
checar("e o foco volta para quem abriu",
       v("mod_foco_voltou") is True,
       "modal que fecha e larga o foco no nada obriga a achar o lugar com o mouse")
checar("tecla que NÃO é Esc não fecha nada",
       v("mod_outra_tecla_nao_fecha") is True)
checar("e vale para o modal de serviço também",
       v("mod_servico_fechou") is True)

print()
print("== 🚨 A RODADA TEM FIM: Concluir, resumo, e volta ao inicio ==")
# Pedido dele em 24/08: "depois de OS gerada com êxito, botão direito chamado
# 'Concluir' que exibe um resumo rápido em modal só para 'ok' e depois retorna
# para o início". Até aqui a tela não tinha fim: as OS saíam, o resultado
# ficava na etapa 4 e a única forma de começar outra rodada era recarregar a
# página -- ou trocar o tipo de operação, que zera por EFEITO COLATERAL.
checar("antes de gerar não há o que concluir",
       v("fim_botao_antes") is True,
       "o botão nasce escondido: rodada sem OS não tem resumo")
checar("geradas as OS, o Concluir aparece", v("fim_botao_apareceu") is True)
checar("ele abre o resumo em modal", v("fim_modal_abriu") is True)
checar("com a contagem de OS criadas",
       "OS criadas" in (v("fim_resumo") or ""), (v("fim_resumo") or "")[:200])
# 🚨 O NUMERO DA OS E O QUE O OPERADOR ANOTA. O duble mandava so `os_id` e a
# tela le `numero_ordem` -- os dois campos existem no router, e o exercicio
# aprovava numero vazio.
checar("e com o NÚMERO da OS, que é o que se anota",
       "16901" in (v("fim_resumo") or ""), (v("fim_resumo") or "")[:200])
checar("o foco vai para o OK, único caminho daqui",
       v("fim_focou_ok") is True)
checar("OK fecha o modal", v("fim_modal_fechou") is True)
checar("e devolve a tela para a etapa 1",
       v("fim_etapa") == 1, f"parou na {v('fim_etapa')}")
checar("o lote foi esquecido", v("fim_lote") is None)
checar("as linhas de placa saíram", v("fim_linhas") == 0)
# ⚠️ A TABELA FICAVA NA TELA depois de zerar: `linhasPlacas` esvaziava e o HTML
# dela continuava lá até alguém reabrir a etapa 3. Trocar de perfil deixava as
# placas do perfil anterior à vista.
checar("e a tabela de placas foi apagada da TELA, não só do estado",
       v("fim_tabela_limpa") is True)
checar("a prévia também saiu", v("fim_previa_limpa") is True)
checar("o botão some junto", v("fim_botao_sumiu") is True)
checar("a etapa 1 volta a mostrar o número 1",
       v("fim_marca_1") == "1", v("fim_marca_1"))
checar("e o contador acompanha",
       v("fim_contador") == "Etapa 1 de 4", v("fim_contador"))

print()
print(f"== {ok} verificações OK, {len(falhas)} falha(s) ==")
if falhas:
    for f in falhas:
        print(f"   - {f}")
    sys.exit(1)
