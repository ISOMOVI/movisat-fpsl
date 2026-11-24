# -*- coding: utf-8 -*-
"""Tarefa 4.4 (B1) — a varredura de rotas DESCE no `_IncludedRouter`.

🚨 O DEFEITO, MEDIDO EM 23/11 e pior do que o registro dizia. `app.routes` tem
**37 entradas**, e **19 delas são `_IncludedRouter`** -- embrulhos opacos que o
FastAPI novo põe no lugar de copiar as rotas filhas. Quem varre `app.routes`
lendo `.path` vê **17 caminhos**; as rotas de verdade são **192**.

    entradas em app.routes:  37   (1 Route + 16 APIRoute + 19 _IncludedRouter + 1 Mount)
    rotas EFETIVAS:         192

⚠️ E o registro dizia *"17 das 37"*: o 37 era o tamanho da LISTA, não o número
de rotas. A conta certa é 17 de 192 -- e `/api/os/ficha`, a ponte inteira do
MoviZap, era uma das invisíveis.

🚨 POR QUE ISSO IMPORTA: toda varredura que confere permissão, prefixo ou
duplicidade por `app.routes` está medindo 9% do sistema e dizendo que mediu
tudo. Trava que olha para o lugar errado é pior que trava nenhuma -- ela dá o
verde.

⚠️ `Mount` fica de fora de propósito: é o diretório estático, não rota de API.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.routing import _IncludedRouter  # noqa: E402

from main import app  # noqa: E402


def rotas_efetivas(aplicacao) -> list[tuple[str, str]]:
    """Todo par (método, caminho) que a aplicação REALMENTE serve.

    🚨 A recursão é o ponto: `_IncludedRouter.effective_candidates()` é o que
    revela as filhas, e uma filha pode ser outro `_IncludedRouter` (router
    dentro de router). Parar no primeiro nível perderia um nível inteiro sem
    dizer nada.
    """
    saida: list[tuple[str, str]] = []
    pilha = list(aplicacao.routes)
    while pilha:
        r = pilha.pop()
        if isinstance(r, _IncludedRouter):
            pilha.extend(r.effective_candidates())
            continue
        caminho = getattr(r, "path", None)
        if not caminho:
            continue
        for metodo in sorted(getattr(r, "methods", None) or ["-"]):
            saida.append((metodo, caminho))
    return saida


class TestAVarreduraVeTodasAsRotas:
    def test_a_varredura_desce_no_IncludedRouter(self):
        """🚨 A trava central: varrer `app.routes` cru vê 17 de 192."""
        cru = [getattr(r, "path", None) for r in app.routes]
        cru = [p for p in cru if p]
        todas = rotas_efetivas(app)
        assert len(todas) > len(cru) * 5, (
            "a varredura nao esta descendo: %d caminhos crus x %d efetivas"
            % (len(cru), len(todas)))

    def test_a_ponte_do_MoviZap_NAO_e_invisivel(self):
        """🚨 `/api/os/ficha` era uma das 175 que a varredura crua nao via -- e
        e a rota que o card do chamado usa. A ponte inteira estava fora."""
        todas = rotas_efetivas(app)
        assert ("GET", "/api/os/ficha") in todas, (
            "a rota da ficha nao aparece nem na varredura que desce")
        ponte = {c for m, c in todas if c.startswith("/api/os/")}
        assert len(ponte) >= 10, (
            "a ponte tem 10 rotas documentadas e a varredura achou %d: %s"
            % (len(ponte), sorted(ponte)))

    def test_NENHUMA_rota_fica_na_SOMBRA_de_outra(self):
        """🚨 E para isto que a varredura existe: dois registros do MESMO par
        (metodo, caminho) significam que o segundo nunca roda -- o FastAPI
        atende o primeiro que casa, em silencio.

        📏 Medido em 23/11: ZERO sombras nas 192. A trava guarda o estado.
        """
        todas = rotas_efetivas(app)
        repetidos = sorted(k for k, n in Counter(todas).items() if n > 1)
        assert repetidos == [], (
            "rota na sombra (o segundo registro nunca roda): %s" % repetidos)

    def test_toda_rota_mora_num_NAMESPACE_CONHECIDO(self):
        """⚠️ CORRIJO UMA SUPOSICAO MINHA, de 23/11: eu escrevi primeiro uma
        trava exigindo `/api/` em toda rota de API, e ela reprovou com 147
        rotas. O FPSL nao usa esse prefixo -- usa `/painel/api/`, `/weso/`,
        `/demandas/` e `/admin/`. Era a TRAVA errada, nao o codigo.

        🚨 O que vale medir e outra coisa: rota que nasce FORA dos namespaces
        conhecidos escapa das travas de permissao e das regras do nginx, que
        sao escritas por prefixo -- e escapa calada, do mesmo jeito que as 175
        rotas escapavam da varredura.

        📏 Os namespaces sao os medidos em 23/11, nao presumidos.
        """
        # 📏 Os DEZ namespaces medidos em 23/11. ⚠️ O `/api/pagamento/` entrou
        # porque esta propria trava o achou: sao as 15 rotas da aba 2
        # (Servico dos tecnicos), e eu havia listado so o `/api/os/`.
        CONHECIDOS = ("/api/os/", "/api/pagamento/", "/painel", "/weso/",
                      "/demandas/", "/admin/", "/docs", "/redoc",
                      "/openapi.json", "/health")
        fora = sorted({
            c for _m, c in rotas_efetivas(app)
            if not c.startswith(CONHECIDOS)
        })
        assert fora == [], (
            "rota fora de todo namespace conhecido (as travas de permissao e "
            "o nginx sao por prefixo, entao ela escapa das duas): %s" % fora)
