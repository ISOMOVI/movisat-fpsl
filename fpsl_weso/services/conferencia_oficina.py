"""Conferência da oficina: o que a OS diz × o que a WESO diz.

🔵 Nasceu do pedido dele em 01/10: *"verifique na rotina de historico de OS, que
nas buscas dele (mesmo que seja outra aba dento) verificar se o ID weso e modelo
batem com os da OS"*. Só LÊ -- nada aqui escreve em sistema nenhum.

🚨 TRÊS REGRAS DESTE MÓDULO FORAM MEDIDAS, NÃO SUPOSTAS (01/10, 197 OS com
oficina no `os_historico`):

1. **Quem prevê a ação é o `problema`, NÃO o `tipo`.** Ele disse isso desde o
   começo e eu o "corrigi" errado com base em 3 OS. Nas 197, o `tipo` mais comum
   é o **2 "Contrato" (64 OS)**, que não diz ação nenhuma; os genéricos 1782-1784
   somam 30. O `problema` prevê em todos os grupos.

2. **O material da OS reflete o equipamento que ENTRA**; quando nada entra
   (retirada pura), reflete o que sai. Medido: a OS 16914 tem material `20314`,
   entra `20314` e sai `7004` -- o material acompanhou quem entrou. A 16818 idem
   (`338502` entra, `20314` sai). As retiradas (16959-16963) têm material igual
   ao que saiu, porque nada entrou.

3. **Rastreador NÃO se reconhece por texto.** `operacoes_os.eh_rastreador()`
   procura "RASTREADOR" na descrição e **não acha** `ST310U`, `ST340RB`,
   `RST-MINI`, `TK 100`, `XT40 - OBDII`, `ST8300 (SKD)` -- 9 das 24 descrições do
   de-para. A OS 16962 é exatamente esse furo. Aqui o critério é o `idProduto`
   estar entre os ids do de-para `painel_modelos_produto`.

⚠️ NADA AQUI IMPORTA DE `painel/operacoes_*`. As duas constantes de situação e o
carregador do cache são **copiados com origem anotada**, como o próprio projeto
faz entre os clones (ver o aviso em `operacoes_equipamentos.py:31-50`). A aba
Operações é intocável por decisão dele.
"""
import logging
import sys

logger = logging.getLogger("fpsl.conferencia_oficina")

ACAO_INSTALACAO = 1       # `oficina[].status` 1
ACAO_DESINSTALACAO = 2    # `oficina[].status` 2

# Copiadas de `painel/operacoes_equipamentos.py:646` (não importadas: ver topo).
SITUACAO_LIVRE = "Estoque"
SITUACAO_PRESA = "Instalado"

# Situação da WESO que não é nem livre nem presa. Medido no cache em 01/10
# (3.803 rastreadores): Bancada 210 · Manutenção 206 · Cliente (Comodato) 38 ·
# Irrecuperável 21. 🚨 Não é erro: é "saiu da placa mas não está disponível", e
# vira CINZA com o nome da situação. Tratar como vermelho acusaria 475 falsos.
SITUACOES_INTERMEDIARIAS = {"Bancada", "Manutenção", "Cliente (Comodato)", "Irrecuperável"}

