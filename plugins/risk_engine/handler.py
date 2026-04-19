STATE = {
    "enabled": True,
    "daily_pnl": 0.0,
    "max_daily_loss": -0.02,   # -2%
    "max_drawdown": -0.05,     # -5%
    "last_status": "OK"
}


def can_trade():
    return STATE["enabled"]


def check_risk(pnl: float):
    pnl = float(pnl)
    STATE["daily_pnl"] += pnl

    if STATE["daily_pnl"] <= STATE["max_daily_loss"]:
        STATE["enabled"] = False
        STATE["last_status"] = "KILL_SWITCH_DAILY_LOSS"
        return STATE["last_status"]

    if STATE["daily_pnl"] <= STATE["max_drawdown"]:
        STATE["enabled"] = False
        STATE["last_status"] = "KILL_SWITCH_DRAWDOWN"
        return STATE["last_status"]

    STATE["last_status"] = "OK"
    return STATE["last_status"]


def get_risk_state():
    return STATE


def reset_risk_state():
    STATE["enabled"] = True
    STATE["daily_pnl"] = 0.0
    STATE["last_status"] = "RESET"
    return STATE
