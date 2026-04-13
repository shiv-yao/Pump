from app.engine import runtime as rt
from app.engine.features import features, score_with_allocator


def sniper_guard(f):
    liq = float(f.get("liq", 0) or 0)
    concentration = float(f.get("concentration", 0) or 0)

    return (
        liq > float(getattr(rt, "MIN_LIQUIDITY_TRADE", 15000) or 15000)
        and concentration < 0.65
    )


def _sniper_pass(f, score):
    source = str(f.get("source", "")).lower()
    is_new = bool(f.get("is_new", False))
    liq = float(f.get("liq", 0) or 0)

    entry_thr = float(getattr(rt, "SNIPER_ENTRY_THRESHOLD", 0.065) or 0.065)

    # 放寬 entry（關鍵）
    if score < entry_thr:
        return False

    # 必須是 early token
    if not (is_new or source in ["mempool", "pumpfun"]):
        return False

    if not sniper_guard(f):
        return False

    # 進一步避免太爛的早期 token
    if liq < float(getattr(rt, "MIN_LIQUIDITY_OBSERVE", 3000) or 3000):
        return False

    # 不要卡太死
    if getattr(rt, "SNIPER_A_PLUS_ONLY", False):
        if score < 0.11:
            return False

    return True


async def run_sniper_engine(tokens):
    ranked = []
    tokens = tokens if isinstance(tokens, list) else []

    for t in tokens:
        try:
            f = await features(t)
            if not f:
                continue

            score, _mode, detail = score_with_allocator(f)

            if not _sniper_pass(f, score):
                continue

            f["_score"] = score
            f["_mode"] = "sniper"
            f["_tier"] = "A+" if score > 0.13 else "A" if score > 0.09 else "B"
            f["_detail"] = detail

            ranked.append(f)
        except Exception:
            continue

    ranked.sort(key=lambda x: x.get("_score", 0.0), reverse=True)

    # fallback（避免 sniper 死掉）
    if not ranked:
        for t in tokens[:3]:
            try:
                f = await features(t)
                if not f:
                    continue

                source = str(f.get("source", "")).lower()
                if source not in {"mempool", "pumpfun"} and not bool(f.get("is_new", False)):
                    continue

                score, _mode, detail = score_with_allocator(f)

                liq = float(f.get("liq", 0) or 0)
                if liq < float(getattr(rt, "MIN_LIQUIDITY_OBSERVE", 3000) or 3000):
                    continue

                f["_score"] = score
                f["_mode"] = "sniper"
                f["_tier"] = "B"
                f["_detail"] = detail

                ranked.append(f)
            except Exception:
                continue

    return ranked[: int(getattr(rt, "SNIPER_TOP_K", 2) or 2)]
