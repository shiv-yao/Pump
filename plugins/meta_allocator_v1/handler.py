def allocate_capital_v1(strategies: dict, capital: float):
    capital = float(capital)
    scores = {}
    total_score = 0.0

    for name, item in (strategies or {}).items():
        try:
            pnl = float(item.get("pnl", 0.0))
            winrate = float(item.get("winrate", 0.0))
        except Exception:
            pnl = 0.0
            winrate = 0.0

        score = max(0.0, winrate * 0.7 + pnl * 0.3)
        scores[name] = score
        total_score += score

    alloc = {}
    if total_score <= 0:
        for name in scores:
            alloc[name] = 0.0
        return {
            "allocations": alloc,
            "total_score": total_score
        }

    for name, score in scores.items():
        alloc[name] = capital * (score / total_score)

    return {
        "allocations": alloc,
        "total_score": total_score
    }
