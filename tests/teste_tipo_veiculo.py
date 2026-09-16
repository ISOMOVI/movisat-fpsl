"""Tipo do veículo na WESO, na etapa 3/4 da aba Operações. 2026-09-16.

Pedido do usuário: um `<select>` de tipo (Carro/Moto/Caminhão/Portátil/
Máquina/Ônibus/Trator) na etapa 3, entre `#` e `Veículo`. A criação do
veículo (etapa 3) SEMPRE ignora o tipo -- medido ao vivo, criando e
corrigindo veículos de teste na Velasco -- então a correção de verdade só
acontece na etapa 4, junto do "Gerar", com `PUT /Veiculos/Atualizar`.

O que este arquivo PRENDE:

  1. **A tabela de códigos é a medida na tela, não a da documentação antiga.**
     `docs/weso/01_Veiculos.md` e um comentário velho diziam 2=Caminhão,
     5=Motocicleta -- cópia do fornecedor, nunca testada. O dropdown real da
     WESO (print de 16/09, confirmado testando os 7 na Velasco) é outro:
     1=Carro, 2=Moto, 3=Caminhão, 4=Portátil, 5=Máquina, 6=Ônibus, 7=Trator.

  2. **Só corrige quem tem os dois dados E cuja OS saiu bem.** Placa sem
     `weso_veiculo_id` (perfil que não cria veículo), sem `tipo_veiculo`
     (operador não escolheu, ou perfil não mostra o campo) ou cuja OS
     falhou no Harmonit não gera chamada nenhuma pra WESO.

  3. **A correção NUNCA levanta.** Pedido explícito do usuário: uma falha na
     WESO não pode virar erro na geração de OS, que já aconteceu. O `except`
     é largo de propósito (não só `HTTPException`).

Roda na VPS: venv/bin/python tests/teste_tipo_veiculo.py

🚨 NÃO FAZ REDE. Todo `weso_post` entra por dublê.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import operacoes_config as cfg  # noqa: E402
from fpsl_weso.painel import operacoes_os as oos  # noqa: E402
from fpsl_weso.painel.routers import operacoes_router as oper  # noqa: E402

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


def placa(txt, weso_veiculo_id=None, tipo_veiculo=None):
    return oos.PlacaOS(placa=txt, veiculo="CAMINHAO GENERICO",
                       weso_veiculo_id=weso_veiculo_id,
                       tipo_veiculo=tipo_veiculo)


def criada(placa_txt, ok_=True):
    return {"placa": placa_txt, "ok": ok_}


# ── 1. a tabela de códigos, medida na tela da WESO em 16/09 ─────────────────

def teste_tabela_de_codigos():
    print("\n1. A tabela de códigos — medida na tela, não suposta")
    esperado = {"carro": 1, "moto": 2, "caminhao": 3, "portatil": 4,
                "maquina": 5, "onibus": 6, "trator": 7}
    for nome, codigo in esperado.items():
        checar(f"{nome} -> {codigo}", cfg.resolver_tipo_veiculo(nome) == codigo)

    checar("maiúscula funciona igual", cfg.resolver_tipo_veiculo("MOTO") == 2)
    checar("espaço nas pontas não atrapalha",
           cfg.resolver_tipo_veiculo("  trator  ") == 7)
    checar("nome fora da lista não inventa código",
           cfg.resolver_tipo_veiculo("aviao") is None)
    checar("vazio não inventa código", cfg.resolver_tipo_veiculo("") is None)
    checar("None não inventa código", cfg.resolver_tipo_veiculo(None) is None)

    # 🚨 A TABELA ANTIGA (documentação e comentário velho) dizia isto -- e
    # ESTAVA ERRADA. Fixa aqui pra não reabrir por engano lendo a doc velha.
    checar("2 NÃO é caminhão (era o que a doc antiga dizia)",
           cfg.resolver_tipo_veiculo("moto") != 3)
    checar("5 NÃO é motocicleta (era o que a doc antiga dizia)",
           cfg.resolver_tipo_veiculo("maquina") != 2)


# ── 2. quem entra na correção ────────────────────────────────────────────────

def teste_selecao_de_placas():
    print("\n2. Só entra quem tem os dois dados e cuja OS saiu bem")

    p_completa = placa("TST 0C01", weso_veiculo_id=89211, tipo_veiculo="carro")
    saida = oper._placas_para_corrigir_tipo([p_completa], [criada("TST 0C01")])
    checar("placa completa, OS ok -> entra", saida == [(89211, 1)], str(saida))

    sem_weso_id = placa("TST 0X01", weso_veiculo_id=None, tipo_veiculo="moto")
    saida = oper._placas_para_corrigir_tipo([sem_weso_id], [criada("TST 0X01")])
    checar("sem weso_veiculo_id (perfil não cria veículo) -> não entra",
           saida == [], str(saida))

    sem_tipo = placa("TST 0X02", weso_veiculo_id=1, tipo_veiculo=None)
    saida = oper._placas_para_corrigir_tipo([sem_tipo], [criada("TST 0X02")])
    checar("sem tipo escolhido -> não entra", saida == [], str(saida))

    os_falhou = placa("TST 0X03", weso_veiculo_id=2, tipo_veiculo="caminhao")
    saida = oper._placas_para_corrigir_tipo(
        [os_falhou], [criada("TST 0X03", ok_=False)])
    checar("OS falhou no Harmonit -> não corrige o tipo",
           saida == [], str(saida))

    tipo_desconhecido = placa("TST 0X04", weso_veiculo_id=3, tipo_veiculo="aviao")
    saida = oper._placas_para_corrigir_tipo(
        [tipo_desconhecido], [criada("TST 0X04")])
    checar("tipo que não bate com nenhum dos 7 -> não entra",
           saida == [], str(saida))

    # 🚨 A FINANCEIRA TEM placa == "(financeira)" -- nunca deveria casar.
    financeira = criada("(financeira)")
    saida = oper._placas_para_corrigir_tipo([p_completa], [criada("TST 0C01"), financeira])
    checar("a entrada da financeira não interfere",
           saida == [(89211, 1)], str(saida))

    # duas placas, só uma com OS ok
    duas = [placa("TST 0A01", weso_veiculo_id=10, tipo_veiculo="moto"),
            placa("TST 0A02", weso_veiculo_id=11, tipo_veiculo="onibus")]
    resultados = [criada("TST 0A01", ok_=True), criada("TST 0A02", ok_=False)]
    saida = oper._placas_para_corrigir_tipo(duas, resultados)
    checar("só a placa cuja OS deu certo entra",
           saida == [(10, 2)], str(saida))


# ── 3. a correção nunca levanta, e conta as falhas ──────────────────────────

async def teste_corrigir_nunca_levanta():
    print("\n3. `_corrigir_tipos_veiculo` nunca levanta, mesmo com a WESO fora")

    chamadas = []

    async def _sempre_ok(rota, body, allow_409=False):
        chamadas.append((rota, body))
        return {"id": body["veiculo_id"]}

    original = oper.weso_post
    oper.weso_post = _sempre_ok
    try:
        placas = [placa("TST 0C01", weso_veiculo_id=89211, tipo_veiculo="carro"),
                  placa("TST 0M01", weso_veiculo_id=89212, tipo_veiculo="moto")]
        criadas = [criada("TST 0C01"), criada("TST 0M01")]
        falhas_n = await oper._corrigir_tipos_veiculo(placas, criadas)
        checar("nenhuma falha quando a WESO responde bem", falhas_n == 0)
        checar("manda os dois PUTs, com o campo achatado (fora do complemento)",
               chamadas == [("/Veiculos/Atualizar", {"veiculo_id": 89211, "tipo_eqp": 1}),
                            ("/Veiculos/Atualizar", {"veiculo_id": 89212, "tipo_eqp": 2})],
               str(chamadas))
    finally:
        oper.weso_post = original

    async def _sempre_falha(rota, body, allow_409=False):
        raise RuntimeError("WESO indisponível (simulado)")

    oper.weso_post = _sempre_falha
    try:
        placas = [placa("TST 0T01", weso_veiculo_id=89213, tipo_veiculo="caminhao")]
        criadas = [criada("TST 0T01")]
        # 🚨 O PONTO CENTRAL DO PEDIDO: isto NÃO PODE lançar.
        falhas_n = await oper._corrigir_tipos_veiculo(placas, criadas)
        checar("uma falha na WESO não propaga exceção", True)
        checar("e é contada", falhas_n == 1)
    finally:
        oper.weso_post = original

    # mistura: uma falha, uma sucesso -- a boa não pode ser jogada fora
    contador = {"n": 0}

    async def _uma_falha_uma_ok(rota, body, allow_409=False):
        contador["n"] += 1
        if contador["n"] == 1:
            raise RuntimeError("simulado")
        return {"id": body["veiculo_id"]}

    oper.weso_post = _uma_falha_uma_ok
    try:
        placas = [placa("TST 0X05", weso_veiculo_id=1, tipo_veiculo="carro"),
                  placa("TST 0X06", weso_veiculo_id=2, tipo_veiculo="moto")]
        criadas = [criada("TST 0X05"), criada("TST 0X06")]
        falhas_n = await oper._corrigir_tipos_veiculo(placas, criadas)
        checar("uma falha não impede a correção da outra placa",
               falhas_n == 1 and contador["n"] == 2, str(contador))
    finally:
        oper.weso_post = original


async def main():
    teste_tabela_de_codigos()
    teste_selecao_de_placas()
    await teste_corrigir_nunca_levanta()
    print(f"\n{'=' * 62}")
    print(f"{ok} verificações OK, {len(falhas)} falhas")
    if falhas:
        for f in falhas:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
