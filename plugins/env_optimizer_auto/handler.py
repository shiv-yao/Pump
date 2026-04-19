import json
import importlib.util
import inspect
from pathlib import Path


def _find_plugins_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "plugins"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent


def _load_tool(tool_name: str):
    plugins_root = _find_plugins_root()

    for plugin_dir in plugins_root.iterdir():
        if not plugin_dir.is_dir():
            continue

        manifest_path = plugin_dir / "plugin.json"
        handler_path = plugin_dir / "handler.py"

        if not manifest_path.exists() or not handler_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not any(t.get("name") == tool_name for t in manifest.get("tools", [])):
            continue

        spec = importlib.util.spec_from_file_location(f"plugin_{plugin_dir.name}", handler_path)
        if not spec or not spec.loader:
            continue

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool_name):
            return getattr(mod, tool_name)

    return None


async def _call_tool(tool_name: str, payload: dict):
    fn = _load_tool(tool_name)
    if not fn:
        return {"error": f"tool not found: {tool_name}"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


async def auto_optimize_env(engine_tool: str = "get_state", current: dict | None = None):
    # 1. 讀 engine trades
    state = await _call_tool(engine_tool, {})

    if not isinstance(state, dict):
        return {"error": "engine state is not dict"}

    trades = state.get("trades", [])
    if not isinstance(trades, list):
        return {"error": "trades not found in engine state"}

    # 2. 跑 optimizer
    suggest = await _call_tool("suggest_env_params", {
        "trades": trades,
        "current": current or {}
    })

    if not isinstance(suggest, dict) or "params" not in suggest:
        return {"error": "suggest_env_params failed", "raw": suggest}

    params = suggest["params"]

    # 3. 輸出 env block
    env_block = await _call_tool("export_env_block", {
        "params": params
    })

    return {
        "stats": suggest.get("stats", {}),
        "params": params,
        "env_block": env_block
    }
