def adaptive_filter(feature_row, _context=None, _no_trade_cycles=0):
    score = float(feature_row.get("_score", feature_row.get("score", 0.0)) or 0.0)
    liq = float(feature_row.get("liq", 0.0) or 0.0)
    smart = float(feature_row.get("smart", 0.0) or 0.0)
    breakout = float(feature_row.get("breakout", 0.0) or 0.0)
    meta = {
        "score": score,
        "liq": liq,
        "smart": smart,
        "breakout": breakout,
    }
    ok = score >= 0.08 and liq >= 3_000 and breakout > -0.03
    if smart >= 0.66:
        ok = ok or score >= 0.07
    return ok, meta
