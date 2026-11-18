"""Nenhuma OS de retirada sai com item de comodato flegado — 17/11.

🔵 DECISÃO DELE (17/11): *"nenhuma OS de retirada pode ter item de comodato
flegado"*, delimitada no mesmo dia por *"somente rescisão"*, *"Sub retirada
não é só retirada"* e *"1 regra só para as duas, evitar lixo"*.

O que este arquivo PRENDE, e que reprova se alguém desfizer:
  1. **A trava do tipo:** 57 é o `tipo_id` do perfil `rescisao` nos DOIS
     configs, nenhum outro perfil usa 57, e o 73 da Substituição Retirada
     fica de fora. Mudar um config faria a regra deixar de pegar em silêncio;
     aqui ela reprova antes.
  2. **Caminho novo (aba Operações), termo 8893 real:** a OS de rescisão sai
     com ZERO material flegado, inclusive o EQUIPAMENTO da WESO -- que era
     exatamente o que escapava da regra de 13/11.
  3. **O defeito fica guardado:** sem a regra, a mesma montagem AINDA produz
     comodato. Teste que não reprova no código de antes não prova nada.
  4. **Caminho velho (tela Gerar OS):** idem -- e ali o item do CONTRATO
     também saía flegado, porque o `_resolver_vinculos` dela nunca recebeu a
     regra de 13/11 (não recebe nem o perfil).
  5. **O valor patrimonial fica de pé** e o que a regra NÃO faz: não toca
     `cobrar`, não toca valor, não remove nem reordena item.
  6. **Os outros tipos não se movem:** Substituição Retirada (73), contrato
     (76), upgrade (77), manutenção (1783) e a financeira (2) saem idênticos.
  7. **A ordem da chamada:** nos dois routers a regra roda DEPOIS do cabeçalho,
     que é quem fecha o `tipo_id`. Trava no próprio fonte, como a do
     `teste_car_variavel`.

Roda na VPS: venv/bin/python tests/teste_retirada_sem_comodato.py
🚨 NÃO FAZ REDE E NÃO ESCREVE EM SISTEMA EXTERNO.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg  # noqa: E402
from fpsl_weso.painel import operacoes_os as oos  # noqa: E402
from fpsl_weso.painel import operacoes_retirada as ret  # noqa: E402
from fpsl_weso.painel import templates_config as tcfg  # noqa: E402

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# ⚠️ IDS REAIS dos vínculos de produção (os mesmos do
# `teste_aquisicao_retirada`, para os dois testes falarem do mesmo termo).
CATALOGO = {
    "CENTRAL 24 HORAS": {"harmonit_id": 6976, "oculto": False, "nas_duas": True},
    "RASTREADOR": {"harmonit_id": 20314, "oculto": False, "nas_duas": False},
    "CHIP DE DADOS": {"harmonit_id": 16016, "oculto": False, "nas_duas": False},
    "BLOQUEIO VEICULAR": {"harmonit_id": 45689, "oculto": False, "nas_duas": False},
    "LEITOR I-BUTTON": {"harmonit_id": 6984, "oculto": False, "nas_duas": False},
}

# O de-para do modelo: o ST310U de R$ 1.100,00, como em produção.
PRODUTO = {"harmonit_id": 999, "valor": 1100.0, "descricao": "RASTREADOR ST310U"}


async def _vinculo(nome):
    return CATALOGO.get(oos._sem_acento(nome))


def instalar_dubles():
    """🚨 DUBLÊ NA BORDA, só: banco e de-para. A regra e a montagem são as de
    produção -- duplo que cobre regra fica verde em produção quebrada."""
    storage.buscar_vinculo_item = _vinculo
    oos.storage.buscar_vinculo_item = _vinculo
    storage.produto_do_modelo = lambda m: PRODUTO
    oos.storage.produto_do_modelo = lambda m: PRODUTO
    oos.modelo_da_operacao = lambda *a, **k: "ST310U"


def item(desc, valor, tipo):
    return oos.ItemContrato(descricao=desc, quantidade="01",
                            valor_unitario=valor, comodato_ou_aquisicao=tipo)


# O termo 8893, linha a linha como está no PDF.
TERMO_8893 = [
    item("RASTREADOR", "999,90", "COMODATO"),
    item("CHIP DE DADOS", "50,00", "COMODATO"),
    item("BLOQUEIO VEICULAR", "50,00", "COMODATO"),
    item("CENTRAL 24 HORAS", "10,00", "DESATIVAR NO SISTEMA"),
    item("LEITOR I-BUTTON", "150,00", "AQUISIÇÃO"),
]

PLACAS = [oos.PlacaOS(placa="ABC1234", veiculo="FIAT STRADA")]


def _flegados(operacoes):
    """Descrição de todo material com comodato, por OS de retirada."""
    saida = []
    for op in operacoes:
        if op.get("tipo_id") != ret.TIPO_OS_RETIRADA:
            continue
        saida += [m.get("descricao") for m in op.get("materiais") or []
                  if m.get("comodato")]
    return saida


# ── 1. a trava do tipo ───────────────────────────────────────────────────────

def teste_trava_do_tipo():
    print("\n1. O tipo 57 é da rescisão, e só dela, nos dois configs")
    checar("o módulo diz 57", ret.TIPO_OS_RETIRADA == 57,
           str(ret.TIPO_OS_RETIRADA))
    checar("config novo: rescisao é 57",
           cfg.PERFIS["rescisao"]["tipo_id"] == ret.TIPO_OS_RETIRADA,
           str(cfg.PERFIS["rescisao"].get("tipo_id")))
    checar("config velho: rescisao é 57",
           tcfg.PERFIS["rescisao"]["tipo_id"] == ret.TIPO_OS_RETIRADA,
           str(tcfg.PERFIS["rescisao"].get("tipo_id")))
    for nome, perfis in (("novo", cfg.PERFIS), ("velho", tcfg.PERFIS)):
        outros = [k for k, v in perfis.items()
                  if k != "rescisao" and v.get("tipo_id") == ret.TIPO_OS_RETIRADA]
        checar(f"config {nome}: nenhum outro perfil usa 57", outros == [],
               str(outros))
        # 🔵 DELE: *"Sub retirada não é só retirada"* -- o 73 fica fora.
        subs = [k for k, v in perfis.items()
                if v.get("tipo_id_retirada") == ret.TIPO_OS_RETIRADA]
        checar(f"config {nome}: nenhum tipo_id_retirada é 57 (o 73 fica fora)",
               subs == [], str(subs))


# ── 2 e 3. caminho novo: a montagem de produção ──────────────────────────────

async def _montagem_nova():
    resolvidos, *_ = await oos.resolver_vinculos(TERMO_8893,
                                                 perfil_chave="rescisao")
    perfil = cfg.PERFIS["rescisao"]
    oper, fin = oos.separar_itens(perfil, resolvidos)
    alocacao, _avisos = oos.alocar_itens_por_placa(oper, PLACAS)
    body = oos.MontarInput(perfil="rescisao", cliente_id=260516,
                           produto_servico_id=1, termo="8893", placas=PLACAS,
                           itens=TERMO_8893)
    return body, perfil, alocacao, fin, resolvidos


async def teste_caminho_novo():
    print("\n2-3. Caminho novo (aba Operações), termo 8893 real")
    body, perfil, alocacao, fin, resolvidos = await _montagem_nova()

    # 🚨 O DEFEITO, GUARDADO: a montagem CRUA ainda flega o equipamento.
    cru = oos.montar(body, perfil, alocacao, fin, resolvidos, {}, {}, {})
    antes = _flegados(cru)
    checar("sem a regra a montagem AINDA flega (o teste reprova no código "
           "de antes)", antes != [], f"flegados={antes}")
    checar("e o que escapava era o EQUIPAMENTO da WESO",
           any("ST310U" in (d or "") for d in antes), f"flegados={antes}")

    # Agora o caminho de produção: `_montar_tudo`, que é quem a prévia e a
    # gravação chamam.
    from fpsl_weso.painel.routers import operacoes_router as novo
    pre = {"perfil": perfil, "alocacao": alocacao, "itens_financeiro": fin,
           "resolvidos": resolvidos, "cabecalho": {},
           "ctx": {"seriais": {}, "recipientes": {}, "dados": {}}}
    operacoes = novo._montar_tudo(body, pre)
    depois = _flegados(operacoes)
    checar("a OS de rescisão sai com ZERO material flegado", depois == [],
           f"flegados={depois}")

    retirada = [o for o in operacoes if o.get("tipo_id") == ret.TIPO_OS_RETIRADA]
    checar("e houve uma OS de retirada para conferir", len(retirada) == 1,
           f"{len(retirada)} OS tipo {ret.TIPO_OS_RETIRADA}")
    if not retirada:
        return
    mats = retirada[0]["materiais"]
    rastreador = next((m for m in mats if "ST310U" in (m.get("descricao") or "")),
                      None)
    checar("o equipamento continua na OS (não foi removido)", rastreador is not None,
           str([m.get("descricao") for m in mats]))
    checar("com o valor patrimonial de pé (R$ 1.100,00)",
           rastreador and rastreador["valor_unitario"] == 1100.0, str(rastreador))
    checar("sem cobrar -- distrato não cobra o que volta",
           rastreador and rastreador["cobrar"] is False, str(rastreador))
    cobrados = [m.get("descricao") for m in mats if m.get("cobrar")]
    checar("nenhum material da retirada virou cobrança", cobrados == [],
           str(cobrados))


# ── 4. caminho velho: a tela Gerar OS ────────────────────────────────────────

async def teste_caminho_velho():
    print("\n4. Caminho velho (tela Gerar OS) — onde até o item do contrato "
          "saía flegado")
    from fpsl_weso.painel.routers import os_router as velho
    velho._modelo_da_operacao = lambda *a, **k: "ST310U"

    itens = [velho.ItemContratoInput(descricao=i.descricao, quantidade="01",
                                     valor_unitario=i.valor_unitario,
                                     comodato_ou_aquisicao=i.comodato_ou_aquisicao)
             for i in TERMO_8893]
    resolvidos, *_ = await velho._resolver_vinculos(itens)
    checar("o termo foi resolvido nesta tela também", resolvidos != [],
           f"{len(resolvidos)} itens")
    if not resolvidos:
        return

    perfil = tcfg.PERFIS["rescisao"]
    try:
        equip = velho._material_do_equipamento(perfil, "ABC1234", resolvidos, {}, {})
    except TypeError:
        equip = velho._material_do_equipamento(perfil, "ABC1234", resolvidos)
    mats = velho._substituir_rastreador(resolvidos, equip)
    op = {"tipo_id": perfil["tipo_id"], "materiais": mats}

    antes = _flegados([op])
    checar("sem a regra esta tela flega VÁRIOS itens, não só o equipamento",
           len(antes) >= 2, f"flegados={antes}")
    checar("entre eles item do CONTRATO (a regra de 13/11 nunca chegou aqui)",
           any(d in ("CHIP DE DADOS", "BLOQUEIO VEICULAR") for d in antes),
           f"flegados={antes}")

    ret.aplicar([op])
    depois = _flegados([op])
    checar("com a regra, ZERO flegado nesta tela também", depois == [],
           f"flegados={depois}")
    checar("e nenhum item foi removido", len(op["materiais"]) == len(mats),
           f"{len(op['materiais'])} de {len(mats)}")


# ── 5 e 6. o que a regra NÃO faz ─────────────────────────────────────────────

def teste_nao_toca_o_resto():
    print("\n5-6. O que a regra não faz, e os tipos que não se movem")
    base = {"descricao": "RASTREADOR", "harmonit_id": 1, "quantidade": 1,
            "valor_unitario": 1100.0, "comodato": True, "cobrar": True}

    op = {"tipo_id": ret.TIPO_OS_RETIRADA, "materiais": [dict(base)]}
    ret.aplicar([op])
    m = op["materiais"][0]
    checar("na retirada apaga SÓ o comodato", m["comodato"] is False, str(m))
    checar("não toca `cobrar`", m["cobrar"] is True, str(m))
    checar("não toca o valor", m["valor_unitario"] == 1100.0, str(m))
    checar("não mexe no harmonit_id nem na quantidade",
           m["harmonit_id"] == 1 and m["quantidade"] == 1, str(m))

    # 🔵 DELE: *"Demais tipos não pode mexer"*. 73 = Substituição Retirada.
    outros = {"Substituição Retirada": 73, "contrato": 76, "upgrade": 77,
              "manutenção": 1783, "financeira": cfg.TIPO_CONTRATO_ID}
    for nome, tipo in outros.items():
        op = {"tipo_id": tipo, "materiais": [dict(base)]}
        ret.aplicar([op])
        checar(f"tipo {tipo} ({nome}): sai idêntico",
               op["materiais"][0] == base, str(op["materiais"][0]))

    op = {"tipo_id": None, "materiais": [dict(base)]}
    ret.aplicar([op])
    checar("OS sem tipo não é retirada (não mexe)",
           op["materiais"][0] == base, str(op["materiais"][0]))
    ret.aplicar([])
    ret.aplicar([{"tipo_id": ret.TIPO_OS_RETIRADA}])
    checar("lista vazia e OS sem materiais não estouram", True)


# ── 7. a ordem da chamada, no fonte ──────────────────────────────────────────

def teste_ordem_no_fonte():
    print("\n7. A regra roda DEPOIS do cabeçalho, nos dois routers")
    base = pathlib.Path(__file__).resolve().parent.parent / "fpsl_weso" / "painel" / "routers"
    casos = (
        ("operacoes_router.py", "_aplicar_cabecalho(operacoes"),
        ("os_router.py", 'op["tipo_id"] = cabecalho.get("tipo_id")'),
    )
    for arquivo, marca_cabecalho in casos:
        texto = (base / arquivo).read_text(encoding="utf-8")
        checar(f"{arquivo}: chama a regra única",
               "retirada.aplicar(" in texto)
        checar(f"{arquivo}: importa o módulo da regra",
               "operacoes_retirada as retirada" in texto)
        # 🚨 NENHUMA CÓPIA DA REGRA: o tipo 57 não pode estar escrito aqui, nem
        # como número nem como constante redefinida. É isto que impede o gêmeo
        # de nascer de novo.
        # ⚠️ NÃO VALE OLHAR `"comodato": False`: medido em 17/11, o `os_router`
        # tem 4 ocorrências LEGÍTIMAS e antigas dele (o `_material_fixo` e os
        # ramos de transferência, que limpam a flag pelo caminho próprio desde
        # 29/07). A primeira versão desta trava reprovava por causa delas --
        # era a trava errada, não o código.
        checar(f"{arquivo}: não tem o 57 solto (a regra não foi copiada)",
               "== 57" not in texto and "TIPO_OS_RETIRADA =" not in texto
               and "= 57" not in texto)
        linhas = texto.splitlines()
        i_cab = next((i for i, l in enumerate(linhas) if marca_cabecalho in l), -1)
        i_reg = next((i for i, l in enumerate(linhas)
                      if "retirada.aplicar(" in l), -1)
        checar(f"{arquivo}: a regra vem depois do cabeçalho",
               i_cab >= 0 and i_reg > i_cab, f"cabecalho={i_cab} regra={i_reg}")


async def main():
    instalar_dubles()
    teste_trava_do_tipo()
    await teste_caminho_novo()
    await teste_caminho_velho()
    teste_nao_toca_o_resto()
    teste_ordem_no_fonte()
    print(f"\n{'=' * 62}")
    print(f"{ok} verificações OK, {len(falhas)} falhas")
    if falhas:
        for f in falhas:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
