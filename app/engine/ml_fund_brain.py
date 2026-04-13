from app.engine import runtime as rt
from app.state import engine
from app.engine.utils import sf


def _ensure():
    if not hasattr(rt, "FUND_ALLOCATOR"):
        rt.FUND_ALLOCATOR = {
            "stable": 0.4,
            "sniper": 0.2,
            "momentum": 0.35,
            "explore": 0.05,
        }

    if not hasattr(rt, "FUND_PERF"):
        rt.FUND_PERF = {}

    if not hasattr(rt, "ADAPT_STATE"):
        rt.ADAPT_STATE = {
            "entry_mult": 1.0,
            "tp_mult": 1.0,
            "sl_mult": 1.0,
        }


# =========================================================
# STRATEGY PERFORMANCE（哪個策略在賺）
# =========================================================
def _calc_strategy_perf():
    trades = getattr(engine, "trade_history", []) or []

    perf = {}

    for t in trades[-30:]:
        strat = str(t.get("mode", "unknown"))
        pnl = sf(t.get("pnl", 0.0), 0.0)

        if strat not in perf:
            perf[strat] = {"pnl": 0.0, "trades": 0}

        perf[strat]["pnl"] += pnl
        perf[strat]["trades"] += 1

    return perf


# =========================================================
# ALLOCATOR（資金配置會自己變）
# =========================================================
def _adjust_allocator(perf):
    total = sum(abs(v["pnl"]) for v in perf.values()) or 1.0

    for strat in ["stable", "sniper", "momentum"]:
        p = perf.get(strat, {"pnl": 0.0})

        score = p["pnl"] / total

        if score > 0.2:
            rt.FUND_ALLOCATOR[strat] = min(
                rt.FUND_ALLOCATOR.get(strat, 0.3) * 1.15,
                0.6,
            )
        elif score < -0.1:
            rt.FUND_ALLOCATOR[strat] = max(
                rt.FUND_ALLOCATOR.get(strat, 0.3) * 0.75,
                0.05,
            )

    # normalize
    s = sum(rt.FUND_ALLOCATOR.values())
    for k in rt.FUND_ALLOCATOR:
        rt.FUND_ALLOCATOR[k] /= s


# =========================================================
# ENTRY ADAPT（超關鍵）
# =========================================================
def _adjust_entry():
    no_trade = int(getattr(engine, "no_trade_cycles", 0) or 0)
    wins = int(engine.stats.get("wins", 0))
    losses = int(engine.stats.get("losses", 0))

    base = getattr(rt, "ENTRY_THRESHOLD", 0.07)

    # 沒單 → 降門檻
    if no_trade > 15:
        rt.ENTRY_THRESHOLD = max(base * 0.85, 0.04)

    # 連輸 → 提高門檻
    elif losses > wins + 3:
        rt.ENTRY_THRESHOLD = min(base * 1.2, 0.12)

    else:
        rt.ENTRY_THRESHOLD = base


# =========================================================
# TP / SL ADAPT
# =========================================================
def _adjust_tp_sl():
    regime = getattr(rt, "REGIME_STATE", {}).get("mode", "neutral")

    base_tp = getattr(rt, "TAKE_PROFIT", 0.02)
    base_sl = getattr(rt, "STOP_LOSS", -0.01)

    if regime == "bull":
        rt.TAKE_PROFIT = base_tp * 1.4
        rt.STOP_LOSS = base_sl * 0.8

    elif regime == "bear":
        rt.TAKE_PROFIT = base_tp * 0.7
        rt.STOP_LOSS = base_sl * 1.2

    else:
        rt.TAKE_PROFIT = base_tp
        rt.STOP_LOSS = base_sl


# =========================================================
# MAIN
# =========================================================
def ml_adjust_allocator():
    _ensure()

    perf = _calc_strategy_perf()
    rt.FUND_PERF = perf

    _adjust_allocator(perf)
    _adjust_entry()
    _adjust_tp_sl()
