"""Aba Operações — etapa 4 (F4): as OS, com as 14 regras. 2026-08-20.

O que este arquivo PRENDE, e que reprova se alguém desfizer:

  1. **Regra 4 — a financeira LISTA sempre.** Item de cobrança entra mesmo com
     valor zero; o `cobrar` é que depende do valor. Antes, financeira de valor
     zero saía com o corpo vazio e ninguém via o que tinha sido contratado --
     era por isso que "teste de tecnologia" precisava de perfil próprio.

  2. **Regra 7 — o `nas_duas` saiu.** Cada item pertence a um lado só. Nenhuma
     cópia de item de cobrança aparece na OS operacional.

  3. **A separação vem ANTES da alocação.** Alocar cobrança pelas placas a
     faria aparecer nas duas OS -- desfazendo a regra 7 por outro caminho.

  4. **Regra 9 — a WESO manda no modelo, e sem equipamento o operador
     escolhe.** Escolheu: o material sai do de-para, com o valor patrimonial.
     Não escolheu: sai o marcador e NÃO entra material -- não se inventa.

  5. **Os DOIS estados que produziam o mesmo texto.** "Nasceu agora" e "não
     consegui ler a WESO" são coisas diferentes; o segundo é o defeito da OS
     16775. Falha de leitura vence tudo, porque é a única que significa
     "não sei".

  6. **Regra 10 — novo titular vira DUAS OS.** A operacional só leva comodato;
     a cobrança vai na financeira. A híbrida antiga não existe mais.

  7. **Regra 11 — o ressarcimento é híbrido e NÃO tem comodato.** É por isso
     que ele pode ser híbrido e o novo titular não.

  8. **Regra 12 — a substituição FALHA ALTO sem o serviço escolhido**, e o
     valor vem do termo, não do código. Id fixo em código apodrece: foi assim
     que 7 das 14 OS de manutenção ficaram com `tipo = 55`.

  9. **A rescisão continua com `financeira_embutida`.** Decisão de 29/07, e a
     regra 3 da spec 28 a reverteria -- está PENDENTE de confirmação do
     usuário. Enquanto isso, o teste prende o que foi decidido.

 10. **Manutenção não flega nada e não gera financeira.**

Roda na VPS: venv/bin/python tests/teste_operacoes_f4.py

🚨 NÃO FAZ REDE E NÃO ESCREVE EM SISTEMA EXTERNO. Toda leitura de WESO e
Harmonit entra por dublê. Em 17/08 a própria suíte criou 6 veículos permanentes
no Harmonit; não se repete.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi import HTTPException  # noqa: E402
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg  # noqa: E402
from fpsl_weso.painel import operacoes_os as oos  # noqa: E402

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# ── dublês ───────────────────────────────────────────────────────────────────
#
# ⚠️ VALORES MEDIDOS E CONGELADOS, não inventados na hora. O de-para real tem
# 24 modelos; aqui basta um, com a forma exata que `produto_do_modelo` devolve.

CATALOGO = {
    "RASTREADOR": {"harmonit_id": 501, "oculto": False, "nas_duas": True},
    "TAXA DE ADESAO": {"harmonit_id": 502, "oculto": False, "nas_duas": False},
    "CENTRAL 24H": {"harmonit_id": 503, "oculto": False, "nas_duas": True},
    "ITEM OCULTO": {"harmonit_id": 504, "oculto": True, "nas_duas": False},
}

PRODUTO_ST340 = {"harmonit_id": 9001, "descricao": "RASTREADOR ST340",
                 "valor": 480.0}
# 🚨 O 2G NÃO TEM VALOR PATRIMONIAL NO DE-PARA, e chega como 0.0 -- não como
# None. É esse detalhe que fez o ST310U sair com R$ 0,00 em 14/08 contra
# R$ 1.100,00 no contrato.
PRODUTO_ST310U = {"harmonit_id": 9002, "descricao": "RASTREADOR ST310U",
                  "valor": 0.0}


async def _vinculo(nome):
    return CATALOGO.get(nome.strip().upper())


def _produto(modelo):
    m = str(modelo or "").upper()
    if m.startswith("ST340"):
        return PRODUTO_ST340
    if m.startswith("ST310U"):
        return PRODUTO_ST310U
    return None


def instalar_dubles(modelo_na_weso=None):
    """Nenhuma chamada sai desta máquina depois disto."""
    storage.buscar_vinculo_item = _vinculo
    storage.produto_do_modelo = _produto
    oos.storage.buscar_vinculo_item = _vinculo
    oos.storage.produto_do_modelo = _produto
    oos.eqp.modelo_da_placa = lambda placa: modelo_na_weso
    oos.eqp.serie_de = lambda seriais, placa: seriais.get(
        oos.eqp.chave(placa), "série não localizada")


def item(desc, qtd="1", valor="0,00", tipo="COMODATO"):
    return oos.ItemContrato(descricao=desc, quantidade=qtd,
                            valor_unitario=valor, comodato_ou_aquisicao=tipo)


def corpo(perfil, placas, itens, **extra):
    return oos.MontarInput(perfil=perfil, cliente_id=998063, termo="8800",
                           produto_servico_id=777, placas=placas,
                           itens=itens, **extra)


def placa(txt, veic="CAMINHAO", **extra):
    return oos.PlacaOS(placa=txt, veiculo=veic, **extra)


def descricoes(materiais):
    return [m["descricao"] for m in materiais]


async def montar(body, perfil_nome=None, **ctx):
    p = cfg.PERFIS[perfil_nome or body.perfil]
    resolvidos, pendentes, descartados = await oos.resolver_vinculos(body.itens)
    op_itens, fin_itens = oos.separar_itens(p, resolvidos)
    alocacao, _ = oos.alocar_itens_por_placa(op_itens, body.placas)
    return oos.montar(body, ctx.get("perfil_obj", p), alocacao, fin_itens,
                      resolvidos, ctx.get("seriais"), ctx.get("recipientes"),
                      ctx.get("dados")), resolvidos, pendentes, descartados


# ── 1. regra 4: a financeira lista sempre ────────────────────────────────────

async def teste_regra_4():
    print("\n1. Regra 4 — a financeira lista os itens SEMPRE")
    instalar_dubles()
    body = corpo("contrato_novo", [placa("AAA 0A00")], [
        item("RASTREADOR", "1", "480,00", "COMODATO"),
        item("TAXA DE ADESAO", "1", "0,00", "SERVICO"),
        item("CENTRAL 24H", "1", "89,90", "SERVICO"),
    ])
    ops, resolvidos, _, _ = await montar(body)
    fin = [o for o in ops if o.get("eh_financeira")]
    checar("gera exatamente 1 financeira", len(fin) == 1, f"veio {len(fin)}")
    d = descricoes(fin[0]["materiais"])
    checar("financeira LISTA o item de valor zero", "TAXA DE ADESAO" in d, d)
    checar("financeira lista o item com valor", "CENTRAL 24H" in d, d)
    # ⚠️ `.get` E NÃO `[...]`: quando a regra 4 é desfeita, o item some da
    # financeira e o acesso direto ESTOURA -- levando junto as outras 60
    # verificações, que passariam a não ser medidas. Teste que quebra diz menos
    # que teste que acusa.
    por_nome = {m["descricao"]: m for m in fin[0]["materiais"]}
    checar("item de valor zero vai com cobrar DESMARCADO",
           por_nome.get("TAXA DE ADESAO", {}).get("cobrar") is False,
           f"não achei o item na financeira: {d}")
    checar("item com valor vai com cobrar MARCADO",
           por_nome.get("CENTRAL 24H", {}).get("cobrar") is True,
           f"não achei o item na financeira: {d}")
    checar("comodato NUNCA vai para a financeira", "RASTREADOR" not in d, d)


# ── 2. regra 7: o nas_duas saiu ──────────────────────────────────────────────

async def teste_regra_7():
    print("\n2. Regra 7 — o `nas_duas` saiu; cada item pertence a um lado só")
    instalar_dubles()
    body = corpo("contrato_novo", [placa("AAA 0A00")], [
        item("RASTREADOR", "1", "480,00", "COMODATO"),
        item("CENTRAL 24H", "1", "89,90", "SERVICO"),
    ])
    ops, resolvidos, _, _ = await montar(body)
    checar("`nas_duas` não é sequer lido do vínculo",
           all("nas_duas" not in i for i in resolvidos),
           str(resolvidos))
    operacional = [o for o in ops if not o.get("eh_financeira")][0]
    d = descricoes(operacional["materiais"])
    checar("item de cobrança NÃO aparece na operacional",
           "CENTRAL 24H" not in d, d)
    checar("comodato aparece na operacional", "RASTREADOR" in d, d)
    checar("nenhuma cópia de valor zero do item de cobrança",
           sum(1 for m in operacional["materiais"]
               if m["descricao"] == "CENTRAL 24H") == 0)


# ── 3. a separação vem antes da alocação ─────────────────────────────────────

async def teste_separa_antes_de_alocar():
    print("\n3. A separação vem ANTES da alocação")
    instalar_dubles()
    p = cfg.PERFIS["contrato_novo"]
    itens = [
        {"descricao": "RASTREADOR", "harmonit_id": 1, "quantidade": 3,
         "valor_unitario": 480.0, "comodato": True, "cobrar": False},
        {"descricao": "CENTRAL 24H", "harmonit_id": 3, "quantidade": 3,
         "valor_unitario": 89.9, "comodato": False, "cobrar": True},
    ]
    op_itens, fin_itens = oos.separar_itens(p, itens)
    checar("operacional recebe só o comodato",
           descricoes(op_itens) == ["RASTREADOR"], descricoes(op_itens))
    checar("financeira recebe o que não é comodato",
           descricoes(fin_itens) == ["CENTRAL 24H"], descricoes(fin_itens))
    alocacao, _ = oos.alocar_itens_por_placa(
        op_itens, [placa("A"), placa("B"), placa("C")])
    todos = [m["descricao"] for lista in alocacao for m in lista]
    checar("a alocação por placa não distribui item de cobrança",
           "CENTRAL 24H" not in todos, todos)


# ── 4. regra 9: o seletor de modelo ──────────────────────────────────────────

async def teste_regra_9():
    print("\n4. Regra 9 — sem equipamento na WESO, o operador escolhe")
    instalar_dubles(modelo_na_weso=None)   # placa nasceu agora: sem rastreador

    escolhido = corpo("contrato_novo",
                      [placa("AAA 0A00", modelo_escolhido="ST340")],
                      [item("RASTREADOR", "1", "480,00", "COMODATO")])
    ops, _, _, _ = await montar(escolhido)
    operacional = [o for o in ops if not o.get("eh_financeira")][0]
    d = descricoes(operacional["materiais"])
    checar("modelo escolhido vira MATERIAL, vindo do de-para",
           "RASTREADOR ST340" in d, d)
    equip = [m for m in operacional["materiais"]
             if m["descricao"] == "RASTREADOR ST340"][0]
    checar("o equipamento entra como comodato", equip["comodato"] is True)
    checar("com o valor PATRIMONIAL do de-para", equip["valor_unitario"] == 480.0)
    checar("e nunca cobra", equip["cobrar"] is False)
    checar("a descrição da OS leva o modelo escolhido",
           "ST340" in operacional["descricao"], operacional["descricao"])

    sem = corpo("contrato_novo", [placa("AAA 0A00")],
                [item("RASTREADOR", "1", "480,00", "COMODATO")])
    ops2, _, _, _ = await montar(sem)
    op2 = [o for o in ops2 if not o.get("eh_financeira")][0]
    checar("sem escolha, a descrição leva o MARCADOR, não um modelo plausível",
           oos.eqp.MARCADOR_MODELO in op2["descricao"], op2["descricao"])
    checar("sem escolha, NÃO entra material de equipamento",
           "RASTREADOR ST340" not in descricoes(op2["materiais"]),
           descricoes(op2["materiais"]))


# ── 5. os dois estados ───────────────────────────────────────────────────────

async def teste_dois_estados():
    print("\n5. Os DOIS estados que produziam o mesmo texto")
    nascidas = {oos.eqp.chave("AAA 0A00")}
    checar("placa criada nesta rodada => nasceu agora",
           oos.motivo_sem_equipamento("AAA 0A00", nascidas, False)
           == oos.SEM_EQUIPAMENTO_NASCEU_AGORA)
    checar("placa antiga sem equipamento => sem equipamento",
           oos.motivo_sem_equipamento("BBB 0B00", nascidas, False)
           == oos.SEM_EQUIPAMENTO_SEM_REGISTRO)
    checar("falha de leitura VENCE, mesmo na placa que nasceu agora",
           oos.motivo_sem_equipamento("AAA 0A00", nascidas, True)
           == oos.SEM_EQUIPAMENTO_WESO_MUDA)
    recado = oos.RECADO_SEM_EQUIPAMENTO[oos.SEM_EQUIPAMENTO_WESO_MUDA]
    checar("o recado da falha de leitura cita a OS 16775", "16775" in recado)
    checar("os três estados têm recado próprio",
           len({oos.RECADO_SEM_EQUIPAMENTO[k] for k in
                (oos.SEM_EQUIPAMENTO_NASCEU_AGORA,
                 oos.SEM_EQUIPAMENTO_WESO_MUDA,
                 oos.SEM_EQUIPAMENTO_SEM_REGISTRO)}) == 3)


# ── 6. regra 10: novo titular vira duas OS ───────────────────────────────────

async def teste_regra_10():
    print("\n6. Regra 10 — novo titular vira DUAS OS")
    instalar_dubles(modelo_na_weso="ST340")
    body = corpo("transferencia_novo_titular",
                 [placa("AAA 0A00"), placa("BBB 0B00")], [
                     item("RASTREADOR", "2", "480,00", "COMODATO"),
                     item("TAXA DE ADESAO", "1", "150,00", "SERVICO"),
                 ])
    ops, _, _, _ = await montar(body)
    checar("gera exatamente 2 OS", len(ops) == 2, f"veio {len(ops)}")
    operacional = [o for o in ops if not o.get("eh_financeira")]
    financeira = [o for o in ops if o.get("eh_financeira")]
    checar("uma operacional e uma financeira",
           len(operacional) == 1 and len(financeira) == 1)
    d_op = descricoes(operacional[0]["materiais"])
    # 🚨 UMA LINHA DE EQUIPAMENTO POR PLACA, com o modelo que a WESO diz. O
    # vínculo trazia UM item com a quantidade do termo, e todas as placas
    # viravam o mesmo produto -- "RASTREADOR" cai sempre em ST310U.
    checar("a operacional leva o equipamento resolvido pela WESO",
           "RASTREADOR ST340" in d_op, d_op)
    checar("o item genérico do vínculo NÃO sobrevive",
           "RASTREADOR" not in d_op, d_op)
    checar("uma linha de equipamento POR PLACA, não uma para o termo",
           sum(1 for x in d_op if x == "RASTREADOR ST340") == 2, d_op)
    checar("a operacional NÃO leva item de cobrança (regra 7)",
           "TAXA DE ADESAO" not in d_op, d_op)
    d_fin = descricoes(financeira[0]["materiais"])
    checar("a financeira leva a cobrança", "TAXA DE ADESAO" in d_fin, d_fin)
    checar("a financeira NÃO leva comodato", "RASTREADOR" not in d_fin, d_fin)
    checar("a financeira usa o técnico do financeiro",
           financeira[0]["tecnico_id"] == cfg.FINANCEIRO_TECNICO_ID)
    checar("a financeira é sempre prioridade Normal",
           financeira[0]["prioridade_id"] == cfg.PRIORIDADE_NORMAL_ID)


# ── 7. regra 11: a híbrida do ressarcimento ──────────────────────────────────

async def teste_regra_11():
    print("\n7. Regra 11 — o ressarcimento é híbrido e NÃO tem comodato")
    instalar_dubles(modelo_na_weso="ST340")
    body = corpo("ressarcimento_sem_termo", [placa("AAA 0A00")],
                 [item("RASTREADOR", "1", "480,00", "COMODATO")],
                 valor_ressarcimento=1200.0)
    ops, _, _, _ = await montar(body)
    checar("gera UMA OS só", len(ops) == 1, f"veio {len(ops)}")
    o = ops[0]
    checar("marcada como híbrida", o.get("hibrida") is True)
    checar("nasce no Financeiro",
           o["situacao_id"] == cfg.SITUACAO_FINANCEIRO_ID)
    checar("com a técnica do financeiro",
           o["tecnico_id"] == cfg.FINANCEIRO_TECNICO_ID)
    checar("NENHUM item de comodato na híbrida",
           all(not m.get("comodato") for m in o["materiais"]),
           str(o["materiais"]))
    ress = [m for m in o["materiais"] if m["descricao"] == "RESSARCIMENTO"]
    checar("o item de ressarcimento entra com o valor digitado",
           len(ress) == 1 and ress[0]["valor_unitario"] == 1200.0, str(ress))
    checar("e com cobrar marcado, porque tem valor",
           ress and ress[0]["cobrar"] is True)

    zero = corpo("ressarcimento_sem_termo", [placa("AAA 0A00")], [])
    ops0, _, _, _ = await montar(zero)
    r0 = [m for m in ops0[0]["materiais"] if m["descricao"] == "RESSARCIMENTO"]
    checar("valor zero mantém cobrar DESMARCADO (regra 4, sem exceção)",
           r0 and r0[0]["cobrar"] is False, str(r0))
    checar("e a descrição diz SEM CUSTO com o motivo",
           "SEM CUSTO" in ops0[0]["descricao"], ops0[0]["descricao"])


# ── 8. regra 12: a substituição ──────────────────────────────────────────────

async def teste_regra_12():
    print("\n8. Regra 12 — a substituição gera a financeira no serviço 6967")
    # 🆕 RESOLVIDO PELO USUÁRIO EM 21/08. Até então este teste prendia o estado
    # PENDENTE: dois registros de nome idêntico no Harmonit (6967 e 54845), o id
    # em `None`, e a geração parando com 422. Ele escolheu o 6967, com valor
    # fixo e sem pergunta na tela.
    instalar_dubles(modelo_na_weso="ST340")
    body = corpo("substituicao",
                 [placa("AAA 0A00", placa_entrada="BBB 0B00",
                        veiculo_entrada="CARRO NOVO")],
                 [item("RASTREADOR", "1", "480,00", "COMODATO")])
    ops, _, _, _ = await montar(body)
    financeiras = [o for o in ops if o.get("eh_financeira")]
    checar("gera a OS financeira", len(financeiras) == 1,
           [o.get("rotulo") for o in ops])
    checar("2 OS operacionais por placa (retirada e instalação)",
           len([o for o in ops if not o.get("eh_financeira")]) == 2,
           [o.get("rotulo") for o in ops])
    taxa = [m for m in financeiras[0]["materiais"]
            if "local diferente" in (m.get("descricao") or "").lower()]
    checar("com o valor de 299,90",
           taxa and taxa[0]["valor_unitario"] == 299.90, str(taxa))
    checar("e marcado para cobrar", taxa and taxa[0]["cobrar"] is True)

    # 🚨 A GUARDA DO ID FIXO, que acompanha a escolha sem contradizê-la.
    # Id em código apodrece em silêncio -- 7 das 14 OS de manutenção ficaram
    # com `tipo = 55`, que não existe mais e ninguém viu.
    checar("some do catálogo → acusa",
           cfg.conferir_servico_de_substituicao([{"id": 1}]) is not None)
    checar("catálogo fora do ar NÃO vira aviso falso",
           cfg.conferir_servico_de_substituicao([]) is None)

    # 🚨 O VALOR VEM DO TERMO. Id e valor fixos em código apodrecem: foi assim
    # que 7 das 14 OS de manutenção ficaram com `tipo = 55`.
    escolhido = dict(cfg.PERFIS["substituicao"])
    escolhido["financeira_servico_id"] = 6967
    body2 = corpo("substituicao",
                  [placa("AAA 0A00", placa_entrada="BBB 0B00",
                         veiculo_entrada="CARRO NOVO")],
                  [item("RASTREADOR", "1", "480,00", "COMODATO")],
                  valor_substituicao=299.90, local_diferente=True)
    ops, _, _, _ = await montar(body2, perfil_obj=escolhido)
    operacionais = [o for o in ops if not o.get("eh_financeira")]
    checar("substituição gera 2 OS operacionais (retirada + instalação)",
           len(operacionais) == 2, f"veio {len(operacionais)}")
    checar("a retirada é da placa que sai",
           operacionais[0]["placa"] == "AAA 0A00")
    checar("a instalação é da placa que entra",
           operacionais[1]["placa"] == "BBB 0B00")
    fin = [o for o in ops if o.get("eh_financeira")][0]
    taxa = [m for m in fin["materiais"] if "SUBSTITUIÇÃO" in m["descricao"]]
    checar("a financeira ganha o item de substituição",
           len(taxa) == 1, descricoes(fin["materiais"]))
    checar("com o valor vindo do TERMO, não do código",
           taxa and taxa[0]["valor_unitario"] == 299.90, str(taxa))
    checar("marcado para cobrar", taxa and taxa[0]["cobrar"] is True)
    checar("e o texto diz qual local", taxa and "local diferente" in taxa[0]["descricao"])


# ── 9. rescisão: OS operacional E OS financeira ──────────────────────────────
#
# 🆕 DECISÃO DO USUÁRIO, 21/08: "rescisao tera OS OP e FIN, decisão nova do
# pessoal". É a regra 3 da spec 28, e ela REVERTE a decisão de 29/07 -- que
# mandava a cobrança embutida em cada OS de placa "porque é mais seguro assim",
# amarrada ao veículo que a gerou.
#
# ⚠️ O QUE MUDOU DE CONTEXTO: a aba nova tem etapa de conferência de placa, que
# a tela velha não tinha. Era ela que faltava para o agregado ser conferível.

async def teste_rescisao():
    print("\n9. Rescisão — OS operacional + OS financeira (decisão de 21/08)")
    instalar_dubles(modelo_na_weso="ST340")
    body = corpo("rescisao", [placa("AAA 0A00"), placa("BBB 0B00")], [
        item("TAXA DE ADESAO", "2", "150,00", "SERVICO"),
    ])
    ops, _, _, _ = await montar(body)
    financeiras = [o for o in ops if o.get("eh_financeira")]
    operacionais = [o for o in ops if not o.get("eh_financeira")]
    checar("gera UMA OS financeira agregada, por termo",
           len(financeiras) == 1, [o.get("rotulo") for o in ops])
    checar("e 1 OS operacional por placa",
           len(operacionais) == 2, f"veio {len(operacionais)}")
    d_op = descricoes(operacionais[0]["materiais"])
    checar("a cobrança NÃO vai mais na OS de placa",
           "TAXA DE ADESAO" not in d_op, d_op)
    d_fin = descricoes(financeiras[0]["materiais"])
    checar("ela vai na financeira", "TAXA DE ADESAO" in d_fin, d_fin)
    # A taxa mudou de lugar: era `ops[0]`, a OS de placa, e agora vive na
    # financeira agregada. O `cobrar` continua tendo de vir marcado -- item com
    # valor e sem comodato cobra, que é a regra 2 e não mudou.
    taxa = [m for m in financeiras[0]["materiais"]
            if m["descricao"] == "TAXA DE ADESAO"][0]
    checar("com o `cobrar` preservado", taxa["cobrar"] is True)


# ── 10. manutenção: não flega nada ───────────────────────────────────────────

async def teste_manutencao():
    print("\n10. Manutenção — não flega nada e não gera financeira")
    instalar_dubles(modelo_na_weso="ST340")
    body = corpo("manutencao_local", [placa("AAA 0A00")], [
        item("RASTREADOR", "1", "480,00", "COMODATO"),
        item("TAXA DE ADESAO", "1", "150,00", "SERVICO"),
    ])
    ops, _, _, _ = await montar(body)
    checar("nenhuma financeira",
           not any(o.get("eh_financeira") for o in ops))
    mats = ops[0]["materiais"]
    checar("nenhum item flega comodato",
           all(not m["comodato"] for m in mats), str(mats))
    checar("nenhum item flega cobrar",
           all(not m["cobrar"] for m in mats), str(mats))
    equip = [m for m in mats if m["descricao"] == "RASTREADOR ST340"]
    checar("o equipamento aparece como material, para o técnico saber",
           len(equip) == 1, descricoes(mats))
    checar("e ele também não flega nada",
           equip and not equip[0]["comodato"] and not equip[0]["cobrar"])


# ── 11. ordem dos materiais (regra 6, mantida) ───────────────────────────────

async def teste_ordem():
    print("\n11. Regra 6 — a ordem dos materiais na operacional")
    instalar_dubles(modelo_na_weso=None)
    body = corpo("contrato_novo", [placa("AAA 0A00")],
                 [item("RASTREADOR", "1", "480,00", "COMODATO")])
    ops, _, _, _ = await montar(body)
    d = descricoes(ops[0]["materiais"])
    checar("o serviço do cabeçalho vem primeiro, sem flag",
           d[0] == "SERVIÇO DO CABEÇALHO (sem flag)", d)
    checar("ENTREGA OS vem por último", d[-1] == "ENTREGA OS", d)
    checar("os itens alocados ficam no meio", "RASTREADOR" in d[1:-1], d)


# ── 11b. o valor patrimonial se herda, e zero é "não sei" ────────────────────

async def teste_valor_patrimonial():
    print("\n11b. O valor patrimonial se herda quando o de-para não tem")
    instalar_dubles(modelo_na_weso="ST310U")
    body = corpo("contrato_novo", [placa("AAA 0A00")],
                 [item("RASTREADOR", "1", "1.100,00", "COMODATO")])
    ops, _, _, _ = await montar(body)
    mats = ops[0]["materiais"]
    equip = [m for m in mats if m["descricao"] == "RASTREADOR ST310U"]
    checar("o equipamento do de-para entra", len(equip) == 1, descricoes(mats))
    # 🚨 Testar `is not None` nunca herdaria: o de-para devolve `row[2] or 0.0`,
    # entao vazio chega como 0.0. Foi assim que o ST310U saiu R$ 0,00 em 14/08.
    checar("de-para sem valor HERDA o valor do item do contrato",
           equip and equip[0]["valor_unitario"] == 1100.0, str(equip))
    checar("e continua comodato, sem cobrar",
           equip and equip[0]["comodato"] is True and equip[0]["cobrar"] is False)

    instalar_dubles(modelo_na_weso="ST340")
    body2 = corpo("contrato_novo", [placa("AAA 0A00")],
                  [item("RASTREADOR", "1", "1.100,00", "COMODATO")])
    ops2, _, _, _ = await montar(body2)
    e2 = [m for m in ops2[0]["materiais"] if m["descricao"] == "RASTREADOR ST340"]
    checar("quando o de-para TEM valor, ele vence o do contrato",
           e2 and e2[0]["valor_unitario"] == 480.0, str(e2))

    # 🚨 A F5 DEPENDE DESTA MARCA. É por ela que a liberação da série confirma
    # que o equipamento foi mesmo anexado antes de apagar o recipiente.
    checar("o equipamento carrega a marca interna `_equipamento`",
           e2 and e2[0].get("_equipamento") is True, str(e2))
    checar("e a marca NÃO está nos itens que vieram do vínculo",
           all(not m.get("_equipamento") for m in ops2[0]["materiais"]
               if m["descricao"] != "RASTREADOR ST340"))

    instalar_dubles(modelo_na_weso="ST310U")
    body3 = corpo("manutencao_local", [placa("AAA 0A00")],
                  [item("RASTREADOR", "1", "1.100,00", "COMODATO")])
    ops3, _, _, _ = await montar(body3)
    e3 = [m for m in ops3[0]["materiais"] if m["descricao"] == "RASTREADOR ST310U"]
    checar("na manutenção o equipamento vai com valor ZERO e sem flag",
           e3 and e3[0]["valor_unitario"] == 0.0
           and e3[0]["comodato"] is False, str(e3))


# ── 12. o recipiente duvidoso é descartado, com aviso ────────────────────────

async def teste_conferir_recipientes():
    print("\n12. Sem 'entrará' plausível, não inventa (14/08)")
    instalar_dubles()
    p = dict(cfg.PERFIS["upgrade"])
    body = corpo("upgrade", [placa("OOM 4131")], [])

    bons, avisos = oos.conferir_recipientes(body, p, {})
    checar("recipiente ausente é descartado", bons == {})
    checar("e vira aviso citando a placa derivada",
           avisos and "OOM4131-UPGRADE" in avisos[0], str(avisos))

    ch = oos.eqp.chave("OOM 4131")
    bons, avisos = oos.conferir_recipientes(
        body, p, {ch: {"ambiguo": ["OOM4131-UPGRADE", "OOM 4131-UPGRADE"],
                       "serie": "123"}})
    checar("recipiente ambíguo é descartado", bons == {})
    checar("e o aviso diz que ambiguidade não se resolve sozinha",
           avisos and "automática" in avisos[0], str(avisos))

    bons, avisos = oos.conferir_recipientes(
        body, p, {ch: {"descricao": "TERMO 7777", "serie": "123"}})
    checar("recipiente de OUTRA rodada é descartado", bons == {})
    checar("e o aviso diz que é de rodada anterior",
           avisos and "ANTERIOR" in avisos[0], str(avisos))

    bons, avisos = oos.conferir_recipientes(
        body, p, {ch: {"descricao": "TERMO 8800", "serie": None}})
    checar("recipiente sem série é descartado", bons == {})

    bons, avisos = oos.conferir_recipientes(
        body, p, {ch: {"descricao": "TERMO 8800", "serie": "007933914"}})
    checar("recipiente bom passa", ch in bons, str(bons))
    checar("e não gera aviso", avisos == [], str(avisos))

    # 🚨 O ACENTO. Os recipientes `-MANUT` da WESO estão gravados MANUTENCAO,
    # sem cedilha; o perfil escreve MANUTENCAO. Sem dobrar acento, TODA geração
    # de manutenção morreria.
    pm = dict(cfg.PERFIS["manutencao_troca"])
    bodym = corpo("manutencao_troca", [placa("OOM 4131")], [])
    bons, _ = oos.conferir_recipientes(
        bodym, pm, {ch: {"descricao": "MANUTENÇÃO", "serie": "1"}})
    checar("descrição com acento casa com a sem acento", ch in bons, str(bons))


# ── 13. cobrança zerada exige motivo ─────────────────────────────────────────

async def teste_aviso_cobranca():
    print("\n13. Cobrança sem valor exige motivo — nos dois caminhos")
    instalar_dubles()
    zerado = [{"descricao": "TAXA DE RETIRADA", "harmonit_id": 1,
               "quantidade": 1, "valor_unitario": 0.0, "comodato": False,
               "cobrar": True}]
    body = corpo("rescisao", [placa("AAA 0A00")], [])
    avisos = oos.aviso_cobranca_sem_motivo(body, cfg.PERFIS["rescisao"], zerado)
    checar("avisa na RESCISÃO, onde a financeira é embutida",
           len(avisos) == 1, str(avisos))
    com_motivo = corpo("rescisao", [placa("AAA 0A00")], [],
                       motivo_financeira_zero="acordo interno")
    checar("com motivo informado, não avisa",
           oos.aviso_cobranca_sem_motivo(
               com_motivo, cfg.PERFIS["rescisao"], zerado) == [])
    checar("manutenção não avisa, porque não tem financeira",
           oos.aviso_cobranca_sem_motivo(
               body, cfg.PERFIS["manutencao_local"], zerado) == [])


# ── 14. Tipo e Problema por NOME, não por id ─────────────────────────────────

async def teste_cabecalho_por_nome():
    print("\n14. Tipo e Problema por NOME contra a lista viva (14/08)")
    from fpsl_weso.painel.routers import operacoes_router as opr

    lista = {"/TipoOrdemServico/ObterListaTipoOrdemServico":
             [{"id": 4242, "descricao": "Solicitação de Cliente"}],
             "/Problema/ObterProblemas":
             [{"id": 5151, "descricao": "MANUTENCAO"}]}

    async def _ok(path):
        return lista[path]

    opr._lista_do_harmonit = _ok
    cab, avisos = await opr._resolver_cabecalho_por_nome(
        cfg.PERFIS["manutencao_local"])
    checar("resolve o Tipo pelo nome, ignorando o id do perfil",
           cab.get("tipo_id") == 4242, str(cab))
    checar("resolve o Problema pelo nome mesmo sem acento",
           cab.get("problema_id") == 5151, str(cab))
    checar("e não avisa quando resolveu", avisos == [], str(avisos))

    async def _mudo(path):
        return None

    opr._lista_do_harmonit = _mudo
    cab, avisos = await opr._resolver_cabecalho_por_nome(
        cfg.PERFIS["manutencao_local"])
    checar("lista muda NÃO trava a geração — usa o último id conhecido",
           cab.get("tipo_id") == cfg.PERFIS["manutencao_local"]["tipo_id"],
           str(cab))
    checar("mas avisa que usou o id velho", len(avisos) == 2, str(avisos))

    async def _sumiu(path):
        return [{"id": 1, "descricao": "OUTRA COISA"}]

    opr._lista_do_harmonit = _sumiu
    estourou = None
    try:
        await opr._resolver_cabecalho_por_nome(cfg.PERFIS["manutencao_local"])
    except HTTPException as exc:
        estourou = exc
    checar("nome que SUMIU da lista recusa a geração",
           estourou is not None and estourou.status_code == 400, f"{estourou}")

    # A financeira traz o próprio cabeçalho e não pode ser sobrescrita.
    ops = [{"eh_financeira": True, "problema_id": cfg.FINANCEIRO_PROBLEMA_ID,
            "tipo_id": cfg.TIPO_CONTRATO_ID},
           {"problema_id": 1, "tipo_id": 1}]
    body = corpo("manutencao_local", [placa("AAA 0A00")], [], problema_id=999)
    opr._aplicar_cabecalho(ops, cfg.PERFIS["manutencao_local"],
                           {"tipo_id": 4242, "problema_id": 5151}, body)
    checar("a financeira NÃO é tocada pelo cabeçalho",
           ops[0]["problema_id"] == cfg.FINANCEIRO_PROBLEMA_ID, str(ops[0]))
    checar("a operacional recebe o Tipo resolvido", ops[1]["tipo_id"] == 4242)
    checar("a escolha da tela vence nos perfis SEM TERMO",
           ops[1]["problema_id"] == 999, str(ops[1]))

    ops2 = [{"problema_id": 7457, "tipo_id": 76}]
    body2 = corpo("contrato_novo", [placa("AAA 0A00")], [], problema_id=999)
    opr._aplicar_cabecalho(ops2, cfg.PERFIS["contrato_novo"], {}, body2)
    checar("num CONTRATO a escolha da tela NÃO vence — manda o documento",
           ops2[0]["problema_id"] == 7457, str(ops2))


async def main():
    for t in (teste_regra_4, teste_regra_7, teste_separa_antes_de_alocar,
              teste_regra_9, teste_dois_estados, teste_regra_10,
              teste_regra_11, teste_regra_12, teste_rescisao,
              teste_manutencao, teste_ordem, teste_valor_patrimonial,
              teste_conferir_recipientes,
              teste_aviso_cobranca, teste_cabecalho_por_nome):
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
