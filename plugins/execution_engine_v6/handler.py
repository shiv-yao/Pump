import asyncio
import time
import json
import importlib.util
import inspect
from pathlib import Path

RUNNING = False

POSITIONS = {}   # asset_id -> {size, avg}
PNL = 0.0
TRADES = []


# ========= loader =========
def root():
    for p in Path(__file__).resolve().parents:
        if (p / "plugins").exists():
            return p / "plugins"
    return Path(__file__).resolve().parent.parent


def load(tool):
    for d in root().iterdir():
        m = d / "plugin.json"
        h = d / "handler.py"

        if not m.exists() or not h.exists():
            continue

        try:
            data = json.loads(m.read_text())
        except Exception:
            continue

        if not any(t["name"] == tool for t in data.get("tools", [])):
            continue

        spec = importlib.util.spec_from_file_location("mod", h)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool):
            return getattr(mod, tool)

    return None


async def call(tool, payload):
    fn = load(tool)
    if not fn:
        return {"error": f"{tool} not found"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


# ========= risk =========
def risk_check(asset_id, size, capital):
    pos = POSITIONS.get(asset_id, {"size": 0.0})

    # 單筆 <= 2%
    if size > capital * 0.02:
        return False

    # 單市場 <= 20%
    if abs(pos["size"]) > capital * 0.2:
        return False

    return True


# ========= fill =========
async def apply_fill(asset_id, side, price, size):
    global PNL

    px = float(price)
    qty = float(size)

    pos = POSITIONS.get(asset_id, {"size": 0.0, "avg": 0.0})

    if side == "buy":
        new_size = pos["size"] + qty
        pos["avg"] = (pos["avg"] * pos["size"] + px * qty) / max(new_size, 1e-9)
        pos["size"] = new_size
    else:
        # 這裡是簡化版 realized pnl
        realized = (px - pos["avg"]) * qty
        PNL += realized
        pos["size"] -= qty

    POSITIONS[asset_id] = pos

    # 同步 inventory controller
    await call("adjust_position", {
        "asset_id": asset_id,
        "size": qty,
        "side": side
    })

    TRADES.append({
        "time": time.time(),
        "asset_id": asset_id,
        "side": side,
        "price": px,
        "size": qty,
        "pnl": PNL
    })


# ========= execution =========
async def execute(asset_id, side, bid, ask, size):

    # 價格由 orderbook_edge 決定
    limit_price = await call("get_limit_price", {
        "bid": bid,
        "ask": ask,
        "side": side
    })

    if isinstance(limit_price, dict) and "error" in limit_price:
        return limit_price

    if not limit_price:
        return {"skipped": "spread too narrow"}

    price = float(limit_price)

    # ===== 1) LIMIT =====
    res = await call("pm_limit", {
        "asset_id": asset_id,
        "side": side,
        "price": price,
        "size": size,
        "ioc": False
    })

    if isinstance(res, dict) and "error" in res:
        return res

    oid = res.get("order_id")
    if not oid:
        return {"error": "no order_id returned"}

    # ===== 2) 等成交 =====
    filled = False

    for _ in range(10):
        od = await call("pm_get_order", {"order_id": oid})

        if isinstance(od, dict) and "error" in od:
            await asyncio.sleep(0.1)
            continue

        order = od.get("order", {})
        status = str(order.get("status", "")).lower()

        if status in ("filled", "partially_filled"):
            avg = float(order.get("avgPrice", price))
            qty = float(order.get("filledSize", size))
            await apply_fill(asset_id, side, avg, qty)
            filled = True
            break

        await asyncio.sleep(0.1)

    # ===== 3) fallback IOC =====
    if not filled:
        await call("pm_cancel", {"order_id": oid})

        res2 = await call("pm_limit", {
            "asset_id": asset_id,
            "side": side,
            "price": ask if side == "buy" else bid,
            "size": size,
            "ioc": True
        })

        if isinstance(res2, dict) and "error" in res2:
            return res2

        await asyncio.sleep(0.2)

        fills = await call("pm_get_fills", {"limit": 10})
        if isinstance(fills, dict):
            for f in fills.get("fills", []):
                if str(f.get("asset_id")) == str(asset_id):
                    try:
                        await apply_fill(
                            asset_id,
                            side,
                            float(f.get("price")),
                            float(f.get("size"))
                        )
                        filled = True
                        break
                    except Exception:
                        continue

    return {
        "asset_id": asset_id,
        "side": side,
        "size": size,
        "filled": filled
    }


# ========= main engine =========
async def start_v6_engine(markets, capital=100):
    global RUNNING
    RUNNING = True

    await call("start_polymarket_book", {"asset_ids": markets})

    while RUNNING:

        for m in markets:
            # ===== alpha =====
            alpha = await call("get_alpha_v2", {"asset_id": m})
            if not isinstance(alpha, dict) or "error" in alpha:
                continue

            side = alpha.get("action", "hold")
            score = float(alpha.get("score", 0.0))

            # ===== signal filter =====
            filtered = await call("filter_signal", {
                "score": score,
                "action": side
            })

            if isinstance(filtered, dict):
                filtered = filtered.get("action", "hold")

            side = str(filtered).lower().strip()

            if side == "hold":
                continue

            # ===== book =====
            book = await call("get_polymarket_book_cache", {"asset_id": m})
            if not isinstance(book, dict) or "error" in book:
                continue

            bid = book.get("best_bid")
            ask = book.get("best_ask")

            if not bid or not ask:
                continue

            bid = float(bid)
            ask = float(ask)

            # ===== inventory reduce =====
            reduce_needed = await call("should_reduce", {"asset_id": m})

            if reduce_needed is True:
                current = POSITIONS.get(m, {"size": 0.0})
                if current["size"] > 0:
                    side = "sell"
                elif current["size"] < 0:
                    side = "buy"

            # ===== size 動態 =====
            size = capital * (0.01 + score * 0.02)

            if not risk_check(m, size, capital):
                continue

            await execute(m, side, bid, ask, size)

        await asyncio.sleep(0.2)

    return "stopped"


def stop_v6_engine():
    global RUNNING
    RUNNING = False
    return "stopped"


def get_state():
    return {
        "positions": POSITIONS,
        "pnl": PNL,
        "trades": TRADES[-20:]
    }
