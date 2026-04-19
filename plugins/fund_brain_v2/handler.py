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

def decide_trade(score: float):
    if score > 0.65:
        return "buy"
    elif score < 0.35:
        return "sell"
    return "hold"


def position_size(score: float, capital: float):
    # 動態倉位（越確定越大）
    return capital * min(max(score, 0.1), 0.5)
