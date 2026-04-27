from __future__ import annotations

import os
from typing import Any


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def kronos_score(candidate: dict) -> float:
    """Lightweight Kronos-compatible direction filter.

    Uses DEX momentum/volume fields now; can be replaced with real KronosPredictor later.
    Returns 0..1 where higher means better short-term direction.
    """
    if os.getenv("ENABLE_KRONOS_FILTER", "true").lower() not in {"1", "true", "yes", "on"}:
        return 1.0

    liq = _f(candidate.get("liquidity"), 0.0)
    vol = _f(candidate.get("volume"), 0.0)
    m5 = _f(candidate.get("price_change_m5"), 0.0)
    h1 = _f(candidate.get("price_change_h1"), 0.0)
    buys = _f(candidate.get("buys_h1"), 0.0)
    sells = _f(candidate.get("sells_h1"), 0.0)

    liq_s = min(liq / _f(os.getenv("KRONOS_LIQ_NORM", "50000"), 50000), 1.0)
    vol_s = min(vol / _f(os.getenv("KRONOS_VOL_NORM", "100000"), 100000), 1.0)
    mom_raw = max(min((m5 * 0.6 + h1 * 0.4) / 100.0, 1.0), -1.0)
    mom_s = max(mom_raw, 0.0)
    pressure = buys / max(buys + sells, 1.0)

    return max(0.0, min(1.0, liq_s * 0.20 + vol_s * 0.25 + mom_s * 0.35 + pressure * 0.20))


def allow_trade(candidate: dict) -> tuple[bool, float, str]:
    threshold = _f(os.getenv("KRONOS_MIN_SCORE", "0.55"), 0.55)
    score = kronos_score(candidate)
    if score < threshold:
        return False, score, f"kronos_low:{score:.3f}<{threshold:.3f}"
    return True, score, "kronos_ok"
