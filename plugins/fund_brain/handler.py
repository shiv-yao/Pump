import json
WEIGHTS = {"price": 0.3, "event": 0.4, "wallet": 0.2, "momentum": 0.1, "onchain": 0.5}
def combine_alpha_signals(signals: dict) -> str:
    score = 0.0; side = None; used = {}
    for name, sig in signals.items():
        if not sig or isinstance(sig, str): continue
        try:
            w = WEIGHTS.get(name, 0); s = float(sig.get("score", 0))
            score += s * w; used[name] = {"weight": w, "score": s}
            if not side: side = sig.get("side")
        except Exception:
            continue
    if abs(score) < 0.2:
        return json.dumps({"decision": "SKIP", "score": score, "used": used}, ensure_ascii=False, indent=2)
    return json.dumps({"decision": side or "WATCH", "score": score, "used": used}, ensure_ascii=False, indent=2)
