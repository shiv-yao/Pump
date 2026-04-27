import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from app.agent_runtime import get_session
from app.builtin_plugins import ensure_builtin_plugins
from app.command_router import execute_platform_command
from app.db import init_plugin_db
from app.env_guard import check_env, assert_env_ready
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
from app.api.orchestrator import router as orchestrator_router
from app.api.diagnostics import router as diagnostics_router
from app.state import state
from app.runtime.original_auto import start_runtime, stop_runtime

try:
    from app.runtime.onchain_sniper import start as start_onchain_sniper
    from app.runtime.onchain_sniper import stop as stop_onchain_sniper
except Exception as e:
    start_onchain_sniper = None
    stop_onchain_sniper = None
    ONCHAIN_IMPORT_ERROR = e
else:
    ONCHAIN_IMPORT_ERROR = None

try:
    from app.runtime.auto_sell import start as start_auto_sell
    from app.runtime.auto_sell import stop as stop_auto_sell
except Exception as e:
    start_auto_sell = None
    stop_auto_sell = None
    AUTO_SELL_IMPORT_ERROR = e
else:
    AUTO_SELL_IMPORT_ERROR = None


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    env_check = check_env()
    log.info(f"ENV CHECK: {env_check}")

    if _enabled("ENV_STRICT", "false"):
        assert_env_ready()

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

    if _enabled("AUTO_TRADING", "false"):
        started = start_runtime()
        log.info(f"AUTO_TRADING enabled: original runtime started={started}")
    else:
        log.info("AUTO_TRADING disabled")

    if _enabled("ENABLE_ONCHAIN_SNIPER", "false"):
        if start_onchain_sniper:
            started = start_onchain_sniper()
            log.info(f"ONCHAIN_SNIPER enabled: started={started}")
        else:
            log.warning(f"ONCHAIN_SNIPER unavailable: {ONCHAIN_IMPORT_ERROR}")
    else:
        log.info("ONCHAIN_SNIPER disabled")

    if _enabled("ENABLE_AUTO_SELL", "true"):
        if start_auto_sell:
            started = start_auto_sell()
            log.info(f"AUTO_SELL enabled: started={started}")
        else:
            log.warning(f"AUTO_SELL unavailable: {AUTO_SELL_IMPORT_ERROR}")
    else:
        log.info("AUTO_SELL disabled")

    log.info("AI Plugin Terminal started")

    try:
        yield
    finally:
        stop_runtime()

        if stop_onchain_sniper:
            try:
                stop_onchain_sniper()
            except Exception as e:
                log.warning(f"stop_onchain_sniper failed: {e}")

        if stop_auto_sell:
            try:
                stop_auto_sell()
            except Exception as e:
                log.warning(f"stop_auto_sell failed: {e}")

        log.info("AI Plugin Terminal stopped")


app = FastAPI(
    title="AI Plugin Terminal",
    version="3.2.0-env-guard",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_v4_router)
app.include_router(trade_router)
app.include_router(orchestrator_router)
app.include_router(diagnostics_router)


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
        "auto_trading": _enabled("AUTO_TRADING", "false"),
        "onchain_sniper": _enabled("ENABLE_ONCHAIN_SNIPER", "false"),
        "onchain_import_ok": ONCHAIN_IMPORT_ERROR is None,
        "onchain_import_error": str(ONCHAIN_IMPORT_ERROR) if ONCHAIN_IMPORT_ERROR else None,
        "auto_sell": _enabled("ENABLE_AUTO_SELL", "true"),
        "auto_sell_import_ok": AUTO_SELL_IMPORT_ERROR is None,
        "auto_sell_import_error": str(AUTO_SELL_IMPORT_ERROR) if AUTO_SELL_IMPORT_ERROR else None,
        "real_trading": _enabled("REAL_TRADING", "false"),
        "manual_confirm": _enabled("MANUAL_CONFIRM", "true"),
        "running": bool(state.get("running", False)),
        "kill": bool(state.get("kill", False)),
        "claude_enabled": ENABLE_CLAUDE,
        "openai_enabled": ENABLE_OPENAI,
        "env_ok": check_env()["ok"],
    }


@app.get("/api/debug/env")
async def debug_env():
    return {
        "success": True,
        "env": check_env(),
    }


@app.get("/api/debug/net")
async def debug_network():
    results = {}

    urls = {
        "jupiter_lite": os.getenv("JUP_QUOTE_URL", "https://lite-api.jup.ag/swap/v1/quote"),
        "jupiter_backup": os.getenv("JUP_QUOTE_URL_BACKUP", "https://quote-api.jup.ag/v6/quote"),
        "solana_rpc": os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com"),
    }

    async with httpx.AsyncClient(timeout=5) as client:
        for name, url in urls.items():
            try:
                r = await client.get(url)
                results[name] = {
                    "ok": True,
                    "status_code": r.status_code,
                }
            except Exception as e:
                results[name] = {
                    "ok": False,
                    "error": str(e),
                }

    return {
        "success": True,
        "network": results,
        "env": {
            "JUP_QUOTE_URL": os.getenv("JUP_QUOTE_URL"),
            "JUP_QUOTE_URL_BACKUP": os.getenv("JUP_QUOTE_URL_BACKUP"),
            "SOLANA_RPC": os.getenv("SOLANA_RPC"),
            "SOLANA_WS": os.getenv("SOLANA_WS"),
        },
    }


