"""Motor das Contas a Receber (`CAR_1.1`) — etapa E3.

Fixtures à mão, nenhum banco: é o que o motor ser puro compra.

🚨 OS CASOS QUE ESTE TESTE EXISTE PARA FECHAR:
1. **`PRECO` fora de vigência não vale.** Lançar o reajuste de novembro não
   pode mudar a cobrança de outubro -- se mudar, reabrir um mês fechado passa a
   dar outro número, e aí nenhuma conferência contra o Harmonit fecha nunca.
2. **Dois `PRECO` no mesmo mês**: o último lançado ganha, e isso tem de ser
   determinístico, não "o que o SELECT devolver primeiro".
3. **`ANULA` devolve o estado anterior**, e `ANULA` de `ANULA` ressuscita o
   evento -- com anulação mútua o motor **termina**, em vez de girar.
4. **`CANCELA` no meio do mês** vale do mês inteiro, e se ainda há placa ativa
   na CTR isso é DIVERGÊNCIA, não silêncio: é serviço rodando sem cobrança.
5. **Termo não assinado é INATIVO para cobrança** e, ao mesmo tempo, a placa
   segue sustentada na CTR. As duas coisas são verdade juntas, e a falta de
   assinatura é achado.
6. **Valor nulo nunca é zero.** `R$ 0,00` afirmaria que a placa não cobra nada.
7. **O motor não faz I/O** -- travado no fonte, para o `import sqlite3` não
   entrar aqui amanhã por descuido.

Roda na VPS:  venv/bin/python tests/teste_car_motor.py
"""
import pathlib
import sys
from datetime import date

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from fpsl_weso.painel import car_motor as m                      # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


def ev(id, acao, competencia, valor=None, placa=None, fonte="operador",
       corrige=None, motivo=None):
    return {"id": id, "acao": acao, "competencia": competencia,
            "valor_mensal": valor, "placa_chave": placa, "fonte": fonte,
            "corrige_evento_id": corrige, "motivo": motivo, "por": "admin"}


