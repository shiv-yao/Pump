import asyncio
import time
import json
import importlib.util
import inspect
from pathlib import Path

RUNNING = False

POSITIONS = {}   # asset_id → {size, avg}
PNL = 0


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
        except:
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


# ========= 風控 =========
def risk_check(asset_id, size, capital):
    pos = POSITIONS.get(asset_id, {"size": 0})

    # 單筆 <= 2%
    if size > capital * 0.02:
        return False

    # 單市場 <= 20%
    if abs(pos["size"]) > capital * 0.2:
        return False

    return True


# ========= 成交 =========
def apply_fill(asset_id, side, price, size):
    global PNL

    pos = POSITIONS.get(asset_id, {"size": 0, "avg": 0})

    if side == "buy":
        new_size = pos["size"] + size
        pos["avg"] = (pos["avg"] * pos["size"] + price * size) / max(new_size, 1)
        pos["size"] = new_size
    else:
        pnl = (price - pos["avg"]) * size
        PNL += pnl
        pos["size"] -= size

    POSITIONS[asset_id] = pos


# ========= 下單 =========
async def execute(asset_id, side, bid, ask, size):

    price = bid if side == "buy" else ask

    # ===== LIMIT =====
    res = await call("pm_limit", {
        "asset_id": asset_id,
        "side": side,
        "price": price,
        "size": size,
        "ioc": False
    })

    oid = res.get("order_id")
    if not oid:
        return

    # ===== 等成交 =====
    filled = False

    for _ in range(10):
        od = await call("pm_get_order", {"order_id": oid})
        order = od.get("order", {})
        status = order.get("status")

        if status in ("filled", "partially_filled"):

            avg = float(order.get("avgPrice", price))
            qty = float(order.get("filledSize", size))

            apply_fill(asset_id, side, avg, qty)
            filled = True
            break

        await asyncio.sleep(0.1)

    # ===== fallback IOC =====
    if not filled:
        await call("pm_cancel", {"order_id": oid})

        res2 = await call("pm_limit", {
            "asset_id": asset_id,
            "side": side,
            "price": ask if side == "buy" else bid,
            "size": size,
            "ioc": True
        })

        await asyncio.sleep(0.2)
        fills = await call("pm_get_fills", {"limit": 5})

        for f in fills.get("fills", []):
            if f.get("asset_id") == asset_id:
                apply_fill(
                    asset_id,
                    side,
                    float(f.get("price")),
                    float(f.get("size"))
                )


# ========= 主引擎 =========
async def start_v6_engine(markets, capital=100):

    global RUNNING
    RUNNING = True

    await call("start_polymarket_book", {"asset_ids": markets})

    while RUNNING:

        for m in markets:

            # ===== 取得 alpha =====
            alpha = await call("get_alpha_v2", {"asset_id": m})

            if "error" in alpha:
                continue

            side = alpha.get("action")
            score = alpha.get("score", 0)

            if side == "hold":
                continue

            # ===== 取得 orderbook =====
            book = await call("get_polymarket_book_cache", {"asset_id": m})
            if "error" in book:
                continue

            bid = book.get("best_bid")
            ask = book.get("best_ask")

            if not bid or not ask:
                continue

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
        "pnl": PNL
    }
