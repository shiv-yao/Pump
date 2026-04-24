from __future__ import annotations

import os
from typing import Any

from app.utils.loader import call
from app.alpha.gnn_wallet_graph import get_wallet_score
from app.alpha.ml_alpha import predict


MIN_SCORE = float(os.getenv("MIN_SCORE", os.getenv("FB_THRESHOLD_MIN", "0.60")))
MAX_SIZE = float(os.getenv("MAX_POSITION_SIZE", os.getenv("SNIPER_MAX_SIZE", "0.05")))
MIN_LIQUIDITY = float(os.getenv("EARLY_MIN_LIQ", os.getenv("RUG_LIQ_MIN", "300")))
MAX_IMPACT = float(os.getenv("EARLY_MAX_IMPACT", "0.15"))
DEV_SCORE = float(os.getenv("DEV_SIGNAL_THRESHOLD", "0.80"))


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


async def _safe_call(name: str, payload: dict | None = None):
    try:
        return await call(name, payload or {})
    except Exception as e:
        return {"error": f"{name} failed: {str(e)}"}


async def fund_decide_trade(symbol: str, capital: float = 100, **kwargs):
    return await decide_trade(symbol=symbol, capital=capital, **kwargs)


async def decide_trade(symbol: str, capital: float = 100, **kwargs):
    symbol = symbol or kwargs.get("asset_id") or "BTCUSDT"
    capital = _f(capital, 100.0)

    # =========================
    # 1. DEV WALLET 最高優先
    # =========================
    dev = await _safe_call("get_dev_signal", {"asset_id": symbol, "symbol": symbol})

    if isinstance(dev, dict):
        dev_score = _f(dev.get("score"), 0.0)

        if dev_score >= DEV_SCORE:
            return {
                "action": "buy",
                "size": min(capital * 0.06, MAX_SIZE),
                "reason": "dev_wallet",
                "score": dev_score,
                "strategy_id": "dev_wallet_alpha",
                "priority": "jito",
                "meta": {
                    "source": "dev_wallet",
                    "wallet": dev.get("wallet"),
                    "raw": dev,
                },
            }

    # =========================
    # 2. GNN Wallet Graph
    # =========================
    wallet_score = 0.0
    wallet_meta = {}

    try:
        wallet = await get_wallet_score(symbol)
        if isinstance(wallet, dict):
            wallet_score = _f(wallet.get("score"), 0.0)
            wallet_meta = wallet
    except Exception as e:
        wallet_meta = {"error": str(e)}

    # =========================
    # 3. Market Features
    # =========================
    market = await _safe_call("get_market_features", {"symbol": symbol, "asset_id": symbol})

    if not isinstance(market, dict) or "error" in market:
        return {
            "action": "hold",
            "reason": "no_market",
            "symbol": symbol,
            "market": market,
        }

    liquidity = _f(market.get("liquidity"), 0.0)
    impact = _f(market.get("price_impact", market.get("impact", 0.0)), 0.0)

    if liquidity < MIN_LIQUIDITY:
        return {
            "action": "hold",
            "reason": "low_liquidity",
            "liquidity": liquidity,
            "min_liquidity": MIN_LIQUIDITY,
        }

    if impact > MAX_IMPACT:
        return {
            "action": "hold",
            "reason": "high_impact",
            "impact": impact,
            "max_impact": MAX_IMPACT,
        }

    features = {
        "momentum": _f(market.get("momentum"), 0.0),
        "volume": _f(market.get("volume"), 0.0),
        "liquidity": liquidity,
        "price_impact": impact,
        "wallet_score": wallet_score,
    }

    # =========================
    # 4. ML Alpha
    # =========================
    try:
        ml = predict(features)
    except Exception as e:
        return {
            "action": "hold",
            "reason": "ml_error",
            "error": str(e),
            "features": features,
        }

    if not isinstance(ml, dict):
        return {
            "action": "hold",
            "reason": "ml_invalid",
            "features": features,
        }

    score = _f(ml.get("score"), 0.0)
    action = str(ml.get("action", "hold")).lower().strip()

    if action != "buy" or score < MIN_SCORE:
        return {
            "action": "hold",
            "reason": "ml_filter",
            "score": score,
            "min_score": MIN_SCORE,
            "features": features,
        }

    # =========================
    # 5. Dynamic Position Sizing
    # =========================
    size = min(
        capital * 0.02 * (1 + wallet_score * 1.5),
        MAX_SIZE,
    )

    # =========================
    # 6. Risk Gate
    # =========================
    risk = await _safe_call("check_risk", {
        "symbol": symbol,
        "asset_id": symbol,
        "size": size,
        "capital": capital,
    })

    if isinstance(risk, dict):
        if risk.get("allowed") is False:
            return {
                "action": "hold",
                "reason": risk.get("reason", "risk_blocked"),
                "risk": risk,
            }
        if risk.get("enabled") is False:
            return {
                "action": "hold",
                "reason": risk.get("last_status", "risk_disabled"),
                "risk": risk,
            }

    return {
        "action": "buy",
        "size": size,
        "amount": size,
        "reason": "ml+gnn",
        "strategy_id": "ml_gnn_fund_brain",
        "score": score,
        "priority": "jito" if score > 0.75 else "normal",
        "symbol": symbol,
        "asset_id": symbol,
        "meta": {
            "wallet_score": wallet_score,
            "wallet": wallet_meta,
            "features": features,
            "ml": ml,
            "risk": risk,
        },
    }


async def run_fund_cycle(symbol: str = "BTCUSDT", capital: float = 100, **kwargs):
    decision = await decide_trade(symbol=symbol, capital=capital, **kwargs)

    if not isinstance(decision, dict):
        return {"error": "decision_failed"}

    action = str(decision.get("action", "hold")).lower()
    size = _f(decision.get("size"), 0.0)

    if action not in {"buy", "sell"} or size <= 0:
        return {
            "status": "no_trade",
            "symbol": symbol,
            "decision": decision,
        }

    payload = {
        "symbol": symbol,
        "asset_id": symbol,
        "side": action,
        "size": size,
        "amount": size,
        "strategy_id": decision.get("strategy_id", "fund_brain"),
        "priority": decision.get("priority", "normal"),
    }

    result = await _safe_call("trade_order", payload)

    return {
        "status": "submitted" if not (isinstance(result, dict) and "error" in result) else "error",
        "symbol": symbol,
        "decision": decision,
        "trade_result": result,
    }
