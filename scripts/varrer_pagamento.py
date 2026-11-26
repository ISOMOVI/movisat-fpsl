"""A VARREDURA DA ABA 2, NO CRON — 25/11/2026 (tarefa 1.3).

🔵 Decisão dele, 24/11: *"o cron diário é quem traz o card da OS nova"*, e o
corte segue pela **data da OS**, nunca pelo nascimento do card.

🚨 **O HORÁRIO É A PARTE QUE IMPORTA, NÃO O CRON.** Esta varredura lê
`os_historico`, que é escrito pelo cache WESO às **04:15** e pelo Harmonit às
**04:50**. Rodar antes varreria o cache de ONTEM; rodar em cima disputaria
escrita no mesmo SQLite. Por isso a linha é **05:10**:

    10 5 * * * cd /home/claude/fpsl_weso && venv/bin/python scripts/varrer_pagamento.py >> /home/claude/logs/fpsl_pagamento.log 2>&1

⚠️ **O `cd` e o `venv` não são decoração:** fora de `/home/claude/fpsl_weso` o
`settings` estoura com `ValidationError: weso_api_key`, e com o python do
MoviZap falta `pydantic_settings`.

🟡 **`horas=None` é decisão minha, declarada.** O padrão `horas=24` filtra por
`atualizado_em`: se o cron falhar um dia, aquele serviço fica fora da tela
**para sempre** — é o buraco de hoje em outra forma. Varrer o cache inteiro
custa uma passada em ~650 linhas, e `ja_existiam` protege o que já andou
(artefato que já andou **não é sobrescrito**). O botão manual da tela já usa
`horas=None` pelo mesmo motivo.

🚨 **NÃO FALA COM O HARMONIT.** Zero chamada ao ERP: tudo sai do cache. O ERP
esgota o pool todo dia e uma rotina que o consultasse por OS entraria na fila
com o painel da manhã.

Uso:
    venv/bin/python scripts/varrer_pagamento.py              varre e relata
    venv/bin/python scripts/varrer_pagamento.py --json       o mesmo, em JSON
    venv/bin/python scripts/varrer_pagamento.py --horas 24   só o que mudou

Saída de processo: 0 quando varreu, 1 quando estourou — para que o log diga a
diferença entre "rodou e não havia nada" e "não rodou".
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fpsl_weso import rotinas, storage  # noqa: E402
from fpsl_weso.services import pagamento_servico  # noqa: E402

# 🚨 O NOME DO LAÇO NO VIGIA DOS MUDOS. Sem isto, cron que para de rodar não
# aparece em lugar nenhum: o `scripts/rotinas_mudas.py` das 18:10 lista os
# laços de `rotinas.LACOS`, e o que não está lá **não é vigiado**. A tela diria
# "varrido há 6 dias" apenas para quem olhasse.
# ⚠️ Carimba SEMPRE, inclusive quando estourou: o relatório tem de distinguir
# "rodou e deu erro" de "não rodou", e as duas coisas são passadas.
LACO = "pagamento_servico"

AQUI = ZoneInfo("America/Sao_Paulo")

# 🚨 A ORDEM DAS CHAVES É A DA LEITURA, não a do dicionário: quem abre o log às
# 7h quer saber primeiro quantas nasceram.
ORDEM = ("novos", "ja_existiam", "com_valor", "lidas", "antes_da_data",
         "sem_tecnico", "sem_orcamento", "tecnicos", "desde", "varrido_em")


def _agora_local() -> str:
    return datetime.now(timezone.utc).astimezone(AQUI).strftime(
        "%d/%m/%Y %H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--horas", type=int, default=None,
                    help="janela de `atualizado_em`; o padrao e o cache inteiro")
    ap.add_argument("--json", action="store_true", help="saida em JSON")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        resumo = pagamento_servico.varrer(horas=args.horas)
    except Exception as e:                      # noqa: BLE001
        asyncio.run(rotinas.marcar(LACO, f"ESTOUROU: {e}"))
        # 🚨 ESTOURO NÃO PODE VIRAR LINHA DE LOG CALMA. O carimbo só é gravado
        # dentro da transação que terminou, então a tela continuará mostrando a
        # varredura ANTERIOR -- e é isso que se quer: quadro velho se anuncia
        # velho, em vez de se dizer de hoje.
        print(f"[{_agora_local()}] A VARREDURA ESTOUROU: {e}", file=sys.stderr)
        logging.exception("varredura de pagamento falhou")
        return 1

    # 🚨 DEPOIS da passada, nunca antes: carimbar antes diria "rodou" de uma
    # rodada que ainda podia estourar. É a régua do `marcar_avisadas` da fila.
    asyncio.run(rotinas.marcar(
        LACO, f"{resumo.get('novos', 0)} novos, "
              f"{resumo.get('ja_existiam', 0)} já existiam, "
              f"{resumo.get('lidas', 0)} lidas"))

    if args.json:
        print(json.dumps(resumo, ensure_ascii=False, sort_keys=True))
        return 0

    partes = [f"{c}={resumo[c]}" for c in ORDEM if c in resumo]
    outras = sorted(k for k in resumo if k not in ORDEM)
    partes += [f"{k}={resumo[k]}" for k in outras]
    print(f"[{_agora_local()}] banco={storage.DB_PATH}")
    print(f"[{_agora_local()}] " + "  ".join(partes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
