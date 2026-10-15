"""Listagem da Gestão de Contratos (`CTR_1.2`) — etapa G3. 2026-10-14.

O grid da aba: **uma linha por cliente**, com a situação já somada. Módulo
próprio porque aqui **nada se grava** -- quem escreve é o `contratos_registro`,
e separar as duas coisas é o que permite ler este arquivo inteiro e saber que
abrir a tela não muda a base.

🚨 A LISTAGEM NÃO CHAMA `ficha()`. A ficha recalcula o cliente na hora, e
chamá-la 731 vezes para desenhar a primeira tela era o caminho natural e
errado: o grid lê o cache `contrato_placa` em agregações, e o recálculo é feito
**uma vez**, em lote, quando o cache é de outro dia (ver `_cache_velho`).

🚨 O CACHE ENVELHECE SOZINHO. O aviso prévio vence pelo calendário, sem nenhum
evento novo para disparar a conta -- é a mesma razão pela qual a rotina de
auditoria recalcula antes de comparar. Cache de ontem mostraria placa
rescindida há 91 dias ainda "em aviso", e isso é tela que mente.

⚠️ A LINHA É O CLIENTE, e isso é escolha com motivo: a pergunta da tela é "como
está o contrato deste cliente". Termo (4.599) e placa (6.800) são detalhe, e
viram gaveta. Termo como linha esconde o cliente; placa como linha repete o
mesmo cliente em até 38 linhas.
"""
import csv
import io
import re

from . import contratos_eventos as motor
from . import contratos_registro as registro
from . import contratos_tabelas

# Estados do cliente. 🚨 ENUM FECHADO, E NUM LUGAR SÓ: é por aqui que as fases
# futuras (termo em geração, enviado para assinar, entregue ao financeiro)
# crescem. Espalhar `if` na tela foi o que fez duas telas prometerem o que não
# faziam -- quando o estado muda, muda aqui, e a tela não precisa saber a regra.
EM_DIA = "EM_DIA"
ATIVA_SEM_ASSINATURA = "ATIVA_SEM_ASSINATURA"
A_REVISAR = "A_REVISAR"
SEM_PLACA_ATIVA = "SEM_PLACA_ATIVA"

ESTADOS = {
    EM_DIA: "placas ativas, todas com termo assinado",
    ATIVA_SEM_ASSINATURA: "tem placa ativa sustentada por termo sem assinatura",
    A_REVISAR: "tem termo marcado a revisar",
    SEM_PLACA_ATIVA: "nenhuma placa ativa hoje — só histórico",
}

# A base "não assinado" é a que o motor escreve quando nenhum documento assinado
# sustenta a placa. As outras ("assinado", "assinado (troca registrada...)",
# "assinado com 'a definir'...") todas começam por "assinado".
BASE_NAO_ASSINADO = "nao assinado"


def estado_cliente(linha: dict) -> str:
    """O estado de uma linha já somada. Função pura -- testável sem banco.

    ⚠️ A ORDEM É A PRIORIDADE, e ela não é alfabética: "placa ativa sem
    assinatura" vem antes de "a revisar" porque é a que tem dinheiro e risco
    jurídico em cima; "a revisar" é dúvida de cadastro.
    """
    if linha.get("so_nao_assinado"):
        return ATIVA_SEM_ASSINATURA
    if linha.get("a_revisar"):
        return A_REVISAR
    if not linha.get("ativas") and not linha.get("aviso"):
        return SEM_PLACA_ATIVA
    return EM_DIA


# 🆕 D4: a aderência entre o que o contrato sustenta e o que está em uso.
# 🚨 A MARGEM É DELE: *"primeiro os casos de 100% de aderência com margem de
# 1+ ou -"*. ±1 cobre a placa comprada e ainda não instalada, que é normal --
# com folga zero, cliente com uma única instalação pendente cairia na lista de
# problema (a auditoria achou 1.362 casos de "contratada e não instalada").
MARGEM_ADERENCIA = 1

