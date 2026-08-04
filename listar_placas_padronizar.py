"""Lista as placas da WESO fora do padrão, para padronização manual (2026-07-27).

Só leitura. Gera CSV em /tmp/placas_padronizar.csv e imprime o resumo.

Grupos:
  A) convencional SEM espaco  -> essas sim precisam virar 'ABC 1D23'
  B) com minuscula            -> padronizar caixa
  C) nao convencional         -> chassi/serie de maquina, NAO e placa (nao mexer)
"""
import asyncio
import csv
import re

import httpx

from fpsl_weso.config import settings

# client proprio so pra este script: o padrao do projeto usa timeout 30s e a
# lista inteira (1.965 veiculos) as vezes passa disso. A key vem do settings
# (lido do .env) -- nunca de linha de comando.
TIMEOUT = 180

RE_ANTIGA = re.compile(r"^[A-Z]{3}[ -]?\d{4}$")
RE_MERCOSUL = re.compile(r"^[A-Z]{3}[ -]?\d[A-Z]\d{2}$")


def limpar(p):
    return re.sub(r"\s*\(RD\)\s*", "", str(p).strip().upper())


def classificar(p):
    c = limpar(p)
    if RE_ANTIGA.match(c):
        return "convencional antiga"
    if RE_MERCOSUL.match(c):
        return "convencional Mercosul"
    return "NAO convencional"


def sugerir(p):
    """'ABC1234' -> 'ABC 1234' (mantem o marcador (RD) no fim, se houver)."""
    rd = " (RD)" if re.search(r"\(RD\)", str(p), re.I) else ""
    c = limpar(p)
    if len(c) == 7 and " " not in c:
        return f"{c[:3]} {c[3:]}{rd}"
    return ""


async def buscar_veiculos(tentativas=3):
    async with httpx.AsyncClient(base_url=settings.weso_base_url, timeout=TIMEOUT) as c:
        for n in range(1, tentativas + 1):
            try:
                r = await c.get("/Veiculos/Consultar", params={"key": settings.weso_api_key})
                corpo = r.json()
                dados = corpo.get("Data", corpo)
                return dados.get("veiculos") or []
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                print(f"  tentativa {n}/{tentativas} falhou ({type(e).__name__}), repetindo...")
                if n == tentativas:
                    raise
                await asyncio.sleep(5)


async def main():
    if True:
        veics = await buscar_veiculos()

        sem_espaco, minusculas = [], []
        for v in veics:
            p = str(v.get("placa") or "")
            if not p:
                continue
            if " " not in p.strip():
                sem_espaco.append(v)
            if p != p.upper():
                minusculas.append(v)

        conv = [v for v in sem_espaco if classificar(v["placa"]) != "NAO convencional"]
        nconv = [v for v in sem_espaco if classificar(v["placa"]) == "NAO convencional"]

        print(f"total na WESO: {len(veics)}")
        print(f"sem espaco: {len(sem_espaco)}  ->  {len(conv)} convencionais (PADRONIZAR) "
              f"+ {len(nconv)} chassi/serie (nao mexer)")
        print(f"com minuscula: {len(minusculas)}\n")

        print("=" * 72)
        print("A) CONVENCIONAIS SEM ESPACO  -- estas precisam de correcao")
        print("=" * 72)
        print(f"{'veiculo_id':>10}  {'placa atual':<22} {'sugerido':<22} rastreador_id")
        for v in sorted(conv, key=lambda x: str(x.get("placa"))):
            print(f"{v['id']:>10}  {str(v['placa']):<22} {sugerir(v['placa']):<22} {v.get('rastreador_id')}")

        print()
        print("=" * 72)
        print("B) COM MINUSCULA -- padronizar caixa")
        print("=" * 72)
        print(f"{'veiculo_id':>10}  {'placa atual':<22} {'sugerido':<22} rastreador_id")
        for v in sorted(minusculas, key=lambda x: str(x.get("placa"))):
            alvo = str(v["placa"]).upper()
            print(f"{v['id']:>10}  {str(v['placa']):<22} {alvo:<22} {v.get('rastreador_id')}")

        print()
        print("=" * 72)
        print(f"C) NAO CONVENCIONAIS ({len(nconv)}) -- chassi/serie de maquina, NAO sao placa")
        print("=" * 72)
        for v in sorted(nconv, key=lambda x: str(x.get("placa"))):
            desc = str(v.get("descricao") or "")[:34]
            print(f"{v['id']:>10}  {str(v['placa']):<26} {desc}")

        with open("/tmp/placas_padronizar.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["grupo", "veiculo_id", "placa_atual", "sugerido", "rastreador_id", "descricao"])
            for v in conv:
                w.writerow(["A_convencional_sem_espaco", v["id"], v["placa"], sugerir(v["placa"]),
                            v.get("rastreador_id"), v.get("descricao")])
            for v in minusculas:
                w.writerow(["B_minuscula", v["id"], v["placa"], str(v["placa"]).upper(),
                            v.get("rastreador_id"), v.get("descricao")])
            for v in nconv:
                w.writerow(["C_nao_convencional", v["id"], v["placa"], "",
                            v.get("rastreador_id"), v.get("descricao")])
        print("\nCSV: /tmp/placas_padronizar.csv")


asyncio.run(main())
