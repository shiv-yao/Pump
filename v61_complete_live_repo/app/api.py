import asyncio
from fastapi import FastAPI
from pydantic import BaseModel

from app.state import engine
from app.engine.v61_engine import main_loop, get_metrics, buy, get_price
from app.engine.v61_engine import ensure_engine

BOT_TASK = None
app = FastAPI(title="V61 Trading API")

class ManualTrade(BaseModel):
    mint: str
    size_sol: float
    mode: str = "manual"

@app.on_event("startup")
async def _startup():
    global BOT_TASK
    ensure_engine()
    if BOT_TASK is None or BOT_TASK.done():
        BOT_TASK = asyncio.create_task(main_loop())

@app.get("/health")
async def health():
    return {"ok": True, "running": bool(engine.running), "capital": engine.capital}

@app.get("/metrics")
async def metrics():
    return get_metrics()

@app.get("/positions")
async def positions():
    return engine.positions

@app.get("/orders")
async def orders():
    return engine.trade_history[-50:]

@app.post("/start")
async def start():
    global BOT_TASK
    engine.running = True
    if BOT_TASK is None or BOT_TASK.done():
        BOT_TASK = asyncio.create_task(main_loop())
    return {"ok": True}

@app.post("/killswitch")
async def killswitch():
    engine.running = False
    return {"ok": True, "running": engine.running}

@app.post("/trade/buy")
async def trade_buy(req: ManualTrade):
    f = {
        "mint": req.mint,
        "price": await get_price(req.mint) or 0.0,
        "_score": 0.2,
        "_tier": "A",
        "_mode": req.mode,
        "source": "manual",
        "meta": {},
        "liq": 999999,
        "smart": 0.0,
        "breakout": 0.0,
        "momentum": 0.0,
        "wallet_count": 0,
        "price_source": "manual",
    }
    ok = await buy(req.mint, f, req.size_sol, req.mode, forced=True)
    return {"ok": ok}
