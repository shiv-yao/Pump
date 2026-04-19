import math

# ===== config =====
BASE_WEIGHT = 0.2
MAX_WEIGHT = 0.6
MIN_WEIGHT = 0.05

DD_PENALTY = 1.5
VOL_SCALE = 1.2


# ===== helpers =====
async def _get_rankings(call):
    res = await call("strategy_get_rankings", {})
    if not isinstance(res, list):
        return []
    return res


def _volatility_score(stats):
    """
    簡單 volatility proxy：
    用 winrate + drawdown 做穩定度評分
    """
    win = stats.get("winrate", 0)
    dd = stats.get("drawdown", 0)

    stability = win * 1.2 - dd * 0.8
    return max(0.1, stability)


def _score_strategy(stats):
    pnl = stats.get("pnl", 0)
    win = stats.get("winrate", 0)
    dd = stats.get("drawdown", 0)

    score = 0.0

    score += pnl * 0.4
    score += win * 2.0

    # drawdown penalty
    score -= dd * DD_PENALTY

    return max(0.0, score)


# ===== allocation map =====
async def allocator_get_allocation_map():
    from inspect import iscoroutinefunction

    # dynamic call loader（跟你系統一致）
    async def call(tool, payload=None):
        payload = payload or {}
        fn = globals().get("_call_tool")
        if fn:
            return await fn(tool, payload)
        return {"error": "call not available"}

    rankings = await call("strategy_get_rankings", {})

    if not isinstance(rankings, list) or len(rankings) == 0:
        return {}

    scores = {}
    total_score = 0.0

    for sid, stats in rankings:
        s = _score_strategy(stats)

        # volatility scaling
        vol = _volatility_score(stats)
        s *= vol * VOL_SCALE

        scores[sid] = s
        total_score += s

    # fallback
    if total_score <= 0:
        n = len(scores)
        return {k: 1 / n for k in scores}

    # normalize
    weights = {}
    for sid, s in scores.items():
        w = s / total_score

        # clamp
        w = max(MIN_WEIGHT, min(MAX_WEIGHT, w))
        weights[sid] = w

    # re-normalize after clamp
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    return weights


# ===== main allocation =====
async def allocator_get_budget(strategy_id, capital):
    capital = float(capital)

    # call wrapper（跟你 execution engine 一致）
    async def call(tool, payload=None):
        payload = payload or {}
        fn = globals().get("_call_tool")
        if fn:
            return await fn(tool, payload)
        return {"error": "call not available"}

    weights = await call("allocator_get_allocation_map", {})

    if not weights or strategy_id not in weights:
        return {
            "budget": capital * BASE_WEIGHT,
            "weight": BASE_WEIGHT
        }

    w = weights[strategy_id]

    # final safety clamp
    w = max(MIN_WEIGHT, min(MAX_WEIGHT, w))

    return {
        "budget": capital * w,
        "weight": w
    }
