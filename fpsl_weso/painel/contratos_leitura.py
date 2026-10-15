"""Leitura do termo para a Gestão de Contratos (`CTR_1.1`). 2026-10-13.

Transforma o que o `pdf_extractor` devolve em **eventos por placa**, que é o
que o `contratos_eventos` sabe aplicar. Só leitura: não grava, não consulta
Harmonit nem WESO.

🚨 EXISTE PARA NÃO TOCAR O `pdf_extractor` NEM A ABA OPERAÇÕES. Aquele arquivo
é lido por três telas, e a aba Operações é intocável por decisão dele. Daqui o
`pdf_extractor` só é **LIDO** (`extrair_campos`, `_ler_paginas`), exatamente
como o `operacoes_extracao.py` já faz desde 26/08.

🚨 MAPA DE PERFIS PRÓPRIO, E ISSO É O CRITÉRIO DA CASA: regra que muda entre as
telas se CLONA; infraestrutura sem regra se REUSA. O que a Operações faz com um
perfil é gerar OS; o que a CTR faz é decidir se a placa entra, sai ou é
rescindida. São regras diferentes sobre a mesma leitura. As CHAVES são as mesmas
da Operações de propósito, para o operador ler o mesmo vocabulário nas duas abas.

⚠️ O LAYOUT VAI EXPLÍCITO PARA O EXTRATOR. A Operações passa a própria chave
(`contrato_novo`) e o extrator só reconhece `cliente_novo` para decidir ficha
cadastral -- então `contrato_novo` cai no parser genérico sem ficha. Não é
defeito meu para corrigir ali (a aba é intocável), mas aqui eu digo o layout em
vez de herdar a diferença.
"""
import re

from .contratos_eventos import ASSINADO, ENTRA, HARMONIT, RESCINDE, SAI, UPGRADE, chave
from .pdf_extractor import _ler_paginas, extrair_campos

# perfil -> o que ele faz com a placa, e qual layout o extrator deve usar.
PERFIS = {
    "contrato_novo": {"label": "Contrato novo ou teste de tecnologia", "acao": ENTRA, "layout": "cliente_novo"},
    "aditivo": {"label": "Aditivo ou teste upgrade", "acao": ENTRA, "layout": "aditivo"},
    "rescisao": {"label": "Rescisão", "acao": RESCINDE, "layout": "rescisao"},
    "substituicao": {"label": "Substituição (troca de equipamento)", "acao": "PARES", "layout": "substituicao"},
    "transferencia_novo_titular": {"label": "Transferência — Novo titular", "acao": ENTRA, "layout": "transferencia_novo_titular"},
    "transferencia_antigo_titular": {"label": "Transferência — Antigo titular", "acao": RESCINDE, "layout": "transferencia_antigo_titular"},
    "upgrade": {"label": "Upgrade de tecnologia", "acao": UPGRADE, "layout": "upgrade"},
    "ressarcimento_com_termo": {"label": "Ressarcimento com termo", "acao": RESCINDE, "layout": "rescisao"},
}

# ⚠️ FICAM DE FORA, E A TELA DIZ POR QUÊ -- `M12`: tela que promete o que não
# faz é defeito. Manutenção e ressarcimento sem termo NÃO nascem de documento
# (`sem_termo` na Operações), então não há termo assinado para subir aqui. A
# transferência no modelo novo tem leitor próprio na Operações e junta rescisão
# e entrada no mesmo papel: entra quando for tarefa dela, não por chute.
PERFIS_FORA = {
    "manutencao_local": "não nasce de documento",
    "manutencao_troca": "não nasce de documento",
    "ressarcimento_sem_termo": "não nasce de documento",
    "transferencia_termo_novo": "modelo novo, leitor próprio — ainda não suportado na Gestão de Contratos",
}

# A vaga que o extrator cria quando o termo assinado traz "A DEFINIR".
_VAGA_RE = re.compile(r"^A_DEFINIR_(.+)$")

# Anotação de troca de placa no PDF do Harmonit. Medida nos 53 termos que a
# auditoria de 13/10 encontrou com esse padrão, em 43 clientes.
_TROCA_RE = re.compile(r"(?i)(pediu|solicit|altera[cç][aã]o|alterad|troca|trocou|substitu[ií]d"
                       r"|placa correta|anterior assinada)")
