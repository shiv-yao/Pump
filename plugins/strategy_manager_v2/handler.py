import time

STRATEGIES = {}

# ===== config =====
WINDOW = 50
MIN_TRADES = 10
COOLDOWN_SEC = 300


def _get(sid):
    if sid not in STRATEGIES:
        STRATEGIES[sid] = {
            "trades": [],
            "pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "enabled": True,
            "disabled_until": 0,
            "equity": [],
            "regimes": {}
        }
    return STRATEGIES[sid]


# ===== drawdown =====
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


# ===== record trade =====
def strategy_record_trade(strategy_id, pnl, regime=None):
    s = _get(strategy_id)

    pnl = float(pnl)
    ts = time.time()

    trade = {
        "time": ts,
        "pnl": pnl,
        "regime": regime or "unknown"
    }

    s["trades"].append(trade)
    s["pnl"] += pnl

    if pnl > 0:
        s["wins"] += 1
    else:
        s["losses"] += 1

    eq = (s["equity"][-1] if s["equity"] else 0.0) + pnl
    s["equity"].append(eq)

    r = trade["regime"]
    if r not in s["regimes"]:
        s["regimes"][r] = {"pnl": 0.0, "trades": 0}

    s["regimes"][r]["pnl"] += pnl
    s["regimes"][r]["trades"] += 1

    if len(s["trades"]) > WINDOW:
        s["trades"] = s["trades"][-WINDOW:]
        s["equity"] = s["equity"][-WINDOW:]

    return {"ok": True}


# ===== manual controls =====
def strategy_disable(strategy_id):
    s = _get(strategy_id)
    s["enabled"] = False
    return {"ok": True, "strategy_id": strategy_id, "enabled": False}


def strategy_enable(strategy_id):
    s = _get(strategy_id)
    s["enabled"] = True
    s["disabled_until"] = 0
    return {"ok": True, "strategy_id": strategy_id, "enabled": True}


# ===== decision gate =====
def strategy_should_trade(strategy_id, regime=None):
    s = _get(strategy_id)
    now = time.time()

    if now < s["disabled_until"]:
        return {"trade": False, "reason": "cooldown"}

    if not s["enabled"]:
        return {"trade": False, "reason": "disabled"}

    trades = s["trades"]
    n = len(trades)

    if n < MIN_TRADES:
        return {"trade": True, "reason": "insufficient data"}

    pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    winrate = wins / n if n else 0.0
    dd = _drawdown(s["equity"])

    if regime and regime in s["regimes"]:
        r = s["regimes"][regime]
        if r["trades"] > 5 and r["pnl"] < 0:
            return {"trade": False, "reason": "bad regime"}

    if winrate < 0.35 and n > 20:
        s["enabled"] = False
        s["disabled_until"] = now + COOLDOWN_SEC
        return {"trade": False, "reason": "low winrate"}

    if dd > abs(pnl) * 0.8 and n > 20:
        s["enabled"] = False
        s["disabled_until"] = now + COOLDOWN_SEC
        return {"trade": False, "reason": "high drawdown"}

    return {"trade": True, "reason": "ok"}


# ===== stats =====
def strategy_get_stats():
    out = {}

    for k, s in STRATEGIES.items():
        trades = s["trades"]
        n = len(trades)

        pnl = s["pnl"]
        wins = s["wins"]
        winrate = wins / n if n else 0.0
        dd = _drawdown(s["equity"])

        out[k] = {
            "pnl": round(pnl, 4),
            "trades": n,
            "winrate": round(winrate, 4),
            "drawdown": round(dd, 4),
            "enabled": s["enabled"],
            "cooldown": max(0, int(s["disabled_until"] - time.time())),
            "regimes": s["regimes"]
        }

    return out


# ===== ranking =====
def strategy_get_rankings():
    stats = strategy_get_stats()

    ranked = sorted(
        stats.items(),
        key=lambda x: (
            x[1]["pnl"],
            x[1]["winrate"],
            -x[1]["drawdown"]
        ),
        reverse=True
    )

    return ranked