ADERENTE = "ADERENTE"
CONTRATO_MAIOR = "CONTRATO_MAIOR_QUE_USO"
USO_MAIOR = "USO_MAIOR_QUE_CONTRATO"
SEM_DADO = "SEM_DADO_DA_WESO"
# ⚠️ CLIENTE SEM PLACA SUSTENTADA NÃO É "SEM DADO DA WESO". A primeira versão
# punha os dois no mesmo rótulo e a tela acusava o cache por 252 clientes que
# simplesmente não têm nada ativo para comparar -- culpar a fonte errada manda
# procurar defeito onde não há.
SEM_SUSTENTADA = "SEM_PLACA_SUSTENTADA"

ADERENCIAS = {
    ADERENTE: "o que o contrato sustenta bate com o que está em uso (margem de ±1)",
    CONTRATO_MAIOR: "o contrato sustenta mais placas do que a WESO tem em uso",
    USO_MAIOR: "há placa em uso que o contrato não sustenta",
    SEM_SUSTENTADA: "o cliente não tem placa sustentada hoje — nada a comparar",
    SEM_DADO: "sem o cache da WESO não há com o que comparar",
}


def aderencia_da_linha(linha: dict) -> str:
    """Compara o sustentado com o que está em uso. Função pura.

    ⚠️ Esta conta é "contrato sem uso". Ela **não** acusa a placa que está na
    WESO e não tem contrato nenhum -- aquilo é "em uso sem contrato", achado da
    rotina C6 (320 casos), e segue por lá. `USO_MAIOR` aqui só aparece se o
    cache trouxer mais do que o próprio contrato lista, o que seria um defeito
    de contagem, não um achado de negócio.
    """
    sustentadas = (linha.get("ativas") or 0) + (linha.get("aviso") or 0)
    if not sustentadas:
        return SEM_SUSTENTADA
    if linha.get("em_uso") is None:
        return SEM_DADO
    dif = sustentadas - linha["em_uso"]
    if abs(dif) <= MARGEM_ADERENCIA:
        return ADERENTE
    return CONTRATO_MAIOR if dif > 0 else USO_MAIOR


def acoes_da_linha(linha: dict) -> list:
    """O que se pode fazer nesta linha, com o motivo quando não se pode.

    🚨 A TELA NÃO DECIDE ISSO. Botão que existe e não faz nada é defeito, e
    botão escondido sem explicação manda o operador procurar. Então a ação vem
    daqui com `{ativa, motivo}`, e a tela só desenha.

    ⚠️ O que a aba ainda não faz **não aparece**: gerar termo, enviar para
    assinatura, cobrar etapa e entregar ao financeiro não estão nesta lista.
    """
    acoes = [
        {"id": "subir_termo", "label": "Subir termo", "ativa": True},
        {"id": "ficha", "label": "Ver ficha", "ativa": True},
    ]
    acoes.append({"id": "achados", "label": "Ver achados",
                  "ativa": bool(linha.get("achados")),
                  "motivo": None if linha.get("achados")
                  else "a última rodada da auditoria não achou nada neste cliente"})
    acoes.append({"id": "revisar", "label": "Resolver a revisar",
                  "ativa": bool(linha.get("a_revisar")),
                  "motivo": None if linha.get("a_revisar") else "nenhum termo marcado a revisar"})
    acoes.append({"id": "troca", "label": "Confirmar quem sai",
                  "ativa": bool(linha.get("troca_pendente")),
                  "motivo": None if linha.get("troca_pendente")
                  else "nenhuma troca registrada esperando confirmação"})
    acoes.append({"id": "fila", "label": "Documento na fila",
                  "ativa": bool(linha.get("na_fila")),
                  "motivo": None if linha.get("na_fila")
                  else "nenhum documento assinado parado esperando decisão"})
    acoes.append({"id": "nome", "label": "Corrigir nome", "ativa": True})
    return acoes


def _cache_velho(conn) -> str | None:
    """Por que o cache precisa ser refeito, ou `None` quando está em dia.

    🚨 CACHE VAZIO TAMBÉM É CACHE VELHO, e isto quase passou: com
    `contrato_placa` vazia o `MIN` vem nulo, e devolver "está em dia" fazia o
    grid mostrar **0 placas ativas para os 731 clientes** -- tela que mente,
    com a base cheia de eventos do lado. Acontece de verdade: um banco
    restaurado, ou termos gravados por um caminho que não recalculou.
    """
    linha = conn.execute("SELECT MIN(calculado_em) FROM contrato_placa").fetchone()
    mais_antigo = linha[0] if linha else None
    if not mais_antigo:
        tem_evento = conn.execute("SELECT 1 FROM contrato_evento LIMIT 1").fetchone()
        return "cache vazio com eventos na base" if tem_evento else None
    hoje = registro._agora()[:10]
    return mais_antigo if mais_antigo[:10] < hoje else None


