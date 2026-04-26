import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from app.agent_runtime import get_session
from app.builtin_plugins import ensure_builtin_plugins
from app.command_router import execute_platform_command
from app.db import init_plugin_db
from app.models import (
    ChatRequest,
    CommandRequest,
    InstallPluginRequest,
    PluginManualCreate,
)
from app.plugin_manager import (
    create_plugin_from_manifest,
    get_store_registry,
    install_plugin_from_inline_manifest,
    install_plugin_from_url,
    load_all_plugins,
    plugin_registry,
    remove_plugin,
    restore_installed_plugins,
    set_plugin_enabled,
)
from app.provider_status import (
    check_claude_status,
    check_openai_status,
    check_trading_status,
)
from app.settings import ENABLE_CLAUDE, ENABLE_OPENAI, INDEX_HTML
from app.routers.dashboard_v4 import router as dashboard_v4_router
from app.api.trade import router as trade_router
from app.state import state
from app.runtime.original_auto import start_runtime, stop_runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

from app.api.orchestrator import router as orchestrator_router
app.include_router(orchestrator_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_ok = True

    try:
        init_plugin_db()
        log.info("Plugin DB initialized")
    except Exception as e:
        db_ok = False
        log.warning(f"Plugin DB init skipped: {e}")

    try:
        await ensure_builtin_plugins()
        log.info("Built-in plugins ensured")
    except Exception as e:
        log.error(f"ensure_builtin_plugins failed: {e}")

    try:
        load_all_plugins()
        log.info(f"Loaded local plugins: {len(plugin_registry)}")
    except Exception as e:
        log.error(f"load_all_plugins failed: {e}")

    if db_ok:
        try:
            await restore_installed_plugins()
            load_all_plugins()
            log.info(f"Restored plugins loaded: {len(plugin_registry)}")
        except Exception as e:
            log.warning(f"restore_installed_plugins skipped: {e}")
    else:
        log.warning("DB unavailable, skipping installed plugin restore")

    if os.getenv("AUTO_TRADING", "false").lower() == "true":
        started = start_runtime()
        log.info(f"AUTO_TRADING enabled: original runtime started={started}")
    else:
        log.info("AUTO_TRADING disabled")

    log.info("AI Plugin Terminal started")
    try:
        yield
    finally:
        stop_runtime()
        log.info("AI Plugin Terminal stopped")


app = FastAPI(title="AI Plugin Terminal", version="3.2.0-original-core-real-market", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_v4_router)
app.include_router(trade_router)


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
        "auto_trading": os.getenv("AUTO_TRADING", "false").lower() == "true",
        "real_trading": os.getenv("REAL_TRADING", "false").lower() == "true",
        "manual_confirm": os.getenv("MANUAL_CONFIRM", "true").lower() == "true",
        "running": bool(state.get("running", False)),
    }


@app.get("/api/state")
async def api_state():
    return {
        "success": True,
        "data": {
            "running": bool(state.get("running", False)),
            "mode": state.get("mode", "PAPER"),
            "pnl": float(state.get("pnl", 0.0)),
            "unrealized_pnl": float(state.get("unrealized_pnl", 0.0)),
            "positions_count": len(state.get("positions", []) or []),
            "trades_count": len(state.get("trade_history", []) or []),
            "winrate": float(state.get("winrate", 0.0)),
            "drawdown": float(state.get("drawdown", 0.0)),
            "total_exposure": float(state.get("total_exposure", 0.0)),
            "positions": state.get("positions", []) or [],
            "recent_trades": (state.get("trade_history", []) or [])[-20:],
            "logs": (state.get("logs", []) or [])[-100:],
        },
        "meta": {
            "auto_trading_env": os.getenv("AUTO_TRADING", "false"),
            "real_trading_env": os.getenv("REAL_TRADING", "false"),
            "manual_confirm_env": os.getenv("MANUAL_CONFIRM", "true"),
            "enable_pump_sniper": os.getenv("ENABLE_PUMP_SNIPER", "true"),
        },
    }


@app.post("/api/trading/start")
async def trading_start():
    state["kill"] = False
    state["running"] = True
    started = start_runtime()
    return {"success": True, "running": True, "started_new_task": started, "mode": state.get("mode", "PAPER")}


@app.post("/api/trading/stop")
async def trading_stop():
    stop_runtime()
    return {"success": True, "running": False}


@app.post("/api/killswitch")
async def api_killswitch():
    state["kill"] = True
    stop_runtime()
    return {"success": True, "kill": True, "running": False}


@app.post("/api/killswitch/reset")
async def api_killswitch_reset():
    state["kill"] = False
    return {"success": True, "kill": False}


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
        ok = install_plugin_from_inline_manifest(req.name, dict(req.manifest))
        if ok:
            return {"success": True, "message": f"Plugin '{req.name}' installed from manifest"}
        raise HTTPException(status_code=400, detail="Install failed from manifest")

    if req.url:
        ok = await install_plugin_from_url(req.name, req.url, remember=True)
        if ok:
            return {"success": True, "message": f"Plugin '{req.name}' installed from URL"}
        raise HTTPException(status_code=400, detail="Install failed from URL")

    raise HTTPException(status_code=400, detail="Provide manifest or url")


@app.post("/api/plugins/create")
async def create_plugin(req: PluginManualCreate):
    plugin_id = create_plugin_from_manifest(
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
    ok = set_plugin_enabled(plugin_id, not enabled_now)
    if not ok:
        raise HTTPException(status_code=400, detail="Toggle failed")

    return {"success": True, "enabled": not enabled_now}


@app.delete("/api/plugins/{plugin_id}")
async def delete_plugin(plugin_id: str):
    ok = remove_plugin(plugin_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Plugin not found")
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
        return JSONResponse(
            {"success": False, "output": f"Command error: {str(e)}"},
            status_code=500,
        )


@app.get("/api/env/latest")
async def download_latest_env():
    env_path = Path("latest.env")

    if not env_path.exists():
        raise HTTPException(status_code=404, detail="latest.env not found")

    return FileResponse(
        path=str(env_path),
        media_type="text/plain",
        filename="latest.env",
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc), "path": str(request.url.path)},
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)

@app.get("/api/debug/flow")
async def debug_flow():
    try:
        from app.state import engine

        logs = list(getattr(engine, "logs", []))
        trades = list(getattr(engine, "trade_history", []))
        positions = list(getattr(engine, "positions", []))

        return {
            "running": bool(getattr(engine, "running", False)),
            "mode": getattr(engine, "mode", "PAPER"),
            "last_logs": logs[-20:],
            "positions": positions,
            "recent_trades": trades[-10:],
            "summary": {
                "logs_count": len(logs),
                "positions_count": len(positions),
                "trades_count": len(trades),
            },
        }
    except Exception as e:
        return {"error": str(e)}
