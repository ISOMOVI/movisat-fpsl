"""Aba Operações — a Central 24h vai nas DUAS OS e nunca flega. 2026-08-26 (C3).

Decisão do usuário, 26/08, em três frases dele:

  - "a central tem que aparecer em ambas, se tiver como 'desativar' ou
    'desativar no sistema' ou 'contratado'";
  - "se estiver como 'não possui', 'não contratado' não deve aparecer em
    ambas";
  - "a central nunca vai ter flag de cobrar ou comodato em ambas OS, nunca".

O que este arquivo PRENDE:

  1. **A regra vale nos ONZE perfis**, não nos que eu lembrei. O teste percorre
     `cfg.PERFIS` inteiro: se um perfil novo nascer sem tratar a Central, ele
     reprova aqui. 🚨 Na auditoria de 26/08 a transferência novo titular
     escapou -- ela monta a OS a partir de `resolvidos`, sem passar por
     `separar_itens` -- e o placar teria ficado verde.

  2. **Zerada em TODA OS onde apareça.** Não é "zerada na operacional": é em
     qualquer uma. O termo 8848 traz R$ 10,00 na Central e nenhuma OS pode
     levar esse valor.

  3. **`NÃO POSSUI` some como `NÃO CONTRATADO`.** Até 26/08 o painel não
     conhecia a palavra: item `NÃO POSSUI` com valor ia COBRADO para a
     financeira.

  4. **Presença, não contagem.** "01 CENTRAL 24 HORAS" para 2 veículos entra
     nos dois -- alocar pela quantidade deixaria o segundo técnico sem o
     recado.

  5. **A exceção é do VÍNCULO, não do nome no código.** Quem decide é a coluna
     `nas_duas` de `painel_vinculos_itens`, que o usuário marca na tela.

Roda na VPS: venv/bin/python tests/teste_central_nas_duas.py

🚨 NÃO FAZ REDE E NÃO ESCREVE EM SISTEMA EXTERNO.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg  # noqa: E402
from fpsl_weso.painel import operacoes_os as oos  # noqa: E402
from fpsl_weso.painel.pdf_extractor import extrair_campos  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
CENTRAL = "CENTRAL 24 HORAS"

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# ── dublê ────────────────────────────────────────────────────────────────────
#
# ⚠️ IDS REAIS. `CENTRAL 24 HORAS` -> 6976 com `nas_duas` marcado é o vínculo
# que existe em produção (id 2), marcado pelo usuário em 14/08.

CATALOGO = {
    "CENTRAL 24 HORAS": {"harmonit_id": 6976, "oculto": False, "nas_duas": True},
    "RASTREADOR": {"harmonit_id": 20314, "oculto": False, "nas_duas": False},
    "CHIP DE DADOS": {"harmonit_id": 16016, "oculto": False, "nas_duas": False},
    "BLOQUEIO VEICULAR": {"harmonit_id": 45689, "oculto": False, "nas_duas": False},
    "LEITOR RFID": {"harmonit_id": 6984, "oculto": False, "nas_duas": False},
    "TAXA DE RETIRADA": {"harmonit_id": 7277, "oculto": False, "nas_duas": False},
    "90 DIAS DE AVISO PREVIO DE CANCELAMENTO": {
        "harmonit_id": 16033, "oculto": False, "nas_duas": False},
}


async def _vinculo(nome):
    return CATALOGO.get(oos._sem_acento(nome))


def instalar_dubles():
    storage.buscar_vinculo_item = _vinculo
    storage.produto_do_modelo = lambda modelo: None
    oos.storage.buscar_vinculo_item = _vinculo
    oos.storage.produto_do_modelo = lambda modelo: None
    oos.eqp.modelo_da_placa = lambda placa: None
    oos.eqp.serie_de = lambda seriais, placa: "007933911"


def item(desc, qtd="1", valor="0,00", tipo=None):
    return oos.ItemContrato(descricao=desc, quantidade=qtd,
                            valor_unitario=valor, comodato_ou_aquisicao=tipo)


def placa(txt, **extra):
    return oos.PlacaOS(placa=txt, veiculo="CAMINHAO", **extra)


async def montar(perfil_nome, placas, itens, **extra):
    p = cfg.PERFIS[perfil_nome]
    body = oos.MontarInput(perfil=perfil_nome, cliente_id=998063, termo="8848",
                           produto_servico_id=777, placas=placas, itens=itens,
                           **extra)
    resolvidos, pendentes, descartados, _oc = await oos.resolver_vinculos(body.itens)
    op_itens, fin_itens = oos.separar_itens(p, resolvidos)
    alocacao, _av = oos.alocar_itens_por_placa(op_itens, body.placas)
    ops = oos.montar(body, p, alocacao, fin_itens, resolvidos)
    return ops, resolvidos, descartados


def centrais_de(ops):
    return [(o.get("eh_financeira", False), m)
            for o in ops for m in o["materiais"] if m["descricao"] == CENTRAL]


# ── 1. a regra vale nos ONZE perfis ──────────────────────────────────────────

# ⚠️ A substituição exige placa de entrada, e o ressarcimento sem termo não lê
# item de contrato nenhum. O que muda é o CORPO da chamada, não a exigência.
EXTRA_POR_PERFIL = {
    "substituicao": dict(placas=[placa("AAA 0A00", placa_entrada="BBB 1B11")],
                         extra={"valor_substituicao": 299.9}),
}


async def teste_todos_os_perfis():
    print("\n1. A regra vale em todo perfil que monte a Central")
    instalar_dubles()
    itens = [item("RASTREADOR", "1", "999,90", "COMODATO"),
             item(CENTRAL, "1", "10,00", "DESATIVAR NO SISTEMA")]
    vistos = 0
    for nome in cfg.PERFIS:
        cfgp = EXTRA_POR_PERFIL.get(nome, {})
        placas = cfgp.get("placas") or [placa("AAA 0A00")]
        try:
            ops, _resolvidos, _d = await montar(
                nome, placas, itens, **(cfgp.get("extra") or {}))
        except Exception as exc:                      # perfil que exige mais
            checar(f"{nome}: montou", False, f"{type(exc).__name__}: {exc}")
            continue
        achadas = centrais_de(ops)
        if not achadas:
            continue
        vistos += 1
        checar(f"{nome}: Central sem cobrar e sem comodato, em toda OS",
               all(not m["cobrar"] and not m["comodato"] for _f, m in achadas),
               str(achadas))
        checar(f"{nome}: Central com valor zerado, em toda OS",
               all(float(m["valor_unitario"]) == 0.0 for _f, m in achadas),
               str(achadas))
    checar("a Central foi exercitada em mais de um perfil", vistos >= 6,
           f"perfis com Central: {vistos}")


# ── 2. nas duas OS, quando existem duas ──────────────────────────────────────

async def teste_nas_duas():
    print("\n2. Onde há operacional E financeira, a Central está nas duas")
    instalar_dubles()
    itens = [item("RASTREADOR", "2", "999,90", "COMODATO"),
             item(CENTRAL, "2", "10,00", "DESATIVAR NO SISTEMA")]
    for nome in ("contrato_novo", "aditivo", "rescisao", "upgrade"):
        ops, _r, _d = await montar(nome, [placa("AAA 0A00"), placa("BBB 1B11")],
                                   itens)
        lados = {fin for fin, _m in centrais_de(ops)}
        checar(f"{nome}: aparece na operacional e na financeira",
               lados == {True, False}, str(lados))
        por_placa = [o for o in ops if not o.get("eh_financeira")]
        checar(f"{nome}: uma linha em CADA OS operacional",
               all(sum(1 for m in o["materiais"] if m["descricao"] == CENTRAL) == 1
                   for o in por_placa),
               str([descr_de(o) for o in por_placa]))


def descr_de(op):
    return [m["descricao"] for m in op["materiais"]]


# ── 3. o caminho que escapou na auditoria ────────────────────────────────────

async def teste_titularidade():
    print("\n3. Transferência de titularidade — os dois lados")
    instalar_dubles()
    itens = [item("RASTREADOR", "2", "999,90", "COMODATO"),
             item(CENTRAL, "2", "10,00", "CONTRATADO")]
    placas = [placa("AAA 0A00"), placa("BBB 1B11")]

    # 🚨 O NOVO TITULAR NÃO PASSA POR `separar_itens`. Foi o caminho que
    # escapou na auditoria de 26/08.
    ops, _r, _d = await montar("transferencia_novo_titular", placas, itens)
    achadas = centrais_de(ops)
    lados = {fin for fin, _m in achadas}
    checar("novo titular: Central na operacional e na financeira",
           lados == {True, False}, str(lados))
    op = [o for o in ops if not o.get("eh_financeira")][0]
    linha = [m for m in op["materiais"] if m["descricao"] == CENTRAL][0]
    checar("novo titular: a OS é agregada, então a quantidade é o nº de placas",
           linha["quantidade"] == 2, str(linha))
    checar("novo titular: e nem assim flega ou leva valor",
           not linha["cobrar"] and not linha["comodato"]
           and float(linha["valor_unitario"]) == 0.0, str(linha))

    # O antigo titular gera UMA OS e não tem financeira: a Central herda a
    # regra da origem, sem tratamento próprio.
    ops2, _r2, _d2 = await montar("transferencia_antigo_titular", placas, itens)
    achadas2 = centrais_de(ops2)
    checar("antigo titular: a Central está na OS única", len(achadas2) == 1,
           str(achadas2))
    checar("antigo titular: zerada e sem flags",
           all(not m["cobrar"] and not m["comodato"]
               and float(m["valor_unitario"]) == 0.0 for _f, m in achadas2),
           str(achadas2))


# ── 4. não possui / não contratado ───────────────────────────────────────────

async def teste_nao_tem():
    print("\n4. 'NÃO POSSUI' e 'NÃO CONTRATADO' não entram em OS nenhuma")
    instalar_dubles()
    for tipo in ("NÃO POSSUI", "NAO POSSUI", "NÃO CONTRATADO",
                 "NÃO CONTRATADO*"):
        ops, resolvidos, descartados = await montar(
            "contrato_novo", [placa("AAA 0A00")],
            [item("RASTREADOR", "1", "999,90", "COMODATO"),
             item(CENTRAL, "1", "10,00", tipo)])
        checar(f"{tipo!r}: a Central não aparece em OS nenhuma",
               centrais_de(ops) == [], str(centrais_de(ops)))
        checar(f"{tipo!r}: e é declarada como descartada",
               descartados == [CENTRAL], str(descartados))

    # 🚨 O QUE NÃO PODE ACONTECER: 'NÃO POSSUI' COM VALOR virando cobrança.
    # Era o comportamento até 26/08, porque a palavra não existia no código.
    ops, _r, _d = await montar(
        "contrato_novo", [placa("AAA 0A00")],
        [item(CENTRAL, "1", "10,00", "NÃO POSSUI")])
    tudo = [m for o in ops for m in o["materiais"]]
    checar("nada de 'NÃO POSSUI' vira material cobrado",
           not any(m["cobrar"] for m in tudo), str(tudo))


# ── 5. presença, não contagem ────────────────────────────────────────────────

async def teste_presenca():
    print("\n5. Uma Central no termo, três placas: entra nas três")
    instalar_dubles()
    ops, _r, _d = await montar(
        "contrato_novo", [placa("AAA 0A00"), placa("BBB 1B11"), placa("CCC 2C22")],
        [item(CENTRAL, "1", "10,00", "DESATIVAR NO SISTEMA")])
    operacionais = [o for o in ops if not o.get("eh_financeira")]
    checar("são 3 OS operacionais", len(operacionais) == 3, str(len(operacionais)))
    checar("e a Central está em todas as três",
           all(any(m["descricao"] == CENTRAL for m in o["materiais"])
               for o in operacionais),
           str([descr_de(o) for o in operacionais]))


# ── 6. quem decide é o vínculo ───────────────────────────────────────────────

async def teste_comodato_protegido():
    print("\n6b. A regra NUNCA se aplica a comodato")
    instalar_dubles()
    # 🚨 Marcar `nas_duas` num item de COMODATO pela tela de Vínculos zeraria o
    # valor PATRIMONIAL e tiraria a flag: a DANFE de comodato sairia zerada e o
    # rastreador do contrato viraria linha informativa. Achado em 26/08 pelo
    # dublê do `teste_operacoes_f4`, que marcava o RASTREADOR assim.
    CATALOGO["RASTREADOR"] = {"harmonit_id": 20314, "oculto": False,
                              "nas_duas": True}
    try:
        ops, resolvidos, _d = await montar(
            "contrato_novo", [placa("AAA 0A00")],
            [oos.ItemContrato(descricao="RASTREADOR", quantidade="1",
                              valor_unitario="999,90",
                              comodato_ou_aquisicao="COMODATO")])
        r = resolvidos[0]
        checar("comodato marcado `nas_duas` continua comodato",
               r["comodato"] is True, str(r))
        checar("e o valor patrimonial não é zerado",
               float(r["valor_unitario"]) == 999.9, str(r))
        checar("e não vira linha informativa", not r.get("nas_duas"), str(r))
        na_fin = [m for o in ops if o.get("eh_financeira")
                  for m in o["materiais"] if m["descricao"] == "RASTREADOR"]
        checar("e continua fora da financeira", na_fin == [], str(na_fin))
    finally:
        CATALOGO["RASTREADOR"] = {"harmonit_id": 20314, "oculto": False,
                                  "nas_duas": False}


async def teste_quem_decide():
    print("\n6. A exceção é do vínculo, não do nome no código")
    instalar_dubles()
    CATALOGO["CENTRAL 24 HORAS"] = {"harmonit_id": 6976, "oculto": False,
                                    "nas_duas": False}
    try:
        ops, _r, _d = await montar(
            "contrato_novo", [placa("AAA 0A00")],
            [item(CENTRAL, "1", "10,00", "CONTRATADO")])
        lados = {fin for fin, _m in centrais_de(ops)}
        checar("desmarcado o `nas_duas`, a Central volta a ser item comum",
               lados == {True}, str(lados))
        cobradas = [m for _f, m in centrais_de(ops) if m["cobrar"]]
        checar("e volta a cobrar, porque a regra não é sobre o nome dela",
               len(cobradas) == 1, str(cobradas))
    finally:
        CATALOGO["CENTRAL 24 HORAS"] = {"harmonit_id": 6976, "oculto": False,
                                        "nas_duas": True}


# ── 7. o termo real ──────────────────────────────────────────────────────────

async def teste_termo_real():
    print("\n7. Os termos reais 8848 e 8842, ponta a ponta")
    instalar_dubles()
    for arquivo in ("rescisao_8848.pdf", "rescisao_8842.pdf"):
        campos = extrair_campos(str(FIXTURES / arquivo), "rescisao")
        itens = [oos.ItemContrato(
            descricao=i["descricao"], quantidade=i.get("quantidade"),
            valor_unitario=i.get("valor_unitario"),
            comodato_ou_aquisicao=i.get("comodato_ou_aquisicao"))
            for i in campos["itens"]]
        checar(f"{arquivo}: o termo diz DESATIVAR NO SISTEMA na Central",
               any(i.descricao == CENTRAL
                   and "DESATIVAR" in (i.comodato_ou_aquisicao or "").upper()
                   for i in itens),
               str([(i.descricao, i.comodato_ou_aquisicao) for i in itens]))
        ops, _r, _d = await montar("rescisao",
                                   [placa("QAA 1E73"), placa("OOJ 6E94")], itens)
        achadas = centrais_de(ops)
        lados = {fin for fin, _m in achadas}
        checar(f"{arquivo}: Central nas duas OS", lados == {True, False},
               str(lados))
        checar(f"{arquivo}: zerada e sem flags em todas",
               all(not m["cobrar"] and not m["comodato"]
                   and float(m["valor_unitario"]) == 0.0 for _f, m in achadas),
               str(achadas))
        # 🚨 O EFEITO COMPLETO NO 8848: a Central sai da cobrança e o aviso
        # prévio entra. Era o contrário em 25/08 -- Central R$ 20,00 cobrando e
        # aviso prévio nenhum.
        fin = [o for o in ops if o.get("eh_financeira")][0]
        cobrados = [m["descricao"] for m in fin["materiais"] if m["cobrar"]]
        checar(f"{arquivo}: o aviso prévio é o que cobra na financeira",
               any(oos.eh_aviso_previo(d) for d in cobrados), str(cobrados))
        checar(f"{arquivo}: e a Central não está entre os cobrados",
               CENTRAL not in cobrados, str(cobrados))


async def main():
    for t in (teste_todos_os_perfis, teste_nas_duas, teste_titularidade,
              teste_nao_tem, teste_presenca, teste_comodato_protegido,
              teste_quem_decide, teste_termo_real):
        await t()
    print(f"\n{'=' * 62}")
    print(f"{ok} verificações OK, {len(falhas)} falhas")
    if falhas:
        for f in falhas:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
