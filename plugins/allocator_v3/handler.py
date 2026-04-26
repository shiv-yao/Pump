from __future__ import annotations

from typing import Any

from app.utils.loader import call


BASE_WEIGHTS = {
    "wallet_alpha": 0.45,
    "market_alpha": 0.35,
    "smart_money": 0.20,
}

BOOSTS = {}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, _f(v, 0.0)) for v in weights.values())
    if total <= 0:
        n = len(weights) or 1
        return {k: 1.0 / n for k in weights.keys()}
    return {k: max(0.0, _f(v, 0.0)) / total for k, v in weights.items()}


async def _get_regime_name(symbol=None, asset_id=None):
    regime = await call("fb_get_regime", {"symbol": symbol or asset_id})
    if isinstance(regime, dict) and "error" not in regime:
        return str(regime.get("regime", regime.get("state", "unknown")))
    regime = await call("get_market_regime", {"symbol": symbol or asset_id})
    if isinstance(regime, dict) and "error" not in regime:
        return str(regime.get("regime", regime.get("state", "unknown")))
    return "unknown"


async def _get_strategy_stats():
    stats = await call("strategy_get_stats", {})
    if isinstance(stats, dict) and "error" not in stats:
        return stats
    return {}


async def allocator_get_allocation_map(capital=100.0, **kwargs):
    capital = max(_f(capital, 100.0), 1e-9)

    weights = dict(BASE_WEIGHTS)
    stats = await _get_strategy_stats()

    # 1. performance tilt
    for sid, s in stats.items():
        if sid not in weights:
            continue

        pnl = _f(s.get("pnl", 0.0), 0.0)
        winrate = _f(s.get("winrate", 0.0), 0.0)
        dd = _f(s.get("drawdown", 0.0), 0.0)
        enabled = bool(s.get("enabled", True))

        if not enabled:
            weights[sid] *= 0.05
            continue

        if pnl > 0:
            weights[sid] *= 1.10
        if winrate > 0.55:
            weights[sid] *= 1.10
        if dd > abs(pnl) * 0.7 and pnl != 0:
            weights[sid] *= 0.75

    # 2. manual boosts
    for sid, factor in BOOSTS.items():
        if sid in weights:
            weights[sid] *= max(0.1, _f(factor, 1.0))

    weights = _normalize(weights)

    allocations = {
        sid: capital * w
        for sid, w in weights.items()
    }

    return {
        "capital": capital,
        "weights": weights,
        "allocations": allocations
    }


async def allocator_get_budget(strategy_id, capital=100.0, symbol=None, asset_id=None, **kwargs):
    strategy_id = strategy_id or "market_alpha"
    capital = max(_f(capital, 100.0), 1e-9)

    alloc_map = await allocator_get_allocation_map(capital=capital)
    if not isinstance(alloc_map, dict):
        return {"budget": 0.0}

    allocations = alloc_map.get("allocations", {})
    budget = _f(allocations.get(strategy_id, capital * 0.10), capital * 0.10)

    regime_name = await _get_regime_name(symbol=symbol, asset_id=asset_id)

    # regime-based scaling
    if regime_name == "trend":
        if strategy_id in {"market_alpha", "smart_money"}:
            budget *= 1.10
    elif regime_name == "range":
        if strategy_id == "market_alpha":
            budget *= 0.85
    elif regime_name == "risk_off":
        budget *= 0.50

    # global cap
    budget = min(budget, capital * 0.25)

    return {
        "budget": budget,
        "strategy_id": strategy_id,
        "regime": regime_name
    }


async def allocator_boost(strategy_id, factor=1.2, **kwargs):
    BOOSTS[strategy_id] = _f(factor, 1.2)
    return {
        "ok": True,
        "strategy_id": strategy_id,
        "factor": BOOSTS[strategy_id]
    }
