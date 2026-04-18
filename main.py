"""
main.py - AI Agent with Plugin Skill Store
Railway 可部署，⽀援動態安裝/管理 skills
"""
import asyncio
import importlib.util
import inspect
import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import anthropic
import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
app = FastAPI(title="AI Agent Skill Store", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["
# ─── Paths ───
SKILLS_DIR = Path("skills")
SKILLS_DIR.mkdir(exist_ok=True)
# ─── Global skill registry ───
skill_registry: dict[str, dict] = {}
loaded_tools: dict[str, Any] = {}
# ══════════════════════════════════════════
# SKILL LOADER
# ══════════════════════════════════════════
def load_skill_manifest(skill_dir: Path) -> Optional[dict]:
manifest_path = skill_dir / "skill.json"
if not manifest_path.exists():
return None
with open(manifest_path) as f:
return json.load(f)
def load_all_skills():
"""掃描並載入所有已安裝的 skills"""
global skill_registry
skill_registry = {}
for skill_path in SKILLS_DIR.iterdir():
if skill_path.is_dir():
manifest = load_skill_manifest(skill_path)
if manifest:
skill_name = manifest.get("name", skill_path.name)
skill_registry[skill_name] = {
"manifest": manifest,
"path": str(skill_path),
"enabled": manifest.get("enabled", True),
"installed_at": manifest.get("installed_at", "unknown"),
}
log.info(f" Loaded skill: {skill_name}")
log.info(f" Total skills loaded: {len(skill_registry)}")
def get_active_tools() -> list[dict]:
"""回傳所有啟⽤ skill 的 Anthropic tool 定義"""
tools = []
for name, info in skill_registry.items():
if not info["enabled"]:
continue
manifest = info["manifest"]
for tool_def in manifest.get("tools", []):
tools.append(tool_def)
return tools
async def execute_tool(tool_name: str, tool_input: dict) -> str:
"""執⾏指定 skill 的 tool"""
for skill_name, info in skill_registry.items():
if not info["enabled"]:
continue
for tool_def in info["manifest"].get("tools", []):
if tool_def["name"] == tool_name:
skill_path = Path(info["path"])
handler_file = skill_path / "handler.py"
if handler_file.exists():
spec = importlib.util.spec_from_file_location(
f"skill_{skill_name}", handler_file
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
if hasattr(mod, tool_name):
fn = getattr(mod, tool_name)
if inspect.iscoroutinefunction(fn):
result = await fn(**tool_input)
else:
result = fn(**tool_input)
return str(result)
return f"Tool '{tool_name}' not found or not executable."
# ══════════════════════════════════════════
# AI AGENT CORE
# ══════════════════════════════════════════
class AgentSession:
def __init__(self):
self.client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
self.model = os.getenv("CLAUDE_MODEL", "claude-opus-4-5")
self.system_prompt = os.getenv("AGENT_SYSTEM_PROMPT",
"你是⼀個強⼤的 AI Agent，擁有多種 skills 可以使⽤。"
"根據⽤⼾需求選擇合適的⼯具完成任務。使⽤繁體中⽂回應。"
)
async def run(self, user_message: str, history: list = None) -> dict:
messages = history or []
messages.append({"role": "user", "content": user_message})
tools = get_active_tools()
steps = []
max_iterations = 10
for i in range(max_iterations):
kwargs = {
"model": self.model,
"max_tokens": 4096,
"system": self.system_prompt,
"messages": messages,
}
if tools:
kwargs["tools"] = tools
response = await self.client.messages.create(**kwargs)
messages.append({"role": "assistant", "content": response.content})
# 檢查是否有⼯具呼叫
tool_uses = [b for b in response.content if b.type == "tool_use"]
text_blocks = [b for b in response.content if b.type == "text"]
if text_blocks:
for tb in text_blocks:
steps.append({"type": "text", "content": tb.text})
if response.stop_reason == "end_turn" or not tool_uses:
break
# 執⾏所有⼯具
tool_results = []
for tool_use in tool_uses:
steps.append({
"type": "tool_call",
"tool": tool_use.name,
"input": tool_use.input
})
log.info(f" try:
Executing tool: {tool_use.name} with {tool_use.input}")
result = await execute_tool(tool_use.name, tool_use.input)
except Exception as e:
result = f"Error: {traceback.format_exc()}"
steps.append({"type": "tool_result", "tool": tool_use.name, "result": result}
tool_results.append({
"type": "tool_result",
"tool_use_id": tool_use.id,
"content": result
})
messages.append({"role": "user", "content": tool_results})
# 最終回應
final_text = ""
for step in reversed(steps):
if step["type"] == "text" and step["content"].strip():
final_text = step["content"]
break
return {
"response": final_text,
"steps": steps,
"messages": messages,
}
agent_sessions: dict[str, AgentSession] = {}
def get_session(session_id: str = "default") -> AgentSession:
if session_id not in agent_sessions:
agent_sessions[session_id] = AgentSession()
return agent_sessions[session_id]
# ══════════════════════════════════════════
# SKILL STORE API
# ══════════════════════════════════════════
SKILL_REGISTRY_URL = os.getenv(
"SKILL_REGISTRY_URL",
"https://raw.githubusercontent.com/your-org/skill-store/main/registry.json"
)
async def fetch_remote_registry() -> list[dict]:
"""從遠端抓取可⽤ skill 清單"""
try:
async with httpx.AsyncClient(timeout=10) as client:
resp = await client.get(SKILL_REGISTRY_URL)
if resp.status_code == 200:
return resp.json()
except Exception as e:
log.warning(f"Cannot fetch remote registry: {e}")
return []
async def install_skill_from_url(skill_name: str, url: str) -> bool:
"""從 URL 安裝 skill（下載 skill.json + handler.py）"""
skill_dir = SKILLS_DIR / skill_name
skill_dir.mkdir(exist_ok=True)
try:
async with httpx.AsyncClient(timeout=30) as client:
# 下載 skill.json
r = await client.get(f"{url}/skill.json")
if r.status_code != 200:
return False
manifest = r.json()
manifest["installed_at"] = datetime.now().isoformat()
manifest["enabled"] = True
with open(skill_dir / "skill.json", "w") as f:
json.dump(manifest, f, indent=2)
# 下載 handler.py (選擇性)
r2 = await client.get(f"{url}/handler.py")
if r2.status_code == 200:
with open(skill_dir / "handler.py", "w") as f:
f.write(r2.text)
load_all_skills()
return True
except Exception as e:
log.error(f"Install skill error: {e}")
return False
# ══════════════════════════════════════════
# REQUEST MODELS
# ══════════════════════════════════════════
class ChatRequest(BaseModel):
message: str
session_id: str = "default"
history: list = []
class InstallSkillRequest(BaseModel):
name: str
url: Optional[str] = None
manifest: Optional[dict] = None # 直接傳入 manifest（不從 URL 下載）
class SkillManualCreate(BaseModel):
name: str
description: str
tools: list[dict]
handler_code: Optional[str] = None
# ══════════════════════════════════════════
# API ROUTES
# ══════════════════════════════════════════
@app.on_event("startup")
async def startup():
load_all_skills()
# 預裝內建 skills
await ensure_builtin_skills()
log.info(" AI Agent started")
async def ensure_builtin_skills():
"""確保內建 skills 已安裝"""
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
"description": "數學計算⼯具",
"version": "1.0.0",
"enabled": True,
"installed_at": datetime.now().isoformat(),
"tools": [{
"name": "calculate",
"description": "執⾏數學運算",
"input_schema": {
"type": "object",
"properties": {
"expression": {"type": "string", "description": "數學表達式，如 2+2*3"}
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
"symbol": {"type": "string", "description": "幣種，如 BTCUSDT"},
"timeframe": {"type": "string", "description": "時間框架，如 15m, 1h",
},
"required": ["symbol"]
}
}]
}
}
for skill_name, manifest in builtin.items():
skill_dir = SKILLS_DIR / skill_name
if not skill_dir.exists():
skill_dir.mkdir(exist_ok=True)
with open(skill_dir / "skill.json", "w") as f:
json.dump(manifest, f, indent=2)
# 寫入 handler
_write_builtin_handlers()
load_all_skills()
def _write_builtin_handlers():
# calculator handler
calc_handler = '''
import ast
import operator
def calculate(expression: str) -> str:
"""安全的數學計算"""
ops = {
ast.Add: operator.add, ast.Sub: operator.sub,
ast.Mult: operator.mul, ast.Div: operator.truediv,
ast.Pow: operator.pow, ast.USub: operator.neg,
}
def eval_node(node):
if isinstance(node, ast.Num):
return node.n
elif isinstance(node, ast.BinOp):
return ops[type(node.op)](eval_node(node.left), eval_node(node.right))
elif isinstance(node, ast.UnaryOp):
return ops[type(node.op)](eval_node(node.operand))
raise ValueError(f"Unsupported: {node}")
try:
tree = ast.parse(expression, mode="eval")
result = eval_node(tree.body)
return f"{expression} = {result}"
except Exception as e:
return f"計算錯誤: {e}"
'''
with open(SKILLS_DIR / "calculator" / "handler.py", "w") as f:
f.write(calc_handler)
# trading_signals handler
trading_handler = '''
import httpx
import asyncio
async def get_trading_signal(symbol: str, timeframe: str = "1h") -> str:
"""從 DexScreener/Binance 取得簡易交易信號"""
try:
url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol.upper().replace('/'
async with httpx.AsyncClient(timeout=10) as client:
r = await client.get(url)
if r.status_code == 200:
data = r.json()
price = float(data["lastPrice"])
change = float(data["priceChangePercent"])
volume = float(data["quoteVolume"])
signal = " 做多" if change > 2 else (" 做空" if change < -2 else " return (
f" {symbol} 信號分析\\n"
f"現價: {price:,.4f}\\n"
f"24h漲跌: {change:+.2f}%\\n"
f"24h成交量: {volume:,.0f} USDT\\n"
f"信號: {signal}"
觀望"
)
except Exception as e:
return f"無法取得 {symbol} 數據: {e}"
return "無數據"
'''
with open(SKILLS_DIR / "trading_signals" / "handler.py", "w") as f:
f.write(trading_handler)
# web_search handler (mock - replace with real API)
search_handler = '''
import httpx
import os
async def web_search(query: str) -> str:
"""網路搜尋（需設定 SERPER_API_KEY）"""
api_key = os.getenv("SERPER_API_KEY", "")
if not api_key:
return f"[模擬搜尋] 查詢: {query}\\n請設定 SERPER_API_KEY 啟⽤真實搜尋"
try:
async with httpx.AsyncClient(timeout=10) as client:
r = await client.post(
"https://google.serper.dev/search",
headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
json={"q": query, "num": 5}
)
data = r.json()
results = data.get("organic", [])[:3]
out = []
for item in results:
out.append(f"• {item.get('title')}\\n {item.get('snippet')}\\n {item.get('l
return "\\n\\n".join(out) or "無結果"
except Exception as e:
return f"搜尋錯誤: {e}"
'''
with open(SKILLS_DIR / "web_search" / "handler.py", "w") as f:
f.write(search_handler)
# ─── Chat ───
@app.post("/api/chat")
async def chat(req: ChatRequest):
session = get_session(req.session_id)
result = await session.run(req.message, req.history.copy() if req.history else [])
return {
"response": result["response"],
"steps": result["steps"],
"session_id": req.session_id,
}
# ─── Skills ───
@app.get("/api/skills")
async def list_skills():
return {
"skills": [
{
"name": name,
"description": info["manifest"].get("description", ""),
"version": info["manifest"].get("version", "1.0.0"),
"enabled": info["enabled"],
"tools": [t["name"] for t in info["manifest"].get("tools", [])],
"installed_at": info["installed_at"],
}
for name, info in skill_registry.items()
]
}
@app.post("/api/skills/install")
async def install_skill(req: InstallSkillRequest):
if req.manifest:
# 直接安裝 manifest
skill_dir = SKILLS_DIR / req.name
skill_dir.mkdir(exist_ok=True)
req.manifest["installed_at"] = datetime.now().isoformat()
req.manifest["enabled"] = True
with open(skill_dir / "skill.json", "w") as f:
json.dump(req.manifest, f, indent=2)
load_all_skills()
return {"success": True, "message": f"Skill '{req.name}' installed"}
elif req.url:
success = await install_skill_from_url(req.name, req.url)
if success:
return {"success": True, "message": f"Skill '{req.name}' installed from {req.url}
raise HTTPException(400, "Failed to install skill from URL")
raise HTTPException(400, "Provide either manifest or url")
@app.post("/api/skills/create")
async def create_skill(req: SkillManualCreate):
"""直接建立⾃定義 skill（含 handler code）"""
skill_dir = SKILLS_DIR / req.name
skill_dir.mkdir(exist_ok=True)
manifest = {
"name": req.name,
"description": req.description,
"version": "1.0.0",
"enabled": True,
"installed_at": datetime.now().isoformat(),
"tools": req.tools,
}
with open(skill_dir / "skill.json", "w") as f:
json.dump(manifest, f, indent=2)
if req.handler_code:
with open(skill_dir / "handler.py", "w") as f:
f.write(req.handler_code)
load_all_skills()
return {"success": True, "skill": req.name}
@app.delete("/api/skills/{skill_name}")
async def uninstall_skill(skill_name: str):
import shutil
skill_dir = SKILLS_DIR / skill_name
if skill_dir.exists():
shutil.rmtree(skill_dir)
load_all_skills()
return {"success": True}
raise HTTPException(404, f"Skill '{skill_name}' not found")
@app.patch("/api/skills/{skill_name}/toggle")
async def toggle_skill(skill_name: str):
if skill_name not in skill_registry:
raise HTTPException(404, "Skill not found")
skill_dir = SKILLS_DIR / skill_name
manifest_path = skill_dir / "skill.json"
with open(manifest_path) as f:
manifest = json.load(f)
manifest["enabled"] = not manifest.get("enabled", True)
with open(manifest_path, "w") as f:
json.dump(manifest, f, indent=2)
load_all_skills()
return {"success": True, "enabled": manifest["enabled"]}
@app.get("/api/skills/store/browse")
async def browse_store():
remote = await fetch_remote_registry()
installed = set(skill_registry.keys())
return {
"available": [
{**s, "installed": s["name"] in installed}
for s in remote
]
}
@app.get("/health")
async def health():
return {"status": "ok", "skills": len(skill_registry), "time": datetime.now().isoformat()
# ─── Frontend ───
@app.get("/", response_class=HTMLResponse)
async def frontend():
with open("index.html") as f:
return f.read()
# ─── Entry Point ───
if __name__ == "__main__":
import uvicorn
port = int(os.environ.get("PORT", 8080))
uvicorn.run(app, host="0.0.0.0", port=port)
