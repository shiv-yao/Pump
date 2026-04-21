# app/utils/loader.py

from app.plugin_manager import plugin_registry

# ===== 優先順序（新版優先）=====
PRIORITY = [
    "env_optimizer_ai_v2",
    "auto_evolution_v1",
    "execution_engine_v7",
    "strategy_manager_v2",
    "allocator_v3",
    "wallet_alpha_v3",
    "ledger_v2",
    "polymarket_exec_prod",
    "execution_simulator_v1",
    "replay_engine_v1",
    "market_data",
]


def load_tool(tool_name: str):
    """
    根據 priority 找最正確 plugin
    """

    # 1️⃣ 先按 priority 找
    for pid in PRIORITY:
        p = plugin_registry.get(pid)
        if not p or not p.get("enabled"):
            continue

        for t in p["manifest"].get("tools", []):
            if t.get("name") == tool_name:
                return p["impl"], t["name"], pid

    # 2️⃣ fallback（避免完全壞掉）
    for pid, p in plugin_registry.items():
        if not p.get("enabled"):
            continue

        for t in p["manifest"].get("tools", []):
            if t.get("name") == tool_name:
                return p["impl"], t["name"], pid

    return None, None, None


async def call(tool_name: str, args: dict):
    impl, name, pid = load_tool(tool_name)

    if not impl:
        return {"error": f"tool not found: {tool_name}"}

    try:
        return await impl(name, args)
    except Exception as e:
        return {"error": f"{pid}.{tool_name} failed: {str(e)}"}
