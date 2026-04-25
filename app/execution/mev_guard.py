from __future__ import annotations

from typing import Any


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def mev_risk(market: dict, micro: dict, priority: str = "normal") -> dict:
    impact = _f(micro.get("impact"))
    spread = _f(micro.get("spread"))
    volatility = _f(market.get("volatility", 0.02))
    recent_volume = _f(market.get("volume", 0))

    risk = 0.0
    risk += min(0.35, impact * 2.0)
    risk += min(0.25, spread * 3.0)
    risk += min(0.25, volatility * 4.0)

    if recent_volume <= 0:
        risk += 0.10

    if priority == "jito":
        risk *= 0.65

    risk = max(0.0, min(1.0, risk))

    return {
        "allowed": risk < 0.55,
        "risk": risk,
        "reason": "ok" if risk < 0.55 else "mev_or_sandwich_risk",
        "use_jito": risk >= 0.25 or priority == "jito",
        "suggested_priority": "jito" if risk >= 0.25 else priority,
    }
