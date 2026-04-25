from __future__ import annotations

from typing import Any


DEFAULT_WEIGHTS = {
    "dev_wallet_alpha": 0.25,
    "sniper_early": 0.25,
    "ml_gnn_fund_brain": 0.30,
    "market_alpha": 0.10,
    "orderbook_microstructure": 0.10,
}


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def normalize(weights: dict) -> dict:
    total = sum(max(0.0, _f(v)) for v in weights.values())
    if total <= 0:
        return DEFAULT_WEIGHTS.copy()
    return {k: max(0.0, _f(v)) / total for k, v in weights.items()}


def allocator_get_budget(strategy_id: str, capital: float = 100, stats: dict | None = None, **kwargs) -> dict:
    weights = DEFAULT_WEIGHTS.copy()

    stats = stats or {}
    s = stats.get(strategy_id, {}) if isinstance(stats, dict) else {}

    winrate = _f(s.get("winrate"), 0.5)
    pnl = _f(s.get("pnl"), 0.0)
    dd = _f(s.get("drawdown"), 0.0)

    if strategy_id in weights:
        factor = 1.0
        factor *= 0.75 + winrate
        factor *= 1.15 if pnl > 0 else 0.85
        factor *= max(0.4, 1.0 - dd)
        weights[strategy_id] *= factor

    weights = normalize(weights)
    w = weights.get(strategy_id, 0.05)

    return {
        "strategy_id": strategy_id,
        "weight": w,
        "budget": float(capital) * w,
        "weights": weights,
    }


def allocator_get_allocation_map(capital: float = 100, stats: dict | None = None, **kwargs) -> dict:
    weights = normalize(DEFAULT_WEIGHTS.copy())
    return {
        "capital": float(capital),
        "allocations": weights,
        "budgets": {k: float(capital) * v for k, v in weights.items()},
    }