# ── O `problema` da OS prevê a ação (medido em 197 OS, 01/10) ────────────────
# Catálogo `/Problema/ObterProblemas`, empresaId 98. O número entre parênteses é
# quantas OS com oficina daquele problema foram medidas.
PROBLEMA_DESINSTALA = {
    7421,   # RETIRADA (18)
    7502,   # RESCISÃO (44)
    7471,   # SUBSTITUIÇÃO/RETIRADA (28)
    7524,   # RESSARCIMENTO (3)
}
PROBLEMA_INSTALA = {
    7372,   # ADITIVO (31)
    7457,   # CONTRATO NOVO (6)
    7472,   # SUBSTITUIÇÃO/INSTALAÇÃO (23)
    7433,   # INSTALAÇÃO (3)
    7678,   # REINSTALAÇÃO (1)
}
# Problema que legitimamente tem as duas ações, ou uma ou outra conforme o caso.
# Não se julga: mostra-se.
PROBLEMA_MISTO = {
    7474,   # TRANSFERÊNCIA DE TITULARIDADE (13) -- 5 entram, 5 saem, 2 trocam
    7484,   # UPGRADE PLANO DO SISTEMA (5)
    7612,   # UPGRADE 4G (6)
    7384,   # MANUTENÇÃO (17) -- 11 são troca
    7485,   # TESTE GRATUITO (2)
    7518,   # CORREÇÃO SISTÊMICA (1)
}
# Transferência muda o DONO, não o equipamento: o rastreador fica no carro.
PROBLEMA_TRANSFERENCIA = {7474}

# Copiado de `painel/operacoes_equipamentos.py` (`MODELO_COM_RFID`), não
# importado. "ST340 com leitor RFID é ST340RB" -- a WESO não tem campo de
# acessório, então registra ST340 puro, e a OS cobra ST340RB. Medido em 01/10:
# a OS 16836 tem `LEITOR RFID (404)` nos materiais, a WESO diz ST340 e a OS lança
# ST340RB (27241). Sem esta regra, ela sairia como divergência de modelo.
MODELO_COM_RFID = {"SUNTECH ST340": "SUNTECH ST340RB"}


def tem_leitor_rfid(materiais: list) -> bool:
    """Mesmo critério de `operacoes_equipamentos.tem_leitor_rfid`."""
    return any("RFID" in str(m.get("descricao") or "").upper() for m in materiais or [])

OK = "ok"
DIVERGENTE = "divergente"
INDEFINIDO = "indefinido"
SEM_REGRA = "sem_regra"

CACHE_DIR = "/home/claude/weso_cache"


def carregar_cache():
    """O cache da WESO (leitura, `mode=ro`), ou `None` se não der.

    Copiado de `painel/operacoes_equipamentos.py:145` -- mesmo desenho, de
    propósito: **nunca levanta**. Sem cache a conferência fica indefinida, que é
    um veredito honesto; derrubar a tela não é."""
    try:
        if CACHE_DIR not in sys.path:
            sys.path.insert(0, CACHE_DIR)
        import cache                                    # noqa: PLC0415
        return cache
    except Exception:
        logger.warning("conferencia_oficina: cache da WESO indisponível")
        return None


def acao_esperada(problema) -> str:
    """O que o `problema` da OS prevê: `instalacao`, `desinstalacao`, `misto`
    ou `sem_regra` (problema 0, nulo ou fora do catálogo medido)."""
    if problema in PROBLEMA_DESINSTALA:
        return "desinstalacao"
    if problema in PROBLEMA_INSTALA:
        return "instalacao"
    if problema in PROBLEMA_MISTO:
        return "misto"
    return SEM_REGRA


def situacao_esperada(acao) -> str | None:
    """Só informativo, para a tela mostrar o que seria o estado "limpo".

    🚨 **NÃO é o critério do veredito** -- ver `_veredito_vinculo`."""
    if acao == ACAO_INSTALACAO:
        return SITUACAO_PRESA
    if acao == ACAO_DESINSTALACAO:
        return SITUACAO_LIVRE
    return None


