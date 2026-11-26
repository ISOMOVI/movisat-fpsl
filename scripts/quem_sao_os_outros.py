"""Quem sao os tecnicos das OS de 16/11 em diante, e por que alguns caem fora.

So leitura. Usa o extrator DE VERDADE (`_tecnico_da_os`), nao LIKE no json --
LIKE casa pedaco de nome e mente ("LS" casou 337 OS).
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso import storage
from fpsl_weso.services import pagamento_servico as ps
from fpsl_weso.painel.templates_config import (KM_DESLOCAMENTO_ID,
                                               PAGAMENTO_TECNICO_ID)

CORTE = "2026-11-16"

with storage._connect() as conn:
    excluidos = {r[0] for r in conn.execute(
        "SELECT tecnico_id FROM tecnicos WHERE excluido = 1").fetchall()}
    nomes = dict(conn.execute(
        "SELECT tecnico_id, nome FROM tecnicos").fetchall())
    linhas = conn.execute(
        "SELECT numero_os, tecnicos_json, materiais_json, data_previsao, "
        "       situacao_id, status_str "
        "  FROM os_historico WHERE excluida = 0").fetchall()

print(f"tecnicos excluidos no cadastro: {len(excluidos)}")
print(f"{'OS':>7} {'data':>11} {'situacao':>9} {'status':>11} "
      f"{'pagto':>7} {'km':>7}  quem o JSON diz  ->  quem o extrator pega")
print("-" * 120)

contagem = {}
for numero, tecnicos, materiais, previsao, situacao, status in linhas:
    iso = ps._iso_da_data(previsao)
    if iso and iso < CORTE:
        continue
    pagamento, km = (0.0, 0.0)
    if materiais:
        pagamento, km = ps._valores_do_corpo(materiais)
    tid, nome = ps._tecnico_da_os(tecnicos, excluidos)
    crus = []
    try:
        for t in json.loads(tecnicos or "[]"):
            uid = t.get("usuarioId")
            crus.append(f"{t.get('nomeTecnico') or nomes.get(uid) or '?'}"
                        f"#{uid}"
                        f"{' EXCLUIDO' if uid in excluidos else ''}")
    except Exception:  # noqa: BLE001
        crus = ["(json ilegivel)"]
    pego = f"{nome}#{tid}" if tid else "-- NENHUM --"
    contagem[pego.split("#")[0]] = contagem.get(pego.split("#")[0], 0) + 1
    print(f"{numero:>7} {str(iso):>11} {situacao or '':>9} {str(status):>11} "
          f"{pagamento:>7} {km:>7}  {', '.join(crus) or '(vazio)':<45} -> {pego}")

print()
for quem, n in sorted(contagem.items(), key=lambda x: -x[1]):
    print(f"  {quem:<22} {n}")
