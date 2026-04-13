from app.engine import runtime as rt
from app.engine.features import features, score_with_allocator, safe_adaptive_filter


def _stable_pass(f, score):
    liq = f.get("liq", 0)
    wg = f.get("wallet_graph_score", 0)
    smart = f.get("smart", 0)

    # ✅ 放寬 entry（關鍵）
    if score < getattr(rt, "STABLE_ENTRY_THRESHOLD", 0.075):
        return False

    # ✅ 流動性不要卡太死
    if liq < max(getattr(rt, "MIN_LIQUIDITY_TRADE", 20000), 15000):
        return False

    # ✅ 強 wallet graph → 直接過
    if wg > 0.45:
        return True

    # ✅ smart money + liquidity
    if smart > 0.45 and liq > 30000:
        return True

    # ✅ fallback（防止完全不交易）
    if score > 0.10:
        return True

    return False


async def run_stable_engine(tokens):
    ranked = []

    for t in tokens:
        f = await features(t)
        if not f:
            continue

        score, _, detail = score_with_allocator(f)

        if not _stable_pass(f, score):
            continue

        # ✅ adaptive filter
        ok, _ = safe_adaptive_filter(f)
        if not ok and score < getattr(rt, "FILTER_SCORE_BYPASS", 0.13):
            continue

        f["_score"] = score
        f["_mode"] = "stable"
        f["_tier"] = "A+" if score > 0.13 else "A"
        f["_detail"] = detail

        ranked.append(f)

    ranked.sort(key=lambda x: x["_score"], reverse=True)

    # ✅ fallback：如果完全沒東西 → 放寬
    if not ranked:
        for t in tokens[:5]:
            f = await features(t)
            if not f:
                continue
            score, _, detail = score_with_allocator(f)
            f["_score"] = score
            f["_mode"] = "stable"
            f["_tier"] = "B"
            f["_detail"] = detail
            ranked.append(f)

    return ranked[:3]
