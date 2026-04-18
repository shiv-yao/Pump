"""
main.py - AI Agent with Plugin Skill Store
Railway 可部署，支援動態安裝 / 管理 skills
Claude 餘額不足時自動 fallback 到 GPT
"""

import importlib.util
import inspect
import json
import logging
import os
import shutil
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
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
BASE_DIR = Path(__file__).resolve().parent
SKILLS_DIR = BASE_DIR / "skills"
INDEX_HTML = BASE_DIR / "index.html"

SKILLS_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# GLOBALS
# =========================================================
skill_registry: dict[str, dict] = {}
agent_sessions: dict[str, "AgentSession"] = {}

SKILL_REGISTRY_URL = os.getenv(
    "SKILL_REGISTRY_URL",
    "https://raw.githubusercontent.com/your-org/skill-store/main/registry.json"
)

DEFAULT_CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
DEFAULT_GPT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "AGENT_SYSTEM_PROMPT",
    "你是一個強大的 AI Agent，擁有多種 skills 可以使用。"
    "根據用戶需求選擇合適的工具完成任務。使用繁體中文回應。"
)

ENABLE_OPENAI_FALLBACK = os.getenv("ENABLE_OPENAI", "true").lower() == "true"

# =========================================================
# SKILL LOADER
# =========================================================
def load_skill_manifest(skill_dir: Path) -> Optional[dict]:
    manifest_path = skill_dir / "skill.json"
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed loading manifest {manifest_path}: {e}")
        return None


def load_all_skills():
    global skill_registry
    skill_registry = {}

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    for skill_path in SKILLS_DIR.iterdir():
        if not skill_path.is_dir():
            continue

        manifest = load_skill_manifest(skill_path)
        if not manifest:
            continue

        skill_name = manifest.get("name", skill_path.name)
        skill_registry[skill_name] = {
            "manifest": manifest,
            "path": str(skill_path),
            "enabled": manifest.get("enabled", True),
            "installed_at": manifest.get("installed_at", "unknown"),
        }
        log.info(f"Loaded skill: {skill_name}")

    log.info(f"Total skills loaded: {len(skill_registry)}")


def get_active_tools() -> list[dict]:
    tools: list[dict] = []

    for _, info in skill_registry.items():
        if not info["enabled"]:
            continue

        manifest = info["manifest"]
        for tool_def in manifest.get("tools", []):
            if isinstance(tool_def, dict) and tool_def.get("name"):
                tools.append(tool_def)

    return tools


async def execute_tool(tool_name: str, tool_input: dict) -> str:
    for skill_name, info in skill_registry.items():
        if not info["enabled"]:
            continue

        for tool_def in info["manifest"].get("tools", []):
            if tool_def.get("name") != tool_name:
                continue

            skill_path = Path(info["path"])
            handler_file = skill_path / "handler.py"

            if not handler_file.exists():
                return f"Tool '{tool_name}' handler.py not found."

            try:
                spec = importlib.util.spec_from_file_location(
                    f"skill_{skill_name}",
                    handler_file
                )
                if spec is None or spec.loader is None:
                    return f"Tool '{tool_name}' load failed."

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

    return f"Tool '{tool_name}' not found or not executable."


# =========================================================
# MODEL HELPERS
# =========================================================
def flatten_history_to_text(history: Optional[list]) -> str:
    if not history:
        return ""

    lines = []
    for item in history:
        role = item.get("role", "unknown")
        content = item.get("content", "")
        if isinstance(content, list):
            content = json.dumps(content, ensure_ascii=False)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def is_low_balance_error(message: str) -> bool:
    msg = message.lower()
    markers = [
        "credit balance is too low",
        "purchase credits",
        "plans & billing",
        "billing",
        "insufficient credits",
    ]
    return any(m in msg for m in markers)