def listar(conn, q: str | None = None, estado: str | None = None,
           empresa: str | None = None, aderencia: str | None = None,
           recalcular_se_velho: bool = True) -> dict:
    """Uma linha por cliente, com contagens e ações. **Não grava** (ver nota).

    ⚠️ A exceção é o recálculo em lote, que é escrita no CACHE derivado e não em
    fonte nenhuma -- e acontece no máximo uma vez por dia. Ele pode ser
    desligado (`recalcular_se_velho=False`) para o teste medir o cache como
    está, sem a tela mudando o que ele quer observar.
    """
    contratos_tabelas.criar(conn)
    contratos_tabelas.migrar(conn)

    recalculado = None
    if recalcular_se_velho and _cache_velho(conn):
        recalculado = registro.recalcular_todos(conn)

    # 1 de 3: termos por cliente.
    linhas = {}
    for (cnpj, termos, sem_assinatura, a_revisar, ultima, troca_pendente,
         empresas, so_harmonit) in conn.execute(
            """SELECT cnpj,
                      COUNT(*),
                      SUM(CASE WHEN assinado = 0 THEN 1 ELSE 0 END),
                      SUM(CASE WHEN revisar = 1 THEN 1 ELSE 0 END),
                      MAX(assinado_em),
                      SUM(CASE WHEN troca_registrada IS NOT NULL AND troca_registrada <> ''
                                AND revisar_motivo LIKE '%confirmação de qual placa sai%'
                               THEN 1 ELSE 0 END),
                      GROUP_CONCAT(DISTINCT empresa),
                      SUM(CASE WHEN assinado = 0 AND harmonit_assinado = 'sim' THEN 1 ELSE 0 END)
                 FROM contrato_termo GROUP BY cnpj"""):
        linhas[cnpj] = {
            "cnpj": cnpj, "termos": termos, "sem_assinatura": sem_assinatura or 0,
            "a_revisar": a_revisar or 0, "ultima_assinatura": ultima,
            "troca_pendente": troca_pendente or 0,
            "empresas": sorted((empresas or "").split(",")) if empresas else [],
            # ⚠️ "o Harmonit diz que está assinado e não há assinatura
            # verificável" -- NÃO é prova, é a pergunta que ele precisa ver.
            "so_marca_harmonit": so_harmonit or 0,
            "ativas": 0, "aviso": 0, "encerradas": 0, "so_nao_assinado": 0, "achados": 0,
            "na_fila": 0, "em_uso": None,
        }

    # 2 de 3: placas por cliente, do cache derivado.
    for cnpj, situacao, base, quantas in conn.execute(
            """SELECT cnpj, situacao, base, COUNT(*) FROM contrato_placa
                GROUP BY cnpj, situacao, base"""):
        alvo = linhas.setdefault(cnpj, {
            "cnpj": cnpj, "termos": 0, "sem_assinatura": 0, "a_revisar": 0,
            "ultima_assinatura": None, "troca_pendente": 0, "empresas": [],
            "so_marca_harmonit": 0, "ativas": 0, "aviso": 0, "encerradas": 0,
            "so_nao_assinado": 0, "achados": 0, "na_fila": 0, "em_uso": None})
        if situacao == motor.ATIVA:
            alvo["ativas"] += quantas
        elif situacao == motor.EM_AVISO_PREVIO:
            alvo["aviso"] += quantas
        else:
            alvo["encerradas"] += quantas
        if situacao in (motor.ATIVA, motor.EM_AVISO_PREVIO) and (base or "") == BASE_NAO_ASSINADO:
            alvo["so_nao_assinado"] += quantas

    # 3 de 3: achados da última rodada da auditoria.
    for cnpj, quantos in conn.execute(
            """SELECT cnpj, COUNT(*) FROM contrato_achado
                WHERE rodada_em = (SELECT MAX(rodada_em) FROM contrato_achado)
                GROUP BY cnpj"""):
        if cnpj in linhas:
            linhas[cnpj]["achados"] = quantos

    # 🆕 D4: quantas das placas sustentadas estão em uso na WESO.
    # 🚨 É O DESEMPATE DELE NA TELA: *"o criterio de desempate será quantas
    # placas ativas ele tem na weso"*. Sem isto, o grid mostrava 2.778 ativas e
    # não dizia em cima de quê -- e a pergunta dele foi exatamente essa.
    # ⚠️ Quando o cache não existe, `em_uso` fica `None` (a tela mostra "—" e
    # diz por quê). Zero seria uma afirmação falsa: "nada em uso".
    from . import contratos_aderencia as ader
    chaves_weso, idade_cache = ader.chaves_do_cache()
    if chaves_weso:
        for cnpj, k in conn.execute(
                """SELECT cnpj, placa_chave FROM contrato_placa
                    WHERE situacao IN (?, ?)""", (motor.ATIVA, motor.EM_AVISO_PREVIO)):
            alvo = linhas.get(cnpj)
            if alvo is None:
                continue
            if alvo.get("em_uso") is None:
                alvo["em_uso"] = 0
            if k in chaves_weso:
                alvo["em_uso"] += 1

    # 4 de 4: documentos que a carga dos assinados não conseguiu encaixar.
    # 🚨 A FILA TEM DE APARECER NO GRID. Ela mora no livro-razão
    # (`contrato_carga_pdf`), e um documento parado lá é trabalho esperando
    # decisão: leitura que veio descritiva, CNPJ divergente, número que existe
    # nas duas empresas. Fila invisível é fila que ninguém resolve.
    for cnpj, quantos in conn.execute(
            """SELECT cnpj, COUNT(*) FROM contrato_carga_pdf
                WHERE status = 'fila' GROUP BY cnpj"""):
        if cnpj in linhas:
            linhas[cnpj]["na_fila"] = quantos

    nomes = dict(conn.execute("SELECT cnpj, nome FROM contrato_cliente"))
    itens = []
    for cnpj, linha in linhas.items():
        linha["nome"] = nomes.get(cnpj)
        linha["estado"] = estado_cliente(linha)
        linha["aderencia"] = aderencia_da_linha(linha)
        linha["acoes"] = acoes_da_linha(linha)
        itens.append(linha)

    # Sem nome, ordena pelo CNPJ -- e nunca "sem nome" no fim escondido: o
    # cliente sem nome é justamente o que precisa de conserto.
    itens.sort(key=lambda i: (i.get("nome") or "zzz " + i["cnpj"]))

    contagens = {
        "clientes": len(itens),
        "com_ativa_sem_assinatura": sum(1 for i in itens if i["so_nao_assinado"]),
        "com_a_revisar": sum(1 for i in itens if i["a_revisar"]),
        "com_achados": sum(1 for i in itens if i["achados"]),
        "com_troca_pendente": sum(1 for i in itens if i["troca_pendente"]),
        # Contado aqui, e não na tela: o chip tem de vir do mesmo payload da
        # tabela, senão ele pode discordar dela.
        "com_sem_placa_ativa": sum(1 for i in itens if i["estado"] == SEM_PLACA_ATIVA),
        "em_dia": sum(1 for i in itens if i["estado"] == EM_DIA),
        "sem_nome": sum(1 for i in itens if not i["nome"]),
        "com_documento_na_fila": sum(1 for i in itens if i["na_fila"]),
        "aderentes": sum(1 for i in itens if i["aderencia"] == ADERENTE),
        "contrato_maior_que_uso": sum(1 for i in itens if i["aderencia"] == CONTRATO_MAIOR),
        "sem_dado_da_weso": sum(1 for i in itens if i["aderencia"] == SEM_DADO),
        "sem_placa_sustentada": sum(1 for i in itens if i["aderencia"] == SEM_SUSTENTADA),
        "placas_em_uso": sum(i["em_uso"] or 0 for i in itens),
        "placas_ativas": sum(i["ativas"] for i in itens),
        "placas_em_aviso": sum(i["aviso"] for i in itens),
    }

    filtrados = [i for i in itens if _passa(i, q, estado, empresa, aderencia)]

    # ⚠️ BUSCA POR PLACA SEM CAMPO SEPARADO. `ASC100` tem letra, então o filtro
    # acima a trata como nome e não acha nada -- e um campo de busca que
    # devolve vazio para uma placa que existe na base é defeito. Então, só
    # quando nada casou, a mesma caixa procura o identificador.
    achados_por_placa = []
    if q and not filtrados:
        cnpjs = {a["cnpj"] for a in clientes_por_placa(conn, q)}
        if cnpjs:
            achados_por_placa = sorted(cnpjs)
            filtrados = [i for i in itens if i["cnpj"] in cnpjs
                         and _passa(i, None, estado, empresa, aderencia)]

    return {
        "contagens": contagens,
        "total": len(filtrados),
        "filtro": {"q": q, "estado": estado, "empresa": empresa, "aderencia": aderencia},
        "estados": ESTADOS,
        "aderencias": ADERENCIAS,
        "recalculado": recalculado,
        # A tela DIZ de quando e o numero da WESO -- e diz quando nao tem.
        "weso": {"tem_cache": bool(chaves_weso),
                 "idade_h": round(idade_cache, 1) if idade_cache is not None else None,
                 "veiculos": len(chaves_weso) or None},
        # A tela diz "achei pela placa", em vez de fingir que foi pelo nome.
        "achou_por_placa": achados_por_placa,
        "itens": filtrados,
    }


