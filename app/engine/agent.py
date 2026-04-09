from app.engine import runtime as rt
from app.engine.risk import detect_regime, institutional_daily_loss_hit, institutional_paused
from app.engine.utils import clamp, now, recent_closed_trades, sf

def agent_in_cooldown():
    return now() < sf(rt.AGENT_STATE.get("cooldown_until", 0.0), 0.0)

def agent_recent_rows():
    return [x for x in recent_closed_trades(rt.AGENT_LOOKBACK_TRADES) if isinstance(x, dict)]

def agent_loss_streak(rows=None):
    rows = rows or agent_recent_rows()
    streak = 0
    for r in reversed(rows):
        if sf(r.get("pnl"), 0.0) < 0:
            streak += 1
        else:
            break
    return streak

def agent_update():
    if now() - sf(rt.AGENT_STATE.get("last_update", 0.0), 0.0) < rt.AGENT_UPDATE_SEC:
        return
    rows = agent_recent_rows()
    if len(rows) < rt.AGENT_MIN_TRADES:
        rt.AGENT_STATE["last_update"] = now()
        rt.AGENT_STATE["last_reason"] = "not_enough_trades"
        return

    pnls = [sf(x.get("pnl"), 0.0) for x in rows]
    wins = sum(1 for x in pnls if x > 0)
    count = len(pnls)
    winrate = wins / count if count else 0.0
    avg_pnl = sum(pnls) / count if count else 0.0
    streak = agent_loss_streak(rows)

    mode = "normal"
    reason = "balanced"
    if streak >= rt.AGENT_KILL_LOSS_STREAK:
        rt.AGENT_STATE["cooldown_until"] = now() + rt.AGENT_KILL_COOLDOWN_SEC
        mode = "defensive"
        reason = f"kill_loss_streak_{streak}"
    elif winrate >= rt.AGENT_BULL_WINRATE and avg_pnl > 0:
        mode = "aggressive"
        reason = "good_recent_performance"
    elif winrate <= rt.AGENT_BEAR_WINRATE and avg_pnl < 0:
        mode = "defensive"
        reason = "bad_recent_performance"

    rt.AGENT_STATE["mode"] = mode
    rt.AGENT_STATE["confidence"] = clamp(winrate if count else 0.5, 0.1, 0.95)
    risk_mult = rt.AGENT_STATE.get("risk_mult", 1.0)
    if mode == "aggressive":
        risk_mult += 0.08
    elif mode == "defensive":
        risk_mult *= 0.82
    else:
        risk_mult += 0.03
    rt.AGENT_STATE["risk_mult"] = clamp(risk_mult, rt.AGENT_RISK_MIN, rt.AGENT_RISK_MAX)
    rt.AGENT_STATE["last_update"] = now()
    rt.AGENT_STATE["last_reason"] = reason

def agent_adjust_params():
    mode = rt.AGENT_STATE.get("mode", "normal")
    if mode == "aggressive":
        rt.AUTO_PARAMS.update({"entry_threshold": rt.AGENT_AGGRESSIVE_ENTRY, "take_profit": rt.AGENT_AGGRESSIVE_TP, "stop_loss": rt.AGENT_AGGRESSIVE_SL})
    elif mode == "defensive":
        rt.AUTO_PARAMS.update({"entry_threshold": rt.AGENT_DEFENSIVE_ENTRY, "take_profit": rt.AGENT_DEFENSIVE_TP, "stop_loss": rt.AGENT_DEFENSIVE_SL})
    else:
        rt.AUTO_PARAMS.update({"entry_threshold": rt.AGENT_NORMAL_ENTRY, "take_profit": rt.AGENT_NORMAL_TP, "stop_loss": rt.AGENT_NORMAL_SL})

def agent_effective_entry_threshold():
    return clamp(sf(rt.AUTO_PARAMS.get("entry_threshold", rt.ENTRY_THRESHOLD), rt.ENTRY_THRESHOLD), rt.ADAPTIVE_THRESHOLD_MIN, 0.20)

def agent_effective_tp():
    return sf(rt.AUTO_PARAMS.get("take_profit", rt.TAKE_PROFIT), rt.TAKE_PROFIT)

def agent_effective_sl():
    return sf(rt.AUTO_PARAMS.get("stop_loss", rt.STOP_LOSS), rt.STOP_LOSS)

def agent_force_trade_allowed():
    return rt.AGENT_FORCE_TRADE_ENABLE and (not agent_in_cooldown()) and rt.AGENT_STATE.get("mode") != "defensive" and (not institutional_paused()) and (not institutional_daily_loss_hit())

def current_dynamic_threshold():
    base = agent_effective_entry_threshold()
    regime = detect_regime()
    if regime == "bull":
        base *= 0.94
    elif regime == "bear":
        base *= 1.10
    if rt.engine.no_trade_cycles > 30:
        base *= 0.78
    elif rt.engine.no_trade_cycles > 15:
        base *= 0.90
    if rt.AGENT_STATE.get("mode") == "aggressive":
        base *= 0.96
    elif rt.AGENT_STATE.get("mode") == "defensive":
        base *= 1.05
    if institutional_paused() or institutional_daily_loss_hit():
        base *= 1.15
    return clamp(base, rt.ADAPTIVE_THRESHOLD_MIN, 0.20)
