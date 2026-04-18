import os, json, inspect, importlib.util
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
import anthropic
from openai import AsyncOpenAI

app = FastAPI()

PLUGINS_DIR = Path("plugins")
PLUGINS_DIR.mkdir(exist_ok=True)

plugin_registry = {}

def load_all_plugins():
    global plugin_registry
    plugin_registry = {}
    for p in PLUGINS_DIR.iterdir():
        if p.is_dir():
            f = p / "plugin.json"
            if f.exists():
                data = json.load(open(f))
                plugin_registry[data["id"]] = {
                    "manifest": data,
                    "path": str(p),
                    "enabled": data.get("enabled", True)
                }

def get_active_tools():
    tools = []
    for p in plugin_registry.values():
        if p["enabled"]:
            tools.extend(p["manifest"]["tools"])
    return tools

async def execute_tool(name, inp):
    for p in plugin_registry.values():
        if not p["enabled"]:
            continue
        for t in p["manifest"]["tools"]:
            if t["name"] == name:
                path = Path(p["path"]) / "handler.py"
                spec = importlib.util.spec_from_file_location("mod", path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                fn = getattr(mod, name)
                if inspect.iscoroutinefunction(fn):
                    return await fn(**inp)
                return fn(**inp)
    return "tool not found"

class Agent:
    def __init__(self):
        self.claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.gpt = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def run(self, msg):
        tools = get_active_tools()
        try:
            res = await self.claude.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=500,
                messages=[{"role": "user", "content": msg}],
                tools=tools
            )
            return str(res.content)
        except:
            res = await self.gpt.responses.create(
                model="gpt-4.1-mini",
                input=msg
            )
            return res.output_text

agent = Agent()

class Chat(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(req: Chat):
    return {"response": await agent.run(req.message)}

@app.get("/api/plugins")
async def plugins():
    return plugin_registry

@app.post("/api/plugins/install")
async def install(req: dict):
    name = req["name"]
    url = req["url"]
    p = PLUGINS_DIR / name
    p.mkdir(exist_ok=True)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{url}/plugin.json")
        if r.status_code != 200:
            raise HTTPException(400)
        open(p/"plugin.json","w").write(r.text)
        r2 = await c.get(f"{url}/handler.py")
        if r2.status_code == 200:
            open(p/"handler.py","w").write(r2.text)
    load_all_plugins()
    return {"success": True}

@app.get("/api/store")
async def store():
    data = json.load(open("plugins/registry.json"))
    installed = set(plugin_registry.keys())
    return [{**p, "installed": p["id"] in installed} for p in data]

@app.get("/", response_class=HTMLResponse)
async def ui():
    return open("index.html").read()

@app.on_event("startup")
async def start():
    load_all_plugins()
