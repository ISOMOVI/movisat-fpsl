"""Carga histórica da Gestão de Contratos (`CTR_1.1`) — etapa C5. 2026-10-13.

Lê o JSONL que a auditoria produziu (`exportar_para_ctr.py`) e grava termos e
eventos dos 731 clientes. Decisão dele em 13/10: **a carga entra**, e o que não
fechou entra marcado "a revisar".

🚨 NÃO RELÊ PDF. A auditoria já leu os 4.266 documentos e aplicou as regras;
reler na VPS levaria horas para chegar ao mesmo lugar. O que entra aqui é o
resultado dela, traduzido em eventos — e **marcado `origem="carga"`**, para
nunca se confundir com o que subiu pela tela.

🚨 SEM HASH DE PDF, A CHAVE É (cnpj, numero, empresa). A carga não guarda
documento, então o `UNIQUE(hash)` não protege. Sem esta checagem, rodar a carga
duas vezes **dobraria** 12.114 eventos — e evento dobrado dobra placa no
contrato. Rodar de novo é seguro: o que já existe é pulado.

⚠️ TERMO SEM ASSINATURA ENTRA, COM OS EVENTOS. Filtrar aqui tiraria do motor a
informação de que a lacuna existe, e é justamente o motor que aplica a regra
dele ("não assinado só conta se falta dos dois lados"). 1.184 termos estão
nessa situação.
"""
import json
import logging

from . import contratos_eventos as motor
from . import contratos_registro as registro
from . import contratos_tabelas

log = logging.getLogger("fpsl.contratos_carga")


def _ja_gravados(conn) -> set:
    return {(c, n, e) for c, n, e in
            conn.execute("SELECT cnpj, numero, empresa FROM contrato_termo")}


def _so_digitos(v) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def _agora() -> str:
    return registro._agora()


