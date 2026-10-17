"""Quando cada laço do FPSL passou pela última vez (16/10/2026).

🚨 POR QUE ISTO EXISTE. Os oito laços do FPSL rodavam sem deixar rastro
nenhum: o `logger.info` deles não tinha handler (ver o bloco de log no
`main.py`, do mesmo dia), e a tela da rotina dizia se o interruptor estava
ligado -- nunca se ela havia rodado. Depois do reinício de 16/10 (manutenção
de emergência da Hostinger), a única forma de provar que os laços tinham
voltado foi ler carimbo de escrita de OUTRAS tabelas, por fora.

🚨 "PASSOU" NÃO É "FEZ". Toda passada carimba, inclusive a que não achou
nada e inclusive a que viu a rotina desligada -- e é justamente essa
distinção que a tela precisa dar: *laço vivo com rotina desligada* é uma
coisa, *laço morto* é outra, e até hoje as duas apareciam iguais.

🚨 CARIMBO EM UTC, conversão só na exibição. É a mesma armadilha que o módulo
de demandas documenta: carimbo nasce adiantado se alguém misturar as duas
noções de "agora". Aqui o banco guarda ISO em UTC e quem mostra converte.

⚠️ `atrasada` é SUSPEITA, não sentença: o limite é o dobro do intervalo
esperado, porque um laço que acabou de subir ainda não passou uma vez, e
rotina de uma vez por dia não é "atrasada" às 10 da manhã.
"""
from datetime import datetime, timezone

from . import storage

# nome -> (rótulo para a tela, intervalo esperado em segundos)
#
# ⚠️ O intervalo aqui é SÓ para julgar atraso. Quem manda no ritmo é a
# constante do próprio módulo do laço -- duplicar o número aqui seria criar o
# segundo lugar que alguém esquece de mudar.
LACOS: dict[str, tuple[str, int]] = {
    "inadimplencia": ("Inadimplência (WESO)", 600),
    "scan_os": ("Varredura de OS", 300),
    "resync_os": ("Resync de OS", 43200),
    "operacoes": ("Rotina da aba Operações", 21600),
    "conferencia_fechamento": ("Conferência de Fechamento", 3600),
    "contratos_auditoria": ("Auditoria de Contratos", 21600),
    "sync_tecnicos": ("Sync de técnicos", 86400),
    "cartoes_fechamento": ("Semáforo dos cartões", 3600),
}

TOLERANCIA = 2  # dobro do intervalo antes de chamar de atrasada

LIMITE_RESULTADO = 200


def _chave(nome: str, campo: str) -> str:
    return f"rotina_{nome}_{campo}"


async def marcar(nome: str, resultado: str) -> None:
    """Carimba uma passada. Nunca levanta: observabilidade não derruba rotina.

    🚨 Chamado de DENTRO do laço, depois do `try/except` da passada -- se
    falhar aqui, o laço seguinte continua. Um carimbo perdido é um buraco no
    relatório; uma exceção aqui mataria a rotina que ele devia vigiar.
    """
    try:
        agora = datetime.now(timezone.utc).isoformat()
        await storage.set_config(_chave(nome, "ultima_em"), agora)
        await storage.set_config(_chave(nome, "resultado"),
                                 (resultado or "")[:LIMITE_RESULTADO])
    except Exception:  # noqa: BLE001
        pass


def _atrasada(ultima_em: str, intervalo: int) -> bool:
    if not ultima_em:
        return False          # nunca carimbou: "sem registro", não "atrasada"
    try:
        quando = datetime.fromisoformat(ultima_em)
    except ValueError:
        return False
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    idade = (datetime.now(timezone.utc) - quando).total_seconds()
    return idade > intervalo * TOLERANCIA


async def ultima(nome: str) -> dict:
    """O que se sabe de UM laço. `ultima_em` vazio = sem registro."""
    rotulo, intervalo = LACOS.get(nome, (nome, 3600))
    ultima_em = await storage.get_config(_chave(nome, "ultima_em"), "")
    return {
        "nome": nome,
        "rotulo": rotulo,
        "intervalo_seg": intervalo,
        "ultima_em": ultima_em,
        "resultado": await storage.get_config(_chave(nome, "resultado"), ""),
        "atrasada": _atrasada(ultima_em, intervalo),
        "sem_registro": not ultima_em,
    }


async def estado() -> list[dict]:
    """Os oito laços, na ordem do dicionário."""
    return [await ultima(nome) for nome in LACOS]
