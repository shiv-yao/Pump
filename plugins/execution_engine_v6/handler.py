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
            data = json.loads(m.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not any(t.get("name") == tool for t in data.get("tools", [])):
            continue

        spec = importlib.util.spec_from_file_location(f"plugin_{d.name}", h)
        if not spec or not spec.loader:
            continue

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


# ========= wallet alpha resolver =========
async def get_best_wallet_alpha(asset_id):
    """
    Prefer wallet_alpha_v3, then v2, then v1.
    Returns normalized dict: {"action": "...", "score": ...}
    """
    for tool_name in ("get_wallet_alpha_v3", "get_wallet_alpha_v2", "get_wallet_alpha"):
        result = await call(tool_name, {"asset_id": asset_id})
        if isinstance(result, dict) and "error" not in result:
            action = str(result.get("action", "hold")).lower().strip()
            try:
                score = float(result.get("score", 0.0))
            except Exception:
                score = 0.0
            return {
                "tool": tool_name,
                "action": action,
                "score": score,
                "raw": result,
            }

    return {
        "tool": None,
        "action": "hold",
        "score": 0.0,
        "raw": {"error": "no wallet alpha available"},
    }


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
async def apply_fill(asset_id, side, price, size, strategy_id="fusion_alpha_v1"):
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
        "pnl_total": PNL,
        "pnl_delta": pnl_delta,
        "strategy_id": strategy_id
    })

    # fund_brain_v8
    await call("fb_record_trade", {"pnl": pnl_delta})

    # strategy manager
    await call("strategy_record_trade", {
        "strategy_id": strategy_id,
        "pnl": pnl_delta
    })

    # ledger_v2
    await call("ledger_record_fill", {
        "asset_id": asset_id,
        "side": side,
        "price": px,
        "size": qty
    })

    # wallet alpha feed
    # 真資料版本之後可把 wallet 改成實際地址
    await call("wa_record_trade", {
        "wallet": "market_wallet",
        "asset_id": asset_id,
        "side": side,
        "price": px,
        "size": qty
    })

    return pnl_delta


# ========= alpha fusion =========
async def get_fused_signal(asset_id):
    # 1) orderbook alpha
    alpha = await call("get_alpha_v2", {"asset_id": asset_id})
    if not isinstance(alpha, dict) or "error" in alpha:
        return {"error": "alpha_v2 failed"}

    side = str(alpha.get("action", "hold")).lower().strip()
    score = float(alpha.get("score", 0.0))

    # 2) wallet alpha (v3 -> v2 -> v1)
    wallet = await get_best_wallet_alpha(asset_id)
    w_side = wallet["action"]
    w_score = float(wallet["score"])

    # 強融合版
    if w_score > 0.75 and w_side != "hold":
        side = w_side
        score = max(score, w_score)

    elif w_score > 0.55 and w_side == side:
        score = max(score, w_score) * 1.2

    elif w_side != side and w_side != "hold":
        score *= 0.4

    # 3) 弱訊號直接 hold
    if score < 0.55:
        side = "hold"

    # 4) signal filter
    filtered = await call("filter_signal", {
        "score": score,
        "action": side
    })

    if isinstance(filtered, dict):
        side = str(filtered.get("action", "hold")).lower().strip()
    else:
        side = str(filtered).lower().strip()

    return {
        "action": side,
        "score": score,
        "wallet_tool": wallet["tool"]
    }


# ========= execution intelligence =========
def calc_edge(bid, ask):
    return abs(float(ask) - float(bid))


def predict_fill_probability(bids, asks):
    bid_sz = sum(float(x["size"]) for x in bids[:3]) if bids else 0.0
    ask_sz = sum(float(x["size"]) for x in asks[:3]) if asks else 0.0

    total = bid_sz + ask_sz
    if total == 0:
        return 0.0

    return abs(bid_sz - ask_sz) / total


