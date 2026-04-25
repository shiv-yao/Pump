from __future__ import annotations

import os
from typing import Any

from app.utils.loader import call
from app.alpha.gnn_wallet_graph import get_wallet_score
from app.alpha.ml_alpha import predict

# ✅ 新增
from app.execution.orderbook_microstructure import analyze_orderbook
from app.execution.mev_guard import mev_risk
from app.portfolio.multi_strategy_allocator import allocator_get_budget


# =========================
# CONFIG
# =========================

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


# =========================
# MAIN DECISION
# =========================

async def decide_trade(symbol: str, capital: float = 100, **kwargs):
    symbol = symbol or kwargs.get("asset_id") or "BTCUSDT"
    capital = _f(capital, 100.0)

    # =========================
    # 1️⃣ DEV WALLET (最高優先)
    # =========================
    dev = await _safe_call("get_dev_signal", {"asset_id": symbol})

    if isinstance(dev, dict):
        dev_score = _f(dev.get("score"))
        if dev_score >= DEV_SCORE:
            return {
                "action": "buy",
                "size": min(capital * 0.06, MAX_SIZE),
                "reason": "dev_wallet",
                "score": dev_score,
                "strategy_id": "dev_wallet_alpha",
                "priority": "jito",
                "meta": dev,
            }

    # =========================
    # 2️⃣ GNN Wallet
    # =========================
    wallet_score = 0.0
    wallet_meta = {}

    try:
        wallet = await get_wallet_score(symbol)
        if isinstance(wallet, dict):
            wallet_score = _f(wallet.get("score"))
            wallet_meta = wallet
    except Exception as e:
        wallet_meta = {"error": str(e)}

    # =========================
    # 3️⃣ Market
    # =========================
    market = await _safe_call("get_market_features", {"symbol": symbol})

    if not isinstance(market, dict) or "error" in market:
        return {"action": "hold", "reason": "no_market"}

    liquidity = _f(market.get("liquidity"))
    impact = _f(market.get("price_impact"))

    if liquidity < MIN_LIQUIDITY:
        return {"action": "hold", "reason": "low_liquidity"}

    if impact > MAX_IMPACT:
        return {"action": "hold", "reason": "high_impact"}

    # =========================
    # 4️⃣ Orderbook Microstructure（🔥關鍵）
    # =========================
    book = await _safe_call("get_orderbook", {"symbol": symbol})

    trial_size = min(capital * 0.02, MAX_SIZE)

    micro = analyze_orderbook(book, trial_size) if isinstance(book, dict) else {"ok": False}

    if not micro.get("ok"):
        return {"action": "hold", "reason": "no_orderbook"}

    if micro.get("spread", 1) > 0.04:
        return {"action": "hold", "reason": "spread_too_wide"}

    if micro.get("impact", 1) > MAX_IMPACT:
        return {"action": "hold", "reason": "orderbook_impact_high"}

    # =========================
    # 5️⃣ ML Alpha
    # =========================
    features = {
        "momentum": _f(market.get("momentum")),
        "volume": _f(market.get("volume")),
        "liquidity": liquidity,
        "wallet_score": wallet_score,
    }

    ml = predict(features)

    score = _f(ml.get("score"))
    action = ml.get("action", "hold")

    if action != "buy" or score < MIN_SCORE:
        return {"action": "hold", "reason": "ml_filter", "score": score}

    # =========================
    # 6️⃣ MEV 防禦（🔥關鍵）
    # =========================
    mev = mev_risk(market, micro, priority="jito")

    if not mev.get("allowed"):
        return {
            "action": "hold",
            "reason": "mev_blocked",
            "mev": mev,
        }

    # =========================
    # 7️⃣ Fund Allocator（🔥資金分配）
    # =========================
    alloc = allocator_get_budget(
        strategy_id="ml_gnn_fund_brain",
        capital=capital,
    )

    budget = _f(alloc.get("budget"), capital * 0.03)

    # =========================
    # 8️⃣ Position Size（融合 micro + GNN）
    # =========================
    size = min(
        budget * (1 + wallet_score * 1.2) * micro.get("micro_score", 0.5),
        MAX_SIZE,
    )

    # =========================
    # 9️⃣ Risk Gate
    # =========================
    risk = await _safe_call("check_risk", {
        "symbol": symbol,
        "size": size,
        "capital": capital,
    })

    if isinstance(risk, dict) and risk.get("allowed") is False:
        return {"action": "hold", "reason": "risk_blocked"}

    return {
        "action": "buy",
        "size": size,
        "reason": "fund_brain_v12",
        "strategy_id": "ml_gnn_fund_brain",
        "score": score,
        "priority": "jito" if mev.get("use_jito") else "normal",
        "meta": {
            "wallet_score": wallet_score,
            "wallet": wallet_meta,
            "features": features,
            "micro": micro,
            "mev": mev,
            "allocator": alloc,
        },
    }


# =========================
# EXECUTION
# =========================

async def run_fund_cycle(symbol: str = "BTCUSDT", capital: float = 100, **kwargs):
    decision = await decide_trade(symbol, capital, **kwargs)

    if decision.get("action") != "buy":
        return {"status": "no_trade", "decision": decision}

    payload = {
        "symbol": symbol,
        "side": "buy",
        "size": decision["size"],
        "priority": decision.get("priority", "normal"),
        "strategy_id": decision.get("strategy_id"),
    }

    result = await _safe_call("trade_order", payload)

    return {
        "status": "submitted",
        "decision": decision,
        "result": result,
    }
