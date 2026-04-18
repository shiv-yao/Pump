import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.agent_runtime import get_session
from app.builtin_plugins import ensure_builtin_plugins
from app.command_router import execute_platform_command
from app.db import forget_installed_plugin, init_plugin_db
from app.models import ChatRequest, CommandRequest, InstallPluginRequest, PluginManualCreate
from app.plugin_manager import (
    get_store_registry,
    install_plugin_from_url,
    load_all_plugins,
    plugin_registry,
    restore_installed_plugins,
)
from app.provider_status import (
    check_claude_status,
    check_openai_status,
    check_trading_status,
)
from app.settings import ENABLE_CLAUDE, ENABLE_OPENAI, INDEX_HTML, PLUGINS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_plugin_db()
    await ensure_builtin_plugins()
    load_all_plugins()
    await restore_installed_plugins()
    load_all_plugins()

    log.info("AI Plugin Terminal started")
    yield
    log.info("AI Plugin Terminal stopped")


app = FastAPI(title="AI Plugin Terminal", version="2.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def frontend():
    if INDEX_HTML.exists():
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>index.html not found</h1>"


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "plugins": len(plugin_registry),
        "claude_enabled": ENABLE_CLAUDE,
        "openai_enabled": ENABLE_OPENAI,
    }


@app.get("/api/plugins")
async def list_plugins():
    return {
        "plugins": [
            {
                "id": pid,
                "name": info["manifest"].get("name", pid),
                "description": info["manifest"].get("description", ""),
                "version": info["manifest"].get("version", "1.0.0"),
                "enabled": info["enabled"],
                "category": info["manifest"].get("category", "utility"),
                "price": info["manifest"].get("price", 0),
                "tools": [t.get("name") for t in info["manifest"].get("tools", [])],
            }
            for pid, info in plugin_registry.items()
        ]
    }


@app.get("/api/store")
async def store():
    data = get_store_registry()
    installed = set(plugin_registry.keys())
    return {
        "plugins": [
            {**p, "installed": p.get("id") in installed}
            for p in data
            if isinstance(p, dict)
        ]
    }


@app.post("/api/plugins/install")
async def install_plugin(req: InstallPluginRequest):
    if req.manifest:
        return {"success": True, "message": "Manifest install route placeholder"}

    if req.url:
        ok = await install_plugin_from_url(req.name, req.url, remember=True)
        if ok:
            return {"success": True, "message": f"Plugin '{req.name}' installed from URL"}
        raise HTTPException(status_code=400, detail="Install failed from URL")

    raise HTTPException(status_code=400, detail="Provide manifest or url")


@app.post("/api/plugins/create")
async def create_plugin(req: PluginManualCreate):
    return {"success": True, "plugin": req.name}


@app.patch("/api/plugins/{plugin_id}/toggle")
async def toggle_plugin(plugin_id: str):
    import json
    from pathlib import Path

    if plugin_id not in plugin_registry:
        raise HTTPException(status_code=404, detail="Plugin not found")

    plugin_json = Path(plugin_registry[plugin_id]["path"]) / "plugin.json"
    with open(plugin_json, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    manifest["enabled"] = not manifest.get("enabled", True)

    with open(plugin_json, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    load_all_plugins()
    return {"success": True, "enabled": manifest["enabled"]}


@app.delete("/api/plugins/{plugin_id}")
async def remove_plugin(plugin_id: str):
    import shutil

    pdir = PLUGINS_DIR / plugin_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="Plugin not found")

    shutil.rmtree(pdir)
    forget_installed_plugin(plugin_id)
    load_all_plugins()
    return {"success": True}


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


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session = get_session(req.session_id)
    result = await session.run(req.message, req.history.copy() if req.history else [])
    return JSONResponse({
        "response": result.get("response", ""),
        "steps": result.get("steps", []),
        "provider": result.get("provider"),
        "error": result.get("error"),
        "session_id": req.session_id,
    })


@app.post("/api/command")
async def command(req: CommandRequest):
    try:
        result = await execute_platform_command(req.command)
        return JSONResponse(result)
    except Exception as e:
        log.error(f"Command error: {e}")
        return JSONResponse({"success": False, "output": f"Command error: {str(e)}"}, status_code=500)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc), "path": str(request.url.path)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
