"""Regressão do perfil UPGRADE — termo real 8820 (2026-08-13).

🚨 UPGRADE NÃO É SUBSTITUIÇÃO. Na Substituição muda o VEÍCULO (equipamento vai
do veículo A para o B, os dois reais, os dois no documento). No Upgrade muda o
EQUIPAMENTO e o veículo é o mesmo — a placa `-UPGRADE` é um RECIPIENTE DE TESTE
criado pelo setor de configuração na WESO, não um destino.

O que este teste trava:
  1. extração do 8820 — 2 de 2 placas, sem inventar e sem perder;
  2. derivação da placa-recipiente (`OOM 4131` -> `OOM4131-UPGRADE`);
  3. a descrição final com SAIRÁ e ENTRARÁ e as duas séries certas;
  4. a conferência de termo — recipiente de OUTRO termo não passa;
  5. ausência de recipiente NÃO bloqueia (best-effort da casa).

Roda na VPS:  venv/bin/python tests/teste_upgrade_8820.py
Só leitura — não toca Harmonit nem escreve na WESO. Usa o cache local.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import equipamentos, templates_config  # noqa: E402
from fpsl_weso.painel.pdf_extractor import extrair_campos  # noqa: E402
from fpsl_weso.painel.routers import os_router  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


# ── 1. extração ──────────────────────────────────────────────────────────────
r = extrair_campos(str(FIXTURES / "upgrade_8820.pdf"), "upgrade")

checar("termo", "8820", r["termo"])
checar("cnpj", "26.137.632/0001-95", r["cnpj"])
checar("cliente", "M TRANS TRANSPORTE E LOGISTICA LTDA", r["cliente_nome_sugerido"])
checar("quantas placas", 2, len(r["placas"]))
checar("placa 1", "OOM 3895", r["placas"][0]["placa"])
checar("placa 2", "OOM 4131", r["placas"][1]["placa"])
checar("veiculo 2", "SR/FACCHINI SRF CA, DIESEL, 2015/2016, CINZA", r["placas"][1]["veiculo"])
# 8721 é DOCUMENTO REFERÊNCIA, não placa -- a coluna vizinha não pode vazar
checar("nao vira placa o doc de referencia", [],
       [p for p in r["placas"] if "8721" in p["placa"]])
checar("nenhum veiculo sem placa", [], r["veiculos_sem_placa"])

# ── 2. derivação do recipiente ───────────────────────────────────────────────
checar("deriva OOM 4131", "OOM4131-UPGRADE", equipamentos.placa_teste("OOM 4131", "-UPGRADE"))
checar("deriva com espaco e minuscula", "OOM3895-UPGRADE",
       equipamentos.placa_teste("  oom 3895 ", "-UPGRADE"))
checar("placa vazia nao deriva", "", equipamentos.placa_teste("", "-UPGRADE"))

# ── 3. o perfil ──────────────────────────────────────────────────────────────
perfil = templates_config.PERFIS["upgrade"]
checar("1 OS por placa (nao e substituicao)", 1, perfil["os_por_placa"])
checar("sufixo do recipiente", "-UPGRADE", perfil["placa_teste_sufixo"])
checar("template tem SAIRA", True, "SAIRÁ: {serie}" in perfil["descricao_template"])
checar("template tem ENTRARA", True, "ENTRARÁ: {serie_entrada}" in perfil["descricao_template"])

# ── 4. a descrição final, ponta a ponta ──────────────────────────────────────
seriais = asyncio.run(equipamentos.buscar_seriais(
    ["OOM 4131", "OOM 3895", "OOM4131-UPGRADE", "OOM3895-UPGRADE"]))

checar("serie que SAI da OOM 4131", "356354872583936", equipamentos.serie_de(seriais, "OOM 4131"))
checar("serie que ENTRA na OOM 4131", "356354871411980",
       equipamentos.serie_de(seriais, "OOM4131-UPGRADE"))
checar("serie que SAI da OOM 3895", "356354872585899", equipamentos.serie_de(seriais, "OOM 3895"))
# ⚠️ na WESO esta gravada como ' OOM3895-UPGRADE', com espaco na frente
checar("serie que ENTRA na OOM 3895 (apesar do espaco na WESO)", "356354871410958",
       equipamentos.serie_de(seriais, "OOM3895-UPGRADE"))

# 🚨 MUDOU EM 14/08: o dado do recipiente deixou de ser lido DENTRO de
# `_modelo_da_operacao` e passa por fora, num dicionario montado uma vez por
# geracao. O motivo e a manutencao, que precisa ler ao vivo (o recipiente nasce
# minutos antes da OS e o cache so atualiza as 04:15). O upgrade continua
# lendo do cache -- monta o mesmo formato a partir dele, como faz `gerar_os`.
RECIPIENTES = {
    equipamentos._chave(p): {
        "descricao": equipamentos.descricao_da_placa(equipamentos.placa_teste(p, "-UPGRADE")),
        "modelo": equipamentos.modelo_da_placa(equipamentos.placa_teste(p, "-UPGRADE")),
        "serie": equipamentos.serie_de(seriais, equipamentos.placa_teste(p, "-UPGRADE")),
    }
    for p in ("OOM 4131", "OOM 3895")
}

checar("descricao completa da OOM 4131",
       "Upgrade: OOM 4131 | SR/FACCHINI SRF CA, DIESEL, 2015/2016, CINZA | "
       "SAIRÁ: 356354872583936 (XT40) | ENTRARÁ: 356354871411980 (XT40 Portatil) | "
       "TERMO 8820",
       perfil["descricao_template"].format(
           placa="OOM 4131", veiculo="SR/FACCHINI SRF CA, DIESEL, 2015/2016, CINZA",
           termo="8820", serie=equipamentos.serie_de(seriais, "OOM 4131"),
           serie_entrada=equipamentos.serie_de(seriais, "OOM4131-UPGRADE"),
           modelo=os_router._modelo_da_operacao(perfil, "OOM 4131", [], RECIPIENTES),
           modelo_saida=equipamentos.modelo_efetivo(
               equipamentos.modelo_da_placa("OOM 4131"), False)))

# ── 6. o modelo vem da WESO pelo ID da placa, nao do vinculo ─────────────────
# 🚨 O vinculo diria ST310U ou XT40 4G conforme o TEXTO do termo. A WESO diz o
# que esta de fato no veiculo -- e no upgrade, o que ENTRA e outro aparelho.
checar("modelo do que SAI da OOM 4131", "XT40", equipamentos.modelo_da_placa("OOM 4131"))
checar("modelo do que ENTRA na OOM 4131", "XT40 Portatil",
       equipamentos.modelo_da_placa("OOM4131-UPGRADE"))
checar("modelo do que SAI da OOM 3895", "XT40", equipamentos.modelo_da_placa("OOM 3895"))
checar("modelo do que ENTRA na OOM 3895", "XT40 Portatil",
       equipamentos.modelo_da_placa("OOM3895-UPGRADE"))
checar("perfil upgrade le o modelo do recipiente", "placa_teste",
       perfil.get("modelo_origem"))
checar("_modelo_da_operacao do upgrade devolve o que ENTRA", "XT40 Portatil",
       os_router._modelo_da_operacao(perfil, "OOM 4131", [], RECIPIENTES))
# 🚨 SEM RECIPIENTE NAO INVENTA MODELO. Antes de 14/08 a funcao ia ao cache por
# dentro; agora, se o recipiente nao chegou (nao existe, ambiguo ou de outra
# rodada), o modelo e o marcador -- e sem modelo nao ha produto, entao o
# equipamento nao entra nos materiais. E a trava que sustenta a decisao de
# gerar com `NUMERO DE SERIE` em vez de recusar.
checar("upgrade sem recipiente devolve o marcador, nao um modelo plausivel",
       equipamentos.MARCADOR_MODELO,
       os_router._modelo_da_operacao(perfil, "OOM 4131", [], {}))
checar("placa inexistente devolve None, nao string", None,
       equipamentos.modelo_da_placa("XXX0000"))

# ── 7. a regra do ST340RB ────────────────────────────────────────────────────
# ⚠️ A WESO NAO sabe se o veiculo tem RFID -- a API de rastreador nao tem campo
# de acessorio e o `acessorios` do espelho esta vazio nos 1998 registros. Entao
# a regra depende do TERMO, e por placa: num termo de 10 placas so as que
# recebem leitor viram RB.
checar("ST340 sem RFID continua ST340", "Suntech ST340",
       equipamentos.modelo_efetivo("Suntech ST340", False))
checar("ST340 com RFID vira ST340RB", "Suntech ST340RB",
       equipamentos.modelo_efetivo("Suntech ST340", True))
checar("a regra nao depende da caixa", "Suntech ST340RB",
       equipamentos.modelo_efetivo("suntech st340", True))
checar("RFID nao mexe em outro modelo", "Suntech ST310",
       equipamentos.modelo_efetivo("Suntech ST310", True))
checar("XT40 Portatil com RFID nao vira RB", "XT40 Portatil",
       equipamentos.modelo_efetivo("XT40 Portatil", True))
checar("modelo desconhecido vira marcador", "modelo nao localizado",
       equipamentos.modelo_efetivo(None, True))

checar("LEITOR RFID no item liga a regra", True,
       equipamentos.tem_leitor_rfid([{"descricao": "LEITOR RFID"}]))
checar("LEITOR I-BUTTON NAO liga a regra", False,
       equipamentos.tem_leitor_rfid([{"descricao": "LEITOR I-BUTTON"}]))
checar("acha o RFID no meio da lista", True,
       equipamentos.tem_leitor_rfid([{"descricao": "RASTREADOR"},
                                     {"descricao": "leitor rfid"}]))
checar("sem material nenhum e False", False, equipamentos.tem_leitor_rfid([]))

# ── 5. a conferência de termo ────────────────────────────────────────────────
checar("recipiente do 8820 tem a descricao do 8820", "TERMO 8820",
       equipamentos.descricao_da_placa("OOM4131-UPGRADE"))
# 🚨 este é o caso que a conferência existe para pegar: recipiente de OUTRO termo
checar("recipiente de outro termo e reconhecido como outro", "TERMO 8824",
       equipamentos.descricao_da_placa("GCW9H80-UPGRADE"))
checar("recipiente inexistente devolve None, nao string vazia", None,
       equipamentos.descricao_da_placa("NAOEXISTE-UPGRADE"))
checar("None e diferente de nao confere", True,
       equipamentos.descricao_da_placa("NAOEXISTE-UPGRADE") is None)

checar("_norm_desc tolera espaco e caixa", "TERMO 8820", os_router._norm_desc("  termo   8820 "))

# ── 8. a WESO SUBSTITUI o item do vinculo (14/08) ───────────────────────────
# 🚨 MUDANCA DE MAIOR ALCANCE ATE AQUI: vale para os 9 perfis. Ate 14/08, se o
# termo ja tivesse listado um rastreador, o material da WESO era DESCARTADO
# para nao duplicar -- e a OS saia com o que o vendedor escreveu no contrato.
# O vinculo distingue DOIS modelos ("RASTREADOR" -> ST310U, "RASTREADOR 4G" ->
# XT40); a WESO tem 20+ em uso. Decisao do usuario: a WESO manda, porque o
# veiculo ja existe la quando a OS e gerada -- inclusive em Cliente novo.
print("\n[8] a WESO substitui o item do vinculo")

_do_vinculo = {"descricao": "EQUIPAMENTO RASTREADOR TELEMETRIA AVANCADA 4G",
               "harmonit_id": 338502, "quantidade": 1, "valor_unitario": 1100.0,
               "comodato": True, "cobrar": False}
_acessorio = {"descricao": "BLOQUEIO VEICULAR", "harmonit_id": 45689,
              "quantidade": 1, "valor_unitario": 50.0,
              "comodato": True, "cobrar": False}
_da_weso = {"descricao": "ST310U", "harmonit_id": 20314, "quantidade": 1,
            "valor_unitario": 0.0, "comodato": True, "cobrar": False}

_saida = os_router._substituir_rastreador([_do_vinculo, _acessorio], _da_weso)
checar("o rastreador do vinculo sai", False,
       any("TELEMETRIA" in m["descricao"] for m in _saida))
checar("o da WESO entra", True, any(m["descricao"] == "ST310U" for m in _saida))
checar("o acessorio NAO e tocado", True,
       any(m["descricao"] == "BLOQUEIO VEICULAR" for m in _saida))
checar("nao duplica: 2 itens entram, 2 saem", 2, len(_saida))

# ⚠️ SEM EQUIPAMENTO RESOLVIDO NAO MEXE. Apagar o item do contrato e nao pôr
# nada no lugar seria pior que a imprecisao que estamos corrigindo.
_intacto = os_router._substituir_rastreador([_do_vinculo, _acessorio], None)
checar("sem equipamento da WESO, a lista fica como estava", 2, len(_intacto))
checar("e o item do contrato continua la", True,
       any("TELEMETRIA" in m["descricao"] for m in _intacto))

checar("acessorio nao e confundido com rastreador", False,
       os_router._eh_rastreador(_acessorio))
checar("o equipamento e reconhecido", True, os_router._eh_rastreador(_do_vinculo))

# Os 9 perfis leem a WESO -- nenhum ficou de fora da decisao.
_sem_origem = [k for k, p in templates_config.PERFIS.items()
               if not p.get("modelo_origem")]
checar("todos os perfis leem a WESO para o modelo", [], _sem_origem)

print()
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)

