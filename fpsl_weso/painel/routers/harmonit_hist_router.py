"""Historico das chamadas ao Harmonit — auditoria no painel.

Decisao do usuario (2026-07-29): "preciso auditar isso no painel ou ao menos
registrar atrasos, dados, mas nao de forma desenfreada de timeout, algo sensato
mesmo."

Traducao: TODA chamada e gravada (harmonit_client._executar, ponto unico), mas
o painel apresenta em dois niveis:

  - RESUMO por servico: quantas chamadas, quantas falharam, mediana e p95 de
    tempo. E onde se ve "o Harmonit esta lento hoje" com numero;
  - DETALHE: as chamadas recentes, filtraveis, para investigar um caso.

O que NAO existe aqui de proposito: alerta por timeout isolado. A instabilidade
do Harmonit e conhecida e um alerta por ocorrencia vira ruido que se aprende a
ignorar. O sinal de evento e o DISJUNTOR (harmonit_client.estado()) -- quando
ele abre, aconteceu algo que merece atencao.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from ..auth import requer_aba
from ...harmonit_client import estado as estado_disjuntor
from ... import storage

router = APIRouter(prefix="/painel/api/harmonit", tags=["harmonit-historico"])


def _conn():
    c = sqlite3.connect(storage.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _corte(horas: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()


@router.get("/resumo")
async def resumo(horas: int = Query(24, ge=1, le=720),
                 _=Depends(requer_aba("harmonit_historico"))):
    """Uma linha por servico. Mediana e p95 em vez de media: a media esconde
    cauda longa, e cauda longa e exatamente o problema do Harmonit."""
    corte = _corte(horas)
    with _conn() as c:
        linhas = []
        servicos = [r["servico"] for r in c.execute(
            "SELECT DISTINCT servico FROM harmonit_chamadas WHERE momento >= ? "
            "ORDER BY servico", (corte,))]
        for s in servicos:
            tempos = [r["ms"] for r in c.execute(
                "SELECT ms FROM harmonit_chamadas WHERE servico = ? AND momento >= ? "
                "ORDER BY ms", (s, corte))]
            tot = len(tempos)
            # "vazio" (OS nao encontrada) NAO conta como falha: a varredura
            # sonda numeros sequenciais e a numeracao do Harmonit tem buracos.
            # Sem essa separacao o painel mostrava 100% de erro num sistema sao.
            falhas = c.execute(
                "SELECT COUNT(*) n FROM harmonit_chamadas WHERE servico = ? "
                "AND momento >= ? AND COALESCE(categoria, CASE WHEN ok=1 THEN 'ok' "
                "ELSE 'erro' END) = 'erro'", (s, corte)).fetchone()["n"]
            vazios = c.execute(
                "SELECT COUNT(*) n FROM harmonit_chamadas WHERE servico = ? "
                "AND momento >= ? AND categoria = 'vazio'", (s, corte)).fetchone()["n"]
            linhas.append({
                "servico": s,
                "chamadas": tot,
                "falhas": falhas,
                "vazios": vazios,
                "pct_falha": round(100 * falhas / tot, 1) if tot else 0,
                "ms_mediana": tempos[tot // 2] if tot else None,
                "ms_p95": tempos[min(tot - 1, int(tot * 0.95))] if tot else None,
                "ms_max": tempos[-1] if tot else None,
            })
        total = c.execute(
            "SELECT COUNT(*) n, "
            "SUM(CASE WHEN COALESCE(categoria, CASE WHEN ok=1 THEN 'ok' ELSE 'erro' END)"
            " = 'erro' THEN 1 ELSE 0 END) f, "
            "SUM(CASE WHEN categoria = 'vazio' THEN 1 ELSE 0 END) v "
            "FROM harmonit_chamadas WHERE momento >= ?", (corte,)).fetchone()
    return {
        "horas": horas,
        "total": total["n"] or 0,
        "falhas": total["f"] or 0,
        "vazios": total["v"] or 0,
        "disjuntor": estado_disjuntor(),
        "retencao_dias": storage.RETENCAO_CHAMADAS_DIAS,
        "servicos": linhas,
    }


@router.get("/chamadas")
async def chamadas(horas: int = Query(24, ge=1, le=720),
                   servico: str | None = None,
                   so_falhas: bool = False,
                   limite: int = Query(200, ge=1, le=2000),
                   _=Depends(requer_aba("harmonit_historico"))):
    sql = "SELECT * FROM harmonit_chamadas WHERE momento >= ?"
    args = [_corte(horas)]
    if servico:
        sql += " AND servico = ?"
        args.append(servico)
    if so_falhas:
        sql += (" AND COALESCE(categoria, CASE WHEN ok=1 THEN 'ok' ELSE 'erro' END)"
                " = 'erro'")
    sql += " ORDER BY momento DESC LIMIT ?"
    args.append(limite)
    with _conn() as c:
        return {"chamadas": [dict(r) for r in c.execute(sql, args)]}