def importar_nomes(conn, caminho: str) -> dict:
    """Grava o nome do cliente que o arquivo da carga trazia (campo `cliente`).

    🚨 ESTE É O ÚNICO LUGAR ONDE O NOME DOS 731 CLIENTES EXISTE. A `CTR_1.1`
    gravou só o CNPJ; a tabela `clientes` do FPSL tem apenas `harmonit_id` e
    `cnpjcpf`, e o cache da WESO cobre 304 clientes -- a 2HM não está nele.
    Grid de 731 linhas sem nome não se usa.

    ⚠️ `INSERT OR IGNORE`: nome já gravado NÃO é tocado. É o que preserva a
    correção à mão (`nome_fonte='manual'`), porque o nome da carga vem do
    índice do Harmonit e chega sanitizado (`M_ D_ G_ COMERCIO...`). Rodar duas
    vezes não muda nada -- conferido relendo a tabela, não a resposta.
    """
    contratos_tabelas.criar(conn)
    r = {"lidos": 0, "gravados": 0, "sem_nome": 0}
    agora = _agora()
    with open(caminho, encoding="utf-8") as fh:
        for linha in fh:
            try:
                c = json.loads(linha)
            except ValueError:
                continue
            cnpj = _so_digitos(c.get("cnpj"))
            nome = (c.get("cliente") or "").strip()
            if not cnpj:
                continue
            r["lidos"] += 1
            if not nome:
                r["sem_nome"] += 1
                continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO contrato_cliente
                   (cnpj, nome, nome_fonte, atualizado_em, atualizado_por)
                   VALUES (?,?,?,?,?)""",
                (cnpj, nome, "carga", agora, "carga-auditoria-13-10"))
            r["gravados"] += cur.rowcount or 0
    return r


def importar_harmonit_assinado(conn, caminho: str) -> dict:
    """Preenche `contrato_termo.harmonit_assinado` a partir do mesmo arquivo.

    ⚠️ NÃO É PROVA DE ASSINATURA -- é a marca do ÍNDICE do Harmonit, e a regra
    dele é "vale o assinado". Fica em coluna própria justamente para a tela
    poder mostrar a diferença: na 2HM, os termos 255, 2207 e 2224 estão "sim"
    aqui e não têm nada na Clicksign.

    🚨 Só escreve onde está NULO. A chave é `(cnpj, numero, empresa)`, a mesma
    da carga -- o número do termo repete entre Instituto e Movisat.
    """
    contratos_tabelas.criar(conn)
    contratos_tabelas.migrar(conn)
    # ⚠️ `ja_tinha` e `sem_termo` são contagens SEPARADAS de propósito: juntas,
    # a segunda rodada diria "não achei 4.599 termos" quando o certo é "já
    # estavam preenchidos" -- número que mente é defeito, inclusive em log.
    r = {"atualizados": 0, "sem_marca": 0, "ja_tinha": 0, "sem_termo": 0}
    with open(caminho, encoding="utf-8") as fh:
        for linha in fh:
            try:
                c = json.loads(linha)
            except ValueError:
                continue
            cnpj = _so_digitos(c.get("cnpj"))
            for t in c.get("termos") or []:
                marca = t.get("harmonit_assinado")
                if marca in (None, ""):
                    r["sem_marca"] += 1
                    continue
                cur = conn.execute(
                    """UPDATE contrato_termo SET harmonit_assinado = ?
                        WHERE cnpj = ? AND numero = ? AND empresa = ?
                          AND harmonit_assinado IS NULL""",
                    (str(marca), cnpj, str(t.get("numero") or ""),
                     t.get("empresa") or "MOVISAT"))
                if cur.rowcount:
                    r["atualizados"] += cur.rowcount
                    continue
                existe = conn.execute(
                    """SELECT 1 FROM contrato_termo
                        WHERE cnpj = ? AND numero = ? AND empresa = ? LIMIT 1""",
                    (cnpj, str(t.get("numero") or ""), t.get("empresa") or "MOVISAT")).fetchone()
                r["ja_tinha" if existe else "sem_termo"] += 1
    return r


def importar(conn, caminho: str, limite_clientes: int | None = None) -> dict:
    """Grava o que ainda não existe. Idempotente por (cnpj, numero, empresa).

    ⚠️ `limite_clientes` limita os TERMOS, não os nomes: nome e marca do
    Harmonit entram pelo arquivo inteiro, porque o grid precisa dos 731.
    """
    contratos_tabelas.criar(conn)
    contratos_tabelas.migrar(conn)
    existentes = _ja_gravados(conn)
    r = {"clientes": 0, "termos": 0, "pulados": 0, "eventos": 0, "a_revisar": 0, "erros": 0}
    # O nome entra pelo arquivo inteiro, antes dos termos: rodar a carga de
    # novo depois da C5 pula todos os termos (idempotência por
    # `(cnpj, numero, empresa)`) e é justamente assim que os 731 nomes chegam à
    # base sem reimportar nada. A marca do Harmonit vai no FIM -- ela faz
    # `UPDATE` em `contrato_termo`, e rodando antes do laço, numa base vazia,
    # não encontraria termo nenhum e a marca se perderia em silêncio (medido:
    # `sem_termo` em vez de `atualizados`).
    r["nomes"] = importar_nomes(conn, caminho)

    with open(caminho, encoding="utf-8") as fh:
        for i, linha in enumerate(fh):
            if limite_clientes is not None and r["clientes"] >= limite_clientes:
                break
            try:
                c = json.loads(linha)
            except ValueError:
                r["erros"] += 1
                continue
            cnpj = c.get("cnpj") or ""
            if not cnpj:
                r["erros"] += 1
                continue
            gravou_algum = False
            for t in c.get("termos") or []:
                chave = (cnpj, str(t.get("numero") or ""), t.get("empresa") or "MOVISAT")
                if chave in existentes:
                    r["pulados"] += 1
                    continue
                lido = {
                    "numero": t.get("numero"), "perfil": t.get("tipo"),
                    "empresa": t.get("empresa") or "MOVISAT",
                    "a_definir": False, "eventos": t.get("eventos") or [],
                }
                try:
                    registro.gravar(
                        conn, cnpj, lido, assinado=bool(t.get("assinado")),
                        assinado_em=t.get("assinado_em"), origem="carga",
                        enviado_por="carga-auditoria-13-10",
                        revisar_motivo=t.get("revisar_motivo"))
                except Exception as e:                       # pragma: no cover
                    log.warning("falha gravando %s %s: %s", cnpj, chave[1], e)
                    r["erros"] += 1
                    continue
                existentes.add(chave)
                r["termos"] += 1
                r["eventos"] += len(lido["eventos"])
                r["a_revisar"] += 1 if t.get("revisar_motivo") else 0
                gravou_algum = True
            if gravou_algum:
                # A situação derivada é refeita uma vez por cliente, no fim —
                # não a cada termo. Recalcular por termo seria o mesmo
                # resultado com 4.599 passagens em vez de 731.
                registro.recalcular(conn, cnpj)
            r["clientes"] += 1

    r["harmonit_assinado"] = importar_harmonit_assinado(conn, caminho)
    return r


def main(caminho: str, limite: int | None = None) -> dict:
    with registro._connect() as conn:
        res = importar(conn, caminho, limite)
        conn.commit()
    return res


if __name__ == "__main__":                                   # pragma: no cover
    import sys
    caminho = sys.argv[1]
    limite = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print(main(caminho, limite))
