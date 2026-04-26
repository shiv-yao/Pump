import importlib.util
import inspect
import json
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

        tools = manifest.get("tools", [])
        if not any(t.get("name") == tool_name for t in tools):
            continue

        spec = importlib.util.spec_from_file_location(f"plugin_{plugin_dir.name}", handler_path)
        if spec is None or spec.loader is None:
            continue

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool_name):
            fn = getattr(mod, tool_name)
            return fn

    return None


async def route_order(target: str, side: str, symbol: str, amount: float):
    target = (target or "").strip().lower()
    side = (side or "").strip().lower()

    if side not in {"buy", "sell"}:
        return {"error": f"unsupported side: {side}"}

    if target == "polymarket":
        tool_name = "pm_buy" if side == "buy" else "pm_sell"
        fn = _load_tool(tool_name)
        if not fn:
            return {"error": f"{tool_name} not found. Is polymarket_exec installed and enabled?"}

        payload = {"market": symbol, "amount": amount}

    elif target == "solana":
        tool_name = "sol_buy" if side == "buy" else "sol_sell"
        fn = _load_tool(tool_name)
        if not fn:
            return {"error": f"{tool_name} not found. Is solana_exec installed and enabled?"}

        if side == "buy":
            payload = {"mint": symbol, "sol": amount}
        else:
            payload = {"mint": symbol}

    else:
        return {"error": f"unknown target: {target}"}

    try:
        if inspect.iscoroutinefunction(fn):
            result = await fn(**payload)
        else:
            result = fn(**payload)

        return {
            "target": target,
            "side": side,
            "symbol": symbol,
            "amount": amount,
            "result": result
        }
    except Exception as e:
        return {"error": f"route_order failed: {e}"}
