from collections import defaultdict
from typing import Dict, Any


class FundBrain:
    def __init__(self):
        self.allocator = {
            "stable": 0.30,
            "degen": 0.45,
            "sniper": 0.25,
        }
        self.strategy_stats = defaultdict(lambda: {
            "pnl": 0.0,
            "trades": 0,
            "wins": 0,
            "losses": 0,
        })
        self.last_reason = "boot"

    def update_after_trade(self, strategy: str, pnl: float):
        s = self.strategy_stats[strategy]
        s["pnl"] += pnl
        s["trades"] += 1
        if pnl > 0:
            s["wins"] += 1
        else:
            s["losses"] += 1

    def rebalance(self, regime: str):
        base = {
            "stable": 0.30,
            "degen": 0.45,
            "sniper": 0.25,
        }

        if regime == "bull":
            base = {"stable": 0.20, "degen": 0.45, "sniper": 0.35}
            self.last_reason = "bull_regime"
        elif regime == "bear":
            base = {"stable": 0.50, "degen": 0.30, "sniper": 0.20}
            self.last_reason = "bear_regime"
        else:
            self.last_reason = "neutral_regime"

        for k in list(base.keys()):
            perf = self.strategy_stats[k]["pnl"]
            base[k] += max(min(perf, 0.15), -0.15)

        s = sum(base.values()) or 1.0
        self.allocator = {k: max(v / s, 0.05) for k, v in base.items()}

        s2 = sum(self.allocator.values()) or 1.0
        self.allocator = {k: v / s2 for k, v in self.allocator.items()}

        return self.allocator

    def snapshot(self) -> Dict[str, Any]:
        return {
            "allocator": self.allocator,
            "strategy_stats": dict(self.strategy_stats),
            "reason": self.last_reason,
        }
