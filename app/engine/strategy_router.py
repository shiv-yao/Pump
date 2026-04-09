
from app.engine import runtime as rt

def route_strategy(f: dict) -> str:
    source = str(f.get("source", "")).lower()
    if f.get("is_new") or source in {"mempool", "pumpfun"}:
        return "sniper"
    if f.get("wallet_graph_score", 0.0) >= getattr(rt, "STABLE_WALLET_GRAPH_CUTOFF", 0.55):
        return "stable"
    if f.get("smart", 0.0) >= getattr(rt, "STABLE_SMART_CUTOFF", 0.55):
        return "stable"
    return "momentum"

def apply_strategy_boost(score: float, f: dict):
    strat = route_strategy(f)
    if strat == "sniper":
        return score * getattr(rt, "SNIPER_MULTIPLIER", 1.30), strat
    if strat == "stable":
        return score * getattr(rt, "STABLE_MULTIPLIER", 1.12), strat
    return score * getattr(rt, "MOMENTUM_MULTIPLIER", 1.00), strat
