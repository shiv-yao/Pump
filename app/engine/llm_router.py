from typing import Any, Dict, List

from app.engine.utils import sf, clamp


def _score_action(action: str) -> float:
    action = str(action or "").lower().strip()
    if action == "buy":
        return 1.0
    if action == "watch":
        return 0.4
    return 0.0


def fuse_llm_decisions(review: Dict[str, Any]) -> Dict[str, Any]:
    decisions: List[Dict[str, Any]] = list(review.get("decisions", []) or [])

    if not decisions:
        return {
            "llm_score": 0.0,
            "llm_buy_votes": 0,
            "llm_watch_votes": 0,
            "llm_skip_votes": 0,
            "llm_win_prob": 0.5,
            "llm_tp": 0.0,
            "llm_sl": 0.0,
            "llm_size_mult": 1.0,
            "llm_reason": "no_llm",
        }

    buy_votes = 0
    watch_votes = 0
    skip_votes = 0

    weighted_score = 0.0
    weight_sum = 0.0
    win_prob_sum = 0.0
    tp_sum = 0.0
    sl_sum = 0.0
    size_mult_sum = 0.0

    for d in decisions:
        action = str(d.get("action", "skip")).lower()
        conf = clamp(sf(d.get("confidence", 0.0), 0.0), 0.0, 1.0)
        win_prob = clamp(sf(d.get("win_prob", 0.5), 0.5), 0.0, 1.0)
        tp = sf(d.get("tp", 0.0), 0.0)
        sl = sf(d.get("sl", 0.0), 0.0)
        size_mult = clamp(sf(d.get("size_mult", 1.0), 1.0), 0.25, 2.0)

        w = max(conf, 0.2)

        if action == "buy":
            buy_votes += 1
        elif action == "watch":
            watch_votes += 1
        else:
            skip_votes += 1

        weighted_score += _score_action(action) * w
        win_prob_sum += win_prob * w
        tp_sum += tp * w
        sl_sum += sl * w
        size_mult_sum += size_mult * w
        weight_sum += w

    if weight_sum <= 0:
        weight_sum = 1.0

    reasons = [str(d.get("provider", "")) + ":" + str(d.get("action", "")) for d in decisions]

    return {
        "llm_score": weighted_score / weight_sum,
        "llm_buy_votes": buy_votes,
        "llm_watch_votes": watch_votes,
        "llm_skip_votes": skip_votes,
        "llm_win_prob": win_prob_sum / weight_sum,
        "llm_tp": tp_sum / weight_sum,
        "llm_sl": sl_sum / weight_sum,
        "llm_size_mult": size_mult_sum / weight_sum,
        "llm_reason": " | ".join(reasons)[:500],
    }


def apply_llm_to_candidate(f: Dict[str, Any], fused: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(f)

    local_score = sf(out.get("_score", 0.0), 0.0)
    llm_score = sf(fused.get("llm_score", 0.0), 0.0)
    llm_win_prob = clamp(sf(fused.get("llm_win_prob", 0.5), 0.5), 0.0, 1.0)

    final_score = (
        local_score * 0.70
        + llm_score * 0.20
        + llm_win_prob * 0.10
    )

    out["_llm_score"] = llm_score
    out["_llm_win_prob"] = llm_win_prob
    out["_llm_tp"] = sf(fused.get("llm_tp", 0.0), 0.0)
    out["_llm_sl"] = sf(fused.get("llm_sl", 0.0), 0.0)
    out["_llm_size_mult"] = clamp(sf(fused.get("llm_size_mult", 1.0), 1.0), 0.25, 2.0)
    out["_llm_buy_votes"] = int(fused.get("llm_buy_votes", 0))
    out["_llm_reason"] = fused.get("llm_reason", "")
    out["_score"] = final_score

    return out
