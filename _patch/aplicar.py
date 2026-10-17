"""Aplicador de trocas ancoradas em texto, para o FPSL (16/10/2026).

Cada troca vive em DOIS arquivos de texto puro (`*_antes.txt` e `*_depois.txt`),
listados no `manifesto.txt`. Assim não há aspas escapadas dentro de aspas
escapadas -- a armadilha que fez a primeira tentativa deste patch morrer no
shell.

Uso, de dentro de /home/claude/fpsl_weso:
    venv/bin/python _patch/aplicar.py

Regras:
  · a âncora tem de aparecer EXATAMENTE uma vez, senão o script para sem tocar
    em nada;
  · se o resultado já estiver no arquivo, a troca é pulada (rodar duas vezes
    não duplica);
  · backup `.bak_2026-10-16_log` por arquivo, só na primeira vez.
"""
import pathlib
import shutil
import sys

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = pathlib.Path("/home/claude/fpsl_weso")
SELO = ".bak_2026-10-16_log"

feitos, pulados = [], []

for linha in (AQUI / "manifesto.txt").read_text(encoding="utf-8").splitlines():
    linha = linha.strip()
    if not linha or linha.startswith("#"):
        continue
    rel, antes_arq, depois_arq, apelido = [x.strip() for x in linha.split("|")]
    alvo = RAIZ / rel
    if not alvo.exists():
        print(f"PARO: {rel} não existe")
        sys.exit(1)
    antes = (AQUI / antes_arq).read_text(encoding="utf-8")
    depois = (AQUI / depois_arq).read_text(encoding="utf-8")
    texto = alvo.read_text(encoding="utf-8")

    # Marca de "já aplicado": a primeira linha não-vazia do resultado que não
    # exista na âncora. É o que torna o script repetível.
    marca = next((l for l in depois.splitlines()
                  if l.strip() and l not in antes), None)
    if marca and marca in texto:
        pulados.append(apelido)
        continue
    if texto.count(antes) != 1:
        print(f"PARO: âncora de '{apelido}' aparece {texto.count(antes)}x em {rel}")
        sys.exit(1)
    bak = alvo.with_name(alvo.name + SELO)
    if not bak.exists():
        shutil.copy2(alvo, bak)
    alvo.write_text(texto.replace(antes, depois), encoding="utf-8")
    feitos.append(apelido)

print("APLICADOS:")
for f in feitos:
    print("  +", f)
if pulados:
    print("já estavam aplicados:")
    for p in pulados:
        print("  =", p)
if not feitos:
    print("  (nenhuma troca nova)")
