import json
import asyncio
from typing import Dict, List, Any

from app.engine import runtime as rt
from app.engine.utils import sf, clamp


def _enabled(name: str, default=False) -> bool:
    try:
        v = getattr(rt, name, default)
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        return default


def _model(name: str, default: str) -> str:
    try:
        v = getattr(rt, name, default)
        return str(v).strip() if v else default
    except Exception:
        return default


def _api_key(name: str) -> str:
    try:
        v = getattr(rt, name, "")
        return str(v).strip()
    except Exception:
        return ""


def _top_k() -> int:
    try:
        return max(1, int(getattr(rt, "LLM_REVIEW_TOP_K", 2) or 2))
    except Exception:
        return 2


def _min_score() -> float:
    try:
        return float(getattr(rt, "LLM_MIN_SCORE", 0.35) or 0.35)
    except Exception:
        return 0.35


def llm_brain_enabled() -> bool:
    return _enabled("ENABLE_LLM_BRAIN", False)


def candidate_payload(f: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mint": f.get("mint"),
        "source": f.get("source"),
        "price": sf(f.get("price", 0.0), 0.0),
        "liq": sf(f.get("liq", 0.0), 0.0),
        "breakout": sf(f.get("breakout", 0.0), 0.0),
        "momentum": sf(f.get("momentum", 0.0), 0.0),
        "smart": sf(f.get("smart", 0.0), 0.0),
        "wallet_count": int(f.get("wallet_count", 0) or 0),
        "wallet_graph_score": sf(f.get("wallet_graph_score", 0.0), 0.0),
        "smart_ratio": sf(f.get("smart_ratio", 0.0), 0.0),
        "concentration": sf(f.get("concentration", 0.0), 0.0),
        "fresh_wallet_ratio": sf(f.get("fresh_wallet_ratio", 0.0), 0.0),
        "mempool_bonus": sf(f.get("mempool_bonus", 0.0), 0.0),
        "early_bonus": sf(f.get("early_bonus", 0.0), 0.0),
        "score": sf(f.get("_score", 0.0), 0.0),
        "tier": f.get("_tier", "B"),
        "mode": f.get("_mode", "momentum"),
        "ai_win_prob": sf(f.get("_ai_win_prob", 0.5), 0.5),
        "ai_pnl": sf(f.get("_ai_pnl", 0.0), 0.0),
    }


def build_prompt(f: Dict[str, Any]) -> str:
    payload = candidate_payload(f)
    return (
        "You are a crypto trading risk reviewer.\n"
        "Review this token candidate and output strict JSON only.\n"
        "Required JSON schema:\n"
        '{"decision":"buy|skip","confidence":0.0,"score_adjust":-0.15,"reason":"short"}\n'
        "Rules:\n"
        "- Prefer safety over aggression.\n"
        "- Skip if liquidity is weak, concentration is high, or momentum is bad.\n"
        "- Small positive score_adjust if strong early/smart-money setup.\n"
        "- Keep score_adjust between -0.15 and +0.15.\n"
        "- Output JSON only.\n\n"
        f"candidate={json.dumps(payload, ensure_ascii=False)}"
    )


async def _call_openai(prompt: str) -> Dict[str, Any]:
    try:
        from openai import AsyncOpenAI
    except Exception:
        return {"decision": "skip", "confidence": 0.0, "score_adjust": -0.02, "reason": "openai_sdk_missing"}

    key = _api_key("OPENAI_API_KEY")
    if not key:
        return {"decision": "skip", "confidence": 0.0, "score_adjust": -0.02, "reason": "openai_key_missing"}

    model = _model("OPENAI_MODEL", "gpt-5.4")
    client = AsyncOpenAI(api_key=key)

    try:
        resp = await client.responses.create(
            model=model,
            input=prompt,
        )
        text = getattr(resp, "output_text", "") or ""
        return _parse_llm_json(text, provider="openai")
    except Exception as e:
        return {"decision": "skip", "confidence": 0.0, "score_adjust": -0.02, "reason": f"openai_error:{e}"}


async def _call_claude(prompt: str) -> Dict[str, Any]:
    try:
        import anthropic
    except Exception:
        return {"decision": "skip", "confidence": 0.0, "score_adjust": -0.02, "reason": "anthropic_sdk_missing"}

    key = _api_key("ANTHROPIC_API_KEY")
    if not key:
        return {"decision": "skip", "confidence": 0.0, "score_adjust": -0.02, "reason": "anthropic_key_missing"}

    model = _model("ANTHROPIC_MODEL", "claude-sonnet-4.5")
    client = anthropic.AsyncAnthropic(api_key=key)

    try:
        msg = await client.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in getattr(msg, "content", []) or []:
            if getattr(block, "type", "") == "text":
                text += getattr(block, "text", "")
        return _parse_llm_json(text, provider="claude")
    except Exception as e:
        return {"decision": "skip", "confidence": 0.0, "score_adjust": -0.02, "reason": f"claude_error:{e}"}


