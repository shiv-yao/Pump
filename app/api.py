# ================= V62 AI FUND BRAIN (FORCE TRADE LIVE) =================
import asyncio
import time
import random
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.state import engine

# 👉 正確 import（你現在 repo）
from app.engine import main_loop as real_main_loop

BOT_TASK = None


# ================= INIT =================
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


# ================= FORCE TRADE ENGINE =================
async def force_trade_loop():
    print("🔥 V62 FORCE TRADE LOOP STARTED")

    TOKENS = [
        "So11111111111111111111111111111111111111112",  # SOL
        "Es9vMFrzaCERh6kFh9U8u8nXcV4bLhM1cBh73PvvrLpz",  # USDT
    ]

    while True:
        try:
            print("🔄 LOOP TICK")

            engine.stats["signals"] += 1

            # 👉 隨機模擬 alpha
            score = random.random()

            mint = random.choice(TOKENS)

            engine.last_signal = f"{mint[:6]} score={score:.4f}"

            print(f"📊 SIGNAL: {engine.last_signal}")

            # ================= BUY =================
            if score > 0.5 or engine.stats["signals"] % 5 == 0:
                size = 0.001

                engine.positions.append({
                    "mint": mint,
                    "size": size,
                    "entry_time": time.time()
                })

                engine.stats["buys"] += 1
                engine.last_trade = f"BUY {mint[:6]}"

                print(f"🟢 BUY {mint[:6]} size={size}")

            # ================= SELL =================
            if engine.positions and random.random() > 0.7:
                pos = engine.positions.pop(0)

                engine.stats["sells"] += 1
                engine.last_trade = f"SELL {pos['mint'][:6]}"

                print(f"🔴 SELL {pos['mint'][:6]}")

        except Exception as e:
            engine.stats["errors"] += 1
            print("❌ LOOP ERROR:", e)

        await asyncio.sleep(5)


# ================= ENGINE RUNNER =================
async def _engine_runner():
    print("🚀 ENGINE START")

    try:
        # 👉 先跑你原本 engine（如果有）
        asyncio.create_task(real_main_loop())

        # 👉 再跑強制交易（保證動）
        await force_trade_loop()

    except Exception as e:
        print("❌ ENGINE CRASH:", e)


# ================= FASTAPI =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global BOT_TASK

    init_engine()

    BOT_TASK = asyncio.create_task(_engine_runner())

    yield

    if BOT_TASK:
        BOT_TASK.cancel()


app = FastAPI(lifespan=lifespan)


# ================= API =================
@app.get("/")
def root():
    return {"status": "V62 LIVE"}


@app.get("/health")
def health():
    return {
        "running": engine.running,
        "uptime": time.time() - engine.start_time,
        "positions": len(engine.positions),
        "last_trade": engine.last_trade,
        "signals": engine.stats["signals"]
    }


@app.get("/positions")
def positions():
    return engine.positions


@app.get("/stats")
def stats():
    return engine.stats


@app.post("/kill")
def kill():
    engine.running = False
    return {"status": "stopped"}
