import time

STRATEGIES = {}


def _get(sid):
    if sid not in STRATEGIES:
        STRATEGIES[sid] = {
            "trades": [],
            "pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "enabled": True,
            "equity": [],
        }
    return STRATEGIES[sid]


def strategy_record_trade(strategy_id, pnl):
    s = _get(strategy_id)

    pnl = float(pnl)

    s["trades"].append({
        "time": time.time(),
        "pnl": pnl
    })

    s["pnl"] += pnl

    if pnl > 0:
        s["wins"] += 1
    else:
        s["losses"] += 1

    eq = (s["equity"][-1] if s["equity"] else 0.0) + pnl
    s["equity"].append(eq)

    return {"ok": True}


def _drawdown(eq):
    peak = 0.0
    max_dd = 0.0
    for v in eq:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    return max_dd


def strategy_get_stats():
    out = {}

    for k, s in STRATEGIES.items():
        trades = s["trades"]
        n = len(trades)

        winrate = s["wins"] / n if n else 0.0
        dd = _drawdown(s["equity"])

        out[k] = {
            "pnl": round(s["pnl"], 6),
            "trades": n,
            "winrate": round(winrate, 4),
            "drawdown": round(dd, 6),
            "enabled": s["enabled"]
        }

    return out


def strategy_get_rankings():
    stats = strategy_get_stats()

    ranked = sorted(
        stats.items(),
        key=lambda x: (x[1]["pnl"], x[1]["winrate"]),
        reverse=True
    )

    return ranked


def strategy_should_trade(strategy_id):
    s = _get(strategy_id)

    if not s["enabled"]:
        return {"trade": False, "reason": "disabled"}

    n = len(s["trades"])
    if n < 10:
        return {"trade": True, "reason": "not enough data"}

    winrate = s["wins"] / n
    dd = _drawdown(s["equity"])

    if winrate < 0.35 and n > 20:
        s["enabled"] = False
        return {"trade": False, "reason": "low winrate"}

    if dd > abs(s["pnl"]) * 0.8 and n > 20:
        s["enabled"] = False
        return {"trade": False, "reason": "high drawdown"}

    return {"trade": True, "reason": "ok"}
