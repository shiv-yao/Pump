# app/utils/loader.py

import importlib.util
import inspect
from pathlib import Path
from typing import Any

from app.plugin_manager import plugin_registry


PLUGIN_PRIORITY = [
    "auto_evolution_v1",
    "env_optimizer_ai_v2",
    "execution_engine_v7",
    "strategy_manager_v2",
    "allocator_v3",
    "portfolio_manager_v2",
    "wallet_alpha_v3",
    "ledger_v2",
    "replay_engine_v1",
    "execution_simulator_v1",
    "execution_gateway",
    "polymarket_exec_prod",
    "polymarket_alpha_ws",
    "wallet_feed_ws",
    "risk_engine",
    "orderbook_edge",
    "signal_filter",
    "market_data",
]

TOOL_ALIASES = {
    "price": ["get_spot_price", "get_ticker_24h", "get_price"],
    "balance": ["pm_balance", "get_balance", "balance"],
    "positions": ["get_positions", "positions", "get_state"],
    "orders": ["get_orders", "orders", "list_orders"],
    "scan": ["scan_market", "scanner_run", "scan"],
    "start_engine": ["start_v7_engine", "start_v6_engine", "start_engine"],
    "stop_engine": ["stop_v7_engine", "stop_v6_engine", "stop_engine"],
    "state": ["get_state", "state"],
    "start_arb_bot": ["start_arb_bot", "start_arb_engine", "arb_start"],
    "stop_arb_bot": ["stop_arb_bot", "stop_arb_engine", "arb_stop"],
    "arb_status": ["arb_status", "get_arb_status"],
    "replay": ["replay_run", "run_replay"],
    "evolution_status": ["evolution_status", "get_evolution_status"],
}


def _enabled_plugins() -> dict[str, dict[str, Any]]:
    return {
        pid: info
        for pid, info in plugin_registry.items()
        if info.get("enabled", False)
    }


def _tool_names(info: dict[str, Any]) -> list[str]:
    return [
        t.get("name")
        for t in info.get("manifest", {}).get("tools", [])
        if isinstance(t, dict) and t.get("name")
    ]


def _candidate_tool_names(tool_name: str) -> list[str]:
    names = [tool_name]
    aliases = TOOL_ALIASES.get(tool_name, [])
    for x in aliases:
        if x not in names:
            names.append(x)
    return names


def _load_handler_function(plugin_id: str, plugin_info: dict[str, Any], resolved_tool_name: str):
    handler_file = Path(plugin_info["path"]) / "handler.py"
    if not handler_file.exists():
        return None

    try:
        spec = importlib.util.spec_from_file_location(f"plugin_{plugin_id}", handler_file)
        if spec is None or spec.loader is None:
            return None

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, resolved_tool_name):
            return getattr(mod, resolved_tool_name)

        return None
    except Exception:
        return None


def find_tool(tool_name: str):
    """
    回傳:
      (fn, resolved_tool_name, plugin_id)
    """
    enabled = _enabled_plugins()
    candidates = _candidate_tool_names(tool_name)

    for pid in PLUGIN_PRIORITY:
        info = enabled.get(pid)
        if not info:
            continue

        tools = _tool_names(info)
        for candidate_name in candidates:
            if candidate_name in tools:
                fn = _load_handler_function(pid, info, candidate_name)
                if fn is not None:
                    return fn, candidate_name, pid

    for pid, info in enabled.items():
        if pid in PLUGIN_PRIORITY:
            continue

        tools = _tool_names(info)
        for candidate_name in candidates:
            if candidate_name in tools:
                fn = _load_handler_function(pid, info, candidate_name)
                if fn is not None:
                    return fn, candidate_name, pid

    return None, None, None


async def call(tool_name: str, args: dict | None = None):
    args = args or {}

    fn, resolved_name, plugin_id = find_tool(tool_name)

    if not fn:
        return {"error": f"tool not found: {tool_name}"}

    try:
        if inspect.iscoroutinefunction(fn):
            return await fn(**args)
        return fn(**args)
    except Exception as e:
        return {"error": f"{plugin_id}.{resolved_name} failed: {str(e)}"}


async def call_first(tool_names: list[str], args: dict | None = None):
    args = args or {}
    last_error = None

    for name in tool_names:
        result = await call(name, args)
        if not (isinstance(result, dict) and "error" in result):
            return result
        last_error = result

    return last_error or {"error": f"tool chain failed: {tool_names}"}


def debug_tool_map() -> dict[str, dict[str, Any]]:
    enabled = _enabled_plugins()
    all_tools = set()

    for info in enabled.values():
        all_tools.update(_tool_names(info))

    for alias_name in TOOL_ALIASES.keys():
        all_tools.add(alias_name)

    out: dict[str, dict[str, Any]] = {}

    for name in sorted(all_tools):
        _, resolved_name, pid = find_tool(name)
        out[name] = {
            "plugin_id": pid or "",
            "resolved_tool_name": resolved_name or "",
        }

    return out
