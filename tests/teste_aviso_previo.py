"""Aba Operações — o aviso prévio da rescisão. 2026-08-26 (C1).

O que este arquivo PRENDE, e que reprova se alguém desfizer:

  1. **O prazo negociado não muda o item.** O modelo do termo traz "90 DIAS DE
     AVISO PRÉVIO DE CANCELAMENTO"; quando o comercial concede prazo menor, o
     campo vira "(90) 30 DIAS DE AVISO PRÉVIO DE CANCELAMENTO". O vínculo casa
     por texto EXATO, então a segunda grafia virava PENDENTE, bloqueava a
     geração, e a saída fácil na tela de Vínculos era marcar OCULTO.

     🚨 FOI ASSIM QUE R$ 131,74 SUMIRAM. Termo 8848, 25/08: o item foi ocultado
     às 12:15:27, a prévia foi aberta às 12:15:59 e a OS gerada às 12:16:05 --
     a financeira 16805 saiu com R$ 20,00 de Central e nada de aviso prévio.

  2. **A DESCRIÇÃO ORIGINAL NÃO SE PERDE.** A normalização é só a chave de
     busca do vínculo. É a descrição do termo que a financeira lista e é dela
     que sai o prazo -- se ela fosse sobrescrita pelo canônico, toda rescisão
     passaria a dizer "90 dias", inclusive as de 30.

  3. **Mede o sufixo E o que vem antes dele**, não a ocorrência da palavra
     (`M7`). "MULTA POR 90 DIAS DE AVISO PRÉVIO DE CANCELAMENTO" NÃO é este
     item e continua pendente, que é o comportamento honesto.

  4. **O prazo vai para a solução técnica, acima do traço.** Decisão do usuário
     em 26/08. O cabeçalho com data e o separador já existiam e vinham sempre
     vazios: a aba nunca preencheu `solucao_tecnica`.

  5. **Item OCULTO deixa rastro na prévia.** Era a única forma de um item do
     termo sumir da OS sem nada aparecer na tela -- `NÃO CONTRATADO` sempre
     virou aviso, oculto era mudo. É o outro lado do mesmo prejuízo do 8848.

Roda na VPS: venv/bin/python tests/teste_aviso_previo.py

🚨 NÃO FAZ REDE E NÃO ESCREVE EM SISTEMA EXTERNO. O vínculo entra por dublê;
os termos são os PDFs reais de `tests/fixtures`.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import operacoes_os as oos  # noqa: E402
from fpsl_weso.painel.pdf_extractor import extrair_campos  # noqa: E402
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


# ── dublê ────────────────────────────────────────────────────────────────────
#
# ⚠️ IDS REAIS, CONGELADOS. O 16033 é o serviço AVISO PRÉVIO do Harmonit, e o
# vínculo `90 DIAS DE AVISO PREVIO DE CANCELAMENTO` -> 16033 existe em produção
# desde 24/07. O dublê reproduz a busca do storage: normalizada, sem acento.

CATALOGO = {
    "90 DIAS DE AVISO PREVIO DE CANCELAMENTO": {
        "harmonit_id": 16033, "oculto": False, "nas_duas": False},
    "TAXA DE RETIRADA": {"harmonit_id": 7277, "oculto": False, "nas_duas": False},
    "CENTRAL 24 HORAS": {"harmonit_id": 6976, "oculto": False, "nas_duas": True},
    "RASTREADOR": {"harmonit_id": 20314, "oculto": False, "nas_duas": False},
    "CHIP DE DADOS": {"harmonit_id": 16016, "oculto": False, "nas_duas": False},
    "BLOQUEIO VEICULAR": {"harmonit_id": 45689, "oculto": False, "nas_duas": False},
}


async def _vinculo(nome):
    return CATALOGO.get(oos._sem_acento(nome))


def instalar_dubles():
    """Nenhuma chamada sai desta máquina depois disto."""
    storage.buscar_vinculo_item = _vinculo
    oos.storage.buscar_vinculo_item = _vinculo


def item(desc, qtd="1", valor="0,00", tipo=None):
    return oos.ItemContrato(descricao=desc, quantidade=qtd,
                            valor_unitario=valor, comodato_ou_aquisicao=tipo)


# ── 1. as três redações reais ────────────────────────────────────────────────

MODELO = "90 DIAS DE AVISO PRÉVIO DE CANCELAMENTO"
NEGOCIADO = "(90) 30 DIAS DE AVISO PRÉVIO DE CANCELAMENTO"


async def teste_reconhecimento():
    print("\n1. Reconhecer o aviso prévio em qualquer redação de prazo")
    checar("a redação do modelo é reconhecida", oos.eh_aviso_previo(MODELO))
    checar("a redação com prazo negociado é reconhecida",
           oos.eh_aviso_previo(NEGOCIADO))
    checar("as duas procuram o MESMO vínculo",
           oos.nome_para_vinculo(MODELO) == oos.nome_para_vinculo(NEGOCIADO)
           == oos.AVISO_PREVIO_CANONICO,
           f"{oos.nome_para_vinculo(MODELO)!r} x {oos.nome_para_vinculo(NEGOCIADO)!r}")
    checar("o prazo sai na ordem em que está escrito",
           oos.prazo_do_aviso(NEGOCIADO) == "90/30",
           oos.prazo_do_aviso(NEGOCIADO))

    # 🚨 M7: mede a LIGAÇÃO, não a ocorrência da palavra. O que vem antes do
    # sufixo tem de ser só prazo -- número, parêntese, barra, espaço.
    outro = "MULTA POR 90 DIAS DE AVISO PRÉVIO DE CANCELAMENTO"
    checar("encargo com outra palavra antes do prazo NÃO é este item",
           not oos.eh_aviso_previo(outro))
    checar("e continua procurando o vínculo pelo próprio nome",
           oos.nome_para_vinculo(outro) == outro)
    checar("item comum não tem a chave de busca alterada",
           oos.nome_para_vinculo("TAXA DE RETIRADA") == "TAXA DE RETIRADA")
    checar("sufixo parecido, sem 'DIAS', não é este item",
           not oos.eh_aviso_previo("SEM AVISO PRÉVIO DE CANCELAMENTO"))


# ── 2. resolve o vínculo, e preserva o que o termo escreveu ──────────────────

async def teste_resolve_sem_pendencia():
    print("\n2. O prazo negociado resolve o vínculo e NÃO vira pendente")
    instalar_dubles()
    resolvidos, pendentes, descartados, _oc = await oos.resolver_vinculos(
        [item(NEGOCIADO, "1", "131,74")])
    checar("não sobrou pendente", pendentes == [], str(pendentes))
    checar("nada foi descartado", descartados == [], str(descartados))
    checar("resolveu no serviço AVISO PRÉVIO (16033)",
           [r["harmonit_id"] for r in resolvidos] == [16033], str(resolvidos))
    checar("a cobrança sai marcada, porque tem valor",
           resolvidos[0]["cobrar"] is True and not resolvidos[0]["comodato"])
    checar("o valor do termo chega inteiro",
           resolvidos[0]["valor_unitario"] == 131.74,
           str(resolvidos[0]["valor_unitario"]))
    # 🚨 A descrição é a do TERMO, não a canônica: senão toda rescisão passaria
    # a dizer "90 dias", inclusive as de 30.
    checar("a descrição do termo é preservada",
           resolvidos[0]["descricao"] == NEGOCIADO, resolvidos[0]["descricao"])

    resolvidos_modelo, pend2, _, _oc = await oos.resolver_vinculos(
        [item(MODELO, "1", "6.447,48")])
    checar("a redação do modelo continua resolvendo igual",
           pend2 == [] and resolvidos_modelo[0]["harmonit_id"] == 16033)
    checar("e o valor de milhar não se perde no caminho",
           resolvidos_modelo[0]["valor_unitario"] == 6447.48,
           str(resolvidos_modelo[0]["valor_unitario"]))


# ── 3. o prazo na solução técnica ────────────────────────────────────────────

async def teste_contexto():
    print("\n3. O prazo vai para a solução técnica, acima do traço")
    instalar_dubles()
    resolvidos, _, _, _oc = await oos.resolver_vinculos([item(NEGOCIADO, "1", "131,74")])
    contexto = oos.contexto_do_termo(resolvidos)
    checar("a linha diz os dois prazos", "90/30 dias" in contexto, contexto)
    checar("a linha diz o valor em real", "R$ 131,74" in contexto, contexto)

    texto = oos.formatar_solucao_tecnica(
        oos.contexto_da_os(None, resolvidos), "")
    checar("o prazo entra ACIMA do separador",
           texto.index("90/30 dias") < texto.index("-------------"), texto)
    checar("o cabeçalho com data continua sendo a primeira linha",
           texto.startswith("[") and "Contexto da extração automática:" in texto)

    # ⚠️ A tela nunca mandou `solucao_tecnica`; se um dia mandar, os dois textos
    # somam -- preencher a tela não pode apagar o que o termo diz.
    juntos = oos.contexto_da_os("Cliente pediu retirada na sexta.", resolvidos)
    checar("texto da tela e texto do termo convivem",
           "sexta" in juntos and "90/30 dias" in juntos, juntos)

    vazio = oos.contexto_do_termo([
        {"descricao": "TAXA DE RETIRADA", "valor_unitario": 299.0}])
    checar("termo sem aviso prévio não inventa linha", vazio == "", vazio)


# ── 4. os documentos reais ───────────────────────────────────────────────────

async def teste_termos_reais():
    print("\n4. Os termos de rescisão reais, como o extrator os entrega")
    instalar_dubles()
    for arquivo, prazo_esperado in (("rescisao_8848.pdf", "90/30"),
                                    ("rescisao_8842.pdf", "90"),
                                    ("rescisao.pdf", "90")):
        campos = extrair_campos(str(FIXTURES / arquivo), "rescisao")
        itens = campos.get("itens") or []
        avisos = [i for i in itens if oos.eh_aviso_previo(i["descricao"])]
        checar(f"{arquivo}: o encargo de aviso prévio é reconhecido",
               len(avisos) == 1,
               str([i["descricao"] for i in itens]))
        if not avisos:
            continue
        checar(f"{arquivo}: prazo {prazo_esperado}",
               oos.prazo_do_aviso(avisos[0]["descricao"]) == prazo_esperado,
               oos.prazo_do_aviso(avisos[0]["descricao"]))
        resolvidos, pendentes, _, _oc = await oos.resolver_vinculos(
            [oos.ItemContrato(**{k: v for k, v in i.items()
                                 if k in ("descricao", "quantidade",
                                          "valor_unitario",
                                          "comodato_ou_aquisicao")})
             for i in itens])
        # ⚠️ AFIRMA SÓ SOBRE O AVISO PRÉVIO. O dublê é um recorte do catálogo,
        # não o catálogo -- `rescisao.pdf` traz LEITOR RFID, que não está aqui.
        # Exigir "nenhum pendente" mediria o dublê, não a correção.
        checar(f"{arquivo}: o aviso prévio não fica pendente",
               not any(oos.eh_aviso_previo(p) for p in pendentes),
               str(pendentes))
        ids = [r["harmonit_id"] for r in resolvidos
               if oos.eh_aviso_previo(r["descricao"])]
        checar(f"{arquivo}: o aviso prévio resolve em 16033", ids == [16033],
               str(ids))

    # 🚨 O 8848 é o termo que perdeu a cobrança. O valor tem de chegar inteiro.
    campos = extrair_campos(str(FIXTURES / "rescisao_8848.pdf"), "rescisao")
    aviso = [i for i in campos["itens"] if oos.eh_aviso_previo(i["descricao"])][0]
    checar("8848: o valor do aviso prévio é o TOTAL GERAL, R$ 131,74",
           oos.parse_valor(aviso["valor_unitario"]) == 131.74,
           str(aviso))
    # A taxa de retirada do 8848 vem riscada (R$ 299,00 -> R$ 0,00*) e o
    # extrator já a descarta. Não é regressão: é o comportamento certo.
    checar("8848: a taxa de retirada riscada continua fora",
           not any("RETIRADA" in i["descricao"].upper()
                   for i in campos["itens"]),
           str([i["descricao"] for i in campos["itens"]]))


# ── 5. o item oculto deixa rastro ───────────────────────────────────────────

async def teste_oculto_deixa_rastro():
    print("\n5. Item com vínculo OCULTO aparece na prévia")
    instalar_dubles()
    CATALOGO["ITEM QUE ALGUEM OCULTOU"] = {
        "harmonit_id": None, "oculto": True, "nas_duas": False}

    # 🚨 NENHUMA REDE. `_preparar` leria WESO e Harmonit; os dois entram por
    # dublê, e é por isso que este teste pode rodar na suíte.
    oper._ler_weso = lambda body, perfil: _sem_weso()
    body = oos.MontarInput(
        perfil="contrato_novo", cliente_id=998063, termo="8848",
        produto_servico_id=777,
        placas=[oos.PlacaOS(placa="AAA 0A00", veiculo="CAMINHAO")],
        itens=[item("RASTREADOR", "1", "999,90", "COMODATO"),
               item("ITEM QUE ALGUEM OCULTOU", "1", "131,74", "CONTRATADO")])
    pre = await oper._preparar(body)

    checar("o oculto sai da OS", not any(
        r["descricao"] == "ITEM QUE ALGUEM OCULTOU" for r in pre["resolvidos"]))
    checar("mas volta como lista própria",
           pre["ocultados"] == ["ITEM QUE ALGUEM OCULTOU"], str(pre["ocultados"]))
    textos = " ".join(a["texto"] for a in pre["avisos"])
    checar("e vira aviso na prévia", "OCULTO" in textos, textos)
    checar("o aviso nomeia o item", "ITEM QUE ALGUEM OCULTOU" in textos, textos)
    checar("e diz o que acontece com a cobrança",
           "cobrança não vai sair" in textos, textos)
    checar("o item normal continua entrando",
           any(r["descricao"] == "RASTREADOR" for r in pre["resolvidos"]))

    # ⚠️ Sem oculto NENHUM, nada é dito: aviso falso treina a equipe a ignorar
    # aviso, que é a regra escrita em 19/08.
    limpo = await oper._preparar(oos.MontarInput(
        perfil="contrato_novo", cliente_id=998063, termo="8848",
        produto_servico_id=777,
        placas=[oos.PlacaOS(placa="AAA 0A00", veiculo="CAMINHAO")],
        itens=[item("RASTREADOR", "1", "999,90", "COMODATO")]))
    checar("termo sem item oculto não gera o aviso",
           not any("OCULTO" in a["texto"] for a in limpo["avisos"]),
           str(limpo["avisos"]))
    del CATALOGO["ITEM QUE ALGUEM OCULTOU"]


async def _sem_weso():
    return {"seriais": {}, "dados": {}, "recipientes": {}, "falhas": []}


async def main():
    for t in (teste_reconhecimento, teste_resolve_sem_pendencia,
              teste_contexto, teste_termos_reais, teste_oculto_deixa_rastro):
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
