from app.engine import runtime as rt
from app.engine.utils import clamp, log, now, recent_closed_trades, sf

def breathing_risk_mult():
    return clamp(sf(rt.BREATHING_STATE.get("risk_mult", 1.0), 1.0), rt.BREATHING_MIN_RISK_MULT, rt.BREATHING_MAX_RISK_MULT)

def update_breathing_state():
    rows = recent_closed_trades(6)
    if not rows:
        rt.BREATHING_STATE["risk_mult"] = 1.0
        return
    last2 = rows[-2:] if len(rows) >= 2 else rows
    streak = 0
    for r in reversed(last2):
        if sf(r.get("pnl"), 0.0) < 0:
            streak += 1
        else:
            break
    if streak >= rt.BREATHING_LOSS_STREAK:
        rt.BREATHING_STATE["risk_mult"] = max(rt.BREATHING_MIN_RISK_MULT, rt.BREATHING_STATE["risk_mult"] * 0.70)
        rt.BREATHING_STATE["cooldown_until"] = now() + rt.BREATHING_COOLDOWN_SEC
        log(f"BREATHING_DE_RISK streak={streak} risk={rt.BREATHING_STATE['risk_mult']:.2f}")
        return
    recent = rows[-3:]
    if recent and all(sf(x.get("pnl"), 0.0) > 0 for x in recent):
        rt.BREATHING_STATE["risk_mult"] = min(rt.BREATHING_MAX_RISK_MULT, rt.BREATHING_STATE["risk_mult"] + 0.08)
        return
    if now() > sf(rt.BREATHING_STATE.get("cooldown_until", 0.0), 0.0):
        rt.BREATHING_STATE["risk_mult"] = min(rt.BREATHING_MAX_RISK_MULT, rt.BREATHING_STATE["risk_mult"] + 0.03)

def detect_regime():
    if now() - sf(rt.REGIME_STATE.get("last_update", 0.0), 0.0) < 15:
        return rt.REGIME_STATE["mode"]
    rows = recent_closed_trades(8)
    if len(rows) < 4:
        rt.REGIME_STATE.update({"mode": "neutral", "last_update": now()})
        return "neutral"
    pnls = [sf(x.get("pnl"), 0.0) for x in rows]
    wins = sum(1 for x in pnls if x > 0)
    avg_pnl = sum(pnls) / max(len(pnls), 1)
    winrate = wins / max(len(pnls), 1)
    mode = "neutral"
    if winrate >= 0.60 and avg_pnl > 0:
        mode = "bull"
    elif winrate <= 0.30 and avg_pnl < 0:
        mode = "bear"
    rt.REGIME_STATE.update({"mode": mode, "last_update": now()})
    return mode

def buy_window_count():
    cutoff = now() - rt.BUY_WINDOW_SEC
    while rt.BUY_TIMES and rt.BUY_TIMES[0] < cutoff:
        rt.BUY_TIMES.pop(0)
    return len(rt.BUY_TIMES)

def institutional_day_reset():
    import time
    bucket = int(time.time() // 86400)
    if bucket != rt.INSTITUTIONAL_STATE["day_bucket"]:
        rt.INSTITUTIONAL_STATE["day_bucket"] = bucket
        rt.INSTITUTIONAL_STATE["daily_realized_pnl_sol"] = 0.0
        rt.INSTITUTIONAL_STATE["last_reason"] = "new_day"

def institutional_paused():
    institutional_day_reset()
    return now() < sf(rt.INSTITUTIONAL_STATE.get("pause_until", 0.0), 0.0)

def institutional_loss_pause_if_needed():
    rows = recent_closed_trades(10)
    streak = 0
    for r in reversed(rows):
        if sf(r.get("pnl"), 0.0) < 0:
            streak += 1
        else:
            break
    if streak >= rt.INSTITUTIONAL_LOSS_PAUSE_STREAK:
        rt.INSTITUTIONAL_STATE["pause_until"] = now() + rt.INSTITUTIONAL_LOSS_PAUSE_SEC
        rt.INSTITUTIONAL_STATE["last_reason"] = f"loss_streak_{streak}"
        log(f"INSTITUTIONAL_PAUSE streak={streak} sec={rt.INSTITUTIONAL_LOSS_PAUSE_SEC}")

def institutional_daily_loss_hit():
    institutional_day_reset()
    return rt.INSTITUTIONAL_STATE["daily_realized_pnl_sol"] <= -abs(rt.DAILY_LOSS_LIMIT_SOL)
