import asyncio
import importlib.util
import inspect
import json
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import anthropic
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ================= LOG =================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ================= APP =================
app = FastAPI(title="AI Agent Skill Store", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= PATH =================
SKILLS_DIR = Path("skills")
SKILLS_DIR.mkdir(exist_ok=True)

# ================= GLOBAL =================
skill_registry: dict[str, dict] = {}

# =========================================================
# SKILL LOADER
# =========================================================

def load_skill_manifest(skill_dir: Path) -> Optional[dict]:
    path = skill_dir / "skill.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)

def load_all_skills():
    global skill_registry
    skill_registry = {}

    for skill_path in SKILLS_DIR.iterdir():
        if skill_path.is_dir():
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
            if tool["name"] == tool_name:
                handler_file = Path(info["path"]) / "handler.py"

                if handler_file.exists():
                    spec = importlib.util.spec_from_file_location("mod", handler_file)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)

                    if hasattr(mod, tool_name):
                        fn = getattr(mod, tool_name)

                        if inspect.iscoroutinefunction(fn):
                            return await fn(**tool_input)
                        else:
                            return fn(**tool_input)

    return "Tool not found"

# =========================================================
# AGENT
# =========================================================

class AgentSession:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = os.getenv("CLAUDE_MODEL", "claude-opus-4-5")

    async def run(self, message: str):
        tools = get_active_tools()

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": message}],
            tools=tools if tools else None,
        )

        return str(response.content)

sessions = {}

def get_session(sid="default"):
    if sid not in sessions:
        sessions[sid] = AgentSession()
    return sessions[sid]

# =========================================================
# API
# =========================================================

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

@app.post("/api/chat")
async def chat(req: ChatRequest):
    session = get_session(req.session_id)
    res = await session.run(req.message)
    return {"response": res}

@app.get("/api/skills")
async def skills():
    return skill_registry

# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
async def startup():
    load_all_skills()
    log.info("AI Agent Started")

# =========================================================
# FRONTEND
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
    <body>
    <h1>AI Agent Running 🚀</h1>
    </body>
    </html>
    """

# =========================================================
# ENTRY
# =========================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
