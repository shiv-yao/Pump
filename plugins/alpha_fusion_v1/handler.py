def fuse_alpha(alpha_inputs: dict):
    weights = {
        "orderbook": 0.4,
        "wallet": 0.3,
        "momentum": 0.2,
        "event": 0.1
    }

    score = 0.0
    total_weight = 0.0

    for key, value in (alpha_inputs or {}).items():
        try:
            v = float(value)
        except Exception:
            continue

        w = float(weights.get(key, 0.0))
        score += w * v
        total_weight += w

    if total_weight > 0:
        score = score / total_weight

    if score > 0.6:
        decision = "buy"
    elif score < 0.4:
        decision = "sell"
    else:
        decision = "hold"

    return {
        "score": score,
        "decision": decision
    }
