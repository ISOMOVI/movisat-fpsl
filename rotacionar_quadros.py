"""Rotaciona o token de compartilhamento dos quadros do Painel Rápido.

🚨 POR QUE ROTACIONAR: em 12/08 o token apareceu no `fpsl_access.log` (2.083
linhas, agora mascaradas) e um deles foi impresso numa conversa. O token na URL
**é** a credencial -- o quadro é compartilhado por link, sem login --, então
quem o tiver abre o quadro. Mascarar o log daqui para a frente não desfaz o que
já circulou: o único conserto é trocar o valor.

🚨 O LINK ANTIGO PARA DE FUNCIONAR. Quem estiver com ele guardado (favorito,
mensagem no grupo) precisa do novo. É o preço de rotacionar, e é por isso que
o valor antigo fica guardado no arquivo de saída -- dá para voltar atrás.

⚠️ O TOKEN NOVO NÃO É IMPRESSO NA TELA. Ele vai para um arquivo 600 no home,
porque foi exatamente imprimir valor em terminal que criou este problema.

Uso:  ./venv/bin/python rotacionar_quadros.py --conferir
      ./venv/bin/python rotacionar_quadros.py --aplicar
"""
import secrets
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BANCO = Path("/home/claude/fpsl_weso/data/fpsl.db")
SAIDA = Path("/home/claude/links_painel_rapido.txt")
DOMINIO = "https://fpsl.movisat.com.br"


def conectar():
    c = sqlite3.connect(BANCO, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def conferir() -> list[sqlite3.Row]:
    with conectar() as c:
        quadros = c.execute(
            "SELECT id, titulo, token, modo, ativo FROM demanda_quadro "
            " ORDER BY id").fetchall()
    for q in quadros:
        # Só o tamanho e o fim, nunca o valor: dá para conferir que mudou sem
        # o token voltar a circular.
        fim = q["token"][-6:] if q["token"] else "?"
        print(f"  #{q['id']} {q['titulo']!r} modo={q['modo']} "
              f"ativo={q['ativo']} token=…{fim} ({len(q['token'])} chars)")
    return quadros


def aplicar(so_estes: set[int] | None = None) -> None:
    """⚠️ ROTACIONA SÓ O QUE FOR PEDIDO. Cada quadro tem um link em uso por
    gente diferente; trocar o de todos "por garantia" derruba o acesso de quem
    não tinha problema nenhum. A exposição de 12/08 foi de UM quadro na
    conversa -- os outros só estiveram no log, que exige root para ler."""
    quadros = [q for q in conferir()
               if so_estes is None or q["id"] in so_estes]
    if not quadros:
        raise SystemExit("nenhum quadro selecionado.")

    carimbo = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linhas = [f"# Painel Rápido — links rotacionados em {carimbo}",
              "# 🚨 O link ANTIGO parou de funcionar. Reenvie o novo a quem usa.",
              ""]
    with conectar() as c:
        for q in quadros:
            novo = secrets.token_hex(32)
            c.execute("UPDATE demanda_quadro SET token = ? WHERE id = ?",
                      (novo, q["id"]))
            linhas += [
                f"## {q['titulo']}  (quadro #{q['id']}, modo {q['modo']})",
                f"NOVO:    {DOMINIO}/demandas/{novo}",
                f"antigo:  ...{q['token'][-6:]}  (revogado, guardado abaixo)",
                f"         {q['token']}",
                "",
            ]
        c.commit()

    SAIDA.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    SAIDA.chmod(0o600)

    # 🚨 A prova é RELER O ESTADO, não o "commit deu certo".
    with conectar() as c:
        depois = c.execute("SELECT id, token FROM demanda_quadro "
                           " ORDER BY id").fetchall()
    antigos = {q["id"]: q["token"] for q in quadros}
    for d in depois:
        if d["id"] not in antigos:
            continue          # não foi pedido; tem de continuar igual
        if d["token"] == antigos[d["id"]]:
            raise SystemExit(f"ABORTADO: quadro #{d['id']} não trocou de token.")
        if len(d["token"]) != 64:
            raise SystemExit(f"ABORTADO: quadro #{d['id']} com token estranho.")

    # 🚨 CONTAR O QUE MUDOU, NÃO O QUE FOI LIDO. A primeira versão imprimia
    # `len(depois)` -- o total de quadros do banco -- e anunciou "2 rotacionados"
    # quando só um tinha mudado. Rótulo que não vem da mesma medida da ação é a
    # verificação que mente, e é o erro que este projeto mais repete.
    mudados = [d["id"] for d in depois
               if d["id"] in antigos and d["token"] != antigos[d["id"]]]
    print()
    print(f"rotacionado(s): {mudados}  ·  intocado(s): "
          f"{[d['id'] for d in depois if d['id'] not in antigos]}")
    print("Nenhum token impresso aqui.")
    print(f"OS LINKS NOVOS ESTÃO EM: {SAIDA}  (modo 600)")
    print("Leia com:  cat ~/links_painel_rapido.txt")


if __name__ == "__main__":
    if "--aplicar" in sys.argv:
        ids = {int(a) for a in sys.argv[sys.argv.index("--quadro") + 1].split(",")} \
            if "--quadro" in sys.argv else None
        aplicar(ids)
    else:
        conferir()
        print("\n(--conferir) nada alterado.")
        print("Use: --aplicar --quadro 2      (só o quadro 2)")
        print("     --aplicar                 (TODOS -- derruba todos os links)")
