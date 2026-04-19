# ================= FINAL PRODUCTION VERSION =================

import asyncio
import time
import json
import importlib.util
import inspect
from pathlib import Path

RUNNING = False

POSITIONS = {}
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
            data = json.loads(m.read_text(encoding="utf-8"))
        except:
            continue

        if not any(t.get("name") == tool for t in data.get("tools", [])):
            continue

        spec = importlib.util.spec_from_file_location(f"plugin_{d.name}", h)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool):
            return getattr(mod, tool)

    return None


async def call(tool, payload=None):
    payload = payload or {}
    fn = load(tool)

    if not fn:
        return {"error": f"{tool} not found"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


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
    return {"tool": None, "action": "hold", "score": 0.0}


# ========= risk =========
def risk_check(asset_id, size, capital):
    pos = POSITIONS.get(asset_id, {"size": 0})

    if size > capital * 0.02:
        return False

    if abs(pos["size"]) > capital * 0.2:
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
        pnl_delta = 0
    else:
        pnl_delta = (px - pos["avg"]) * qty
        PNL += pnl_delta
        pos["size"] -= qty

    POSITIONS[asset_id] = pos

    # ===== record =====
    TRADES.append({
        "time": time.time(),
        "asset_id": asset_id,
        "side": side,
        "price": px,
        "size": qty,
        "pnl_delta": pnl_delta,
        "strategy_id": strategy_id
    })

    # ===== plugins =====
    await call("fb_record_trade", {"pnl": pnl_delta})
    await call("strategy_record_trade", {"strategy_id": strategy_id, "pnl": pnl_delta})
    await call("ledger_record_fill", {
        "asset_id": asset_id,
        "side": side,
        "price": px,
        "size": qty
    })

    return pnl_delta


# ========= alpha =========
async def get_fused_signal(asset_id):
    alpha = await call("get_alpha_v2", {"asset_id": asset_id})
    if not isinstance(alpha, dict) or "error" in alpha:
        return {"error": "alpha fail"}

    side = alpha.get("action", "hold")
    score = float(alpha.get("score", 0))

    wallet = await get_best_wallet_alpha(asset_id)

    if wallet["score"] > 0.75:
        side = wallet["action"]
        score = max(score, wallet["score"])
    elif wallet["score"] > 0.55 and wallet["action"] == side:
        score *= 1.2
    elif wallet["action"] != side:
        score *= 0.4

    if score < 0.55:
        return {"action": "hold", "score": score}

    return {"action": side, "score": score}


# ========= execution =========
async def smart_execute(asset_id, side, book, size, capital, strategy_id):
    bid = float(book["best_bid"])
    ask = float(book["best_ask"])

    edge = abs(ask - bid)
    if edge < 0.02:
        return

    if not risk_check(asset_id, size, capital):
        return

    price = ask if side == "buy" else bid

    res = await call("pm_limit", {
        "asset_id": asset_id,
        "side": side,
        "price": price,
        "size": size,
        "ioc": True
    })

    if "error" in res:
        return

    oid = res.get("order_id")

    for _ in range(4):
        od = await call("pm_get_order", {"order_id": oid})
        if "error" in od:
            continue

        status = od.get("order", {}).get("status", "")

        if status in ("filled", "partially_filled"):
            avg = float(od["order"].get("avgPrice", price))
            qty = float(od["order"].get("filledSize", size))

            await apply_fill(asset_id, side, avg, qty, strategy_id)
            return


# ========= engine =========
async def start_v7_engine(markets, capital=100):
    global RUNNING

    if RUNNING:
        return {"ok": True}

    RUNNING = True

    await call("start_polymarket_book", {"asset_ids": markets})
    await call("start_wallet_feed_ws", {"asset_ids": markets})

    while RUNNING:
        for m in markets:

            fused = await get_fused_signal(m)
            if "error" in fused:
                continue

            side = fused["action"]
            score = fused["score"]

            if side == "hold":
                continue

            wallet = await get_best_wallet_alpha(m)

            # ===== strategy id 強化 =====
            if wallet["score"] > score:
                strategy_id = wallet["tool"]
            else:
                strategy_id = "orderbook_alpha_v2"

            # ===== strategy gate =====
            ok = await call("strategy_should_trade", {"strategy_id": strategy_id})
            if not ok.get("trade", True):
                continue

            # ===== allocator v3 =====
            alloc = await call("allocator_get_budget", {
                "strategy_id": strategy_id,
                "capital": capital
            })

            if "error" in alloc:
                continue

            budget = float(alloc.get("budget", 0))
            if budget <= 0:
                continue

            # ===== portfolio v2 =====
            pm = await call("run_portfolio_v2", {
                "asset_id": m,
                "capital": budget,
                "orderbook_score": score,
                "wallet_score": wallet["score"]
            })

            if not isinstance(pm, dict):
                continue

            side = pm.get("action", "hold")
            size = float(pm.get("size", 0))

            if side == "hold" or size <= 0:
                continue

            book = await call("get_polymarket_book_cache", {"asset_id": m})
            if "error" in book:
                continue

            await smart_execute(m, side, book, size, capital, strategy_id)

        await asyncio.sleep(0.2)

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
        "trades": TRADES[-20:]
    }