def _veredito_vinculo(acao, serial_id, veiculo, placa_da_os,
                      situacao=None, placa_atual_da_serie=None,
                      os_posterior=None) -> tuple[str, str]:
    """A pergunta é **"o rastreador ainda está NAQUELA placa?"**, não "está em
    Estoque?".

    🚨 ESTA REGRA SUBSTITUIU UMA ERRADA MINHA, E OS DADOS DERRUBARAM (01/10).
    Eu comparava a situação atual com a esperada: retirada deveria dar `Estoque`.
    Resultado: **46 das 199 OS (23%) acusadas de divergência**. Amostrando 8
    delas contra o vínculo real do cache, **5 eram REUSO** -- o rastreador foi
    retirado daquela placa e depois instalado em OUTRA, o que é o ciclo normal e
    prova que a retirada funcionou. Só 3 eram defeito de verdade (o rastreador
    seguia na MESMA placa da OS).

    Exemplos medidos: a OS 16972 retirou o `907112547` da `EPW 0I21` e hoje ele
    está na `GKD 3D08` -- retirada OK. A 16940 retirou o `007933269` da
    `DOT 0C95` e ele **continua na `DOT 0C95`** -- aí sim não refletiu.

    Uma tela que grita 46 vezes e acerta 3 perde a credibilidade inteira, e
    quem a usa passa a ignorar o vermelho que importa.
    """
    if acao not in (ACAO_INSTALACAO, ACAO_DESINSTALACAO):
        return INDEFINIDO, "ação da oficina não é instalação nem desinstalação"
    if serial_id is None:
        return INDEFINIDO, "série não está na WESO"

    # 🚨 O ESTADO DE HOJE SÓ JULGA A ÚLTIMA OS QUE MEXEU NA SÉRIE. Esta tela olha
    # OS de meses atrás contra a WESO de agora. Se uma OS POSTERIOR tocou a mesma
    # série, o que a WESO mostra hoje é efeito DAQUELA -- julgar esta por ela
    # seria acusar o passado pelo que veio depois.
    if os_posterior:
        return INDEFINIDO, f"série mexida depois na OS {os_posterior}"

    atual = _como_veiculo(placa_atual_da_serie)
    na_placa = (veiculo is not None and veiculo.get("rastreador_id") == serial_id) \
        or mesmo_veiculo(placa_da_os, atual)
    onde = f"; a série está hoje em {atual['placa']!r}" if atual else ""

    if acao == ACAO_INSTALACAO:
        if na_placa:
            return OK, ""
        if veiculo is None:
            return DIVERGENTE, f"instalou na placa {placa_da_os!r}, que não existe na WESO{onde}"
        return DIVERGENTE, f"instalou mas a placa {placa_da_os!r} não tem esta série na WESO{onde}"

    # desinstalação
    if na_placa:
        return DIVERGENTE, f"desinstalou mas a série segue na placa {placa_da_os!r} na WESO"
    # 🚨 RASTREADOR PRESO: a série saiu da placa, mas a WESO a dá como
    # `Instalado` sem veículo nenhum -- a liberação não terminou. É o padrão
    # documentado em `docs/fpsl/29_Rastreador_Preso_Harmonit.md` (do lado do
    # Harmonit; aqui é o espelho na WESO). Medido em 01/10: 1 caso em 102.
    if situacao == SITUACAO_PRESA and atual is None:
        return DIVERGENTE, "série saiu da placa mas segue 'Instalado' sem veículo (rastreador preso)"
    # ⚠️ Placa que SUMIU da WESO numa desinstalação é o caminho normal: a
    # retirada exclui o veículo. Medido em 01/10: das 102 desinstalações com a
    # placa fora da WESO, 73 tinham a série em Estoque e 26 reusada em outra
    # placa -- todas retiradas que funcionaram.
    return OK, ""


def _norm(s) -> str:
    """Identificador de veículo comparável: maiúsculo, só letra e número, sem os
    rótulos que o projeto pendura na frente (`(RD)`, `CHASSI:`)."""
    t = str(s or "").upper().replace("(RD)", "")
    t = "".join(ch for ch in t if ch.isalnum())
    return t[6:] if t.startswith("CHASSI") else t


def _como_veiculo(v) -> dict | None:
    """Aceita placa (texto) ou `{placa, chassi}`, devolve sempre o dict."""
    if not v:
        return None
    if isinstance(v, str):
        return {"placa": v, "chassi": None}
    return v


