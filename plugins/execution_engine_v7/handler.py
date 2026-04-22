import asyncio
import time
from app.utils.loader import call

RUNNING = False
TASK = None

POSITIONS = {}
PNL = 0.0
TRADES = []


# ========= ENGINE LOOP =========
async def engine_loop(markets, capital):
    global RUNNING, PNL

    while RUNNING:
        loop_start = time.time()

        for m in markets:
            try:
                # ===== FUND BRAIN =====
                decision = await call("fund_decide_trade", {
                    "symbol": m,
                    "capital": capital
                })

                if not isinstance(decision, dict):
                    continue

                side = decision.get("action", "hold")
                size = float(decision.get("size", 0))
                strategy_id = decision.get("strategy_id", "fund_brain")

                if side == "hold" or size <= 0:
                    continue

                # ===== PRICE =====
                price_data = await call("get_spot_price", {"symbol": m})
                if not isinstance(price_data, dict):
                    continue

                price = float(price_data.get("price", 1))

                # ===== EXECUTION =====
                result = await call("simulate_order", {
                    "asset_id": m,
                    "side": side,
                    "price": price,
                    "size": size
                })

                if result.get("filled"):
                    await apply_fill(
                        m,
                        side,
                        result.get("avg_price", price),
                        result.get("size", size),
                        strategy_id
                    )

            except Exception as e:
                print(f"[ENGINE ERROR] {m}: {e}")

        await asyncio.sleep(max(0.2 - (time.time() - loop_start), 0))


# ========= FILL =========
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
        "size": qty,
        "strategy": strategy_id
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
