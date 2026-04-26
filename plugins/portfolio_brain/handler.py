from app.utils.loader import call

STATE = {
    "weights": {},
    "last_update": 0
}


async def portfolio_allocate(capital=100):
    rankings = await call("strategy_get_rankings", {})

    if not isinstance(rankings, list):
        return {"error": "no rankings"}

    total_score = 0
    weights = {}

    for sid, stat in rankings[:5]:
        score = stat["pnl"] + stat["winrate"] * 10
        score = max(score, 0.01)

        weights[sid] = score
        total_score += score

    # normalize
    for k in weights:
        weights[k] /= total_score

    STATE["weights"] = weights

    return {
        "capital": capital,
        "allocations": {
            k: round(capital * w, 4)
            for k, w in weights.items()
        }
    }