def mesmo_veiculo(placa_da_os, veiculo_atual) -> bool:
    """A OS e a WESO apontam para o MESMO carro, mesmo escritos diferente?

    Medido em 01/10, os dois jeitos que produziam divergência falsa:

    - **chassi com e sem rótulo**: a OS 16712 grava `9BWKL45U5VP010644` e a WESO
      tem `CHASSI: 9BWKL45U5VP010644` -- é o mesmo chassi. E quando a OS grava o
      chassi e a WESO já tem a placa, a coluna `chassi` do veículo no cache prova
      que é o mesmo carro, em vez de supor;
    - **`(RD)`**: a OS 16517 grava `OWE 0I25` e a WESO tem `(RD) OWE 0I25`. RD é
      a convenção do projeto para o rastreador redundante, com placa-chave
      própria -- é o mesmo carro.

    🚨 Não julga FORMATO de placa (`reference_placa_identificador`): só compara
    os dois identificadores depois de tirar os rótulos conhecidos.
    """
    if not veiculo_atual:
        return False
    a = _norm(placa_da_os)
    if not a:
        return False
    if a in (_norm(veiculo_atual.get("placa")), _norm(veiculo_atual.get("chassi"))):
        return True
    # 🚨 A WESO GUARDA O CHASSI NA DESCRIÇÃO quando a coluna `chassi` está vazia
    # -- medido em 01/10: só 250 dos 1.940 veículos têm a coluna preenchida. A OS
    # 16900 grava `CHASSI: 9BM951500TB474833` e o veículo `UEX 5E41` tem
    # exatamente isso na descrição. ⚠️ Só para identificador LONGO (cara de
    # chassi, ≥ 10): uma placa de 7 caracteres casaria por acaso dentro de texto
    # livre como "FIAT/MOBI TREKKING...".
    return len(a) >= 10 and a in _norm(veiculo_atual.get("descricao"))


def produtos_rastreador_da_os(materiais: list, ids_de_para: set) -> set:
    """Os `idProduto` dos materiais que SÃO rastreador -- pelo de-para, nunca
    por texto (ver regra 3 no topo)."""
    return {m.get("idProduto") for m in materiais or []
            if m.get("idProduto") in ids_de_para}


