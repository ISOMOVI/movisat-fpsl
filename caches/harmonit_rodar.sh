#!/usr/bin/env bash
# Atualiza o cache da base de veiculos do Harmonit. Cron 1x por dia (04:50).
# Roda com o venv do FPSL porque reusa a config dele -- a credencial fica num
# lugar so, nao ha credencial duplicada aqui.
#
# 🚨 O SCRIPT VIVE NO REPOSITORIO, O DADO VIVE FORA (24/08). Ver caches/README.md.
set -u
LOG=/home/claude/harmonit_cache/atualizar.log
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
  /home/claude/fpsl_weso/venv/bin/python /home/claude/fpsl_weso/caches/harmonit_atualizar.py
  echo "saida=$?"
} >> "$LOG" 2>&1
tail -n 400 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
