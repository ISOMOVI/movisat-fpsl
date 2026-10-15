"""Carga dos PDFs ASSINADOS da Clicksign (`C7`). 2026-10-14.

A `CTR_1.1` nasceu sem documento: os 4.599 termos entraram pelos CSVs da
auditoria, e **nenhum** tem PDF guardado. Pior, a carga gravou a lista de placas
do **Harmonit** -- e o PDF do Harmonit é editado DEPOIS de assinado. Em 412
termos as duas listas divergem, e é isso que faz a ficha dar 2.979 placas
sustentadas contra 2.811 da planilha.

Este módulo lê o documento ASSINADO e faz três coisas, nesta ordem de valor:
  1. guarda o PDF no termo (a ação "PDF" do grid passa a existir);
  2. **corrige** pelo assinado, lançando `ANULA` onde a lista do Harmonit pôs
     placa que o documento não traz -- sem apagar nada;
  3. preenche o valor mensal onde o documento declara.

🚨 TRÊS DESTINOS, E "FILA" NÃO É FALHA. Cada documento vai para *anexado*,
*documento só* ou *fila da tela*. A fila é onde mora tudo que exige uma pessoa:
CNPJ divergente, número ambíguo entre Instituto e Movisat, tipo que não casa.
Forçar esses casos seria anexar o assinado ao contrato errado, e isso cancela
ou cria cobrança no lugar errado.

🚨 A CHAVE É O NÚMERO LIDO DENTRO DO PDF, NUNCA O DO NOME DO ARQUIVO. Medido na
2HM: dois documentos chamados `2 - aditivo - assinado [...]` são, de fato, os
assinados dos termos **2207** e **2224** -- as datas de envio (07/07/2021 e
03/08/2021) batem exatamente com as dos dois termos. Tratá-los pelo nome
criaria dois termos falsos e deixaria 2207 e 2224 para sempre "sem assinatura".

🚨 SÓ `assinado` ENTRA. Cancelado, rascunho e pendente são barrados aqui E não
são nem copiados para a VPS -- a 2HM tem um `3520 cancelado` com o mesmo número
de um `3520 assinado`.

⚠️ `journal_mode=delete` no banco: cada escrita tranca o serviço. Então é **uma
transação curta por PDF**, e o livro-razão (`contrato_carga_pdf`) é o que
permite parar no meio e continuar sem reprocessar.
"""
import hashlib
import json
import logging
import re
from pathlib import Path

from . import contratos_eventos as motor
from . import contratos_leitura as leitura
from . import contratos_registro as registro
from . import contratos_tabelas

log = logging.getLogger("fpsl.contratos_assinados")

# Só este estado entra. É lista branca, não negra: tipo novo na Clicksign fica
# de fora por omissão, que é o lado seguro.
ESTADOS_QUE_ENTRAM = {"assinado"}

# ── o tipo do nome do arquivo → perfil de leitura ───────────────────────────
# ⚠️ O NOME DO ARQUIVO NÃO É VOCABULÁRIO CONFIÁVEL: nos 2.825 assinados há ~50
# grafias, incluindo `subtituicao`, `adtivo`, `resscisao`, `dowgrade` e palavras
# soltas que vieram do nome do cliente. Por isso o mapa casa por RADICAL, e o
# que não casa não é chutado -- vira "documento só" ou fila.
_RADICAIS = (
    ("substitu", "substituicao"), ("subtitu", "substituicao"), ("substuic", "substituicao"),
    ("troca", "substituicao"),
    ("ressarc", "ressarcimento_com_termo"),
    ("rescis", "rescisao"), ("resscis", "rescisao"), ("distrat", "rescisao"),
    ("upgrade", "upgrade"), ("dowgrade", "upgrade"), ("downgrade", "upgrade"),
    ("aditiv", "aditivo"), ("adtiv", "aditivo"), ("aditic", "aditivo"), ("aditament", "aditivo"),
    ("contrat", "contrato_novo"), ("teste", "contrato_novo"), ("comodat", "contrato_novo"),
)

