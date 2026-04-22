from __future__ import annotations

from typing import Any

from app.utils.loader import call as shared_call


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
        result = await shared_call(name, payload)
        if not (isinstance(result, dict) and "error" in result):
            return result
        last_error = result

    return last_error or {"error": f"tool chain failed: {tool_names}"}


async def start_engine(markets=None, capital=DEFAULT_CAPITAL, **kwargs):
    payload = {
        "markets": markets or DEFAULT_MARKETS,
        "capital": _safe_float(capital, DEFAULT_CAPITAL),
    }

    return await _call_first(
        ["start_v7_engine", "start_v6_engine"],
        payload
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


async def fund_decide_trade(symbol: str = "BTCUSDT", capital: float = DEFAULT_CAPITAL, **kwargs):
    symbol = symbol or "BTCUSDT"
    capital = _safe_float(capital, DEFAULT_CAPITAL)

    price_info = await _call_first(
        ["price", "get_spot_price", "get_ticker_24h"],
        {"symbol": symbol}
    )

    alpha_info = await _call_first(
        ["get_alpha_v2", "get_alpha_signal", "get_trading_signal"],
        {"asset_id": symbol, "symbol": symbol}
    )

    regime_info = await _call_first(
        ["fb_get_regime"],
        {"symbol": symbol}
    )

    params_info = await _call_first(
        ["fb_adjust_params", "auto_optimize_env"],
        {}
    )

    sizing_payload = {
        "symbol": symbol,
        "asset_id": symbol,
        "capital": capital,
    }
    sizing_info = await _call_first(
        ["fb_position_size", "allocator_get_budget"],
        sizing_payload
    )

    risk_info = await _call_first(
        ["get_risk_state", "check_risk"],
        {"symbol": symbol, "asset_id": symbol}
    )

    score = 0.0
    action = "hold"
    size = 0.0

    if isinstance(alpha_info, dict):
        score = _safe_float(alpha_info.get("score", 0.0), 0.0)
        action = str(alpha_info.get("action", "hold")).lower().strip() or "hold"

    if isinstance(sizing_info, dict):
        size = _safe_float(
            sizing_info.get("size", sizing_info.get("budget", 0.0)),
            0.0
        )

    if isinstance(risk_info, dict):
        risk_level = _safe_float(risk_info.get("risk_level", 0.0), 0.0)
        can_trade = risk_info.get("can_trade", True)
        if risk_level > 0.8 or can_trade is False:
            action = "hold"
            size = 0.0

    if action == "hold":
        if score >= 0.7:
            action = "buy"
        elif score <= -0.7:
            action = "sell"

    return {
        "symbol": symbol,
        "capital": capital,
        "decision": {
            "action": action,
            "score": score,
            "size": size,
        },
        "inputs": {
            "price": price_info,
            "alpha": alpha_info,
            "regime": regime_info,
            "params": params_info,
            "sizing": sizing_info,
            "risk": risk_info,
        }
    }


async def run_fund_cycle(symbol: str = "BTCUSDT", capital: float = DEFAULT_CAPITAL, **kwargs):
    decision_bundle = await fund_decide_trade(symbol=symbol, capital=capital, **kwargs)

    if not isinstance(decision_bundle, dict) or "decision" not in decision_bundle:
        return {"error": "fund_decide_trade failed"}

    decision = decision_bundle.get("decision", {})
    action = str(decision.get("action", "hold")).lower().strip()
    size = _safe_float(decision.get("size", 0.0), 0.0)

    if action not in {"buy", "sell"} or size <= 0:
        return {
            "status": "no_trade",
            "symbol": symbol,
            "decision_bundle": decision_bundle
        }

    trade_payload = {
        "symbol": symbol,
        "asset_id": symbol,
        "side": action,
        "size": size,
        "amount": size,
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
        "decision_bundle": decision_bundle,
        "trade_result": trade_result,
    }
