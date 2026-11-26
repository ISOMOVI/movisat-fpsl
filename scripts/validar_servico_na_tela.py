"""VALIDA SE TUDO DE 16/11/2026 EM DIANTE ESTA NA TELA — 25/11, pedido dele.

🚨 A PERGUNTA NAO E "a varredura criou o que ela aceita", e sim "o que existe
de 16/11 em diante aparece?". Por isso a base aqui e a `os_historico` INTEIRA,
sem o filtro de `materiais_json` que a varredura usa: OS sem corpo de material
nunca entra na varredura, e contar so as que entram esconderia exatamente o
buraco que ele quer medir.

So leitura. Uso: cd /home/claude/fpsl_weso && venv/bin/python scripts/validar_servico_na_tela.py
"""
import pathlib
import sys

# ⚠️ `parent.parent`: o script vive em `scripts/` e o pacote esta um
# nivel acima -- foi o que quebrou ao mover o arquivo para ca.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso import storage
from fpsl_weso.services import pagamento_servico as ps

CORTE = "2026-11-16"

with storage._connect() as conn:
    corte = ps.desde(conn)
    print(f"corte no config = {corte}  (esperado {CORTE})")

    linhas = conn.execute(
        "SELECT numero_os, materiais_json, tecnicos_json, data_previsao, "
        "       situacao_id, excluida "
        "  FROM os_historico").fetchall()
    artefatos = {r[0]: r[1] for r in conn.execute(
        "SELECT numero_os, coluna FROM pagamento_artefato").fetchall()}

dentro, excluidas = [], []
for numero, materiais, tecnicos, previsao, situacao, excluida in linhas:
    data_iso = ps._iso_da_data(previsao)
    if data_iso and data_iso < corte:
        continue
    if excluida:
        excluidas.append((numero, data_iso))
        continue
    pagamento, km = (0.0, 0.0)
    if materiais:
        pagamento, km = ps._valores_do_corpo(materiais)
    tid, nome = ps._tecnico_da_os(tecnicos, set())
    dentro.append({"os": numero, "data": data_iso or "SEM DATA",
                   "tem_material": bool(materiais),
                   "pagamento": pagamento, "km": km,
                   "tecnico": nome or "", "situacao": situacao,
                   "no_quadro": numero in artefatos,
                   "coluna": artefatos.get(numero, "")})

dentro.sort(key=lambda r: (r["data"], r["os"]))
print(f"\nOS de {corte} em diante, excluidas fora: {len(dentro)}"
      f"   (excluidas ignoradas: {len(excluidas)})")
print(f"{'OS':>7} {'data':>11} {'mat':>4} {'pagto':>8} {'km':>8} "
      f"{'quadro':>7}  tecnico / porque nao esta")
for r in dentro:
    if r["no_quadro"]:
        porque = f"OK em {r['coluna']}"
    elif not r["tem_material"]:
        porque = "SEM corpo de material -- a varredura nem a le"
    elif r["pagamento"] <= 0 and r["km"] <= 0:
        porque = "material SEM pagamento e SEM km -- descartada"
    else:
        porque = "🚨 TEM VALOR E NAO ESTA NO QUADRO"
    print(f"{r['os']:>7} {r['data']:>11} {'sim' if r['tem_material'] else 'NAO':>4} "
          f"{r['pagamento']:>8} {r['km']:>8} {'sim' if r['no_quadro'] else 'NAO':>7}  "
          f"{r['tecnico'][:18]:18} {porque}")

no_quadro = [r for r in dentro if r["no_quadro"]]
sem_material = [r for r in dentro if not r["tem_material"]]
sem_valor = [r for r in dentro
             if r["tem_material"] and r["pagamento"] <= 0 and r["km"] <= 0]
faltando = [r for r in dentro if not r["no_quadro"] and r["tem_material"]
            and (r["pagamento"] > 0 or r["km"] > 0)]

print(f"\n{len(dentro)} OS de {corte} em diante:")
print(f"  no quadro ............... {len(no_quadro)}")
print(f"  sem corpo de material ... {len(sem_material)}")
print(f"  material sem valor ...... {len(sem_valor)}")
print(f"  COM VALOR E FORA ........ {len(faltando)}  <- tem de ser ZERO")

if faltando:
    print("\n🚨 FALTOU: " + ", ".join(str(r["os"]) for r in faltando))
    raise SystemExit(1)
print("\nOK: nenhuma OS com valor de 16/11 em diante ficou fora do quadro.")
