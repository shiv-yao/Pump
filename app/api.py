import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

# ===== SAFE IMPORTS =====
router_errors = []
plugin_errors = []


def safe_import_router():
    try:
        from app.routers.dashboard_v4 import router
        return router
    except Exception as e:
        router_errors.append(f"dashboard_v4 load failed: {e}")
        return None


def safe_import_plugin_manager():
    try:
        from app.plugin_manager import (
            plugin_registry,
            load_all_plugins,
            install_plugin_from_url,
            install_plugin_from_inline_manifest,
            create_plugin_from_manifest,
            get_store_registry,
            remove_plugin,
            set_plugin_enabled,
        )
        return {
            "plugin_registry": plugin_registry,
            "load_all_plugins": load_all_plugins,
            "install_plugin_from_url": install_plugin_from_url,
            "install_plugin_from_inline_manifest": install_plugin_from_inline_manifest,
            "create_plugin_from_manifest": create_plugin_from_manifest,
            "get_store_registry": get_store_registry,
            "remove_plugin": remove_plugin,
            "set_plugin_enabled": set_plugin_enabled,
        }
    except Exception as e:
        plugin_errors.append(f"plugin_manager import failed: {e}")
        return None


def safe_import_agent_runtime():
    try:
        from app.agent_runtime import get_session
        return get_session
    except Exception as e:
        plugin_errors.append(f"agent_runtime import failed: {e}")
        return None


def safe_import_models():
    try:
        from app.models import (
            ChatRequest,
            InstallPluginRequest,
            PluginManualCreate,
        )
        return {
            "ChatRequest": ChatRequest,
            "InstallPluginRequest": InstallPluginRequest,
            "PluginManualCreate": PluginManualCreate,
        }
    except Exception as e:
        plugin_errors.append(f"models import failed: {e}")
        return None


# ===== CORE IMPORTS =====
from app.command_router import execute_platform_command
from app.provider_status import (
    check_claude_status,
    check_openai_status,
    check_trading_status,
)

# OPTIONAL SETTINGS
try:
    from app.settings import ENABLE_CLAUDE, ENABLE_OPENAI, INDEX_HTML
except Exception:
    ENABLE_CLAUDE = False
    ENABLE_OPENAI = False
    INDEX_HTML = Path("index.html")


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# safe loaded deps
plugin_manager = safe_import_plugin_manager()
get_session = safe_import_agent_runtime()
models = safe_import_models()

plugin_registry = plugin_manager["plugin_registry"] if plugin_manager else {}


# ===== LIFESPAN =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Hardened API...")

    if plugin_manager and plugin_manager.get("load_all_plugins"):
        try:
            plugin_manager["load_all_plugins"]()
            log.info(f"Plugins loaded: {len(plugin_registry)}")
        except Exception as e:
            plugin_errors.append(f"load_all_plugins failed: {e}")
            log.error(f"Plugin load failed: {e}")
    else:
        log.warning("Plugin system unavailable")

    yield
    log.info("Stopping API...")


# ===== APP =====
app = FastAPI(
    title="AI Trading System (Hardened)",
    version="5.1.0",
    lifespan=lifespan,
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

    return """
    <h1>🔥 AI Trading System Running</h1>
    <p><a href="/docs">API Docs</a></p>
    <p><a href="/debug">Debug</a></p>
    <p><a href="/api/dashboard/v4">Dashboard V4</a></p>
    """


# ===== HEALTH =====
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "claude": ENABLE_CLAUDE,
        "openai": ENABLE_OPENAI,
        "routers_loaded": dashboard_router is not None,
        "plugins_loaded": len(plugin_registry),
    }


# ===== DEBUG =====
@app.get("/debug")
async def debug():
    index_exists = False
    try:
        index_exists = Path(INDEX_HTML).exists() if INDEX_HTML else False
    except Exception:
        index_exists = False

    return {
        "router_errors": router_errors,
        "plugin_errors": plugin_errors,
        "index_exists": index_exists,
        "env": {
            "PORT": os.getenv("PORT"),
            "TRADING_API_BASE": os.getenv("TRADING_API_BASE"),
        },
        "plugins_count": len(plugin_registry),
        "sample_plugins": list(plugin_registry.keys())[:20],
    }


