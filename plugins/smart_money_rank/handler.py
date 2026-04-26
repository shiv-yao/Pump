from __future__ import annotations

from typing import Any
from app.utils.loader import call


def _f(x: Any, default: float = 0.0):
    try:
        return float(x)
    except:
        return default


async def get_smart_money_score(symbol=None, asset_id=None, **kwargs):
    target = symbol or asset_id or "BTCUSDT"

    # ===== wallet alpha =====
    wallet = await call("get_wallet_alpha_v3", {"asset_id": target})
    if not isinstance(wallet, dict):
        wallet = await call("get_wallet_alpha_v2", {"asset_id": target})

    wallet_score = _f(wallet.get("score", 0.0), 0.0) if isinstance(wallet, dict) else 0.0
    wallet_action = str(wallet.get("action", "hold")).lower() if isinstance(wallet, dict) else "hold"

    # ===== flow proxy (未來可接 onchain flow) =====
    flow_score = min(wallet_score * 0.8, 1.0)

    # ===== fusion =====
    score = wallet_score * 0.7 + flow_score * 0.3

    # ===== direction =====
    if score > 0.65:
        action = wallet_action if wallet_action != "hold" else "buy"
    elif score < 0.35:
        action = "sell"
    else:
        action = "hold"

    return {
        "score": round(score, 4),
        "direction": action,
        "source": "smart_money",
        "target": target
    }
