import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.api.routes.health import router as health_router
from app.api.routes.positions import router as positions_router
from app.api.routes.state import router as state_router
from app.runtime.state import SYSTEM_STATE
from app.runtime.trading_loop import trading_loop

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
DASHBOARD_INDEX = DASHBOARD_DIR / "index.html"

FALLBACK_HTML = """
<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>KRONOS OMEGA</title></head><body style='background:#070b14;color:#fff;font-family:sans-serif;padding:24px'>
<h1>KRONOS OMEGA</h1><p>Dashboard fallback page.</p>
<p><a style='color:#60a5fa' href='/api/state'>/api/state</a> | <a style='color:#60a5fa' href='/api/positions'>/api/positions</a> | <a style='color:#60a5fa' href='/health'>/health</a></p>
</body></html>
"""


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


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    if DASHBOARD_INDEX.exists():
        return FileResponse(DASHBOARD_INDEX)
    return HTMLResponse(FALLBACK_HTML)


@app.get("/api/root")
async def api_root():
    return {
        "system": "KRONOS OMEGA ADVANCED",
        "status": "running",
        "dashboard_url": "/dashboard",
        "dashboard_index_url": "/dashboard/index.html",
    }


@app.get("/version")
async def version():
    return {
        "railway_git_commit_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA"),
        "railway_git_branch": os.getenv("RAILWAY_GIT_BRANCH"),
        "railway_environment": os.getenv("RAILWAY_ENVIRONMENT"),
        "service": "Pump",
    }


@app.get("/dashboard", include_in_schema=False)
async def dashboard_home():
    return RedirectResponse(url="/dashboard/index.html")


@app.get("/dashboard/{file_path:path}", include_in_schema=False)
async def dashboard_files(file_path: str):
    normalized = (file_path or "index.html").lstrip("/")
    target = (DASHBOARD_DIR / normalized).resolve()

    if (
        DASHBOARD_DIR.exists()
        and str(target).startswith(str(DASHBOARD_DIR.resolve()))
        and target.exists()
        and target.is_file()
    ):
        return FileResponse(target)

    if DASHBOARD_INDEX.exists():
        return FileResponse(DASHBOARD_INDEX)
    return HTMLResponse(FALLBACK_HTML)
