"""Motor de eventos da Gestão de Contratos (`CTR_1.1`). 2026-10-13.

Entra termo, sai a situação de cada placa. **Sem I/O**: não toca banco, Harmonit,
WESO nem disco. É de propósito -- é o que permite travar as regras dele contra
termos reais numa suíte que roda em qualquer máquina.

🚨 EVENTO IMUTÁVEL, SITUAÇÃO DERIVADA. O termo não "atualiza" a placa: ele
registra um evento, e a situação é o resultado de ler os eventos em ordem. É
isso que faz a pergunta "por que esta placa está ativa?" ter um documento como
resposta. Foi copiar estado em vez de referenciar evento que quebrou o
`HBG 8442` (ver docs/fpsl/31_Gestao_Contratos.md).

🚨 A ORDEM É O NÚMERO DO TERMO, NUNCA A DATA. Medido na auditoria de 13/10: a
data do Harmonit vem `01-01-2000` quando não existe, e o contrato 5029 da JLM
está datado de 2026 tendo sido rescindido pelo 6026, que é anterior. Ordenar
por data inverte a história de clientes reais.

🚨 DUAS PASSADAS, PORQUE "VALE O ASSINADO" TEM EXCEÇÃO. Regra dele (13/10):
*"vale o assinado, e termo não assinado não conta -- a menos que falte em ambos
os lados"*. Então:

    passada 1   só o que foi assinado decide;
    passada 2   para a placa que NENHUM termo assinado menciona, o termo sem
                assinatura cobre a lacuna -- e a placa sai marcada
                `base="nao assinado"`, nunca silenciosamente.

Uma passada só não expressa isso: se o não assinado entrasse junto, a rescisão
cancelada da JLM (distrato 6026) apagaria 5 placas que o contrato 5029
assinado sustenta; se ficasse de fora, 229 placas medidas em uso ficariam sem
nenhuma base.
"""
import re
import unicodedata
from datetime import date, timedelta

# Situações de CONTRATO. O que é "aguardando instalação" NÃO mora aqui: isso é
# comparação com a WESO, não estado do contrato, e misturar os dois foi o que
# fez a auditoria contar a mesma placa duas vezes.
ATIVA = "ATIVA"
EM_AVISO_PREVIO = "EM_AVISO_PREVIO"
RESCINDIDA = "RESCINDIDA"
SUBSTITUIDA = "SUBSTITUIDA"

# Ações possíveis de um evento. A substituição NÃO é uma ação: ela chega como um
# `SAI` e um `ENTRA` no mesmo termo, que é exactamente como o documento a
# escreve (duas colunas, "veículos que sairão" e "que entrarão").
ENTRA = "ENTRA"
SAI = "SAI"
RESCINDE = "RESCINDE"
UPGRADE = "UPGRADE"

# 🆕 C7 (14/10): ANULA desfaz um evento ANTERIOR, apontando para o `id` dele em
# `corrige`. Nasceu da releitura dos PDFs assinados: a carga de 13/10 gravou a
# lista de placas do **Harmonit** (o PDF é editado depois de assinado), e onde
# o documento assinado não traz aquela placa, o evento que a fez entrar está
# errado.
#
# 🚨 POR QUE NÃO DAVA PARA USAR `SAI` NEM `RESCINDE`: os dois MENTIRIAM. A
# placa ficaria SUBSTITUIDA ou RESCINDIDA, e a verdade é outra -- ela **nunca
# esteve no contrato**. Dizer "saiu" inventa um fato (uma saída que não houve) e
# ainda muda o que a futura cobrança entende.
#
# 🚨 E NÃO DAVA PARA CORRIGIR O EVENTO VELHO: `contrato_evento` é imutável, e é
# essa imutabilidade que faz "por que esta placa está ativa?" ter documento como
# resposta. Corrigir é ACRESCENTAR -- o evento errado continua lá, visível,
# apontado por quem o anulou, com autoria e motivo.
ANULA = "ANULA"
ACOES = (ENTRA, SAI, RESCINDE, UPGRADE, ANULA)

# Fonte do evento: de qual versão do termo ele foi lido.
ASSINADO = "assinado"
HARMONIT = "harmonit"