def is_claude_retryable_or_fallback_error(message: str) -> bool:
    msg = message.lower()
    markers = [
        "credit balance is too low",
        "purchase credits",
        "plans & billing",
        "invalid api key",
        "authentication",
        "unauthorized",
        "forbidden",
        "model not found",
        "not allowed",
        "overloaded",
        "rate limit",
        "temporarily unavailable",
    ]
    return any(m in msg for m in markers)


# =========================================================
# AGENT CORE
# =========================================================
class AgentSession:
    def __init__(self):
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        self.claude_client = anthropic.AsyncAnthropic(api_key=anthropic_key) if anthropic_key else None
        self.openai_client = AsyncOpenAI(api_key=openai_key) if openai_key else None

        self.claude_model = DEFAULT_CLAUDE_MODEL
        self.gpt_model = DEFAULT_GPT_MODEL
        self.system_prompt = DEFAULT_SYSTEM_PROMPT

    async def _run_with_claude(self, user_message: str, history: Optional[list] = None) -> dict:
        if not self.claude_client:
            return {
                "response": "尚未設定 ANTHROPIC_API_KEY。",
                "steps": [],
                "messages": [],
                "error": "missing_anthropic_api_key",
                "provider": "claude",
            }

        messages = list(history) if history else []
        messages.append({"role": "user", "content": user_message})

        tools = get_active_tools()
        steps: list[dict] = []
        max_iterations = 10

        for _ in range(max_iterations):
            kwargs = {
                "model": self.claude_model,
                "max_tokens": 4096,
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
                log.info(f"Claude executing tool: {tool_use.name} with {tool_use.input}")

                try:
                    result = await execute_tool(tool_use.name, tool_use.input)
                except Exception:
                    result = f"Error:\n{traceback.format_exc()}"

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
                "response": "Claude 無法使用，且尚未設定 OPENAI_API_KEY，無法 fallback 到 GPT。",
                "steps": [],
                "messages": history or [],
                "error": "missing_openai_api_key",
                "provider": "gpt",
            }

        # 這裡採用文字 fallback，不強行複刻 Claude tool loop。
        # 若要做 GPT tool calling，可再另外擴充。
        history_text = flatten_history_to_text(history)
        prompt = (
            f"{self.system_prompt}\n\n"
            f"你目前是 Claude 的備援模型。"
            f"若前面提到 Claude 失敗原因，請不要重複報錯，直接繼續幫使用者完成任務。\n"
        )

        if history_text:
            prompt += f"\n以下是先前對話紀錄：\n{history_text}\n"

        if reason:
            prompt += f"\nClaude 失敗原因：{reason}\n"

        prompt += f"\n使用者最新訊息：{user_message}\n"

        resp = await self.openai_client.responses.create(
            model=self.gpt_model,
            input=prompt,
        )

        text = getattr(resp, "output_text", "") or "GPT 已接手，但沒有文字回應。"

        steps = []
        if reason:
            steps.append({
                "type": "fallback",
                "content": f"Claude unavailable, fallback to GPT: {reason}"
            })

        return {
            "response": text,
            "steps": steps,
            "messages": history or [],
            "provider": "gpt",
        }

    async def _run_local_fallback(self, user_message: str, history: Optional[list] = None, reason: str = "") -> Optional[dict]:
        # 最後一道 fallback：如果像數學算式，就直接用 calculator
        lowered = user_message.strip()
        if any(ch.isdigit() for ch in lowered) and any(op in lowered for op in ["+", "-", "*", "/", "%"]):
            try:
                result = await execute_tool("calculate", {"expression": lowered})
                return {
                    "response": f"雲端模型暫時不可用，已改用本地 calculator：\n{result}",
                    "steps": [
                        {
                            "type": "fallback",
                            "content": f"Local fallback because model unavailable: {reason}"
                        },
                        {
                            "type": "tool_result",
                            "tool": "calculate",
                            "result": result,
                        }
                    ],
                    "messages": history or [],
                    "provider": "local",
                }
            except Exception:
                pass
        return None

    async def run(self, user_message: str, history: Optional[list] = None) -> dict:
        history = list(history) if history else []

        # 先試 Claude
        try:
            result = await self._run_with_claude(user_message, history)
            if not result.get("error"):
                return result

            # 缺 key 也允許 fallback GPT
            reason = result.get("response", result.get("error", "Claude unavailable"))
            if ENABLE_OPENAI_FALLBACK:
                try:
                    return await self._run_with_gpt(user_message, history, reason=reason)
                except Exception as gpt_err:
                    local = await self._run_local_fallback(user_message, history, reason=str(gpt_err))
                    if local:
                        return local
                    return {
                        "response": f"Claude 無法使用，GPT fallback 也失敗：{str(gpt_err)}",
                        "steps": [],
                        "messages": history,
                        "error": "all_models_failed",
                        "provider": "none",
                    }
            return result

        except Exception as e:
            err_text = str(e)
            log.error(f"Claude request failed: {err_text}\n{traceback.format_exc()}")

            # Claude 餘額不足 / 權限問題 / 模型問題 → fallback GPT
            if ENABLE_OPENAI_FALLBACK and is_claude_retryable_or_fallback_error(err_text):
                try:
                    return await self._run_with_gpt(user_message, history, reason=err_text)
                except Exception as gpt_err:
                    log.error(f"GPT fallback failed: {gpt_err}\n{traceback.format_exc()}")
                    local = await self._run_local_fallback(user_message, history, reason=str(gpt_err))
                    if local:
                        return local

                    if is_low_balance_error(err_text):
                        return {
                            "response": (
                                "Claude API 無法使用：Anthropic 帳戶餘額不足。"
                                f"已嘗試 fallback 到 GPT，但 GPT 也失敗：{str(gpt_err)}"
                            ),
                            "steps": [],
                            "messages": history,
                            "error": "anthropic_low_balance_and_gpt_failed",
                            "provider": "none",
                        }

                    return {
                        "response": f"Claude 失敗，且 GPT fallback 也失敗：{str(gpt_err)}",
                        "steps": [],
                        "messages": history,
                        "error": "all_models_failed",
                        "provider": "none",
                    }

            # 非預期錯誤：也嘗試本地 fallback
            local = await self._run_local_fallback(user_message, history, reason=err_text)
            if local:
                return local

            return {
                "response": f"Claude API error: {err_text}",
                "steps": [{"type": "error", "content": traceback.format_exc()}],
                "messages": history,
                "error": "anthropic_request_failed",
                "provider": "claude",
            }