_PLACA_NA_LINHA = re.compile(r"\b[A-Z]{3} ?-?\d[A-Z0-9]\d{2}\b")
# ⚠️ O QUE NÃO É ANOTAÇÃO DE TROCA, e por isso sai: "Sem Alteração" é rótulo de
# coluna em termo de migração, e linha de taxa/valor/cláusula fala de troca sem
# trocar nada. Sem este filtro a varredura deu 63 linhas, 10 delas ruído.
_TROCA_NAO = re.compile(r"(?i)sem altera|bloqueio|taxa|valor|R\$|cl[aá]usula|ve[ií]culos que (sair|entrar)")


def eh_vaga(placa) -> str | None:
    """Devolve o número do termo quando a 'placa' é a vaga do `A DEFINIR`.

    🚨 ISTO É O ELO QUE A AUDITORIA NÃO TINHA. O extrator já troca "A DEFINIR"
    por `A_DEFINIR_<termo>` e sugere o apelido `TERMO:<termo>` -- e é por isso
    que a WESO tem veículos chamados `TERMO 8396`: são vagas esperando placa.
    A auditoria procurava a expressão "a definir" no texto do PDF e por isso
    casava "a definição" das cláusulas; o dado estruturado não erra.
    """
    m = _VAGA_RE.match(str(placa or "").strip())
    return m.group(1) if m else None


def _placas_do_campo(campos, lista, chave_placa) -> list:
    out = []
    for v in campos.get(lista) or []:
        if isinstance(v, dict) and (v.get(chave_placa) or "").strip():
            out.append(v)
    return out


# 🚨 AMPLIADO EM 14/10, POR DECISÃO DELE, E PORQUE A VERSÃO ESTREITA ERA QUASE
# INERTE. A primeira regra procurava "mensalidade|monitoramento|locação|plano" e
# o item real do termo da 2HM é **"PACOTE FULL MANAGER ... Mensal"** -- não
# casava, e nenhuma placa recebia valor. Medir antes de prometer: o extrator já
# entrega `valor_unitario` por item (tratando valor riscado), mas o vocabulário
# do documento não é o que eu supus.
_MENSALIDADE_RE = re.compile(
    r"(?i)mensalidade|mensal|monitoramento|locac|loca[çc][aã]o|plano|"
    r"pacote|full\s*manager|gestor")

# 🚨 O QUE SE PAGA UMA VEZ SÓ NÃO É MENSALIDADE, e isto foi medido no termo
# 2207 da 2HM: a regra ampliada pegou **dois** itens -- `PACOTE FULL MANAGER`
# (75,26, que é a mensalidade) e `Equipamento rastreador telemetria avançada`
# (999,90, que é a VENDA do aparelho). Com dois candidatos, nenhuma placa
# recebia valor; sem a exclusão, a cobrança poderia sair com o preço do
# equipamento no lugar da mensalidade -- 13× o valor certo.
_NAO_MENSAL_RE = re.compile(
    r"(?i)ades[ãa]o|taxa|equipamento|instalac|instala[çc][ãa]o|aquisic|aquisi[çc][ãa]o|"
    r"retirada|aviso\s*pr[eé]vio|multa|ressarcimento|frete|cadastro|desinstalac")


