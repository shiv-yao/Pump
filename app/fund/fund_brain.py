from __future__ import annotations
from typing import Any
from app.utils.loader import call

# ===== config =====
MIN_SCORE = 0.60
DEV_OVERRIDE_SCORE = 0.80

def _f(x: Any, d: float = 0.0):
    try:
        return float(x)
    except:
        return d


async def decide_trade(symbol: str, capital: float = 100):

    # ===== 1. DEV WALLET（最高優先）=====
    dev = await call("get_dev_signal", {"asset_id": symbol})

    if isinstance(dev, dict):
        dev_score = _f(dev.get("score"))

        if dev_score > DEV_OVERRIDE_SCORE:
            return {
                "action": "buy",
                "size": min(capital * 0.05, 0.08),
                "reason": "dev_wallet",
                "score": dev_score
            }

    # ===== 2. SNIPER SIGNAL =====
    sniper = await call("sniper_scan", {})
    tokens = sniper.get("candidates", []) if isinstance(sniper, dict) else []

    for t in tokens:
        if t.get("asset_id") == symbol and _f(t.get("score")) > 0.75:
            return {
                "action": "buy",
                "size": 0.02,
                "reason": "sniper",
                "score": t.get("score")
            }

    # ===== 3. ALPHA =====
    alpha = await call("get_alpha_signal", {"symbol": symbol})

    if not isinstance(alpha, dict):
        return {"action": "hold"}

    score = _f(alpha.get("score"))
    side = alpha.get("action", "hold")

    if score < MIN_SCORE:
        return {"action": "hold", "reason": "low_score"}

    return {
        "action": side,
        "size": 0.01,
        "reason": "alpha",
        "score": score
    }
