from __future__ import annotations

from typing import Any

from app.utils.loader import call


DEFAULT_MARKETS = ["BTCUSDT"]
DEFAULT_CAPITAL = 100.0


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


async def _call_first(tool_names: list[str], payload: dict | None = None):
    payload = payload or {}
    last_error = None

    for name in tool_names:
        result = await call(name, payload)
        if not (isinstance(result, dict) and "error" in result):
            return result
        last_error = result

    return last_error or {"error": f"tool chain failed: {tool_names}"}


# =========================
# ENGINE WRAPPER
# =========================
async def start_engine(markets=None, capital=DEFAULT_CAPITAL, **kwargs):
    return await _call_first(
        ["start_v7_engine", "start_v6_engine"],
        {
            "markets": markets or DEFAULT_MARKETS,
            "capital": _safe_float(capital, DEFAULT_CAPITAL),
        }
    )


async def stop_engine(**kwargs):
    return await _call_first(
        ["stop_v7_engine", "stop_v6_engine"],
        {}
    )


async def get_state(**kwargs):
    return await _call_first(
        ["get_state", "state"],
        {}
    )


# =========================
# FUND DECISION
# =========================
async def fund_decide_trade(symbol, capital=DEFAULT_CAPITAL, **kwargs):
    symbol = symbol or "BTCUSDT"
    capital = _safe_float(capital, DEFAULT_CAPITAL)

    # ===== ALPHA =====
    alpha = await call("get_alpha_v2", {"asset_id": symbol})
    wallet = await call("get_wallet_alpha_v3", {"asset_id": symbol})

    if not isinstance(alpha, dict):
        return {"action": "hold", "reason": "alpha_unavailable"}

    base_score = _safe_float(alpha.get("score", 0.0), 0.0)
    base_side = str(alpha.get("action", "hold")).lower().strip() or "hold"

    wallet_score = _safe_float(wallet.get("score", 0.0), 0.0) if isinstance(wallet, dict) else 0.0
    wallet_side = str(wallet.get("action", "hold")).lower().strip() if isinstance(wallet, dict) else "hold"

    # ===== REGIME / PARAMS =====
    regime = await _call_first(["fb_get_regime", "get_market_regime"], {"symbol": symbol})
    regime_name = "unknown"
    if isinstance(regime, dict):
        regime_name = str(regime.get("regime", regime.get("state", "unknown")))

    params = await _call_first(["fb_adjust_params"], {"symbol": symbol})
    min_score = 0.5
    if isinstance(params, dict):
        min_score = _safe_float(params.get("min_score", params.get("entry_threshold", 0.5)), 0.5)

    # ===== FUSION =====
    if wallet_score > base_score:
        side = wallet_side
        score = wallet_score
        strategy_id = "wallet_alpha"
    else:
        side = base_side
        score = base_score
        strategy_id = "market_alpha"

    # ===== STRATEGY GATE =====
    gate = await _call_first(
        ["strategy_should_trade"],
        {"strategy_id": strategy_id, "regime": regime_name}
    )
    if isinstance(gate, dict) and not gate.get("trade", True):
        return {
            "action": "hold",
            "reason": gate.get("reason", "strategy_blocked"),
            "strategy_id": strategy_id,
            "score": score,
            "regime": regime_name,
        }

    # ===== FILTER =====
    if side == "hold":
        return {
            "action": "hold",
            "reason": "alpha_hold",
            "strategy_id": strategy_id,
            "score": score,
            "regime": regime_name,
        }

    if score < min_score:
        return {
            "action": "hold",
            "reason": "below_threshold",
            "strategy_id": strategy_id,
            "score": score,
            "regime": regime_name,
        }

    # ===== ALLOCATOR =====
    alloc = await _call_first(
        ["allocator_get_budget", "fb_position_size"],
        {
            "strategy_id": strategy_id,
            "capital": capital,
            "symbol": symbol,
            "asset_id": symbol,
        }
    )

    if not isinstance(alloc, dict):
        return {
            "action": "hold",
            "reason": "allocator_unavailable",
            "strategy_id": strategy_id,
            "score": score,
            "regime": regime_name,
        }

    budget = _safe_float(alloc.get("budget", alloc.get("size", 0.0)), 0.0)
    if budget <= 0:
        return {
            "action": "hold",
            "reason": "zero_budget",
            "strategy_id": strategy_id,
            "score": score,
            "regime": regime_name,
        }

    size = budget * 0.2

    # ===== CLAMP =====
    size = max(0.001, min(size, capital * 0.05))

    # ===== RISK =====
    risk = await _call_first(
        ["check_risk", "get_risk_state"],
        {
            "asset_id": symbol,
            "size": size,
            "capital": capital,
        }
    )

    if isinstance(risk, dict):
        if risk.get("allowed") is False:
            return {
                "action": "hold",
                "reason": risk.get("reason", "risk_blocked"),
                "strategy_id": strategy_id,
                "score": score,
                "regime": regime_name,
            }

        if risk.get("enabled") is False:
            return {
                "action": "hold",
                "reason": risk.get("last_status", "global_risk_off"),
                "strategy_id": strategy_id,
                "score": score,
                "regime": regime_name,
            }

    return {
        "action": side,
        "size": size,
        "strategy_id": strategy_id,
        "score": score,
        "regime": regime_name,
        "meta": {
            "base_score": base_score,
            "wallet_score": wallet_score,
            "min_score": min_score,
        }
    }


# =========================
# SINGLE FUND CYCLE
# =========================
async def run_fund_cycle(symbol="BTCUSDT", capital=DEFAULT_CAPITAL, **kwargs):
    symbol = symbol or "BTCUSDT"
    capital = _safe_float(capital, DEFAULT_CAPITAL)

    decision = await fund_decide_trade(symbol=symbol, capital=capital, **kwargs)

    if not isinstance(decision, dict):
        return {"error": "fund_decide_trade_failed"}

    action = str(decision.get("action", "hold")).lower().strip()
    size = _safe_float(decision.get("size", 0.0), 0.0)

    if action not in {"buy", "sell"} or size <= 0:
        return {
            "status": "no_trade",
            "symbol": symbol,
            "decision": decision,
        }

    # ===== PRICE =====
    price_data = await _call_first(
        ["price", "get_spot_price", "get_ticker_24h"],
        {"symbol": symbol}
    )

    # ===== EXECUTION =====
    trade_payload = {
        "symbol": symbol,
        "asset_id": symbol,
        "side": action,
        "size": size,
        "amount": size,
        "price": price_data.get("price") if isinstance(price_data, dict) else None,
        "strategy_id": decision.get("strategy_id", "fund_brain"),
    }

    trade_result = await _call_first(
        [
            "trade_order",
            "place_order",
            "buy_token" if action == "buy" else "sell_token",
            "simulate_order",
        ],
        trade_payload
    )

    return {
        "status": "ok",
        "symbol": symbol,
        "decision": decision,
        "price": price_data,
        "trade_result": trade_result,
    }