@app.get("/api/state")
async def api_state():
    logs = list(state.get("logs", []) or [])
    trades = list(state.get("trade_history", []) or [])
    positions = list(state.get("positions", []) or [])

    return {
        "success": True,
        "data": {
            "running": bool(state.get("running", False)),
            "mode": state.get("mode", "PAPER"),
            "kill": bool(state.get("kill", False)),
            "pnl": float(state.get("pnl", 0.0)),
            "unrealized_pnl": float(state.get("unrealized_pnl", 0.0)),
            "positions_count": len(positions),
            "trades_count": len(trades),
            "winrate": float(state.get("winrate", 0.0)),
            "drawdown": float(state.get("drawdown", 0.0)),
            "total_exposure": float(state.get("total_exposure", 0.0)),
            "positions": positions,
            "recent_trades": trades[-20:],
            "logs": logs[-100:],
        },
        "meta": {
            "AUTO_TRADING": os.getenv("AUTO_TRADING", "false"),
            "ENABLE_ONCHAIN_SNIPER": os.getenv("ENABLE_ONCHAIN_SNIPER", "false"),
            "ENABLE_AUTO_SELL": os.getenv("ENABLE_AUTO_SELL", "true"),
            "REAL_TRADING": os.getenv("REAL_TRADING", "false"),
            "MANUAL_CONFIRM": os.getenv("MANUAL_CONFIRM", "true"),
            "SOLANA_WS": os.getenv("SOLANA_WS", ""),
            "JUP_QUOTE_URL": os.getenv("JUP_QUOTE_URL", ""),
            "JUP_QUOTE_URL_BACKUP": os.getenv("JUP_QUOTE_URL_BACKUP", ""),
        },
    }


@app.get("/api/debug/flow")
async def debug_flow():
    logs = list(state.get("logs", []) or [])
    trades = list(state.get("trade_history", []) or [])
    positions = list(state.get("positions", []) or [])

    return {
        "running": bool(state.get("running", False)),
        "mode": state.get("mode", "PAPER"),
        "kill": bool(state.get("kill", False)),
        "last_logs": logs[-50:],
        "positions": positions,
        "recent_trades": trades[-10:],
        "summary": {
            "logs_count": len(logs),
            "positions_count": len(positions),
            "trades_count": len(trades),
        },
        "env": {
            "AUTO_TRADING": os.getenv("AUTO_TRADING", "false"),
            "ENABLE_ONCHAIN_SNIPER": os.getenv("ENABLE_ONCHAIN_SNIPER", "false"),
            "ENABLE_AUTO_SELL": os.getenv("ENABLE_AUTO_SELL", "true"),
            "REAL_TRADING": os.getenv("REAL_TRADING", "false"),
            "MANUAL_CONFIRM": os.getenv("MANUAL_CONFIRM", "true"),
            "SOLANA_WS": os.getenv("SOLANA_WS", ""),
            "JUP_QUOTE_URL": os.getenv("JUP_QUOTE_URL", ""),
            "JUP_QUOTE_URL_BACKUP": os.getenv("JUP_QUOTE_URL_BACKUP", ""),
        },
    }


@app.post("/api/trading/start")
async def trading_start():
    state["kill"] = False
    state["running"] = True

    runtime_started = False
    if _enabled("AUTO_TRADING", "false"):
        runtime_started = start_runtime()

    sniper_started = False
    if _enabled("ENABLE_ONCHAIN_SNIPER", "false") and start_onchain_sniper:
        sniper_started = start_onchain_sniper()

    auto_sell_started = False
    if _enabled("ENABLE_AUTO_SELL", "true") and start_auto_sell:
        auto_sell_started = start_auto_sell()

    return {
        "success": True,
        "running": True,
        "runtime_started": runtime_started,
        "onchain_sniper_started": sniper_started,
        "auto_sell_started": auto_sell_started,
        "mode": state.get("mode", "PAPER"),
    }


@app.post("/api/trading/stop")
async def trading_stop():
    stop_runtime()

    if stop_onchain_sniper:
        stop_onchain_sniper()

    if stop_auto_sell:
        stop_auto_sell()

    state["running"] = False

    return {
        "success": True,
        "running": False,
    }


@app.post("/api/killswitch")
async def api_killswitch():
    state["kill"] = True
    state["running"] = False

    stop_runtime()

    if stop_onchain_sniper:
        stop_onchain_sniper()

    if stop_auto_sell:
        stop_auto_sell()

    return {
        "success": True,
        "kill": True,
        "running": False,
    }


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
        content={
            "success": False,
            "error": str(exc),
            "path": str(request.url.path),
        },
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
