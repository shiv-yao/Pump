import inspect
from typing import Any

from app.plugin_manager import plugin_registry

# 新版優先，避免舊版同名工具搶走
PLUGIN_PRIORITY = [
    "auto_evolution_v1",
    "env_optimizer_ai_v2",
    "execution_engine_v7",
    "strategy_manager_v2",
    "allocator_v3",
    "wallet_alpha_v3",
    "ledger_v2",
    "replay_engine_v1",
    "execution_simulator_v1",
    "polymarket_exec_prod",
    "polymarket_alpha_ws",
    "wallet_feed_ws",
    "market_data",
]


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


def find_tool(tool_name: str):
    """
    回傳:
      (impl, resolved_tool_name, plugin_id)

    impl 預期是 plugin_manager 放進 registry 的可呼叫實作。
    """
    enabled = _enabled_plugins()

    # 1. 先依照 priority 找
    for pid in PLUGIN_PRIORITY:
        info = enabled.get(pid)
        if not info:
            continue

        if tool_name in _tool_names(info):
            return info.get("impl"), tool_name, pid

    # 2. 再從其餘 enabled plugins 找
    for pid, info in enabled.items():
        if pid in PLUGIN_PRIORITY:
            continue

        if tool_name in _tool_names(info):
            return info.get("impl"), tool_name, pid

    return None, None, None


async def call(tool_name: str, args: dict | None = None):
    """
    統一工具呼叫入口。
    支援兩種 plugin impl 形態：

    1. impl(tool_name, args)
    2. handler function / coroutine function
    """
    args = args or {}

    impl, resolved_name, plugin_id = find_tool(tool_name)

    if not impl:
        return {"error": f"tool not found: {tool_name}"}

    try:
        # plugin_manager 風格：impl(name, args)
        if callable(impl):
            try:
                result = impl(resolved_name, args)
                if inspect.isawaitable(result):
                    result = await result
                return result
            except TypeError:
                # fallback: 直接把 args 當 kwargs 傳入 handler function
                if inspect.iscoroutinefunction(impl):
                    return await impl(**args)
                return impl(**args)

        return {"error": f"invalid impl for tool: {tool_name}"}

    except Exception as e:
        return {"error": f"{plugin_id}.{tool_name} failed: {str(e)}"}


def debug_tool_map() -> dict[str, dict[str, str]]:
    """
    給 /debug 或人工檢查用：
    列出目前 tool 會被哪個 plugin 接走。
    """
    enabled = _enabled_plugins()
    all_tools = set()

    for info in enabled.values():
        all_tools.update(_tool_names(info))

    out = {}
    for name in sorted(all_tools):
        _, _, pid = find_tool(name)
        out[name] = {"plugin_id": pid or ""}

    return out
