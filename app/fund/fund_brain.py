from __future__ import annotations
from typing import Any
from app.utils.loader import call

from app.alpha.gnn_wallet_graph import get_wallet_score
from app.alpha.ml_alpha import predict

# ===== config =====
MIN_SCORE = 0.60
MAX_SIZE = 0.05


def _f(x: Any, d: float = 0.0):
    try:
        return float(x)
    except:
        return d


async def decide_trade(symbol: str, capital: float = 100):

    # =========================
    # 1️⃣ DEV WALLET（最高優先）
    # =========================
    dev = await call("get_dev_signal", {"asset_id": symbol})

    if isinstance(dev, dict):
        dev_score = _f(dev.get("score"))

        if dev_score > 0.80:
            return {
                "action": "buy",
                "size": min(capital * 0.06, MAX_SIZE),
                "reason": "dev_wallet",
                "score": dev_score,
            }

    # =========================
    # 2️⃣ GNN Wallet Graph
    # =========================
    wallet = await get_wallet_score(symbol)
    wallet_score = _f(wallet.get("score"))

    # =========================
    # 3️⃣ Market Features
    # =========================
    market = await call("get_market_features", {"symbol": symbol})

    if not isinstance(market, dict):
        return {"action": "hold", "reason": "no_market"}

    features = {
        "momentum": _f(market.get("momentum")),
        "volume": _f(market.get("volume")),
        "liquidity": _f(market.get("liquidity")),
        "wallet_score": wallet_score,
    }

    # =========================
    # 4️⃣ ML Alpha
    # =========================
    ml = predict(features)

    score = _f(ml.get("score"))
    action = ml.get("action", "hold")

    if action != "buy" or score < MIN_SCORE:
        return {
            "action": "hold",
            "reason": "ml_filter",
            "score": score,
        }

    # =========================
    # 5️⃣ Position Sizing（重要）
    # =========================
    size = min(
        capital * 0.03 * (1 + wallet_score),
        MAX_SIZE
    )

    return {
        "action": "buy",
        "size": size,
        "reason": "ml+gnn",
        "score": score,
        "meta": {
            "wallet_score": wallet_score,
            "features": features
        }
    }
