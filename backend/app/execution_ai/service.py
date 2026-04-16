from __future__ import annotations

import random


def predict_slippage(size_usd: float, regime: str) -> float:
    base = 8.0 if regime == "balanced" else 12.0 if regime == "bull" else 5.0
    return round(base + min(size_usd / 20.0, 20.0), 2)


def predict_fill_probability(regime: str) -> float:
    if regime == "bull":
        return 0.86
    if regime == "defensive":
        return 0.72
    return 0.80


def execute(symbol: str, size_usd: float, provider: str, paper_mode: bool) -> dict:
    if provider == "integration":
        # Safe integration point
        return {
            "ok": True,
            "provider": "integration_stub",
            "symbol": symbol,
            "size_usd": size_usd,
            "paper_mode": paper_mode,
        }

    return {
        "ok": True,
        "provider": "mock",
        "symbol": symbol,
        "size_usd": size_usd,
        "paper_mode": paper_mode,
    }


def realized_pnl(regime: str, strategy_name: str) -> float:
    bias = 5.0 if strategy_name == "Execution RL" else 3.0 if strategy_name == "Allocator Fusion" else 2.0
    if regime == "defensive":
        bias -= 4.0
    return round(random.uniform(-15, 20) + bias, 2)\n