import importlib.util
import inspect
import json
import logging
import os
import shutil
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# =========================================================
# PATHS
# =========================================================
BASE_DIR = Path(__file__).resolve().parent          # /app/app
PROJECT_ROOT = BASE_DIR.parent                      # /app

INDEX_HTML = PROJECT_ROOT / "index.html"
PLUGINS_DIR = PROJECT_ROOT / "plugins"
REGISTRY_FILE = PLUGINS_DIR / "registry.json"
INSTALLED_PLUGINS_FILE = PROJECT_ROOT / "installed_plugins.json"

PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# GLOBALS
# =========================================================
plugin_registry: dict[str, dict] = {}
agent_sessions: dict[str, "AgentSession"] = {}

DEFAULT_CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
DEFAULT_GPT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "AGENT_SYSTEM_PROMPT",
    "你是一個強大的 AI Agent，擁有多種 plugins 可以使用。"
    "根據用戶需求選擇合適的工具完成任務。使用繁體中文回應。"
)

ENABLE_CLAUDE = os.getenv("ENABLE_CLAUDE", "true").lower() == "true"
ENABLE_OPENAI = os.getenv("ENABLE_OPENAI", "true").lower() == "true"

# =========================================================
# REQUEST MODELS
# =========================================================
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list = Field(default_factory=list)


class CommandRequest(BaseModel):
    command: str
    session_id: str = "default"


class InstallPluginRequest(BaseModel):
    name: str
    url: Optional[str] = None
    manifest: Optional[dict] = None


class PluginManualCreate(BaseModel):
    name: str
    description: str
    tools: list[dict]
    handler_code: Optional[str] = None
    category: Optional[str] = "utility"
    price: Optional[float] = 0


# =========================================================
# HELPERS
# =========================================================
def mask_key(value: str) -> str:
    if not value:
        return ""
    v = value.strip()
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:6]}***{v[-4:]}"


