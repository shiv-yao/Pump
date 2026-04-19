import random

STRATEGIES = {
    "polymarket": 0.3,
    "solana": 0.5,
    "alpha": 0.2
}


def allocate_capital(total: float):
    alloc = {}
    for k, w in STRATEGIES.items():
        alloc[k] = total * w
    return alloc


def decide_trade(signal_score: float):
    if signal_score > 0.7:
        return "buy"
    elif signal_score < 0.3:
        return "sell"
    return "hold"
