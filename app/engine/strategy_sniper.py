from app.engine import runtime as rt
from app.engine.features import features, score_with_allocator


def sniper_guard(f):
    return (
        f.get("liq", 0) > getattr(rt, "MIN_LIQUIDITY_TRADE", 15000)
        and f.get("concentration", 0) < 0.65
    )


def _sniper_pass(f, score):
    source = f.get("source")
    is_new = f.get("is_new")

    # ✅ 放寬 entry（關鍵）
    if score < getattr(rt, "SNIPER_ENTRY_THRESHOLD", 0.065):
        return False

    # ✅ 必須是 early token
    if not (is_new or source in ["mempool", "pumpfun"]):
        return False

    if not sniper_guard(f):
        return False

    # ✅ 不要卡太死
    if getattr(rt, "SNIPER_A_PLUS_ONLY", False):
        if score < 0.11:
            return False

    return True


async def run_sniper_engine(tokens):
    ranked = []

    for t in tokens:
        f = await features(t)
        if not f:
            continue

        score, _, detail = score_with_allocator(f)

        if not _sniper_pass(f, score):
            continue

        f["_score"] = score
        f["_mode"] = "sniper"
        f["_tier"] = "A+" if score > 0.13 else "A"
        f["_detail"] = detail

        ranked.append(f)

    ranked.sort(key=lambda x: x["_score"], reverse=True)

    # ✅ fallback（避免 sniper 死掉）
    if not ranked:
        for t in tokens[:3]:
            f = await features(t)
            if not f:
                continue
            score, _, detail = score_with_allocator(f)

            f["_score"] = score
            f["_mode"] = "sniper"
            f["_tier"] = "B"
            f["_detail"] = detail

            ranked.append(f)

    return ranked[:2]