# 🚨 TRANSFERÊNCIA NÃO TEM PERFIL ÚNICO: ela é dois documentos, um por titular, e
# `transferencia_termo_novo` está em `PERFIS_FORA`. Vai para a fila com o motivo.
_FILA_POR_TIPO = ("transferen",)

# Documento que não lista veículo: guarda o PDF e não lê placa. O 3465 da 2HM é
# o caso -- é uma renegociação, com 0 placas. Ler como contrato marcaria o termo
# "a revisar" por não confirmar nada, o que seria defeito inventado por nós.
_DOC_SO = ("acordo", "negocia", "minuta", "atualiza", "outros", "aviso", "carta")

# O `tipo` que a carga gravou no termo → a família de perfil que se espera.
# Serve de CONFERÊNCIA contra o nome do arquivo: discordando, vai para a fila.
_FAMILIA_DO_TIPO_NO_BANCO = {
    "CONTRATO": "contrato_novo", "EMPRESTIMO_TESTE": "contrato_novo",
    "ADITIVO": "aditivo", "UPGRADE": "upgrade",
    "RESCISAO": "rescisao", "RESCISAO_FINAL": "rescisao",
    "RESSARCIMENTO_RESCISAO": "ressarcimento_com_termo",
    "RESSARCIMENTO_RESCISAO_FINAL": "ressarcimento_com_termo",
    "SUBSTITUICAO": "substituicao",
}

# Ações que, anuladas, significam "esta placa nunca esteve neste termo".
_ANULAVEIS = (motor.ENTRA, motor.SAI, motor.RESCINDE, motor.UPGRADE)

# Identificador com 10+ caracteres que é prefixo de outro é a MESMA placa com o
# chassi cortado na quebra de linha (`9BD281A22MYV` × `9BD281A22MYV30872`).
# Tratar como placa diferente geraria anulação e entrada no mesmo passo.
_MIN_PREFIXO = 10


def sha256_do_arquivo(caminho) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for pedaco in iter(lambda: fh.read(1 << 20), b""):
            h.update(pedaco)
    return h.hexdigest()


def perfil_do_nome(tipo_nome: str):
    """Devolve `(perfil, rota, motivo)`. `rota` é 'ler', 'doc_so' ou 'fila'."""
    t = (tipo_nome or "").strip().lower()
    for radical in _FILA_POR_TIPO:
        if radical in t:
            return None, "fila", f"tipo '{tipo_nome}': transferência tem um documento por titular, decidir na tela"
    for radical, perfil in _RADICAIS:
        if radical in t:
            return perfil, "ler", None
    for radical in _DOC_SO:
        if radical in t:
            return None, "doc_so", f"tipo '{tipo_nome}' não lista veículo: o PDF é guardado, sem ler placa"
    return None, "doc_so", f"tipo '{tipo_nome}' não reconhecido: o PDF é guardado, sem ler placa"


def _mesma_familia(perfil: str, tipo_no_banco: str | None) -> bool:
    """O nome do arquivo e o `tipo` do termo contam a mesma história?

    ⚠️ Quando o `tipo` do banco não é reconhecido (44 termos têm no lugar dele a
    primeira linha do texto do PDF), não há conferência a fazer -- e isso não é
    motivo para recusar: é motivo para não usar essa fonte.
    """
    familia = _FAMILIA_DO_TIPO_NO_BANCO.get((tipo_no_banco or "").strip().upper())
    if familia is None:
        return True
    return familia == perfil


def _prefixo_de(a: str, b: str) -> bool:
    if len(a) < _MIN_PREFIXO or len(b) < _MIN_PREFIXO:
        return False
    # ⚠️ CONTÉM, não só começa: o identificador certo pode vir NO MEIO de uma
    # linha descritiva (`... Amarela- 1F9210GXKED520143 - 2014`). Tratar isso
    # como placa diferente anularia o identificador bom e deixaria o lixo.
    return a.startswith(b) or b.startswith(a) or a in b or b in a


# Nenhuma placa ou chassi real passa de 17 caracteres (VIN tem 17).
_MAX_IDENTIFICADOR = 20
_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]{4,}")


