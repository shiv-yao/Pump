# app/api.py
import os
import asyncio
import importlib
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.state import engine


# =========================================================
# ENGINE IMPORT RESOLVER
# Compatible with:
# - app.engine
# - app.engine.main
# - app.core.engine
# - app.engine.v62
# - older/future layouts
# =========================================================

ENGINE_TASK: Optional[asyncio.Task] = None
ENGINE_MAIN_LOOP = None
ENGINE_GET_METRICS = None


def _safe_get_metrics_fallback() -> Dict[str, Any]:
    positions = getattr(engine, "positions", []) or []
    trades = getattr(engine, "trade_history", []) or []
    logs = getattr(engine, "logs", []) or []
    stats = getattr(engine, "stats", {}) or {}

    capital = float(getattr(engine, "capital", 0.0))
    start_capital = float(getattr(engine, "start_capital", capital))
    peak_capital = float(getattr(engine, "peak_capital", capital))

    total_return = capital - start_capital
    return_pct = (total_return / start_capital) if start_capital > 0 else 0.0
    drawdown = ((peak_capital - capital) / peak_capital) if peak_capital > 0 else 0.0

    return {
        "summary": {
            "capital": capital,
            "start_capital": start_capital,
            "peak_capital": peak_capital,
            "equity_gain": total_return,
            "return_pct": return_pct,
            "drawdown": drawdown,
            "running": bool(getattr(engine, "running", False)),
            "mode": "REAL" if str(os.getenv("REAL_TRADING", "false")).lower() == "true" else "PAPER",
        },
        "performance": {
            "trades": len(trades),
            "wins": int(stats.get("wins", 0)),
            "losses": int(stats.get("losses", 0)),
            "win_rate": (
                int(stats.get("wins", 0)) / len(trades) if len(trades) > 0 else 0.0
            ),
            "profit_factor": 0.0,
            "total_return": total_return,
        },
        "trading": {
            "signals": int(stats.get("signals", 0)),
            "executed": int(stats.get("executed", 0)),
            "rejected": int(stats.get("rejected", 0)),
            "errors": int(stats.get("errors", 0)),
            "open_positions": len(positions),
            "open_exposure": float(stats.get("open_exposure", 0.0)),
            "forced_trades": int(stats.get("forced_trades", 0)),
            "no_trade_cycles": int(getattr(engine, "no_trade_cycles", 0)),
        },
        "positions": positions,
        "recent_trades": trades[-20:],
        "logs": logs[-120:],
    }


def _resolve_engine_module():
    global ENGINE_MAIN_LOOP, ENGINE_GET_METRICS

    candidates = [
        "app.engine",
        "app.engine.main",
        "app.core.engine",
        "app.engine.v62",
        "app.engine.v61",
        "app.engine.v60",
    ]

    for mod_name in candidates:
        try:
            mod = importlib.import_module(mod_name)

            main_loop = getattr(mod, "main_loop", None)
            get_metrics = getattr(mod, "get_metrics", None)

            if callable(main_loop):
                ENGINE_MAIN_LOOP = main_loop
                ENGINE_GET_METRICS = get_metrics if callable(get_metrics) else _safe_get_metrics_fallback
                print(f"✅ ENGINE LOADED: {mod_name}")
                return mod
        except Exception as e:
            print(f"ENGINE_IMPORT_SKIP {mod_name}: {e}")

    ENGINE_MAIN_LOOP = None
    ENGINE_GET_METRICS = _safe_get_metrics_fallback
    print("⚠️ NO REAL ENGINE MODULE FOUND; USING FALLBACK METRICS")
    return None


# =========================================================
# ENGINE STATE INIT
# =========================================================

def ensure_engine():
    engine.positions = getattr(engine, "positions", [])
    engine.trade_history = getattr(engine, "trade_history", [])
    engine.logs = getattr(engine, "logs", [])

    engine.capital = float(getattr(engine, "capital", 5.0))
    engine.start_capital = float(getattr(engine, "start_capital", engine.capital))
    engine.peak_capital = float(getattr(engine, "peak_capital", engine.capital))

    engine.running = bool(getattr(engine, "running", True))
    engine.no_trade_cycles = int(getattr(engine, "no_trade_cycles", 0))

    engine.last_signal = getattr(engine, "last_signal", "")
    engine.last_trade = getattr(engine, "last_trade", "")

    engine.stats = getattr(engine, "stats", {})
    engine.stats.setdefault("signals", 0)
    engine.stats.setdefault("executed", 0)
    engine.stats.setdefault("rejected", 0)
    engine.stats.setdefault("errors", 0)
    engine.stats.setdefault("open_positions", 0)
    engine.stats.setdefault("open_exposure", 0.0)
    engine.stats.setdefault("trades", 0)
    engine.stats.setdefault("wins", 0)
    engine.stats.setdefault("losses", 0)
    engine.stats.setdefault("forced_trades", 0)


