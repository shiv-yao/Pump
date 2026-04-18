import os

import anthropic
from openai import AsyncOpenAI

from app.settings import (
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_GPT_MODEL,
    ENABLE_CLAUDE,
    ENABLE_OPENAI,
    TRADING_API_BASE,
    TRADING_API_KEY,
    mask_key,
)


def is_fallback_error(message: str) -> bool:
    msg = message.lower()
    markers = [
        "credit balance is too low",
        "purchase credits",
        "plans & billing",
        "billing",
        "quota",
        "authentication_error",
        "invalid x-api-key",
        "unauthorized",
        "forbidden",
        "model not found",
        "not allowed",
        "incorrect api key",
        "invalid_api_key",
        "overloaded",
        "temporarily unavailable",
        "401",
        "403",
    ]
    return any(m in msg for m in markers)


async def check_claude_status() -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model = DEFAULT_CLAUDE_MODEL

    if not ENABLE_CLAUDE:
        return {
            "provider": "claude",
            "ok": False,
            "status": "disabled",
            "message": "Claude 已停用",
            "model": model,
            "key_masked": "",
        }

    if not api_key:
        return {
            "provider": "claude",
            "ok": False,
            "status": "missing_key",
            "message": "ANTHROPIC_API_KEY 未設定",
            "model": model,
            "key_masked": "",
        }

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        await client.messages.create(
            model=model,
            max_tokens=8,
            messages=[{"role": "user", "content": "ping"}],
        )
        return {
            "provider": "claude",
            "ok": True,
            "status": "ok",
            "message": "Claude API 可用",
            "model": model,
            "key_masked": mask_key(api_key),
        }
    except Exception:
        return {
            "provider": "claude",
            "ok": False,
            "status": "error",
            "message": "Claude 檢查失敗",
            "model": model,
            "key_masked": mask_key(api_key),
        }


async def check_openai_status() -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = DEFAULT_GPT_MODEL

    if not ENABLE_OPENAI:
        return {
            "provider": "openai",
            "ok": False,
            "status": "disabled",
            "message": "GPT fallback 已停用",
            "model": model,
            "key_masked": "",
        }

    if not api_key:
        return {
            "provider": "openai",
            "ok": False,
            "status": "missing_key",
            "message": "OPENAI_API_KEY 未設定",
            "model": model,
            "key_masked": "",
        }

    try:
        client = AsyncOpenAI(api_key=api_key)
        await client.responses.create(model=model, input="ping")
        return {
            "provider": "openai",
            "ok": True,
            "status": "ok",
            "message": "OpenAI API 可用",
            "model": model,
            "key_masked": mask_key(api_key),
        }
    except Exception:
        return {
            "provider": "openai",
            "ok": False,
            "status": "error",
            "message": "OpenAI 檢查失敗",
            "model": model,
            "key_masked": mask_key(api_key),
        }


def check_trading_status() -> dict:
    if not TRADING_API_BASE:
        return {
            "provider": "trading_api",
            "ok": False,
            "status": "missing_base",
            "message": "TRADING_API_BASE 未設定",
            "base": "",
            "key_masked": "",
        }

    return {
        "provider": "trading_api",
        "ok": True,
        "status": "configured",
        "message": "Trading API 已設定",
        "base": TRADING_API_BASE,
        "key_masked": mask_key(TRADING_API_KEY) if TRADING_API_KEY else "",
    }
