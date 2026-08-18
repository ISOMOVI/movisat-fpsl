"""A tela de Cadastro de Placas — passo 3, o caminho do termo.

🚨 O QUE ESTE ARQUIVO PRENDE, e por que cada coisa:

  1. **O caminho digitado sobreviveu.** A manutenção não tem documento; se a
     origem "do termo" tivesse substituído o textarea em vez de somar, a
     manutenção pararia de funcionar e nada acusaria.

  2. **A tabela editável tem os dois campos por linha**, com `data-linha`
     casando veículo e placa. Sem isso o botão inverter troca o par errado.

  3. **Inverter é por LINHA.** O erro contratual costuma ser em algumas linhas,
     não no documento inteiro.

  4. **Descrição vazia BLOQUEIA o avanço.** A `FKX 9E34` do 8800 vem sem
     descrição, e sem ela a WESO grava a própria placa como descrição -- que é
     dado inventado entrando em sistema de produção.

  5. **O recipiente sai do PERFIL, não de seletor.** Um seletor a mais seria
     uma chance a mais de escolher errado.

  6. **Escape em tudo que vem do PDF.** O texto vem de documento externo -- é a
     origem menos confiável de todas, e foi a auditoria de 15/07 que impôs isso.

Roda na VPS: venv/bin/python tests/teste_tela_cadastro_placas.py
Lê o `/perfis` e o `/extrair`. NÃO ESCREVE NADA.
"""
import asyncio
import pathlib
import re
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel.auth import criar_token  # noqa: E402

BASE = "http://127.0.0.1:8004"
RAIZ = pathlib.Path(__file__).resolve().parent.parent
TELA = RAIZ / "frontend" / "cadastro_placas.html"

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


html = TELA.read_text(encoding="utf-8")

print("\n[1] os dois caminhos convivem")
checar("o bloco do termo existe", True, 'id="blocoTermo"' in html)
# 🚨 se este sumir, a manutenção para de funcionar
checar("o bloco digitado continua", True, 'id="blocoDigitado"' in html)
checar("a caixa de placas digitadas continua", True, 'id="placas"' in html)
checar("e a origem manutenção continua no seletor", True,
       'value="manutencao"' in html)

print("\n[2] a tabela editável")
checar("tem coluna Veículo antes de Placa", True,
       html.index("<th>Veículo</th>") < html.index("<th>Placa</th>"))
checar("os campos carregam data-linha", True,
       'data-campo="veiculo" data-linha=' in html and
       'data-campo="placa" data-linha=' in html)
checar("o botão inverter é por linha", True,
       bool(re.search(r'onclick="inverter\(\$\{n\}\)"', html)))
checar("e inverter troca os DOIS campos da MESMA linha", True,
       bool(re.search(r"function inverter\(n\)[\s\S]{0,320}data-linha=\"\$\{n\}\""
                      r"[\s\S]{0,320}data-linha=\"\$\{n\}\"", html)))

print("\n[3] descrição vazia bloqueia")
checar("há guarda de descrição vazia", True, "sem descrição do veículo" in html)
checar("e ela impede o avanço (return antes da prévia)", True,
       bool(re.search(r"semDesc\.length[\s\S]{0,140}return;", html)))
checar("a linha sem descrição é destacada", True, "linha-atencao" in html)

print("\n[4] o recipiente vem do perfil")
checar("usa recipiente_sufixo do backend", True,
       "extraido.recipiente_sufixo" in html)
# ⚠️ o seletor manual de sufixo continua existindo SÓ no caminho digitado
checar("não há seletor de sufixo no caminho do termo", True,
       "extraido.sufixo" not in html)

print("\n[5] escape do que vem do PDF")
for campo in ("i.veiculo", "i.placa", "c.harmonit_nome", "c.weso_nome",
              "c.nome_no_termo", "d.documento"):
    checar(f"{campo} passa por escapeHtml", True,
           bool(re.search(r"escapeHtml\(\s*" + re.escape(campo), html)))

print("\n[6] resposta lida como TEXTO antes de virar JSON")
# 🚨 em 14/08 uma página HTML de 504 caiu num `res.json()` e virou "erro json"
checar("lerTermo lê texto primeiro", True,
       bool(re.search(r"async function lerTermo[\s\S]{0,900}await res\.text\(\)", html)))


async def main():
    admin = await storage.buscar_usuario_painel("admin")
    h = {"Authorization": "Bearer " + criar_token(admin["login"])}

    async with httpx.AsyncClient(base_url=BASE, timeout=180) as c:
        print("\n[7] o seletor de perfis funciona para esta aba")
        r = await c.get("/painel/api/perfis", headers=h)
        checar("/perfis responde", 200, r.status_code)
        perfis = r.json()
        com_termo = [k for k, p in perfis.items() if not p.get("sem_termo")]
        checar("7 perfis nascem de documento", 7, len(com_termo))
        checar("manutenção NÃO está entre eles", True,
               not any(k.startswith("manutencao") for k in com_termo))

        print("\n[8] ponta a ponta: o 8800 chega pronto para a tabela")
        with open(RAIZ / "tests" / "fixtures" / "upgrade_4g_8800.pdf", "rb") as f:
            r = await c.post("/painel/api/placas/extrair?perfil=upgrade",
                             headers=h,
                             files={"arquivo": ("t.pdf", f.read(), "application/pdf")})
        d = r.json()
        checar("11 linhas para a tabela", 11, len(d["itens"]))
        checar("cada uma tem veículo e placa", True,
               all("veiculo" in i and "placa" in i for i in d["itens"]))
        checar("a tela sabe qual destacar", 1,
               sum(1 for i in d["itens"] if i["sem_descricao"]))
        checar("e qual recipiente criar", "-UPGRADE", d["recipiente_sufixo"])


asyncio.run(main())

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
