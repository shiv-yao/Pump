import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

INDEX_HTML = PROJECT_ROOT / "index.html"
PLUGINS_DIR = PROJECT_ROOT / "plugins"
REGISTRY_FILE = PLUGINS_DIR / "registry.json"

PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

ENABLE_CLAUDE = os.getenv("ENABLE_CLAUDE", "true").lower() == "true"
ENABLE_OPENAI = os.getenv("ENABLE_OPENAI", "true").lower() == "true"

DEFAULT_CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
DEFAULT_GPT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

DEFAULT_SYSTEM_PROMPT = os.getenv(
    "AGENT_SYSTEM_PROMPT",
    "你是一個強大的 AI Agent，擁有多種 plugins 可以使用。"
    "根據用戶需求選擇合適的工具完成任務。使用繁體中文回應。"
)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

TRADING_API_BASE = os.getenv("TRADING_API_BASE", "").strip()
TRADING_API_KEY = os.getenv("TRADING_API_KEY", "").strip()


def mask_key(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:6]}***{value[-4:]}"
