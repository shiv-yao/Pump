from app.utils.loader import call


PARAMS = {
    "threshold": 0.6,
    "size_factor": 1.0
}


async def auto_optimize():
    stats = await call("strategy_get_stats", {})

    if not isinstance(stats, dict):
        return {"error": "no stats"}

    avg_winrate = sum(s["winrate"] for s in stats.values()) / len(stats)

    # ===== 調 threshold =====
    if avg_winrate < 0.45:
        PARAMS["threshold"] += 0.02
    else:
        PARAMS["threshold"] -= 0.01

    PARAMS["threshold"] = max(0.5, min(0.75, PARAMS["threshold"]))

    # ===== 調 size =====
    total_pnl = sum(s["pnl"] for s in stats.values())

    if total_pnl > 0:
        PARAMS["size_factor"] *= 1.05
    else:
        PARAMS["size_factor"] *= 0.95

    PARAMS["size_factor"] = max(0.5, min(2.0, PARAMS["size_factor"]))

    return PARAMS


async def get_params():
    return PARAMS
