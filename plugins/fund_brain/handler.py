from __future__ import annotations

from typing import Any
from app.utils.loader import call


DEFAULT_MARKETS = ["BTCUSDT"]
DEFAULT_CAPITAL = 100.0


def _f(x: Any, default: float = 0.0) -> float:
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


async def start_engine(markets=None, capital=DEFAULT_CAPITAL, **kwargs):
    return await _call_first(
        ["start_v7_engine", "start_v6_engine"],
        {
            "markets": markets or DEFAULT_MARKETS,
            "capital": _f(capital, DEFAULT_CAPITAL),
        }
    )


async def stop_engine(**kwargs):
    return await _call_first(["stop_v7_engine", "stop_v6_engine"], {})


async def get_state(**kwargs):
    return await _call_first(["get_state", "state"], {})


async def fund_decide_trade(symbol, capital=DEFAULT_CAPITAL, **kwargs):
    symbol = symbol or "BTCUSDT"
    capital = _f(capital, DEFAULT_CAPITAL)

    alpha = await _call_first(["get_alpha_v2", "get_alpha_signal"], {"asset_id": symbol, "symbol": symbol})
    wallet = await _call_first(["get_wallet_alpha_v3", "get_wallet_alpha_v2"], {"asset_id": symbol, "symbol": symbol})
    smart = await _call_first(["get_smart_money_score"], {"asset_id": symbol, "symbol": symbol})
    regime = await _call_first(["fb_get_regime", "get_market_regime"], {"symbol": symbol})
    rug = await _call_first(["rug_check"], {"asset_id": symbol, "symbol": symbol})

    if isinstance(rug, dict) and rug.get("allowed") is False:
        return {"action": "hold", "reason": rug.get("reason", "rug_blocked")}

    base_score = _f(alpha.get("score", 0.0), 0.0) if isinstance(alpha, dict) else 0.0
    base_side = str(alpha.get("action", "hold")).lower().strip() if isinstance(alpha, dict) else "hold"

    wallet_score = _f(wallet.get("score", 0.0), 0.0) if isinstance(wallet, dict) else 0.0
    wallet_side = str(wallet.get("action", "hold")).lower().strip() if isinstance(wallet, dict) else "hold"

    smart_score = _f(smart.get("score", 0.0), 0.0) if isinstance(smart, dict) else 0.0
    smart_side = str(smart.get("direction", "hold")).lower().strip() if isinstance(smart, dict) else "hold"

    final_score = base_score * 0.45 + wallet_score * 0.35 + smart_score * 0.20
    side = base_side
    strategy_id = "market_alpha"

    if wallet_score > base_score and wallet_side != "hold":
        side = wallet_side
        strategy_id = "wallet_alpha"

    if smart_score > 0.7 and smart_side != "hold":
        side = smart_side
        strategy_id = "smart_money"

    regime_name = str(regime.get("regime", "unknown")) if isinstance(regime, dict) else "unknown"

    if regime_name == "range":
        final_score *= 0.85
    elif regime_name == "risk_off":
        return {"action": "hold", "reason": "risk_off_regime"}

    gate = await _call_first(
        ["strategy_should_trade"],
        {"strategy_id": strategy_id, "regime": regime_name}
    )
    if isinstance(gate, dict) and not gate.get("trade", True):
        return {"action": "hold", "reason": gate.get("reason", "strategy_blocked")}

    params = await _call_first(["fb_adjust_params"], {"symbol": symbol})
    min_score = 0.60
    if isinstance(params, dict):
        min_score = _f(params.get("min_score", params.get("entry_threshold", 0.60)), 0.60)

    if side == "hold" or final_score < min_score:
        return {
            "action": "hold",
            "reason": "below_threshold",
            "score": final_score,
            "strategy_id": strategy_id,
            "regime": regime_name,
        }

    alloc = await _call_first(
        ["allocator_get_budget", "fb_position_size"],
        {"strategy_id": strategy_id, "capital": capital, "symbol": symbol, "asset_id": symbol}
    )
    if not isinstance(alloc, dict):
        return {"action": "hold", "reason": "allocator_unavailable"}

    budget = _f(alloc.get("budget", alloc.get("size", 0.0)), 0.0)
    if budget <= 0:
        return {"action": "hold", "reason": "zero_budget"}

    size = budget * 0.25
    size = max(0.001, min(size, capital * 0.05))

    risk = await _call_first(
        ["check_risk", "get_risk_state"],
        {"asset_id": symbol, "size": size, "capital": capital}
    )
    if isinstance(risk, dict):
        if risk.get("allowed") is False:
            return {"action": "hold", "reason": risk.get("reason", "risk_blocked")}
        if risk.get("enabled") is False:
            return {"action": "hold", "reason": risk.get("last_status", "global_risk_off")}

    return {
        "action": side,
        "size": size,
        "strategy_id": strategy_id,
        "score": final_score,
        "regime": regime_name,
        "meta": {
            "base_score": base_score,
            "wallet_score": wallet_score,
            "smart_score": smart_score
        }
    }


async def run_fund_cycle(symbol="BTCUSDT", capital=DEFAULT_CAPITAL, **kwargs):
    decision = await fund_decide_trade(symbol=symbol, capital=capital, **kwargs)

    if not isinstance(decision, dict):
        return {"error": "fund_decide_trade_failed"}

    action = str(decision.get("action", "hold")).lower().strip()
    size = _f(decision.get("size", 0.0), 0.0)

    if action not in {"buy", "sell"} or size <= 0:
        return {"status": "no_trade", "symbol": symbol, "decision": decision}

    price_data = await _call_first(
        ["price", "get_spot_price", "get_ticker_24h"],
        {"symbol": symbol}
    )

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
        ["trade_order", "place_order", "buy_token" if action == "buy" else "sell_token", "simulate_order"],
        trade_payload
    )

    return {
        "status": "ok",
        "symbol": symbol,
        "decision": decision,
        "price": price_data,
        "trade_result": trade_result
    }
