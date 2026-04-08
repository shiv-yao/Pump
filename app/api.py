import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.state import engine
from app.core.engine import main_loop, get_metrics

BOT_TASK = None


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def ensure_engine_defaults():
    engine.running = getattr(engine, "running", True)

    engine.capital = _safe_float(getattr(engine, "capital", 5.0), 5.0)
    engine.start_capital = _safe_float(
        getattr(engine, "start_capital", engine.capital),
        engine.capital,
    )
    engine.peak_capital = _safe_float(
        getattr(engine, "peak_capital", engine.capital),
        engine.capital,
    )

    engine.positions = getattr(engine, "positions", [])
    engine.trade_history = getattr(engine, "trade_history", [])
    engine.logs = getattr(engine, "logs", [])
    engine.last_signal = getattr(engine, "last_signal", "")
    engine.last_trade = getattr(engine, "last_trade", "")
    engine.no_trade_cycles = int(getattr(engine, "no_trade_cycles", 0))

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


def append_log(msg: str):
    print(msg)
    engine.logs.append(str(msg))
    engine.logs = engine.logs[-1000:]


async def _engine_runner():
    try:
        await main_loop()
    except asyncio.CancelledError:
        append_log("ENGINE_TASK_CANCELLED")
        raise
    except Exception as e:
        engine.stats["errors"] = int(engine.stats.get("errors", 0)) + 1
        append_log(f"ENGINE_TASK_CRASH {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global BOT_TASK

    ensure_engine_defaults()
    append_log("V61 COMPLETE LIVE ENGINE START")

    if BOT_TASK is None or BOT_TASK.done():
        BOT_TASK = asyncio.create_task(_engine_runner())

    try:
        yield
    finally:
        if BOT_TASK and not BOT_TASK.done():
            BOT_TASK.cancel()
            try:
                await BOT_TASK
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Pump Trading API",
    version="61.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    ensure_engine_defaults()
    return {
        "ok": True,
        "name": "V61 COMPLETE LIVE ENGINE",
        "mode": "REAL" if os.getenv("REAL_TRADING", "false").lower() == "true" else "PAPER",
        "running": bool(getattr(engine, "running", False)),
        "capital": _safe_float(getattr(engine, "capital", 0.0)),
        "open_positions": len(getattr(engine, "positions", [])),
    }


@app.get("/health")
async def health():
    ensure_engine_defaults()
    return {
        "ok": True,
        "running": bool(getattr(engine, "running", False)),
        "capital": _safe_float(getattr(engine, "capital", 0.0)),
        "start_capital": _safe_float(getattr(engine, "start_capital", 0.0)),
        "peak_capital": _safe_float(getattr(engine, "peak_capital", 0.0)),
        "open_positions": len(getattr(engine, "positions", [])),
        "task_alive": bool(BOT_TASK and not BOT_TASK.done()),
    }


@app.get("/metrics")
async def metrics():
    ensure_engine_defaults()
    try:
        data = get_metrics()
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(e),
                "running": bool(getattr(engine, "running", False)),
            },
        )


@app.get("/positions")
async def positions():
    ensure_engine_defaults()
    return {
        "ok": True,
        "count": len(getattr(engine, "positions", [])),
        "positions": getattr(engine, "positions", []),
    }


@app.get("/trades")
async def trades(limit: int = 50):
    ensure_engine_defaults()
    limit = max(1, min(limit, 500))
    rows = getattr(engine, "trade_history", [])
    return {
        "ok": True,
        "count": min(len(rows), limit),
        "trades": rows[-limit:],
    }


@app.get("/logs")
async def logs(limit: int = 200):
    ensure_engine_defaults()
    limit = max(1, min(limit, 1000))
    rows = getattr(engine, "logs", [])
    return {
        "ok": True,
        "count": min(len(rows), limit),
        "logs": rows[-limit:],
    }


@app.post("/control/start")
async def control_start():
    global BOT_TASK

    ensure_engine_defaults()
    engine.running = True

    if BOT_TASK is None or BOT_TASK.done():
        append_log("ENGINE_RESTART_REQUEST")
        BOT_TASK = asyncio.create_task(_engine_runner())

    return {
        "ok": True,
        "running": True,
        "task_alive": bool(BOT_TASK and not BOT_TASK.done()),
    }


@app.post("/control/stop")
async def control_stop():
    ensure_engine_defaults()
    engine.running = False
    append_log("ENGINE_STOP_REQUEST")
    return {
        "ok": True,
        "running": False,
    }


@app.post("/control/restart")
async def control_restart():
    global BOT_TASK

    ensure_engine_defaults()
    engine.running = False
    append_log("ENGINE_RESTART_BEGIN")

    if BOT_TASK and not BOT_TASK.done():
        BOT_TASK.cancel()
        try:
            await BOT_TASK
        except asyncio.CancelledError:
            pass

    engine.running = True
    BOT_TASK = asyncio.create_task(_engine_runner())

    return {
        "ok": True,
        "running": True,
        "task_alive": True,
    }


@app.get("/state")
async def state():
    ensure_engine_defaults()
    return {
        "ok": True,
        "running": bool(getattr(engine, "running", False)),
        "capital": _safe_float(getattr(engine, "capital", 0.0)),
        "start_capital": _safe_float(getattr(engine, "start_capital", 0.0)),
        "peak_capital": _safe_float(getattr(engine, "peak_capital", 0.0)),
        "last_signal": getattr(engine, "last_signal", ""),
        "last_trade": getattr(engine, "last_trade", ""),
        "no_trade_cycles": int(getattr(engine, "no_trade_cycles", 0)),
        "stats": getattr(engine, "stats", {}),
        "task_alive": bool(BOT_TASK and not BOT_TASK.done()),
    }
