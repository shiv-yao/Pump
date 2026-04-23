from app.utils.loader import call


async def alpha_breakdown():
    stats = await call("strategy_get_stats", {})

    if not isinstance(stats, dict):
        return {"error": "no stats"}

    total_pnl = sum(s["pnl"] for s in stats.values())

    breakdown = {}

    for k, v in stats.items():
        pnl = v["pnl"]

        breakdown[k] = {
            "pnl": pnl,
            "contribution": pnl / total_pnl if total_pnl else 0,
            "winrate": v["winrate"]
        }

    return breakdown