# 🆕 D (14/10): a prova não é um documento, é o USO. Regra dele:
# *"placas sem assinatura mas placa ativa, placa vence, pois se existe na weso
# foi feita, o erro é não ter assinatura"* e *"pode ser que N placas foram
# rescindidas mas nao assinadas, se tiverem fora da Weso, é recisão mesmo"*.
#
# 🚨 EVENTO COM `fonte="weso"` VALE MESMO EM TERMO SEM ASSINATURA. É a única
# fonte com esse poder, e tem motivo: ela não afirma o que o cliente assinou,
# afirma o que **está instalado**. A rescisão não assinada de uma placa que já
# saiu da WESO não é dúvida -- é o cadastro atrasado em relação ao fato.
#
# ⚠️ QUEM GERA ESTE EVENTO É UMA ROTINA, NUNCA O MOTOR. O motor é sem I/O (é o
# que permite travar as regras dele em teste, em qualquer máquina); a consulta à
# WESO mora em `contratos_aderencia.py`, que insere o evento com a data do cache
# no `obs`. Deixar o motor olhar a WESO transformaria a situação da placa em algo
# que muda sem evento nenhum -- e ninguém saberia explicar por quê.
WESO = "weso"

AVISO_PREVIO_DIAS = 90

# Placa que o termo deixou em branco. Termo assinado com "A DEFINIR" na coluna
# de entrada não ativa nada -- a placa real é preenchida depois, no Harmonit, e
# entra pela regra da troca. Medido em Eco System 3085, Tec & Forte 2669 e
# Sanex 8008.
_SEM_PLACA = {"", "ADEFINIR", "ADEFNIR", "ADEFINIRADEFINIR"}


