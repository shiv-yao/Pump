import importlib.util
import inspect
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ================= LOG =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ================= PATH =================
SKILLS_DIR = Path("skills")
SKILLS_DIR.mkdir(exist_ok=True)

# ================= GLOBAL =================
skill_registry: dict[str, dict] = {}
sessions: dict[str, "AgentSession"] = {}


# =========================================================
# SKILL LOADER
# =========================================================
def load_skill_manifest(skill_dir: Path) -> Optional[dict]:
    path = skill_dir / "skill.json"
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all_skills():
    global skill_registry
    skill_registry = {}

    for skill_path in SKILLS_DIR.iterdir():
        if not skill_path.is_dir():
            continue

        manifest = load_skill_manifest(skill_path)
        if manifest:
            name = manifest.get("name", skill_path.name)
            skill_registry[name] = {
                "manifest": manifest,
                "path": str(skill_path),
                "enabled": manifest.get("enabled", True),
            }
            log.info(f"Loaded skill: {name}")

    log.info(f"Total skills: {len(skill_registry)}")


def get_active_tools():
    tools = []
    for info in skill_registry.values():
        if not info["enabled"]:
            continue
        tools.extend(info["manifest"].get("tools", []))
    return tools


async def execute_tool(tool_name: str, tool_input: dict):
    for info in skill_registry.values():
        if not info["enabled"]:
            continue

        for tool in info["manifest"].get("tools", []):
            if tool.get("name") != tool_name:
                continue

            handler_file = Path(info["path"]) / "handler.py"
            if not handler_file.exists():
                return f"Tool '{tool_name}' handler.py not found"

            spec = importlib.util.spec_from_file_location(f"skill_{tool_name}", handler_file)
            if spec is None or spec.loader is None:
                return f"Tool '{tool_name}' load failed"

            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, tool_name):
                return f"Tool '{tool_name}' function not found in handler.py"

            fn = getattr(mod, tool_name)
            if inspect.iscoroutinefunction(fn):
                return await fn(**tool_input)
            return fn(**tool_input)

    return f"Tool '{tool_name}' not found"


# =========================================================
# AGENT
# =========================================================
class AgentSession:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else None
        self.model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
        self.system_prompt = os.getenv(
            "AGENT_SYSTEM_PROMPT",
            "你是一個 AI Agent，可以依需求使用 skills。請用繁體中文回應。"
        )

    async def run(self, message: str):
        if not self.client:
            return {
                "ok": False,
                "response": "尚未設定 ANTHROPIC_API_KEY",
                "steps": []
            }

        tools = get_active_tools()
        messages = [{"role": "user", "content": message}]
        steps = []

        max_iterations = 8

        for _ in range(max_iterations):
            kwargs = {
                "model": self.model,
                "max_tokens": 2000,
                "system": self.system_prompt,
                "messages": messages,
            }

            if tools:
                kwargs["tools"] = tools

            response = await self.client.messages.create(**kwargs)

            assistant_blocks = response.content
            messages.append({"role": "assistant", "content": assistant_blocks})

            tool_uses = [b for b in assistant_blocks if b.type == "tool_use"]
            text_blocks = [b for b in assistant_blocks if b.type == "text"]

            for tb in text_blocks:
                if tb.text.strip():
                    steps.append({"type": "text", "content": tb.text})

            if not tool_uses:
                final_text = "\n".join(
                    s["content"] for s in steps if s["type"] == "text"
                ).strip()
                return {
                    "ok": True,
                    "response": final_text or "已完成，但沒有文字輸出",
                    "steps": steps,
                }

            tool_results = []

            for tool_use in tool_uses:
                steps.append({
                    "type": "tool_call",
                    "tool": tool_use.name,
                    "input": tool_use.input,
                })

                try:
                    result = await execute_tool(tool_use.name, tool_use.input)
                except Exception as e:
                    result = f"Tool error: {e}"

                steps.append({
                    "type": "tool_result",
                    "tool": tool_use.name,
                    "result": str(result),
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": str(result),
                })

            messages.append({"role": "user", "content": tool_results})

        return {
            "ok": False,
            "response": "工具迭代次數超過上限",
            "steps": steps,
        }


def get_session(sid: str = "default"):
    if sid not in sessions:
        sessions[sid] = AgentSession()
    return sessions[sid]


# =========================================================
# API MODELS
# =========================================================
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


# =========================================================
# APP LIFESPAN
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all_skills()
    log.info("AI Agent Started")
    yield
    log.info("AI Agent Stopped")


# =========================================================
# APP
# =========================================================
app = FastAPI(title="AI Agent Skill Store", version="1.0.0", lifespan=lifespan)

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
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session = get_session(req.session_id)
    result = await session.run(req.message)
    return JSONResponse(result)


@app.get("/api/skills")
async def skills():
    return {
        "skills": [
            {
                "name": name,
                "enabled": info["enabled"],
                "tools": [t.get("name") for t in info["manifest"].get("tools", [])],
                "description": info["manifest"].get("description", ""),
            }
            for name, info in skill_registry.items()
        ]
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!doctype html>
    <html lang="zh-Hant">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width,initial-scale=1" />
      <title>AI Agent Skill Store</title>
      <style>
        body {
          font-family: -apple-system, BlinkMacSystemFont, sans-serif;
          background: #0b1020;
          color: white;
          margin: 0;
          padding: 24px;
        }
        .card {
          max-width: 760px;
          margin: 40px auto;
          background: #151b2f;
          border-radius: 16px;
          padding: 24px;
          box-shadow: 0 10px 30px rgba(0,0,0,.25);
        }
        h1 { margin-top: 0; }
        .muted { color: #aab3c5; }
        .btn {
          display: inline-block;
          margin-top: 12px;
          padding: 12px 16px;
          border-radius: 10px;
          background: #6d5efc;
          color: white;
          text-decoration: none;
          font-weight: 600;
        }
        code {
          background: #0f1424;
          padding: 2px 6px;
          border-radius: 6px;
        }
      </style>
    </head>
    <body>
      <div class="card">
        <h1>AI Agent Running 🚀</h1>
        <p class="muted">Railway 部署成功，後端正在運行。</p>
        <p>健康檢查：<code>/health</code></p>
        <p>技能列表：<code>/api/skills</code></p>
        <p>聊天 API：<code>POST /api/chat</code></p>
        <a class="btn" href="/api/skills">查看 Skills</a>
      </div>
    </body>
    </html>
    """


# =========================================================
# ENTRY
# =========================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
