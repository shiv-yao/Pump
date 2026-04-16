from __future__ import annotations


def policy_score(strategy_mode: str, regime: str) -> float:
    score = 0.5
    if strategy_mode == "aggressive":
        score += 0.2
    if regime == "bull":
        score += 0.15
    if regime == "defensive":
        score -= 0.1
    return round(score, 2)\n