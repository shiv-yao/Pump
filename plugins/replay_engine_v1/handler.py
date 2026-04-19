import json
import random
import inspect
import importlib.util
from pathlib import Path


# ===== param space =====
PARAM_SPACE = {
    "ENTRY_THRESHOLD": [0.50, 0.55, 0.60, 0.65],
    "RISK_SCALE": [0.50, 0.70, 1.00],
    "SIZE_MULT": [0.50, 1.00, 1.50],
}


# ===== plugin tool loader =====
def _plugins_root() -> Path:
    cur = Path(__file__).resolve()
    for p in cur.parents:
        if (p / "plugins").exists():
            return p / "plugins"
    return Path(__file__).resolve().parent.parent


def _load_tool(tool_name: str):
    plugins_root = _plugins_root()

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


async def _call_tool(tool_name: str, payload: dict | None = None):
    payload = payload or {}
    fn = _load_tool(tool_name)

    if not fn:
        return {"error": f"tool not found: {tool_name}"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


# ===== data loader =====
def _load_recent_trades(sample_size=200):
    """
    Reads recent trades from execution_engine_v7 source file namespace.
    """
    try:
        plugins_dir = _plugins_root()
        engine_file = plugins_dir / "execution_engine_v7" / "handler.py"
        if not engine_file.exists():
