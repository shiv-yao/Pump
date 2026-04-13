from app.engine import runtime as rt
from app.state import engine
from app.engine.utils import sf


def _clamp(x, lo, hi):
    try:
        x = float(x)
    except Exception:
        x = lo
    return max(lo, min(hi, x))


def _ensure():
    if not hasattr(rt, "FUND_ALLOCATOR") or not isinstance(rt.FUND_ALLOCATOR, dict):
        rt.FUND_ALLOCATOR = {
            "stable": 0.40,
            "sniper": 0.20,
            "momentum": 0.35,
            "explore": 0.05,
        }

    if not hasattr(rt, "FUND_PERF") or not isinstance(rt.FUND_PERF, dict):
        rt.FUND_PERF = {}

    if not hasattr(rt, "FUND_STATE") or not isinstance(rt.FUND_STATE, dict):
        rt.FUND_STATE = {
            "last_reason": "boot",
            "last_perf": {},
        }

    if not hasattr(rt, "ADAPT_STATE") or not isinstance(rt.ADAPT_STATE, dict):
        rt.ADAPT_STATE = {
            "entry_mult": 1.0,
            "tp_mult": 1.0,
            "sl_mult": 1.0,
        }

    # 保留 base 值，避免每輪越改越飄
    if not hasattr(rt, "BASE_ENTRY_THRESHOLD"):
        rt.BASE_ENTRY_THRESHOLD = float(getattr(rt, "ENTRY_THRESHOLD", 0.07) or 0.07)

    if not hasattr(rt, "BASE_TAKE_PROFIT"):
        rt.BASE_TAKE_PROFIT = float(getattr(rt, "TAKE_PROFIT", 0.02) or 0.02)

    if not hasattr(rt, "BASE_STOP_LOSS"):
        rt.BASE_STOP_LOSS = float(getattr(rt, "STOP_LOSS", -0.01) or -0.01)

    if not hasattr(engine, "stats") or not isinstance(engine.stats, dict):
        engine.stats = {}

    engine.stats.setdefault("wins", 0)
    engine.stats.setdefault("losses", 0)
    engine.stats.setdefault("trades", 0)


# =========================================================
# STRATEGY PERFORMANCE（哪個策略在賺）
# =========================================================
def _calc_strategy_perf():
    trades = getattr(engine, "trade_history", []) or []

    perf = {
        "stable": {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0},
        "sniper": {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0},
        "momentum": {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0},
        "explore": {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0},
    }

    for t in trades[-30:]:
        if not isinstance(t, dict):
            continue

        strat = str(t.get("mode", "unknown")).lower()
        if strat not in perf:
            continue

        pnl = sf(t.get("pnl", 0.0), 0.0)
        perf[strat]["pnl"] += pnl
        perf[strat]["trades"] += 1

        if pnl > 0:
            perf[strat]["wins"] += 1
        else:
            perf[strat]["losses"] += 1

    return perf


# =========================================================
# ALLOCATOR（資金配置會自己變）
# =========================================================
def _adjust_allocator(perf):
    # 沒資料時維持現狀
    total_abs = sum(abs(v["pnl"]) for v in perf.values()) or 1.0

    # base anchors
    current = dict(getattr(rt, "FUND_ALLOCATOR", {}) or {})
    base = {
        "stable": float(current.get("stable", 0.40) or 0.40),
        "sniper": float(current.get("sniper", 0.20) or 0.20),
        "momentum": float(current.get("momentum", 0.35) or 0.35),
        "explore": float(current.get("explore", 0.05) or 0.05),
    }

    new_alloc = dict(base)

    for strat in ["stable", "sniper", "momentum"]:
        p = perf.get(strat, {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0})
        pnl = sf(p.get("pnl", 0.0), 0.0)
        trades = int(p.get("trades", 0) or 0)
        wins = int(p.get("wins", 0) or 0)
        losses = int(p.get("losses", 0) or 0)
        total = max(wins + losses, 1)
        winrate = wins / total

        # 資料太少時只做很小調整
        if trades < 3:
            boost = 1.0
        else:
            rel = pnl / total_abs

            boost = 1.0
            if rel > 0.20:
                boost *= 1.15
            elif rel > 0.08:
                boost *= 1.08
            elif rel < -0.10:
                boost *= 0.78
            elif rel < -0.04:
                boost *= 0.90

            if winrate > 0.60:
                boost *= 1.05
            elif winrate < 0.35:
                boost *= 0.92

        new_alloc[strat] = base[strat] * boost

    # explore 固定偏小
    new_alloc["explore"] = _clamp(base.get("explore", 0.05), 0.02, 0.08)

    # clamp by bucket
    new_alloc["stable"] = _clamp(new_alloc["stable"], 0.20, 0.65)
    new_alloc["sniper"] = _clamp(new_alloc["sniper"], 0.08, 0.35)
    new_alloc["momentum"] = _clamp(new_alloc["momentum"], 0.10, 0.50)
    new_alloc["explore"] = _clamp(new_alloc["explore"], 0.02, 0.08)

    # normalize
    s = sum(new_alloc.values()) or 1.0
    for k in new_alloc:
        new_alloc[k] = new_alloc[k] / s

    rt.FUND_ALLOCATOR.update(new_alloc)
    rt.FUND_STATE["last_perf"] = perf


