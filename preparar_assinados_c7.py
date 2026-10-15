"""Prepara o lote de PDFs ASSINADOS para a carga `C7`. RODA NO WINDOWS.

Lê a pasta da auditoria (`Downloads\\Termos Harmonit por Cliente`), onde cada
cliente tem `clicksign.csv` e uma subpasta `CLICKSIGN/`, e produz:

  <saida>/plano.jsonl   uma linha por documento, com o que o CSV sabe
  <saida>/pdf/<nome>    só os PDFs que vão subir

🚨 A PRIMEIRA GUARDA CONTRA DOCUMENTO ERRADO É NÃO COPIÁ-LO. Dos 3.251
documentos da Clicksign, 340 estão `cancelado`, 72 `rascunho` e 14 `pendente` --
e a 2HM tem um `3520 cancelado` ao lado de um `3520 assinado`. Aqui só o
`assinado` é copiado, e o estado do CSV tem de concordar com o nome do arquivo:
discordando, o documento é listado como excluído e não vai.

🚨 O CNPJ VEM DO NOME DA PASTA (`<RAZÃO SOCIAL> - <CNPJ>`), conferido: 731
pastas, nenhum CNPJ repetido. As duas pastas sem cliente (`_SEM_CLIENTE` e
`_SEM_CLIENTE_CLICKSIGN`) ficam de fora -- documento sem cliente não tem onde
ser gravado.

⚠️ O nome do arquivo tem `[` e `]` e acento. No PowerShell isso exige
`-LiteralPath`; aqui, em Python, `pathlib` já trata.

Uso:
  python preparar_assinados_c7.py "<pasta da auditoria>" "<pasta de saida>" [--cnpj X] [--limite N]
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

ESTADOS_QUE_SOBEM = {"assinado"}
PASTAS_SEM_CLIENTE = {"_SEM_CLIENTE", "_SEM_CLIENTE_CLICKSIGN"}


def cnpj_da_pasta(nome: str) -> str | None:
    m = re.search(r"(\d{11,14})\s*$", nome)
    return m.group(1) if m else None


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for pedaco in iter(lambda: fh.read(1 << 20), b""):
            h.update(pedaco)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("origem")
    p.add_argument("saida")
    p.add_argument("--cnpj", default=None)
    p.add_argument("--limite", type=int, default=None)
    a = p.parse_args()

    origem, saida = Path(a.origem), Path(a.saida)
    (saida / "pdf").mkdir(parents=True, exist_ok=True)

    contagem = {"clientes": 0, "copiados": 0, "fora_por_estado": 0,
                "estado_discorda_do_nome": 0, "arquivo_faltando": 0, "sem_cnpj_na_pasta": 0}
    plano = []

    for pasta in sorted(origem.iterdir()):
        if not pasta.is_dir() or pasta.name in PASTAS_SEM_CLIENTE:
            continue
        cnpj = cnpj_da_pasta(pasta.name)
        if not cnpj:
            contagem["sem_cnpj_na_pasta"] += 1
            continue
        if a.cnpj and cnpj != a.cnpj:
            continue
        csv_path = pasta / "clicksign.csv"
        if not csv_path.exists():
            continue
        contagem["clientes"] += 1

        with csv_path.open(encoding="utf-8-sig") as fh:
            for linha in csv.DictReader(fh, delimiter="|"):
                estado = (linha.get("Situacao") or "").strip().lower()
                arquivo = (linha.get("Arquivo") or "").strip()
                if estado not in ESTADOS_QUE_SOBEM:
                    contagem["fora_por_estado"] += 1
                    continue
                # 🚨 O CSV e o NOME têm de concordar. Duas fontes dizendo o
                # mesmo é o que impede um cancelado entrar por nome enganoso.
                if "- assinado [" not in arquivo:
                    contagem["estado_discorda_do_nome"] += 1
                    continue
                fonte = pasta / "CLICKSIGN" / arquivo
                if not fonte.exists():
                    contagem["arquivo_faltando"] += 1
                    continue

                # Nome de destino único: o mesmo nome de arquivo repete entre
                # clientes (`2 - aditivo - assinado [...]`), e dois clientes
                # diferentes não podem se sobrescrever no lote.
                destino_nome = f"{cnpj}__{arquivo}"
                shutil.copy2(fonte, saida / "pdf" / destino_nome)
                plano.append({
                    "cnpj": cnpj,
                    "cliente": pasta.name.rsplit(" - ", 1)[0],
                    "arquivo": destino_nome,
                    "arquivo_original": arquivo,
                    "estado": estado,
                    "numero": (linha.get("NrTermo") or "").strip(),
                    "tipo": (linha.get("Tipo") or "").strip(),
                    "assinado_em": (linha.get("AssinadoEm") or "").strip() or None,
                    "enviado_em": (linha.get("EnviadoEm") or "").strip() or None,
                    "chave_clicksign": (linha.get("ChaveClicksign") or "").strip(),
                    "vinculo_da_auditoria": (linha.get("Vinculo") or "").strip(),
                    "cnpj_no_pdf": (linha.get("CNPJ_CPF_no_PDF") or "").strip() or None,
                    "sha256": sha256(fonte),
                })
                contagem["copiados"] += 1
                if a.limite and contagem["copiados"] >= a.limite:
                    break
        if a.limite and contagem["copiados"] >= a.limite:
            break

    with (saida / "plano.jsonl").open("w", encoding="utf-8") as fh:
        for reg in plano:
            fh.write(json.dumps(reg, ensure_ascii=False) + "\n")

    print(json.dumps(contagem, ensure_ascii=False, indent=2))
    print(f"plano: {saida / 'plano.jsonl'} ({len(plano)} documentos)")


if __name__ == "__main__":
    main()
