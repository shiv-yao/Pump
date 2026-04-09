
from app.engine import runtime as rt
from app.engine.utils import clamp, sf

def ml_adjust_allocator():
    # Lightweight adaptive allocator driven by realized pnl and win rate.
    buckets = ["stable", "sniper", "momentum", "explore"]
    scores = {}
    total = 0.0
    for b in buckets:
        perf = rt.FUND_PERF.get(b, {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0})
        pnl = sf(perf.get("pnl", 0.0), 0.0)
        trades = int(perf.get("trades", 0))
        wins = int(perf.get("wins", 0))
        losses = int(perf.get("losses", 0))
        winrate = wins / max(wins + losses, 1)
        if trades < 3:
            prior = {
                "stable": 1.15,
                "sniper": 0.90,
                "momentum": 1.00,
                "explore": 0.40,
            }.get(b, 1.0)
            s = prior
        else:
            s = clamp(0.75 + max(pnl, -0.25) + winrate, 0.10, 3.00)
        scores[b] = s
        total += s

    total = total or 1.0
    new_alloc = {k: v / total for k, v in scores.items()}

    # Clamp to long-run ranges
    new_alloc["stable"] = clamp(new_alloc.get("stable", 0.40), 0.25, 0.70)
    new_alloc["sniper"] = clamp(new_alloc.get("sniper", 0.20), 0.05, 0.35)
    new_alloc["momentum"] = clamp(new_alloc.get("momentum", 0.25), 0.10, 0.40)
    new_alloc["explore"] = clamp(new_alloc.get("explore", 0.08), 0.02, 0.12)

    s = sum(new_alloc.values()) or 1.0
    for k in list(new_alloc.keys()):
        new_alloc[k] = new_alloc[k] / s

    rt.FUND_ALLOCATOR.update(new_alloc)
    rt.FUND_STATE["last_reason"] = "ml_adjust_allocator"