def push_log(msg: str):
    print(msg)
    engine.logs.append(str(msg))
    engine.logs = engine.logs[-1000:]


# =========================================================
# V63 / V64 BOOT
# =========================================================

async def _engine_runner():
    """
    V63 = real trading loop
    V64 = AI fund brain loop
    This wrapper keeps Railway alive and captures crash logs.
    """
    ensure_engine()
    push_log("🚀 V63/V64 COMPLETE LIVE ENGINE START")

    if ENGINE_MAIN_LOOP is None:
        push_log("❌ ENGINE_MAIN_LOOP missing")
        return

    try:
        await ENGINE_MAIN_LOOP()
    except asyncio.CancelledError:
        push_log("🛑 ENGINE TASK CANCELLED")
        raise
    except Exception as e:
        engine.stats["errors"] = int(engine.stats.get("errors", 0)) + 1
        push_log(f"❌ ENGINE CRASH: {e}")
        raise


async def start_engine_task():
    global ENGINE_TASK

    if ENGINE_TASK and not ENGINE_TASK.done():
        return False

    engine.running = True
    ENGINE_TASK = asyncio.create_task(_engine_runner())
    push_log("🔥 ENGINE TASK STARTED")
    return True


async def stop_engine_task():
    global ENGINE_TASK

    engine.running = False

    if ENGINE_TASK and not ENGINE_TASK.done():
        ENGINE_TASK.cancel()
        try:
            await ENGINE_TASK
        except Exception:
            pass

    push_log("🛑 ENGINE TASK STOPPED")
    return True


# =========================================================
# FASTAPI LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_engine()
    _resolve_engine_module()

    auto_start = str(os.getenv("AUTO_START_ENGINE", "true")).lower() == "true"
    if auto_start:
        await start_engine_task()

    yield

    await stop_engine_task()


app = FastAPI(
    title="V63/V64 Pump Trading API",
    version="63.64.0",
    lifespan=lifespan,
)


# =========================================================
# ROOT / HEALTH
# =========================================================

@app.get("/")
async def root():
    return {
        "status": "ok",
        "name": "V63/V64 COMPLETE LIVE ENGINE",
        "real_trading": str(os.getenv("REAL_TRADING", "false")).lower() == "true",
        "engine_running": bool(getattr(engine, "running", False)),
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "engine_running": bool(getattr(engine, "running", False)),
        "task_alive": bool(ENGINE_TASK and not ENGINE_TASK.done()),
        "real_trading": str(os.getenv("REAL_TRADING", "false")).lower() == "true",
        "capital": float(getattr(engine, "capital", 0.0)),
    }


# =========================================================
# METRICS / LOGS
# =========================================================

@app.get("/metrics")
async def metrics():
    try:
        data = ENGINE_GET_METRICS() if callable(ENGINE_GET_METRICS) else _safe_get_metrics_fallback()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"metrics_error: {e}")


@app.get("/logs")
async def logs(limit: int = 200):
    xs = getattr(engine, "logs", []) or []
    return {
        "count": min(limit, len(xs)),
        "logs": xs[-limit:],
    }


# =========================================================
# CONTROL
# =========================================================

@app.post("/start")
async def start():
    started = await start_engine_task()
    return {
        "ok": True,
        "started": started,
        "engine_running": bool(getattr(engine, "running", False)),
    }


@app.post("/stop")
async def stop():
    await stop_engine_task()
    return {
        "ok": True,
        "engine_running": bool(getattr(engine, "running", False)),
    }


@app.post("/killswitch")
async def killswitch():
    await stop_engine_task()
    return {
        "ok": True,
        "killed": True,
        "engine_running": False,
    }


# =========================================================
# STATUS DATA
# =========================================================

@app.get("/positions")
async def positions():
    return {
        "count": len(getattr(engine, "positions", []) or []),
        "positions": getattr(engine, "positions", []) or [],
    }


@app.get("/trades")
async def trades(limit: int = 50):
    xs = getattr(engine, "trade_history", []) or []
    return {
        "count": min(limit, len(xs)),
        "trades": xs[-limit:],
    }


@app.get("/signal")
async def signal():
    return {
        "last_signal": getattr(engine, "last_signal", ""),
        "last_trade": getattr(engine, "last_trade", ""),
        "stats": getattr(engine, "stats", {}) or {},
    }


