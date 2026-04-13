from app.engine import runtime as rt
from app.engine.features import features, score_with_allocator, safe_adaptive_filter

try:
    from app.engine.ai_predictor import predict_trade_quality
except Exception:
    def predict_trade_quality(_f):
        return {
            "win_prob": 0.5,
            "expected_pnl": 0.0,
            "score": 0.0,
        }


def _stable_pass(f, score):
    liq = float(f.get("liq", 0) or 0)
    wg = float(f.get("wallet_graph_score", 0) or 0)
    smart = float(f.get("smart", 0) or 0)
    source = str(f.get("source", "")).lower()
    is_new = bool(f.get("is_new", False))

    entry_thr = float(getattr(rt, "STABLE_ENTRY_THRESHOLD", 0.075) or 0.075)
    min_liq_trade = float(getattr(rt, "MIN_LIQUIDITY_TRADE", 20000) or 20000)

    # 穩定策略門檻
    if score < entry_thr:
        return False

    # 流動性不要卡太死，但 still prefer better liquidity
    if liq < max(min_liq_trade, 15000):
        return False

    # 穩定策略不優先追最早期標的，除非品質很好
    if is_new and score < (entry_thr + 0.02):
        return False

    if source in {"mempool", "pumpfun"} and score < (entry_thr + 0.02):
        return False

    # 強 wallet graph → 直接過
    if wg > 0.45:
        return True

    # smart money + liquidity
    if smart > 0.45 and liq > 30000:
        return True

    # 高流動性 + 好分數也可過
    if liq > 50000 and score > 0.095:
        return True

    # fallback（防止完全不交易）
    if score > 0.10:
        return True

    return False


async def run_stable_engine(tokens):
    ranked = []
    tokens = tokens if isinstance(tokens, list) else []

    for t in tokens:
        try:
            f = await features(t)
            if not f:
                continue

            score, _mode, detail = score_with_allocator(f)

            # ===== V82 AI predictor =====
            ai = predict_trade_quality(f)
            f["_ai_win_prob"] = float(ai.get("win_prob", 0.5) or 0.5)
            f["_ai_pnl"] = float(ai.get("expected_pnl", 0.0) or 0.0)
            f["_ai_score"] = float(ai.get("score", 0.0) or 0.0)

            # stable 對 AI 要求可略高一點
            if f["_ai_win_prob"] < 0.50:
                continue

            score *= (0.75 + f["_ai_win_prob"] * 0.50)

            if not _stable_pass(f, score):
                continue

            ok, _ = safe_adaptive_filter(
                {
                    **f,
                    "_score": score,
                },
                None,
                getattr(getattr(rt, "engine", None), "no_trade_cycles", 0),
            )
            if not ok and score < getattr(rt, "FILTER_SCORE_BYPASS", 0.13):
                continue

            f["_score"] = score
            f["_mode"] = "stable"
            f["_tier"] = "A+" if score > 0.13 else "A" if score > 0.09 else "B"
            f["_detail"] = detail

            ranked.append(f)
        except Exception:
            continue

    ranked.sort(key=lambda x: x.get("_score", 0.0), reverse=True)

    # fallback：如果完全沒東西 → 放寬
    if not ranked:
        for t in tokens[:5]:
            try:
                f = await features(t)
                if not f:
                    continue

                score, _mode, detail = score_with_allocator(f)

                ai = predict_trade_quality(f)
                f["_ai_win_prob"] = float(ai.get("win_prob", 0.5) or 0.5)
                f["_ai_pnl"] = float(ai.get("expected_pnl", 0.0) or 0.0)
                f["_ai_score"] = float(ai.get("score", 0.0) or 0.0)

                if f["_ai_win_prob"] < 0.45:
                    continue

                liq = float(f.get("liq", 0) or 0)
                if liq < float(getattr(rt, "MIN_LIQUIDITY_OBSERVE", 3000) or 3000):
                    continue

                score *= (0.75 + f["_ai_win_prob"] * 0.50)

                f["_score"] = score
                f["_mode"] = "stable"
                f["_tier"] = "B"
                f["_detail"] = detail
                ranked.append(f)
            except Exception:
                continue

    return ranked[: int(getattr(rt, "STABLE_TOP_K", 3) or 3)]
