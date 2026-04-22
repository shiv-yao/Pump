from __future__ import annotations

from typing import Any
from app.utils.loader import call


DEFAULT_MARKETS = ["BTCUSDT"]
DEFAULT_CAPITAL = 100.0

# ===== early alpha params =====
EARLY_WALLET_MIN = 0.60
EARLY_RUG_MAX = 0.70
EARLY_ENTRY_FRAC = 0.005       # 第一筆試單 0.5%
EARLY_ADDON_FRAC = 0.015       # 通過後加倉 1.5%
EARLY_MAX_IMPACT = 0.15
EARLY_MIN_LIQ = 300.0


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


# =========================
# ENGINE WRAPPER
# =========================
async def start_engine(markets=None, capital=DEFAULT_CAPITAL, **kwargs):
    return await _call_first(
        ["start_v7_engine", "start_v6_engine"],
        {
            "markets": markets or DEFAULT_MARKETS,
            "capital": _f(capital, DEFAULT_CAPITAL),
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
# EARLY FILTERS
# =========================
async def _wallet_gate(symbol: str):
    wallet = await _call_first(
        ["get_wallet_alpha_v3", "get_wallet_alpha_v2", "get_wallet_alpha"],
        {"asset_id": symbol}
    )

    if not isinstance(wallet, dict):
        return {
            "ok": False,
            "reason": "wallet_unavailable",
            "wallet_score": 0.0,
            "wallet_action": "hold",
        }

    wallet_score = _f(wallet.get("score", 0.0), 0.0)
    wallet_action = str(wallet.get("action", "hold")).lower().strip()

    if wallet_score < EARLY_WALLET_MIN:
        return {
            "ok": False,
            "reason": "wallet_too_weak",
            "wallet_score": wallet_score,
            "wallet_action": wallet_action,
        }

    return {
        "ok": True,
        "reason": "ok",
        "wallet_score": wallet_score,
        "wallet_action": wallet_action,
    }


async def _rug_gate(symbol: str):
    rug = await _call_first(
        ["rug_check"],
        {"asset_id": symbol, "symbol": symbol}
    )

    if not isinstance(rug, dict):
        return {"ok": False, "reason": "rug_unavailable", "rug_score": 1.0}

    rug_score = _f(rug.get("score", 1.0), 1.0)
    allowed = rug.get("allowed", True)

    if allowed is False or rug_score > EARLY_RUG_MAX:
        return {
            "ok": False,
            "reason": rug.get("reason", "rug_risk"),
            "rug_score": rug_score,
        }

    return {
        "ok": True,
        "reason": "ok",
        "rug_score": rug_score,
    }


async def _market_quality_gate(symbol: str):
    """
    這裡先用 price / liquidity proxy。
    若你之後有真 liquidity / price impact plugin，可直接替換。
    """
    price_data = await _call_first(
        ["price", "get_spot_price", "get_ticker_24h"],
        {"symbol": symbol}
    )

    if not isinstance(price_data, dict):
        return {"ok": False, "reason": "no_price", "liquidity": 0.0, "impact": 1.0}

    liquidity = _f(price_data.get("liquidity", EARLY_MIN_LIQ), EARLY_MIN_LIQ)
    impact = _f(price_data.get("price_impact", 0.0), 0.0)

    if liquidity < EARLY_MIN_LIQ:
        return {"ok": False, "reason": "low_liquidity", "liquidity": liquidity, "impact": impact}

    if impact > EARLY_MAX_IMPACT:
        return {"ok": False, "reason": "high_price_impact", "liquidity": liquidity, "impact": impact}

    return {"ok": True, "reason": "ok", "liquidity": liquidity, "impact": impact}


# =========================
# FUND DECISION
# =========================
async def fund_decide_trade(symbol, capital=DEFAULT_CAPITAL, **kwargs):
    symbol = symbol or "BTCUSDT"
    capital = _f(capital, DEFAULT_CAPITAL)

    alpha = await _call_first(
        ["get_alpha_v2", "get_alpha_signal"],
        {"asset_id": symbol, "symbol": symbol}
    )

    if not isinstance(alpha, dict):
        return {"action": "hold", "reason": "alpha_unavailable"}

    base_score = _f(alpha.get("score", 0.0), 0.0)
    base_side = str(alpha.get("action", "hold")).lower().strip() or "hold"

    # ===== early wallet gate =====
    wallet_gate = await _wallet_gate(symbol)
    if not wallet_gate["ok"]:
        return {
            "action": "hold",
            "reason": wallet_gate["reason"],
            "wallet_score": wallet_gate.get("wallet_score", 0.0),
        }

    wallet_score = _f(wallet_gate["wallet_score"], 0.0)
    wallet_side = wallet_gate.get("wallet_action", "hold")

    # ===== rug gate =====
    rug_gate = await _rug_gate(symbol)
    if not rug_gate["ok"]:
        return {
            "action": "hold",
            "reason": rug_gate["reason"],
            "rug_score": rug_gate.get("rug_score", 1.0),
        }

    # ===== market quality =====
    quality_gate = await _market_quality_gate(symbol)
    if not quality_gate["ok"]:
        return {
            "action": "hold",
            "reason": quality_gate["reason"],
            "liquidity": quality_gate.get("liquidity", 0.0),
            "impact": quality_gate.get("impact", 1.0),
        }

    # ===== regime =====
    regime = await _call_first(["fb_get_regime", "get_market_regime"], {"symbol": symbol})
    regime_name = "unknown"
    if isinstance(regime, dict):
        regime_name = str(regime.get("regime", regime.get("state", "unknown")))

    if regime_name == "risk_off":
        return {"action": "hold", "reason": "risk_off_regime"}

    # ===== alpha fusion =====
    if wallet_score > base_score and wallet_side != "hold":
        side = wallet_side
        score = wallet_score
        strategy_id = "wallet_alpha"
    else:
        side = base_side
        score = base_score
        strategy_id = "market_alpha"

    # ===== strategy gate =====
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
        }

    # ===== threshold =====
    params = await _call_first(["fb_adjust_params"], {"symbol": symbol})
    min_score = 0.60
    if isinstance(params, dict):
        min_score = _f(params.get("min_score", params.get("entry_threshold", 0.60)), 0.60)

    if side == "hold" or score < min_score:
        return {
            "action": "hold",
            "reason": "below_threshold",
            "strategy_id": strategy_id,
            "score": score,
        }

    # ===== allocator =====
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
        return {"action": "hold", "reason": "allocator_unavailable"}

    budget = _f(alloc.get("budget", alloc.get("size", 0.0)), 0.0)
    if budget <= 0:
        return {"action": "hold", "reason": "zero_budget"}

    # ===== early entry =====
    # 第一筆先很小
    trial_size = max(0.001, min(capital * EARLY_ENTRY_FRAC, capital * 0.01))
    # 若條件很好，再放大到 allocator budget 的部分
    full_size = max(0.001, min(budget * EARLY_ADDON_FRAC / max(EARLY_ENTRY_FRAC, 1e-9), capital * 0.05))

    # 這裡直接回早期入場倉位，等下一輪再擴大
    size = min(trial_size, full_size)

    # ===== risk =====
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
            }
        if risk.get("enabled") is False:
            return {
                "action": "hold",
                "reason": risk.get("last_status", "global_risk_off"),
                "strategy_id": strategy_id,
                "score": score,
            }

    return {
        "action": side,
        "size": size,
        "strategy_id": strategy_id,
        "score": score,
        "regime": regime_name,
        "meta": {
            "wallet_score": wallet_score,
            "rug_score": rug_gate["rug_score"],
            "liquidity": quality_gate["liquidity"],
            "impact": quality_gate["impact"],
            "entry_mode": "early_trial"
        }
    }


