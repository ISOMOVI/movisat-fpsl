# -*- coding: utf-8 -*-
"""N2.3 — o compromisso passa a dizer QUEM e QUANDO, nas três telas.

🔵 ELE, 23/11: *"os agendamentos feitos por aqui no Movizap, continuam não
sendo escritos nas OS, precisamos de um definitivo para isso!"*

🚨 O QUE A MEDIÇÃO DE 23/11 (N2.1, `medir_agendamento_cru.py`) PROVOU: a
escrita está COMPLETA. Lido o `agendamentoOS` cru do ERP:

    OS 17139  MoviZap mandou 23/11 11:00 -> ERP: start 11:00, end 13:00
    OS 17143  MoviZap mandou 23/11 16:00 -> ERP: start 16:00, end 18:00

...com `usuarioId 14262` (o Franck) e `nomeTecnico = 'Franck'`. A data bate, o
`end` é o `+2h` que a ponte calcula quando o fim vem nulo, e o vínculo existe.

🚨 ENTÃO O DEFEITO É DE LEITURA, E ERA DUPLO -- os dois nesta função:
  1. **O nome:** `_tecnicos_da_os` procurava `nome` e `usuarioNome`. O ERP
     chama o campo **`nomeTecnico`**. Nenhuma das duas chaves existe no dado,
     então o resumo saía `nome: null` SEMPRE -- e a tela caía no `usuário
     14262`. Medido no cache: `nomeTecnico='Franck'`, `nome=None`.
  2. **A janela:** o `agendamentoOS` guardado tem `start` e `end`, e o resumo
     os DESCARTAVA. A tela mostrava "compromisso 969544" e nenhuma data.

⚠️ QUEM OLHAVA ESSA TELA VIA "usuário 14262 — compromisso 969544": nenhum nome
e nenhuma data. Concluir *"não foi escrito"* era a leitura certa do que a tela
mostrava. **Tela que mente é defeito** (`M12`), e a mentira aqui era por
omissão.

🚨 A FORMATAÇÃO NASCE AQUI, NÃO NA TELA, e por um motivo medido: o mesmo bloco
é desenhado em TRÊS telas (`DialogoDeChamado`, `PainelOperacao`,
`PainelServicoDosTecnicos`). Formatar em três lugares é o gêmeo nascendo pela
terceira vez -- a mesma razão do `operacoes_retirada`.

⚠️ O DADO CRU VAI JUNTO (`inicio`/`fim`, como o ERP os escreve): a `janela` é
conforto de leitura, e quem precisar comparar com o que mandamos tem de ter o
original. Dado traduzido sem o original não se audita.
"""
import pathlib

ALVOS = {}


def abrir(rel):
    p = pathlib.Path(rel)
    bruto = p.read_bytes()
    ALVOS[rel] = {"p": p, "crlf": b"\r\n" in bruto,
                  "t": bruto.decode("utf-8").replace("\r\n", "\n")}
    return rel


def troca(rel, velho, novo, rotulo):
    d = ALVOS[rel]
    assert velho in d["t"], "NAO ACHOU (%s)" % rotulo
    assert d["t"].count(velho) == 1, "AMBIGUO %dx (%s)" % (
        d["t"].count(velho), rotulo)
    d["t"] = d["t"].replace(velho, novo, 1)
    print("  ok:", rotulo)


PT = abrir("fpsl_weso/routers/os_ponte.py")

