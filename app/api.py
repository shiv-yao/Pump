# app/api.py
import asyncio
import time
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.state import engine

BOT_TASK = None


def init_engine():
    engine.running = True
    engine.start_time = time.time()

    if not hasattr(engine, "positions"):
        engine.positions = []

    if not hasattr(engine, "logs"):
        engine.logs = []

    if not hasattr(engine, "trade_history"):
        engine.trade_history = []

    if not hasattr(engine, "stats"):
        engine.stats = {
            "signals": 0,
            "buys": 0,
            "sells": 0,
            "errors": 0,
        }

    if not hasattr(engine, "last_trade"):
        engine.last_trade = "NONE"

    if not hasattr(engine, "last_signal"):
        engine.last_signal = "NONE"


def log(msg: str):
    print(msg)
    engine.logs.append(str(msg))
    engine.logs = engine.logs[-300:]


async def force_trade_loop():
    log("🔥 V62 FORCE TRADE LOOP STARTED")

    tokens = [
        "So11111111111111111111111111111111111111112",
        "BONK111111111111111111111111111111111111111",
        "MEME111111111111111111111111111111111111111",
        "DOGE111111111111111111111111111111111111111",
    ]

    while engine.running:
        try:
            engine.stats["signals"] += 1

            score = random.random()
            mint = random.choice(tokens)
            engine.last_signal = f"{mint[:8]} score={score:.4f}"

            log(f"📊 SIGNAL {engine.last_signal}")

            if score > 0.5 or engine.stats["signals"] % 5 == 0:
                pos = {
                    "mint": mint,
                    "size": 0.001,
                    "entry_time": time.time(),
                    "entry_score": score,
                }
                engine.positions.append(pos)
                engine.stats["buys"] += 1
                engine.last_trade = f"BUY {mint[:8]}"
                log(f"🟢 BUY {mint[:8]} size=0.001")

            if engine.positions and random.random() > 0.7:
                pos = engine.positions.pop(0)
                pnl = round(random.uniform(-0.03, 0.06), 4)

                engine.trade_history.append({
                    "mint": pos["mint"],
                    "pnl": pnl,
                    "time": time.time(),
                })
                engine.trade_history = engine.trade_history[-200:]

                engine.stats["sells"] += 1
                engine.last_trade = f"SELL {pos['mint'][:8]}"
                log(f"🔴 SELL {pos['mint'][:8]} pnl={pnl}")

        except Exception as e:
            engine.stats["errors"] += 1
            log(f"❌ LOOP ERROR {e}")

        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global BOT_TASK

    init_engine()
    log("🚀 V62 COMPLETE LIVE ENGINE START")

    BOT_TASK = asyncio.create_task(force_trade_loop())

    yield

    engine.running = False
    if BOT_TASK:
        BOT_TASK.cancel()
        try:
            await BOT_TASK
        except Exception:
            pass


app = FastAPI(lifespan=lifespan)


@app.get("/")
def root():
    return {
        "status": "ok",
        "name": "V62 COMPLETE LIVE ENGINE",
    }


@app.get("/health")
def health():
    return {
        "running": engine.running,
        "uptime_sec": round(time.time() - engine.start_time, 2),
        "signals": engine.stats["signals"],
        "buys": engine.stats["buys"],
        "sells": engine.stats["sells"],
        "errors": engine.stats["errors"],
        "positions": len(engine.positions),
        "last_signal": engine.last_signal,
        "last_trade": engine.last_trade,
    }


@app.get("/positions")
def positions():
    return {
        "count": len(engine.positions),
        "positions": engine.positions,
    }


@app.get("/trades")
def trades():
    return {
        "count": len(engine.trade_history),
        "trades": engine.trade_history[-50:],
    }


@app.get("/logs")
def get_logs():
    return {
        "count": len(engine.logs),
        "logs": engine.logs[-100:],
    }


@app.get("/stats")
def stats():
    return engine.stats


@app.post("/kill")
def kill():
    engine.running = False
    log("🛑 ENGINE STOPPED")
    return {"status": "stopped"}
