"""Gravação da Gestão de Contratos (`CTR_1.1`) — etapa C3. 2026-10-13.

Grava termo, eventos e itens; recalcula a situação derivada; monta a ficha do
cliente. **Não escreve no Harmonit, na WESO nem na Clicksign** -- em nenhuma
fase da aba, por decisão de escopo (doc 31).

🚨 NÚCLEO SÍNCRONO, SUPERFÍCIE ASSÍNCRONA. As funções que recebem `conn` são o
núcleo e rodam em banco de memória num teste, sem asyncio e sem o arquivo real.
As `async` são as que o router chama, no padrão do `storage.py`
(`run_in_executor` em volta de um `_run`). Foi o que permitiu travar as regras
antes de existir tela.

🚨 EVENTO NÃO SE ATUALIZA, SE ACRESCENTA. Nenhum `UPDATE` em
`contrato_evento`: corrigir é lançar outro evento. É o oposto do que o Harmonit
faz hoje -- editar o PDF do termo depois de assinado e anotar a troca em texto
livre -- e é o que faz a pergunta "por que esta placa está ativa?" ter resposta.

🚨 `contrato_placa` É CACHE, NUNCA FONTE. Ela existe para a tela não recalcular
731 clientes a cada abertura. Em caso de divergência o evento ganha, e
`recalcular` a refaz do zero. Nenhuma regra decide lendo ela.
"""
import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .. import storage
from . import contratos_eventos as motor
from . import contratos_tabelas

def pasta_pdf() -> Path:
    """Onde o PDF assinado é guardado. **Resolvida na hora, nunca no import.**

    ⚠️ Era uma constante de módulo e isso tornava o caminho impossível de
    desviar: o teste do router gravaria na pasta de dados de verdade, porque o
    valor fica congelado na importação. Mesma família do erro de ler
    configuração uma vez e nunca mais.
    """
    return Path(storage.DB_PATH).parent / "contratos"


class TermoJaGravado(Exception):
    """Mesmo PDF subindo duas vezes.

    🚨 É O QUE IMPEDE O EVENTO DOBRADO. Clicar duas vezes em "confirmar" já
    duplicou card no Painel Financeiro; aqui o `hash` do arquivo é UNIQUE e a
    segunda tentativa vira erro com o id do primeiro, não um segundo termo.
    """

    def __init__(self, termo_id, numero):
        self.termo_id, self.numero = termo_id, numero
        super().__init__(f"Este PDF já foi gravado no termo {numero} (id {termo_id}).")