def main():
    print("teste_car_motor — fixtures à mão, nenhum banco")

    print("\n[1] competência: ida, volta e recusa")
    checar("competencia_de", "2026-10", m.competencia_de(date(2026, 10, 28)))
    checar("mês de um dígito vem com zero", "2026-01",
           m.competencia_de(date(2026, 1, 5)))
    checar("fim de outubro", date(2026, 10, 31), m.fim_da_competencia("2026-10"))
    checar("fim de fevereiro de ano bissexto", date(2024, 2, 29),
           m.fim_da_competencia("2024-02"))
    checar("fim de fevereiro de ano comum", date(2026, 2, 28),
           m.fim_da_competencia("2026-02"))
    checar("início da competência", date(2026, 10, 1),
           m.inicio_da_competencia("2026-10"))
    for ruim in ("2026-13", "2026-00", "out/2026", "2026-1", "", None, 202610):
        try:
            m.validar_competencia(ruim)
            checar(f"recusa {ruim!r}", True, False)
        except m.CompetenciaInvalida:
            checar(f"recusa {ruim!r}", True, True)
    checar("as 5 ações, e só elas", 5, len(m.ACOES))
    checar("EM_AVISO_PREVIO é cobrável (decisão dele, 28/10)", True,
           "EM_AVISO_PREVIO" in m.SITUACOES_COBRAVEIS)
    checar("RESCINDIDA não é cobrável", False,
           "RESCINDIDA" in m.SITUACOES_COBRAVEIS)

    print("\n[2] 🚨 PRECO fora de vigência NÃO muda o mês já passado")
    eventos = [ev(1, m.PRECO, "2026-10", "R$ 75,26"),
               ev(2, m.PRECO, "2026-11", "R$ 90,00")]
    checar("outubro cobra 75,26", "R$ 75,26",
           m.preco_vigente(eventos, "2026-10")["valor_mensal"])
    checar("novembro cobra 90,00", "R$ 90,00",
           m.preco_vigente(eventos, "2026-11")["valor_mensal"])
    checar("dezembro segue em 90,00", "R$ 90,00",
           m.preco_vigente(eventos, "2026-12")["valor_mensal"])
    checar("setembro não tem preço nenhum", None,
           m.preco_vigente(eventos, "2026-09"))

    print("\n[3] dois PRECO no MESMO mês: o último lançado ganha")
    eventos = [ev(1, m.PRECO, "2026-10", "R$ 75,26"),
               ev(2, m.PRECO, "2026-10", "R$ 80,00")]
    checar("vence o de id maior", "R$ 80,00",
           m.preco_vigente(eventos, "2026-10")["valor_mensal"])
    # E a ordem da lista não pode mudar o resultado.
    checar("e a ordem da lista não importa", "R$ 80,00",
           m.preco_vigente(list(reversed(eventos)), "2026-10")["valor_mensal"])

    print("\n[4] preço da PLACA × preço do CONTRATO")
    eventos = [ev(1, m.PRECO, "2026-10", "R$ 75,26"),
               ev(2, m.PRECO, "2026-10", "R$ 60,00", placa="ABC1D23")]
    checar("a placa com acordo paga o dela", "R$ 60,00",
           m.preco_vigente(eventos, "2026-10", "ABC1D23")["valor_mensal"])
    checar("as outras pagam o do contrato", "R$ 75,26",
           m.preco_vigente(eventos, "2026-10", "XYZ9W88")["valor_mensal"])
    # 🚨 O fato mais recente manda: reajuste geral alcança a placa com acordo.
    eventos.append(ev(3, m.PRECO, "2026-11", "R$ 99,00"))
    checar("reajuste geral de novembro alcança a placa com acordo", "R$ 99,00",
           m.preco_vigente(eventos, "2026-11", "ABC1D23")["valor_mensal"])

    print("\n[5] 🚨 ANULA desfaz, e ANULA de ANULA ressuscita")
    base = [ev(1, m.PRECO, "2026-10", "R$ 75,26"),
            ev(2, m.PRECO, "2026-10", "R$ 999,90")]      # lançado errado
    checar("sem anulação, vale o errado", "R$ 999,90",
           m.preco_vigente(base, "2026-10")["valor_mensal"])
    com_anula = base + [ev(3, m.ANULA, "2026-10", corrige=2)]
    checar("anulado o errado, volta o certo", "R$ 75,26",
           m.preco_vigente(com_anula, "2026-10")["valor_mensal"])
    checar("o anulado aparece em anulados()", {2}, m.anulados(com_anula))
    # 3 eventos: o PRECO certo, o PRECO errado e a ANULA. Vivo fica UM -- a
    # ANULA não é fato de cobrança, e o anulado saiu.
    checar("sobra um evento vivo: nem o anulado, nem a própria ANULA", 1,
           len(m.vivos(com_anula)))
    checar("e o vivo é o PRECO certo", 1, m.vivos(com_anula)[0]["id"])
    arrependido = com_anula + [ev(4, m.ANULA, "2026-10", corrige=3)]
    checar("anulada a anulação, o errado volta a valer", "R$ 999,90",
           m.preco_vigente(arrependido, "2026-10")["valor_mensal"])
    checar("e anulados() aponta a anulação, não o evento", {3},
           m.anulados(arrependido))
    # ⚠️ Anulação MÚTUA: o que importa aqui é TERMINAR.
    mutuo = [ev(1, m.PRECO, "2026-10", "R$ 10,00"),
             ev(2, m.ANULA, "2026-10", corrige=3),
             ev(3, m.ANULA, "2026-10", corrige=2)]
    checar("anulação mútua termina, e ganha a mais recente", {2},
           m.anulados(mutuo))

    print("\n[6] 🚨 EXCECAO vale SÓ no mês em que foi lançada")
    eventos = [ev(1, m.PRECO, "2026-01", "R$ 75,26"),
               ev(2, m.EXCECAO, "2026-10", None, motivo="negociado: rescisão em curso")]
    out = m.valor_da_placa(eventos, "2026-10", "ABC1D23")
    checar("em outubro a exceção manda", "excecao", out["fonte"])
    checar("e o valor é o negociado (nenhum)", None, out["valor"])
    checar("com o motivo na mão", "negociado: rescisão em curso", out["motivo"])
    nov = m.valor_da_placa(eventos, "2026-11", "ABC1D23")
    checar("em novembro o preço volta sozinho", "R$ 75,26", nov["valor"])
    checar("e a fonte diz que veio de preço", "preco_operador", nov["fonte"])

    print("\n[7] 🚨 valor nulo NUNCA é zero, e sempre tem motivo")
    vazio = m.valor_da_placa([], "2026-10", "ABC1D23")
    checar("sem evento e sem item, o valor é nulo", None, vazio["valor"])
    checar("e não é '0,00'", False, vazio["valor"] == "R$ 0,00")
    checar("e o motivo está escrito", True, bool(vazio["motivo"]))
    checar("sem evento, o valor do termo (contrato_item) vale", "R$ 75,26",
           m.valor_da_placa([], "2026-10", "ABC1D23",
                            valor_do_item="R$ 75,26")["valor"])
    checar("e a fonte nomeia o contrato_item", "contrato_item",
           m.valor_da_placa([], "2026-10", "ABC1D23",
                            valor_do_item="R$ 75,26")["fonte"])
    checar("mas o PRECO lançado vence o valor do termo", "R$ 90,00",
           m.valor_da_placa([ev(1, m.PRECO, "2026-10", "R$ 90,00")], "2026-10",
                            "ABC1D23", valor_do_item="R$ 75,26")["valor"])

    print("\n[8] situação do contrato: a régua, na ordem")
    assinado = {"assinado": 1}
    nao_assinado = {"assinado": 0}
    ativa = [{"situacao": "ATIVA"}]
    aviso = [{"situacao": "EM_AVISO_PREVIO"}]
    rescindida = [{"situacao": "RESCINDIDA"}]

    r = m.situacao_do_contrato(assinado, ativa, [], "2026-10")
    checar("assinado com placa ativa -> ATIVO", m.ATIVO, r["situacao"])
    checar("e o motivo conta as placas", "1 placa(s) sustentadas pelo contrato",
           r["motivo"])
    checar("sem divergência", None, r["divergencia"])

    r = m.situacao_do_contrato(assinado, aviso, [], "2026-10")
    checar("aviso prévio sustenta cobrança (decisão dele)", m.ATIVO, r["situacao"])

    r = m.situacao_do_contrato(assinado, rescindida, [], "2026-10")
    checar("só rescindida -> INATIVO", m.INATIVO, r["situacao"])
    checar("com o motivo certo", "sem placa ativa", r["motivo"])

    r = m.situacao_do_contrato(nao_assinado, ativa, [], "2026-10")
    checar("🚨 termo não assinado -> INATIVO, mesmo com placa ativa",
           m.INATIVO, r["situacao"])
    checar("e o motivo é a assinatura", "termo não assinado", r["motivo"])
    checar("e a placa ativa sem assinatura é DIVERGÊNCIA, não silêncio", True,
           "sem assinatura" in (r["divergencia"] or ""))

    cancelado = [ev(1, m.CANCELA, "2026-09", motivo="pedido do cliente")]
    r = m.situacao_do_contrato(assinado, ativa, cancelado, "2026-10")
    checar("cancelado em setembro ainda está cancelado em outubro",
           m.INATIVO, r["situacao"])
    checar("e o motivo traz o mês e a razão", True,
           "2026-09" in r["motivo"] and "pedido do cliente" in r["motivo"])
    checar("🚨 cancelado com placa ativa na CTR é DIVERGÊNCIA", True,
           "seguem sustentadas" in (r["divergencia"] or ""))
    r = m.situacao_do_contrato(assinado, ativa, cancelado, "2026-08")
    checar("e em agosto, antes do cancelamento, estava ATIVO", m.ATIVO,
           r["situacao"])

    anulado = cancelado + [ev(2, m.ANULA, "2026-09", corrige=1)]
    r = m.situacao_do_contrato(assinado, ativa, anulado, "2026-10")
    checar("cancelamento anulado volta a ATIVO", m.ATIVO, r["situacao"])

    print("\n[9] renovação vigente")
    renov = [ev(1, m.RENOVA, "2026-06"), ev(2, m.RENOVA, "2026-12")]
    checar("em outubro vale a de junho", 1,
           m.renovacao_vigente(renov, "2026-10")["id"])
    checar("em dezembro vale a de dezembro", 2,
           m.renovacao_vigente(renov, "2026-12")["id"])

    print("\n[10] 🚨 o motor não faz I/O — medido na ÁRVORE, não no texto")
    # ⚠️ A primeira versão disto procurava a string "import sqlite3" no arquivo
    # -- e o próprio motor escreve essa frase, explicando que NÃO o importa. A
    # prosa casou com a busca e o teste acusou o que ele existe para proteger.
    # Foi o segundo falso vermelho do dia pela mesma causa (o outro foi o
    # "CHECK" no `teste_car_tabelas`). Lição: contrato sobre código se mede no
    # código, e o `ast` é o que distingue código de comentário.
    import ast
    arvore = ast.parse((RAIZ / "fpsl_weso" / "painel" / "car_motor.py")
                       .read_text(encoding="utf-8"))
    modulos = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom):
            modulos.add((no.module or "").split(".")[0])
    checar("importa só calendar, re e datetime", {"calendar", "re", "datetime"},
           modulos)
    nomes = {no.func.id for no in ast.walk(arvore)
             if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)}
    atributos = {no.func.attr for no in ast.walk(arvore)
                 if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)}
    checar("não chama open()", False, "open" in nomes)
    checar("não chama execute()", False, "execute" in atributos)
    checar("não chama connect()", False, "connect" in atributos)
    checar("nenhuma função async (I/O entraria por aí)", 0,
           len([n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef)]))

    print("\n" + "=" * 52)
    print(f"{ok} verificações OK, {len(falhas)} falha(s)")
    for f in falhas:
        print(f"  FALHOU: {f}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
