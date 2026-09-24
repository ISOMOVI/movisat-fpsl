"""Aquisição na retirada não cobra — 24/09, termo 8893.

🔵 O usuário, ao ver a cobrança do LEITOR I-BUTTON no termo 8893: *"quando é
'aquisição' na verdade, no caso da recisão, é que ele ja comprou e não vai
devolver"*. Decisão (1a): entra na financeira ZERADO e sem cobrar, como a
Central; vale para os perfis de retirada (`cfg.PERFIS_RETIRADA`).

O que este arquivo PRENDE, e que reprova se alguém desfizer:
  1. **Termo 8893 real:** o leitor (AQUISIÇÃO, R$ 150,00) sai da financeira
     da rescisão com valor zero e sem `cobrar`. Reprova no código de antes.
  2. **O valor também zera**, não só a flag: `itens_de_cobranca` recalcula o
     `cobrar` pelo valor e desfaria a flag sozinha.
  3. **Contrato continua cobrando aquisição** -- lá é compra nova.
  4. **Comodato não é tocado** na retirada (valor patrimonial da DANFE).
  5. **Os três perfis de retirada** aplicam a regra; ressarcimento não.

Roda na VPS: venv/bin/python tests/teste_aquisicao_retirada.py
🚨 NÃO FAZ REDE E NÃO ESCREVE EM SISTEMA EXTERNO.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg  # noqa: E402
from fpsl_weso.painel import operacoes_os as oos  # noqa: E402

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# ⚠️ IDS REAIS dos vínculos de produção (mesmos de `teste_central_nas_duas`).
CATALOGO = {
    "CENTRAL 24 HORAS": {"harmonit_id": 6976, "oculto": False, "nas_duas": True},
    "RASTREADOR": {"harmonit_id": 20314, "oculto": False, "nas_duas": False},
    "CHIP DE DADOS": {"harmonit_id": 16016, "oculto": False, "nas_duas": False},
    "BLOQUEIO VEICULAR": {"harmonit_id": 45689, "oculto": False, "nas_duas": False},
    "LEITOR I-BUTTON": {"harmonit_id": 6984, "oculto": False, "nas_duas": False},
}


async def _vinculo(nome):
    return CATALOGO.get(oos._sem_acento(nome))


def instalar_dubles():
    storage.buscar_vinculo_item = _vinculo
    oos.storage.buscar_vinculo_item = _vinculo


def item(desc, valor, tipo):
    return oos.ItemContrato(descricao=desc, quantidade="01",
                            valor_unitario=valor, comodato_ou_aquisicao=tipo)


# O termo 8893, linha a linha como está no PDF.
TERMO_8893 = [
    item("RASTREADOR", "999,90", "COMODATO"),
    item("CHIP DE DADOS", "50,00", "COMODATO"),
    item("BLOQUEIO VEICULAR", "50,00", "COMODATO"),
    item("CENTRAL 24 HORAS", "10,00", "DESATIVAR NO SISTEMA"),
    item("LEITOR I-BUTTON", "150,00", "AQUISIÇÃO"),
]


def _leitor(itens):
    return next((i for i in itens if i["descricao"] == "LEITOR I-BUTTON"), None)


async def teste_termo_8893():
    print("\n1-2. Termo 8893 real — o leitor de aquisição não é cobrado")
    resolvidos, *_ = await oos.resolver_vinculos(TERMO_8893, perfil_chave="rescisao")
    _op, fin = oos.separar_itens(cfg.PERFIS["rescisao"], resolvidos)
    leitor = _leitor(fin)
    checar("o leitor continua na financeira (o financeiro vê que existe)", leitor is not None)
    checar("sem cobrar", leitor and leitor["cobrar"] is False, str(leitor))
    checar("valor zerado (senão itens_de_cobranca recalcula o cobrar)",
           leitor and leitor["valor_unitario"] == 0.0, str(leitor))
    checar("marcado como aquisição do cliente (a prévia avisa)",
           leitor and leitor.get("aquisicao_do_cliente") is True)
    cobrados = [i["descricao"] for i in fin if i.get("cobrar")]
    checar("nada de equipamento cobrado na financeira", cobrados == [], str(cobrados))


async def teste_contrato_continua_cobrando():
    print("\n3. Contrato — aquisição é compra nova e continua cobrando")
    resolvidos, *_ = await oos.resolver_vinculos(TERMO_8893, perfil_chave="contrato_novo")
    leitor = _leitor(resolvidos)
    checar("no contrato o leitor cobra R$ 150,00",
           leitor and leitor["cobrar"] is True and leitor["valor_unitario"] == 150.0,
           str(leitor))
    sem_perfil, *_ = await oos.resolver_vinculos(TERMO_8893)
    checar("sem perfil informado, comportamento antigo (cobra)",
           _leitor(sem_perfil)["cobrar"] is True)


async def teste_comodato_intocado():
    print("\n4. Comodato na retirada não perde o valor patrimonial")
    resolvidos, *_ = await oos.resolver_vinculos(TERMO_8893, perfil_chave="rescisao")
    rastreador = next(i for i in resolvidos if i["descricao"] == "RASTREADOR")
    checar("rastreador segue comodato com R$ 999,90",
           rastreador["comodato"] is True and rastreador["valor_unitario"] == 999.9,
           str(rastreador))


async def teste_perfis():
    print("\n5. Quem aplica a regra")
    for chave in ("rescisao", "transferencia_antigo_titular", "transferencia_termo_novo"):
        resolvidos, *_ = await oos.resolver_vinculos(TERMO_8893, perfil_chave=chave)
        checar(f"{chave}: leitor não cobra", _leitor(resolvidos)["cobrar"] is False)
    for chave in ("ressarcimento_com_termo", "ressarcimento_sem_termo", "upgrade", "aditivo"):
        resolvidos, *_ = await oos.resolver_vinculos(TERMO_8893, perfil_chave=chave)
        checar(f"{chave}: fora da regra (cobra)", _leitor(resolvidos)["cobrar"] is True)
    checar("todo perfil de retirada existe no cadastro de perfis",
           cfg.PERFIS_RETIRADA <= set(cfg.PERFIS), str(cfg.PERFIS_RETIRADA - set(cfg.PERFIS)))


async def main():
    instalar_dubles()
    for t in (teste_termo_8893, teste_contrato_continua_cobrando,
              teste_comodato_intocado, teste_perfis):
        await t()
    print(f"\n{'=' * 62}")
    print(f"{ok} verificações OK, {len(falhas)} falhas")
    if falhas:
        for f in falhas:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
