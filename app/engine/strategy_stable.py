from app.engine import runtime as rt
from app.engine.features import features, score_with_allocator, safe_adaptive_filter


def _stable_pass(f, score):
    liq = f.get("liq", 0)
    wg = f.get("wallet_graph_score", 0)
    smart = f.get("smart", 0)

    if score < 0.08:
        return False

    if liq < max(rt.MIN_LIQUIDITY_TRADE, 40000):
        return False

    if wg > 0.5:
        return True

    if smart > 0.5 and liq > 60000:
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

        ok, _ = safe_adaptive_filter(f)
        if not ok and score < rt.FILTER_SCORE_BYPASS:
            continue

        f["_score"] = score
        f["_mode"] = "stable"
        f["_tier"] = "A+" if score > 0.13 else "A"
        f["_detail"] = detail

        ranked.append(f)

    ranked.sort(key=lambda x: x["_score"], reverse=True)
    return ranked[:3]
