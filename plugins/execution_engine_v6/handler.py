import asyncio
import json
import time
import importlib.util
import inspect
from pathlib import Path

RUNNING = False

INVENTORY = {}      # {asset_id: position}
PENDING = {}        # order_id → state
EQUITY = []


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


# ========= 限價單 =========
async def place_limit(asset_id, side, price, size):
    # TODO: 接 polymarket_exec limit order
    return {
        "order_id": f"order_{time.time()}",
        "status": "placed",
        "price": price,
        "size": size,
        "side": side
    }


# ========= IOC fallback =========
async def place_ioc(asset_id, side, size):
    return await call("route_order", {
        "target": "polymarket",
        "side": side,
        "symbol": asset_id,
        "amount": size
    })


# ========= 成交追蹤 =========
def update_inventory(asset_id, side, size):
    pos = INVENTORY.get(asset_id, 0)

    if side == "buy":
        pos += size
    else:
        pos -= size

    INVENTORY[asset_id] = pos


# ========= 核心事件 =========
async def on_book_update(asset_id, book):

    mid = book["mid_price"]
    imbalance = book["imbalance"]

    # 簡單套利條件
    if abs(imbalance) < 0.1:
        return

    size = 1

    # ===== maker 優先 =====
    if imbalance > 0:
        # 買方強 → 掛 bid
        price = mid - 0.01
        order = await place_limit(asset_id, "buy", price, size)
        PENDING[order["order_id"]] = order

    else:
        price = mid + 0.01
        order = await place_limit(asset_id, "sell", price, size)
        PENDING[order["order_id"]] = order

    # ===== fallback IOC =====
    if len(PENDING) > 5:
        await place_ioc(asset_id, "buy", size)


# ========= 主引擎 =========
async def start_v6_engine(markets, capital=100):

    global RUNNING
    RUNNING = True

    # 啟動 WS
    await call("start_polymarket_book", {"asset_ids": markets})

    while RUNNING:

        for m in markets:

            book = await call("get_polymarket_book_cache", {
                "asset_id": m
            })

            if "error" in book:
                continue

            await on_book_update(m, book)

        # ===== PnL（簡化）=====
        equity = sum(INVENTORY.values())
        EQUITY.append({
            "time": time.time(),
            "equity": equity
        })

        await asyncio.sleep(0.1)  # 接近 event-driven

    return "stopped"


def stop_v6_engine():
    global RUNNING
    RUNNING = False
    return "stopped"


def get_inventory():
    return INVENTORY


def get_equity():
    return EQUITY