def identificador_suspeito(texto: str) -> str | None:
    """A leitura devolveu identificador, ou a linha descritiva inteira?

    🚨 ISTO É DEFEITO MEDIDO, NÃO HIPÓTESE. Na primeira passada da 2HM o
    extrator devolveu, como se fossem placas:
        `Cod: 01-06 - Escavadeira Hidraulica- JohnDeere- 210G - Amarela- 1F9210GXKED520143 - 2014`
        `Escavadeira PC350, Komatsu, PC350 LC-8 B10217`
        `1BZ310KXJEC000130 (ID: 007842126)`
        `Cod: 01-05 (ID: 205727026)`
    -- e a carga criou evento com isso E anulou o identificador correto que
    estava na base. **Identificador inventado é pior que identificador
    faltando** (regra 13, a família do `RFD 2447`): a cobrança passa a apontar
    para um veículo que não existe.

    ⚠️ A SAÍDA NÃO É TENTAR DECIFRAR A LINHA. Quem lê documento é o
    `pdf_extractor`, da aba Operações, que é **intocável**. Se a leitura veio
    descritiva, o documento inteiro vai para a fila e uma pessoa decide -- é o
    mesmo princípio de "não se inventa identificador", aplicado a nós mesmos.
    """
    bruto = (texto or "").strip()
    if not bruto:
        return None
    if len(motor.chave(bruto)) > _MAX_IDENTIFICADOR:
        return f"{len(motor.chave(bruto))} caracteres: é linha descritiva, não identificador"
    if any(c in bruto for c in (":", ",", ";")):
        return "tem pontuação de frase (`:`, `,` ou `;`)"
    if bruto.count(" ") >= 3:
        return "tem 3 espaços ou mais: é frase, não identificador"
    palavras = [p for p in _PALAVRA.findall(bruto) if not p.isupper()]
    if palavras:
        return f"contém palavra escrita ({palavras[0]}), não identificador"
    return None


def leitura_confiavel(lido: dict) -> tuple:
    """Todos os identificadores lidos parecem identificador? `(bool, motivo)`."""
    for e in (lido.get("eventos") or []):
        porque = identificador_suspeito(e.get("placa"))
        if porque:
            return False, (f"a leitura devolveu '{str(e.get('placa'))[:60]}' no lugar da placa "
                           f"({porque}): decidir na tela")
    return True, None


def pode_corrigir(termo: dict, lido: dict, nao_confirmados: list) -> tuple:
    """Pode lançar `ANULA` para o que o assinado não confirma? `(bool, motivo)`.

    🚨 CADA RECUSA AQUI É UM CASO MEDIDO, e na dúvida a resposta é NÃO -- o
    termo fica "a revisar", como já ficava, e uma pessoa decide.
    """
    if not nao_confirmados:
        return False, None
    if termo.get("troca_registrada"):
        # A placa a mais pode ser troca legítima pedida pelo cliente, e a
        # anotação que prova isso só existe no PDF do Harmonit.
        return False, "termo com troca registrada no Harmonit: a diferença pode ser troca legítima"
    if termo.get("a_definir"):
        return False, "termo assinado com 'a definir': a placa real foi preenchida depois, no Harmonit"
    if not (lido.get("eventos") or []):
        # Extração que não achou placa nenhuma não é prova de que o documento
        # não as tem -- é prova de que não conseguimos ler.
        return False, "o documento assinado não trouxe nenhuma placa: leitura insuficiente para corrigir"
    total = len(lido["eventos"]) + len(nao_confirmados)
    if len(nao_confirmados) * 2 > total:
        return False, (f"o assinado não confirma {len(nao_confirmados)} de {total} placas: "
                       "diferença grande demais para correção automática")
    return True, None


def _eventos_do_termo(conn, termo_id: int) -> list:
    return [{"id": a, "chave": b, "placa": c, "acao": d}
            for a, b, c, d in conn.execute(
                """SELECT id, placa_chave, placa_texto, acao FROM contrato_evento
                    WHERE termo_id = ? AND acao IN (?,?,?,?) ORDER BY id""",
                (termo_id, *_ANULAVEIS))]