def is_fake_liquidity(bids, asks):
    if len(bids) < 2 or len(asks) < 2:
        return False

    try:
        if float(bids[0]["size"]) > float(bids[1]["size"]) * 10:
            return True
        if float(asks[0]["size"]) > float(asks[1]["size"]) * 10:
            return True
    except Exception:
        return False

    return False


# ========= execution =========
async def smart_execute(asset_id, side, book, size, capital, strategy_id="fusion_alpha_v1"):
    bid = float(book["best_bid"])
    ask = float(book["best_ask"])
    bids = book.get("bids", [])
    asks = book.get("asks", [])

    # 1) edge 檢查
    edge = calc_edge(bid, ask)
    if edge < 0.02:
        return {"skipped": "low edge"}

    # 2) fake liquidity 過濾
    if is_fake_liquidity(bids, asks):
        return {"skipped": "fake liquidity"}

    # 3) fill probability
    fill_prob = predict_fill_probability(bids, asks)

    # 4) 依 fill probability 動態縮放 size
    size *= max(0.3, min(1.0, fill_prob * 2.0))

    # 5) inventory reduce
    reduce_needed = await call("should_reduce", {"asset_id": asset_id})
    if reduce_needed is True:
        current = POSITIONS.get(asset_id, {"size": 0.0})
        if current["size"] > 0:
            side = "sell"
        elif current["size"] < 0:
            side = "buy"

    # 6) price selection
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

    # 7) 風控
    if not risk_check(asset_id, size, capital):
        return {"skipped": "risk blocked"}

    # 8) routing
    use_ioc = False
    if fill_prob < 0.3:
        use_ioc = True
    if edge > 0.05:
        use_ioc = False

    order_price = (
        ask if (use_ioc and side == "buy")
        else bid if (use_ioc and side == "sell")
        else price
    )

    # 9) 下單
    res = await call("pm_limit", {
        "asset_id": asset_id,
        "side": side,
        "price": order_price,
        "size": size,
        "ioc": use_ioc
    })

    if isinstance(res, dict) and "error" in res:
        return res

    oid = res.get("order_id")
    if not oid:
        return {"error": "no order_id returned"}

    # 10) 等成交
    for _ in range(10 if not use_ioc else 4):
        od = await call("pm_get_order", {"order_id": oid})

        if isinstance(od, dict) and "error" in od:
            await asyncio.sleep(0.05)
            continue

        order = od.get("order", {})
        status = str(order.get("status", "")).lower()

        if status in ("filled", "partially_filled"):
            avg = float(order.get("avgPrice", order_price))
            qty = float(order.get("filledSize", size))
            pnl_delta = await apply_fill(asset_id, side, avg, qty, strategy_id=strategy_id)
            return {
                "asset_id": asset_id,
                "side": side,
                "size": qty,
                "filled": True,
                "avg_price": avg,
                "pnl_delta": pnl_delta,
                "mode": "ioc" if use_ioc else "limit",
                "strategy_id": strategy_id
            }

        await asyncio.sleep(0.05 if use_ioc else 0.1)

    # 11) maker 未成交 → cancel → IOC fallback
    if not use_ioc:
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

        oid2 = res2.get("order_id")
        if oid2:
            for _ in range(4):
                od2 = await call("pm_get_order", {"order_id": oid2})
                if isinstance(od2, dict) and "error" not in od2:
                    order2 = od2.get("order", {})
                    status2 = str(order2.get("status", "")).lower()

                    if status2 in ("filled", "partially_filled"):
                        avg2 = float(order2.get("avgPrice", ask if side == "buy" else bid))
                        qty2 = float(order2.get("filledSize", size))
                        pnl_delta = await apply_fill(asset_id, side, avg2, qty2, strategy_id=strategy_id)
                        return {
                            "asset_id": asset_id,
                            "side": side,
                            "size": qty2,
                            "filled": True,
                            "avg_price": avg2,
                            "pnl_delta": pnl_delta,
                            "mode": "ioc_fallback",
                            "strategy_id": strategy_id
                        }
                await asyncio.sleep(0.05)

    return {
        "asset_id": asset_id,
        "side": side,
        "size": size,
        "filled": False,
        "strategy_id": strategy_id
    }


