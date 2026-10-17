"""O carimbo de passada dos laços (`fpsl_weso/rotinas.py`), 16/10/2026.

Uso:  venv/bin/python tests/teste_rotinas.py

🚨 BANCO DE MENTIRA, NÃO O DE PRODUÇÃO. `storage.DB_PATH` é trocado por um
arquivo temporário antes de qualquer chamada: teste que lê (ou escreve) o banco
vivo é armadilha conhecida da casa. É por isso que este arquivo não segue o
estilo dos vizinhos, que limpam o que sujaram no banco real.

O que estes casos protegem, e que nenhuma leitura garante:
  · "sem registro" NÃO é atraso -- se isso se inverter, a tela acusa de
    quebrada toda VPS que acabou de reiniciar;
  · `marcar` NÃO LEVANTA: ela roda dentro do laço, e uma exceção aqui mataria
    justamente a rotina que o carimbo existe para vigiar;
  · o carimbo nasce em UTC. Carimbo em hora local no banco é o defeito que o
    módulo de demandas já teve (`datetime('now')` do SQLite, 3 h adiantado).
"""
import asyncio
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fpsl_weso import rotinas, storage  # noqa: E402

feitos = 0


def ok(condicao, descricao):
    global feitos
    assert condicao, "FALHOU: " + descricao
    feitos += 1
    print("  ok:", descricao)


async def caso_ida_e_volta():
    await rotinas.marcar("scan_os", "3 OS novas")
    r = await rotinas.ultima("scan_os")
    ok(r["resultado"] == "3 OS novas", "o resultado volta como foi gravado")
    ok(r["sem_registro"] is False, "depois de carimbar, não é mais 'sem registro'")
    ok(r["atrasada"] is False, "carimbo de agora não nasce atrasado")
    ok(datetime.fromisoformat(r["ultima_em"]).utcoffset() == timedelta(0),
       "o carimbo é gravado em UTC, não em hora local")
    ok(r["rotulo"] == rotinas.LACOS["scan_os"][0], "o rótulo vem do dicionário dos laços")


async def caso_sem_registro():
    r = await rotinas.ultima("cartoes_fechamento")
    ok(r["sem_registro"] is True, "laço nunca carimbado responde 'sem registro'")
    ok(r["atrasada"] is False,
       "'sem registro' NÃO é atraso -- senão a tela acusa VPS recém-reiniciada")


async def caso_tolerancia():
    nome = "conferencia_fechamento"
    intervalo = rotinas.LACOS[nome][1]

    async def carimbar_atras(segundos):
        quando = datetime.now(timezone.utc) - timedelta(seconds=segundos)
        await storage.set_config(rotinas._chave(nome, "ultima_em"), quando.isoformat())
        await storage.set_config(rotinas._chave(nome, "resultado"), "x")
        return await rotinas.ultima(nome)

    r = await carimbar_atras(intervalo * 1.5)
    ok(r["atrasada"] is False, "uma vez e meia o intervalo ainda não é atraso")
    r = await carimbar_atras(intervalo * (rotinas.TOLERANCIA + 0.5))
    ok(r["atrasada"] is True, "passar do dobro do intervalo acusa atraso")


async def caso_marcar_nao_levanta():
    original = storage.set_config

    async def explodir(*_a, **_k):
        raise RuntimeError("banco fora do ar")

    storage.set_config = explodir
    try:
        await rotinas.marcar("scan_os", "qualquer coisa")
        ok(True, "marcar() engole a falha do banco em vez de matar o laço")
    finally:
        storage.set_config = original


async def caso_teto_do_resultado():
    await rotinas.marcar("operacoes", "x" * 5000)
    r = await rotinas.ultima("operacoes")
    ok(len(r["resultado"]) == rotinas.LIMITE_RESULTADO,
       f"resultado é cortado em {rotinas.LIMITE_RESULTADO} caracteres")


async def caso_dicionario_coerente():
    for nome, (rotulo, intervalo) in rotinas.LACOS.items():
        ok(bool(rotulo) and not rotulo.startswith("rotina_"),
           f"'{nome}' tem rótulo de gente")
        ok(intervalo > 0, f"'{nome}' tem intervalo esperado")
    estado = await rotinas.estado()
    ok(len(estado) == len(rotinas.LACOS),
       f"estado() devolve os {len(rotinas.LACOS)} laços")


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        storage.DB_PATH = Path(tmp) / "teste_rotinas.db"
        storage.init_db()
        print("teste_rotinas — banco temporário em", storage.DB_PATH)
        await caso_ida_e_volta()
        await caso_sem_registro()
        await caso_tolerancia()
        await caso_marcar_nao_levanta()
        await caso_teto_do_resultado()
        await caso_dicionario_coerente()
    print(f"\n{feitos} verificações, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
