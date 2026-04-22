import time
from collections import defaultdict

# ===== GLOBAL STATE =====
STRATEGIES = defaultdict(lambda: {
    "trades": [],
    "pnl": 0.0,
    "wins": 0,
    "losses": 0,
    "enabled": True,
    "disabled_until": 0,
    "equity": [],
    "regimes": {}
})

STATE = {
    "enabled": True,
    "daily_pnl": 0.0,
    "max_daily_loss": -0.02,   # -2%
    "max_drawdown": -0.05,     # -5%
    "last_status": "OK"
}

# ===== CONFIG =====
WINDOW = 50
MIN_TRADES = 10
COOLDOWN_SEC = 300


# =========================
# INTERNAL
# =========================

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


def _get(sid):
    return STRATEGIES[sid]


# =========================
# TRADE RECORD
# =========================

async def strategy_record_trade(strategy_id, pnl=0.0, regime=None, **kwargs):
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

    # 滑動視窗
    if len(s["trades"]) > WINDOW:
        s["trades"] = s["trades"][-WINDOW:]
        s["equity"] = s["equity"][-WINDOW:]

    # ===== global risk update =====
    check_risk(pnl)

    return {"ok": True}


# =========================
# STRATEGY CONTROL
# =========================

async def strategy_should_trade(strategy_id, regime=None, **kwargs):
    s = _get(strategy_id)
    now = time.time()

    # 全局風控
    if not STATE["enabled"]:
        return {"trade": False, "reason": STATE["last_status"]}

    if now < s["disabled_until"]:
        return {"trade": False, "reason": "cooldown"}

    if not s["enabled"]:
        return {"trade": False, "reason": "disabled"}

    trades = s["trades"]
    n = len(trades)

    if n < MIN_TRADES:
        return {"trade": True, "reason": "cold_start"}

    pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    winrate = wins / n if n else 0.0
    dd = _drawdown(s["equity"])

    # ===== regime kill =====
    if regime and regime in s["regimes"]:
        r = s["regimes"][regime]
        if r["trades"] > 5 and r["pnl"] < 0:
            return {"trade": False, "reason": "bad_regime"}

    # ===== strategy kill =====
    if winrate < 0.35 and n > 20:
        s["enabled"] = False
        s["disabled_until"] = now + COOLDOWN_SEC
        return {"trade": False, "reason": "low_winrate"}

    if dd > abs(pnl) * 0.8 and n > 20:
        s["enabled"] = False
        s["disabled_until"] = now + COOLDOWN_SEC
        return {"trade": False, "reason": "high_drawdown"}

    return {"trade": True, "reason": "ok"}


# =========================
# RISK ENGINE（統一版）
# =========================

async def check_risk(asset_id=None, size=0.0, capital=100, **kwargs):
    # ===== size check =====
    if size > capital * 0.05:
        return {"allowed": False, "reason": "size_too_large"}

    # ===== global kill switch =====
    if not STATE["enabled"]:
        return {"allowed": False, "reason": STATE["last_status"]}

    return {"allowed": True}


def check_risk_pnl(pnl):
    pnl = float(pnl)
    STATE["daily_pnl"] += pnl

    if STATE["daily_pnl"] <= STATE["max_daily_loss"]:
        STATE["enabled"] = False
        STATE["last_status"] = "KILL_SWITCH_DAILY"
        return STATE["last_status"]

    if STATE["daily_pnl"] <= STATE["max_drawdown"]:
        STATE["enabled"] = False
        STATE["last_status"] = "KILL_SWITCH_DD"
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


# =========================
# STATS
# =========================

async def strategy_get_stats(**kwargs):
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


async def strategy_get_rankings(**kwargs):
    stats = await strategy_get_stats()

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
