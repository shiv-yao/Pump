import asyncio
import time
import os
import httpx

from app.utils.loader import call

RUNNING = False
TASK = None

POSITIONS = {}
PNL = 0.0
TRADES = []

TRADING_API_BASE = os.getenv("TRADING_API_BASE", "").rstrip("/")


# ========= core loop =========
async def engine_loop(markets, capital):
    global RUNNING, PNL

    while RUNNING:
        loop_start = time.time()

        for m in markets:
            try:
                alpha = await call("get_alpha_v2", {"asset_id": m})
                if not isinstance(alpha, dict):
                    continue

                side = str(alpha.get("action", "hold")).lower()
                score = float(alpha.get("score", 0))

                if side == "hold" or score < 0.5:
                    continue

                size = min(max(0.001, capital * 0.02), capital * 0.05)

                # ===== price =====
                price_data = await call("get_spot_price", {"symbol": m})
                price = price_data.get("price", 1)

                # ===== execute =====
                result = await fallback_execute(m, side, size, price)

                if result.get("filled"):
                    await apply_fill(
                        m,
                        side,
                        result.get("avg_price", price),
                        result.get("size", size),
                        "alpha_v2"
                    )

            except Exception as e:
                print(f"[ENGINE ERROR] {m}: {e}")

        await asyncio.sleep(max(0.2 - (time.time() - loop_start), 0))


# ========= execution =========
async def fallback_execute(asset_id, side, size, price):
    return await call("simulate_order", {
        "asset_id": asset_id,
        "side": side,
        "price": price,
        "size": size
    })


# ========= fill =========
async def apply_fill(asset_id, side, price, size, strategy_id):
    global PNL

    px = float(price)
    qty = float(size)

    pos = POSITIONS.get(asset_id, {"size": 0.0, "avg": 0.0})

    if side == "buy":
        new_size = pos["size"] + qty
        pos["avg"] = (pos["avg"] * pos["size"] + px * qty) / max(new_size, 1e-9)
        pos["size"] = new_size
    else:
        pnl_delta = (px - pos["avg"]) * qty
        PNL += pnl_delta
        pos["size"] -= qty

    POSITIONS[asset_id] = pos

    TRADES.append({
        "time": time.time(),
        "asset_id": asset_id,
        "side": side,
        "price": px,
        "size": qty
    })


# ========= API =========
async def start_v7_engine(markets=None, capital=100, **kwargs):
    global RUNNING, TASK

    if RUNNING:
        return {"ok": True, "msg": "already running"}

    markets = markets or ["BTCUSDT"]

    RUNNING = True
    TASK = asyncio.create_task(engine_loop(markets, capital))

    return {
        "ok": True,
        "msg": "engine started",
        "markets": markets
    }


async def stop_v7_engine(**kwargs):
    global RUNNING, TASK

    RUNNING = False

    if TASK:
        TASK.cancel()
        TASK = None

    return {"ok": True, "msg": "engine stopped"}


def get_state(**kwargs):
    return {
        "running": RUNNING,
        "positions": POSITIONS,
        "pnl": PNL,
        "trades": TRADES[-20:]
    }