async def _call_grok(prompt: str) -> Dict[str, Any]:
    try:
        from openai import AsyncOpenAI
    except Exception:
        return {"decision": "skip", "confidence": 0.0, "score_adjust": -0.02, "reason": "grok_sdk_missing"}

    key = _api_key("XAI_API_KEY")
    if not key:
        return {"decision": "skip", "confidence": 0.0, "score_adjust": -0.02, "reason": "grok_key_missing"}

    model = _model("XAI_MODEL", "grok-4")
    try:
        client = AsyncOpenAI(
            api_key=key,
            base_url="https://api.x.ai/v1",
        )
        resp = await client.responses.create(
            model=model,
            input=prompt,
        )
        text = getattr(resp, "output_text", "") or ""
        return _parse_llm_json(text, provider="grok")
    except Exception as e:
        return {"decision": "skip", "confidence": 0.0, "score_adjust": -0.02, "reason": f"grok_error:{e}"}


def _parse_llm_json(text: str, provider: str) -> Dict[str, Any]:
    try:
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        data = json.loads(text)

        decision = str(data.get("decision", "skip")).strip().lower()
        if decision not in {"buy", "skip"}:
            decision = "skip"

        confidence = clamp(sf(data.get("confidence", 0.0), 0.0), 0.0, 1.0)
        score_adjust = clamp(sf(data.get("score_adjust", 0.0), 0.0), -0.15, 0.15)
        reason = str(data.get("reason", f"{provider}_ok"))[:160]

        return {
            "decision": decision,
            "confidence": confidence,
            "score_adjust": score_adjust,
            "reason": reason,
            "provider": provider,
        }
    except Exception:
        return {
            "decision": "skip",
            "confidence": 0.0,
            "score_adjust": -0.01,
            "reason": f"{provider}_bad_json",
            "provider": provider,
        }


async def review_candidate_with_llms(f: Dict[str, Any]) -> Dict[str, Any]:
    if not llm_brain_enabled():
        return {
            "enabled": False,
            "decision": "buy",
            "confidence": 0.5,
            "score_adjust": 0.0,
            "reason": "llm_disabled",
            "votes": [],
        }

    prompt = build_prompt(f)
    tasks = []

    if _enabled("LLM_ENABLE_OPENAI", False):
        tasks.append(_call_openai(prompt))
    if _enabled("LLM_ENABLE_CLAUDE", False):
        tasks.append(_call_claude(prompt))
    if _enabled("LLM_ENABLE_GROK", False):
        tasks.append(_call_grok(prompt))

    if not tasks:
        return {
            "enabled": True,
            "decision": "buy",
            "confidence": 0.5,
            "score_adjust": 0.0,
            "reason": "no_provider_enabled",
            "votes": [],
        }

    results = await asyncio.gather(*tasks, return_exceptions=True)

    votes: List[Dict[str, Any]] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        if isinstance(r, dict):
            votes.append(r)

    if not votes:
        return {
            "enabled": True,
            "decision": "skip",
            "confidence": 0.0,
            "score_adjust": -0.02,
            "reason": "all_llm_failed",
            "votes": [],
        }

    buy_votes = [v for v in votes if v.get("decision") == "buy"]
    skip_votes = [v for v in votes if v.get("decision") == "skip"]

    avg_conf = sum(sf(v.get("confidence", 0.0), 0.0) for v in votes) / max(len(votes), 1)
    avg_adjust = sum(sf(v.get("score_adjust", 0.0), 0.0) for v in votes) / max(len(votes), 1)

    if len(buy_votes) >= len(skip_votes):
        final_decision = "buy"
    else:
        final_decision = "skip"

    if final_decision == "skip" and avg_adjust > 0:
        avg_adjust = -abs(avg_adjust)

    return {
        "enabled": True,
        "decision": final_decision,
        "confidence": clamp(avg_conf, 0.0, 1.0),
        "score_adjust": clamp(avg_adjust, -0.15, 0.15),
        "reason": "|".join([str(v.get("reason", "")) for v in votes][:3])[:220],
        "votes": votes,
    }


async def apply_llm_review(ranked: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not llm_brain_enabled():
        return ranked if isinstance(ranked, list) else []

    ranked = ranked if isinstance(ranked, list) else []
    if not ranked:
        return []

    min_score = _min_score()
    review_k = _top_k()

    reviewed = []
    untouched = []

    for i, f in enumerate(ranked):
        if i < review_k and sf(f.get("_score", 0.0), 0.0) >= min_score:
            reviewed.append(f)
        else:
            untouched.append(f)

    out = []
    for f in reviewed:
        llm = await review_candidate_with_llms(f)
        f["_llm"] = llm
        f["_llm_decision"] = llm.get("decision", "skip")
        f["_llm_confidence"] = sf(llm.get("confidence", 0.0), 0.0)
        f["_llm_reason"] = llm.get("reason", "")

        base = sf(f.get("_score", 0.0), 0.0)
        adj = sf(llm.get("score_adjust", 0.0), 0.0)

        if llm.get("decision") == "skip":
            f["_score"] = max(0.0, base + min(adj, -0.02))
        else:
            f["_score"] = clamp(base + adj, 0.0, getattr(rt, "MAX_SCORE", 1.5))

        if f["_score"] >= 0.145:
            f["_tier"] = "A+"
        elif f["_score"] >= getattr(rt, "STRICT_A_TIER_THRESHOLD", 0.095):
            f["_tier"] = "A"
        else:
            f["_tier"] = "B"

        out.append(f)

    out.extend(untouched)
    out.sort(key=lambda x: x.get("_score", 0.0), reverse=True)
    return out