def flatten_history_to_text(history: Optional[list]) -> str:
    if not history:
        return ""
    lines = []
    for item in history:
        role = item.get("role", "unknown")
        content = item.get("content", "")
        if isinstance(content, list):
            try:
                content = json.dumps(content, ensure_ascii=False)
            except Exception:
                content = str(content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


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


# =========================================================
# INSTALLED PLUGINS PERSISTENCE
# =========================================================
def load_installed_plugin_records() -> list[dict]:
    if not INSTALLED_PLUGINS_FILE.exists():
        return []

    try:
        with open(INSTALLED_PLUGINS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        log.error(f"Failed to load installed plugin records: {e}")
        return []


def save_installed_plugin_records(records: list[dict]) -> None:
    try:
        with open(INSTALLED_PLUGINS_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Failed to save installed plugin records: {e}")


def remember_installed_plugin(name: str, url: str) -> None:
    records = load_installed_plugin_records()

    exists = any(
        item.get("name") == name and item.get("url") == url
        for item in records
    )

    if not exists:
        records.append({"name": name, "url": url})
        save_installed_plugin_records(records)


def forget_installed_plugin(name: str) -> None:
    records = load_installed_plugin_records()
    filtered = [item for item in records if item.get("name") != name]
    save_installed_plugin_records(filtered)


# =========================================================
# PLUGIN LOADER
# =========================================================
def load_plugin_manifest(plugin_dir: Path) -> Optional[dict]:
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        manifest_path = plugin_dir / "skill.json"
        if not manifest_path.exists():
            return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "id" not in data:
            data["id"] = data.get("name", plugin_dir.name)
        if "name" not in data:
            data["name"] = data["id"]

        data.setdefault("description", "")
        data.setdefault("version", "1.0.0")
        data.setdefault("enabled", True)
        data.setdefault("category", "utility")
        data.setdefault("price", 0)
        data.setdefault("author", "local")
        data.setdefault("tools", [])

        return data

    except Exception as e:
        log.error(f"Failed loading manifest {manifest_path}: {e}")
        return None


def load_all_plugins():
    global plugin_registry
    plugin_registry = {}

    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    for path in PLUGINS_DIR.iterdir():
        if not path.is_dir():
            continue

        manifest = load_plugin_manifest(path)
        if not manifest:
            continue

        plugin_id = manifest.get("id", path.name)
        plugin_registry[plugin_id] = {
            "manifest": manifest,
            "path": str(path),
            "enabled": manifest.get("enabled", True),
        }
        log.info(f"Loaded plugin: {plugin_id}")

    log.info(f"Total plugins loaded: {len(plugin_registry)}")


def get_active_tools() -> list[dict]:
    tools = []
    for plugin in plugin_registry.values():
        if not plugin["enabled"]:
            continue
        for tool in plugin["manifest"].get("tools", []):
            if isinstance(tool, dict) and tool.get("name"):
                tools.append(tool)
    return tools


async def execute_tool(tool_name: str, tool_input: dict):
    for plugin_id, plugin in plugin_registry.items():
        if not plugin["enabled"]:
            continue

        for tool in plugin["manifest"].get("tools", []):
            if tool.get("name") != tool_name:
                continue

            plugin_path = Path(plugin["path"])
            handler_file = plugin_path / "handler.py"

            if not handler_file.exists():
                return f"Tool '{tool_name}' handler.py not found in plugin '{plugin_id}'."

            try:
                spec = importlib.util.spec_from_file_location(f"plugin_{plugin_id}", handler_file)
                if spec is None or spec.loader is None:
                    return f"Tool '{tool_name}' failed to load module spec."

                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                if not hasattr(mod, tool_name):
                    return f"Tool '{tool_name}' function not found in handler.py."

                fn = getattr(mod, tool_name)

                if inspect.iscoroutinefunction(fn):
                    result = await fn(**tool_input)
                else:
                    result = fn(**tool_input)

                if result is None:
                    return ""

                if isinstance(result, (dict, list)):
                    return json.dumps(result, ensure_ascii=False, indent=2)

                return str(result)

            except Exception:
                return f"Tool execution error:\n{traceback.format_exc()}"

    return f"tool not found: {tool_name}"


# =========================================================
# PROVIDER STATUS
# =========================================================
async def check_claude_status() -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model = os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)

    if not ENABLE_CLAUDE:
        return {
            "provider": "claude",
            "ok": False,
            "status": "disabled",
            "message": "Claude 已停用",
            "model": model,
            "key_masked": ""
        }

    if not api_key:
        return {
            "provider": "claude",
            "ok": False,
            "status": "missing_key",
            "message": "ANTHROPIC_API_KEY 未設定",
            "model": model,
            "key_masked": ""
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
            "key_masked": mask_key(api_key)
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
            "key_masked": mask_key(api_key)
        }


async def check_openai_status() -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", DEFAULT_GPT_MODEL)

    if not ENABLE_OPENAI:
        return {
            "provider": "openai",
            "ok": False,
            "status": "disabled",
            "message": "GPT fallback 已停用",
            "model": model,
            "key_masked": ""
        }

    if not api_key:
        return {
            "provider": "openai",
            "ok": False,
            "status": "missing_key",
            "message": "OPENAI_API_KEY 未設定",
            "model": model,
            "key_masked": ""
        }

    try:
        client = AsyncOpenAI(api_key=api_key)
        await client.responses.create(
            model=model,
            input="ping"
        )
        return {
            "provider": "openai",
            "ok": True,
            "status": "ok",
            "message": "OpenAI API 可用",
            "model": model,
            "key_masked": mask_key(api_key)
        }
    except Exception as e:
        msg = str(e).lower()

        if "invalid_api_key" in msg or "incorrect api key" in msg or "401" in msg:
            status = "invalid_key"
            human = "OpenAI API key 無效"
        elif "billing" in msg or "quota" in msg or "insufficient" in msg:
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
            "key_masked": mask_key(api_key)
        }


def check_trading_status() -> dict:
    base = os.getenv("TRADING_API_BASE", "").strip()
    key = os.getenv("TRADING_API_KEY", "").strip()

    if not base:
        return {
            "provider": "trading_api",
            "ok": False,
            "status": "missing_base",
            "message": "TRADING_API_BASE 未設定",
            "base": "",
            "key_masked": ""
        }

    return {
        "provider": "trading_api",
        "ok": True,
        "status": "configured",
        "message": "Trading API 已設定",
        "base": base,
        "key_masked": mask_key(key) if key else ""
    }


# =========================================================
# STORE / INSTALL
# =========================================================
def get_store_registry():
    if not REGISTRY_FILE.exists():
        return []

    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


async def install_plugin_from_url(plugin_name: str, url: str, remember: bool = True) -> bool:
    plugin_dir = PLUGINS_DIR / plugin_name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    base = url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            manifest_resp = await client.get(f"{base}/plugin.json")
            if manifest_resp.status_code != 200:
                manifest_resp = await client.get(f"{base}/skill.json")
                if manifest_resp.status_code != 200:
                    log.error(f"plugin.json/skill.json not found from {base}")
                    return False

            handler_resp = await client.get(f"{base}/handler.py")

            try:
                manifest = manifest_resp.json()
            except Exception:
                log.error("Invalid plugin manifest JSON")
                return False

            if "id" not in manifest:
                manifest["id"] = plugin_name
            if "name" not in manifest:
                manifest["name"] = plugin_name

            with open(plugin_dir / "plugin.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            if handler_resp.status_code == 200:
                with open(plugin_dir / "handler.py", "w", encoding="utf-8") as f:
                    f.write(handler_resp.text)

        load_all_plugins()

        if remember:
            remember_installed_plugin(plugin_name, url)

        return True

    except Exception as e:
        log.error(f"install_plugin_from_url error: {e}")
        return False


async def restore_installed_plugins() -> None:
    records = load_installed_plugin_records()
    if not records:
        log.info("No installed plugin records to restore.")
        return

    log.info(f"Restoring {len(records)} installed plugins...")

    for item in records:
        name = item.get("name", "").strip()
        url = item.get("url", "").strip()

        if not name or not url:
            continue

        try:
            ok = await install_plugin_from_url(name, url, remember=False)
            if ok:
                log.info(f"Restored plugin: {name}")
            else:
                log.warning(f"Failed to restore plugin: {name}")
        except Exception as e:
            log.error(f"Error restoring plugin {name}: {e}")


# =========================================================
# BUILTIN PLUGINS
# =========================================================
async def ensure_builtin_plugins():
    builtin_plugins = {
        "calculator": {
            "plugin_json": {
                "id": "calculator",
                "name": "calculator",
                "description": "數學計算工具",
                "version": "1.0.0",
                "enabled": True,
                "category": "utility",
                "price": 0,
                "author": "system",
                "tools": [{
                    "name": "calculate",
                    "description": "執行數學運算",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string", "description": "例如 2+2*10"}
                        },
                        "required": ["expression"]
                    }
                }]
            },
            "handler": '''import ast
import operator

def calculate(expression: str) -> str:
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.Mod: operator.mod,
    }

    def eval_node(node):
        if isinstance(node, ast.Num):
            return node.n
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in ops:
                raise ValueError(f"Unsupported operator: {op_type}")
            return ops[op_type](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in ops:
                raise ValueError(f"Unsupported unary operator: {op_type}")
            return ops[op_type](eval_node(node.operand))
        raise ValueError(f"Unsupported expression: {node}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = eval_node(tree.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"計算錯誤: {e}"
'''
        },
        "web_search": {
            "plugin_json": {
                "id": "web_search",
                "name": "web_search",
                "description": "搜尋網路上的最新資訊",
                "version": "1.0.0",
                "enabled": True,
                "category": "utility",
                "price": 0,
                "author": "system",
                "tools": [{
                    "name": "web_search",
                    "description": "搜尋網路上的資訊",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "搜尋關鍵字"}
                        },
                        "required": ["query"]
                    }
                }]
            },
            "handler": '''import os
import httpx

async def web_search(query: str) -> str:
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        return f"[模擬搜尋] 查詢: {query}\\n請設定 SERPER_API_KEY 啟用真實搜尋"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": 5},
            )
            if r.status_code != 200:
                return f"搜尋失敗，HTTP {r.status_code}: {r.text}"

            data = r.json()
            results = data.get("organic", [])[:3]
            out = []
            for item in results:
                out.append(
                    f"• {item.get('title', 'No title')}\\n"
                    f"  {item.get('snippet', '')}\\n"
                    f"  {item.get('link', '')}"
                )
            return "\\n\\n".join(out) or "無結果"
    except Exception as e:
        return f"搜尋錯誤: {e}"
'''
        },
        "trading_signals": {
            "plugin_json": {
                "id": "trading_signals",
                "name": "trading_signals",
                "description": "加密貨幣交易信號分析",
                "version": "1.0.0",
                "enabled": True,
                "category": "trading",
                "price": 0,
                "author": "system",
                "tools": [{
                    "name": "get_trading_signal",
                    "description": "取得指定幣種的交易信號",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "例如 BTCUSDT"},
                            "timeframe": {"type": "string", "description": "例如 15m, 1h", "default": "1h"}
                        },
                        "required": ["symbol"]
                    }
                }]
            },
            "handler": '''import httpx

async def get_trading_signal(symbol: str, timeframe: str = "1h") -> str:
    try:
        clean_symbol = symbol.upper().replace("/", "")
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={clean_symbol}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                price = float(data["lastPrice"])
                change = float(data["priceChangePercent"])
                volume = float(data["quoteVolume"])
                signal = "🟢 做多" if change > 2 else ("🔴 做空" if change < -2 else "⚪ 觀望")
                return (
                    f"📊 {symbol} 信號分析\\n"
                    f"時間框架: {timeframe}\\n"
                    f"現價: {price:,.4f}\\n"
                    f"24h漲跌: {change:+.2f}%\\n"
                    f"24h成交量: {volume:,.0f} USDT\\n"
                    f"信號: {signal}"
                )
            return f"無法取得 {symbol} 數據，HTTP {r.status_code}"
    except Exception as e:
        return f"無法取得 {symbol} 數據: {e}"
'''
        },
    }

    for plugin_id, data in builtin_plugins.items():
        pdir = PLUGINS_DIR / plugin_id
        pdir.mkdir(parents=True, exist_ok=True)

        plugin_json_path = pdir / "plugin.json"
        handler_path = pdir / "handler.py"

        if not plugin_json_path.exists():
            with open(plugin_json_path, "w", encoding="utf-8") as f:
                json.dump(data["plugin_json"], f, ensure_ascii=False, indent=2)

        if not handler_path.exists():
            with open(handler_path, "w", encoding="utf-8") as f:
                f.write(data["handler"])

    if not REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


