import json

from app.plugin_manager import (
    execute_tool,
    get_store_registry,
    install_plugin_from_url,
    plugin_registry,
    set_plugin_enabled,
    remove_plugin,
)
from app.provider_status import (
    check_claude_status,
    check_openai_status,
    check_trading_status,
)


def parse_command(command: str) -> dict:
    raw = command.strip()
    if raw.startswith("/"):
        raw = raw[1:].strip()

    if not raw:
        return {"cmd": "", "args": []}

    parts = raw.split()
    return {"cmd": parts[0].lower(), "args": parts[1:]}


async def execute_platform_command(command: str) -> dict:
    parsed = parse_command(command)
    cmd = parsed["cmd"]
    args = parsed["args"]

    if not cmd:
        return {"success": False, "output": "空指令"}

    if cmd == "help":
        return {
            "success": True,
            "output": (
                "/help\n"
                "/skills\n"
                "/providers\n"
                "/store\n"
                "/install <name> <url>\n"
                "/enable <name>\n"
                "/disable <name>\n"
                "/remove <name>\n"
                "/price <symbol>\n"
                "/signal <symbol>\n"
                "/scan <symbol1> [symbol2]\n"
                "/balance\n"
                "/positions\n"
                "/orders\n"
                "/buy <symbol> <amount>\n"
                "/sell <symbol> <amount>\n"
                "/killswitch\n"
                "/start_arb_bot\n"
                "/stop_arb_bot\n"
                "/arb_status\n"
                "/clear"
            )
        }

    if cmd == "skills":
        items = [f"{pid} [{'ON' if info['enabled'] else 'OFF'}]" for pid, info in plugin_registry.items()]
        return {"success": True, "output": "\n".join(items) if items else "No plugins loaded"}

    if cmd == "providers":
        return {
            "success": True,
            "output": json.dumps({
                "claude": await check_claude_status(),
                "openai": await check_openai_status(),
                "trading_api": check_trading_status(),
            }, ensure_ascii=False, indent=2)
        }

    if cmd == "store":
        return {"success": True, "output": json.dumps(get_store_registry(), ensure_ascii=False, indent=2)}

    if cmd == "install":
        if len(args) < 2:
            return {"success": False, "output": "用法：/install <plugin_name> <url>"}
        ok = await install_plugin_from_url(args[0], args[1], remember=True)
        return {"success": ok, "output": f"Installed: {args[0]}" if ok else f"Install failed: {args[0]}"}

    if cmd == "enable":
        if len(args) < 1:
            return {"success": False, "output": "用法：/enable <plugin_name>"}
        ok = set_plugin_enabled(args[0], True)
        return {"success": ok, "output": f"Enabled: {args[0]}" if ok else f"Plugin not found: {args[0]}"}

    if cmd == "disable":
        if len(args) < 1:
            return {"success": False, "output": "用法：/disable <plugin_name>"}
        ok = set_plugin_enabled(args[0], False)
        return {"success": ok, "output": f"Disabled: {args[0]}" if ok else f"Plugin not found: {args[0]}"}

    if cmd == "remove":
        if len(args) < 1:
            return {"success": False, "output": "用法：/remove <plugin_name>"}
        ok = remove_plugin(args[0])
        return {"success": ok, "output": f"Removed: {args[0]}" if ok else f"Plugin not found: {args[0]}"}

    if cmd == "price":
        if len(args) < 1:
            return {"success": False, "output": "用法：/price <symbol>"}
        return {"success": True, "output": str(await execute_tool("get_spot_price", {"symbol": args[0].upper()}))}

    if cmd == "signal":
        if len(args) < 1:
            return {"success": False, "output": "用法：/signal <symbol>"}
        return {"success": True, "output": str(await execute_tool("get_trading_signal", {"symbol": args[0].upper(), "timeframe": "1h"}))}

    if cmd == "scan":
        if len(args) < 1:
            return {"success": False, "output": "用法：/scan <symbol1> [symbol2] ..."}
        return {"success": True, "output": str(await execute_tool("scan_market", {"symbols": [x.upper() for x in args]}))}

    if cmd == "balance":
        return {"success": True, "output": str(await execute_tool("get_balance", {}))}
    if cmd == "positions":
        return {"success": True, "output": str(await execute_tool("get_positions", {}))}
    if cmd == "orders":
        return {"success": True, "output": str(await execute_tool("get_orders", {}))}

    if cmd == "buy":
        if len(args) < 2:
            return {"success": False, "output": "用法：/buy <symbol> <amount>"}
        return {"success": True, "output": str(await execute_tool("buy_token", {"symbol": args[0].upper(), "amount": float(args[1])}))}

    if cmd == "sell":
        if len(args) < 2:
            return {"success": False, "output": "用法：/sell <symbol> <amount>"}
        return {"success": True, "output": str(await execute_tool("sell_token", {"symbol": args[0].upper(), "amount": float(args[1])}))}

    if cmd == "killswitch":
        return {"success": True, "output": str(await execute_tool("kill_switch", {}))}
    if cmd == "start_arb_bot":
        return {"success": True, "output": str(await execute_tool("start_arb_bot", {}))}
    if cmd == "stop_arb_bot":
        return {"success": True, "output": str(await execute_tool("stop_arb_bot", {}))}
    if cmd == "arb_status":
        return {"success": True, "output": str(await execute_tool("arb_status", {}))}

    if cmd == "clear":
        return {"success": True, "output": "__CLEAR__"}

    return {"success": False, "output": f"Unknown command: {cmd}"}
