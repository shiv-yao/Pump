STATE = {
    "daily_loss": 0,
    "max_loss": -0.02,  # -2%
    "enabled": True
}

def check_risk(pnl: float):
    STATE["daily_loss"] += pnl

    if STATE["daily_loss"] < STATE["max_loss"]:
        STATE["enabled"] = False
        return "KILL_SWITCH"

    return "OK"


def can_trade():
    return STATE["enabled"]
