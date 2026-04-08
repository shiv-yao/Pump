import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.state import engine
from app.core.engine import main_loop, get_metrics

BOT_TASK = None


def ensure_engine_defaults():
    engine.running = getattr(engine, "running", True)
    engine.capital = float(getattr(engine, "capital", 5.0))
    engine.start_capital = float(getattr(engine, "start_capital", engine.capital))
    engine.peak_capital = float(getattr(engine, "peak_capital", engine.capital))

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global BOT_TASK

    ensure_engine_defaults()
    print("V61 COMPLETE LIVE ENGINE START")

    # 重點：背景執行，不阻塞 API 啟動
    BOT_TASK = asyncio.create_task(main_loop())

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
    return {
        "ok": True,
        "name": "V61 COMPLETE LIVE ENGINE",
        "mode": "REAL" if os.getenv("REAL_TRADING", "false").lower() == "true" else "PAPER",
        "running": bool(getattr(engine, "running", False)),
    }


@app.get("/health")
async def health():
    return {
        "ok": True,
        "running": bool(getattr(engine, "running", False)),
        "capital": float(getattr(engine, "capital", 0.0)),
        "open_positions": len(getattr(engine, "positions", [])),
    }


@app.get("/metrics")
async def metrics():
    try:
        return JSONResponse(content=get_metrics())
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )


@app.post("/control/start")
async def start_engine():
    engine.running = True
    return {"ok": True, "running": True}


@app.post("/control/stop")
async def stop_engine():
    engine.running = False
    return {"ok": True, "running": False}


@app.get("/positions")
async def positions():
    return {"positions": getattr(engine, "positions", [])}


@app.get("/trades")
async def trades():
    return {"trades": getattr(engine, "trade_history", [])[-50:]}


@app.get("/logs")
async def logs():
    return {"logs": getattr(engine, "logs", [])[-200:]}