# ---------------------------------------------------------------- a formatação
troca(PT,
      '''def _tecnicos_da_os(tecnicos_json: str | None) -> list[dict]:''',
      '''def _janela_legivel(inicio: str | None, fim: str | None) -> str | None:
    """"23/11/2026 16:00 às 18:00" -- a janela do compromisso, para ler.

    🚨 UMA VEZ, AQUI, e não nas três telas que desenham este bloco
    (`DialogoDeChamado`, `PainelOperacao`, `PainelServicoDosTecnicos`).

    ⚠️ O FORMATO É O DO ERP: `dd/MM/yyyy HH:mm:ss`, com barra e sem fuso --
    medido em 23/11 lendo o `agendamentoOS` cru. Não se adivinha ISO aqui.

    ⚠️ E SE NÃO DER PARA LER, DEVOLVE O CRU em vez de `None`: data que o ERP
    mandou e a tela não mostrou é pior que data feia. Quem muda o formato lá é
    o Harmonit, e esconder a mudança faria o defeito voltar calado.
    """
    if not inicio:
        return None
    def _partes(txt):
        pedacos = str(txt).strip().split(" ")
        dia = pedacos[0] if pedacos else ""
        hora = pedacos[1][:5] if len(pedacos) > 1 else ""
        return dia, hora
    d1, h1 = _partes(inicio)
    if not d1 or not h1:
        return " a ".join(x for x in (inicio, fim) if x)
    if not fim:
        return f"{d1} {h1}"
    d2, h2 = _partes(fim)
    if not d2 or not h2:
        return f"{d1} {h1}"
    # Mesmo dia: a data não se repete -- "16:00 às 18:00" é o que a pessoa lê.
    if d2 == d1:
        return f"{d1} {h1} às {h2}"
    return f"{d1} {h1} às {d2} {h2}"


def _tecnicos_da_os(tecnicos_json: str | None) -> list[dict]:''',
      "1. _janela_legivel, uma vez e no backend")

# ---------------------------------------------------------------- o nome
troca(PT,
      '''        atual = por_usuario.setdefault(uid, {
            "usuario_id": uid,
            "nome": t.get("nome") or t.get("usuarioNome") or None,
            "agendamento_id": None,
            "vinculos": 0,
        })
        atual["vinculos"] += 1
        # ⚠️ O vínculo COM agendamento ganha: é o que a tela quer mostrar, e um
        # técnico com dois vínculos tem o compromisso em apenas um deles.
        if t.get("agendamentoId") and not atual["agendamento_id"]:
            atual["agendamento_id"] = t.get("agendamentoId")''',
      '''        atual = por_usuario.setdefault(uid, {
            "usuario_id": uid,
            # 🚨 `nomeTecnico` PRIMEIRO, e isto é um conserto de 23/11: a
            # versão anterior procurava `nome` e `usuarioNome`, e NENHUMA DAS
            # DUAS existe no dado do Harmonit -- medido no cache da OS 17143,
            # que tem `nomeTecnico='Franck'` e `nome=None`. O resumo saía com
            # o nome nulo SEMPRE, e as três telas caíam no "usuário 14262".
            # ⚠️ As outras duas chaves ficam como reserva: custam nada e
            # cobrem o dia em que o ERP renomear o campo.
            "nome": (t.get("nomeTecnico") or t.get("nome")
                     or t.get("usuarioNome") or None),
            "agendamento_id": None,
            # 🚨 A JANELA, que faltava: `start` e `end` estão no
            # `agendamentoOS` guardado e eram DESCARTADOS aqui. Sem eles a
            # tela mostrava "compromisso 969544" e nenhuma data -- e quem
            # olhava concluía, com razão, que o agendamento não tinha sido
            # escrito. O cru vai junto para poder ser auditado contra o que
            # mandamos.
            "inicio": None,
            "fim": None,
            "janela": None,
            "vinculos": 0,
        })
        atual["vinculos"] += 1
        # ⚠️ O vínculo COM agendamento ganha: é o que a tela quer mostrar, e um
        # técnico com dois vínculos tem o compromisso em apenas um deles.
        if t.get("agendamentoId") and not atual["agendamento_id"]:
            atual["agendamento_id"] = t.get("agendamentoId")
            ag = t.get("agendamentoOS")
            if isinstance(ag, dict):
                atual["inicio"] = ag.get("start") or None
                atual["fim"] = ag.get("end") or None
                atual["janela"] = _janela_legivel(atual["inicio"],
                                                  atual["fim"])''',
      "2. o nome certo e a janela, no resumo")


for rel, d in ALVOS.items():
    saida = d["t"].replace("\n", "\r\n") if d["crlf"] else d["t"]
    d["p"].write_bytes(saida.encode("utf-8"))
    print("gravado:", rel, len(saida), "bytes")