def corrigir_pelo_assinado(conn, termo_id: int, nao_confirmados: list, novos: list,
                           chave_clicksign: str, por: str) -> dict:
    """Lança `ANULA` para cada placa que o documento assinado não traz."""
    r = {"anulados": [], "pulados": []}
    chaves_novas = [motor.chave(p) for p in (novos or [])]
    for evento in _eventos_do_termo(conn, termo_id):
        if evento["placa"] not in nao_confirmados:
            continue
        # ⚠️ Chassi cortado na quebra de linha é a MESMA placa, não placa
        # diferente: anular e acrescentar no mesmo passo seria inventar troca.
        if any(_prefixo_de(evento["chave"], k) for k in chaves_novas):
            r["pulados"].append(evento["placa"])
            continue
        try:
            registro.anular_evento(
                conn, evento["id"], por,
                f"C7: constava na lista do Harmonit; o assinado {chave_clicksign} não traz esta placa")
            r["anulados"].append(evento["placa"])
        except registro.JaAnulado:
            r["pulados"].append(evento["placa"])
    return r


# ── livro-razão ─────────────────────────────────────────────────────────────

def ja_processado(conn, sha: str) -> str | None:
    linha = conn.execute("SELECT status FROM contrato_carga_pdf WHERE sha256 = ?", (sha,)).fetchone()
    return linha[0] if linha else None


def anotar(conn, sha: str, reg: dict, status: str, motivo=None, termo_id=None,
           lote=None, antes=None) -> None:
    conn.execute(
        """INSERT INTO contrato_carga_pdf
           (sha256, chave_clicksign, cnpj, arquivo, estado_origem, numero_no_nome, numero_no_pdf,
            status, motivo, termo_id, lote, antes_json, em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(sha256) DO UPDATE SET
             status = excluded.status, motivo = excluded.motivo, termo_id = excluded.termo_id,
             lote = excluded.lote, antes_json = excluded.antes_json, em = excluded.em""",
        (sha, reg.get("chave_clicksign"), reg.get("cnpj"), reg.get("arquivo"),
         reg.get("estado"), str(reg.get("numero") or ""), reg.get("numero_no_pdf"),
         status, motivo, termo_id, lote,
         json.dumps(antes, ensure_ascii=False) if antes else None, registro._agora()))


def _antes_do_termo(conn, termo_id: int) -> dict:
    (assinado, assinado_em, hash_, arquivo, revisar, motivo, por) = conn.execute(
        """SELECT assinado, assinado_em, hash, arquivo, revisar, revisar_motivo, enviado_por
             FROM contrato_termo WHERE id = ?""", (termo_id,)).fetchone()
    return {"assinado": assinado, "assinado_em": assinado_em, "hash": hash_, "arquivo": arquivo,
            "revisar": revisar, "revisar_motivo": motivo, "enviado_por": por}


# ── o passo de um documento ─────────────────────────────────────────────────

