from collections import defaultdict

strategy_stats = defaultdict(lambda: {
    "wins": 0,
    "loss": 0,
    "pnl": 0.0
})


def update_trade(strategy_id: str, pnl: float):
    s = strategy_stats[strategy_id]

    if pnl > 0:
        s["wins"] += 1
    else:
        s["loss"] += 1

    s["pnl"] += pnl


def get_weight(strategy_id: str):
    s = strategy_stats[strategy_id]

    total = s["wins"] + s["loss"]
    if total < 10:
        return 1.0

    winrate = s["wins"] / total

    # 🔥 核心：自適應權重
    return max(0.5, min(2.0, winrate * 2))
