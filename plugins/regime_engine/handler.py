from __future__ import annotations

from typing import Any
from app.utils.loader import call


def _f(x: Any, default=0.0):
    try:
        return float(x)
    except:
        return default


async def get_market_regime(symbol=None, **kwargs):
    symbol = symbol or "BTCUSDT"

    # ===== price snapshot =====
    p1 = await call("get_spot_price", {"symbol": symbol})
    p2 = await call("get_spot_price", {"symbol": symbol})

    if not isinstance(p1, dict) or not isinstance(p2, dict):
        return {"regime": "unknown", "confidence": 0.0}

    px1 = _f(p1.get("price", 0))
    px2 = _f(p2.get("price", 0))

    if px1 <= 0 or px2 <= 0:
        return {"regime": "unknown", "confidence": 0.0}

    change = (px2 - px1) / px1

    # ===== regime logic =====
    if abs(change) > 0.01:
        regime = "trend"
        conf = min(abs(change) * 50, 1.0)
    elif abs(change) < 0.002:
        regime = "range"
        conf = 0.6
    else:
        regime = "neutral"
        conf = 0.5

    # ===== risk off =====
    if change < -0.02:
        regime = "risk_off"
        conf = 0.9

    return {
        "regime": regime,
        "confidence": round(conf, 4),
        "symbol": symbol
    }
