import os
import json
import asyncio
from typing import Any, Dict, Optional

import httpx

from app.engine.utils import sf, clamp

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-4")

OPENAI_URL = os.getenv("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses")
ANTHROPIC_URL = os.getenv("ANTHROPIC_MESSAGES_URL", "https://api.anthropic.com/v1/messages")
XAI_URL = os.getenv("XAI_RESPONSES_URL", "https://api.x.ai/v1/responses")

LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "8.0"))
LLM_ENABLE_OPENAI = os.getenv("LLM_ENABLE_OPENAI", "true").lower() == "true"
LLM_ENABLE_CLAUDE = os.getenv("LLM_ENABLE_CLAUDE", "true").lower() == "true"
LLM_ENABLE_GROK = os.getenv("LLM_ENABLE_GROK", "true").lower() == "true"


def _safe_json_load(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        return {}


def _normalize_decision(raw: Dict[str, Any], provider: str) -> Dict[str, Any]:
    action = str(raw.get("action", "skip")).lower().strip()
    if action not in {"buy", "skip", "watch"}:
        action = "skip"

    return {
        "provider": provider,
        "action": action,
        "confidence": clamp(sf(raw.get("confidence", 0.0), 0.0), 0.0, 1.0),
        "win_prob": clamp(sf(raw.get("win_prob", 0.5), 0.5), 0.0, 1.0),
        "tp": sf(raw.get("tp", 0.0), 0.0),
        "sl": sf(raw.get("sl", 0.0), 0.0),
        "size_mult": clamp(sf(raw.get("size_mult", 1.0), 1.0), 0.25, 2.0),
        "reason": str(raw.get("reason", ""))[:500],
    }


def build_llm_payload(f: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mint": f.get("mint"),
        "source": f.get("source"),
        "price": sf(f.get("price", 0.0), 0.0),
        "liq": sf(f.get("liq", 0.0), 0.0),
        "breakout": sf(f.get("breakout", 0.0), 0.0),
        "momentum": sf(f.get("momentum", 0.0), 0.0),
        "smart": sf(f.get("smart", 0.0), 0.0),
        "wallet_count": int(sf(f.get("wallet_count", 0), 0)),
        "wallet_graph_score": sf(f.get("wallet_graph_score", 0.0), 0.0),
        "cluster_size": int(sf(f.get("cluster_size", 0), 0)),
        "smart_ratio": sf(f.get("smart_ratio", 0.0), 0.0),
        "concentration": sf(f.get("concentration", 0.0), 0.0),
        "fresh_wallet_ratio": sf(f.get("fresh_wallet_ratio", 0.0), 0.0),
        "mempool_bonus": sf(f.get("mempool_bonus", 0.0), 0.0),
        "early_bonus": sf(f.get("early_bonus", 0.0), 0.0),
        "mempool_hits": int(sf(f.get("mempool_hits", 0), 0)),
        "mempool_age_sec": sf(f.get("mempool_age_sec", 999.0), 999.0),
        "local_score": sf(f.get("_score", 0.0), 0.0),
        "local_mode": f.get("_mode", "momentum"),
        "local_tier": f.get("_tier", "B"),
        "ai_win_prob": sf(f.get("_ai_win_prob", 0.5), 0.5),
        "ai_pnl": sf(f.get("_ai_pnl", 0.0), 0.0),
        "ai_score": sf(f.get("_ai_score", 0.0), 0.0),
    }


def build_prompt(payload: Dict[str, Any]) -> str:
    return f"""
You are a crypto trading decision engine.
Return ONLY valid JSON.
No markdown.
No explanation outside JSON.

Goal:
Assess whether this token candidate should be bought right now.

Rules:
- Prefer safety over aggression.
- Reject low-quality setups.
- If liquidity or concentration looks bad, prefer skip.
- Use structured output exactly.

JSON schema:
{{
  "action": "buy|skip|watch",
  "confidence": 0.0,
  "win_prob": 0.0,
  "tp": 0.0,
  "sl": 0.0,
  "size_mult": 1.0,
  "reason": "short reason"
}}

Candidate:
{json.dumps(payload, ensure_ascii=False)}
""".strip()


async def _call_openai(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not OPENAI_API_KEY or not LLM_ENABLE_OPENAI:
        return _normalize_decision({}, "openai")

    prompt = build_prompt(payload)

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": OPENAI_MODEL,
        "input": prompt,
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SEC) as client:
            r = await client.post(OPENAI_URL, headers=headers, json=body)
            data = r.json()

        text = ""
        if isinstance(data, dict):
            text = data.get("output_text", "") or ""

        return _normalize_decision(_safe_json_load(text), "openai")
    except Exception:
        return _normalize_decision({}, "openai")


async def _call_claude(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not ANTHROPIC_API_KEY or not LLM_ENABLE_CLAUDE:
        return _normalize_decision({}, "claude")

    prompt = build_prompt(payload)

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 300,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SEC) as client:
            r = await client.post(ANTHROPIC_URL, headers=headers, json=body)
            data = r.json()

        text = ""
        if isinstance(data, dict):
            content = data.get("content", [])
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    text = first.get("text", "") or ""

        return _normalize_decision(_safe_json_load(text), "claude")
    except Exception:
        return _normalize_decision({}, "claude")


async def _call_grok(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not XAI_API_KEY or not LLM_ENABLE_GROK:
        return _normalize_decision({}, "grok")

    prompt = build_prompt(payload)

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": GROK_MODEL,
        "input": prompt,
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SEC) as client:
            r = await client.post(XAI_URL, headers=headers, json=body)
            data = r.json()

        text = ""
        if isinstance(data, dict):
            text = data.get("output_text", "") or ""

        return _normalize_decision(_safe_json_load(text), "grok")
    except Exception:
        return _normalize_decision({}, "grok")


async def multi_llm_review(f: Dict[str, Any]) -> Dict[str, Any]:
    payload = build_llm_payload(f)

    openai_task = _call_openai(payload)
    claude_task = _call_claude(payload)
    grok_task = _call_grok(payload)

    results = await asyncio.gather(
        openai_task,
        claude_task,
        grok_task,
        return_exceptions=True,
    )

    decisions = []
    for item in results:
        if isinstance(item, dict):
            decisions.append(item)

    return {
        "payload": payload,
        "decisions": decisions,
    }
