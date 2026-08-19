import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fpsl_weso.client import start_client, stop_client
from fpsl_weso.harmonit_client import start_harmonit_client, stop_harmonit_client
from fpsl_weso.routers import clientes, simcards, rastreadores, veiculos, admin
from fpsl_weso.painel.routers import login_router, os_router as painel_os_router
from fpsl_weso.painel.routers import harmonit_hist_router as painel_harmonit_hist_router
from fpsl_weso.painel.routers import clientes_router as painel_clientes_router
from fpsl_weso.painel.routers import usuarios_router as painel_usuarios_router
from fpsl_weso.painel.routers import os_scan_router as painel_os_scan_router
from fpsl_weso.painel.routers import placas_router as painel_placas_router
# 🚨 PÚBLICO por link, fora do /painel: o quadro de demandas não exige conta.
from fpsl_weso.painel.routers import demandas_router
from fpsl_weso import demandas as quadro_demandas
from fpsl_weso.painel.auth import seed_admin_inicial
from fpsl_weso.services import onboarding
from fpsl_weso.services.sync_inadimplencia import loop_inadimplencia
from fpsl_weso import storage

log = logging.getLogger("fpsl")


class MascararSegredoDaQueryString(logging.Filter):
    """Tira segredo da query string da linha de acesso ANTES de ela ir ao disco.

    🚨 O `code` DO OAUTH DO GOOGLE ESTAVA INDO INTEIRO PARA O JOURNAL. Medido em
    18/08: 37 entradas; em 19/08 ainda havia 31 no journal vivo (o resto saiu na
    rotacao). E a mesma classe do incidente de 12/08 no MoviZap, onde o segredo
    do webhook do Evolution foi para o disco 2.527 vezes em 24 h.

    ⚠️ O RISCO AQUI E MENOR, e vale dizer por que: o `code` e de uso unico e
    expira em ~10 min, entao um journal antigo nao autentica ninguem. O que
    justifica o filtro nao e o dano provavel -- e o habito. Segredo em log e
    algo que so se conserta antes de acontecer.

    🚨 POR QUE UM FILTRO E NAO UM MIDDLEWARE: quem escreve esta linha e o
    `uvicorn.access`, que nao passa pelo middleware da aplicacao. Em 12/08
    tentou-se resolver no middleware e o segredo continuou saindo.

    ⚠️ REESCREVE `record.args`, NAO A MENSAGEM FORMATADA. O `uvicorn.access`
    guarda os campos separados (`%s - "%s %s HTTP/%s" %d`) e so os junta na
    hora de escrever; mexer na mensagem final nao pega nada. Foi assim que o
    MoviZap resolveu, e o formato e o mesmo.

    ⚠️ NAO ALCANCA O `access.log` DO NGINX, que registra a mesma linha e exige
    root. No FPSL isso hoje nao e problema: a entrada pelo Google chega pelo
    nginx do MoviZap, que ja tem `log_format` mascarado desde 12/08.
    """

    # Nomes de parametro cujo VALOR nunca pode ir ao disco. `state` entra
    # junto: e o anti-CSRF do fluxo, e vale a mesma regra.
    SENSIVEIS = ("code", "state", "id_token", "access_token", "refresh_token")

    def _limpar(self, caminho: str) -> str:
        if "?" not in caminho:
            return caminho
        rota, _, consulta = caminho.partition("?")
        partes = []
        for par in consulta.split("&"):
            nome, sep, _valor = par.partition("=")
            if sep and nome in self.SENSIVEIS:
                partes.append(f"{nome}=<mascarado>")
            else:
                partes.append(par)
        return rota + "?" + "&".join(partes)

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple):
            return True
        limpos = tuple(
            self._limpar(a) if isinstance(a, str) and "?" in a else a
            for a in args
        )
        if limpos != args:
            record.args = limpos
        return True