def valor_das_placas(itens, eventos) -> dict:
    """Liga o valor do termo às placas — **só quando não há dúvida**.

    🚨 O VALOR DO TERMO NÃO É POR PLACA, E ISSO É LIMITE DO DOCUMENTO, NÃO DO
    CÓDIGO. O `pdf_extractor` entrega os itens de serviço (`descricao`,
    `quantidade`, `valor_unitario`, já tratando valor riscado por
    `_valor_ativo`), e um termo com 12 placas e um item "MENSALIDADE" não diz
    quanto é de cada veículo. Decisão dele (13/10, repetida em 14/10): **o
    valor vem do termo** -- então o que é inequívoco entra, e o resto vira
    pergunta na tela, com o motivo escrito.

    Inequívoco é um destes dois casos:
      1. o termo tem **uma** placa que entra e **um** item de mensalidade;
      2. a descrição do item **nomeia** a placa.

    ⚠️ Ratear o total pelas placas seria inventar número, e número inventado em
    cobrança é pior que número faltando: a CAR emitiria em cima dele.
    """
    cobraveis = [e for e in eventos if e.get("acao") in (ENTRA, UPGRADE) and (e.get("placa") or "").strip()]
    candidatos = [i for i in (itens or [])
                  if isinstance(i, dict) and (i.get("valor_unitario") or "").strip()
                  and _MENSALIDADE_RE.search(str(i.get("descricao") or ""))
                  and not _NAO_MENSAL_RE.search(str(i.get("descricao") or ""))]

    por_placa, aviso = {}, None

    # Caso 2 primeiro: item que nomeia a placa é mais forte que contagem.
    for i in candidatos:
        desc = str(i.get("descricao") or "").upper()
        for e in cobraveis:
            alvo = (e.get("placa") or "").strip().upper()
            if alvo and alvo in desc:
                por_placa[e["placa"]] = i["valor_unitario"]

    if not por_placa and len(cobraveis) == 1 and len(candidatos) == 1:
        por_placa[cobraveis[0]["placa"]] = candidatos[0]["valor_unitario"]

    # 🚨 CASO 3 (decisão dele, 14/10): **um** item mensal cuja QUANTIDADE é igual
    # ao número de placas do termo. Aí o `valor_unitario` é o preço POR VEÍCULO
    # que o documento declara -- medido no termo da 2HM, onde a coluna Qtd traz
    # 16 para 16 placas e 01 para 1.
    # ⚠️ ISTO NÃO É RATEIO. Rateio seria dividir um total pelas placas, e aí o
    # número sairia de nós; aqui ele sai do documento. A diferença importa
    # porque a futura Contas a Receber emite em cima disto.
    if not por_placa and len(candidatos) == 1 and cobraveis:
        qtd = (candidatos[0].get("quantidade") or "").strip()
        digitos = re.sub(r"\D", "", qtd)
        if digitos and int(digitos) == len(cobraveis):
            for e in cobraveis:
                por_placa[e["placa"]] = candidatos[0]["valor_unitario"]

    faltam = [e["placa"] for e in cobraveis if e["placa"] not in por_placa]
    if faltam and candidatos:
        aviso = ("o termo tem valor, mas por item de serviço e não por veículo: "
                 f"{len(faltam)} placa(s) ficam sem valor ({', '.join(faltam[:5])}"
                 f"{' ...' if len(faltam) > 5 else ''}). Confirmar antes de cobrar.")
    elif faltam and not candidatos:
        aviso = "o documento não trouxe item de mensalidade — nenhuma placa recebeu valor."

    return {"itens": list(candidatos), "por_placa": por_placa, "sem_valor": faltam, "aviso": aviso}