# =========================================================
# AGENT
# =========================================================
class AgentSession:
    def __init__(self):
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        self.claude_client = anthropic.AsyncAnthropic(api_key=anthropic_key) if (ENABLE_CLAUDE and anthropic_key) else None
        self.openai_client = AsyncOpenAI(api_key=openai_key) if (ENABLE_OPENAI and openai_key) else None

        self.claude_model = DEFAULT_CLAUDE_MODEL
        self.gpt_model = DEFAULT_GPT_MODEL
        self.system_prompt = DEFAULT_SYSTEM_PROMPT

    async def _run_with_claude(self, user_message: str, history: Optional[list] = None) -> dict:
        if not self.claude_client:
            return {
                "response": "Claude 不可用。",
                "steps": [],
                "messages": [],
                "error": "claude_unavailable",
                "provider": "claude",
            }

        messages = list(history) if history else []
        messages.append({"role": "user", "content": user_message})

        tools = get_active_tools()
        steps = []
        max_iterations = 8

        for _ in range(max_iterations):
            kwargs = {
                "model": self.claude_model,
                "max_tokens": 2048,
                "system": self.system_prompt,
                "messages": messages,
            }

            if tools:
                kwargs["tools"] = tools

            response = await self.claude_client.messages.create(**kwargs)
            messages.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            text_blocks = [b for b in response.content if getattr(b, "type", None) == "text"]

            for tb in text_blocks:
                text = getattr(tb, "text", "")
                if text and text.strip():
                    steps.append({"type": "text", "content": text})

            if response.stop_reason == "end_turn" or not tool_uses:
                break

            tool_results = []
            for tool_use in tool_uses:
                steps.append({
                    "type": "tool_call",
                    "tool": tool_use.name,
                    "input": tool_use.input,
                })
                result = await execute_tool(tool_use.name, tool_use.input)
                steps.append({
                    "type": "tool_result",
                    "tool": tool_use.name,
                    "result": result,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

        final_text = ""
        for step in reversed(steps):
            if step["type"] == "text" and step["content"].strip():
                final_text = step["content"]
                break

        if not final_text:
            final_text = "已完成處理，但沒有文字回應。"

        return {
            "response": final_text,
            "steps": steps,
            "messages": messages,
            "provider": "claude",
        }

    async def _run_with_gpt(self, user_message: str, history: Optional[list] = None, reason: str = "") -> dict:
        if not self.openai_client:
            return {
                "response": "GPT 不可用。",
                "steps": [],
                "messages": history or [],
                "error": "gpt_unavailable",
                "provider": "gpt",
            }

        history_text = flatten_history_to_text(history)
        prompt = (
            f"{self.system_prompt}\n\n"
            f"你目前是 Claude 的備援模型。"
            f"如果 Claude 不可用，請直接繼續幫使用者完成任務。"
        )

        if history_text:
            prompt += f"\n\n先前對話：\n{history_text}"

        prompt += f"\n\n使用者最新訊息：{user_message}"

        resp = await self.openai_client.responses.create(
            model=self.gpt_model,
            input=prompt,
        )

        text = getattr(resp, "output_text", "") or "GPT 已接手，但沒有文字回應。"

        steps = []
        if reason:
            steps.append({
                "type": "fallback",
                "content": "Claude unavailable, switched to GPT"
            })

        return {
            "response": text,
            "steps": steps,
            "messages": history or [],
            "provider": "gpt",
        }

    async def _run_local_fallback(self, user_message: str, history: Optional[list] = None) -> Optional[dict]:
        lowered = user_message.strip()
        if any(ch.isdigit() for ch in lowered) and any(op in lowered for op in ["+", "-", "*", "/", "%"]):
            try:
                result = await execute_tool("calculate", {"expression": lowered})
                return {
                    "response": f"雲端模型暫時不可用，已改用本地 calculator：\n{result}",
                    "steps": [
                        {"type": "fallback", "content": "Cloud model unavailable, switched to local calculator"},
                        {"type": "tool_result", "tool": "calculate", "result": result},
                    ],
                    "messages": history or [],
                    "provider": "local",
                }
            except Exception:
                pass
        return None

    async def run(self, user_message: str, history: Optional[list] = None) -> dict:
        history = list(history) if history else []

        if self.claude_client:
            try:
                return await self._run_with_claude(user_message, history)
            except Exception as e:
                err_text = str(e)
                log.error(f"Claude failed: {err_text}\n{traceback.format_exc()}")

                if self.openai_client and is_fallback_error(err_text):
                    try:
                        return await self._run_with_gpt(user_message, history, reason=err_text)
                    except Exception as gpt_err:
                        log.error(f"GPT fallback failed: {gpt_err}\n{traceback.format_exc()}")

        if self.openai_client:
            try:
                return await self._run_with_gpt(user_message, history, reason="Claude unavailable")
            except Exception as e:
                log.error(f"GPT failed: {e}\n{traceback.format_exc()}")

        local = await self._run_local_fallback(user_message, history)
        if local:
            return local

        return {
            "response": "目前沒有可用的雲端模型，請檢查 API keys。",
            "steps": [],
            "messages": history,
            "error": "no_model_available",
            "provider": "none",
        }


def get_session(session_id: str = "default") -> AgentSession:
    if session_id not in agent_sessions:
        agent_sessions[session_id] = AgentSession()
    return agent_sessions[session_id]


# =========================================================
# COMMAND TERMINAL
# =========================================================
def parse_command(command: str) -> dict:
    raw = command.strip()
    if raw.startswith("/"):
        raw = raw[1:].strip()

    if not raw:
        return {"cmd": "", "args": []}

    parts = raw.split()
    return {"cmd": parts[0].lower(), "args": parts[1:]}


async def execute_platform_command(command: str) -> dict:
    parsed = parse_command(command)
    cmd = parsed["cmd"]
    args = parsed["args"]

    if not cmd:
        return {"success": False, "output": "空指令"}

    if cmd == "help":
        return {
            "success": True,
            "output": (
                "Available commands:\n"
                "/help\n"
                "/skills\n"
                "/providers\n"
                "/store\n"
                "/install <name> <url>\n"
                "/enable <name>\n"
                "/disable <name>\n"
                "/remove <name>\n"
                "/price <symbol>\n"
                "/signal <symbol>\n"
                "/scan <symbol1> [symbol2] ...\n"
                "/balance\n"
                "/positions\n"
                "/orders\n"
                "/buy <symbol> <amount>\n"
                "/sell <symbol> <amount>\n"
                "/killswitch\n"
                "/start_arb_bot\n"
                "/stop_arb_bot\n"
                "/arb_status\n"
                "/clear"
            )
        }

    if cmd == "skills":
        items = []
        for plugin_id, info in plugin_registry.items():
            state = "ON" if info["enabled"] else "OFF"
            items.append(f"{plugin_id} [{state}]")
        return {
            "success": True,
            "output": "\n".join(items) if items else "No plugins loaded"
        }

    if cmd == "providers":
        claude = await check_claude_status()
        openai = await check_openai_status()
        trading = check_trading_status()
        return {
            "success": True,
            "output": json.dumps({
                "claude": claude,
                "openai": openai,
                "trading_api": trading
            }, ensure_ascii=False, indent=2)
        }

    if cmd == "store":
        data = get_store_registry()
        installed = set(plugin_registry.keys())
        items = []
        for p in data:
            pid = p.get("id", "unknown")
            state = "INSTALLED" if pid in installed else "AVAILABLE"
            items.append(f"{pid} | {p.get('name', pid)} | ${p.get('price', 0)} | {state}")
        return {"success": True, "output": "\n".join(items) if items else "Store empty"}

    if cmd == "install":
        if len(args) < 2:
            return {"success": False, "output": "用法：/install <plugin_name> <url>"}
        plugin_name, url = args[0], args[1]
        ok = await install_plugin_from_url(plugin_name, url, remember=True)
        return {
            "success": ok,
            "output": f"Installed: {plugin_name}" if ok else f"Install failed: {plugin_name}"
        }

    if cmd == "enable":
        if len(args) < 1:
            return {"success": False, "output": "用法：/enable <plugin_name>"}
        plugin_id = args[0]
        if plugin_id not in plugin_registry:
            return {"success": False, "output": f"Plugin not found: {plugin_id}"}
        plugin_json = Path(plugin_registry[plugin_id]["path"]) / "plugin.json"
        with open(plugin_json, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["enabled"] = True
        with open(plugin_json, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        load_all_plugins()
        return {"success": True, "output": f"Enabled: {plugin_id}"}

    if cmd == "disable":
        if len(args) < 1:
            return {"success": False, "output": "用法：/disable <plugin_name>"}
        plugin_id = args[0]
        if plugin_id not in plugin_registry:
            return {"success": False, "output": f"Plugin not found: {plugin_id}"}
        plugin_json = Path(plugin_registry[plugin_id]["path"]) / "plugin.json"
        with open(plugin_json, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["enabled"] = False
        with open(plugin_json, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        load_all_plugins()
        return {"success": True, "output": f"Disabled: {plugin_id}"}

    if cmd == "remove":
        if len(args) < 1:
            return {"success": False, "output": "用法：/remove <plugin_name>"}
        plugin_id = args[0]
        pdir = PLUGINS_DIR / plugin_id
        if not pdir.exists():
            return {"success": False, "output": f"Plugin not found: {plugin_id}"}
        shutil.rmtree(pdir)
        forget_installed_plugin(plugin_id)
        load_all_plugins()
        return {"success": True, "output": f"Removed: {plugin_id}"}

    if cmd == "price":
        if len(args) < 1:
            return {"success": False, "output": "用法：/price <symbol>"}
        symbol = args[0].upper()
        result = await execute_tool("get_spot_price", {"symbol": symbol})
        if "not found" in str(result).lower():
            result = await execute_tool("get_trading_signal", {"symbol": symbol, "timeframe": "1h"})
        return {"success": True, "output": str(result)}

    if cmd == "signal":
        if len(args) < 1:
            return {"success": False, "output": "用法：/signal <symbol>"}
        symbol = args[0].upper()
        result = await execute_tool("get_trading_signal", {"symbol": symbol, "timeframe": "1h"})
        return {"success": True, "output": str(result)}

    if cmd == "scan":
        if len(args) < 1:
            return {"success": False, "output": "用法：/scan <symbol1> [symbol2] ..."}
        symbols = [x.upper() for x in args]
        result = await execute_tool("scan_market", {"symbols": symbols})
        return {"success": True, "output": str(result)}

    if cmd == "balance":
        result = await execute_tool("get_balance", {})
        return {"success": True, "output": str(result)}

    if cmd == "positions":
        result = await execute_tool("get_positions", {})
        return {"success": True, "output": str(result)}

    if cmd == "orders":
        result = await execute_tool("get_orders", {})
        return {"success": True, "output": str(result)}

    if cmd == "buy":
        if len(args) < 2:
            return {"success": False, "output": "用法：/buy <symbol> <amount>"}
        symbol = args[0].upper()
        amount = float(args[1])
        result = await execute_tool("buy_token", {"symbol": symbol, "amount": amount})
        return {"success": True, "output": str(result)}

    if cmd == "sell":
        if len(args) < 2:
            return {"success": False, "output": "用法：/sell <symbol> <amount>"}
        symbol = args[0].upper()
        amount = float(args[1])
        result = await execute_tool("sell_token", {"symbol": symbol, "amount": amount})
        return {"success": True, "output": str(result)}

    if cmd == "killswitch":
        result = await execute_tool("kill_switch", {})
        return {"success": True, "output": str(result)}

    if cmd == "start_arb_bot":
        result = await execute_tool("start_arb_bot", {})
        return {"success": True, "output": str(result)}

    if cmd == "stop_arb_bot":
        result = await execute_tool("stop_arb_bot", {})
        return {"success": True, "output": str(result)}

    if cmd == "arb_status":
        result = await execute_tool("arb_status", {})
        return {"success": True, "output": str(result)}

    if cmd == "clear":
        return {"success": True, "output": "__CLEAR__"}

    return {
        "success": False,
        "output": f"Unknown command: {cmd}\nType /help to see available commands."
    }


# =========================================================
# APP LIFESPAN
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_builtin_plugins()
    load_all_plugins()
    await restore_installed_plugins()
    load_all_plugins()

    log.info("AI Plugin Terminal started")
    yield
    log.info("AI Plugin Terminal stopped")


# =========================================================
# APP
# =========================================================
app = FastAPI(title="AI Plugin Terminal", version="2.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# ROUTES
# =========================================================
@app.get("/", response_class=HTMLResponse)
async def frontend():
    if INDEX_HTML.exists():
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            return f.read()

    return f"""
    <h1>index.html not found</h1>
    <p>Expected path: {INDEX_HTML}</p>
    <p>cwd: {os.getcwd()}</p>
    """


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "plugins": len(plugin_registry),
        "claude_enabled": ENABLE_CLAUDE,
        "openai_enabled": ENABLE_OPENAI,
    }


@app.get("/api/plugins")
async def list_plugins():
    return {
        "plugins": [
            {
                "id": pid,
                "name": info["manifest"].get("name", pid),
                "description": info["manifest"].get("description", ""),
                "version": info["manifest"].get("version", "1.0.0"),
                "enabled": info["enabled"],
                "category": info["manifest"].get("category", "utility"),
                "price": info["manifest"].get("price", 0),
                "tools": [t.get("name") for t in info["manifest"].get("tools", [])],
            }
            for pid, info in plugin_registry.items()
        ]
    }


@app.get("/api/store")
async def store():
    data = get_store_registry()
    installed = set(plugin_registry.keys())
    return {
        "plugins": [
            {**p, "installed": p.get("id") in installed}
            for p in data
            if isinstance(p, dict)
        ]
    }


@app.post("/api/plugins/install")
async def install_plugin(req: InstallPluginRequest):
    if req.manifest:
        pdir = PLUGINS_DIR / req.name
        pdir.mkdir(parents=True, exist_ok=True)

        manifest = dict(req.manifest)
        if "id" not in manifest:
            manifest["id"] = req.name
        if "name" not in manifest:
            manifest["name"] = req.name

        with open(pdir / "plugin.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        load_all_plugins()
        return {"success": True, "message": f"Plugin '{req.name}' installed from manifest"}

    if req.url:
        ok = await install_plugin_from_url(req.name, req.url, remember=True)
        if ok:
            return {"success": True, "message": f"Plugin '{req.name}' installed from URL"}
        raise HTTPException(status_code=400, detail="Install failed from URL")

    raise HTTPException(status_code=400, detail="Provide manifest or url")


@app.post("/api/plugins/create")
async def create_plugin(req: PluginManualCreate):
    pdir = PLUGINS_DIR / req.name
    pdir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": req.name,
        "name": req.name,
        "description": req.description,
        "version": "1.0.0",
        "enabled": True,
        "category": req.category or "utility",
        "price": req.price or 0,
        "author": "manual",
        "tools": req.tools,
    }

    with open(pdir / "plugin.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if req.handler_code:
        with open(pdir / "handler.py", "w", encoding="utf-8") as f:
            f.write(req.handler_code)

    load_all_plugins()
    return {"success": True, "plugin": req.name}


@app.patch("/api/plugins/{plugin_id}/toggle")
async def toggle_plugin(plugin_id: str):
    if plugin_id not in plugin_registry:
        raise HTTPException(status_code=404, detail="Plugin not found")

    plugin_json = Path(plugin_registry[plugin_id]["path"]) / "plugin.json"
    with open(plugin_json, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    manifest["enabled"] = not manifest.get("enabled", True)

    with open(plugin_json, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    load_all_plugins()
    return {"success": True, "enabled": manifest["enabled"]}


@app.delete("/api/plugins/{plugin_id}")
async def remove_plugin(plugin_id: str):
    pdir = PLUGINS_DIR / plugin_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="Plugin not found")

    shutil.rmtree(pdir)
    forget_installed_plugin(plugin_id)
    load_all_plugins()

    return {"success": True}


@app.get("/api/status/providers")
async def provider_status():
    claude = await check_claude_status()
    openai = await check_openai_status()
    trading = check_trading_status()
    return {
        "success": True,
        "providers": {
            "claude": claude,
            "openai": openai,
            "trading_api": trading,
        }
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session = get_session(req.session_id)
    result = await session.run(req.message, req.history.copy() if req.history else [])
    return JSONResponse({
        "response": result.get("response", ""),
        "steps": result.get("steps", []),
        "provider": result.get("provider"),
        "error": result.get("error"),
        "session_id": req.session_id,
    })


@app.post("/api/command")
async def command(req: CommandRequest):
    try:
        result = await execute_platform_command(req.command)
        return JSONResponse(result)
    except Exception as e:
        log.error(f"Command error: {e}\n{traceback.format_exc()}")
        return JSONResponse({
            "success": False,
            "output": f"Command error: {str(e)}"
        }, status_code=500)


# =========================================================
# ERROR HANDLER
# =========================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error on {request.url.path}: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc),
            "path": str(request.url.path),
        },
    )


# =========================================================
# ENTRY
# =========================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
