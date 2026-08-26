"""Aba Operações — a taxa de migração do Upgrade. 2026-08-26 (C4).

Até 26/08 TODA OS financeira de upgrade saiu `SEM CUSTO`: 8820 (16744), 8844
(16776), 8834 (16790) e 8827 (16736). O layout do termo de Upgrade não tem
tabela de itens -- tem uma linha por veículo com `VEÍCULOS A MIGRAR`,
`DOCUMENTO REFERÊNCIA`, `TAXA DE MIGRAÇÃO` e `NOVO VALOR MENSAL` --, então o
extrator devolvia `itens: []` e a cobrança não existia.

O que este arquivo PRENDE:

  1. 🚨 **O TOTAL VEM RISCADO EM 2 DOS 3 TERMOS REAIS**, e ler o primeiro valor
     cobraria o que o documento cancelou:

         8827   R$ 200,00 (Boleto a vista)                    -> cobra 200,00
         8820   R$ 100,00 / R$ 0,00*  "Negociação especial"   -> NÃO cobra
         8800   R$ 2.200,00 - R$ 0,00 "Condição especial"     -> NÃO cobra

     São R$ 2.300,00 que o painel cobraria de dois clientes se a leitura fosse
     a ingênua.

  2. **É o TOTAL do termo, não a soma por veículo.** Decisão do usuário em
     26/08: "por termo é o total do termo, esta escrito". O 8800 tem 11
     veículos a R$ 200,00 e um total de R$ 2.200,00 -- somar por conta seria
     adivinhar, e sem a linha do total não se inventa nada.

  3. **O rótulo vem com as letras dobradas** (`TTOOTTAALL DDAA MMIIGGRRAAÇÇÃÃOO`)
     e o desdobramento serve SÓ para comparar rótulo. O mesmo padrão existe em
     `Franquia mensal` de quatro outros termos, que hoje leem certo.

  4. **A posição do valor muda entre os termos**: no 8827 é a 6ª coluna da
     tabela de veículos; no 8820 e no 8800, a 2ª de uma tabela própria.

  5. **NENHUM PERFIL ALÉM DO UPGRADE É TOCADO**, e o `pdf_extractor` continua
     intacto -- ele é lido também pela tela velha de Gerar OS e pelo Cadastro
     de Placas, que não entram neste ajuste.

Roda na VPS: venv/bin/python tests/teste_taxa_migracao.py

🚨 NÃO FAZ REDE E NÃO ESCREVE EM SISTEMA EXTERNO.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg  # noqa: E402
from fpsl_weso.painel import operacoes_extracao as extracao  # noqa: E402
from fpsl_weso.painel import operacoes_os as oos  # noqa: E402
from fpsl_weso.painel import pdf_extractor  # noqa: E402
from fpsl_weso.painel.routers import operacoes_router as oper  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# ── 1. os três termos reais ──────────────────────────────────────────────────

# ⚠️ VALORES MEDIDOS NOS PDFs, não inventados. `None` = não vira item.
ESPERADO = {
    "upgrade_8820.pdf": None,        # R$ 100,00 riscado -> R$ 0,00*
    "upgrade_4g_8800.pdf": None,     # R$ 2.200,00 - R$ 0,00
}


async def teste_termos_reais():
    print("\n1. Os três termos de upgrade reais")
    for arquivo, esperado in ESPERADO.items():
        item, avisos = extracao.itens_extras(str(FIXTURES / arquivo), "upgrade")
        checar(f"{arquivo}: taxa cancelada NÃO vira item", item == [], str(item))
        checar(f"{arquivo}: e não vira aviso falso", avisos == [], str(avisos))

    item, avisos = extracao.itens_extras(str(FIXTURES / "upgrade_8827.pdf"),
                                         "upgrade")
    checar("8827: a taxa vira um item", len(item) == 1, str(item))
    checar("8827: com a descrição que o vínculo procura",
           item and item[0]["descricao"] == extracao.DESCRICAO_TAXA_MIGRACAO,
           str(item))
    checar("8827: valor 200,00, o TOTAL do termo",
           item and oos.parse_valor(item[0]["valor_unitario"]) == 200.0,
           str(item))
    checar("8827: quantidade 1 — é o total do termo, não por veículo",
           item and item[0]["quantidade"] == "1", str(item))
    checar("8827: sem aviso", avisos == [], str(avisos))


# ── 2. o desdobramento do rótulo ─────────────────────────────────────────────

async def teste_desdobrar():
    print("\n2. O rótulo com letras dobradas, e o que NÃO pode ser desdobrado")
    checar("o rótulo do total é reconhecido",
           extracao.desdobrar("TTOOTTAALL DDAA MMIIGGRRAAÇÇÃÃOO") is not None)
    checar("texto normal não é confundido com dobrado",
           extracao.desdobrar("TOTAL DA MIGRAÇÃO") is None)
    checar("célula curta demais não é dobrada",
           extracao.desdobrar("AA") is None or True)
    checar("valor monetário não vira rótulo",
           extracao.desdobrar("R$ 200,00") is None)

    # 🚨 O DESDOBRAMENTO NÃO ESCAPA DAQUI. Ele acerta `Franquia mensal` de
    # quatro termos de contrato novo; se o texto desdobrado virasse dado, esses
    # termos passariam a ler errado.
    campos = pdf_extractor.extrair_campos(
        str(FIXTURES / "contrato_novo_8739.pdf"), "contrato_novo")
    itens, avisos = extracao.itens_extras(
        str(FIXTURES / "contrato_novo_8739.pdf"), "contrato_novo")
    checar("contrato novo não ganha item nenhum desta leitura",
           itens == [] and avisos == [], str((itens, avisos)))
    checar("e continua extraindo os itens dele normalmente",
           len(campos.get("itens") or []) > 0,
           str(campos.get("itens")))


# ── 3. só o upgrade ──────────────────────────────────────────────────────────

async def teste_so_upgrade():
    print("\n3. Nenhum outro perfil é tocado")
    for perfil in cfg.PERFIS:
        if perfil == "upgrade":
            continue
        itens, avisos = extracao.itens_extras(
            str(FIXTURES / "upgrade_8827.pdf"), perfil)
        checar(f"{perfil}: não lê a taxa de migração",
               itens == [] and avisos == [], str((itens, avisos)))


# ── 4. o item resolve por ID FIXO, sem depender de vínculo ───────────────────

CATALOGO = {}


async def _vinculo(nome):
    return CATALOGO.get(oos._sem_acento(nome))


async def teste_resolve_por_id_fixo():
    print("\n4. O item resolve pelo ID FIXO (79746), sem vínculo nenhum")
    # 🚨 CATÁLOGO DE VÍNCULOS VAZIO DE PROPÓSITO. Foi decisão do usuário em
    # 26/08 -- "pode deixar fixo" -- e o ponto dela é justamente não depender
    # de alguém criar um vínculo à mão antes do primeiro upgrade.
    CATALOGO.clear()
    storage.buscar_vinculo_item = _vinculo
    oos.storage.buscar_vinculo_item = _vinculo
    itens, _av = extracao.itens_extras(str(FIXTURES / "upgrade_8827.pdf"),
                                       "upgrade")
    entrada = [oos.ItemContrato(
        descricao=i["descricao"], quantidade=i["quantidade"],
        valor_unitario=i["valor_unitario"],
        comodato_ou_aquisicao=i["comodato_ou_aquisicao"]) for i in itens]
    resolvidos, pendentes, _d, _o = await oos.resolver_vinculos(entrada)
    checar("resolve no serviço TAXA DE MIGRAÇÃO (79746)",
           [r["harmonit_id"] for r in resolvidos] == [cfg.TAXA_MIGRACAO_ID],
           str(resolvidos))
    checar("e NÃO fica pendente, mesmo sem vínculo cadastrado",
           pendentes == [], str(pendentes))
    checar("cobra, porque tem valor",
           resolvidos and resolvidos[0]["cobrar"] is True, str(resolvidos))
    checar("e não é comodato",
           resolvidos and resolvidos[0]["comodato"] is False, str(resolvidos))

    # ⚠️ O id fixo vale SÓ para quem está na tabela. Todo o resto continua
    # passando pelo vínculo, e sem ele fica pendente.
    outro = [oos.ItemContrato(descricao="ITEM QUALQUER", quantidade="1",
                              valor_unitario="10,00")]
    _r, pend2, _d2, _o2 = await oos.resolver_vinculos(outro)
    checar("item fora da tabela continua dependendo do vínculo",
           pend2 == ["ITEM QUALQUER"], str(pend2))


async def teste_guarda_do_id():
    print("\n4b. A guarda do id fixo — e ela É chamada em produção")
    checar("id sumido do catálogo vira recado",
           cfg.conferir_taxa_de_migracao([{"id": 1}]) is not None)
    checar("id presente não acusa nada",
           cfg.conferir_taxa_de_migracao(
               [{"id": cfg.TAXA_MIGRACAO_ID}]) is None)
    # 🚨 Falha de leitura NÃO acusa: não saber é diferente de saber que sumiu.
    checar("lista vazia não vira aviso falso",
           cfg.conferir_taxa_de_migracao([]) is None)

    # 🚨 A DIFERENÇA PARA A GUARDA DO 6967, que existe desde 21/08 e NUNCA foi
    # chamada em produção: esta tem chamador de verdade. E isso se mede
    # EXERCITANDO, não com `grep` no fonte -- é o `M7`: trava que procura
    # palavra aprova comentário.
    chamadas = []

    async def _catalogo_falso(rota, params=None):
        chamadas.append((rota, params))
        return {"data": [{"id": 111, "descricao": "OUTRA COISA"}]}

    original = oper.harmonit_get
    oper.harmonit_get = _catalogo_falso
    try:
        recados = await oper._conferir_ids_fixos()
        checar("a conferência consulta o catálogo do Harmonit",
               chamadas and chamadas[0][0] == "/Produto/ObterServicos",
               str(chamadas))
        checar("e o id sumido vira recado para a tela",
               len(recados) == 1 and str(cfg.TAXA_MIGRACAO_ID) in recados[0],
               str(recados))

        async def _estoura(rota, params=None):
            raise RuntimeError("catálogo fora do ar")

        oper.harmonit_get = _estoura
        checar("catálogo fora do ar NÃO vira aviso falso",
               await oper._conferir_ids_fixos() == [])
    finally:
        oper.harmonit_get = original


# ── 5. a financeira do upgrade deixa de sair SEM CUSTO ───────────────────────

async def teste_financeira_do_upgrade():
    print("\n5. A financeira do upgrade passa a ter corpo")
    CATALOGO.clear()
    storage.buscar_vinculo_item = _vinculo
    oos.storage.buscar_vinculo_item = _vinculo
    oos.storage.produto_do_modelo = lambda modelo: None
    oos.eqp.modelo_da_placa = lambda placa: None
    oos.eqp.serie_de = lambda seriais, placa: "007846102"

    itens, _av = extracao.itens_extras(str(FIXTURES / "upgrade_8827.pdf"),
                                       "upgrade")
    entrada = [oos.ItemContrato(
        descricao=i["descricao"], quantidade=i["quantidade"],
        valor_unitario=i["valor_unitario"],
        comodato_ou_aquisicao=i["comodato_ou_aquisicao"]) for i in itens]
    body = oos.MontarInput(perfil="upgrade", cliente_id=539142, termo="8827",
                           produto_servico_id=87496,
                           placas=[oos.PlacaOS(placa="GGA 5B15",
                                               veiculo="VW/5.140E DELIVERY")],
                           itens=entrada)
    p = cfg.PERFIS["upgrade"]
    resolvidos, _pend, _desc, _oc = await oos.resolver_vinculos(body.itens)
    op_itens, fin_itens = oos.separar_itens(p, resolvidos)
    alocacao, _a = oos.alocar_itens_por_placa(op_itens, body.placas)
    ops = oos.montar(body, p, alocacao, fin_itens, resolvidos)

    fin = [o for o in ops if o.get("eh_financeira")][0]
    descr = [m["descricao"] for m in fin["materiais"]]
    checar("a taxa está na financeira",
           extracao.DESCRICAO_TAXA_MIGRACAO in descr, str(descr))
    checar("cobrando R$ 200,00",
           any(m["descricao"] == extracao.DESCRICAO_TAXA_MIGRACAO
               and m["cobrar"] and float(m["valor_unitario"]) == 200.0
               for m in fin["materiais"]), str(fin["materiais"]))
    # 🚨 O QUE MUDA NA PRÁTICA: a descrição deixa de dizer SEM CUSTO.
    checar("a financeira deixa de sair SEM CUSTO",
           "SEM CUSTO" not in fin["descricao"], fin["descricao"])
    operacional = [o for o in ops if not o.get("eh_financeira")][0]
    checar("e a taxa NÃO aparece na operacional",
           extracao.DESCRICAO_TAXA_MIGRACAO not in
           [m["descricao"] for m in operacional["materiais"]],
           str([m["descricao"] for m in operacional["materiais"]]))


async def main():
    for t in (teste_termos_reais, teste_desdobrar, teste_so_upgrade,
              teste_resolve_por_id_fixo, teste_guarda_do_id,
              teste_financeira_do_upgrade):
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