def get_session(session_id: str = "default") -> AgentSession:
    if session_id not in agent_sessions:
        agent_sessions[session_id] = AgentSession()
    return agent_sessions[session_id]


# =========================================================
# REMOTE REGISTRY
# =========================================================
async def fetch_remote_registry() -> list[dict]:
    if not SKILL_REGISTRY_URL or "your-org" in SKILL_REGISTRY_URL:
        log.warning("SKILL_REGISTRY_URL is placeholder; skip remote registry fetch.")
        return []

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(SKILL_REGISTRY_URL)
            if resp.status_code != 200:
                log.warning(f"Remote registry HTTP {resp.status_code}")
                return []

            data = resp.json()
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        log.warning(f"Cannot fetch remote registry: {e}")
        return []


async def install_skill_from_url(skill_name: str, url: str) -> bool:
    skill_dir = SKILLS_DIR / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            manifest_url = f"{url.rstrip('/')}/skill.json"
            handler_url = f"{url.rstrip('/')}/handler.py"

            manifest_resp = await client.get(manifest_url)
            if manifest_resp.status_code != 200:
                log.error(f"Failed downloading skill.json: {manifest_resp.status_code}")
                return False

            manifest = manifest_resp.json()
            manifest["installed_at"] = datetime.now().isoformat()
            manifest["enabled"] = True

            with open(skill_dir / "skill.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

            handler_resp = await client.get(handler_url)
            if handler_resp.status_code == 200:
                with open(skill_dir / "handler.py", "w", encoding="utf-8") as f:
                    f.write(handler_resp.text)

        load_all_skills()
        return True

    except Exception as e:
        log.error(f"Install skill error: {e}")
        return False


# =========================================================
# REQUEST MODELS
# =========================================================
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list = Field(default_factory=list)


class InstallSkillRequest(BaseModel):
    name: str
    url: Optional[str] = None
    manifest: Optional[dict] = None


class SkillManualCreate(BaseModel):
    name: str
    description: str
    tools: list[dict]
    handler_code: Optional[str] = None


# =========================================================
# BUILTIN SKILLS
# =========================================================
async def ensure_builtin_skills():
    builtin = {
        "web_search": {
            "name": "web_search",
            "description": "搜尋網路上的最新資訊",
            "version": "1.0.0",
            "enabled": True,
            "installed_at": datetime.now().isoformat(),
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
        "calculator": {
            "name": "calculator",
            "description": "數學計算工具",
            "version": "1.0.0",
            "enabled": True,
            "installed_at": datetime.now().isoformat(),
            "tools": [{
                "name": "calculate",
                "description": "執行數學運算",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "數學表達式，如 2+2*3"
                        }
                    },
                    "required": ["expression"]
                }
            }]
        },
        "trading_signals": {
            "name": "trading_signals",
            "description": "加密貨幣交易信號分析",
            "version": "1.0.0",
            "enabled": True,
            "installed_at": datetime.now().isoformat(),
            "tools": [{
                "name": "get_trading_signal",
                "description": "取得指定幣種的交易信號",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "幣種，如 BTCUSDT"
                        },
                        "timeframe": {
                            "type": "string",
                            "description": "時間框架，如 15m, 1h",
                            "default": "1h"
                        }
                    },
                    "required": ["symbol"]
                }
            }]
        }
    }

    for skill_name, manifest in builtin.items():
        skill_dir = SKILLS_DIR / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = skill_dir / "skill.json"
        if not manifest_path.exists():
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

    _write_builtin_handlers()
    load_all_skills()


