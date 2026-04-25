# utils/loader.py

import json
import inspect
import importlib.util
from pathlib import Path

PLUGIN_CACHE = {}


def _find_plugins_root():
    for p in Path(__file__).resolve().parents:
        if (p / "plugins").exists():
            return p / "plugins"
    return Path("plugins")


def _load_plugin_module(plugin_dir):
    if plugin_dir.name in PLUGIN_CACHE:
        return PLUGIN_CACHE[plugin_dir.name]

    handler_path = plugin_dir / "handler.py"
    if not handler_path.exists():
        return None

    spec = importlib.util.spec_from_file_location(
        f"plugin_{plugin_dir.name}",
        handler_path
    )

    if not spec or not spec.loader:
        return None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    PLUGIN_CACHE[plugin_dir.name] = mod
    return mod


def load_tool(tool_name):
    root = _find_plugins_root()

    best_fn = None
    best_priority = -1

    for d in root.iterdir():
        manifest_path = d / "plugin.json"

        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        tools = manifest.get("tools", [])
        priority = manifest.get("priority", 0)

        if not any(t.get("name") == tool_name for t in tools):
            continue

        mod = _load_plugin_module(d)
        if not mod:
            continue

        if hasattr(mod, tool_name):
            if priority >= best_priority:
                best_fn = getattr(mod, tool_name)
                best_priority = priority

    return best_fn


async def call(tool, payload=None):
    payload = payload or {}

    fn = load_tool(tool)

    if not fn:
        return {"error": f"{tool} not found"}

    try:
        if inspect.iscoroutinefunction(fn):
            return await fn(**payload)
        return fn(**payload)

    except Exception as e:
        return {"error": f"{tool} failed: {str(e)}"}