# ========= main engine =========
async def start_v7_engine(markets, capital=100):
    global RUNNING
    RUNNING = True

    await call("start_polymarket_book", {"asset_ids": markets})

    while RUNNING:
        loop_start = time.time()
        max_position_per_trade = 0.05 * capital

        for m in markets:
            t0 = time.time()

            # ===== mark price to ledger =====
            book_for_mark = await call("get_polymarket_book_cache", {"asset_id": m})
            if isinstance(book_for_mark, dict) and "error" not in book_for_mark:
                mark_px = book_for_mark.get("best_bid") or book_for_mark.get("best_ask")
                if mark_px:
                    await call("ledger_mark_price", {
                        "asset_id": m,
                        "price": mark_px
                    })

            # ===== fused alpha =====
            fused = await get_fused_signal(m)
            if "error" in fused:
                continue

            base_side = fused["action"]
            base_score = float(fused["score"])

            if base_side == "hold":
                continue

            # ===== wallet alpha again for allocator / portfolio =====
            wallet = await get_best_wallet_alpha(m)
            wallet_score = float(wallet.get("score", 0.0))

            # ===== dynamic strategy id =====
            if wallet_score > base_score:
                strategy_id = "wallet_alpha_v3" if wallet.get("tool") == "get_wallet_alpha_v3" else "wallet_alpha_v2"
            else:
                strategy_id = "orderbook_alpha_v2"

            # ===== strategy manager gate =====
            strategy_decision = await call("strategy_should_trade", {
                "strategy_id": strategy_id
            })

            if isinstance(strategy_decision, dict) and not strategy_decision.get("trade", True):
                continue

            # ===== allocator v2 =====
            alloc = await call("allocator_get_budget", {
                "strategy_id": strategy_id,
                "capital": capital
            })

            if not isinstance(alloc, dict) or "error" in alloc:
                continue

            strategy_budget = float(alloc.get("budget", 0.0))
            if strategy_budget <= 0:
                continue

            # ===== portfolio manager =====
            pm = await call("run_portfolio_v1", {
                "asset_id": m,
                "capital": strategy_budget,
                "orderbook_score": base_score,
                "wallet_score": wallet_score
            })

            if not isinstance(pm, dict):
                continue

            side = str(pm.get("action", "hold")).lower().strip()
            size = float(pm.get("size", 0.0))
            score = float(pm.get("score", base_score))

            if side == "hold" or size <= 0:
                continue

            # ===== allocator hard cap =====
            size = min(size, strategy_budget * 0.2)

            # ===== V8 entry gate with strong-signal bypass =====
            params = await call("fb_adjust_params", {})
            threshold = params.get("threshold", 0.55) if isinstance(params, dict) else 0.55

            if score < threshold and score < 0.8:
                continue

            # ===== latency guard =====
            if time.time() - t0 > 0.1:
                continue

            # ===== orderbook =====
            book = await call("get_polymarket_book_cache", {"asset_id": m})
            if not isinstance(book, dict) or "error" in book:
                continue

            bid = book.get("best_bid")
            ask = book.get("best_ask")

            if not bid or not ask:
                continue

            # ===== cap single trade size =====
            size = min(size, max_position_per_trade)

            await smart_execute(
                m,
                side,
                book,
                size,
                capital,
                strategy_id=strategy_id
            )

        await asyncio.sleep(max(0.2 - (time.time() - loop_start), 0))

    return "stopped"


def stop_v7_engine():
    global RUNNING
    RUNNING = False
    return "stopped"


def get_state():
    return {
        "positions": POSITIONS,
        "pnl": PNL,
        "trades": TRADES[-20:]
    }
