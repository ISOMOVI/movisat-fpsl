"""Aba Operações — F5, parte 2: a rotina e os quatro casos. 2026-08-20.

O que este arquivo PRENDE:

  1. **Todo caso declarado tem tratador.** Acrescentar um caso sem tratador
     faria a pendência ser contada como falha para sempre, calada.

  2. **A oficina é o GATILHO PARA IR OLHAR; quem decide é o estado relido.**
     A investigação de 08/2026 levanta que "o registro de oficina numa OS é uma
     INTENÇÃO" — agir sobre o registro seria agir antes de o trabalho
     acontecer. Com o equipamento já em Estoque, a rotina conclui sem escrever.

  3. **"A OS ainda não foi varrida" é diferente de "não há oficina".** As duas
     esperam, com mensagens diferentes: tratar como a mesma coisa faria a
     rotina desistir de trabalho que só não tinha sido lido ainda.

  4. **Devolver ao estoque é o primeiro passo, sempre.** Excluir o veículo não
     libera o rastreador — são duas chamadas.

  5. **Na substituição, solta antes de vincular.** A WESO recusa vincular
     rastreador já `Instalado`; a ordem inversa prende o equipamento no veículo
     errado. Se não soltou, NÃO tenta vincular.

  6. **Regravar a OS é save completo com releitura antes.** Mandar só a
     descrição apagaria o resto.

  7. **Pendência que estoura vira falha contada, não derruba o laço.**

Roda na VPS: venv/bin/python tests/teste_operacoes_f5b.py
🚨 NÃO FAZ REDE. Toda leitura e escrita externa entra por dublê.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import operacoes_equipamentos as eqp  # noqa: E402
from fpsl_weso.painel import operacoes_espera as esp  # noqa: E402
from fpsl_weso.painel import operacoes_rotina as rot  # noqa: E402

ok, falhas = 0, []
LOTE = "TESTE-F5B"


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
        c.execute("DELETE FROM os_historico WHERE numero_os >= 990000")


class Espiao:
    def __init__(self):
        self.ordem = []
        self.os_salva = None


def dubles(espiao, *, serie=None, rastreador_id=None, situacao="Instalado",
           veiculo_entrada_id=None, liberar_ok=True, soltar_ok=True,
           vincula=True, descricao_os=None, modelo="ST340",
           tem_de_para=True, material_entra=True):
    """Nenhuma chamada sai desta máquina depois disto."""
    estado = {"situacao": situacao, "vinculado": None, "materiais": []}

    def _produto(m):
        return ({"harmonit_id": 9001, "descricao": f"RASTREADOR {m}",
                 "valor": 480.0} if tem_de_para else None)

    storage.produto_do_modelo = _produto
    rot.storage.produto_do_modelo = _produto

    async def _dados(placas, falhas=None):
        saida = {}
        for p in placas:
            ch = eqp.chave(p)
            if "UPGRADE" in str(p).upper() or "MANUT" in str(p).upper():
                saida[ch] = {"serie": serie, "veiculo_id": 4242,
                             "rastreador_id": rastreador_id, "modelo": modelo}
            elif ch == eqp.chave("BBB 0B00"):
                # ⚠️ `veiculo_entrada_id=None` significa PLACA QUE NÃO EXISTE na
                # WESO. Devolver um veiculo_id qualquer aqui faria o dublê
                # mentir, e o teste mediria o contrário do que diz medir.
                if not veiculo_entrada_id:
                    continue
                saida[ch] = {"veiculo_id": veiculo_entrada_id,
                             "rastreador_id": estado["vinculado"]}
            else:
                saida[ch] = {"veiculo_id": 1111,
                             "rastreador_id": rastreador_id}
        return saida

    async def _situacao(rid):
        return estado["situacao"]

    async def _mudar(rid, nova):
        espiao.ordem.append(f"situacao->{nova}")
        if nova == eqp.SITUACAO_LIVRE and not soltar_ok:
            return False
        estado["situacao"] = nova
        return True

    async def _liberar(vid, rid):
        espiao.ordem.append("liberar_recipiente")
        if not liberar_ok:
            return {"ok": False, "erro": "nao liberou", "passos": [],
                    "dados_para_correcao": {}}
        return {"ok": True, "passos": ["estoque", "recipiente apagado"]}

    async def _weso_post(path, corpo, **kw):
        espiao.ordem.append(f"weso_post {path}")
        if vincula:
            estado["vinculado"] = corpo.get("id")
        return {}

    async def _hpost(path, payload):
        if "Material" in path:
            espiao.ordem.append("anexar_material")
            if material_entra:
                estado["materiais"].append(payload)
            return {}
        espiao.ordem.append("salvar_os")
        espiao.os_salva = payload
        return {}

    eqp.dados_das_placas = _dados
    eqp._situacao_do_rastreador = _situacao
    eqp._mudar_situacao = _mudar
    eqp.liberar_recipiente = _liberar
    eqp.weso_post = _weso_post
    rot.harmonit_post = _hpost

    chamadas = {"os": 0}

    async def _hget(path, params=None):
        if "Materiais" in path:
            espiao.ordem.append("ler_materiais")
            return list(estado["materiais"])
        espiao.ordem.append("ler_os")
        chamadas["os"] += 1
        texto = descricao_os or (
            f"Upgrade | ENTRARÁ: {eqp.MARCADOR_SERIE_A_PREENCHER}")
        # A segunda leitura é a conferência: já com a série trocada.
        if chamadas["os"] > 1 and serie:
            texto = texto.replace(eqp.MARCADOR_SERIE_A_PREENCHER, serie)
        return {"id": 900, "numeroOrdem": 990001, "clienteId": 1,
                "descricaoDetalhada": texto,
                "outroCampo": "nao pode sumir"}

    rot.harmonit_get = _hget
    return estado


async def pendencia(caso, **extra):
    limpar()
    ident = await esp.registrar(lote=LOTE, perfil=extra.pop("perfil", "upgrade"),
                                caso=caso, os_id=extra.pop("os_id", 900),
                                numero_os=990001,
                                placa=extra.pop("placa", "AAA 0A00"), **extra)
    return (await esp.pendentes(caso))[0]


def gravar_oficina(numero_os, status):
    esp._criar()
    import json
    from datetime import datetime, timezone
    agora = datetime.now(timezone.utc).isoformat()
    with storage._connect() as c:
        c.execute("INSERT OR REPLACE INTO os_historico (numero_os, tipo, "
                  "problema, produto_id, cliente_id, data_previsao, "
                  "oficinas_json, n_oficinas, visto_em, atualizado_em) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (numero_os, 1, 1, 1, 1, None,
                   json.dumps([{"status": status}]), 1, agora, agora))


# ── 1. cobertura ─────────────────────────────────────────────────────────────

async def teste_cobertura():
    print("\n1. Todo caso declarado tem tratador")
    checar("os quatro casos têm tratador",
           sorted(rot._TRATADORES) == sorted(esp.CASOS),
           f"{sorted(rot._TRATADORES)} != {sorted(esp.CASOS)}")
    checar("status de desinstalação é 2 (medido, não suposto)",
           rot.STATUS_OFICINA_DESINSTALACAO == 2)
    checar("a rotina roda de 6 em 6 horas", rot.INTERVALO_ROTINA == 6 * 3600)


# ── 2. o recipiente ──────────────────────────────────────────────────────────

async def teste_recipiente():
    print("\n2. Recipiente — série apareceu, escreve, devolve e apaga")
    e = Espiao()
    dubles(e, serie=None)
    p = await pendencia("recipiente", recipiente_placa="AAA0A00-UPGRADE")
    r = await rot._caso_recipiente(p)
    checar("sem série, não age e continua esperando",
           r["ok"] is False and r["estado"] == "esperando", str(r))
    checar("e não tocou em nada", e.ordem == [], str(e.ordem))

    e = Espiao()
    dubles(e, serie="007933914", rastreador_id=50171)
    p = await pendencia("recipiente", recipiente_placa="AAA0A00-UPGRADE")
    r = await rot._caso_recipiente(p)
    checar("com série, conclui", r["ok"] is True, str(r))
    checar("escreveu a série na OS antes de liberar",
           e.ordem.index("salvar_os") < e.ordem.index("liberar_recipiente"),
           str(e.ordem))
    checar("releu a OS ANTES de gravar — é save completo",
           e.ordem[0] == "ler_os", str(e.ordem))
    checar("o payload leva o resto da OS, não só a descrição",
           e.os_salva and e.os_salva.get("outroCampo") == "nao pode sumir",
           str(e.os_salva))
    checar("a série entra no lugar do marcador",
           e.os_salva and "007933914" in e.os_salva["descricaoDetalhada"]
           and eqp.MARCADOR_SERIE_A_PREENCHER
           not in e.os_salva["descricaoDetalhada"], str(e.os_salva))
    checar("e a pendência sai da fila",
           len(await esp.pendentes("recipiente")) == 0)

    e = Espiao()
    dubles(e, serie="007933914", rastreador_id=50171, liberar_ok=False)
    p = await pendencia("recipiente", recipiente_placa="AAA0A00-UPGRADE")
    r = await rot._caso_recipiente(p)
    checar("se a liberação falha, a pendência NÃO conclui",
           r["ok"] is False, str(r))
    checar("e continua na fila para a próxima rodada",
           len(await esp.pendentes("recipiente")) == 1)


# ── 2b. a terceira prova: o equipamento nos MATERIAIS ────────────────────────

async def teste_equipamento_nos_materiais():
    print("\n2b. O equipamento entra nos MATERIAIS, não só na descrição")
    e = Espiao()
    dubles(e, serie="007933914", rastreador_id=50171, modelo="ST340")
    p = await pendencia("recipiente", recipiente_placa="AAA0A00-UPGRADE")
    r = await rot._caso_recipiente(p)
    checar("conclui quando o equipamento entra", r["ok"] is True, str(r))
    checar("anexou o material", "anexar_material" in e.ordem, str(e.ordem))
    checar("conferiu RELENDO os materiais", "ler_materiais" in e.ordem,
           str(e.ordem))
    checar("anexou ANTES de liberar o recipiente",
           e.ordem.index("anexar_material")
           < e.ordem.index("liberar_recipiente"), str(e.ordem))

    # 🚨 Sem produto no de-para o equipamento NÃO pode entrar nos materiais, e
    # liberar a série ali deixaria a OS com série no texto e sem equipamento --
    # que é o defeito do termo 8820. Vira pendência visível, não série solta.
    e = Espiao()
    dubles(e, serie="007933914", rastreador_id=50171, modelo="ST500",
           tem_de_para=False)
    p = await pendencia("recipiente", recipiente_placa="AAA0A00-UPGRADE")
    r = await rot._caso_recipiente(p)
    checar("modelo sem de-para NÃO conclui", r["ok"] is False, str(r))
    checar("e NÃO libera o recipiente",
           "liberar_recipiente" not in e.ordem, str(e.ordem))
    checar("o motivo aponta o de-para", "de-para" in str(r["erro"]), str(r))

    e = Espiao()
    dubles(e, serie="007933914", rastreador_id=50171, material_entra=False)
    p = await pendencia("recipiente", recipiente_placa="AAA0A00-UPGRADE")
    r = await rot._caso_recipiente(p)
    checar("material que não aparece na releitura NÃO conclui",
           r["ok"] is False, str(r))
    checar("e o recipiente fica onde está",
           "liberar_recipiente" not in e.ordem, str(e.ordem))


# ── 3. a oficina é gatilho, o estado decide ──────────────────────────────────

async def teste_oficina_e_gatilho():
    print("\n3. A oficina é o gatilho; quem decide é o estado relido")
    e = Espiao()
    dubles(e, rastreador_id=50171)
    p = await pendencia("rescisao", perfil="rescisao")
    r = await rot._caso_devolver(p)
    checar("OS não varrida ainda: espera, e diz isso",
           r["ok"] is False and "varrid" in str(r["erro"]), str(r))
    checar("e não tocou na WESO", e.ordem == [], str(e.ordem))

    e = Espiao()
    dubles(e, rastreador_id=50171)
    p = await pendencia("rescisao", perfil="rescisao")
    gravar_oficina(990001, rot.STATUS_OFICINA_INSTALACAO)
    r = await rot._caso_devolver(p)
    checar("oficina de INSTALAÇÃO não dispara a devolução",
           r["ok"] is False and "desinstala" in str(r["erro"]), str(r))
    checar("e continua sem tocar na WESO", e.ordem == [], str(e.ordem))

    # 🚨 O caso que a hipótese da INTENÇÃO obriga a cobrir.
    e = Espiao()
    dubles(e, rastreador_id=50171, situacao=eqp.SITUACAO_LIVRE)
    p = await pendencia("rescisao", perfil="rescisao")
    gravar_oficina(990001, rot.STATUS_OFICINA_DESINSTALACAO)
    r = await rot._caso_devolver(p)
    checar("com oficina mas JÁ em Estoque, conclui sem escrever",
           r["ok"] is True, str(r))
    checar("e NÃO chamou mudança de situação",
           not any("situacao->" in x for x in e.ordem), str(e.ordem))

    e = Espiao()
    dubles(e, rastreador_id=50171, situacao=eqp.SITUACAO_PRESA)
    p = await pendencia("rescisao", perfil="rescisao")
    gravar_oficina(990001, rot.STATUS_OFICINA_DESINSTALACAO)
    r = await rot._caso_devolver(p)
    checar("com oficina e ainda Instalado, devolve ao estoque",
           r["ok"] is True, str(r))
    checar("chamando a mudança de situação",
           f"situacao->{eqp.SITUACAO_LIVRE}" in e.ordem, str(e.ordem))

    e = Espiao()
    dubles(e, rastreador_id=None, situacao=eqp.SITUACAO_PRESA)
    p = await pendencia("rescisao", perfil="rescisao")
    gravar_oficina(990001, rot.STATUS_OFICINA_DESINSTALACAO)
    r = await rot._caso_devolver(p)
    checar("veículo sem rastreador conclui — o estado desejado já existe",
           r["ok"] is True, str(r))


# ── 4. a substituição ────────────────────────────────────────────────────────

async def teste_substituicao():
    print("\n4. Substituição — solta antes de vincular, sempre")
    e = Espiao()
    dubles(e, rastreador_id=50171, situacao=eqp.SITUACAO_PRESA,
           veiculo_entrada_id=8888)
    p = await pendencia("substituicao", perfil="substituicao",
                        placa_entrada="BBB 0B00")
    gravar_oficina(990001, rot.STATUS_OFICINA_DESINSTALACAO)
    r = await rot._caso_substituicao(p)
    checar("conclui", r["ok"] is True, str(r))
    i_solta = next(i for i, x in enumerate(e.ordem) if "situacao->Estoque" in x)
    i_vinc = next(i for i, x in enumerate(e.ordem) if "weso_post" in x)
    checar("SOLTOU antes de vincular", i_solta < i_vinc, str(e.ordem))

    e = Espiao()
    dubles(e, rastreador_id=50171, situacao=eqp.SITUACAO_PRESA,
           veiculo_entrada_id=8888, soltar_ok=False)
    p = await pendencia("substituicao", perfil="substituicao",
                        placa_entrada="BBB 0B00")
    gravar_oficina(990001, rot.STATUS_OFICINA_DESINSTALACAO)
    r = await rot._caso_substituicao(p)
    checar("se não soltou, NÃO tenta vincular", r["ok"] is False, str(r))
    checar("e nenhuma escrita de vínculo saiu",
           not any("weso_post" in x for x in e.ordem), str(e.ordem))

    e = Espiao()
    dubles(e, rastreador_id=50171, situacao=eqp.SITUACAO_PRESA,
           veiculo_entrada_id=None)
    p = await pendencia("substituicao", perfil="substituicao",
                        placa_entrada="BBB 0B00")
    gravar_oficina(990001, rot.STATUS_OFICINA_DESINSTALACAO)
    r = await rot._caso_substituicao(p)
    checar("placa de entrada inexistente: para e entrega os números",
           r["ok"] is False and r["dados_para_correcao"].get("rastreador_id")
           == 50171, str(r))


# ── 5. o laço não cai ────────────────────────────────────────────────────────

async def teste_laco():
    print("\n5. Pendência que estoura vira falha contada, não derruba o laço")
    e = Espiao()
    dubles(e, serie="1")

    async def _explode(p):
        raise RuntimeError("estourei de proposito")

    original = rot._TRATADORES["recipiente"]
    rot._TRATADORES["recipiente"] = _explode
    try:
        await pendencia("recipiente", recipiente_placa="AAA0A00-UPGRADE")
        r = await rot.rodar("recipiente")
        checar("a passada termina mesmo com pendência que estoura",
               r["lidas"] == 1 and r["concluidas"] == 0, str(r))
        checar("e o erro fica registrado na pendência",
               any("inesperado" in str(x.get("erro")) for x in r["resultados"]),
               str(r["resultados"]))
    finally:
        rot._TRATADORES["recipiente"] = original


async def main():
    for t in (teste_cobertura, teste_recipiente,
              teste_equipamento_nos_materiais, teste_oficina_e_gatilho,
              teste_substituicao, teste_laco):
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