# ===== PROVIDERS =====
@app.get("/api/status/providers")
async def provider_status():
    return {
        "success": True,
        "providers": {
            "claude": await check_claude_status(),
            "openai": await check_openai_status(),
            "trading_api": check_trading_status(),
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


# ===== CHAT =====
if models and get_session:
    ChatRequest = models["ChatRequest"]

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        try:
            session = get_session(req.session_id)
            result = await session.run(req.message, req.history.copy() if req.history else [])
            return JSONResponse({
                "response": result.get("response", ""),
                "steps": result.get("steps", []),
                "provider": result.get("provider"),
                "error": result.get("error"),
                "session_id": req.session_id,
            })
        except Exception as e:
            log.error(f"Chat error: {e}")
            return JSONResponse(
                {"success": False, "error": str(e)},
                status_code=500,
            )


# ===== PLUGINS LIST =====
@app.get("/api/plugins")
async def list_plugins():
    try:
        return {
            "plugins": [
                {
                    "id": pid,
                    "name": info.get("manifest", {}).get("name", pid),
                    "description": info.get("manifest", {}).get("description", ""),
                    "version": info.get("manifest", {}).get("version", "1.0.0"),
                    "enabled": info.get("enabled", False),
                    "category": info.get("manifest", {}).get("category", "utility"),
                    "price": info.get("manifest", {}).get("price", 0),
                    "tools": [t.get("name") for t in info.get("manifest", {}).get("tools", [])],
                }
                for pid, info in plugin_registry.items()
            ]
        }
    except Exception as e:
        log.error(f"list_plugins failed: {e}")
        return {"plugins": []}


# ===== STORE =====
@app.get("/api/store")
async def store():
    if not plugin_manager or not plugin_manager.get("get_store_registry"):
        return {"plugins": []}

    try:
        data = plugin_manager["get_store_registry"]()
        installed = set(plugin_registry.keys())
        return {
            "plugins": [
                {**p, "installed": p.get("id") in installed}
                for p in data
                if isinstance(p, dict)
            ]
        }
    except Exception as e:
        log.error(f"store failed: {e}")
        return {"plugins": []}


# ===== PLUGIN INSTALL =====
if plugin_manager and models:
    InstallPluginRequest = models["InstallPluginRequest"]
    PluginManualCreate = models["PluginManualCreate"]

    @app.post("/api/plugins/install")
    async def install_plugin(req: InstallPluginRequest):
        if req.manifest:
            ok = plugin_manager["install_plugin_from_inline_manifest"](req.name, dict(req.manifest))
            if ok:
                return {"success": True, "message": f"Plugin '{req.name}' installed from manifest"}
            raise HTTPException(status_code=400, detail="Install failed from manifest")

        if req.url:
            ok = await plugin_manager["install_plugin_from_url"](req.name, req.url, remember=True)
            if ok:
                return {"success": True, "message": f"Plugin '{req.name}' installed from URL"}
            raise HTTPException(status_code=400, detail="Install failed from URL")

        raise HTTPException(status_code=400, detail="Provide manifest or url")

    @app.post("/api/plugins/create")
    async def create_plugin(req: PluginManualCreate):
        plugin_id = plugin_manager["create_plugin_from_manifest"](
            name=req.name,
            description=req.description,
            tools=req.tools,
            handler_code=req.handler_code,
            category=req.category or "utility",
            price=req.price or 0,
        )
        return {"success": True, "plugin": plugin_id}

    @app.patch("/api/plugins/{plugin_id}/toggle")
    async def toggle_plugin(plugin_id: str):
        if plugin_id not in plugin_registry:
            raise HTTPException(status_code=404, detail="Plugin not found")

        enabled_now = plugin_registry[plugin_id]["enabled"]
        ok = plugin_manager["set_plugin_enabled"](plugin_id, not enabled_now)
        if not ok:
            raise HTTPException(status_code=400, detail="Toggle failed")

        return {"success": True, "enabled": not enabled_now}

    @app.delete("/api/plugins/{plugin_id}")
    async def delete_plugin(plugin_id: str):
        ok = plugin_manager["remove_plugin"](plugin_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Plugin not found")
        return {"success": True}


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
