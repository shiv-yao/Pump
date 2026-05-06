from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.health import router as health_router
from app.api.routes.positions import router as positions_router
from app.api.routes.state import router as state_router
from app.runtime.state import SYSTEM_STATE
from app.runtime.trading_loop import trading_loop

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"


@asynccontextmanager
async def lifespan(_: FastAPI):
    import asyncio

    task = asyncio.create_task(trading_loop())
    yield
    SYSTEM_STATE.running = False
    task.cancel()


app = FastAPI(title="KRONOS OMEGA ADVANCED", lifespan=lifespan)

app.include_router(health_router)
app.include_router(state_router)
app.include_router(positions_router)

if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")


@app.get("/")
async def root():
    return {"system": "KRONOS OMEGA ADVANCED", "status": "running", "dashboard_url": "/dashboard"}