def _connect():
    conn = sqlite3.connect(storage.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _agora():
    return datetime.now(timezone.utc).isoformat()


def hash_pdf(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


# ── núcleo (recebe conn; testável em memória) ────────────────────────────────

def gravar(conn, cnpj: str, lido: dict, *, assinado: bool, assinado_em: str | None,
           origem: str, enviado_por: str, hash_arquivo: str | None = None,
           arquivo: str | None = None, saida_confirmada: list | None = None,
           eventos_do_harmonit: list | None = None, troca_registrada: str | None = None,
           revisar_motivo: str | None = None) -> int:
    """Grava o termo e seus eventos. Devolve o `termo_id`.

    `saida_confirmada` são as placas que o OPERADOR disse que saem numa troca.
    🚨 ELAS SÓ EXISTEM PORQUE A ANOTAÇÃO NÃO DIZ QUEM SAI. A anotação da Maxi
    Confort 8872 nomeia só a placa que entra (`FAC 5H30`), e no PDF do Harmonit
    as duas ficam na tabela, no mesmo item -- não há dado que aponte a antiga.
    Em vez de adivinhar (regra 13: **não se inventa identificador**), a saída
    vem confirmada por gente e fica gravada como evento, com a autoria.
    """
    if hash_arquivo:
        ja = conn.execute("SELECT id, numero FROM contrato_termo WHERE hash = ?", (hash_arquivo,)).fetchone()
        if ja:
            raise TermoJaGravado(ja[0], ja[1])

    agora = _agora()
    cur = conn.execute(
        """INSERT INTO contrato_termo
           (cnpj, numero, empresa, tipo, assinado, assinado_em, troca_registrada, a_definir,
            origem, arquivo, hash, revisar, revisar_motivo, enviado_por, enviado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cnpj, str(lido.get("numero") or ""), lido.get("empresa") or "MOVISAT", lido.get("perfil"),
         1 if assinado else 0, assinado_em, troca_registrada, 1 if lido.get("a_definir") else 0,
         origem, arquivo, hash_arquivo, 1 if revisar_motivo else 0, revisar_motivo,
         enviado_por, agora))
    termo_id = cur.lastrowid

    confirmadas = {motor.chave(p) for p in (saida_confirmada or [])}
    eventos = list(lido.get("eventos") or [])

    # ⚠️ Os eventos lidos no PDF do Harmonit entram marcados `fonte=harmonit`.
    # Quem decide se eles valem como assinados é o MOTOR, pela regra da troca /
    # do "a definir" -- não este gravador. Gravar já "resolvido" perderia a
    # razão, e é a razão que a ficha mostra.
    for e in (eventos_do_harmonit or []):
        eventos.append(dict(e, fonte=motor.HARMONIT))

    for p in (saida_confirmada or []):
        eventos.append({"acao": motor.SAI, "placa": p, "fonte": motor.HARMONIT,
                        "obs": f"saída confirmada por {enviado_por} (troca registrada no Harmonit)"})

    for e in eventos:
        placa = (e.get("placa") or "").strip()
        if not placa:
            continue
        rec = e.get("recursos")
        conn.execute(
            """INSERT INTO contrato_evento
               (termo_id, placa_chave, placa_texto, acao, fonte, recursos, valor_mensal, obs, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (termo_id, motor.chave(placa), placa, e["acao"], e.get("fonte") or motor.ASSINADO,
             json.dumps(rec, ensure_ascii=False) if isinstance(rec, (dict, list)) else rec,
             e.get("valor_mensal"), e.get("obs"), agora))

        if e["acao"] == motor.ENTRA and motor.chave(placa) not in confirmadas:
            conn.execute(
                """INSERT INTO contrato_item
                   (cnpj, placa_chave, placa_texto, recursos, valor_mensal, inicio, termo_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (cnpj, motor.chave(placa), placa,
                 json.dumps(rec, ensure_ascii=False) if isinstance(rec, (dict, list)) else rec,
                 e.get("valor_mensal"), assinado_em, termo_id))
    return termo_id


def anexar_assinado(conn, termo_id: int, cnpj: str, lido: dict, *, assinado_em: str | None,
                    enviado_por: str, hash_arquivo: str, arquivo: str | None,
                    eventos_do_harmonit: list | None = None,
                    troca_registrada: str | None = None,
                    saida_confirmada: list | None = None) -> dict:
    """Anexa o PDF assinado a um termo que JÁ EXISTE, em vez de criar outro.

    🚨 É O QUE IMPEDE O TERMO DOBRADO, e o defeito é real: a carga gravou os
    4.599 termos **sem hash** (ela não guarda PDF), e `gravar()` só deduplica
    por hash. Sem este caminho, subir o PDF assinado do 2649 da 2HM criaria um
    SEGUNDO termo 2649, com os eventos repetidos, e o primeiro continuaria
    contado em "sem assinatura" -- a tela mostraria o cliente pior do que ele
    está, por causa do próprio conserto.

    🚨 O EVENTO DA CARGA NÃO SE APAGA. Se o PDF assinado não confirma uma placa
    que a carga trouxe, o termo vira `revisar` com o motivo escrito: o evento é
    imutável, e a carga usou a lista de placas do Harmonit (480 termos já estão
    marcados por isso). Apagar aqui seria decidir, no escuro, contra o
    documento que está na mão de quem subiu.

    Devolve o diff, para a tela dizer o que mudou em vez de só "gravado".
    """
    linha = conn.execute(
        """SELECT cnpj, numero, empresa, hash, assinado FROM contrato_termo WHERE id = ?""",
        (termo_id,)).fetchone()
    if not linha:
        raise ValueError(f"Termo {termo_id} não existe.")
    dono, numero, empresa, hash_atual, ja_assinado = linha
    if dono != cnpj:
        # Anexar no cliente errado move contrato de empresa, e a auditoria achou
        # 33 documentos com CNPJ divergente do cliente que o Harmonit aponta.
        raise ValueError(f"O termo {numero} é do CNPJ {dono}, não do {cnpj}.")
    if hash_atual:
        raise TermoJaGravado(termo_id, numero)

    ja = conn.execute("SELECT id FROM contrato_termo WHERE hash = ?", (hash_arquivo,)).fetchone()
    if ja:
        raise TermoJaGravado(ja[0], numero)

    agora = _agora()
    eventos = list(lido.get("eventos") or [])
    for e in (eventos_do_harmonit or []):
        eventos.append(dict(e, fonte=motor.HARMONIT))
    for p in (saida_confirmada or []):
        eventos.append({"acao": motor.SAI, "placa": p, "fonte": motor.HARMONIT,
                        "obs": f"saída confirmada por {enviado_por} (troca registrada no Harmonit)"})

    # 🚨 A chave serve para COMPARAR e o texto para MOSTRAR: `BUW8732`
    # normaliza para `BUW8H32`, placa que não existe. Então o conjunto é de
    # chaves e o dicionário guarda o texto que será exibido.
    antes = {}
    for p, a in conn.execute(
            "SELECT placa_texto, acao FROM contrato_evento WHERE termo_id = ?", (termo_id,)):
        antes[(motor.chave(p), a)] = p
    novos, confirmados = [], set()
    for e in eventos:
        placa = (e.get("placa") or "").strip()
        if not placa:
            continue
        marca = (motor.chave(placa), e["acao"])
        confirmados.add(marca)
        if marca in antes:
            continue
        rec = e.get("recursos")
        conn.execute(
            """INSERT INTO contrato_evento
               (termo_id, placa_chave, placa_texto, acao, fonte, recursos, valor_mensal, obs, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (termo_id, motor.chave(placa), placa, e["acao"], e.get("fonte") or motor.ASSINADO,
             json.dumps(rec, ensure_ascii=False) if isinstance(rec, (dict, list)) else rec,
             e.get("valor_mensal"), e.get("obs"),
             agora))
        novos.append(placa)

        # 🚨 PLACA QUE ENTRA PELO ASSINADO PRECISA DE ITEM, senão o valor não
        # tem onde morar. Decisão dele (13/10): o valor vive no `contrato_item`.
        # A primeira versão só inseria o evento, e o `preencher_valores` do 2224
        # da 2HM não achava linha para preencher -- calado, como se o documento
        # não trouxesse valor.
        if e["acao"] in (motor.ENTRA, motor.UPGRADE):
            rec = e.get("recursos")
            conn.execute(
                """INSERT INTO contrato_item
                   (cnpj, placa_chave, placa_texto, recursos, valor_mensal, inicio, termo_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (cnpj, motor.chave(placa), placa,
                 json.dumps(rec, ensure_ascii=False) if isinstance(rec, (dict, list)) else rec,
                 e.get("valor_mensal"), assinado_em, termo_id))

    nao_confirmados = sorted({texto for marca, texto in antes.items()
                              if marca not in confirmados})
    motivo = None
    if nao_confirmados:
        motivo = ("o documento assinado não confirma: " + ", ".join(nao_confirmados[:8])
                  + (" ..." if len(nao_confirmados) > 8 else ""))

    conn.execute(
        """UPDATE contrato_termo
              SET assinado = 1, assinado_em = COALESCE(?, assinado_em), hash = ?, arquivo = ?,
                  troca_registrada = COALESCE(?, troca_registrada),
                  a_definir = CASE WHEN ? THEN 1 ELSE a_definir END,
                  revisar = CASE WHEN ? THEN 1 ELSE revisar END,
                  revisar_motivo = CASE WHEN ? THEN
                      CASE WHEN revisar_motivo IS NULL OR revisar_motivo = '' THEN ?
                           ELSE revisar_motivo || '; ' || ? END
                      ELSE revisar_motivo END,
                  enviado_por = ?, enviado_em = ?
            WHERE id = ?""",
        (assinado_em, hash_arquivo, arquivo, troca_registrada,
         1 if lido.get("a_definir") else 0,
         1 if motivo else 0, 1 if motivo else 0, motivo, motivo,
         enviado_por, agora, termo_id))

    # 🆕 C7/A6: o valor que o documento declara entra aqui, porque é o único
    # ponto em que ele passa -- e o `contrato_item` do termo já existe, vazio,
    # desde a carga.
    valores = preencher_valores(conn, termo_id, cnpj,
                                ((lido.get("valores") or {}).get("por_placa") or {}))

    recalcular(conn, cnpj)
    return {"termo_id": termo_id, "numero": numero, "empresa": empresa,
            "valores": valores,
            "ja_estava_assinado": bool(ja_assinado), "eventos_novos": novos,
            "nao_confirmados": nao_confirmados, "a_revisar": bool(motivo),
            "revisar_motivo": motivo}


def preencher_valores(conn, termo_id: int, cnpj: str, por_placa: dict) -> dict:
    """Grava o valor mensal que o documento declara, **só onde está vazio**.

    🚨 PRECISA EXISTIR PORQUE `anexar_assinado` NÃO PREENCHE ITEM. Ele insere só
    o evento que falta, e o `contrato_item` do termo já existe desde a carga --
    com `valor_mensal` nulo em **100%** das 6.462 linhas. Sem isto, a releitura
    guardaria o documento e a futura Contas a Receber continuaria sem nada para
    calcular.

    ⚠️ SÓ ONDE ESTÁ NULO, e isto é deliberado: valor já gravado foi posto por
    alguém olhando, ou por um documento anterior, e sobrescrever seria decidir
    no escuro qual dos dois vale. O que divergir aparece no retorno.
    """
    # ⚠️ `sem_item` existe porque a primeira versão ficava CALADA quando não
    # havia linha para preencher: o `UPDATE` casava 0 e os dois contadores
    # voltavam vazios, como se o documento não tivesse valor. Era o caso real do
    # 2224 da 2HM -- a placa entrou pelo assinado, e `anexar_assinado` não criava
    # o item. Contador que esconde "não existe" é número que mente.
    r = {"preenchidos": [], "ja_tinha": [], "sem_item": []}
    for placa, valor in (por_placa or {}).items():
        if not valor:
            continue
        k = motor.chave(placa)
        cur = conn.execute(
            """UPDATE contrato_item SET valor_mensal = ?
                WHERE cnpj = ? AND termo_id = ? AND placa_chave = ?
                  AND (valor_mensal IS NULL OR valor_mensal = '')""",
            (valor, cnpj, termo_id, k))
        if cur.rowcount:
            r["preenchidos"].append(placa)
        elif conn.execute(
                """SELECT 1 FROM contrato_item
                    WHERE cnpj = ? AND termo_id = ? AND placa_chave = ? LIMIT 1""",
                (cnpj, termo_id, k)).fetchone():
            r["ja_tinha"].append(placa)
        else:
            r["sem_item"].append(placa)
    return r


class JaAnulado(Exception):
    """Este evento já foi anulado antes. Rodar a carga de novo não repete."""


def anular_evento(conn, evento_id: int, por: str, motivo: str) -> dict:
    """Lança um `ANULA` contra um evento que o documento assinado não confirma.

    🚨 CORRIGIR É ACRESCENTAR. O evento errado **continua lá**, visível na
    ficha, apontado por quem o anulou, com autoria e motivo. É o oposto do que o
    Harmonit faz (editar o PDF depois de assinado) e é o que mantém a resposta
    para "por que esta placa está ativa?".

    🚨 NÃO SE USA `SAI` NEM `RESCINDE` PARA ISSO. Os dois mentiriam: a placa
    ficaria SUBSTITUIDA ou RESCINDIDA, e a verdade é que ela **nunca esteve no
    contrato** -- foi a lista do Harmonit que a pôs lá, não o documento que o
    cliente assinou.

    ⚠️ Idempotente pelo índice único parcial de `corrige_evento_id`: a segunda
    tentativa levanta `JaAnulado` em vez de empilhar correção sobre correção.
    """
    linha = conn.execute(
        """SELECT e.termo_id, e.placa_chave, e.placa_texto, e.acao, t.cnpj, t.numero
             FROM contrato_evento e JOIN contrato_termo t ON t.id = e.termo_id
            WHERE e.id = ?""", (evento_id,)).fetchone()
    if not linha:
        raise ValueError(f"Evento {evento_id} não existe.")
    termo_id, chave_placa, placa_texto, acao, cnpj, numero = linha
    if acao == motor.ANULA:
        raise ValueError(f"O evento {evento_id} já é uma anulação — anular anulação não é correção.")

    ja = conn.execute("SELECT id FROM contrato_evento WHERE corrige_evento_id = ?",
                      (evento_id,)).fetchone()
    if ja:
        raise JaAnulado(f"O evento {evento_id} já foi anulado pelo evento {ja[0]}.")

    cur = conn.execute(
        """INSERT INTO contrato_evento
           (termo_id, placa_chave, placa_texto, acao, fonte, obs, corrige_evento_id, criado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (termo_id, chave_placa, placa_texto, motor.ANULA, motor.ASSINADO,
         f"{motivo} (anulado por {por})", evento_id, _agora()))
    recalcular(conn, cnpj)
    return {"anulacao_id": cur.lastrowid, "evento_anulado": evento_id, "termo_id": termo_id,
            "numero": numero, "placa": placa_texto, "cnpj": cnpj}


def correcoes_do_cliente(conn, cnpj: str) -> list:
    """As anulações deste cliente, para a ficha explicar o que foi corrigido.

    ⚠️ A ficha mostra o evento riscado E quem o anulou. Esconder a correção
    deixaria a linha do tempo mentindo por omissão: a placa simplesmente
    desapareceria do contrato, sem nada dizendo por quê.
    """
    # 🚨 O CRITÉRIO É APONTAR OUTRO EVENTO, NÃO SER UM `ANULA`. A primeira
    # versão filtrava por `acao = ANULA`, e quando a frente D trouxe a rescisão
    # confirmada pelo uso -- que é um `RESCINDE` com `corrige_evento_id` -- a
    # ficha parou de mostrar a correção: a placa fechava e nada na tela dizia
    # por quê. Quem define correção é o ponteiro, não a ação.
    return [{"anulacao_id": a, "evento_anulado": b, "termo": c, "placa": d,
             "motivo": e, "em": f, "acao": g, "fonte": h}
            for a, b, c, d, e, f, g, h in conn.execute(
                """SELECT n.id, n.corrige_evento_id, t.numero, n.placa_texto, n.obs,
                          n.criado_em, n.acao, n.fonte
                     FROM contrato_evento n
                     JOIN contrato_termo t ON t.id = n.termo_id
                    WHERE t.cnpj = ? AND n.corrige_evento_id IS NOT NULL
                    ORDER BY n.id""", (cnpj,))]


def candidatos_para_anexar(conn, cnpj: str, numero: str, empresa: str | None = None) -> list:
    """Termos do cliente com este número e SEM PDF guardado.

    ⚠️ Devolve lista, não um escolhido: a 2HM tem **dois** aditivos nº 2 na
    Clicksign, assinados em dias diferentes. Com mais de um candidato, quem
    decide é quem está na tela -- casar por número no escuro anexaria o
    documento ao termo errado.
    """
    sql = """SELECT id, numero, empresa, tipo, assinado, assinado_em, origem, harmonit_assinado
               FROM contrato_termo
              WHERE cnpj = ? AND numero = ? AND (hash IS NULL OR hash = '')"""
    p = [cnpj, str(numero or "")]
    if empresa:
        sql += " AND empresa = ?"
        p.append(empresa)
    return [{"id": i, "numero": n, "empresa": em, "tipo": t, "assinado": bool(a),
             "assinado_em": ae, "origem": o, "harmonit_assinado": ha}
            for i, n, em, t, a, ae, o, ha in conn.execute(sql, tuple(p))]


def confirmar_saida(conn, termo_id: int, placa: str, por: str) -> dict:
    """Grava quem SAI numa troca registrada no Harmonit. Só inserção.

    🚨 A ANOTAÇÃO NOMEIA SÓ QUEM ENTRA. Na Maxi Confort 8872 a anotação é
    *"FAC 5H30 - Cliente pediu alteração da placa"*, e no PDF do Harmonit as
    duas placas ficam no mesmo item, sem posição -- não existe dado que diga
    qual sai. Então a saída vem de gente, fica gravada com a autoria, e nada do
    que já estava lá é alterado (regra 13: não se inventa identificador).
    """
    linha = conn.execute(
        "SELECT cnpj, numero, troca_registrada, revisar_motivo FROM contrato_termo WHERE id = ?",
        (termo_id,)).fetchone()
    if not linha:
        raise ValueError(f"Termo {termo_id} não existe.")
    cnpj, numero, troca, motivo = linha
    if not troca:
        raise ValueError(f"O termo {numero} não tem troca registrada no Harmonit — "
                         "não há saída a confirmar.")
    placa = (placa or "").strip()
    if not placa:
        raise ValueError("Informe a placa que sai.")

    chave = motor.chave(placa)
    conhecidas = {motor.chave(p): p for p, in conn.execute(
        "SELECT placa_texto FROM contrato_evento WHERE termo_id = ?", (termo_id,))}
    if chave not in conhecidas:
        # Placa que não está no termo não sai dele. Aceitar criaria evento de
        # saída para um veículo que este contrato nunca sustentou.
        raise ValueError(f"{placa} não aparece no termo {numero}.")
    if any(True for _ in conn.execute(
            "SELECT 1 FROM contrato_evento WHERE termo_id = ? AND placa_chave = ? AND acao = ?",
            (termo_id, chave, motor.SAI))):
        raise ValueError(f"A saída de {placa} já está gravada no termo {numero}.")

    conn.execute(
        """INSERT INTO contrato_evento
           (termo_id, placa_chave, placa_texto, acao, fonte, obs, criado_em)
           VALUES (?,?,?,?,?,?,?)""",
        (termo_id, chave, conhecidas[chave], motor.SAI, motor.HARMONIT,
         f"saída confirmada por {por} (troca registrada no Harmonit)", _agora()))

    # O motivo da revisão era "troca sem confirmação de quem sai" -- resolvido.
    # ⚠️ O texto não se apaga: fica dito que foi resolvido, e por quem.
    if motivo and "confirmação de qual placa sai" in motivo:
        conn.execute(
            """UPDATE contrato_termo SET revisar = 0,
                      revisar_motivo = revisar_motivo || ' [resolvido: sai ' || ? || ', por ' || ? || ']'
                WHERE id = ?""", (conhecidas[chave], por, termo_id))

    situacoes = recalcular(conn, cnpj)
    return {"termo_id": termo_id, "numero": numero, "saiu": conhecidas[chave],
            "sustentadas": motor.ativas(situacoes)}


def marcar_revisado(conn, termo_id: int, por: str, nota: str | None = None) -> dict:
    """Baixa o flag `revisar` e registra quem olhou. O motivo NÃO se apaga.

    ⚠️ O motivo conta por que o termo entrou duvidoso (sem PDF, placa da lista
    do Harmonit em vez da do assinado, tipo não reconhecido). Apagá-lo faria a
    tela afirmar que nunca houve dúvida, e os 795 termos marcados perderiam a
    razão que a carga mediu.
    """
    linha = conn.execute("SELECT numero, revisar FROM contrato_termo WHERE id = ?",
                         (termo_id,)).fetchone()
    if not linha:
        raise ValueError(f"Termo {termo_id} não existe.")
    numero, revisar = linha
    conn.execute("INSERT INTO contrato_revisao (termo_id, por, em, nota) VALUES (?,?,?,?)",
                 (termo_id, por, _agora(), nota))
    conn.execute("UPDATE contrato_termo SET revisar = 0 WHERE id = ?", (termo_id,))
    return {"termo_id": termo_id, "numero": numero, "estava_marcado": bool(revisar)}


def definir_nome(conn, cnpj: str, nome: str, por: str, fonte: str = "manual") -> dict:
    """Grava o nome do cliente. `manual` sobrescreve; `carga`/`pdf`, não.

    ⚠️ Os nomes da carga vêm do índice do Harmonit e chegam sanitizados
    (`M_ D_ G_ COMERCIO...`). Por isso a correção à mão ganha, e por isso ela
    fica marcada: a próxima carga não desfaz o conserto.
    """
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do cliente.")
    agora = _agora()
    if fonte == "manual":
        conn.execute(
            """INSERT INTO contrato_cliente (cnpj, nome, nome_fonte, atualizado_em, atualizado_por)
               VALUES (?,?,?,?,?)
               ON CONFLICT(cnpj) DO UPDATE SET
                   nome = excluded.nome, nome_fonte = excluded.nome_fonte,
                   atualizado_em = excluded.atualizado_em,
                   atualizado_por = excluded.atualizado_por""",
            (cnpj, nome, fonte, agora, por))
    else:
        conn.execute(
            """INSERT OR IGNORE INTO contrato_cliente
               (cnpj, nome, nome_fonte, atualizado_em, atualizado_por)
               VALUES (?,?,?,?,?)""", (cnpj, nome, fonte, agora, por))
    # A prova é RELER, nunca o que acabamos de mandar gravar.
    return nome_do_cliente(conn, cnpj)


def nome_do_cliente(conn, cnpj: str) -> dict:
    linha = conn.execute(
        "SELECT nome, nome_fonte, atualizado_em, atualizado_por FROM contrato_cliente WHERE cnpj = ?",
        (cnpj,)).fetchone()
    if not linha:
        return {"cnpj": cnpj, "nome": None, "nome_fonte": None}
    return {"cnpj": cnpj, "nome": linha[0], "nome_fonte": linha[1],
            "atualizado_em": linha[2], "atualizado_por": linha[3]}


def termos_do_cliente(conn, cnpj: str) -> list:
    """Os termos do cliente no formato que o motor entende."""
    linhas = conn.execute(
        """SELECT id, numero, empresa, tipo, assinado, assinado_em, troca_registrada, a_definir,
                  origem, arquivo, revisar, revisar_motivo, harmonit_assinado
             FROM contrato_termo WHERE cnpj = ?""", (cnpj,)).fetchall()
    por_id = {}
    for (tid, numero, empresa, tipo, assinado, assinado_em, troca, adef,
         origem, arquivo, revisar, revisar_motivo, harmonit_assinado) in linhas:
        por_id[tid] = {
            "id": tid, "numero": numero, "empresa": empresa, "tipo": tipo,
            "assinado": bool(assinado), "assinado_em": assinado_em,
            "troca_registrada": troca, "a_definir": bool(adef), "origem": origem,
            "arquivo": arquivo, "revisar": bool(revisar), "revisar_motivo": revisar_motivo,
            # ⚠️ A marca do índice do Harmonit vai para a ficha SEPARADA de
            # `assinado`, porque não é prova: na 2HM os termos 255, 2207 e 2224
            # estão "sim" aqui e não têm nada na Clicksign. A tela mostra as
            # duas, e a diferença é a pergunta que ele precisa ver.
            "harmonit_assinado": harmonit_assinado,
            "eventos": [],
        }
    if not por_id:
        return []
    marcas = ",".join("?" * len(por_id))
    # 🆕 C7: `id` e `corrige_evento_id` entram aqui E em `termos_de_todos`, na
    # mesma mudança. 🚨 SEPARAR AS DUAS FARIA A FICHA E O CACHE DIVERGIREM: a
    # ficha recalcula por esta função e o grid lê o cache refeito pela outra --
    # uma enxergando a anulação e a outra não é tela que mente nos dois
    # sentidos ao mesmo tempo.
    for eid, tid, placa_texto, acao, fonte, recursos, valor, obs, corrige in conn.execute(
            f"""SELECT id, termo_id, placa_texto, acao, fonte, recursos, valor_mensal, obs,
                       corrige_evento_id
                  FROM contrato_evento WHERE termo_id IN ({marcas}) ORDER BY id""",
            tuple(por_id)):
        por_id[tid]["eventos"].append({"id": eid, "acao": acao, "placa": placa_texto, "fonte": fonte,
                                       "recursos": recursos, "valor_mensal": valor, "obs": obs,
                                       "corrige": corrige})
    return list(por_id.values())


def recalcular(conn, cnpj: str, hoje=None) -> dict:
    """Refaz `contrato_placa` do cliente a partir dos eventos. Idempotente."""
    situacoes = motor.situacao_das_placas(termos_do_cliente(conn, cnpj), hoje)
    _gravar_situacoes(conn, cnpj, situacoes)
    return situacoes


def _gravar_situacoes(conn, cnpj: str, situacoes: dict) -> None:
    """Refaz as linhas derivadas do cliente. Apaga e insere, nunca atualiza."""
    agora = _agora()
    conn.execute("DELETE FROM contrato_placa WHERE cnpj = ?", (cnpj,))
    for k, v in situacoes.items():
        conn.execute(
            """INSERT INTO contrato_placa
               (cnpj, placa_chave, placa_texto, situacao, base, termo_vigente, desde, aviso_ate, obs, calculado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (cnpj, k, v.get("placa") or k, v["situacao"], v.get("base"),
             str(v.get("termo_vigente") or ""), v.get("desde"), v.get("aviso_ate"), v.get("obs"), agora))


def termos_de_todos(conn) -> dict:
    """Todos os termos, por CNPJ, em **duas** consultas.

    ⚠️ Existe para o `recalcular_todos` não virar 1.462 consultas (duas por
    cliente × 731). O formato é o mesmo que `termos_do_cliente` devolve, porque
    quem consome é o mesmo motor.
    """
    por_id, por_cnpj = {}, {}
    for (tid, cnpj, numero, empresa, tipo, assinado, assinado_em, troca, adef,
         origem, arquivo, revisar, revisar_motivo) in conn.execute(
            """SELECT id, cnpj, numero, empresa, tipo, assinado, assinado_em, troca_registrada,
                      a_definir, origem, arquivo, revisar, revisar_motivo FROM contrato_termo"""):
        t = {"id": tid, "numero": numero, "empresa": empresa, "tipo": tipo,
             "assinado": bool(assinado), "assinado_em": assinado_em,
             "troca_registrada": troca, "a_definir": bool(adef), "origem": origem,
             "arquivo": arquivo, "revisar": bool(revisar), "revisar_motivo": revisar_motivo,
             "eventos": []}
        por_id[tid] = t
        por_cnpj.setdefault(cnpj, []).append(t)
    for eid, tid, placa_texto, acao, fonte, recursos, valor, obs, corrige in conn.execute(
            """SELECT id, termo_id, placa_texto, acao, fonte, recursos, valor_mensal, obs,
                      corrige_evento_id
                 FROM contrato_evento ORDER BY id"""):
        t = por_id.get(tid)
        if t is not None:
            t["eventos"].append({"id": eid, "acao": acao, "placa": placa_texto, "fonte": fonte,
                                 "recursos": recursos, "valor_mensal": valor, "obs": obs,
                                 "corrige": corrige})
    return por_cnpj


def recalcular_todos(conn, hoje=None) -> dict:
    """Refaz `contrato_placa` de TODOS os clientes.

    🚨 PRECISA EXISTIR PORQUE O CACHE ENVELHECE SOZINHO: o aviso prévio vence
    pelo calendário, sem nenhum evento novo para disparar a conta. Ler
    `contrato_placa` de ontem devolveria placa rescindida há 91 dias como se
    ainda estivesse em aviso -- e o grid é justamente uma leitura do cache.

    ⚠️ Idempotente: o `recalcular` de cada cliente apaga e refaz as linhas dele.
    """
    r = {"clientes": 0, "placas": 0}
    for cnpj, termos in termos_de_todos(conn).items():
        situacoes = motor.situacao_das_placas(termos, hoje)
        _gravar_situacoes(conn, cnpj, situacoes)
        r["clientes"] += 1
        r["placas"] += len(situacoes)
    return r


def ficha(conn, cnpj: str, hoje=None) -> dict:
    """Ficha do cliente: placas (situação derivada) e linha do tempo dos termos.

    ⚠️ CALCULA NA HORA e grava o cache no mesmo passo. Ler `contrato_placa`
    sem recalcular devolveria aviso prévio vencido como se ainda valesse -- o
    prazo passa sozinho, sem nenhum evento novo para disparar a conta.
    """
    termos = termos_do_cliente(conn, cnpj)
    situacoes = recalcular(conn, cnpj, hoje)

    def _ordem(t):
        try:
            return (0, int(t["numero"]), "")
        except (TypeError, ValueError):
            return (1, 0, str(t["numero"] or ""))

    placas = [dict(v, chave=k) for k, v in situacoes.items()]
    placas.sort(key=lambda p: (p["situacao"] != motor.ATIVA, p.get("placa") or ""))
    cliente = nome_do_cliente(conn, cnpj)
    return {
        "cnpj": cnpj,
        "nome": cliente.get("nome"),
        "nome_fonte": cliente.get("nome_fonte"),
        "placas": placas,
        "sustentadas": motor.ativas(situacoes),
        "termos": [{k: v for k, v in sorted(t.items()) if k != "eventos"} | {"eventos": t["eventos"]}
                   for t in sorted(termos, key=_ordem)],
        # 🆕 C7: o que a releitura do assinado corrigiu, com o evento riscado.
        "correcoes": correcoes_do_cliente(conn, cnpj),
        "sem_assinatura": [t["numero"] for t in termos if not t["assinado"]],
        "a_revisar": [{"numero": t["numero"], "motivo": t["revisar_motivo"]} for t in termos if t["revisar"]],
    }


# ── superfície assíncrona (o que o router chama) ─────────────────────────────

async def _exec(fn, *a, **kw):
    def _run():
        with _connect() as conn:
            contratos_tabelas.criar(conn)
            # `migrar` entra aqui também, e não só no `init_db`: as rotas leem
            # `harmonit_assinado`, e um banco criado por outro caminho (teste,
            # cópia antiga) não teria a coluna. É um `PRAGMA`, idempotente.
            contratos_tabelas.migrar(conn)
            r = fn(conn, *a, **kw)
            conn.commit()
            return r
    return await asyncio.get_running_loop().run_in_executor(None, _run)


async def gravar_termo(cnpj: str, lido: dict, **kw) -> dict:
    conteudo = kw.pop("conteudo", None)
    nome = kw.pop("nome_arquivo", None)
    h = hash_pdf(conteudo) if conteudo else None
    destino = None
    if conteudo:
        # Guarda o PDF que foi assinado. O nome usa o hash: arquivo de mesmo
        # nome vindo de cliente diferente não se sobrescreve.
        pasta = pasta_pdf()
        pasta.mkdir(parents=True, exist_ok=True)
        destino = f"{cnpj}_{str(lido.get('numero') or 'sem-numero')}_{h[:12]}.pdf"
        (pasta / destino).write_bytes(conteudo)

    def _grava(conn):
        tid = gravar(conn, cnpj, lido, hash_arquivo=h, arquivo=destino or nome, **kw)
        recalcular(conn, cnpj)
        return tid

    termo_id = await _exec(_grava)
    return {"termo_id": termo_id, "arquivo": destino, "hash": h}


async def ficha_do_cliente(cnpj: str) -> dict:
    return await _exec(ficha, cnpj)


async def anexar_pdf(termo_id: int, cnpj: str, lido: dict, **kw) -> dict:
    """Superfície assíncrona do modo anexar. Guarda o PDF com o mesmo padrão."""
    conteudo = kw.pop("conteudo")
    h = hash_pdf(conteudo)
    pasta = pasta_pdf()
    pasta.mkdir(parents=True, exist_ok=True)
    destino = f"{cnpj}_{str(lido.get('numero') or 'sem-numero')}_{h[:12]}.pdf"
    (pasta / destino).write_bytes(conteudo)
    r = await _exec(anexar_assinado, termo_id, cnpj, lido,
                    hash_arquivo=h, arquivo=destino, **kw)
    return dict(r, arquivo=destino, hash=h)


async def listar_candidatos(cnpj: str, numero: str, empresa: str | None = None) -> list:
    return await _exec(candidatos_para_anexar, cnpj, numero, empresa)


async def confirmar_saida_do_termo(termo_id: int, placa: str, por: str) -> dict:
    return await _exec(confirmar_saida, termo_id, placa, por)


async def revisado(termo_id: int, por: str, nota: str | None = None) -> dict:
    return await _exec(marcar_revisado, termo_id, por, nota)


async def nomear_cliente(cnpj: str, nome: str, por: str) -> dict:
    return await _exec(definir_nome, cnpj, nome, por)