# Vale para o logger do uvicorn e para o do gunicorn, conforme quem sobe o
# processo -- registrar nos dois e barato e nao depende de lembrar qual e.
for _nome in ("uvicorn.access", "gunicorn.access"):
    logging.getLogger(_nome).addFilter(MascararSegredoDaQueryString())


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    await seed_admin_inicial()
    # Cria o esquema e a semente do quadro de demandas. Idempotente.
    quadro_demandas.preparar()
    await start_client()
    await start_harmonit_client()
    asyncio.create_task(loop_inadimplencia())
    asyncio.create_task(painel_os_scan_router.loop_scan_os())
    asyncio.create_task(painel_os_scan_router.loop_resync_os())
    yield
    await stop_harmonit_client()
    await stop_client()


app = FastAPI(
    title="FPSL WESO",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

@app.middleware("http")
async def identificar_requisicao(request: Request, call_next):
    """Da um id curto a cada requisicao e devolve no header.

    Espelha o middleware do MoviZap (`movizap/main.py`, em producao desde
    12/08). E esse id que a barra de status mostra: no suporte, o que se
    procura no journal nao e "a tela de placas por volta das 14h" -- e AQUELA
    requisicao. So loga o que interessa (lento ou com erro), para nao repetir
    no journal o que o uvicorn ja escreve.
    """
    req_id = secrets.token_hex(2)
    request.state.req_id = req_id
    inicio = time.perf_counter()
    try:
        resposta = await call_next(request)
    except Exception:
        log.exception("req=%s %s %s", req_id, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno.", "req_id": req_id},
            headers={"X-Request-Id": req_id},
        )
    ms = (time.perf_counter() - inicio) * 1000
    resposta.headers["X-Request-Id"] = req_id
    if ms > 1000 or resposta.status_code >= 400:
        log.info("req=%s %s %s -> %s em %.0fms",
                 req_id, request.method, request.url.path, resposta.status_code, ms)
    return resposta


app.include_router(clientes.router)
app.include_router(simcards.router)
app.include_router(rastreadores.router)
app.include_router(veiculos.router)
app.include_router(onboarding.router)
app.include_router(admin.router)
app.include_router(login_router.router)
app.include_router(painel_os_router.router)
app.include_router(painel_harmonit_hist_router.router)
app.include_router(painel_clientes_router.router)
app.include_router(painel_usuarios_router.router)
app.include_router(painel_os_scan_router.router)
app.include_router(painel_placas_router.router)
app.include_router(demandas_router.router)

app.mount("/painel/static", StaticFiles(directory="frontend"), name="painel_static")


@app.get("/painel")
async def painel_login_page():
    return FileResponse("frontend/login.html")


@app.get("/painel/gerar-os")
async def painel_wizard_page():
    return FileResponse("frontend/gerar_os.html")


@app.get("/painel/usuarios")
async def painel_usuarios_page():
    return FileResponse("frontend/usuarios.html")


@app.get("/painel/vinculos")
async def painel_vinculos_page():
    return FileResponse("frontend/vinculos.html")


@app.get("/painel/cadastro-placas")
async def painel_cadastro_placas_page():
    return FileResponse("frontend/cadastro_placas.html")


# ⚠️ MESMA ABA da tela principal, de propósito. Não é aba nova: quem cadastra
# placa precisa ver o que cadastrou, e uma permissão separada para "ver o que eu
# mesmo fiz" seria burocracia sem dono. Fica fora da sidebar, alcançada por link.
@app.get("/painel/cadastro-placas/historico")
async def painel_cadastro_placas_historico_page():
    return FileResponse("frontend/cadastro_placas_historico.html")


@app.get("/painel/harmonit-historico")
async def painel_harmonit_hist_page():
    return FileResponse("frontend/harmonit_historico.html")


@app.get("/painel/os-historico")
async def painel_os_historico_page():
    return FileResponse("frontend/os_historico.html")


@app.get("/painel/config/telas")
async def painel_registro_telas_page():
    return FileResponse("frontend/registro_telas.html")


@app.get("/painel/config")
async def painel_config_page():
    return FileResponse("frontend/config.html")