def _passa(linha: dict, q: str | None, estado: str | None, empresa: str | None,
           aderencia: str | None = None) -> bool:
    if estado and linha["estado"] != estado:
        return False
    if aderencia and linha.get("aderencia") != aderencia:
        return False
    if empresa and empresa not in (linha.get("empresas") or []):
        return False
    if q:
        alvo = q.strip().lower()
        # 🚨 BUSCA COM LETRA É BUSCA POR NOME. Extrair dígito de qualquer texto
        # parecia inofensivo e não era: "2hm" virava o dígito "2", que casa com
        # quase todo CNPJ -- a busca devolvia a base inteira e o operador
        # concluiria que o filtro não funciona. Medido com 2 clientes, os 2
        # voltaram.
        if any(c.isalpha() for c in alvo):
            return alvo in (linha.get("nome") or "").lower()
        digitos = "".join(c for c in alvo if c.isdigit())
        # Menos de 3 dígitos não é CNPJ nem pedaço útil dele.
        if len(digitos) >= 3:
            return digitos in linha["cnpj"]
        return alvo in (linha.get("nome") or "").lower()
    return True


def clientes_por_placa(conn, texto: str) -> list:
    """Os CNPJs que têm esta placa. Busca do grid por identificador.

    🚨 COMPARA PELA CHAVE, MOSTRA O TEXTO. `BUW8732` normaliza para `BUW8H32`,
    que não existe -- procurar pelo texto cru acharia menos do que existe, e
    devolver a chave mostraria placa inventada.
    """
    chave = motor.chave(texto or "")
    if not chave:
        return []
    return [{"cnpj": c, "placa": p, "situacao": s}
            for c, p, s in conn.execute(
                """SELECT cnpj, placa_texto, situacao FROM contrato_placa
                    WHERE placa_chave = ? OR placa_chave LIKE ?""",
                (chave, f"%{chave}%"))]


