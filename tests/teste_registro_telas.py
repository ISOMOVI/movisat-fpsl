"""O registro de telas — fonte única de navegação, permissão e auditoria.

🚨 A REGRA QUE TUDO SUSTENTA: o código é IMUTÁVEL e NUNCA é reaproveitado.
Reusar faria o log antigo mentir — um `CAD_1.1` gravado em agosto apontaria
para outra tela em novembro, e nenhuma auditoria sobreviveria a isso.

O que este arquivo prende:
  1. código único, e nenhum colide com um aposentado;
  2. o registro é a ÚNICA fonte — `abas.py` deriva dele, não tem lista própria;
  3. toda tela ativa tem rota de página que responde;
  4. toda permissão do registro é exigida por alguma rota (senão é permissão de
     mentira, que foi o que matou a aba `placas` em 14/08);
  5. reservada não sobe, aposentado não aparece;
  6. conta nova nasce sem nada: falha fechado.

Roda na VPS: venv/bin/python tests/teste_registro_telas.py
"""
import asyncio
import pathlib
import re
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso import storage  # noqa: E402
from fpsl_weso.painel import abas as abas_painel, telas  # noqa: E402
from fpsl_weso.painel.auth import criar_token  # noqa: E402

BASE = "http://127.0.0.1:8004"
RAIZ = pathlib.Path(__file__).resolve().parent.parent

ok, falhas = 0, []


def checar(nome, esperado, obtido):
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}\n       esperado: {esperado!r}\n       obtido:   {obtido!r}")


print("\n[1] o código é único e nunca reaproveitado")
codigos = [t["codigo"] for t in telas.TELAS]
checar("nenhum código repetido", len(codigos), len(set(codigos)))
# 🚨 A TRAVA CENTRAL. Se um aposentado voltar, o log antigo passa a mentir.
checar("nenhum código ativo colide com aposentado", set(),
       set(codigos) & telas.CODIGOS_APOSENTADOS)
checar("todo código segue MOD_n.n", [],
       [c for c in codigos if not re.fullmatch(r"[A-Z]{3}_\d+\.\d+", c)])
checar("por_codigo acha todos", len(codigos),
       sum(1 for c in codigos if telas.por_codigo(c)))
try:
    telas.por_codigo("XXX_9.9")
    achou = True
except telas.CodigoDeTelaInvalido:
    achou = False
checar("código inexistente ESTOURA, não degrada", False, achou)

print("\n[2] o registro é a única fonte")
# ⚠️ `abas.py` deixou de ter lista própria em 17/08. Se voltar a ter, existem
# duas fontes e uma delas vai divergir -- que é o problema que o registro
# resolve.
fonte_abas = (RAIZ / "fpsl_weso" / "painel" / "abas.py").read_text(encoding="utf-8")
checar("abas.py não declara ABAS como literal", False,
       bool(re.search(r"^ABAS\s*=\s*\[", fonte_abas, re.M)))
checar("abas.py importa o registro", True, "import telas" in fonte_abas)
checar("as permissões de ABAS vêm do registro",
       telas.PERMISSOES_VALIDAS, {a["id"] for a in abas_painel.ABAS})
checar("uma entrada por permissão, sem repetir",
       len({a["id"] for a in abas_painel.ABAS}), len(abas_painel.ABAS))

print("\n[3] reservada não sobe, e o que sobe é da fase")
ativas = telas.ativas()
checar("nenhuma ativa tem fase acima da atual", [],
       [t["codigo"] for t in ativas if t["fase"] > telas.FASE_ATUAL])
reservadas = [t for t in telas.TELAS if t["fase"] > telas.FASE_ATUAL]
checar("há reservadas registradas", True, len(reservadas) > 0)
checar("e nenhuma delas aparece em `ativas`", set(),
       {t["codigo"] for t in reservadas} & {t["codigo"] for t in ativas})

print("\n[4] permissão que ninguém exige é permissão de mentira")
# 🚨 Foi isso que matou a aba `placas` em 14/08: ela aparecia no perfil e
# nenhuma rota a exigia. Quem recebia via o link e não conseguia usar.
routers = (RAIZ / "fpsl_weso" / "painel" / "routers")
codigo_rotas = "\n".join(p.read_text(encoding="utf-8")
                         for p in routers.glob("*.py") if ".bak" not in p.name)
exigidas = set(re.findall(r'requer_aba\(([^)]*)\)', codigo_rotas))
exigidas = {x.strip().strip('"\'') for grupo in exigidas
            for x in grupo.split(",")}
for p in sorted(telas.PERMISSOES_CONCEDIVEIS):
    checar(f"alguma rota exige {p!r}", True, p in exigidas)

print("\n[5] pública é pública, só-owner é só do owner")
publicas = [t for t in telas.TELAS if t["permissao"] is None]
checar("as públicas estão fora do menu", True,
       all(t.get("no_menu") for t in publicas))
magro = {"owner": False, "abas": list(telas.PERMISSOES_CONCEDIVEIS)}
for p in telas.PERMISSOES_SO_OWNER:
    tela = next(t for t in telas.TELAS if t["permissao"] == p)
    checar(f"quem não é owner não acessa {tela['codigo']}", False,
           telas.pode_acessar(magro, tela["codigo"]))
    checar(f"e {p!r} não é concedível", False,
           p in telas.PERMISSOES_CONCEDIVEIS)

print("\n[6] conta nova falha fechado")
vazio = {"owner": False, "abas": []}
checar("sem permissão, menu vazio", [], telas.do_usuario(vazio))
checar("normalizar descarta o que não é concedível", [],
       telas.normalizar(list(telas.PERMISSOES_SO_OWNER) + ["inventada"]))


async def main():
    admin = await storage.buscar_usuario_painel("admin")
    h = {"Authorization": "Bearer " + criar_token(admin["login"])}

    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        print("\n[7] toda tela ativa com página responde")
        for t in telas.ativas():
            if "{" in t["rota"] or t["permissao"] is None:
                continue          # rota com parâmetro ou pública por token
            r = await c.get(t["rota"], headers=h)
            checar(f"{t['codigo']} {t['rota']}", 200, r.status_code)

        print("\n[8] a CFG_9.1 devolve o registro inteiro")
        r = await c.get("/painel/api/usuarios/telas", headers=h)
        checar("responde ao owner", 200, r.status_code)
        d = r.json()
        checar("conta as ativas", len(telas.ativas()), d["ativas"])
        checar("conta as reservadas", len(reservadas), d["reservadas"])
        # 🚨 O REGISTRO INTEIRO, inclusive reservadas e aposentados: mostrar só
        # o que está no ar esconderia o que a tela existe para proteger.
        checar("traz as reservadas também", len(telas.TELAS), len(d["telas"]))
        checar("e os aposentados", sorted(telas.CODIGOS_APOSENTADOS),
               d["aposentados"])

        r = await c.get("/painel/api/usuarios/telas")
        checar("sem token dá 401", 401, r.status_code)


asyncio.run(main())

print()
print("=" * 52)
print(f"{ok} verificações OK, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1)
