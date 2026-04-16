from __future__ import annotations


def detect_regime(strategy_mode: str, recent_win_rate: float) -> str:
    if strategy_mode == "aggressive" and recent_win_rate > 55:
        return "bull"
    if recent_win_rate < 45:
        return "defensive"
    return "balanced"


def decide_trade(status: dict, settings: dict) -> dict:
    regime = detect_regime(settings["strategy_mode"], status["win_rate_pct"])
    size_usd = min(settings["max_position_usd"], 100.0)

    symbol = "SOL-USD"
    strategy_name = {
        "safe": "Fund Core",
        "balanced": "Allocator Fusion",
        "aggressive": "Execution RL",
    }[settings["strategy_mode"]]

    return {
        "symbol": symbol,
        "side": "buy",
        "size_usd": size_usd,
        "strategy_name": strategy_name,
        "regime": regime,
    }\n