def fila_da_carga(conn, cnpj: str | None = None, limite: int = 500) -> dict:
    """Os documentos assinados que a carga não conseguiu encaixar, com o motivo.

    🚨 CADA LINHA AQUI É TRABALHO ESPERANDO UMA PESSOA, não erro a esconder: a
    leitura que veio descritiva (o extrator devolveu a linha do veículo no lugar
    da placa), o CNPJ do PDF que diverge do cliente da pasta, o número que
    existe no Instituto E na Movisat. Forçar qualquer um deles anexaria o
    documento assinado ao contrato errado.

    ⚠️ Mostra também o que foi **rejeitado** (estado de origem proibido), para a
    conferência poder provar que nenhum cancelado entrou.
    """
    contratos_tabelas.criar(conn)
    sql = """SELECT c.sha256, c.cnpj, cl.nome, c.arquivo, c.estado_origem, c.numero_no_nome,
                    c.numero_no_pdf, c.status, c.motivo, c.lote, c.em
               FROM contrato_carga_pdf c
               LEFT JOIN contrato_cliente cl ON cl.cnpj = c.cnpj
              WHERE c.status IN ('fila', 'rejeitado')"""
    p: tuple = ()
    if cnpj:
        sql += " AND c.cnpj = ?"
        p = (cnpj,)
    sql += " ORDER BY c.cnpj, c.numero_no_nome LIMIT ?"
    linhas = [{"sha256": a, "cnpj": b, "nome": c, "arquivo": d, "estado_origem": e,
               "numero_no_nome": f, "numero_no_pdf": g, "status": h, "motivo": i,
               "lote": j, "em": k}
              for a, b, c, d, e, f, g, h, i, j, k in conn.execute(sql, p + (limite,))]
    resumo: dict = {}
    for linha in linhas:
        # Agrupa pelo começo do motivo, porque o fim traz o nome do arquivo e a
        # placa -- que são do caso, não do tipo.
        # ⚠️ NÃO se corta no `:`: o próprio motivo tem dois-pontos (*"a leitura
        # devolveu 'Cod: 01-05 ...'"*), e cortar ali gerava chave truncada no
        # meio da frase, do tipo `a leitura devolveu 'Cod`.
        # 🚨 O RESUMO AGRUPA POR TIPO DE PROBLEMA, e para isso tem de tirar o
        # que é do CASO: o texto citado (a linha que o extrator devolveu) e os
        # números (o do termo). Sem isso cada documento virava um grupo de um,
        # e um "resumo" com uma linha por item não resume nada.
        bruto = " ".join((linha["motivo"] or "sem motivo registrado").split())
        chave = re.sub(r"\d+", "N", bruto.split("'")[0].split(":")[0]).strip()[:60]
        chave = chave or bruto[:40]
        resumo[chave] = resumo.get(chave, 0) + 1
    return {"total": len(linhas), "resumo": resumo, "itens": linhas}