def conferir_os(os_linha: dict, de_para: dict, rastreador_por_serial,
                veiculo_por_placa=None, placa_do_rastreador=None,
                ultima_os_do_serial: dict | None = None) -> dict:
    """Confere uma OS. Puro: recebe o de-para e os buscadores, não vai ao banco.

    `de_para`: {modelo_weso em MAIÚSCULA: harmonit_produto_id}
    `rastreador_por_serial`: callable(serial) -> dict|None (`id`/`modelo`/`situacao`)
    `veiculo_por_placa`: callable(placa) -> dict|None (`rastreador_id`)
    `placa_do_rastreador`: callable(id do rastreador) -> placa|None -- onde a série
        está HOJE; serve para dizer "está em X" e para achar rastreador preso
    `ultima_os_do_serial`: {serial: maior numero_os com oficina daquela série}
    """
    ultima_os_do_serial = ultima_os_do_serial or {}
    problema = os_linha.get("problema")
    oficinas = os_linha.get("oficinas") or []
    materiais = os_linha.get("materiais") or []
    ids_de_para = set(de_para.values())
    prev = acao_esperada(problema)
    com_rfid = tem_leitor_rfid(materiais)

    # 🚨 MESMA SÉRIE, MESMA PLACA, MAIS DE UMA AÇÃO NA MESMA OS: vale a ÚLTIMA, e
    # "última" é o maior `id` da linha de oficina -- não a ordem do array, e não
    # "a saída" por suposição. Medido em 01/10: a OS 16460 INSTALOU, RETIROU e
    # INSTALOU DE NOVO a mesma série (ids 198094 -> 202562 -> 202563). Se eu
    # assumisse "vale a saída", ela sairia como retirada, o oposto do que é.
    # As linhas anteriores ficam marcadas e não entram em nenhum veredito.
    ultima_do_par = {}
    for i, of in enumerate(oficinas):
        chave = (str(of.get("equipamentoId") or "").strip(), _norm(of.get("veiculoPlaca")))
        ordem = of.get("id") if isinstance(of.get("id"), int) else i
        if chave not in ultima_do_par or ordem > ultima_do_par[chave][0]:
            ultima_do_par[chave] = (ordem, i)
    vigentes = {pos for _, pos in ultima_do_par.values()}

    status_os = os_linha.get("status_str")
    linhas, acoes = [], set()
    for pos, of in enumerate(oficinas):
        serial = str(of.get("equipamentoId") or "").strip()
        placa = of.get("veiculoPlaca")
        acao = of.get("status")
        anulada = pos not in vigentes
        if not anulada:
            acoes.add(acao)
        r = rastreador_por_serial(serial) if serial else None
        modelo = (r or {}).get("modelo")
        situacao = (r or {}).get("situacao")
        chave_modelo = (modelo or "").strip().upper()
        if com_rfid:
            chave_modelo = MODELO_COM_RFID.get(chave_modelo, chave_modelo)
        produto = de_para.get(chave_modelo)
        veic = veiculo_por_placa(placa) if (veiculo_por_placa and placa) else None
        rid = (r or {}).get("id")
        placa_hoje = placa_do_rastreador(rid) if (placa_do_rastreador and rid) else None
        ult = ultima_os_do_serial.get(serial)
        posterior = ult if (ult and os_linha.get("numero_os")
                            and ult > os_linha["numero_os"]) else None
        v_sit, motivo_sit = _veredito_vinculo(
            acao, rid, veic, placa, situacao=situacao,
            placa_atual_da_serie=placa_hoje, os_posterior=posterior)

        if anulada:
            v_sit, motivo_sit = INDEFINIDO, "superada por outra ação na mesma OS -- vale a última"
        # 🚨 TRANSFERÊNCIA DE TITULARIDADE: o rastreador FICA no carro, muda só o
        # dono. "Desinstalou e segue na placa" é o resultado esperado. Medido: a OS
        # 16510 (27 desinstalações) tinha 26 nesse estado e nenhuma estava errada.
        # O que mudaria numa transferência é o CLIENTE do veículo na WESO, que o
        # vínculo placa×série não mede.
        elif (v_sit == DIVERGENTE and acao == ACAO_DESINSTALACAO
              and problema in PROBLEMA_TRANSFERENCIA and "segue na placa" in motivo_sit):
            v_sit, motivo_sit = INDEFINIDO, (
                "transferência de titularidade: o rastreador fica no veículo, muda só o dono")
        # 🚨 OS AINDA NÃO FINALIZADA: a WESO não refletir é o esperado, o trabalho
        # está em andamento. Medido: 9 das 14 OS acusadas estavam em Nova/Iniciada.
        # "Ainda não aconteceu" NUNCA pinta de vermelho -- mas o motivo continua
        # visível, porque é informação útil.
        elif v_sit == DIVERGENTE and status_os != "Finalizado":
            rotulo = status_os or "sem status"
            v_sit, motivo_sit = INDEFINIDO, f"OS ainda {rotulo}, a WESO pode não refletir: {motivo_sit}"

        linhas.append({
            "serial": serial, "placa": placa, "acao": acao,
            "modelo_weso": modelo, "situacao_weso": situacao,
            "situacao_esperada": situacao_esperada(acao),
            "produto_do_modelo": produto,
            "serie_na_placa": bool(veic and r and veic.get("rastreador_id") == r.get("id")),
            "placa_atual_da_serie": (_como_veiculo(placa_hoje) or {}).get("placa"),
            "os_posterior": posterior, "anulada_na_mesma_os": anulada,
            "veredito_situacao": v_sit, "motivo_situacao": motivo_sit,
            "no_cache": r is not None, "placa_no_cache": veic is not None,
        })

    # ── veredito 1: a ação bate com o que o `problema` prevê? ────────────────
    if prev == SEM_REGRA:
        v_acao, motivo_acao = SEM_REGRA, "problema sem regra medida"
    elif prev == "misto":
        v_acao, motivo_acao = INDEFINIDO, "problema admite instalação e desinstalação"
    else:
        alvo = ACAO_INSTALACAO if prev == "instalacao" else ACAO_DESINSTALACAO
        fora = sorted(a for a in acoes if a != alvo and a in (ACAO_INSTALACAO, ACAO_DESINSTALACAO))
        if not acoes:
            v_acao, motivo_acao = INDEFINIDO, "OS sem linha de oficina"
        elif fora:
            v_acao = DIVERGENTE
            nome = {1: "instalação", 2: "desinstalação"}
            # A chave interna (`instalacao`) não vai para a tela: texto com acento.
            previsto = {"instalacao": "instalação", "desinstalacao": "desinstalação"}[prev]
            motivo_acao = (f"problema prevê {previsto}, mas a oficina tem "
                           + " e ".join(nome.get(a, str(a)) for a in fora))
        else:
            v_acao, motivo_acao = OK, ""

    # ── veredito 2: a WESO bate com a ação, linha por linha ─────────────────
    # A linha anulada não entra na conta: quem julga o par é a linha da saída.
    sits = [li["veredito_situacao"] for li in linhas if not li["anulada_na_mesma_os"]]
    if not sits:
        v_weso, motivo_weso = INDEFINIDO, "OS sem linha de oficina"
    elif DIVERGENTE in sits:
        v_weso = DIVERGENTE
        motivo_weso = "; ".join(li["motivo_situacao"] for li in linhas
                               if li["veredito_situacao"] == DIVERGENTE)
    elif all(s == OK for s in sits):
        v_weso, motivo_weso = OK, ""
    else:
        v_weso = INDEFINIDO
        motivo_weso = "; ".join(li["motivo_situacao"] for li in linhas
                               if li["veredito_situacao"] == INDEFINIDO)

    # ── veredito 3: o modelo da WESO bate com o material da OS? ─────────────
    # Regra 2 do topo: vale quem ENTRA; sem ninguém entrando, quem sai.
    entram = [li for li in linhas
              if li["acao"] == ACAO_INSTALACAO and not li["anulada_na_mesma_os"]]
    saem = [li for li in linhas
            if li["acao"] == ACAO_DESINSTALACAO and not li["anulada_na_mesma_os"]]
    referencia = entram or saem
    prod_mat = produtos_rastreador_da_os(materiais, ids_de_para)
    esperados = {li["produto_do_modelo"] for li in referencia
                 if li["produto_do_modelo"] is not None}

    if not referencia:
        v_mod, motivo_mod = INDEFINIDO, "OS sem instalação nem desinstalação"
    elif not esperados:
        v_mod, motivo_mod = INDEFINIDO, (
            "modelo da WESO sem de-para, ou série fora do cache")
    elif not prod_mat:
        v_mod, motivo_mod = INDEFINIDO, "a OS não tem material de rastreador"
    elif esperados & prod_mat:
        v_mod, motivo_mod = OK, ""
    else:
        v_mod = DIVERGENTE
        quem = "entra" if entram else "sai"
        motivo_mod = (f"a WESO diz produto {sorted(esperados)} para quem {quem}, "
                      f"e a OS lança {sorted(prod_mat)}")

    partes = [m for m in (motivo_acao, motivo_weso, motivo_mod) if m]
    return {
        "numero_os": os_linha.get("numero_os"),
        "problema": problema, "tipo": os_linha.get("tipo"),
        "situacao_id": os_linha.get("situacao_id"),
        "status_str": os_linha.get("status_str"),
        "acao_esperada": prev,
        "veredito_acao": v_acao,
        "veredito_weso": v_weso,
        "veredito_modelo": v_mod,
        "linhas": linhas,
        "detalhe": " | ".join(partes) if partes else "bate com a WESO",
    }