def escolher_termo(conn, cnpj: str, numero: str, reg: dict, lido: dict | None):
    """Qual termo recebe este documento. `(termo_id|None, motivo_da_fila|None)`.

    🚨 DESEMPATE SÓ POR PROVA OBJETIVA. Medido: `(cnpj, numero, empresa)` não tem
    duplicata, mas **555 pares `(cnpj, numero)` existem nas duas empresas** -- o
    número do termo repete entre Instituto e Movisat, e o nome do arquivo da
    Clicksign não diz qual é. Sem prova, vai para a fila: adivinhar a empresa
    anexaria o assinado ao contrato errado.
    """
    candidatos = registro.candidatos_para_anexar(conn, cnpj, numero)
    if not candidatos:
        existe = conn.execute(
            "SELECT id, hash FROM contrato_termo WHERE cnpj = ? AND numero = ?",
            (cnpj, str(numero))).fetchall()
        if existe:
            return None, (f"o termo {numero} já tem documento guardado: este é um segundo "
                          "assinado para o mesmo número, decidir na tela")
        return None, f"não existe termo {numero} neste cliente: documento só na Clicksign"
    if len(candidatos) == 1:
        return candidatos[0]["id"], None

    # 1ª prova: a data. A da Clicksign (assinatura ou envio) bate com a do termo.
    datas = {d for d in (reg.get("assinado_em"), reg.get("enviado_em")) if d}
    por_data = [c for c in candidatos if c.get("assinado_em") and c["assinado_em"] in datas]
    if len(por_data) == 1:
        return por_data[0]["id"], None

    # 2ª prova: o tipo do termo no banco concorda com o perfil lido.
    if lido:
        por_tipo = [c for c in candidatos if _mesma_familia(lido["perfil"], c.get("tipo"))]
        if len(por_tipo) == 1:
            return por_tipo[0]["id"], None

    # 3ª prova: as placas do documento aparecem em um único candidato.
    if lido:
        do_doc = {motor.chave(e["placa"]) for e in (lido.get("eventos") or []) if e.get("placa")}
        if do_doc:
            com_interseccao = []
            for c in candidatos:
                chaves = {k for (k,) in conn.execute(
                    "SELECT DISTINCT placa_chave FROM contrato_evento WHERE termo_id = ?", (c["id"],))}
                if chaves & do_doc:
                    com_interseccao.append(c)
            if len(com_interseccao) == 1:
                return com_interseccao[0]["id"], None

    empresas = ", ".join(sorted({c.get("empresa") or "?" for c in candidatos}))
    return None, (f"{len(candidatos)} termos {numero} sem documento ({empresas}) e nenhuma prova "
                  "objetiva de qual é: decidir na tela")