def aderencia_do_cliente(conn, cnpj: str) -> dict:
    """Placa por placa, o motivo: em uso, saiu, ou nunca instalada.

    Reusa `contratos_aderencia.classificar`, que é quem conhece as regras dele
    -- a tela não repete regra nenhuma, só mostra o que o módulo classificou.
    """
    from . import contratos_aderencia as ader
    placas, idade, n_veiculos, teto = ader._weso()
    itens = ader.classificar(conn, placas, cnpj) if placas else []
    return {
        "cnpj": cnpj,
        "tem_cache": bool(placas),
        "idade_h": round(idade, 1) if idade is not None else None,
        "teto_h": teto,
        # ⚠️ A tela precisa saber que o dado está velho para não afirmar em cima
        # dele: acima do teto, a rotina se recusa a decidir, e a tela avisa.
        "cache_velho": bool(idade is not None and idade > teto),
        "veiculos_weso": n_veiculos,
        "itens": itens,
    }


def para_csv(dados: dict) -> str:
    """O grid filtrado, como CSV. Mesmas colunas que a tela mostra."""
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";")
    w.writerow(["CNPJ", "Cliente", "Estado", "Ativas", "Em aviso previo",
                "Ativas sem assinatura", "Encerradas", "Termos", "Sem assinatura",
                "A revisar", "Achados", "Em uso na WESO", "Aderencia", "Ultima assinatura"])
    for i in dados["itens"]:
        w.writerow([i["cnpj"], i.get("nome") or "", i["estado"], i["ativas"], i["aviso"],
                    i["so_nao_assinado"], i["encerradas"], i["termos"], i["sem_assinatura"],
                    i["a_revisar"], i["achados"],
                    "" if i.get("em_uso") is None else i["em_uso"], i.get("aderencia") or "",
                    i.get("ultima_assinatura") or ""])
    return saida.getvalue()


# ── superfície assíncrona ────────────────────────────────────────────────────

async def listar_clientes(**kw) -> dict:
    return await registro._exec(listar, **kw)


async def buscar_por_placa(texto: str) -> list:
    return await registro._exec(clientes_por_placa, texto)


async def fila(cnpj: str | None = None, limite: int = 500) -> dict:
    return await registro._exec(fila_da_carga, cnpj, limite)


async def aderencia(cnpj: str) -> dict:
    return await registro._exec(aderencia_do_cliente, cnpj)
