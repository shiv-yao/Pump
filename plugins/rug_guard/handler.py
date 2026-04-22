from __future__ import annotations

from typing import Any
from app.utils.loader import call


def _f(x: Any, default=0.0):
    try:
        return float(x)
    except:
        return default


async def rug_check(symbol=None, asset_id=None, **kwargs):
    target = symbol or asset_id or "BTCUSDT"

    # ===== liquidity proxy =====
    price = await call("get_spot_price", {"symbol": target})

    if not isinstance(price, dict):
        return {"allowed": False, "reason": "no_price"}

    px = _f(price.get("price", 0), 0)

    # ===== fake simple rug logic =====
    if px <= 0:
        return {"allowed": False, "reason": "invalid_price"}

    if px < 0.0000001:
        return {"allowed": False, "reason": "dust_token"}

    # ===== placeholder for real check =====
    score = 0.1  # 0=安全, 1=危險

    if score > 0.8:
        return {
            "allowed": False,
            "reason": "rug_risk_high",
            "score": score
        }

    return {
        "allowed": True,
        "score": score,
        "reason": "ok",
        "target": target
    }
