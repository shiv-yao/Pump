from app.engine import runtime as rt
from app.engine.utils import clamp, log, now, sf, strategy_bucket_from_mode

def ensure_fund_state():
    for key, default_val in {
        "sniper": rt.FUND_SNIPER_BASE,
        "smart": rt.FUND_SMART_BASE,
        "momentum": rt.FUND_MOMENTUM_BASE,
        "explore": rt.FUND_EXPLORE_BASE,
    }.items():
        rt.FUND_ALLOCATOR.setdefault(key, default_val)
        _ = rt.FUND_PERF[key]

def update_fund_perf(strategy: str, pnl: float):
    strategy = strategy_bucket_from_mode(strategy)
    row = rt.FUND_PERF[strategy]
    row["trades"] += 1
    row["pnl"] += sf(pnl, 0.0)
    if pnl > 0:
        row["wins"] += 1
    else:
        row["losses"] += 1

def update_fund_allocator(force=False):
    ensure_fund_state()
    if not force and (now() - sf(rt.FUND_STATE.get("last_update", 0.0), 0.0) < rt.FUND_BRAIN_UPDATE_SEC):
        return

    raw_scores = {}
    total_score = 0.0
    for strat in ["sniper", "smart", "momentum", "explore"]:
        perf = rt.FUND_PERF[strat]
        trades = int(perf.get("trades", 0))
        pnl = sf(perf.get("pnl", 0.0), 0.0)
        wins = int(perf.get("wins", 0))
        losses = int(perf.get("losses", 0))
        total_done = max(trades, wins + losses)
        winrate = wins / total_done if total_done > 0 else 0.5

        if trades < rt.FUND_MIN_TRADES:
            base_prior = {"sniper": 1.00, "smart": 1.05, "momentum": 1.05, "explore": 0.55}.get(strat, 1.0)
            score = base_prior
        else:
            pnl_score = clamp(1.0 + pnl, 0.10, 2.50)
            wr_score = clamp(0.40 + winrate, 0.10, 1.60)
            stability_penalty = 0.88 if (losses >= wins + 2 and pnl < 0) else 1.0
            score = clamp((pnl_score * 0.55 + wr_score * 0.45) * stability_penalty, 0.10, 3.00)

        raw_scores[strat] = score
        total_score += score

    total_score = total_score or 1.0
    for strat, score in raw_scores.items():
        rt.FUND_ALLOCATOR[strat] = score / total_score

    rt.FUND_ALLOCATOR["sniper"] = clamp(rt.FUND_ALLOCATOR["sniper"], 0.08, 0.55)
    rt.FUND_ALLOCATOR["smart"] = clamp(rt.FUND_ALLOCATOR["smart"], 0.10, 0.55)
    rt.FUND_ALLOCATOR["momentum"] = clamp(rt.FUND_ALLOCATOR["momentum"], 0.10, 0.55)
    rt.FUND_ALLOCATOR["explore"] = clamp(rt.FUND_ALLOCATOR["explore"], 0.02, 0.15)

    s = sum(rt.FUND_ALLOCATOR.values()) or 1.0
    for k in list(rt.FUND_ALLOCATOR.keys()):
        rt.FUND_ALLOCATOR[k] = rt.FUND_ALLOCATOR[k] / s

    rt.FUND_STATE["last_update"] = now()
    rt.FUND_STATE["last_reason"] = "perf_rebalance"
    log("FUND_ALLOC " + " ".join(f"{k}={rt.FUND_ALLOCATOR[k]:.2f}" for k in ["sniper", "smart", "momentum", "explore"]))

def fund_multiplier(strategy: str) -> float:
    strategy = strategy_bucket_from_mode(strategy)
    alloc = sf(rt.FUND_ALLOCATOR.get(strategy, 0.25), 0.25)
    if alloc >= 0.45:
        return 1.35
    if alloc >= 0.35:
        return 1.18
    if alloc >= 0.25:
        return 1.00
    if alloc >= 0.15:
        return 0.82
    return 0.65

def _fund_perf(name):
    s = rt.FUND_PERF.get(name, {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0})
    t = s["trades"]
    return {
        "trades": t,
        "wins": s["wins"],
        "losses": s["losses"],
        "pnl": s["pnl"],
        "win_rate": (s["wins"] / t) if t else 0.0,
        "allocator_weight": sf(rt.FUND_ALLOCATOR.get(name, 0.0), 0.0),
        "capital_multiplier": fund_multiplier(name),
    }
