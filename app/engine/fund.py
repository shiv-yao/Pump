from collections import defaultdict
import time

FUND_ALLOCATOR = {
    "sniper": 0.3,
    "smart": 0.3,
    "momentum": 0.3,
    "explore": 0.1,
}

FUND_PERF = defaultdict(lambda: {"pnl": 0, "trades": 0})


def update_fund_allocator(force=False):
    total = sum(v["pnl"] + 1 for v in FUND_PERF.values())
    if total == 0:
        return

    for k in FUND_ALLOCATOR:
        score = FUND_PERF[k]["pnl"] + 1
        FUND_ALLOCATOR[k] = score / total
