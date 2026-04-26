from __future__ import annotations

from typing import Any


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def analyze_orderbook(book: dict, size: float) -> dict:
    bids = book.get("bids", []) or []
    asks = book.get("asks", []) or []

    best_bid = _f(book.get("best_bid", bids[0][0] if bids else 0))
    best_ask = _f(book.get("best_ask", asks[0][0] if asks else 0))

    if best_bid <= 0 or best_ask <= 0:
        return {"ok": False, "reason": "no_book"}

    spread = (best_ask - best_bid) / best_ask

    ask_depth = sum(_f(x[1]) for x in asks[:5])
    bid_depth = sum(_f(x[1]) for x in bids[:5])

    imbalance = (bid_depth - ask_depth) / max(bid_depth + ask_depth, 1e-9)

    remaining = size
    cost = 0.0
    filled = 0.0

    for px, qty in asks:
        px = _f(px)
        qty = _f(qty)
        take = min(remaining, qty)
        cost += take * px
        filled += take
        remaining -= take
        if remaining <= 0:
            break

    if filled <= 0:
        return {"ok": False, "reason": "no_liquidity"}

    vwap = cost / filled
    impact = (vwap - best_ask) / max(best_ask, 1e-9)

    return {
        "ok": True,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "bid_depth_5": bid_depth,
        "ask_depth_5": ask_depth,
        "imbalance": imbalance,
        "vwap": vwap,
        "impact": impact,
        "fillable": filled >= size,
        "filled_preview": filled,
        "micro_score": max(0.0, min(1.0, 1 - spread * 5 - impact * 3 + max(imbalance, 0) * 0.2)),
    }