# =========================
# SINGLE FUND CYCLE
# =========================
async def run_fund_cycle(symbol="BTCUSDT", capital=DEFAULT_CAPITAL, **kwargs):
    symbol = symbol or "BTCUSDT"
    capital = _f(capital, DEFAULT_CAPITAL)

    decision = await fund_decide_trade(symbol=symbol, capital=capital, **kwargs)

    if not isinstance(decision, dict):
        return {"error": "fund_decide_trade_failed"}

    action = str(decision.get("action", "hold")).lower().strip()
    size = _f(decision.get("size", 0.0), 0.0)

    if action not in {"buy", "sell"} or size <= 0:
        return {
            "status": "no_trade",
            "symbol": symbol,
            "decision": decision,
        }

    trade_payload = {
        "symbol": symbol,
        "asset_id": symbol,
        "side": action,
        "size": size,
        "amount": size,
        "strategy_id": decision.get("strategy_id", "fund_brain"),
    }

    # ===== real execution first =====
    trade_result = await _call_first(["trade_order"], trade_payload)

    # ===== fallback =====
    if isinstance(trade_result, dict) and "error" in trade_result:
        price_data = await _call_first(
            ["price", "get_spot_price", "get_ticker_24h"],
            {"symbol": symbol}
        )

        trade_payload["price"] = price_data.get("price") if isinstance(price_data, dict) else None

        sim_result = await _call_first(["simulate_order"], trade_payload)

        return {
            "status": "fallback_simulated",
            "symbol": symbol,
            "decision": decision,
            "trade_result": sim_result,
            "real_error": trade_result,
        }

    return {
        "status": "ok",
        "symbol": symbol,
        "decision": decision,
        "trade_result": trade_result,
    }
