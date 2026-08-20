"""Placa fora do cache vai ao vivo, uma a uma. 2026-08-20.

🚨 ACHADO NA AUDITORIA, e é o defeito do termo 8820 por outro caminho.

O cache local da WESO atualiza às 04:15. O veículo do termo 8846 nasceu na WESO
às **09:10** e a OS foi tentada às **13:35** — no mesmo dia. `modelo_da_placa`
devolvia `None`, não havia produto no de-para, e a OS sairia **sem a linha do
equipamento nos materiais**. A geração estava desbloqueada e produziria uma OS
incompleta.

A premissa escrita no código era *"o termo demora dias, e 2,3s de rede por
geração não se paga"*. Foi **falsificada**: placa criada de manhã, OS gerada à
tarde.

O que este arquivo prende:

  1. **Placa que o cache CONHECE não gera chamada nenhuma** — cache quente
     continua sendo cache quente, e a correção não troca cache por rede.
  2. **Placa que o cache NÃO conhece vai ao vivo**, por consulta exata.
  3. **Frota inteira desconhecida NÃO dispara** — acima do limiar a consulta
     uma-a-uma perde para a base inteira, e num contrato novo as placas nem
     existem na WESO ainda: custaria 16s para não achar nada.
  4. **O que veio do vivo entra no dicionário**, e o que já havia é preservado.

Roda na VPS: venv/bin/python tests/teste_cache_frio.py
🚨 NÃO FAZ REDE — a leitura ao vivo entra por dublê.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import equipamentos as eqp  # noqa: E402
from fpsl_weso.painel import operacoes_equipamentos as oeqp  # noqa: E402

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


class Espiao:
    def __init__(self):
        self.consultadas = []


def dubles(modulo, espiao, conhecidas=(), ao_vivo=None):
    """`conhecidas` estão no cache; `ao_vivo` é o que a WESO devolveria."""
    def _modelo(placa):
        return "Suntech ST8300" if placa in conhecidas else None

    async def _dados(placas, falhas=None):
        espiao.consultadas.extend(placas)
        return dict(ao_vivo or {})

    modulo.modelo_da_placa = _modelo
    modulo.dados_das_placas = _dados


async def rodar(modulo, nome):
    print(f"\n--- {nome} ---")

    # 1. cache quente: nenhuma chamada
    e = Espiao()
    dubles(modulo, e, conhecidas={"AAA 0A00", "BBB 0B00"})
    saida = await modulo.completar_do_vivo(["AAA 0A00", "BBB 0B00"], {})
    checar(f"{nome}: placa no cache NÃO gera chamada", e.consultadas == [],
           str(e.consultadas))

    # 2. cache frio: vai ao vivo só pela que falta
    e = Espiao()
    ch = modulo._chave("RZL H405")
    dubles(modulo, e, conhecidas={"AAA 0A00"},
           ao_vivo={ch: {"modelo": "Suntech ST8300", "veiculo_id": 88440}})
    saida = await modulo.completar_do_vivo(["AAA 0A00", "RZL H405"], {})
    checar(f"{nome}: consulta SÓ a placa que falta",
           e.consultadas == ["RZL H405"], str(e.consultadas))
    checar(f"{nome}: e o que veio do vivo entra no dicionário",
           (saida.get(ch) or {}).get("modelo") == "Suntech ST8300", str(saida))

    # 3. o que já havia é preservado
    e = Espiao()
    dubles(modulo, e, conhecidas=set(),
           ao_vivo={modulo._chave("NOVA 1A11"): {"modelo": "XT40"}})
    antes = {modulo._chave("VELHA 1A11"): {"modelo": "Suntech ST340"}}
    saida = await modulo.completar_do_vivo(["NOVA 1A11"], antes)
    checar(f"{nome}: o dicionário anterior é preservado",
           saida.get(modulo._chave("VELHA 1A11")) is not None, str(saida))

    # 4. frota inteira desconhecida NÃO dispara
    e = Espiao()
    dubles(modulo, e, conhecidas=set())
    muitas = [f"AAA {i}A00" for i in range(modulo.LIMIAR_PLACA_A_PLACA + 1)]
    await modulo.completar_do_vivo(muitas, {})
    checar(f"{nome}: acima do limiar NÃO vai ao vivo", e.consultadas == [],
           str(e.consultadas))

    e = Espiao()
    dubles(modulo, e, conhecidas=set())
    no_limite = [f"AAA {i}A00" for i in range(modulo.LIMIAR_PLACA_A_PLACA)]
    await modulo.completar_do_vivo(no_limite, {})
    checar(f"{nome}: exatamente no limiar ainda vai",
           len(e.consultadas) == modulo.LIMIAR_PLACA_A_PLACA,
           str(e.consultadas))

    # 5. placa vazia não vira consulta
    e = Espiao()
    dubles(modulo, e, conhecidas=set())
    await modulo.completar_do_vivo(["", None, "   "], {})
    checar(f"{nome}: placa vazia não vira consulta", e.consultadas == [],
           str(e.consultadas))


async def main():
    # 🚨 OS DOIS, porque são clone: a correção tem de valer na tela velha (que a
    # Erika usa hoje) e na aba nova (que a substitui).
    await rodar(eqp, "equipamentos")
    await rodar(oeqp, "operacoes_equipamentos")
    print(f"\n{'=' * 62}")
    print(f"{ok} verificações OK, {len(falhas)} falhas")
    if falhas:
        for f in falhas:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
