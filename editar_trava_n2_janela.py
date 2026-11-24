# -*- coding: utf-8 -*-
"""N2.3, a trava: o resumo do compromisso diz QUEM e QUANDO.

🚨 O defeito era de LEITURA e passava verde: o dado estava inteiro no cache
(`nomeTecnico='Franck'`, `agendamentoOS.start`/`end`) e o resumo devolvia
`nome: None` e nenhuma data, porque procurava chaves que não existem.
"""
import pathlib

q = pathlib.Path("tests/teste_ponte_movizap.py")
bq = q.read_bytes()
CRLF = b"\r\n" in bq
u = bq.decode("utf-8").replace("\r\n", "\n")

TRAVA = '''

class TestOResumoDoCompromissoDizQuemEQuando:
    """🔵 ELE, 23/11: *"os agendamentos feitos por aqui no Movizap, continuam
    nao sendo escritos nas OS, precisamos de um definitivo para isso!"*

    🚨 A MEDICAO CONTRADISSE O SINTOMA, e por isso estas travas existem. Lido o
    `agendamentoOS` CRU do ERP em 23/11 (`medir_agendamento_cru.py`):

        OS 17139  MoviZap mandou 23/11 11:00 -> ERP: start 11:00, end 13:00
        OS 17143  MoviZap mandou 23/11 16:00 -> ERP: start 16:00, end 18:00

    ...com `usuarioId 14262` e `nomeTecnico='Franck'`. A escrita estava
    COMPLETA. O defeito era a LEITURA, e era duplo, os dois no
    `_tecnicos_da_os`: procurava `nome`/`usuarioNome` (nenhuma das duas existe
    no dado) e DESCARTAVA `start`/`end`.

    ⚠️ A tela mostrava *"usuario 14262 - compromisso 969544"*: sem nome e sem
    data. Concluir *"nao foi escrito"* era a leitura certa do que a tela
    mostrava -- tela que mente por omissao (`M12`).
    """

    # O dado como o Harmonit o devolve, com as chaves DELE. ⚠️ Copiado da
    # medicao de 23/11, nao inventado: e por isso que a trava pega o defeito.
    LINHA = {
        "id": 1170039, "usuarioId": 14262, "nomeTecnico": "Franck",
        "email": "zz@exemplo.com", "agendamentoId": 969544,
        "agendamentoOS": {
            "id": 969544, "start": "23/11/2026 16:00:00",
            "end": "23/11/2026 18:00:00", "statusCompromisso": 1,
            "ordemServicoId": 945119, "tecnicoId": 14262,
        },
    }

    def test_o_nome_vem_de_nomeTecnico(self):
        """🚨 A CHAVE E `nomeTecnico`. Medido no cache da OS 17143: `nome` e
        `usuarioNome` sao None ali, e eram as duas unicas que o resumo lia."""
        assert "nome" not in self.LINHA and "usuarioNome" not in self.LINHA, (
            "a fixture deixou de refletir o dado do ERP")
        r = os_ponte._tecnicos_da_os(json.dumps([self.LINHA]))
        assert r[0]["nome"] == "Franck", r

    def test_a_janela_do_compromisso_sai_no_resumo(self):
        """🚨 `start` e `end` existiam no dado e eram descartados -- e a data e
        exatamente o que ele olha na tela para saber se foi escrito."""
        r = os_ponte._tecnicos_da_os(json.dumps([self.LINHA]))[0]
        assert r["inicio"] == "23/11/2026 16:00:00", r
        assert r["fim"] == "23/11/2026 18:00:00", r
        # Mesmo dia: a data nao se repete.
        assert r["janela"] == "23/11/2026 16:00 às 18:00", r

    def test_o_CRU_vai_junto_do_formatado(self):
        """⚠️ Dado traduzido sem o original nao se audita: a `janela` e
        conforto de leitura, e quem comparar com o que mandamos precisa do
        texto como o ERP o escreveu."""
        r = os_ponte._tecnicos_da_os(json.dumps([self.LINHA]))[0]
        assert r["inicio"] and r["fim"] and r["janela"]
        assert r["inicio"] != r["janela"]

    def test_compromisso_sem_janela_nao_inventa_data(self):
        """⚠️ Linha com id de compromisso e SEM `agendamentoOS` e caso real --
        e ali a tela nao pode exibir data nenhuma. `None`, nunca um palpite."""
        sem = {k: v for k, v in self.LINHA.items() if k != "agendamentoOS"}
        r = os_ponte._tecnicos_da_os(json.dumps([sem]))[0]
        assert r["agendamento_id"] == 969544
        assert r["inicio"] is None and r["fim"] is None
        assert r["janela"] is None

    def test_formato_estranho_devolve_o_CRU_em_vez_de_esconder(self):
        """🚨 Se o Harmonit mudar o formato, a tela mostra o cru -- feio e
        verdadeiro. Devolver `None` esconderia a mudanca e o defeito voltaria
        calado."""
        linha = dict(self.LINHA)
        linha["agendamentoOS"] = {"start": "2026-11-23T16:00:00",
                                  "end": "2026-11-23T18:00:00"}
        r = os_ponte._tecnicos_da_os(json.dumps([linha]))[0]
        assert r["janela"] and "2026-11-23" in r["janela"], r

    def test_dois_vinculos_e_o_que_tem_compromisso_ganha(self):
        """⚠️ O segundo vinculo de 21/10 e o caminho do reagendamento: o
        tecnico tem dois, e so um carrega o compromisso. A janela tem de vir do
        que carrega -- do outro viria vazia."""
        vazio = {"id": 1, "usuarioId": 14262, "nomeTecnico": "Franck",
                 "agendamentoId": 0, "agendamentoOS": None}
        r = os_ponte._tecnicos_da_os(json.dumps([vazio, self.LINHA]))
        assert len(r) == 1 and r[0]["vinculos"] == 2, r
        assert r[0]["janela"] == "23/11/2026 16:00 às 18:00", r
'''

assert "TestOResumoDoCompromissoDizQuemEQuando" not in u, "ja aplicado"
assert "os_ponte" in u, "o arquivo nao importa os_ponte"
# ⚠️ `json` não estava importado: a trava monta a fixture como o ERP a devolve
# e serializa, porque o `tecnicos_json` é TEXTO.
if "\nimport json\n" not in u:
    assert "import sys" in u, "nao achei onde por o import"
    u = u.replace("import sys", "import json\nimport sys", 1)
    print("  ok: import json acrescentado")
u = u.rstrip("\n") + "\n" + TRAVA
print("  ok: a classe de travas do resumo do compromisso")

saida = u.replace("\n", "\r\n") if CRLF else u
q.write_bytes(saida.encode("utf-8"))
print("gravado:", q, len(saida), "bytes")
