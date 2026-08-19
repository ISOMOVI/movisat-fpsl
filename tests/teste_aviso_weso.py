"""A WESO que não responde vira AVISO NA TELA, não linha de log (2026-08-19).

🚨 POR QUE ESTE TESTE EXISTE. A OS 16775, gerada em 17/08 15:39, saiu sem o
rastreador e sem o chip, e o operador só descobriu conferindo no Harmonit. A
causa estava no journal, no minuto exato:

    Aug 17 15:39:29  equipamentos: base de veiculos indisponivel:
                     502: WESO indisponivel (timeout)

`_rastreador_id_por_placa` engolia a exceção, devolvia `{}` e a geração seguia
como se a WESO tivesse respondido "nenhuma dessas placas tem rastreador". Sem
rastreador não há modelo, sem modelo não há material nem chip. O de-para estava
íntegro — a hipótese registrada de "modelo faltando no de-para" era falsa.

O que este teste trava:
  1. `_anotar` não repete a mesma mensagem e aceita `None` sem explodir;
  2. WESO fora ⇒ `buscar_seriais` e `dados_das_placas` ANOTAM a falha;
  3. chamador que não passa lista continua funcionando como antes;
  4. 🚨 WESO respondendo ⇒ NENHUM aviso. Aviso falso treina a ignorar o aviso;
  5. o contrato com o `os_router`: as duas chamadas passam a lista e ela cai
     em `avisos`;
  6. o contrato com a TELA: o `gerar_os.html` renderiza `data.avisos`.

Os itens 5 e 6 leem o CONSUMIDOR, que é a lição de 18/08: naquele dia 677
verificações passaram com o painel inteiro derrubado porque nenhuma olhava
quem consome o JSON. Um aviso que a tela não mostra é o mesmo defeito de novo.

Roda na VPS:  venv/bin/python tests/teste_aviso_weso.py
Não faz rede — a WESO é substituída por dublê. Não toca banco.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import equipamentos  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ROUTER = RAIZ / "fpsl_weso" / "painel" / "routers" / "os_router.py"
TELA = RAIZ / "frontend" / "gerar_os.html"

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


# Placa que não existe em lugar nenhum: garante que o cache local não resolve
# antes de a WESO ser chamada. Se um dia existir, o item 2 falha ruidosamente
# em vez de passar por engano.
PLACA = "ZZZ0X99"
MUITAS = [f"ZZZ0X{n:02d}" for n in range(10)]  # acima de LIMIAR_PLACA_A_PLACA


class _SemCache:
    """Dublê do cache local: nunca resolve nada, força ir à WESO."""

    def esta_fresco(self):
        return True

    def idade_horas(self):
        return 0

    def seriais_por_placas(self, placas):
        return {}


def _com_weso(resposta):
    """Substitui `weso_get` por um dublê. `resposta` é chamável ou exceção."""

    async def dubla(path, params=None):
        if isinstance(resposta, BaseException):
            raise resposta
        return resposta

    return dubla


def rodar(corotina):
    return asyncio.run(corotina)


# ── 1. o próprio `_anotar` ───────────────────────────────────────────────────
print("\n[1] _anotar")
_l = []
equipamentos._anotar(_l, "a")
equipamentos._anotar(_l, "a")
equipamentos._anotar(_l, "b")
checar("não repete a mesma mensagem", _l == ["a", "b"], f"obtido: {_l!r}")
equipamentos._anotar(None, "a")  # não pode explodir
checar("aceita None sem explodir", True)

# ── 2. WESO fora: a falha é anotada ──────────────────────────────────────────
print("\n[2] WESO fora — a falha chega a quem pediu")
_weso_real, _cache_real = equipamentos.weso_get, equipamentos._cache
equipamentos.weso_get = _com_weso(RuntimeError("502: WESO indisponível (timeout)"))
equipamentos._cache = lambda: _SemCache()
try:
    f1 = []
    r1 = rodar(equipamentos.buscar_seriais([PLACA], f1))
    checar("buscar_seriais devolve vazio", r1 == {}, f"obtido: {r1!r}")
    checar("buscar_seriais anota a falha",
           f1 == [equipamentos.AVISO_BASE_MUDA], f"obtido: {f1!r}")

    f2 = []
    r2 = rodar(equipamentos.dados_das_placas([PLACA], f2))
    checar("dados_das_placas devolve vazio", r2 == {}, f"obtido: {r2!r}")
    checar("dados_das_placas anota a falha",
           f2 == [equipamentos.AVISO_BASE_MUDA], f"obtido: {f2!r}")

    # ── 3. chamador antigo, que não passa lista ──────────────────────────────
    print("\n[3] chamador que não passa lista continua igual")
    checar("buscar_seriais sem lista", rodar(equipamentos.buscar_seriais([PLACA])) == {})
    checar("dados_das_placas sem lista", rodar(equipamentos.dados_das_placas([PLACA])) == {})
    checar("buscar_recipientes sem lista",
           rodar(equipamentos.buscar_recipientes([PLACA], "-MANUT")) == {})

    # ── 4. timeout da base inteira ───────────────────────────────────────────
    print("\n[4] timeout da base inteira")
    equipamentos.weso_get = _com_weso(asyncio.TimeoutError())
    f3 = []
    rodar(equipamentos.dados_das_placas(MUITAS, f3))
    checar("timeout também anota", f3 == [equipamentos.AVISO_BASE_MUDA], f"obtido: {f3!r}")

    # ── 5. WESO respondendo: silêncio ────────────────────────────────────────
    print("\n[5] WESO respondendo — nenhum aviso")
    equipamentos.weso_get = _com_weso({"veiculos": []})
    f4 = []
    rodar(equipamentos.buscar_seriais([PLACA], f4))
    checar("buscar_seriais não inventa aviso", f4 == [], f"obtido: {f4!r}")
    f5 = []
    rodar(equipamentos.dados_das_placas(MUITAS, f5))
    checar("dados_das_placas não inventa aviso", f5 == [], f"obtido: {f5!r}")
finally:
    equipamentos.weso_get, equipamentos._cache = _weso_real, _cache_real

# ── 6. contrato com o os_router (o consumidor) ───────────────────────────────
print("\n[6] contrato com o os_router")
fonte = ROUTER.read_text(encoding="utf-8")
checar("router declara a lista", "falhas_weso: list[str] = []" in fonte)
checar("router passa a lista a buscar_seriais",
       "buscar_seriais(todas, falhas_weso)" in fonte)
checar("router passa a lista a dados_das_placas",
       "dados_das_placas(alvos, falhas_weso)" in fonte)
checar("router despeja a lista em avisos", "avisos += falhas_weso" in fonte)
# A ordem importa: despejar depois de montar as operações deixaria o aviso
# fora da resposta em qualquer caminho que retorne antes.
checar("despeja ANTES de montar as operações",
       fonte.index("avisos += falhas_weso") < fonte.index("operacoes = _montar_operacoes"))

# ── 7. contrato com a tela ───────────────────────────────────────────────────
print("\n[7] contrato com a tela")
html = TELA.read_text(encoding="utf-8")
checar("a tela lê data.avisos", "data.avisos" in html)
checar("a tela escapa o aviso", "escapeHtml(a)" in html)
checar("o container existe no HTML", 'id="resumoAvisos"' in html)

print(f"\n{'='*60}\n{ok} verificações OK, {len(falhas)} falha(s)")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
