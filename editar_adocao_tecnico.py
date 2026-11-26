# -*- coding: utf-8 -*-
"""A OS não nasce duas vezes quando o técnico aparece depois — 25/11.

🔵 Ele, na tela: *"OS 17131 aparece sem tecnico no painel, mas não tem
agendamento no harmonit corretamente?"* — e o agendamento estava certo.

🚨 Defeito meu, de hoje: a trava de duplicidade é pelo par
`(numero_os, tecnico_id)` e, no SQLite, **NULL não colide com nada**.
"""
import pathlib
import shutil
import sys
from datetime import datetime

ALVO = pathlib.Path("/home/claude/fpsl_weso/fpsl_weso/services/"
                    "pagamento_servico.py")

RESUMO_DE = '''    resumo = {"lidas": 0, "com_valor": 0, "novos": 0, "ja_existiam": 0,
              "sem_tecnico": 0, "tecnicos": 0, "sem_orcamento": 0}'''
RESUMO_PARA = '''    # ⚠️ `adotados` e `conflito` nascem no resumo mesmo valendo zero: chave que
    # só aparece quando acontece faz quem lê o log concluir que a versão velha
    # estava rodando.
    resumo = {"lidas": 0, "com_valor": 0, "novos": 0, "ja_existiam": 0,
              "sem_tecnico": 0, "tecnicos": 0, "sem_orcamento": 0,
              "adotados": 0, "conflito": 0}'''

ACHADO_DE = '''            if achado:
                # ⚠️ NÃO SE SOBRESCREVE ARTEFATO QUE JÁ ANDOU. O operador pode
                # já ter dado ciente, anexado comprovante ou devolvido com
                # justificativa -- e a varredura da noite seguinte não pode
                # apagar isso. O que o `[ atualizar ]` do card faz é outra
                # coisa, e é pedido explícito.
                resumo["ja_existiam"] += 1
                continue'''

ACHADO_PARA = '''            if achado:
                # ⚠️ NÃO SE SOBRESCREVE ARTEFATO QUE JÁ ANDOU. O operador pode
                # já ter dado ciente, anexado comprovante ou devolvido com
                # justificativa -- e a varredura da noite seguinte não pode
                # apagar isso. O que o `[ atualizar ]` do card faz é outra
                # coisa, e é pedido explícito.
                resumo["ja_existiam"] += 1
                continue

            # ===============================================================
            # 🚨 O TÉCNICO QUE APARECE DEPOIS — e a OS NÃO nasce duas vezes
            # ===============================================================
            # 🔵 25/11, ele na tela: *"OS 17131 aparece sem tecnico no painel,
            # mas não tem agendamento no harmonit corretamente?"* -- e tinha:
            # `agendamentoId 970805`, `usuarioId 14262`, situação 15694.
            #
            # 🚨 **O DEFEITO:** a consulta acima procura o par
            # `(numero_os, tecnico_id)`. Quando a OS entrou SEM técnico (o
            # cache ainda não o trazia) e ele aparece depois, o par é outro --
            # e, no SQLite, **NULL não colide com nada**, nem no UNIQUE. A OS
            # 17131 ficou com duas linhas: a de 18/11 sem dono e a de 25/11 com
            # o Franck. **Cada linha é dinheiro a pagar**: duas linhas da mesma
            # OS em dois cards é pagar duas vezes o mesmo serviço.
            #
            # A regra, e ela é conservadora de propósito:
            #   - a linha sem dono que **não andou** ADOTA o técnico (mesmo id,
            #     mesmos eventos: ela só passa a ter dono);
            #   - a que **já andou** não é tocada **e o segundo não nasce** --
            #     conta em `conflito` e alguém resolve à mão, porque duplicar
            #     dinheiro é pior que esperar.
            if tid is not None:
                orfao = conn.execute(
                    "SELECT id, coluna, lote_id, ciente_em, "
                    "       comprovante_arquivo, comprovante_dispensa, "
                    "       devolvido_em, justificativa "
                    "  FROM pagamento_artefato "
                    " WHERE numero_os = ? AND tecnico_id IS NULL",
                    (numero,)).fetchone()
                if orfao:
                    (orfao_id, coluna, lote_id, ciente_em, comprovante,
                     dispensa, devolvido_em, justificativa) = orfao
                    andou = (coluna != "movimentacao" or lote_id is not None
                             or ciente_em or comprovante or dispensa
                             or devolvido_em or justificativa)
                    if andou:
                        log.warning(
                            "OS %s: artefato %s sem tecnico JA ANDOU (coluna "
                            "%s, lote %s) e o tecnico %s apareceu depois -- "
                            "nao adotei e nao criei o segundo",
                            numero, orfao_id, coluna, lote_id, tid)
                        resumo["conflito"] += 1
                        continue
                    conn.execute(
                        "UPDATE pagamento_artefato "
                        "   SET tecnico_id = ?, tecnico_nome = ?, "
                        "       atualizado_em = ? "
                        " WHERE id = ?",
                        (tid, nome or None, _agora(), orfao_id))
                    _evento(conn, artefato_id=orfao_id, acao="adotar_tecnico",
                            de=None, para=str(tid),
                            detalhe=f"o cache passou a trazer {nome or tid}; "
                                    f"a linha sem dono adotou em vez de nascer "
                                    f"uma segunda",
                            por="varredura")
                    resumo["adotados"] += 1
                    tecnicos_vistos.add(tid)
                    continue'''

T = [("as chaves novas do resumo", RESUMO_DE, RESUMO_PARA),
     ("a adoção do técnico", ACHADO_DE, ACHADO_PARA)]


def main() -> int:
    texto = ALVO.read_text(encoding="utf-8")
    for rotulo, de, _p in T:
        if texto.count(de) != 1:
            print(f"ABORTADO em '{rotulo}': {texto.count(de)} ocorrencias.",
                  file=sys.stderr)
            return 1
    novo = texto
    for _r, de, para in T:
        novo = novo.replace(de, para, 1)
    marca = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    shutil.copy2(ALVO, ALVO.with_suffix(ALVO.suffix + f".bak_{marca}_adocao"))
    ALVO.write_text(novo, encoding="utf-8")
    print(f"linhas {len(texto.splitlines())} -> {len(novo.splitlines())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
