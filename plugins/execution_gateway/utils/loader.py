import json
import importlib.util
from pathlib import Path
import inspect


def load_tool(tool):
    root = Path("plugins")

    for d in root.iterdir():
        m = d / "plugin.json"
        h = d / "handler.py"

        if not m.exists() or not h.exists():
            continue

        try:
            data = json.loads(m.read_text())
        except:
            continue

        if not any(t.get("name") == tool for t in data.get("tools", [])):
            continue

        spec = importlib.util.spec_from_file_location(d.name, h)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool):
            return getattr(mod, tool)

    return None


async def call(tool, payload=None):
    payload = payload or {}

    fn = load_tool(tool)
    if not fn:
        return {"error": f"{tool} not found"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)
