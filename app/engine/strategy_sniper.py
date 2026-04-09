from app.engine import runtime as rt
from app.engine.features import features, score_with_allocator


def sniper_guard(f):
    return (
        f.get("liq", 0) > 20000 and
        f.get("concentration", 0) < 0.6
    )


def _sniper_pass(f, score):
    source = f.get("source")
    is_new = f.get("is_new")

    if score < 0.07:
        return False

    if not (is_new or source in ["mempool", "pumpfun"]):
        return False

    if not sniper_guard(f):
        return False

    if rt.SNIPER_A_PLUS_ONLY:
        if score < 0.13:
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
    return ranked[:2]
