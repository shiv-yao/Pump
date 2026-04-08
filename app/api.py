# ================= V65 API (FULL CONTROL LAYER) =================

import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.state import engine
from app.engine.main import main_loop, get_metrics

app = FastAPI()

BOT_TASK = None


# ================= INIT =================

def init_engine():
    engine.running = True

    if not hasattr(engine, "positions"):
        engine.positions = []

    if not hasattr(engine, "logs"):
        engine.logs = []

    if not hasattr(engine, "trade_history"):
        engine.trade_history = []

    if not hasattr(engine, "stats"):
        engine.stats = {}

    if not hasattr(engine, "capital"):
        engine.capital = 5.0

    if not hasattr(engine, "start_capital"):
        engine.start_capital = engine.capital

    if not hasattr(engine, "peak_capital"):
        engine.peak_capital = engine.capital


# ================= START =================

@app.on_event("startup")
async def startup():

    global BOT_TASK

    init_engine()

    if BOT_TASK is None:
        BOT_TASK = asyncio.create_task(main_loop())

    print("🚀 API STARTED + ENGINE RUNNING")


# ================= BASIC =================

@app.get("/")
def root():
    return {
        "status": "ok",
        "engine": "V65 FUND BRAIN LIVE",
        "running": engine.running
    }


# ================= HEALTH =================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "running": engine.running,
        "positions": len(engine.positions),
        "capital": engine.capital
    }


# ================= METRICS =================

@app.get("/metrics")
def metrics():
    return get_metrics()


# ================= LOGS =================

@app.get("/logs")
def logs():
    return {
        "count": len(engine.logs),
        "logs": engine.logs[-100:]
    }


# ================= POSITIONS =================

@app.get("/positions")
def positions():
    return {
        "positions": engine.positions
    }


# ================= TRADES =================

@app.get("/trades")
def trades():
    return {
        "count": len(engine.trade_history),
        "trades": engine.trade_history[-50:]
    }


# ================= CONTROL =================

@app.post("/start")
async def start():

    global BOT_TASK

    if engine.running:
        return {"msg": "already running"}

    engine.running = True
    BOT_TASK = asyncio.create_task(main_loop())

    return {"msg": "started"}


@app.post("/stop")
def stop():
    engine.running = False
    return {"msg": "stopped"}


@app.post("/killswitch")
def killswitch():
    engine.running = False
    engine.positions = []
    return {"msg": "KILLED ALL"}


# ================= MANUAL TRADE =================

@app.post("/trade/buy")
async def manual_buy(mint: str, size: float = 0.01):

    from app.engine.main import buy

    fake_f = {
        "mint": mint,
        "price": 0.001,
        "_score": 0.2,
        "_mode": "manual",
        "_tier": "A",
        "source": "manual",
        "meta": {},
    }

    ok = await buy(mint, fake_f, size, "manual", forced=True)

    return {
        "success": ok
    }


@app.post("/trade/sell")
async def manual_sell(mint: str):

    from app.engine.main import sell

    for p in engine.positions:
        if p["mint"] == mint:
            ok = await sell(p, "MANUAL", 0, p.get("entry", 0))
            return {"success": ok}

    return {"error": "not found"}


# ================= RESET =================

@app.post("/reset")
def reset():

    engine.positions = []
    engine.trade_history = []
    engine.logs = []
    engine.capital = engine.start_capital

    return {"msg": "reset done"}
