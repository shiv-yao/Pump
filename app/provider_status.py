import os

try:
    import anthropic
except Exception:
    anthropic = None

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

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

    if not anthropic:
        return {
            "provider": "claude",
            "ok": False,
            "status": "missing_dependency",
            "message": "anthropic 套件未安裝",
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
    except Exception as e:
        msg = str(e).lower()
        if "credit balance is too low" in msg or "billing" in msg:
            status = "low_balance"
            human = "Claude 餘額不足"
        elif "invalid x-api-key" in msg or "authentication" in msg or "unauthorized" in msg:
            status = "invalid_key"
            human = "Claude API key 無效"
        elif "model" in msg and ("not found" in msg or "not allowed" in msg):
            status = "model_error"
            human = "Claude 模型名稱錯誤或無權限"
        else:
            status = "error"
            human = "Claude 檢查失敗"

        return {
            "provider": "claude",
            "ok": False,
            "status": status,
            "message": human,
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

    if not AsyncOpenAI:
        return {
            "provider": "openai",
            "ok": False,
            "status": "missing_dependency",
            "message": "openai 套件未安裝",
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
    except Exception as e:
        msg = str(e).lower()
        if "incorrect api key" in msg or "invalid_api_key" in msg or "401" in msg:
            status = "invalid_key"
            human = "OpenAI API key 無效"
        elif "quota" in msg or "billing" in msg or "insufficient" in msg:
            status = "billing_error"
            human = "OpenAI billing / 額度有問題"
        elif "model" in msg and ("not found" in msg or "does not exist" in msg):
            status = "model_error"
            human = "OpenAI 模型名稱錯誤"
        else:
            status = "error"
            human = "OpenAI 檢查失敗"

        return {
            "provider": "openai",
            "ok": False,
            "status": status,
            "message": human,
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
