# -*- coding: utf-8 -*-
"""Mede o POST /OrdemServico/AgendarTecnico — FRENTE 6 do plano. NAO LIGA NADA.

🔵 Decisao 7 dele (19/10): o MoviZap e o dono do agendamento, e a escrita no
Harmonit e 2o passo, **testada antes na Velasco**. Este script e esse teste.

🚨 A ROTA NUNCA FOI CHAMADA: zero em 340.840 chamadas registradas (medido em
19/10). E rota crua, e ninguem sabe o que ela faz -- por isso o script mede em
vez de supor, e por isso roda SO na OS 16991, a sandbox da Pastelaria Velasco
(cliente 998063), que ja esta `Finalizado`.

🚨 ELE NAO MUDA NADA NO MOVIZAP, nao mexe em config e nao liga interruptor
nenhum. Le a OS antes, chama a rota, le a OS depois e imprime a diferenca.
Ligar a escrita e decisao dele, DEPOIS do relatorio.

Uso:  ./venv/bin/python medir_agendar_tecnico.py           (so le, nao escreve)
      ./venv/bin/python medir_agendar_tecnico.py --chamar  (chama a rota)
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/home/claude/fpsl_weso")

from fpsl_weso.harmonit_client import (  # noqa: E402
    harmonit_get, harmonit_post, start_harmonit_client, stop_harmonit_client)

OS_NUMERO = 16991          # a sandbox da Velasco, ja Finalizado
CLIENTE_ID = 998063


def _dados(r):
    return r.get("data") if isinstance(r, dict) and "data" in r else r


def _tecnicos(os_dict: dict) -> list:
    """🚨 A CHAVE E `tecnico`, no SINGULAR, e e uma LISTA.

    Medido em 21/10: o retorno de `ObterOrdemServicoPorNumero` nao tem
    `ordemServicoxTecnicos` nem `tecnicos` -- chutar o nome da chave fez a
    primeira versao deste script relatar "sem tecnico vinculado" numa OS que
    tem um. Achado por rodar, nao por ler o swagger.
    """
    return os_dict.get("tecnico") or []


def _retrato(os_dict: dict) -> dict:
    """So o que interessa para a comparacao -- despejar a OS inteira esconde
    a diferenca no meio de duzentas chaves."""
    return {
        "id": os_dict.get("id"),
        "numero": os_dict.get("numero"),
        "situacaoId": os_dict.get("situacaoId"),
        "statusStr": os_dict.get("statusStr"),
        "dataPrevisao": os_dict.get("dataPrevisao"),
        "tecnicos": [
            {
                "ordemServicoxTecnicoId": t.get("id"),
                "nomeTecnico": t.get("nomeTecnico"),
                "agendamentoId": t.get("agendamentoId"),
                "agendado": t.get("agendado"),
                "agendamentoOS": t.get("agendamentoOS"),
            }
            for t in _tecnicos(os_dict) if isinstance(t, dict)
        ],
        "qtd_tecnicos": len(_tecnicos(os_dict)),
    }


async def ler() -> dict:
    r = await harmonit_get("/OrdemServico/ObterOrdemServicoPorNumero",
                           params={"numeroOs": OS_NUMERO})
    d = _dados(r)
    if isinstance(d, list):
        d = d[0] if d else {}
    return d or {}


async def main(chamar: bool):
    await start_harmonit_client()
    try:
        antes = await ler()
        if not antes:
            print("NAO LI A OS 16991 -- o resto do teste nao vale nada. Parei.")
            return
        print("== ANTES ==")
        print(json.dumps(_retrato(antes), ensure_ascii=False, indent=2))

        if not chamar:
            print("\n(so leitura: rode com --chamar para medir a escrita)")
            return

        tecnicos = _tecnicos(antes)
        if not tecnicos:
            print("\nA OS 16991 NAO TEM TECNICO VINCULADO -- o DTO pede "
                  "`ordemServicoxTecnicoId`, e sem ele nao da para chamar sem "
                  "inventar dado. Parei, e isto e um achado do teste.")
            return

        vinculo = tecnicos[0]
        ja = vinculo.get("agendamentoOS") or {}
        # 🚨 USA O AGENDAMENTO QUE JA EXISTE (`id` real, nao 0): a OS 16991 ja
        # nasceu com um compromisso (`agendamentoId` 930447, `agendado:false`),
        # e mandar `id: 0` poderia criar um SEGUNDO na mesma OS. Reagendar o
        # que existe e o teste mais barato de desfazer.
        inicio = (datetime.now() + timedelta(days=2)).replace(
            hour=9, minute=0, second=0, microsecond=0)
        corpo = {
            "id": vinculo.get("agendamentoId") or 0,
            "clienteId": CLIENTE_ID,
            "ordemServicoId": antes.get("id"),
            "ordemServicoxTecnicoId": vinculo.get("id"),
            "inicioCompromisso": inicio.isoformat(),
            "fimCompromisso": (inicio + timedelta(hours=2)).isoformat(),
        }
        print("\n== JANELA ORIGINAL (para desfazer, se ele quiser) ==")
        print(json.dumps({"start": ja.get("start"), "end": ja.get("end")},
                         ensure_ascii=False))
        print("\n== CORPO ENVIADO ==")
        print(json.dumps(corpo, ensure_ascii=False, indent=2))

        try:
            resposta = await harmonit_post("/OrdemServico/AgendarTecnico", corpo)
            print("\n== RESPOSTA ==")
            print(json.dumps(resposta, ensure_ascii=False, indent=2)[:2000])
        except Exception as e:  # a rota e crua: qualquer coisa pode vir
            print(f"\n== A ROTA RECUSOU ==\n{type(e).__name__}: {e}")

        depois = await ler()
        print("\n== DEPOIS ==")
        print(json.dumps(_retrato(depois), ensure_ascii=False, indent=2))

        # 🚨 A prova e RELER O ESTADO, nunca o retorno da chamada.
        mudou = _retrato(antes) != _retrato(depois)
        print(f"\n== O COMPROMISSO APARECEU NA OS AO RELER? {'SIM' if mudou else 'NAO'} ==")
        if not mudou:
            print("A rota pode ter respondido ok e nao ter gravado nada "
                  "visivel por esta leitura -- e exatamente o que o relatorio "
                  "precisa dizer antes de alguem ligar a escrita.")
    finally:
        await stop_harmonit_client()


if __name__ == "__main__":
    asyncio.run(main("--chamar" in sys.argv))
