import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fpsl_weso.client import start_client, stop_client
from fpsl_weso.harmonit_client import start_harmonit_client, stop_harmonit_client
from fpsl_weso.routers import clientes, simcards, rastreadores, veiculos, os, admin
from fpsl_weso.painel.routers import login_router, os_router as painel_os_router
from fpsl_weso.painel.routers import placas_router as painel_placas_router
from fpsl_weso.painel.routers import harmonit_hist_router as painel_harmonit_hist_router
from fpsl_weso.painel.routers import clientes_router as painel_clientes_router
from fpsl_weso.painel.routers import usuarios_router as painel_usuarios_router
from fpsl_weso.painel.routers import oficina_router as painel_oficina_router
from fpsl_weso.painel.routers import os_scan_router as painel_os_scan_router
# 🚨 PÚBLICO por link, fora do /painel: o quadro de demandas não exige conta.
from fpsl_weso.painel.routers import demandas_router
from fpsl_weso import demandas as quadro_demandas
from fpsl_weso.painel.auth import seed_admin_inicial
from fpsl_weso.services import onboarding
from fpsl_weso.services.sync_inadimplencia import loop_inadimplencia
from fpsl_weso import storage


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

app.include_router(clientes.router)
app.include_router(simcards.router)
app.include_router(rastreadores.router)
app.include_router(veiculos.router)
app.include_router(os.router)
app.include_router(onboarding.router)
app.include_router(admin.router)
app.include_router(login_router.router)
app.include_router(painel_os_router.router)
app.include_router(painel_placas_router.router)
app.include_router(painel_harmonit_hist_router.router)
app.include_router(painel_clientes_router.router)
app.include_router(painel_usuarios_router.router)
app.include_router(painel_oficina_router.router)
app.include_router(painel_os_scan_router.router)
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


@app.get("/painel/placas")
async def painel_placas_page():
    return FileResponse("frontend/placas.html")


@app.get("/painel/vinculos")
async def painel_vinculos_page():
    return FileResponse("frontend/vinculos.html")


@app.get("/painel/oficinas")
async def painel_oficinas_page():
    return FileResponse("frontend/oficinas.html")


@app.get("/painel/harmonit-historico")
async def painel_harmonit_hist_page():
    return FileResponse("frontend/harmonit_historico.html")


@app.get("/painel/os-historico")
async def painel_os_historico_page():
    return FileResponse("frontend/os_historico.html")


@app.get("/painel/config")
async def painel_config_page():
    return FileResponse("frontend/config.html")
