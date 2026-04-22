from __future__ import annotations

from typing import Any

# ===== GLOBAL RISK STATE =====
STATE = {
    "enabled": True,
    "daily_pnl": 0.0,
    "peak_pnl": 0.0,
    "drawdown": 0.0,
    "last_status": "OK",
    "max_daily_loss": -2.0,      # 絕對值，預設 -2
    "max_drawdown": -5.0,        # 絕對值，預設 -5
    "max_trade_frac": 0.05,      # 單筆最多 5% capital
    "max_position_frac": 0.20,   # 單市場最多 20% capital
}


POSITIONS: dict[str, float] = {}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _update_drawdown():
    peak = _f(STATE.get("peak_pnl", 0.0), 0.0)
    daily = _f(STATE.get("daily_pnl", 0.0), 0.0)

    if daily > peak:
        peak = daily
        STATE["peak_pnl"] = peak

    dd = daily - peak
    STATE["drawdown"] = dd
    return dd


async def check_risk(asset_id=None, size=0.0, capital=100.0, **kwargs):
    """
    給 fund_brain / execution_engine 用的即時風控閘門
    """
    size = _f(size, 0.0)
    capital = max(_f(capital, 100.0), 1e-9)
    asset_id = asset_id or "unknown"

    if not STATE["enabled"]:
        return {
            "allowed": False,
            "reason": STATE.get("last_status", "DISABLED"),
            "enabled": False
        }

    max_trade = capital * _f(STATE.get("max_trade_frac", 0.05), 0.05)
    if size > max_trade:
        return {
            "allowed": False,
            "reason": "size_too_large",
            "enabled": True,
            "max_trade": max_trade
        }

    current_pos = abs(_f(POSITIONS.get(asset_id, 0.0), 0.0))
    max_position = capital * _f(STATE.get("max_position_frac", 0.20), 0.20)

    if current_pos + size > max_position:
        return {
            "allowed": False,
            "reason": "position_limit",
            "enabled": True,
            "max_position": max_position,
            "current_position": current_pos
        }

    dd = _update_drawdown()
    max_daily_loss = _f(STATE.get("max_daily_loss", -2.0), -2.0)
    max_drawdown = _f(STATE.get("max_drawdown", -5.0), -5.0)

    if _f(STATE.get("daily_pnl", 0.0), 0.0) <= max_daily_loss:
        STATE["enabled"] = False
        STATE["last_status"] = "KILL_SWITCH_DAILY_LOSS"
        return {"allowed": False, "reason": STATE["last_status"], "enabled": False}

    if dd <= max_drawdown:
        STATE["enabled"] = False
        STATE["last_status"] = "KILL_SWITCH_DRAWDOWN"
        return {"allowed": False, "reason": STATE["last_status"], "enabled": False}

    return {
        "allowed": True,
        "reason": "ok",
        "enabled": True,
        "daily_pnl": STATE["daily_pnl"],
        "drawdown": STATE["drawdown"]
    }


async def record_risk_pnl(pnl=0.0, **kwargs):
    pnl = _f(pnl, 0.0)
    STATE["daily_pnl"] = _f(STATE.get("daily_pnl", 0.