def _write_builtin_handlers():
    calc_handler = '''import ast
import operator

def calculate(expression: str) -> str:
    """安全的數學計算"""
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
    (SKILLS_DIR / "calculator").mkdir(parents=True, exist_ok=True)
    with open(SKILLS_DIR / "calculator" / "handler.py", "w", encoding="utf-8") as f:
        f.write(calc_handler)

    trading_handler = '''import httpx

async def get_trading_signal(symbol: str, timeframe: str = "1h") -> str:
    """從 Binance 取得簡易交易信號"""
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
    (SKILLS_DIR / "trading_signals").mkdir(parents=True, exist_ok=True)
    with open(SKILLS_DIR / "trading_signals" / "handler.py", "w", encoding="utf-8") as f:
        f.write(trading_handler)

    search_handler = '''import os
import httpx

async def web_search(query: str) -> str:
    """網路搜尋（需設定 SERPER_API_KEY）"""
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
    (SKILLS_DIR / "web_search").mkdir(parents=True, exist_ok=True)
    with open(SKILLS_DIR / "web_search" / "handler.py", "w", encoding="utf-8") as f:
        f.write(search_handler)


# =========================================================
# APP LIFESPAN
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all_skills()
    await ensure_builtin_skills()
    log.info("AI Agent started")
    yield
    log.info("AI Agent stopped")


# =========================================================
# APP
# =========================================================
app = FastAPI(
    title="AI Agent Skill Store",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# ROUTES
# =========================================================
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "skills": len(skill_registry),
        "time": datetime.now().isoformat(),
        "openai_fallback_enabled": ENABLE_OPENAI_FALLBACK,
    }


@app.get("/api/skills")
async def list_skills():
    return {
        "skills": [
            {
                "name": name,
                "description": info["manifest"].get("description", ""),
                "version": info["manifest"].get("version", "1.0.0"),
                "enabled": info["enabled"],
                "tools": [t.get("name") for t in info["manifest"].get("tools", [])],
                "installed_at": info["installed_at"],
            }
            for name, info in skill_registry.items()
        ]
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session = get_session(req.session_id)
    result = await session.run(req.message, req.history.copy() if req.history else [])
    return JSONResponse({
        "response": result.get("response", ""),
        "steps": result.get("steps", []),
        "session_id": req.session_id,
        "error": result.get("error"),
        "provider": result.get("provider"),
    })


@app.post("/api/skills/install")
async def install_skill(req: InstallSkillRequest):
    if req.manifest:
        skill_dir = SKILLS_DIR / req.name
        skill_dir.mkdir(parents=True, exist_ok=True)

        manifest = dict(req.manifest)
        manifest["installed_at"] = datetime.now().isoformat()
        manifest["enabled"] = True

        with open(skill_dir / "skill.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        load_all_skills()
        return {"success": True, "message": f"Skill '{req.name}' installed"}

    if req.url:
        success = await install_skill_from_url(req.name, req.url)
        if success:
            return {
                "success": True,
                "message": f"Skill '{req.name}' installed from {req.url}"
            }
        raise HTTPException(status_code=400, detail="Failed to install skill from URL")

    raise HTTPException(status_code=400, detail="Provide either manifest or url")


@app.post("/api/skills/create")
async def create_skill(req: SkillManualCreate):
    skill_dir = SKILLS_DIR / req.name
    skill_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": req.name,
        "description": req.description,
        "version": "1.0.0",
        "enabled": True,
        "installed_at": datetime.now().isoformat(),
        "tools": req.tools,
    }

    with open(skill_dir / "skill.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    if req.handler_code:
        with open(skill_dir / "handler.py", "w", encoding="utf-8") as f:
            f.write(req.handler_code)

    load_all_skills()
    return {"success": True, "skill": req.name}


@app.patch("/api/skills/{skill_name}/toggle")
async def toggle_skill(skill_name: str):
    if skill_name not in skill_registry:
        raise HTTPException(status_code=404, detail="Skill not found")

    skill_dir = SKILLS_DIR / skill_name
    manifest_path = skill_dir / "skill.json"

    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="skill.json not found")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    manifest["enabled"] = not manifest.get("enabled", True)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    load_all_skills()
    return {"success": True, "enabled": manifest["enabled"]}


@app.delete("/api/skills/{skill_name}")
async def uninstall_skill(skill_name: str):
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    shutil.rmtree(skill_dir)
    load_all_skills()
    return {"success": True}


@app.get("/api/skills/store/browse")
async def browse_store():
    remote = await fetch_remote_registry()
    installed = set(skill_registry.keys())
    return {
        "available": [
            {**s, "installed": s.get("name") in installed}
            for s in remote
            if isinstance(s, dict) and s.get("name")
        ]
    }


@app.get("/", response_class=HTMLResponse)
async def frontend():
    try:
        if INDEX_HTML.exists():
            with open(INDEX_HTML, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        log.error(f"Failed to read index.html: {e}")

    return """
    <!doctype html>
    <html lang="zh-Hant">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>AI Agent Skill Store</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#081018; color:#fff; padding:24px; }
        .card { max-width:760px; margin:40px auto; background:#111b25; border-radius:16px; padding:24px; }
        a { color:#78f0dc; }
      </style>
    </head>
    <body>
      <div class="card">
        <h1>AI Agent Skill Store 🚀</h1>
        <p>index.html 未找到，已使用備援首頁。</p>
        <p><a href="/health">/health</a></p>
        <p><a href="/api/skills">/api/skills</a></p>
      </div>
    </body>
    </html>
    """


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

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
