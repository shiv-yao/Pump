import asyncio
import time
import json
import importlib.util
import inspect
from pathlib import Path

RUNNING = False

POSITIONS = {}   # asset_id → {size, avg_price}
TRADES = []
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


# ========= 真成交處理 =========
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

    TRADES.append({
        "time": time.time(),
        "asset": asset_id,
        "side": side,
        "price": price,
        "size": size
    })


# ========= 主邏輯 =========
async def start_final(markets, capital=50):

    global RUNNING
    RUNNING = True

    await call("start_polymarket_book", {"asset_ids": markets})

    while RUNNING:

        for m in markets:

            book = await call("get_polymarket_book_cache", {"asset_id": m})
            if "error" in book:
                continue

            bid = book.get("best_bid")
            ask = book.get("best_ask")

            if not bid or not ask:
                continue

            spread = ask - bid

            # ===== 核心 edge（簡化）=====
            if spread < 0.02:
                continue

            size = capital * 0.05

            # ===== 掛單（maker）=====
            order = await call("pm_buy", {
                "market": m,
                "amount": size
            })

            # ⚠️ 這裡要接真成交回傳
            # 假設成交（測試用）
            apply_fill(m, "buy", ask, size)

        await asyncio.sleep(0.5)

    return "stopped"


def stop_final():
    global RUNNING
    RUNNING = False
    return "stopped"


def get_state():
    return {
        "positions": POSITIONS,
        "pnl": PNL,
        "trades": TRADES[-20:]
    }
