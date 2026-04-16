from __future__ import annotations


def shadow_validation(strategy_mode: str, provider: str) -> dict:
    gap = 0.06 if provider == "mock" else 0.12
    approved = gap < 0.10 or strategy_mode == "safe"
    return {
        "approved": approved,
        "domain_gap": gap,
        "stage": "shadow" if approved else "rejected",
    }\n