def ler(fonte, perfil: str, fonte_evento: str = ASSINADO) -> dict:
    """Lê o termo e devolve os eventos que ele produz, sem gravar nada.

    `fonte` é caminho ou objeto tipo arquivo. `fonte_evento` diz de qual versão
    do documento esta leitura veio: `assinado` (Clicksign) ou `harmonit`.
    """
    if perfil in PERFIS_FORA:
        raise ValueError(f"{perfil}: {PERFIS_FORA[perfil]}")
    if perfil not in PERFIS:
        raise ValueError(f"perfil desconhecido: {perfil!r}")

    p = PERFIS[perfil]
    campos = extrair_campos(fonte, p["layout"])
    campos.pop("texto_bruto", None)

    eventos, vagas, avisos = [], [], []

    def _add(acao, reg, chave_placa, recursos=None):
        placa = (reg.get(chave_placa) or "").strip()
        vaga = eh_vaga(placa)
        if vaga:
            # Vaga não vira evento: ninguém entra no contrato sem placa. Ela
            # marca o termo como `a_definir`, e a placa real chega depois pelo
            # PDF do Harmonit.
            vagas.append({"termo": vaga, "acao": acao, "apelido_sugerido": reg.get("apelido_sugerido")})
            return
        eventos.append({"acao": acao, "placa": placa, "fonte": fonte_evento,
                        "recursos": recursos,
                        "convencional": reg.get("placa_convencional", True)})

    if p["acao"] == "PARES":
        for par in campos.get("pares") or []:
            if not isinstance(par, dict):
                continue
            if (par.get("placa_saida") or "").strip():
                _add(SAI, par, "placa_saida")
            if (par.get("placa_entrada") or "").strip():
                _add(ENTRA, par, "placa_entrada", recursos=par.get("acessorios_entrada") or None)
        if not eventos and not vagas:
            avisos.append("a substituição não trouxe nenhum par de placas")
    else:
        for reg in _placas_do_campo(campos, "placas", "placa"):
            _add(p["acao"], reg, "placa")
        if not eventos and not vagas:
            avisos.append("o termo não trouxe nenhuma placa")

    # 🚨 VEÍCULO SEM PLACA VAI PARA A TELA, NUNCA PARA O LIXO. Regra que já
    # existe no FPSL: no termo 8800 eram 2 de 11, e a diferença entre
    # "9 veículos" e "11 veículos, 2 sem placa" é quem nota que falta algo.
    sem_placa = campos.get("veiculos_sem_placa") or []
    if sem_placa:
        avisos.append(f"{len(sem_placa)} veículo(s) sem placa no documento — precisam de revisão humana")

    nao_convencionais = [e["placa"] for e in eventos if not e.get("convencional", True)]
    if nao_convencionais:
        avisos.append("identificador não convencional (chassi/série): " + ", ".join(nao_convencionais[:5]))

    # ⚠️ RESCISÃO NÃO TRAZ CNPJ, E ISSO JÁ ESTÁ MEDIDO: o layout dela só tem o
    # NOME do cliente (achado da Operações nos termos 8788 e 8842). Então a
    # tela PERGUNTA o cliente em vez de adivinhar -- cliente errado grava
    # evento no contrato de outra empresa, e foi isso que a auditoria achou em
    # 33 documentos com CNPJ divergente.
    cnpj = re.sub(r"\D", "", campos.get("cnpj") or campos.get("cpf") or "") or None
    if not cnpj:
        avisos.append("o documento não traz CNPJ/CPF — confirmar o cliente na tela antes de gravar")

    # 🆕 G4: o valor que o termo diz, ligado à placa só quando não há dúvida.
    # O evento recebe `valor_mensal`, e é daí que `gravar()` já alimenta o
    # `contrato_item` -- nenhuma mudança no gravador foi necessária.
    valores = valor_das_placas(campos.get("itens"), eventos)
    for e in eventos:
        if e.get("placa") in valores["por_placa"]:
            e["valor_mensal"] = valores["por_placa"][e["placa"]]
    if valores["aviso"]:
        avisos.append(valores["aviso"])

    return {
        "perfil": perfil,
        "tipo": p["label"],
        "numero": str(campos.get("termo") or "").strip() or None,
        "cnpj": cnpj,
        "cliente_nome_sugerido": campos.get("cliente_nome_sugerido"),
        "a_definir": bool(vagas),
        "vagas": vagas,
        "eventos": eventos,
        "itens": campos.get("itens") or [],
        "valores": valores,
        "termo_relacionado": campos.get("termo_relacionado"),
        "alerta_transferencia": campos.get("alerta_transferencia"),
        "avisos": avisos,
        "veiculos_sem_placa": sem_placa,
    }


def troca_registrada(fonte) -> str | None:
    """A anotação de troca de placa no PDF do Harmonit, ou `None`.

    🚨 REGRA DELE (13/10): *"se o termo X está assinado e o cliente pediu a
    troca e está registrado no Harmonit, está certo"*. O caso é a Maxi Confort
    8872 -- o Harmonit acrescenta `FAC 5H30` com *"Cliente Fernanda Rodrigues
    pediu alteração da placa no dia 30/09/2026 via Movizap"* e não tira a
    antiga. Esta função devolve a frase, para a tela mostrar o motivo em vez de
    o operador confiar num `True`.

    ⚠️ LÊ O TEXTO INTEIRO, não o `texto_bruto` do extrator: aquele vem cortado
    em 3.000 caracteres e a anotação mora no fim da tabela de veículos.
    """
    for pagina in _ler_paginas(fonte):
        for linha in (pagina.get("texto") or "").splitlines():
            s = re.sub(r"\s+", " ", linha).strip()
            if _PLACA_NA_LINHA.search(s) and _TROCA_RE.search(s) and not _TROCA_NAO.search(s):
                return s[:300]
    return None
