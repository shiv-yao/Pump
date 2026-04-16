from __future__ import annotations

from app.alpha_ecosystem.service import active_ecosystem


def investor_overview(metrics: dict) -> dict:
    return {
        "headline": "AI Fund investor overview",
        "summary": "Safe-by-default product with paper-first operating workflow and investor-grade reporting.",
        "ecosystem": active_ecosystem(),
        "metrics": metrics,
    }\n