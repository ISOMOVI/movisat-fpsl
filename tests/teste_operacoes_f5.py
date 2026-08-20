"""Aba Operações — F5, parte 1: o vínculo OS ↔ recipiente. 2026-08-20.

O que este arquivo PRENDE:

  1. **A geração grava o que fica pendente.** É o primeiro dos três riscos que
     a spec lista para a rotina: sem este vínculo, ela teria de deduzir seis
     horas depois, pela descrição da OS — frágil e falha em silêncio.

  2. **O caso vem do PERFIL, nunca do nome da placa.** `libera_serie` é
     recipiente; `vincula_apos_oficina` é substituição; `desativa_apos_oficina`
     é rescisão ou ressarcimento, conforme seja híbrida.

  3. **OS que falhou não vira pendência.** Ela não deixou nada pendente,
     deixou um erro — e esse já está no registro do lote.

  4. **Na substituição, quem carrega a pendência é a OS de RETIRADA**, e ela
     leva a placa de entrada junto. É a única que vincula.

  5. **O teto de tentativas corta o laço**, e `desistiu` sai da fila mas FICA
     na tabela, com o último erro. Desistir em silêncio devolveria o problema
     que o teto existe para resolver.

  6. **Regerar a mesma OS não cria pendência dobrada.**

Roda na VPS: venv/bin/python tests/teste_operacoes_f5.py
🚨 NÃO FAZ REDE. Grava só na tabela local, num lote próprio que ele apaga.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import operacoes_espera as esp  # noqa: E402
from fpsl_weso.painel import operacoes_os as oos  # noqa: E402
from fpsl_weso.painel import operacoes_config as cfg  # noqa: E402
from fpsl_weso.painel.routers import operacoes_router as opr  # noqa: E402

ok, falhas = 0, []
LOTE = "TESTE-F5"


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


def limpar():
    esp._criar()
    with storage._connect() as c:
        c.execute("DELETE FROM operacoes_espera WHERE lote = ?", (LOTE,))


def corpo(perfil, placas):
    return oos.MontarInput(perfil=perfil, cliente_id=998063, lote=LOTE,
                           termo="8800", produto_servico_id=777,
                           placas=placas, itens=[])


def pre_de(perfil_nome, recipientes=None):
    return {"perfil": cfg.PERFIS[perfil_nome],
            "ctx": {"recipientes": recipientes or {}}}


def op(placa, rotulo="Instalação"):
    return {"placa": placa, "rotulo": rotulo}


def criada(os_id, numero=1, ok_=True):
    return {"os_id": os_id, "numero_ordem": numero, "ok": ok_}


# ── 1. o caso vem do perfil ──────────────────────────────────────────────────

async def teste_caso_vem_do_perfil():
    print("\n1. O caso vem do PERFIL, nunca do nome da placa")
    limpar()
    esperado = {
        "upgrade": "recipiente",
        "manutencao_troca": "recipiente",
        "rescisao": "rescisao",
        "ressarcimento_sem_termo": "ressarcimento",
        "substituicao": "substituicao",
    }
    for i, (nome, caso) in enumerate(esperado.items()):
        limpar()
        placas = [oos.PlacaOS(placa="AAA 0A00", veiculo="X")]
        if nome == "substituicao":
            placas = [oos.PlacaOS(placa="AAA 0A00", veiculo="X",
                                  placa_entrada="BBB 0B00")]
        body = corpo(nome, placas)
        rotulo = "Retirada" if nome == "substituicao" else "Instalação"
        p = await opr._gravar_pendencias(
            body, pre_de(nome), [op("AAA 0A00", rotulo)], [criada(7000 + i)])
        checar(f"{nome:24} -> {caso}",
               len(p) == 1 and p[0]["caso"] == caso, str(p))

    limpar()
    body = corpo("contrato_novo", [oos.PlacaOS(placa="AAA 0A00")])
    p = await opr._gravar_pendencias(body, pre_de("contrato_novo"),
                                     [op("AAA 0A00")], [criada(7100)])
    checar("contrato novo NÃO deixa pendência — nada a terminar depois",
           p == [], str(p))


# ── 2. OS que falhou não vira pendência ──────────────────────────────────────

async def teste_falhou_nao_vira_pendencia():
    print("\n2. OS que falhou não vira pendência")
    limpar()
    body = corpo("upgrade", [oos.PlacaOS(placa="AAA 0A00")])
    p = await opr._gravar_pendencias(
        body, pre_de("upgrade"), [op("AAA 0A00")],
        [{"os_id": None, "ok": False, "erro": "o Harmonit recusou"}])
    checar("a OS que falhou não entra na fila", p == [], str(p))
    checar("e nada foi gravado", len(await esp.pendentes()) == 0)


# ── 3. a substituição: só a retirada carrega ─────────────────────────────────

async def teste_substituicao():
    print("\n3. Substituição — quem carrega é a OS de RETIRADA")
    limpar()
    body = corpo("substituicao", [oos.PlacaOS(placa="AAA 0A00", veiculo="X",
                                              placa_entrada="BBB 0B00")])
    p = await opr._gravar_pendencias(
        body, pre_de("substituicao"),
        [op("AAA 0A00", "Retirada"), op("BBB 0B00", "Instalação")],
        [criada(7201), criada(7202)])
    checar("uma pendência só, e não duas", len(p) == 1, str(p))
    checar("e é a da placa que SAI", p and p[0]["placa"] == "AAA 0A00", str(p))
    linhas = await esp.pendentes("substituicao")
    checar("a placa de ENTRADA viaja junto — é para lá que vincula",
           linhas and linhas[0]["placa_entrada"] == "BBB 0B00", str(linhas))


# ── 4. o recipiente vai com os números que a rotina precisa ──────────────────

async def teste_dados_do_recipiente():
    print("\n4. O recipiente vai com os números que a rotina vai usar")
    limpar()
    ch = oos.eqp.chave("AAA 0A00")
    pre = pre_de("upgrade", {ch: {"veiculo_id": 4242, "rastreador_id": 5151,
                                  "serie": "007933914"}})
    body = corpo("upgrade", [oos.PlacaOS(placa="AAA 0A00")])
    await opr._gravar_pendencias(body, pre, [op("AAA 0A00")], [criada(7301, 16999)])
    linhas = await esp.pendentes("recipiente")
    checar("grava o veiculo_id do recipiente",
           linhas and linhas[0]["veiculo_id"] == 4242, str(linhas))
    checar("grava o rastreador_id",
           linhas and linhas[0]["rastreador_id"] == 5151, str(linhas))
    checar("grava a placa derivada do recipiente",
           linhas and linhas[0]["recipiente_placa"] == "AAA0A00-UPGRADE",
           str(linhas))
    checar("e o número da OS, que é o que a pessoa procura",
           linhas and linhas[0]["numero_os"] == 16999, str(linhas))


# ── 5. regerar não duplica ───────────────────────────────────────────────────

async def teste_nao_duplica():
    print("\n5. Regerar a mesma OS não cria pendência dobrada")
    limpar()
    body = corpo("upgrade", [oos.PlacaOS(placa="AAA 0A00")])
    p1 = await opr._gravar_pendencias(body, pre_de("upgrade"),
                                      [op("AAA 0A00")], [criada(7401)])
    p2 = await opr._gravar_pendencias(body, pre_de("upgrade"),
                                      [op("AAA 0A00")], [criada(7401)])
    checar("a primeira grava", len(p1) == 1)
    checar("a segunda não grava de novo", p2 == [], str(p2))
    checar("e a fila tem uma linha só",
           len(await esp.pendentes("recipiente")) == 1)

    # ⚠️ Mesma OS, caso DIFERENTE, pode coexistir: a unicidade é (os_id, caso).
    novo = await esp.registrar(lote=LOTE, perfil="upgrade", caso="rescisao",
                               os_id=7401, numero_os=1, placa="AAA 0A00")
    checar("a mesma OS pode ter pendência de outro caso", novo is not None)


# ── 6. o teto corta o laço, e desistir não é sumir ──────────────────────────

async def teste_teto():
    print("\n6. O teto de tentativas corta o laço — e desistir não é sumir")
    limpar()
    ident = await esp.registrar(lote=LOTE, perfil="upgrade", caso="recipiente",
                                os_id=7501, numero_os=1, placa="AAA 0A00")
    estado = None
    for i in range(esp.TETO_TENTATIVAS - 1):
        estado = await esp.falhar(ident, "a série ainda não apareceu")
    checar(f"até {esp.TETO_TENTATIVAS - 1} tentativas continua esperando",
           estado == "esperando", str(estado))
    checar("e segue na fila", len(await esp.pendentes("recipiente")) == 1)

    estado = await esp.falhar(ident, "a série ainda não apareceu")
    checar(f"na tentativa {esp.TETO_TENTATIVAS} desiste", estado == "desistiu",
           str(estado))
    checar("sai da fila — não se tenta para sempre",
           len(await esp.pendentes("recipiente")) == 0)

    resumo = await esp.resumo()
    checar("mas FICA contado como desistiu, para virar aviso no Registro",
           resumo["desistiu"] == 1, str(resumo))
    with storage._connect() as c:
        r = c.execute("SELECT ultimo_erro FROM operacoes_espera WHERE id = ?",
                      (ident,)).fetchone()
    checar("com o último erro guardado",
           r and "série ainda não apareceu" in (r[0] or ""), str(r))

    # 🚨 O teto é decisão do usuário. O teste prende o NÚMERO de propósito:
    # mudá-lo tem de passar por aqui e ser deliberado.
    checar("o teto está declarado e é 28 (7 dias a cada 6 h)",
           esp.TETO_TENTATIVAS == 28, str(esp.TETO_TENTATIVAS))


# ── 7. concluir tira da fila ────────────────────────────────────────────────

async def teste_concluir():
    print("\n7. Concluir tira da fila")
    limpar()
    ident = await esp.registrar(lote=LOTE, perfil="rescisao", caso="rescisao",
                                os_id=7601, numero_os=1, placa="AAA 0A00")
    checar("entra na fila", len(await esp.pendentes("rescisao")) == 1)
    await esp.concluir(ident, ["devolveu ao estoque", "conferiu relendo"])
    checar("sai da fila ao concluir", len(await esp.pendentes("rescisao")) == 0)
    resumo = await esp.resumo()
    checar("e conta como concluido",
           resumo["por_estado"].get("concluido") == 1, str(resumo))


async def main():
    for t in (teste_caso_vem_do_perfil, teste_falhou_nao_vira_pendencia,
              teste_substituicao, teste_dados_do_recipiente,
              teste_nao_duplica, teste_teto, teste_concluir):
        await t()
    limpar()
    print(f"\n{'=' * 62}")
    print(f"{ok} verificações OK, {len(falhas)} falhas")
    if falhas:
        for f in falhas:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