def chave(identificador) -> str:
    """Identificador comparável entre as três fontes.

    🚨 MESMA PLACA SÓ POR EQUIVALÊNCIA MERCOSUL. `ABC1234` e `ABC1C34` são a
    mesma placa (o 5º caractere 0-9 corresponde a A-J). A regra anterior, de
    "1 caractere diferente", foi ABANDONADA em 13/10: ela juntava placas reais
    da mesma frota (`DTX7581` com `DTX7583`, `DAT0267` com `DAT0262`) e inflou
    as correções de 88 para 711.
    """
    t = unicodedata.normalize("NFKD", str(identificador or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).upper()
    t = re.sub(r"^\s*CH(ASSI|SS)\s*:?\s*", "", t)
    t = re.sub(r"^\(RD\)\s*", "", t)
    t = re.sub(r"[^A-Z0-9]", "", t)
    if re.fullmatch(r"[A-Z]{3}\d[A-J0-9]\d{2}", t) and t[4].isdigit():
        return t[:4] + "ABCDEFGHIJ"[int(t[4])] + t[5:]
    return t


def _ordem(termo) -> tuple:
    n = termo.get("numero")
    try:
        return (0, int(n), "")
    except (TypeError, ValueError):
        return (1, 0, str(n or ""))


def _vale_assinado(termo, evento) -> bool:
    """Este evento conta na passada dos assinados?

    🚨 A REGRA DA TROCA, DELE, EM 13/10: *"se o termo X está assinado e o
    cliente pediu a troca e está registrado no Harmonit, está certo"*. O caso
    que a produziu é a Maxi Confort 8872: o contrato assinado traz `DVS 2992`,
    e o PDF do Harmonit do MESMO termo acrescenta `FAC 5H30` com a anotação
    *"Cliente Fernanda Rodrigues pediu alteração da placa"* -- sem tirar a
    antiga. A placa nova é coberta pelo termo assinado; a antiga sai.

    🚨 A OUTRA PORTA É O `a_definir`, e é regra dele também: termo assinado com
    **"a definir"** na coluna de entrada + placa preenchida depois no Harmonit
    = assinado. O cliente assinou o veículo em branco de propósito, porque na
    hora da assinatura ele ainda não existia. Medido em Eco System 3085
    (`SIF0C19`), Tec & Forte 2669 e Sanex 8008.

    ⚠️ "A DEFINIR" SE CASA PELA EXPRESSÃO EXATA. A primeira versão desta regra
    casava qualquer "a definição" das cláusulas e deu 22 placas por assinadas
    sem estarem -- inclusive a `FAC 5H30` da Maxi Confort, que é troca, não
    "a definir". Quem decide o flag é a extração, lendo a TABELA DE VEÍCULOS.

    ⚠️ SEM `troca_registrada` NEM `a_definir`, EVENTO LIDO NO HARMONIT NÃO VALE
    COMO ASSINADO, mesmo que o termo tenha assinatura. Era assim que 256 termos
    "ganhavam" placas depois de assinados.
    """
    # 🚨 `weso` DECIDE INDEPENDENTE DE ASSINATURA, e é a exceção que ele abriu
    # em 14/10: a prova aqui é o uso, não o documento. Vem antes da checagem de
    # `assinado` de propósito -- o caso que a produziu é justamente a rescisão
    # SEM assinatura de placa que já saiu da WESO (549 placas medidas).
    if evento.get("fonte") == WESO:
        return True
    if not termo.get("assinado"):
        return False
    if evento.get("fonte", ASSINADO) == ASSINADO:
        return True
    return bool(termo.get("troca_registrada") or termo.get("a_definir"))


def _aplicar(termo, evento, placa, estado, base, hoje):
    acao = evento["acao"]
    if acao == ANULA:
        # ⚠️ ANULA não aplica nada: ele só diz que OUTRO evento não vale, e
        # quem trata isso é `situacao_das_placas`, antes das passadas (o evento
        # anulado pode estar em termo diferente deste). Chegar aqui significa
        # que o filtro não rodou -- então é no-op, e não exceção: um evento de
        # correção não pode derrubar a ficha inteira do cliente.
        return
    k = placa
    atual = estado.get(k)
    comum = dict(placa=evento.get("placa") or k, base=base,
                 termo_vigente=termo.get("numero"), empresa=termo.get("empresa"),
                 recursos=evento.get("recursos") or (atual or {}).get("recursos"),
                 valor_mensal=evento.get("valor_mensal") or (atual or {}).get("valor_mensal"))

    if acao == UPGRADE:
        # 🚨 UPGRADE NÃO MUDA PLACA -- regra dele: *"upgrade não necessariamente
        # são aditivos, pois podem refletir a mesma placa"*. Ele só troca
        # equipamento ou plano. Sem esta regra, 117 termos de upgrade ativavam
        # placa que não estava ativa.
        if atual is None:
            return
        novo = dict(atual)
        novo["recursos"] = comum["recursos"]
        if atual["situacao"] != ATIVA:
            novo["obs"] = _mais(atual.get("obs"),
                                f"upgrade (termo {termo.get('numero')}) em placa que nao estava ativa")
        estado[k] = novo
        return

    if acao == ENTRA:
        # ⚠️ A OBSERVAÇÃO DA TROCA É SÓ DE QUEM VEIO PELA TROCA. A primeira
        # versão marcava TODAS as placas do termo, inclusive as que estavam no
        # documento assinado -- a ficha então dizia que uma placa assinada
        # "veio pela troca", o que é falso sobre a origem dela. Quem define é a
        # fonte do EVENTO, não o termo.
        veio_da_troca = (evento.get("fonte", ASSINADO) == HARMONIT and termo.get("troca_registrada"))
        estado[k] = dict(comum, situacao=ATIVA, desde=termo.get("assinado_em") or termo.get("data"),
                         aviso_ate=None,
                         obs=_mais((atual or {}).get("obs"),
                                   f"entrou pela troca registrada no Harmonit (termo {termo.get('numero')})"
                                   if veio_da_troca else None))
        return

    if acao == SAI:
        # Substituição não tem aviso prévio: o equipamento passa para o veículo
        # que entrou no mesmo termo.
        estado[k] = dict(comum, situacao=SUBSTITUIDA, desde=(atual or {}).get("desde"),
                         aviso_ate=None, obs=_mais((atual or {}).get("obs"), evento.get("obs")))
        return

    if acao == RESCINDE:
        assinado_em = termo.get("assinado_em")
        ate = None
        if assinado_em:
            try:
                ate = date.fromisoformat(assinado_em) + timedelta(days=AVISO_PREVIO_DIAS)
            except ValueError:
                ate = None
        dentro = bool(ate and hoje <= ate)
        estado[k] = dict(comum, situacao=EM_AVISO_PREVIO if dentro else RESCINDIDA,
                         desde=(atual or {}).get("desde"),
                         aviso_ate=ate.isoformat() if ate else None,
                         obs=(atual or {}).get("obs"))
        return

    raise ValueError(f"acao desconhecida: {acao!r} (validas: {ACOES})")


def _mais(obs, nova):
    if not nova:
        return obs
    return f"{obs}; {nova}" if obs else nova


def situacao_das_placas(termos, hoje=None) -> dict:
    """Situação de cada placa do cliente, derivada dos termos.

    `termos`: lista de dicts com `numero`, `empresa`, `tipo`, `assinado` (bool),
    `assinado_em` (ISO), `troca_registrada` (texto ou None) e `eventos`, cada
    evento com `acao`, `placa`, `fonte` e, opcionalmente, `recursos` e
    `valor_mensal`.

    Devolve `{chave: {placa, situacao, base, termo_vigente, desde, aviso_ate,
    recursos, valor_mensal, obs}}`.
    """
    hoje = hoje or date.today()
    ordenados = sorted(termos, key=_ordem)

    # 🆕 C7: quem foi ANULADO sai das DUAS passadas, e isto é feito ANTES de
    # qualquer aplicação -- o evento de correção pode estar num termo que vem
    # depois na ordem, ou até em outro termo do mesmo cliente. Varrer primeiro é
    # o que torna a anulação independente da ordem de leitura.
    anulados = {ev["corrige"] for termo in ordenados
                for ev in (termo.get("eventos") or []) if ev.get("corrige")}

    def _vale(ev) -> bool:
        if ev.get("acao") == ANULA:
            return False                      # ele corrige, não aplica
        return not (ev.get("id") is not None and ev["id"] in anulados)

    estado: dict = {}
    for termo in ordenados:
        for ev in termo.get("eventos") or []:
            k = chave(ev.get("placa"))
            if k in _SEM_PLACA or not _vale(ev):
                continue
            if _vale_assinado(termo, ev):
                base = ASSINADO
                if ev.get("fonte") == WESO:
                    # A base DIZ que o lastro é o uso, não a assinatura: quem
                    # lê a ficha precisa saber que esta placa fechou porque
                    # saiu da WESO, e não porque alguém assinou.
                    base = "rescisao confirmada pelo uso (fora da WESO)"
                elif ev.get("fonte", ASSINADO) == HARMONIT:
                    base = ("assinado (troca registrada no Harmonit)"
                            if termo.get("troca_registrada")
                            else "assinado com 'a definir'; placa preenchida no Harmonit")
                _aplicar(termo, ev, k, estado, base, hoje)

    # Passada 2: só para a placa que nenhum termo ASSINADO mencionou.
    tocadas_por_assinado = set(estado)
    sem_assinatura: dict = {}
    for termo in ordenados:
        for ev in termo.get("eventos") or []:
            k = chave(ev.get("placa"))
            if k in _SEM_PLACA or k in tocadas_por_assinado or not _vale(ev):
                continue
            _aplicar(termo, ev, k, sem_assinatura, "nao assinado", hoje)
    for k, v in sem_assinatura.items():
        v["obs"] = _mais(v.get("obs"), "nenhum termo assinado trata desta placa")
        estado[k] = v
    return estado


def ativas(situacoes) -> list:
    """As placas que o contrato sustenta hoje. Em aviso prévio AINDA conta.

    🚨 Regra dele (13/10): rescisão assinada há até 90 dias ainda pode estar em
    uso -- é o aviso prévio que o próprio termo prevê. Dos 152 casos medidos de
    "rescindida e ainda na WESO", 97 estavam dentro do prazo e 52 fora.

    🚨 DEVOLVE A PLACA COMO ESTÁ NO TERMO, NUNCA A CHAVE. A chave é interna: ela
    converte para Mercosul para comparar, e `BUW8732` vira `BUW8H32` -- uma
    placa que não existe em lugar nenhum. Esta função já devolveu chave, e o
    teste pegou; se tivesse chegado à tela, o operador leria placa inventada,
    que é a família do `RFD 2447`.
    """
    return sorted(v.get("placa") or k for k, v in situacoes.items()
                  if v["situacao"] in (ATIVA, EM_AVISO_PREVIO))