# ── Insumos comuns às duas telas (sub-aba e Conferência de Fechamento) ───────

def de_para_do_banco() -> dict:
    """{modelo da WESO em MAIÚSCULA: id do produto no Harmonit}.

    ⚠️ `listar_modelos_produto` é SÍNCRONA (não é `async`) -- as duas formas
    convivem no `storage.py`, e pôr `await` aqui seria erro de execução."""
    from .. import storage                              # noqa: PLC0415
    return {m["modelo"].strip().upper(): m["harmonit_id"]
            for m in storage.listar_modelos_produto()
            if m.get("modelo") and m.get("harmonit_id")}


async def ultima_os_por_serial() -> dict:
    """{série: maior número de OS com oficina daquela série}, do histórico
    INTEIRO -- não da fila nem da página exibida. Senão a OS mais antiga mostrada
    não saberia que uma posterior mexeu na mesma série."""
    from .. import storage                              # noqa: PLC0415
    ultima: dict = {}
    for ln in await storage.os_com_oficina(5000):
        for of in ln["oficinas"]:
            s = str(of.get("equipamentoId") or "").strip()
            if s:
                ultima[s] = max(ultima.get(s, 0), ln["numero_os"])
    return ultima


# ── O que a tela consome ─────────────────────────────────────────────────────

