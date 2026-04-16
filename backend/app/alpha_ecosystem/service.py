from __future__ import annotations


def active_ecosystem() -> list[dict]:
    return [
        {"name": "Momentum", "weight_pct": 30.0, "species": "trend"},
        {"name": "Mean Reversion", "weight_pct": 20.0, "species": "reversion"},
        {"name": "Execution AI", "weight_pct": 25.0, "species": "execution"},
        {"name": "Allocator", "weight_pct": 25.0, "species": "meta"},
    ]\n