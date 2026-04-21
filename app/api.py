import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

# ===== SAFE IMPORTS =====
router_errors = []

def safe_import_router():
    try:
        from app.routers.dashboard_v4 import router
        return router
    except Exception as e:
        router_errors.append(f"dashboard_v4 load failed: {e}")
        return None


# ===== OPTIONAL IMPORTS =====
def safe_import_plugins():
    try:
        from app.plugin_manager import load_all_plugins, plugin_registry
        return load_all_plugins, plugin_registry
    except Exception as e:
        return None, {}

# ===== CORE IMPORTS =====
from app.agent_runtime import get_session
from app.command_router import execute_platform_command
from app.provider_status import (
    check_claude_status,
    check_openai_status,
    check_trading_status,
)

# OPTIONAL SETTINGS
try:
    from app.settings import ENABLE_CLAUDE, ENABLE_OPENAI, INDEX_HTML
except:
    ENABLE_CLAUDE = False
    ENABLE_OPENAI = False
    INDEX_HTML = Path("index.html")


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ===== LIFESPAN =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Hardened API...")

    # Plugin loading safe
    load_plugins, plugin_registry = safe_import_plugins()

    if load_plugins:
        try:
            load_plugins()
            log.info(f"Plugins loaded: {len(plugin_registry)}")
        except Exception as e:
            log.error(f"Plugin load failed: {e}")
    else:
        log.warning("Plugin system unavailable")

    yield
    log.info("Stopping API...")


# ===== APP =====
app = FastAPI(
    title="AI Trading System (Hardened)",
    version="5.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== ROUTER SAFE LOAD =====
dashboard_router = safe_import_router()
if dashboard_router:
    app.include_router(dashboard_router)
    log.info("dashboard_v4 router loaded")
else:
    log.warning("dashboard_v4 router NOT loaded")


# ===== FRONTEND =====
@app.get("/", response_class=HTMLResponse)
async def frontend():
    try:
        if INDEX_HTML and Path(INDEX_HTML).exists():
            return Path(INDEX_HTML).read_text(encoding="utf-8")
    except Exception as e:
        log.error(f"index load error: {e}")

    # 永遠 fallback
    return """
    <h1>🔥 AI Trading System Running</h1>
    <p><a href="/docs">API Docs</a></p>
    <p><a href="/debug">Debug</a></p>
    """


# ===== HEALTH =====
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "claude": ENABLE_CLAUDE,
        "openai": ENABLE_OPENAI,
        "routers_loaded": dashboard_router is not None,
    }


# ===== DEBUG =====
@app.get("/debug")
async def debug():
    return {
        "router_errors": router_errors,
        "index_exists": Path(INDEX_HTML).exists() if INDEX_HTML else False,
        "env": {
            "PORT": os.getenv("PORT"),
            "TRADING_API_BASE": os.getenv("TRADING_API_BASE"),
        }
    }


# ===== COMMAND =====
@app.post("/api/command")
async def command(req: dict):
    try:
        result = await execute_platform_command(req.get("command", ""))
        return JSONResponse(result)
    except Exception as e:
        log.error(f"Command error: {e}")
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


# ===== PROVIDERS =====
@app.get("/api/status/providers")
async def provider_status():
    return {
        "claude": await check_claude_status(),
        "openai": await check_openai_status(),
        "trading_api": check_trading_status(),
    }


# ===== ENV DOWNLOAD =====
@app.get("/api/env/latest")
async def download_latest_env():
    env_path = Path("latest.env")

    if not env_path.exists():
        raise HTTPException(status_code=404, detail="latest.env not found")

    return FileResponse(
        path=str(env_path),
        media_type="text/plain",
        filename="latest.env"
    )


# ===== GLOBAL ERROR =====
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc),
            "path": str(request.url.path)
        },
    )


# ===== RUN LOCAL =====
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