async def conferir_do_banco(limit: int = 200, so_divergentes: bool = False,
                            so_servico_realizado: bool = False) -> dict:
    """Confere as OS com oficina que o `os_historico` já guarda.

    ⚠️ Nenhuma chamada de API: tudo sai do banco local e do cache da WESO. A
    resposta diz a IDADE do cache, porque um serviço feito hoje aparece com a
    WESO de ontem -- e quem olha a tela precisa saber disso
    (`M12`: tela que não diz o que sabe, mente por omissão)."""
    from .. import storage                              # noqa: PLC0415

    c = carregar_cache()
    de_para = de_para_do_banco()

    def buscar(serial):
        if not c:
            return None
        try:
            return c.rastreador_por_serial(serial)
        except Exception:
            return None

    def buscar_placa(placa):
        if not c:
            return None
        try:
            return c.veiculo_por_placa(placa)
        except Exception:
            return None

    # Onde a série está HOJE. O `cache.py` não tem essa busca (só placa -> série),
    # então lê o mesmo arquivo direto, em `mode=ro` -- igual ao `cache.py`.
    wc = None
    try:
        import sqlite3                                  # noqa: PLC0415
        wc = sqlite3.connect(f"file:{CACHE_DIR}/weso.db?mode=ro", uri=True)
    except Exception:
        wc = None

    def placa_do_rastreador(rid):
        """Veículo onde a série está HOJE, com o chassi -- é ele que prova que
        "chassi da OS" e "placa da WESO" são o mesmo carro."""
        if not wc:
            return None
        try:
            row = wc.execute("SELECT placa, chassi, descricao FROM veiculos "
                             "WHERE rastreador_id = ?", (rid,)).fetchone()
            return ({"placa": row[0], "chassi": row[1], "descricao": row[2]}
                    if row else None)
        except Exception:
            return None

    ultima = await ultima_os_por_serial()

    itens = []
    for linha in await storage.os_com_oficina(limit, so_servico_realizado):
        v = conferir_os(linha, de_para, buscar, buscar_placa,
                        placa_do_rastreador, ultima)
        if so_divergentes and DIVERGENTE not in (
                v["veredito_acao"], v["veredito_weso"], v["veredito_modelo"]):
            continue
        itens.append(v)

    if wc:
        wc.close()
    idade = None
    if c:
        try:
            idade = c.idade_horas()
        except Exception:
            idade = None
    return {"itens": itens, "cache_idade_horas": idade,
            "cache_ok": c is not None, "modelos_no_de_para": len(de_para)}
