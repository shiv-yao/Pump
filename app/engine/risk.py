import time
import asyncio

from app.engine import runtime as rt
from app.engine.utils import clamp, now, safe_div, sf


def _ensure_runtime_state():
    if not hasattr(rt, "BREATHING_STATE") or rt.BREATHING_STATE is None:
        rt.BREATHING_STATE = {"risk_mult": 1.0, "cooldown_until": 0.0}

    if not hasattr(rt, "REGIME_STATE") or rt.REGIME_STATE is None:
        rt.REGIME_STATE = {"mode": "neutral", "last_update": 0.0}

    if not hasattr(rt, "INSTITUTIONAL_STATE") or rt.INSTITUTIONAL_STATE is None:
        rt.INSTITUTIONAL_STATE = {
            "pause_until": 0.0,
            "daily_realized_pnl_sol": 0.0,
            "day_bucket": int(time.time() // 86400),
            "last_reason": "boot",
        }

    if not hasattr(rt, "LAST_PRICE") or rt.LAST_PRICE is None:
        rt.LAST_PRICE = {}

    if not hasattr(rt, "LAST_MOMENTUM") or rt.LAST_MOMENTUM is None:
        rt.LAST_MOMENTUM = {}

    if not hasattr(rt, "engine"):
        raise RuntimeError("runtime.engine missing")


def _log(msg: str):
    try:
        if not hasattr(rt.engine, "logs") or rt.engine.logs is None:
            rt.engine.logs = []
        rt.engine.logs.append(str(msg))
        rt.engine.logs = rt.engine.logs[-1200:]
    except Exception:
        pass
    print(msg)


def _roll_day_if_needed():
    _ensure_runtime_state()
    bucket = int(time.time() // 86400)
    if bucket != rt.INSTITUTIONAL_STATE.get("day_bucket"):
        rt.INSTITUTIONAL_STATE["day_bucket"] = bucket
        rt.INSTITUTIONAL_STATE["daily_realized_pnl_sol"] = 0.0
        rt.INSTITUTIONAL_STATE["last_reason"] = "new_day"


def detect_regime():
    _ensure_runtime_state()

    trades = list(getattr(rt.engine, "trade_history", []) or [])
    if not trades:
        rt.REGIME_STATE["mode"] = "neutral"
        rt.REGIME_STATE["last_update"] = now()
        return "neutral"

    recent = trades[-10:]
    pnls = [sf(t.get("pnl", 0.0), 0.0) for t in recent if isinstance(t, dict)]
    if not pnls:
        rt.REGIME_STATE["mode"] = "neutral"
        rt.REGIME_STATE["last_update"] = now()
        return "neutral"

    avg = sum(pnls) / max(len(pnls), 1)

    if avg > 0.02:
        mode = "bull"
    elif avg < -0.01:
        mode = "bear"
    else:
        mode = "neutral"

    rt.REGIME_STATE["mode"] = mode
    rt.REGIME_STATE["last_update"] = now()
    return mode


def update_breathing_state():
    _ensure_runtime_state()

    recent = list(getattr(rt.engine, "trade_history", []) or [])
    lookback = max(8, int(getattr(rt, "BREATHING_LOSS_STREAK", 2)) + 2)
    recent = recent[-lookback:]

    streak = 0
    for t in reversed(recent):
        pnl = sf(t.get("pnl", 0.0), 0.0)
        if pnl <= 0:
            streak += 1
        else:
            break

    if streak >= getattr(rt, "BREATHING_LOSS_STREAK", 2):
        rt.BREATHING_STATE["risk_mult"] = max(
            getattr(rt, "BREATHING_MIN_RISK_MULT", 0.45),
            sf(rt.BREATHING_STATE.get("risk_mult", 1.0), 1.0) * 0.85,
        )
        rt.BREATHING_STATE["cooldown_until"] = now() + getattr(rt, "BREATHING_COOLDOWN_SEC", 180)
        _log(
            f"BREATHING cooldown streak={streak} "
            f"risk_mult={rt.BREATHING_STATE['risk_mult']:.2f}"
        )
    else:
        if now() >= sf(rt.BREATHING_STATE.get("cooldown_until", 0.0), 0.0):
            rt.BREATHING_STATE["risk_mult"] = min(
                getattr(rt, "BREATHING_MAX_RISK_MULT", 1.20),
                sf(rt.BREATHING_STATE.get("risk_mult", 1.0), 1.0) + 0.02,
            )


def institutional_daily_loss_hit():
    _roll_day_if_needed()

    daily_loss_limit = abs(sf(getattr(rt, "DAILY_LOSS_LIMIT_SOL", 0.60), 0.60))
    daily_realized = sf(rt.INSTITUTIONAL_STATE.get("daily_realized_pnl_sol", 0.0), 0.0)
    return daily_realized <= -daily_loss_limit


def hourly_loss_hit():
    _ensure_runtime_state()

    trades = list(getattr(rt.engine, "trade_history", []) or [])
    if not trades:
        return False

    cutoff = now() - 3600
    pnl_sol_sum = 0.0

    for t in trades:
        if not isinstance(t, dict):
            continue

        close_ts = sf(t.get("time_close", t.get("time", 0.0)), 0.0)
        if close_ts < cutoff:
            continue

        pnl_sol_sum += sf(t.get("pnl_sol", 0.0), 0.0)

    max_loss_per_hour = abs(sf(getattr(rt, "MAX_LOSS_PER_HOUR_SOL", 0.12), 0.12))
    return pnl_sol_sum <= -max_loss_per_hour


def max_trades_per_day_hit():
    _roll_day_if_needed()

    trades = list(getattr(rt.engine, "trade_history", []) or [])
    if not trades:
        return False

    current_bucket = int(time.time() // 86400)
    count = 0

    for t in trades:
        if not isinstance(t, dict):
            continue

        ts = sf(t.get("time_close", t.get("time", 0.0)), 0.0)
        if int(ts // 86400) == current_bucket:
            count += 1

    max_trades = int(getattr(rt, "MAX_TRADES_PER_DAY", 999999) or 999999)
    return count >= max_trades


def institutional_pause_active():
    _ensure_runtime_state()
    return now() < sf(rt.INSTITUTIONAL_STATE.get("pause_until", 0.0), 0.0)


def institutional_paused():
    return institutional_pause_active()


def institutional_loss_pause_if_needed():
    _roll_day_if_needed()

    if institutional_daily_loss_hit():
        rt.INSTITUTIONAL_STATE["pause_until"] = now() + getattr(rt, "INSTITUTIONAL_LOSS_PAUSE_SEC", 600)
        rt.INSTITUTIONAL_STATE["last_reason"] = "daily_loss_limit"
        _log("INSTITUTIONAL pause triggered by daily loss limit")
        return True

    if hourly_loss_hit():
        rt.INSTITUTIONAL_STATE["pause_until"] = now() + getattr(rt, "INSTITUTIONAL_LOSS_PAUSE_SEC", 600)
        rt.INSTITUTIONAL_STATE["last_reason"] = "hourly_loss_limit"
        _log("INSTITUTIONAL pause triggered by hourly loss limit")
        return True

    if max_trades_per_day_hit():
        rt.INSTITUTIONAL_STATE["pause_until"] = now() + getattr(rt, "INSTITUTIONAL_LOSS_PAUSE_SEC", 600)
        rt.INSTITUTIONAL_STATE["last_reason"] = "max_trades_per_day"
        _log("INSTITUTIONAL pause triggered by max trades per day")
        return True

    recent = list(getattr(rt.engine, "trade_history", []) or [])
    lookback = max(10, int(getattr(rt, "INSTITUTIONAL_LOSS_PAUSE_STREAK", 5)) + 2)
    recent = recent[-lookback:]

    streak = 0
    for t in reversed(recent):
        pnl = sf(t.get("pnl", 0.0), 0.0)
        if pnl <= 0:
            streak += 1
        else:
            break

    if streak >= getattr(rt, "INSTITUTIONAL_LOSS_PAUSE_STREAK", 5):
        rt.INSTITUTIONAL_STATE["pause_until"] = now() + getattr(rt, "INSTITUTIONAL_LOSS_PAUSE_SEC", 600)
        rt.INSTITUTIONAL_STATE["last_reason"] = "loss_streak"
        _log(f"INSTITUTIONAL pause triggered by streak={streak}")
        return True

    return False


async def check_sell(p):
    _ensure_runtime_state()

    try:
        from app.engine.sources import get_price
    except Exception:
        async def get_price(_mint):
            return None

    try:
        from app.engine.agent import agent_effective_sl, agent_effective_tp
    except Exception:
        def agent_effective_sl():
            return getattr(rt, "STOP_LOSS", -0.012)

        def agent_effective_tp():
            return getattr(rt, "TAKE_PROFIT", 0.022)

    try:
        from app.engine.execution import sell
    except Exception:
        async def sell(*args, **kwargs):
            return False

    m = p.get("mint")
    if not m:
        return False

    price = await get_price(m)
    entry = sf(p.get("entry_price", p.get("entry")), 0.0)
    if price is None or entry <= 0:
        return False

    p["price"] = price
    p["mark_price"] = price

    hold_sec = now() - sf(p.get("time", now()), now())
    if price < 1e-12 or hold_sec < 5:
        return False

    last = rt.LAST_PRICE.get(m)
    if last and last > 0:
        jump = abs(price - last) / last
        if jump > 0.25 and hold_sec < 20:
            return False

    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    entry_value = sf(p.get("entry_value", p.get("size", 0.0)), 0.0)
    if token_amount <= 0 or entry_value <= 0:
        return False

    market_value = token_amount * price
    pnl = clamp(
        safe_div(market_value - entry_value, entry_value, 0.0),
        -getattr(rt, "MAX_PNL_ABS", 0.20),
        getattr(rt, "MAX_PNL_ABS", 0.20),
    )

    p["high"] = max(sf(p.get("high", entry), entry), price)

    tier = p.get("tier") or (p.get("meta", {}) or {}).get("tier", "C")
    momentum_now = sf(rt.LAST_MOMENTUM.get(m, 0.0), 0.0)
    regime = detect_regime()

    hard_stop = getattr(rt, "HARD_STOP_LOSS", -0.020)
    if pnl <= hard_stop:
        return await sell(p, "HARD_STOP", price, 1.0)

    if hold_sec > getattr(rt, "FORCE_EXIT_SEC", 90):
        return await sell(p, "FORCE_EXIT", price, 1.0)

    fast_cut_line = -0.02 if regime != "bear" else -0.015
    if pnl < fast_cut_line and hold_sec > 20:
        return await sell(p, "FAST_CUT", price, 1.0)

    if pnl > 0 and momentum_now > 0.0035:
        return False

    if -0.02 < pnl < 0 and momentum_now > 0.0045:
        return False

    if pnl >= 0.008 and not p.get("tp1_done"):
        p["tp1_done"] = True
        return await sell(p, "PARTIAL_TP", price, 0.50)

    tp = agent_effective_tp()
    if tier == "A+":
        tp *= 2.2
    elif tier == "A":
        tp *= 1.8

    if regime == "bull":
        tp *= 1.15
    elif regime == "bear":
        tp *= 0.85

    if pnl >= tp:
        return await sell(p, "TP", price, 1.0)

    effective_sl = agent_effective_sl()
    if pnl <= effective_sl:
        await asyncio.sleep(0.4)
        price2 = await get_price(m)
        if price2:
            market_value2 = token_amount * price2
            pnl2 = clamp(
                safe_div(market_value2 - entry_value, entry_value, 0.0),
                -getattr(rt, "MAX_PNL_ABS", 0.20),
                getattr(rt, "MAX_PNL_ABS", 0.20),
            )
            if pnl2 <= effective_sl:
                return await sell(p, "SL", price2, 1.0)
        return False

    dynamic_trailing_gap = getattr(rt, "TRAILING_GAP", 0.01)
    dynamic_trailing_gap *= 1.15 if tier == "A+" else 1.0
    dynamic_trailing_gap *= 0.85 if regime == "bear" else 1.0

    if price < p["high"] * (1 - dynamic_trailing_gap):
        return await sell(p, "TRAIL", price, 1.0)

    dynamic_hold = int(
        getattr(rt, "MAX_HOLD_SEC", 120)
        * (1.25 if regime == "bull" else 0.70 if regime == "bear" else 1.0)
    )

    if hold_sec > dynamic_hold:
        if tier in {"A", "A+"} and momentum_now > 0.0025 and pnl > 0:
            return False
        if pnl < 0.003:
            return await sell(p, "TIME", price, 1.0)

    return False
