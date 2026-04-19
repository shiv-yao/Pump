import asyncio
import time
import json
import importlib.util
import inspect
from pathlib import Path

RUNNING = False

POSITIONS = {}
PNL = 0
TRADES = []

MAX_LATENCY = 0.1   # 100ms
MIN_EDGE = 0.02


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
            data = json.loads(m.read_text(encoding="utf-8"))
        except:
            continue

        if not any(t.get("name") == tool for t in data.get("tools", [])):
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


# ========= execution intelligence =========

def calc_edge(bid, ask):
    return abs(ask - bid)


def predict_fill_probability(bids, asks):
    bid_sz = sum(x["size"] for x in bids[:3])
    ask_sz = sum(x["size"] for x in asks[:3])

    total = bid_sz + ask_sz
    if total == 0:
        return 0

    imbalance = abs(bid_sz - ask_sz) / total
    return imbalance


def is_fake_liquidity(bids, asks):
    if not bids or not asks:
        return True

    # 大單突然跳出 → fake
    if bids[0]["size"] > bids[1]["size"] * 10:
        return True

    if asks[0]["size"] > asks[1]["size"] * 10:
        return True

    return False


async def smart_execute(asset_id, side, book, size):
    bid = float(book["best_bid"])
    ask = float(book["best_ask"])
    bids = book.get("bids", [])
    asks = book.get("asks", [])

    # ===== 1️⃣ edge =====
    edge = calc_edge(bid, ask)
    if edge < MIN_EDGE:
        return {"skipped": "low edge"}

    # ===== 2️⃣ fake liquidity =====
    if is_fake_liquidity(bids, asks):
        return {"skipped": "fake liquidity"}

    # ===== 3️⃣ fill probability =====
    fill_prob = predict_fill_probability(bids, asks)

    # ===== 4️⃣ routing =====
    use_ioc = False

    if fill_prob < 0.3:
        use_ioc = True

    if edge > 0.05:
        use_ioc = False

    price = ask if side == "buy" else bid

    # ===== 5️⃣ 下單 =====
    res = await call("pm_limit", {
        "asset_id": asset_id,
        "side": side,
        "price": price,
        "size": size,
        "ioc": use_ioc
    })

    if "error" in res:
        return res

    oid = res.get("order_id")

    if not oid:
        return {"error": "no order id"}

    # ===== 6️⃣ 等成交 =====
    for _ in range(6):
        od = await call("pm_get_order", {"order_id": oid})

        if "error" in od:
            continue

        order = od.get("order", {})
        status = str(order.get("status", "")).lower()

        if status in ("filled", "partially_filled"):
            return {"filled": True}

        await asyncio.sleep(0.05)

    # ===== 7️⃣ fallback =====
    await call("pm_cancel", {"order_id": oid})

    res2 = await call("pm_limit", {
        "asset_id": asset_id,
        "side": side,
        "price": price,
        "size": size,
        "ioc": True
    })

    return res2


# ========= main =========

async def start_v7_engine(markets, capital=100):
    global RUNNING
    RUNNING = True

    await call("start_polymarket_book", {"asset_ids": markets})

    while RUNNING:

        loop_start = time.time()

        for m in markets:

            t0 = time.time()

            # ===== alpha =====
            alpha = await call("get_alpha_v2", {"asset_id": m})
            if "error" in alpha:
                continue

            side = alpha["action"]
            score = float(alpha["score"])

            wallet = await call("get_wallet_alpha", {"asset_id": m})
            if "error" not in wallet:
                if wallet["score"] > 0.7:
                    side = wallet["action"]
                    score = wallet["score"]

            if score < 0.55:
                continue

            # ===== latency guard =====
            if time.time() - t0 > MAX_LATENCY:
                continue

            # ===== orderbook =====
            book = await call("get_polymarket_book_cache", {"asset_id": m})
            if "error" in book:
                continue

            size = capital * (0.01 + score * 0.02)

            await smart_execute(m, side, book, size)

        await asyncio.sleep(max(0.2 - (time.time() - loop_start), 0))


def stop_v7_engine():
    global RUNNING
    RUNNING = False
