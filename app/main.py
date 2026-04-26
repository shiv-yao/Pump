import logging
import os
import asyncio
import time
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

try:
    from app.api.trade import router as trade_router
except Exception as e:
    trade_router = None
    trade_import_error = e
else:
    trade_import_error = None


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


AUTO_TRADING = os.getenv("AUTO_TRADING", "false").lower() == "true"
REAL_TRADING = os.getenv("REAL_TRADING", "false").lower() == "true"
TRADING_INTERVAL_SEC = int(os.getenv("TRADING_INTERVAL_SEC", "10"))
BOT_TASK = None


async def auto_trading_loop():
    try:
        from app.state import engine
    except Exception as e:
        engine = None
        log.warning(f"[AUTO] engine unavailable: {e}")

    if engine:
        try:
            engine.running = True
            engine.mode = "REAL" if REAL_TRADING else "PAPER"
            if hasattr(engine, "logs"):
                engine.logs.append(f"[AUTO] started mode={engine.mode}")
        except Exception as e:
            log.warning(f"[AUTO] engine init failed: {e}")

    while True:
        try:
            msg = f"[AUTO] bot tick {int(time.time())}"
            log.info(msg)

            if engine and hasattr(engine, "logs"):
                engine.logs.append(msg)

            result = None

            # 優先跑你原本的 auto_trader_v2 plugin
            try:
                from plugins.auto_trader_v2.handler import run

                maybe = run({"action": "tick"})
                if asyncio.iscoroutine(maybe):
                    result = await maybe
                else:
                    result = maybe

                log.info(f"[AUTO] auto_trader_v2 result: {result}")

                if engine and hasattr(engine, "logs"):
                    engine.logs.append(f"[AUTO] auto_trader_v2 result: {result}")

            except Exception as e:
                log.warning(f"[AUTO] auto_trader_v2 skipped: {e}")
                if engine and hasattr(engine, "logs"):
                    engine.logs.append(f"[AUTO] auto_trader_v2 skipped: {e}")

            await asyncio.sleep(TRADING_INTERVAL_SEC)

        except asyncio.CancelledError:
            log.info("[AUTO] bot loop cancelled")
            break

        except Exception as e:
            log.error(f"[AUTO ERROR] {e}")
            if engine and hasattr(engine, "logs"):
                engine.logs.append(f"[AUTO ERROR] {e}")
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global BOT_TASK

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

    if AUTO_TRADING and BOT_TASK is None:
        BOT_TASK = asyncio.create_task(auto_trading_loop())
        log.info("AUTO_TRADING enabled: bot loop started")
    else:
        log.info("AUTO_TRADING disabled")

    log.info("AI Plugin Terminal started")

    try:
        yield
    finally:
        if BOT_TASK:
            BOT_TASK.cancel()
        log.info("AI Plugin Terminal stopped")


app = FastAPI(title="AI Plugin Terminal", version="3.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_v4_router)

if trade_router:
    app.include_router(trade_router)
    log.info("Trade router loaded")
else:
    log.warning(f"Trade router unavailable: {trade_import_error}")


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
        "auto_trading": AUTO_TRADING,
        "real_trading": REAL_TRADING,
        "trade_router": trade_router is not None,
        "trade_import_error": str(trade_import_error) if trade_import_error else None,
    }


@app.get("/api/state")
async def api_state():
    try:
        from app.state import engine

        return {
            "success": True,
            "data": {
                "running": bool(getattr(engine, "running", False)),
                "mode": getattr(engine, "mode", "PAPER"),
                "pnl": float(getattr(engine, "pnl", 0.0)),
                "unrealized_pnl": float(getattr(engine, "unrealized_pnl", 0.0)),
                "positions_count": len(getattr(engine, "positions", []) or []),
                "trades_count": len(getattr(engine, "trade_history", []) or []),
                "winrate": float(getattr(engine, "winrate", 0.0)),
                "drawdown": float(getattr(engine, "drawdown", 0.0)),
                "total_exposure": float(getattr(engine, "total_exposure", 0.0)),
                "positions": getattr(engine, "positions", []) or [],
                "recent_trades": (getattr(engine, "trade_history", []) or [])[-20:],
                "logs": (getattr(engine, "logs", []) or [])[-80:],
            },
            "meta": {},
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/trading/start")
async def trading_start():
    global BOT_TASK

    try:
        from app.state import engine

        engine.running = True
        engine.mode = "REAL" if REAL_TRADING else "PAPER"
    except Exception:
        pass

    if BOT_TASK is None or BOT_TASK.done():
        BOT_TASK = asyncio.create_task(auto_trading_loop())

    return {
        "success": True,
        "running": True,
        "mode": "REAL" if REAL_TRADING else "PAPER",
    }


@app.post("/api/trading/stop")
async def trading_stop():
    global BOT_TASK

    try:
        from app.state import engine

        engine.running = False
        if hasattr(engine, "logs"):
            engine.logs.append("[AUTO] stopped by API")
    except Exception:
        pass

    if BOT_TASK:
        BOT_TASK.cancel()
        BOT_TASK = None

    return {"success": True, "running": False}


@app.post("/api/killswitch")
async def killswitch():
    global BOT_TASK

    try:
        from app.state import engine

        engine.running = False
        engine.killswitch = True
        if hasattr(engine, "logs"):
            engine.logs.append("[KILLSWITCH] activated")
    except Exception:
        pass

    if BOT_TASK:
        BOT_TASK.cancel()
        BOT_TASK = None

    return {"success": True, "killswitch": True}


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
        },
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session = get_session(req.session_id)
    result = await session.run(req.message, req.history.copy() if req.history else [])
    return JSONResponse(
        {
            "response": result.get("response", ""),
            "steps": result.get("steps", []),
            "provider": result.get("provider"),
            "error": result.get("error"),
            "session_id": req.session_id,
        }
    )


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
