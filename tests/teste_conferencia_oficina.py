"""Conferência da oficina (01/10): a função pura, com dublê.

🚨 NÃO TOCA NO BANCO NEM NO CACHE. `conferir_os` recebe o de-para e o buscador
de serial como parâmetro, de propósito -- é o que permite testar os casos de
borda que não existem no dado real (série fora do cache, modelo sem de-para).

Os números dos casos são OS REAIS medidas em 01/10, para o teste falar a mesma
língua do banco.

    venv/bin/python tests/teste_conferencia_oficina.py
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fpsl_weso.services import conferencia_oficina as co   # noqa: E402

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


# de-para reduzido, com os ids reais do `painel_modelos_produto`
DE_PARA = {
    "SUNTECH ST310": 20314, "SUNTECH ST310U": 20314,
    "SUNTECH ST340": 7004, "SUNTECH ST300": 7006,
    "XT40-TM": 600267, "XT40": 338502,
    # NT2x e ST500 existem na WESO e NÃO têm de-para, de propósito (84 unidades)
}


def weso(mapa):
    """Dublê do cache, lado rastreador: {serial: (modelo, situacao)}.

    O `id` é derivado do próprio serial para o teste poder casar vínculo."""
    return lambda s: (
        {"id": "ID:" + s, "modelo": mapa[s][0], "situacao": mapa[s][1]}
        if s in mapa else None)


def placas(mapa):
    """Dublê do cache, lado veículo: {placa: serial que ela tem AGORA}.

    `None` como valor = placa existe na WESO e está sem rastreador."""
    return lambda p: ({"rastreador_id": ("ID:" + mapa[p]) if mapa[p] else None}
                      if p in mapa else None)


def onde(mapa):
    """Dublê da busca reversa: {serial: placa em que ele está HOJE}."""
    return lambda rid: mapa.get(rid[3:]) if rid else None


print("\n[1] o `problema` prevê a ação (regra medida em 197 OS)")
checar("7421 RETIRADA -> desinstalacao", "desinstalacao", co.acao_esperada(7421))
checar("7502 RESCISAO -> desinstalacao", "desinstalacao", co.acao_esperada(7502))
checar("7372 ADITIVO -> instalacao", "instalacao", co.acao_esperada(7372))
checar("7457 CONTRATO NOVO -> instalacao", "instalacao", co.acao_esperada(7457))
checar("7384 MANUTENCAO -> misto", "misto", co.acao_esperada(7384))
checar("7474 TRANSFERENCIA -> misto", "misto", co.acao_esperada(7474))
checar("problema 0 -> sem regra", "sem_regra", co.acao_esperada(0))
checar("problema nulo -> sem regra", "sem_regra", co.acao_esperada(None))
# 🚨 O TIPO NAO DECIDE: a OS 16962 e tipo 57 (Retirada) e a 16963 tipo 57 tambem,
# mas 64 OS medidas sao tipo 2 "Contrato", que nao diz acao nenhuma.
checar("tipo nao entra na conta (so problema)", "sem_regra", co.acao_esperada(57))

print("\n[2] retirada que bate nos tres (caso real: OS 16962)")
r = co.conferir_os(
    {"numero_os": 16962, "problema": 7502, "tipo": 57,
     "oficinas": [{"equipamentoId": "007786380", "veiculoPlaca": "RDM 3E86", "status": 2}],
     "materiais": [{"idProduto": 7277, "descricao": "RETIRADA CLIENTE"},
                   {"idProduto": 20314, "descricao": "ST310U"}]},
    DE_PARA, weso({"007786380": ("Suntech ST310", "Estoque")}),
    placas({"RDM 3E86": None}))          # placa existe e está sem rastreador
checar("acao bate com o problema", "ok", r["veredito_acao"])
checar("saiu da placa = retirou", "ok", r["veredito_weso"])
checar("modelo bate pelo de-para (ST310 -> 20314)", "ok", r["veredito_modelo"])
checar("e o detalhe nao inventa problema", "bate com a WESO", r["detalhe"])

print("\n[2b] 🚨 REUSO NÃO É DIVERGÊNCIA (caso real: OS 16972)")
# Medido em 01/10: a 16972 retirou o 907112547 da EPW 0I21, e hoje ele está na
# GKD 3D08. A regra antiga (esperar `Estoque`) acusava divergência -- e acusou em
# 46 das 199 OS, das quais 5 de cada 8 amostradas eram reuso legítimo.
r = co.conferir_os(
    {"numero_os": 16972, "problema": 7518,
     "oficinas": [{"equipamentoId": "907112547", "veiculoPlaca": "EPW 0I21", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"907112547": ("Suntech ST340", "Instalado")}),
    placas({"EPW 0I21": "OUTRO"}),       # a placa da OS tem outra série agora
    onde({"907112547": "GKD 3D08"}))     # e a série está noutra placa
checar("retirou e a serie foi para outra placa -> OK", "ok", r["veredito_weso"])

print("\n[2d] 🚨 a PLACA SUMIR da WESO numa retirada e o caminho normal")
# Medido em 01/10: 102 desinstalacoes com a placa fora da WESO -- 73 com a serie
# em Estoque, 26 reusada. A retirada EXCLUI o veiculo. Placa sumida confirma.
r = co.conferir_os(
    {"numero_os": 10, "problema": 7502,
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "SUMIU 1", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Estoque")}), placas({}), onde({}))
checar("placa excluida + serie em Estoque -> OK", "ok", r["veredito_weso"])

print("\n[2e] 🚨 rastreador preso: saiu da placa mas segue 'Instalado' sem veiculo")
r = co.conferir_os(
    {"numero_os": 11, "problema": 7502, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "SUMIU 1", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({}), onde({}))
checar("Instalado sem veiculo -> divergente", "divergente", r["veredito_weso"])
checar("e o detalhe nomeia o padrao", True, "preso" in r["detalhe"])

print("\n[2f] 🚨 OS SUPERADA: uma OS posterior mexeu na mesma serie")
# O estado de hoje e efeito da posterior -- julgar esta por ele seria acusar o
# passado pelo que veio depois.
r = co.conferir_os(
    {"numero_os": 16550, "problema": 7372,
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "FXP 1666", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}),
    placas({"FXP 1666": None}), onde({"A": "UEF 2D06"}),
    {"A": 16900})                        # a OS 16900 tocou a serie depois
checar("instalacao antiga superada -> indefinido, nao vermelho", "indefinido", r["veredito_weso"])
checar("e o detalhe diz qual OS", True, "16900" in r["detalhe"])
r = co.conferir_os(
    {"numero_os": 16900, "problema": 7372,
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "UEF 2D06", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}),
    placas({"UEF 2D06": "A"}), onde({"A": "UEF 2D06"}), {"A": 16900})
checar("a propria ultima OS continua julgavel", "ok", r["veredito_weso"])

print("\n[2c] e o defeito de verdade (caso real: OS 16940)")
# A 16940 retirou o 007933269 da DOT 0C95 -- e ele CONTINUA na DOT 0C95.
r = co.conferir_os(
    {"numero_os": 16940, "problema": 7502, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "007933269", "veiculoPlaca": "DOT 0C95", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"007933269": ("Suntech ST310", "Instalado")}),
    placas({"DOT 0C95": "007933269"}))   # segue na mesma placa
checar("retirou e segue na MESMA placa -> divergente", "divergente", r["veredito_weso"])
checar("e o detalhe nomeia a placa", True, "DOT 0C95" in r["detalhe"])

print("\n[3] 🚨 o furo do `eh_rastreador`: ST310U nao tem a palavra RASTREADOR")
checar("mas o de-para acha pelo idProduto", {20314},
       co.produtos_rastreador_da_os(
           [{"idProduto": 20314, "descricao": "ST310U"},
            {"idProduto": 7277, "descricao": "RETIRADA CLIENTE"}], set(DE_PARA.values())))
checar("e material que nao e rastreador fica fora", set(),
       co.produtos_rastreador_da_os(
           [{"idProduto": 11802, "descricao": "ENTREGA OS"}], set(DE_PARA.values())))

print("\n[4] troca: o material acompanha quem ENTRA (caso real: OS 16914)")
r = co.conferir_os(
    {"numero_os": 16914, "problema": 7384,
     "oficinas": [{"equipamentoId": "ENTRA", "veiculoPlaca": "AAA1A11", "status": 1},
                  {"equipamentoId": "SAI", "veiculoPlaca": "AAA1A11", "status": 2}],
     "materiais": [{"idProduto": 20314, "descricao": "ST310U"}]},
    DE_PARA, weso({"ENTRA": ("Suntech ST310", "Instalado"),
                   "SAI": ("Suntech ST340", "Estoque")}),
    placas({"AAA1A11": "ENTRA"}))        # a placa ficou com quem entrou
checar("modelo OK: vale quem entra (20314), nao quem sai (7004)", "ok", r["veredito_modelo"])
checar("WESO OK nas duas pontas da troca", "ok", r["veredito_weso"])
checar("manutencao e misto, entao a acao nao se julga", "indefinido", r["veredito_acao"])

print("\n[5] divergencia de modelo de verdade")
r = co.conferir_os(
    {"numero_os": 1, "problema": 7372,
     "oficinas": [{"equipamentoId": "X", "veiculoPlaca": "AAA1A11", "status": 1}],
     "materiais": [{"idProduto": 20314, "descricao": "ST310U"}]},
    DE_PARA, weso({"X": ("Suntech ST340", "Instalado")}),
    placas({"AAA1A11": "X"}))
checar("acusa divergencia", "divergente", r["veredito_modelo"])
checar("e diz os dois lados", True,
       "7004" in r["detalhe"] and "20314" in r["detalhe"])

print("\n[6] 🚨 ausencia NUNCA e vermelho")
r = co.conferir_os(
    {"numero_os": 2, "problema": 7502,
     "oficinas": [{"equipamentoId": "FORA", "veiculoPlaca": "AAA1A11", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({}), placas({"AAA1A11": None}))
checar("serie fora do cache -> WESO indefinido", "indefinido", r["veredito_weso"])
checar("e modelo indefinido, nao divergente", "indefinido", r["veredito_modelo"])

r = co.conferir_os(
    {"numero_os": 3, "problema": 7502,
     "oficinas": [{"equipamentoId": "NT", "veiculoPlaca": "AAA1A11", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"NT": ("NT2x", "Estoque")}), placas({"AAA1A11": None}))
checar("modelo SEM de-para -> indefinido (84 unidades reais)", "indefinido", r["veredito_modelo"])
checar("mas o vinculo ainda e conferivel", "ok", r["veredito_weso"])

r = co.conferir_os(
    {"numero_os": 4, "problema": 7502,
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "AAA1A11", "status": 2}],
     "materiais": [{"idProduto": 11802, "descricao": "ENTREGA OS"}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Estoque")}), placas({"AAA1A11": None}))
checar("OS sem material de rastreador -> indefinido", "indefinido", r["veredito_modelo"])

print("\n[7] instalacao numa placa que a WESO nao conhece")
r = co.conferir_os(
    {"numero_os": 5, "problema": 7372, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "SUH 9H53", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({}),
    onde({"A": "UEX 5E41"}))
checar("instalou em placa inexistente, serie noutro carro -> divergente",
       "divergente", r["veredito_weso"])
checar("e o detalhe diz a placa e onde a serie esta", True,
       "SUH 9H53" in r["detalhe"] and "UEX 5E41" in r["detalhe"])

print("\n[7b] 🚨 MESMO CARRO escrito diferente nao e divergencia (medido 01/10)")
# OS 16712: chassi sem rotulo x `CHASSI: ...` na WESO -- mesmo chassi.
r = co.conferir_os(
    {"numero_os": 16712, "problema": 7372, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "9BWKL45U5VP010644", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({}),
    onde({"A": "CHASSI: 9BWKL45U5VP010644"}))
checar("chassi com e sem rotulo -> mesmo carro -> OK", "ok", r["veredito_weso"])
# OS 16517: `OWE 0I25` x `(RD) OWE 0I25` -- RD e a convencao do rastreador redundante.
r = co.conferir_os(
    {"numero_os": 16517, "problema": 7372, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "OWE 0I25", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}),
    placas({"OWE 0I25": "OUTRA"}), onde({"A": "(RD) OWE 0I25"}))
checar("(RD) da mesma placa -> mesmo carro -> OK", "ok", r["veredito_weso"])
# OS gravou o CHASSI, a WESO ja tem a PLACA -- a coluna chassi do cache prova.
r = co.conferir_os(
    {"numero_os": 16900, "problema": 7372, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "CHASSI: 9BM951500TB474833", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({}),
    lambda rid: {"placa": "UEX 5E41", "chassi": "9BM951500TB474833"})
checar("chassi da OS = chassi do veiculo na WESO -> OK", "ok", r["veredito_weso"])
r = co.conferir_os(
    {"numero_os": 16900, "problema": 7372, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "CHASSI: 9BM951500TB474833", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({}),
    lambda rid: {"placa": "UEX 5E41", "chassi": "OUTROCHASSI0000"})
checar("chassi DIFERENTE -> segue divergente (nao relaxa a regra)", "divergente", r["veredito_weso"])
# A WESO guarda o chassi na DESCRICAO quando a coluna esta vazia (1690 de 1940).
r = co.conferir_os(
    {"numero_os": 16900, "problema": 7372, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "CHASSI: 9BM951500TB474833", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({}),
    lambda rid: {"placa": "UEX 5E41", "chassi": None,
                 "descricao": "CHASSI: 9BM951500TB474833"})
checar("chassi achado na DESCRICAO do veiculo -> mesmo carro -> OK", "ok", r["veredito_weso"])
# Trava: placa curta NAO casa por acaso dentro de texto livre.
r = co.conferir_os(
    {"numero_os": 13, "problema": 7372, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "MOB 1000", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({}),
    lambda rid: {"placa": "TDA 0A69", "chassi": None,
                 "descricao": "FIAT/MOB 1000 TREKKING, PRETA"})
checar("placa curta dentro de descricao livre NAO casa", "divergente", r["veredito_weso"])
# E o caso que fica vermelho de verdade (OS 16732): identificador que nao
# casa com nada -- uma perfuratriz cadastrada como BIO400.
r = co.conferir_os(
    {"numero_os": 16732, "problema": 7612, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": " C40025013", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({}),
    lambda rid: {"placa": "BIO400", "chassi": None, "descricao": "PERFURATRIZ DE SONDAGEM"})
checar("identificador sem correspondencia -> divergente (e para gente olhar)",
       "divergente", r["veredito_weso"])

print("\n[7c] 🚨 transferencia de titularidade: o rastreador fica no carro")
# OS 16510: 27 desinstalacoes, 26 seguindo na mesma placa -- nenhuma errada.
r = co.conferir_os(
    {"numero_os": 16510, "problema": 7474, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "BQI 5647", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}),
    placas({"BQI 5647": "A"}), onde({"A": "BQI 5647"}))
checar("transferencia: segue na placa -> indefinido, nao vermelho", "indefinido", r["veredito_weso"])
checar("e o detalhe explica", True, "transferência" in r["detalhe"])
r = co.conferir_os(
    {"numero_os": 9, "problema": 7502, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "BQI 5647", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}),
    placas({"BQI 5647": "A"}), onde({"A": "BQI 5647"}))
checar("mas numa RESCISAO o mesmo estado continua divergente", "divergente", r["veredito_weso"])

print("\n[7d] 🚨 OS ainda nao finalizada: ainda nao aconteceu nunca e vermelho")
for st in ("Nova", "Iniciada", None):
    r = co.conferir_os(
        {"numero_os": 12, "problema": 7372, "status_str": st,
         "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "AAA1A11", "status": 1}],
         "materiais": [{"idProduto": 20314}]},
        DE_PARA, weso({"A": ("Suntech ST310", "Estoque")}), placas({"AAA1A11": None}), onde({}))
    checar(f"status {st} -> indefinido", "indefinido", r["veredito_weso"])
    checar(f"status {st} -> motivo continua visivel", True, "não tem esta série" in r["detalhe"])

print("\n[8] 🚨 a situacao da WESO NAO decide o veredito -- o vinculo decide")
# Estoque/Bancada/Manutencao/Irrecuperavel dao o MESMO veredito se a serie saiu
# da placa. E `Instalado` tambem, DESDE QUE esteja noutro veiculo (reuso).
for sit in ("Estoque", "Bancada", "Manutenção", "Irrecuperável"):
    r = co.conferir_os(
        {"numero_os": 6, "problema": 7502,
         "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "AAA1A11", "status": 2}],
         "materiais": [{"idProduto": 20314}]},
        DE_PARA, weso({"A": ("Suntech ST310", sit)}), placas({"AAA1A11": None}), onde({}))
    checar(f"saiu da placa com situacao {sit} -> OK", "ok", r["veredito_weso"])
r = co.conferir_os(
    {"numero_os": 6, "problema": 7502,
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "AAA1A11", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({"AAA1A11": None}),
    onde({"A": "ZZZ9Z99"}))
checar("saiu da placa e esta Instalado em OUTRA -> OK (reuso)", "ok", r["veredito_weso"])

print("\n[9] acao que contradiz o problema")
r = co.conferir_os(
    {"numero_os": 7, "problema": 7421,     # RETIRADA
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "AAA1A11", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Instalado")}), placas({"AAA1A11": "A"}))
checar("retirada com instalacao -> divergente", "divergente", r["veredito_acao"])
checar("e diz o que achou", True, "instalação" in r["detalhe"])

print("\n[10] instalacao que nao refletiu na WESO")
r = co.conferir_os(
    {"numero_os": 9, "problema": 7372, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "AAA1A11", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"A": ("Suntech ST310", "Estoque")}), placas({"AAA1A11": None}))
checar("instalou e a placa nao tem a serie -> divergente", "divergente", r["veredito_weso"])

print("\n[11] a sandbox 16991, como ele a deixou")
r = co.conferir_os(
    {"numero_os": 16991, "problema": 7421, "tipo": 1785,
     "oficinas": [{"equipamentoId": "907011861", "veiculoPlaca": "PLACA1", "status": 1},
                  {"equipamentoId": "907011861", "veiculoPlaca": "PLACA1", "status": 2},
                  {"equipamentoId": "356354872124749", "veiculoPlaca": "OVG7C78", "status": 2}],
     "materiais": [{"idProduto": 20314, "descricao": "ST310U"}]},
    DE_PARA, weso({"907011861": ("Suntech ST340", "Manutenção"),
                   "356354872124749": ("XT40-TM", "Estoque")}),
    placas({}), onde({}))                # nenhuma das duas placas existe na WESO
# A 907011861 entra e DEPOIS sai da PLACA1: vale a saida, entao o efeito liquido
# da OS e retirada -- coerente com o problema 7421 RETIRADA.
checar("entrada superada pela saida -> acao bate com RETIRADA", "ok", r["veredito_acao"])
checar("entrada da 907011861 marcada como anulada pela propria saida", [True],
       [li["anulada_na_mesma_os"] for li in r["linhas"] if li["acao"] == 1])
checar("as duas desinstalacoes sairam da placa -> ok por linha", ["ok", "ok"],
       [li["veredito_situacao"] for li in r["linhas"] if li["acao"] == 2])
checar("entao o vinculo da OS fica OK", "ok", r["veredito_weso"])
checar("material ST310U x WESO ST340 -> modelo divergente", "divergente", r["veredito_modelo"])
checar("tres linhas conferidas", 3, len(r["linhas"]))

print("\n[11b] 🚨 vale a ULTIMA acao pelo id da oficina, nao 'a saida' (OS 16460)")
# Medido: instalou (198094), retirou (202562), instalou DE NOVO (202563).
r = co.conferir_os(
    {"numero_os": 16460, "problema": 7433, "status_str": "Finalizado",
     "oficinas": [{"id": 198094, "equipamentoId": "007458869", "veiculoPlaca": "ELW 5196", "status": 1},
                  {"id": 202562, "equipamentoId": "007458869", "veiculoPlaca": "ELW 5196", "status": 2},
                  {"id": 202563, "equipamentoId": "007458869", "veiculoPlaca": "ELW 5196", "status": 1}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"007458869": ("Suntech ST310", "Instalado")}),
    placas({"ELW 5196": "007458869"}), onde({"007458869": "ELW 5196"}))
checar("as duas primeiras ficam superadas, so a ultima vale", [True, True, False],
       [li["anulada_na_mesma_os"] for li in r["linhas"]])
checar("INSTALACAO com instalacao vigente -> acao OK", "ok", r["veredito_acao"])
checar("e a serie esta na placa -> vinculo OK", "ok", r["veredito_weso"])
# A mesma sequencia na ordem inversa (retirou por ultimo) da o oposto.
r = co.conferir_os(
    {"numero_os": 14, "problema": 7502, "status_str": "Finalizado",
     "oficinas": [{"id": 10, "equipamentoId": "B", "veiculoPlaca": "AAA1A11", "status": 1},
                  {"id": 11, "equipamentoId": "B", "veiculoPlaca": "AAA1A11", "status": 2}],
     "materiais": [{"idProduto": 20314}]},
    DE_PARA, weso({"B": ("Suntech ST310", "Estoque")}), placas({"AAA1A11": None}), onde({}))
checar("RESCISAO com saida por ultimo -> acao OK", "ok", r["veredito_acao"])

print("\n[11c] 🚨 regra do RFID: ST340 + leitor RFID = ST340RB (OS 16836)")
DE_PARA_RB = dict(DE_PARA, **{"SUNTECH ST340RB": 27241})
r = co.conferir_os(
    {"numero_os": 16836, "problema": 7502, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "AAA1A11", "status": 2}],
     "materiais": [{"idProduto": 6991, "descricao": "LEITOR RFID (404)"},
                   {"idProduto": 27241, "descricao": "ST340RB"}]},
    DE_PARA_RB, weso({"A": ("Suntech ST340", "Estoque")}), placas({"AAA1A11": None}), onde({}))
checar("WESO ST340 + RFID na OS -> ST340RB -> modelo OK", "ok", r["veredito_modelo"])
r = co.conferir_os(
    {"numero_os": 15, "problema": 7502, "status_str": "Finalizado",
     "oficinas": [{"equipamentoId": "A", "veiculoPlaca": "AAA1A11", "status": 2}],
     "materiais": [{"idProduto": 27241, "descricao": "ST340RB"}]},
    DE_PARA_RB, weso({"A": ("Suntech ST340", "Estoque")}), placas({"AAA1A11": None}), onde({}))
checar("sem leitor RFID na OS, ST340 x ST340RB segue divergente", "divergente", r["veredito_modelo"])

print("\n[12] OS sem oficina nenhuma")
r = co.conferir_os({"numero_os": 8, "problema": 7502, "oficinas": [], "materiais": []},
                   DE_PARA, weso({}), placas({}))
checar("nada a conferir, nada vermelho", ["indefinido"] * 3,
       [r["veredito_acao"], r["veredito_weso"], r["veredito_modelo"]])

print("\n" + "=" * 62)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
