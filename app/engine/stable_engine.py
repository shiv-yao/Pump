
from app.engine import runtime as rt
from app.engine.features import features, score_with_allocator, safe_adaptive_filter

async def run_stable_engine(tokens):
    ranked = []
    for t in tokens:
        f = await features(t)
        if not f:
            continue
        score, mtype, _detail = score_with_allocator(f)
        if mtype != "stable":
            continue
        ok, _ = safe_adaptive_filter(f, None, getattr(rt.engine, "no_trade_cycles", 0))
        if not ok and score < getattr(rt, "FILTER_SCORE_BYPASS", 0.10):
            continue
        f["_score"] = score
        f["_mode"] = "stable"
        f["_tier"] = "A+" if score >= 0.13 else "A" if score >= 0.09 else "B"
        ranked.append(f)
    ranked.sort(key=lambda x: x["_score"], reverse=True)
    return ranked[: getattr(rt, "STABLE_TOP_K", 4)]