def processar_um(conn, reg: dict, caminho: Path, lote: str, por: str, dry_run: bool) -> dict:
    """Um documento, uma transação. Devolve o que aconteceu, para o relatório."""
    sha = sha256_do_arquivo(caminho)
    estado = (reg.get("estado") or "").strip().lower()
    # O número do NOME entra no relatório desde o começo (o de dentro do PDF
    # substitui depois, quando houver): fila sem número na linha obriga quem lê
    # o relatório a procurar o caso no arquivo.
    saida = {"arquivo": reg.get("arquivo"), "cnpj": reg.get("cnpj"), "sha256": sha,
             "numero": str(reg.get("numero") or "") or None}

    anterior = ja_processado(conn, sha)
    if anterior in ("anexado", "doc_so"):
        return dict(saida, status="pulado", motivo=f"já processado antes como {anterior}")

    # 🚨 Lista branca de estado. É a terceira camada da mesma guarda: a primeira
    # é não copiar o arquivo para a VPS, a segunda é o filtro do plano.
    if estado not in ESTADOS_QUE_ENTRAM:
        if not dry_run:
            anotar(conn, sha, reg, "rejeitado", f"estado de origem '{estado}' não entra", lote=lote)
        return dict(saida, status="rejeitado", motivo=f"estado '{estado}'")

    cnpj = "".join(c for c in (reg.get("cnpj") or "") if c.isdigit())
    if len(cnpj) not in (11, 14):
        if not dry_run:
            anotar(conn, sha, reg, "fila", "cliente sem CNPJ/CPF na pasta", lote=lote)
        return dict(saida, status="fila", motivo="cliente sem CNPJ/CPF")

    perfil, rota, motivo_perfil = perfil_do_nome(reg.get("tipo"))

    if rota == "fila":
        if not dry_run:
            anotar(conn, sha, reg, "fila", motivo_perfil, lote=lote)
        return dict(saida, status="fila", motivo=motivo_perfil)

    lido = None
    if rota == "ler":
        try:
            with open(caminho, "rb") as fh:
                lido = leitura.ler(fh, perfil)
        except Exception as e:                                   # pragma: no cover
            if not dry_run:
                anotar(conn, sha, reg, "fila", f"não deu para ler o documento: {e}", lote=lote)
            return dict(saida, status="fila", motivo=f"leitura falhou: {e}")
        reg["numero_no_pdf"] = lido.get("numero")

        # 🚨 ANTES DE QUALQUER ESCRITA: a leitura devolveu identificador ou a
        # linha descritiva inteira? Na primeira passada da 2HM ela devolveu a
        # linha, e a carga criou evento com lixo E anulou o identificador bom.
        confiavel, motivo_leitura = leitura_confiavel(lido)
        if not confiavel:
            if not dry_run:
                anotar(conn, sha, reg, "fila", motivo_leitura, lote=lote)
            return dict(saida, status="fila", motivo=motivo_leitura)

    # 🚨 O NÚMERO DE DENTRO DO PDF GANHA. O do nome do arquivo é conferência --
    # na 2HM, dois arquivos chamados "2" são os assinados de 2207 e 2224.
    numero = (reg.get("numero_no_pdf") or "").strip() or str(reg.get("numero") or "").strip()
    if not numero:
        if not dry_run:
            anotar(conn, sha, reg, "fila", "sem número no documento nem no nome do arquivo", lote=lote)
        return dict(saida, status="fila", motivo="sem número")

    termo_id, motivo_fila = escolher_termo(conn, cnpj, numero, reg, lido)
    if termo_id is None:
        if not dry_run:
            anotar(conn, sha, reg, "fila", motivo_fila, lote=lote)
        return dict(saida, status="fila", motivo=motivo_fila, numero=numero)

    campos = ("numero", "empresa", "tipo", "troca_registrada", "a_definir")
    termo = dict(zip(campos, conn.execute(
        f"SELECT {', '.join(campos)} FROM contrato_termo WHERE id = ?", (termo_id,)).fetchone()))

    # Conferência das três fontes: nome do arquivo × tipo do termo × leitura.
    if rota == "ler" and not _mesma_familia(perfil, termo.get("tipo")):
        motivo = (f"o nome do arquivo diz '{reg.get('tipo')}' e o termo {numero} está como "
                  f"'{termo.get('tipo')}': decidir na tela")
        if not dry_run:
            anotar(conn, sha, reg, "fila", motivo, termo_id=termo_id, lote=lote)
        return dict(saida, status="fila", motivo=motivo, numero=numero)

    if dry_run:
        return dict(saida, status=("anexaria" if rota == "ler" else "guardaria o documento"),
                    numero=numero, termo_id=termo_id, empresa=termo.get("empresa"),
                    placas_no_assinado=len((lido or {}).get("eventos") or []))

    antes = _antes_do_termo(conn, termo_id)

    # 🚨 O PDF VAI PARA A PASTA DE DOCUMENTOS ANTES DE O TERMO APONTAR PARA ELE.
    # Na primeira passada o caminho "documento só" gravou o NOME do arquivo do
    # lote sem copiar nada: o termo ficava apontando para um arquivo que não
    # existia na pasta, e a ação "PDF" do grid responderia *"está registrado
    # como X, mas não está na pasta de documentos"*. Medido: 5 termos com
    # arquivo contra 4 PDFs em disco.
    # `.tmp` + rename: se cair no meio, não fica PDF truncado com nome de bom.
    destino = registro.pasta_pdf() / f"{cnpj}_{numero}_{sha[:12]}.pdf"
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".pdf.tmp")
    tmp.write_bytes(caminho.read_bytes())
    tmp.replace(destino)

    if rota == "doc_so":
        conn.execute(
            """UPDATE contrato_termo
                  SET assinado = 1, assinado_em = COALESCE(?, assinado_em), hash = ?, arquivo = ?,
                      enviado_por = ?, enviado_em = ?
                WHERE id = ?""",
            (reg.get("assinado_em"), sha, destino.name, por, registro._agora(), termo_id))
        registro.recalcular(conn, cnpj)
        anotar(conn, sha, reg, "doc_so", motivo_perfil, termo_id=termo_id, lote=lote, antes=antes)
        return dict(saida, status="doc_so", numero=numero, termo_id=termo_id)

    try:
        r = registro.anexar_assinado(
            conn, termo_id, cnpj, lido, assinado_em=reg.get("assinado_em"),
            enviado_por=por, hash_arquivo=sha, arquivo=destino.name)
    except registro.TermoJaGravado as e:
        anotar(conn, sha, reg, "rejeitado", str(e), termo_id=termo_id, lote=lote)
        return dict(saida, status="rejeitado", motivo=str(e))
    except ValueError as e:
        anotar(conn, sha, reg, "fila", str(e), termo_id=termo_id, lote=lote)
        return dict(saida, status="fila", motivo=str(e))

    correcao = {"anulados": [], "pulados": []}
    pode, motivo_nao = pode_corrigir(termo, lido, r.get("nao_confirmados") or [])
    if pode:
        correcao = corrigir_pelo_assinado(
            conn, termo_id, r["nao_confirmados"], r.get("eventos_novos") or [],
            reg.get("chave_clicksign") or sha[:8], por)
        if correcao["anulados"]:
            # O termo foi marcado "a revisar" pelo próprio anexo; a correção
            # resolveu o motivo. ⚠️ O texto do motivo NÃO se apaga.
            registro.marcar_revisado(
                conn, termo_id, por,
                f"C7: corrigido pelo assinado — {len(correcao['anulados'])} placa(s) anulada(s)")

    registro.recalcular(conn, cnpj)
    anotar(conn, sha, reg, "anexado",
           motivo_nao or (f"{len(correcao['anulados'])} anulada(s)" if correcao["anulados"] else None),
           termo_id=termo_id, lote=lote, antes=antes)
    return dict(saida, status="anexado", numero=numero, termo_id=termo_id,
                eventos_novos=r.get("eventos_novos") or [],
                nao_confirmados=r.get("nao_confirmados") or [],
                anulados=correcao["anulados"], pulados_no_prefixo=correcao["pulados"],
                nao_corrigiu_porque=motivo_nao)