# =========================================================
# ENTRY ADAPT（超關鍵）
# =========================================================
def _adjust_entry():
    no_trade = int(getattr(engine, "no_trade_cycles", 0) or 0)
    wins = int(engine.stats.get("wins", 0) or 0)
    losses = int(engine.stats.get("losses", 0) or 0)

    base = float(getattr(rt, "BASE_ENTRY_THRESHOLD", getattr(rt, "ENTRY_THRESHOLD", 0.07)) or 0.07)
    entry_mult = 1.0
    reason = "entry_normal"

    # 沒單 → 降門檻
    if no_trade > 20:
        entry_mult = 0.82
        reason = "entry_low_no_trade_20+"
    elif no_trade > 10:
        entry_mult = 0.90
        reason = "entry_low_no_trade_10+"

    # 連輸 → 提高門檻
    if losses > wins + 5:
        entry_mult *= 1.20
        reason = "entry_high_loss_guard_strong"
    elif losses > wins + 3:
        entry_mult *= 1.10
        reason = "entry_high_loss_guard"

    rt.ENTRY_THRESHOLD = _clamp(base * entry_mult, 0.04, 0.12)
    rt.ADAPT_STATE["entry_mult"] = entry_mult
    return reason


# =========================================================
# TP / SL ADAPT
# =========================================================
def _adjust_tp_sl():
    regime = getattr(rt, "REGIME_STATE", {}).get("mode", "neutral")
    wins = int(engine.stats.get("wins", 0) or 0)
    losses = int(engine.stats.get("losses", 0) or 0)

    base_tp = float(getattr(rt, "BASE_TAKE_PROFIT", getattr(rt, "TAKE_PROFIT", 0.02)) or 0.02)
    base_sl = float(getattr(rt, "BASE_STOP_LOSS", getattr(rt, "STOP_LOSS", -0.01)) or -0.01)

    tp_mult = 1.0
    sl_mult = 1.0
    reason = "tp_sl_normal"

    if regime == "bull":
        tp_mult *= 1.25
        sl_mult *= 0.90
        reason = "tp_sl_bull"
    elif regime == "bear":
        tp_mult *= 0.80
        sl_mult *= 1.10
        reason = "tp_sl_bear"

    # 近期表現差 → 再保守一點
    if losses > wins + 3:
        tp_mult *= 0.92
        sl_mult *= 0.95
        reason += "_loss_guard"

    rt.TAKE_PROFIT = _clamp(base_tp * tp_mult, 0.008, 0.05)
    rt.STOP_LOSS = -abs(_clamp(abs(base_sl) * abs(sl_mult), 0.006, 0.03))

    rt.ADAPT_STATE["tp_mult"] = tp_mult
    rt.ADAPT_STATE["sl_mult"] = sl_mult
    return reason


# =========================================================
# MAIN
# =========================================================
def ml_adjust_allocator():
    _ensure()

    perf = _calc_strategy_perf()
    rt.FUND_PERF = perf

    _adjust_allocator(perf)
    reason_entry = _adjust_entry()
    reason_tp_sl = _adjust_tp_sl()

    rt.FUND_STATE["last_reason"] = f"{reason_entry} | {reason_tp_sl}"
