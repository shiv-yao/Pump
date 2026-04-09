
from app.engine import runtime as rt
from app.engine.features import features, score_with_allocator

async def run_sniper_engine(tokens):
    ranked = []
    for t in tokens:
        f = await features(t)
        if not f:
            continue
        score, mtype, _detail = score_with_allocator(f)
        if mtype != "sniper":
            continue
        if score < getattr(rt, "SNIPER_ENTRY_THRESHOLD", 0.07):
            continue
        f["_score"] = score
        f["_mode"] = "sniper"
        f["_tier"] = "A+" if score >= 0.135 else "A" if score >= 0.095 else "B"
        if getattr(rt, "SNIPER_A_PLUS_ONLY", False) and f["_tier"] != "A+":
            continue
        ranked.append(f)
    ranked.sort(key=lambda x: x["_score"], reverse=True)
    return ranked[: getattr(rt, "SNIPER_TOP_K", 3)]