def processar(plano: Path, pasta: Path, lote: str, por: str = "c7-releitura",
              dry_run: bool = True, so_cnpj: str | None = None, limite: int | None = None) -> dict:
    """Roda o plano inteiro, **um documento por transação**.

    ⚠️ Transação curta de propósito: o banco está em `journal_mode=delete` e
    cada escrita tranca o serviço. Lote grande numa transação só deixaria o
    painel parado por minutos.
    """
    linhas = []
    with open(plano, encoding="utf-8") as fh:
        for linha in fh:
            if not linha.strip():
                continue
            reg = json.loads(linha)
            if so_cnpj and "".join(c for c in (reg.get("cnpj") or "") if c.isdigit()) != so_cnpj:
                continue
            linhas.append(reg)
            if limite and len(linhas) >= limite:
                break

    relatorio = {"lote": lote, "dry_run": dry_run, "documentos": len(linhas), "por_status": {},
                 "detalhe": []}
    for reg in linhas:
        caminho = pasta / reg["arquivo"]
        if not caminho.exists():
            r = {"arquivo": reg.get("arquivo"), "status": "faltando",
                 "motivo": "o arquivo não está na pasta do lote"}
        else:
            with registro._connect() as conn:
                conn.execute("PRAGMA busy_timeout = 10000")
                contratos_tabelas.criar(conn)
                contratos_tabelas.migrar(conn)
                try:
                    r = processar_um(conn, reg, caminho, lote, por, dry_run)
                    conn.commit()
                except Exception as e:                           # pragma: no cover
                    conn.rollback()
                    log.exception("falha no documento %s", reg.get("arquivo"))
                    r = {"arquivo": reg.get("arquivo"), "status": "erro", "motivo": str(e)}
        relatorio["por_status"][r["status"]] = relatorio["por_status"].get(r["status"], 0) + 1
        relatorio["detalhe"].append(r)
    return relatorio


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    p = argparse.ArgumentParser(description="Carga dos PDFs assinados (C7)")
    p.add_argument("plano", help="JSONL com uma linha por documento")
    p.add_argument("pasta", help="pasta onde os PDFs do lote estão")
    p.add_argument("--lote", required=True)
    p.add_argument("--cnpj", default=None, help="roda só este cliente")
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--por", default="c7-releitura")
    p.add_argument("--valendo", action="store_true",
                   help="sem isto, é ensaio: nada é gravado")
    a = p.parse_args()
    r = processar(Path(a.plano), Path(a.pasta), a.lote, a.por,
                  dry_run=not a.valendo, so_cnpj=a.cnpj, limite=a.limite)
    print(json.dumps(r, ensure_ascii=False, indent=2))
