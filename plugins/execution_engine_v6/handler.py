import asyncio
import time
import os
import httpx

from utils.loader import call

RUNNING = False

POSITIONS = {}
PNL = 0.0
TRADES = []

TRADING_API_BASE = os.getenv("TRADING_API_BASE", "").rstrip("/")


# ========= wallet alpha =========
async def get_best_wallet_alpha(asset_id):
    for tool in ("get_wallet_alpha_v3", "get_wallet_alpha_v2", "get_wallet_alpha"):
        res = await call(tool, {"asset_id": asset_id})
        if isinstance(res, dict) and "error" not in res:
            return {
                "tool": tool,
                "action": res.get("action", "hold"),
                "score": float(res.get("score", 0))
            }
    return {"action": "hold", "score": 0.0, "tool": None}


# ========= risk =========
async def risk_check(asset_id, size):
    res = await call("check_risk", {
        "asset_id": asset_id,
        "size": size
    })

    if isinstance(res, dict):
        if res.get("allowed") is False:
            return False

    return True


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
        pnl_delta = 0.0
    else:
        pnl_delta = (px - pos["avg"]) * qty
        PNL += pnl_delta
        pos["size"] -= qty

    POSITIONS[asset_id] = pos

    await call("strategy_record_trade", {
        "strategy_id": strategy_id,
        "pnl": pnl_delta
    })

    await call("ledger_record_fill", {
        "asset_id": asset_id,
        "side": side,
        "price": px,
        "size": qty
    })

    TRADES.append({
        "time": time.time(),
        "asset_id": asset_id,
        "side": side,
        "price": px,
        "size": qty,
        "pnl": pnl_delta,
        "strategy_id": strategy_id
    })

    return pnl_delta


# ========= gateway execution =========
async def gateway_execute(asset_id, side, size, price, strategy_id):
    if not TRADING_API_BASE:
        return {"error": "TRADING_API_BASE not set"}

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.post(
                f"{TRADING_API_BASE}/trade/order",
                json={
                    "asset_id": asset_id,
                    "side": side,
                    "size": size,
                    "price": price,
                    "strategy_id": strategy_id
                }
            )
            return res.json()

    except Exception as e:
        return {"error": f"gateway_fail: {str(e)}"}


# ========= fallback =========
async def fallback_execute(asset_id, side, size, price):
    return await call("simulate_order", {
        "asset_id": asset_id,
        "side": side,
        "price": price,
        "size": size
    })


# ========= main =========
async def start_v7_engine(markets, capital=100):
    global RUNNING

    if RUNNING:
        return {"ok": True, "msg": "already running"}

    RUNNING = True

    await call("start_polymarket_book", {"asset_ids": markets})
    await call("start_wallet_feed_ws", {"asset_ids": markets})

    while RUNNING:
        loop_start = time.time()

        for m in markets:
            try:
                t0 = time.time()

                # ===== alpha =====
                alpha = await call("get_alpha_v2", {"asset_id": m})
                if not isinstance(alpha, dict):
                    continue

                base_side = str(alpha.get("action", "hold")).lower()
                base_score = float(alpha.get("score", 0))

                wallet = await get_best_wallet_alpha(m)
                wallet_side = wallet["action"]
                wallet_score = wallet["score"]

                # ===== fuse =====
                if wallet_score > base_score:
                    side = wallet_side
                    score = wallet_score
                else:
                    side = base_side
                    score = base_score

                if side == "hold":
                    continue

                # ===== strategy id FIXED =====
                strategy_id = (
                    "wallet_alpha_v3"
                    if wallet_score > base_score
                    else "orderbook_alpha_v2"
                )

                # ===== strategy gate =====
                gate = await call("strategy_should_trade", {
                    "strategy_id": strategy_id
                })

                if isinstance(gate, dict) and not gate.get("trade", True):
                    continue

                # ===== allocator =====
                alloc = await call("allocator_get_budget", {
                    "strategy_id": strategy_id,
                    "capital": capital
                })

                if not isinstance(alloc, dict):
                    continue

                budget = float(alloc.get("budget", 0))
                if budget <= 0:
                    continue

                size = budget * 0.2

                # ===== clamp =====
                size = max(0.001, min(size, capital * 0.05))

                # ===== risk =====
                if not await risk_check(m, size):
                    continue

                # ===== orderbook =====
                book = await call("get_polymarket_book_cache", {"asset_id": m})
                if not isinstance(book, dict):
                    continue

                bid = book.get("best_bid")
                ask = book.get("best_ask")

                if not bid or not ask:
                    continue

                price = ask if side == "buy" else bid

                # ===== latency guard =====
                if time.time() - t0 > 0.15:
                    continue

                # ===== execute =====
                result = await gateway_execute(
                    m, side, size, price, strategy_id
                )

                # ===== fallback =====
                if "error" in result:
                    result = await fallback_execute(m, side, size, price)

                # ===== fill =====
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
                continue

        await asyncio.sleep(max(0.2 - (time.time() - loop_start), 0))

    return {"ok": True}


async def stop_v7_engine():
    global RUNNING
    RUNNING = False
    await call("stop_wallet_feed_ws", {})
    return {"ok": True}


def get_state():
    return {
        "positions": POSITIONS,
        "pnl": PNL,
        "trades": TRADES[-20:],
        "running": RUNNING
    }