@app.get("/config")
async def config():
    return {
        "REAL_TRADING": str(os.getenv("REAL_TRADING", "false")).lower() == "true",
        "AUTO_START_ENGINE": str(os.getenv("AUTO_START_ENGINE", "true")).lower() == "true",
        "MAX_POSITIONS": os.getenv("MAX_POSITIONS"),
        "MAX_EXPOSURE": os.getenv("MAX_EXPOSURE"),
        "MAX_POSITION_SIZE": os.getenv("MAX_POSITION_SIZE"),
        "TAKE_PROFIT": os.getenv("TAKE_PROFIT"),
        "STOP_LOSS": os.getenv("STOP_LOSS"),
        "ENTRY_THRESHOLD": os.getenv("ENTRY_THRESHOLD"),
        "SOLANA_RPC_HTTP": os.getenv("SOLANA_RPC_HTTP"),
        "SOLANA_RPC_WSS": os.getenv("SOLANA_RPC_WSS"),
        "JUP_BASE_API": os.getenv("JUP_BASE_API"),
        "USE_JITO": os.getenv("USE_JITO"),
    }


# =========================================================
# MANUAL V63 REAL TRADE ENDPOINTS
# =========================================================

@app.post("/trade/buy")
async def trade_buy(payload: Dict[str, Any]):
    """
    Manual buy endpoint for V63 real trading.
    Expected payload:
    {
        "mint": "...",
        "amount_sol": 0.02
    }
    """
    mint = str(payload.get("mint", "")).strip()
    amount_sol = float(payload.get("amount_sol", 0.0))

    if not mint:
        raise HTTPException(status_code=400, detail="mint_required")
    if amount_sol <= 0:
        raise HTTPException(status_code=400, detail="amount_sol_must_be_positive")

    try:
        mod = _resolve_engine_module()
        if mod is None:
            raise HTTPException(status_code=500, detail="engine_not_loaded")

        manual_buy = getattr(mod, "manual_buy", None)
        if not callable(manual_buy):
            raise HTTPException(status_code=500, detail="manual_buy_not_implemented_in_engine")

        res = await manual_buy(mint, amount_sol)
        return {"ok": True, "result": res}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"manual_buy_error: {e}")


@app.post("/trade/sell")
async def trade_sell(payload: Dict[str, Any]):
    """
    Manual sell endpoint for V63 real trading.
    Expected payload:
    {
        "mint": "...",
        "pct": 1.0
    }
    """
    mint = str(payload.get("mint", "")).strip()
    pct = float(payload.get("pct", 1.0))

    if not mint:
        raise HTTPException(status_code=400, detail="mint_required")
    if pct <= 0 or pct > 1:
        raise HTTPException(status_code=400, detail="pct_must_be_between_0_and_1")

    try:
        mod = _resolve_engine_module()
        if mod is None:
            raise HTTPException(status_code=500, detail="engine_not_loaded")

        manual_sell = getattr(mod, "manual_sell", None)
        if not callable(manual_sell):
            raise HTTPException(status_code=500, detail="manual_sell_not_implemented_in_engine")

        res = await manual_sell(mint, pct)
        return {"ok": True, "result": res}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"manual_sell_error: {e}")


# =========================================================
# V64 AI FUND BRAIN CONTROL
# =========================================================

@app.get("/fund/brain")
async def fund_brain():
    """
    Returns allocator / brain snapshot if engine exposes it.
    """
    try:
        mod = _resolve_engine_module()
        if mod is None:
            return {
                "ok": True,
                "brain": {},
                "note": "engine_not_loaded",
            }

        getter = getattr(mod, "get_fund_brain", None)
        if callable(getter):
            data = getter()
            return {"ok": True, "brain": data}

        return {
            "ok": True,
            "brain": {
                "allocator": getattr(engine, "engine_allocator", {}),
                "engine_stats": getattr(engine, "engine_stats", {}),
            },
            "note": "fallback_brain_snapshot",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fund_brain_error: {e}")


@app.post("/fund/rebalance")
async def fund_rebalance():
    """
    Triggers rebalance if V64 engine implements it.
    """
    try:
        mod = _resolve_engine_module()
        if mod is None:
            raise HTTPException(status_code=500, detail="engine_not_loaded")

        fn = getattr(mod, "manual_rebalance", None)
        if not callable(fn):
            raise HTTPException(status_code=500, detail="manual_rebalance_not_implemented")

        res = await fn()
        return {"ok": True, "result": res}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rebalance_error: {e}")


# =========================================================
# DEBUG
# =========================================================

@app.get("/debug/state")
async def debug_state():
    return {
        "engine_running": bool(getattr(engine, "running", False)),
        "task_alive": bool(ENGINE_TASK and not ENGINE_TASK.done()),
        "capital": float(getattr(engine, "capital", 0.0)),
        "start_capital": float(getattr(engine, "start_capital", 0.0)),
        "positions": len(getattr(engine, "positions", []) or []),
        "trades": len(getattr(engine, "trade_history", []) or []),
        "stats": getattr(engine, "stats", {}) or {},
        "last_signal": getattr(engine, "last_signal", ""),
        "last_trade": getattr(engine, "last_trade", ""),
    }
