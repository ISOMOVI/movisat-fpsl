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


def importar(conn, caminho: str, limite_clientes: int | None = None) -> dict:
    """Grava o que ainda não existe. Idempotente por (cnpj, numero, empresa)."""
    contratos_tabelas.criar(conn)
    existentes = _ja_gravados(conn)
    r = {"clientes": 0, "termos": 0, "pulados": 0, "eventos": 0, "a_revisar": 0, "erros": 0}

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
