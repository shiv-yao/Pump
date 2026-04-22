import json

from app.plugin_manager import (
    plugin_registry,
    install_plugin_from_url,
    remove_plugin,
    set_plugin_enabled,
)
from app.provider_status import (
    check_claude_status,
    check_openai_status,
    check_trading_status,
)

# ===== unified loader =====
try:
    from app.utils.loader import call as shared_call
except Exception:
    shared_call = None


# =========================
# CORE CALL
# =========================

async def _call_tool(tool_name: str, payload=None):
    payload = payload or {}

    if shared_call is None:
        return {"error": f"loader not available: {tool_name}"}

    try:
        return await shared_call(tool_name, payload)
    except Exception as e:
        return {"error": f"{tool_name} failed: {str(e)}"}


async def _call_first(tool_names, payload=None):
    payload = payload or {}
    last_error = None

    for name in tool_names:
        result = await _call_tool(name, payload)

        if not (isinstance(result, dict) and "error" in result):
            return result

        last_error = result

    return last_error or {"error": f"tool chain failed: {tool_names}"}


# =========================
# UTILS
# =========================

def _parse_payload(text: str):
    text = (text or "").strip()

    if not text:
        return {}

    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except:
            return {"_raw": text}

    return {"_raw": text}


def _format(obj):
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except:
        return str(obj)


# =========================
# MAIN ROUTER
# =========================

async def execute_platform_command(command: str):
    raw = (command or "").strip()

    if not raw:
        return {"success": False, "output": "Empty command"}

    cmdline = raw[1:] if raw.startswith("/") else raw
    parts = cmdline.split(maxsplit=1)

    head = parts[0].strip()
    tail = parts[1].strip() if len(parts) > 1 else ""

    # ========= HELP =========
    if head in {"help", "?"}:
        return {
            "success": True,
            "output": (
                "/price BTCUSDT\n"
                "/balance\n"
                "/positions\n"
                "/orders\n"
                "/buy BTCUSDT 10\n"
                "/sell BTCUSDT 10\n"
                "/scan BTCUSDT SOLUSDT\n"
                "/state\n"
                "/start_engine\n"
                "/stop_engine\n"
                "/start_arb_bot\n"
                "/stop_arb_bot\n"
                "/arb_status\n"
                "/apply_env\n"
                "/replay\n"
                "/auto_evolution\n"
            )
        }

    # ========= CLEAR =========
    if head == "clear":
        return {"success": True, "output": "__CLEAR__"}

    # ========= PROVIDERS =========
    if head in {"providers", "status"}:
        return {
            "success": True,
            "output": _format({
                "claude": await check_claude_status(),
                "openai": await check_openai_status(),
                "trading_api": check_trading_status(),
            })
        }

    # ========= PRICE =========
    if head == "price":
        if not tail:
            return {"success": False, "output": "Usage: /price BTCUSDT"}

        result = await _call_first(
            ["price", "get_spot_price", "get_ticker_24h"],
            {"symbol": tail}
        )
        return {"success": True, "output": _format(result)}

    # ========= BALANCE =========
    if head == "balance":
        result = await _call_first(
            ["pm_balance", "get_balance", "balance"],
            {}
        )
        return {"success": True, "output": _format(result)}

    # ========= POSITIONS =========
    if head == "positions":
        result = await _call_first(
            ["get_positions", "positions", "get_state"],
            {}
        )
        return {"success": True, "output": _format(result)}

    # ========= ORDERS =========
    if head == "orders":
        result = await _call_first(
            ["get_orders", "orders"],
            {}
        )
        return {"success": True, "output": _format(result)}

    # ========= BUY / SELL =========
    if head in {"buy", "sell"}:
        args = tail.split()

        if len(args) < 2:
            return {"success": False, "output": f"/{head} BTCUSDT 10"}

        symbol = args[0]

        try:
            size = float(args[1])
        except:
            return {"success": False, "output": "size must be number"}

        result = await _call_first(
            [
                "buy_token" if head == "buy" else "sell_token",
                "trade_order",
                "simulate_order"
            ],
            {
                "symbol": symbol,
                "asset_id": symbol,
                "size": size,
                "side": head
            }
        )

        return {"success": True, "output": _format(result)}

    # ========= SCAN =========
    if head == "scan":
        symbols = tail.split()
        result = await _call_first(
            ["scan_market", "scan"],
            {"symbols": symbols}
        )
        return {"success": True, "output": _format(result)}

    # ========= FUND / ENGINE =========
    if head == "state":
        result = await _call_first(["get_state", "state"], {})
        return {"success": True, "output": _format(result)}

    if head == "start_engine":
        result = await _call_first(
            ["start_engine", "start_v7_engine"],
            {}
        )
        return {"success": True, "output": _format(result)}

    if head == "stop_engine":
        result = await _call_first(
            ["stop_engine", "stop_v7_engine"],
            {}
        )
        return {"success": True, "output": _format(result)}

    # ========= ARB =========
    if head == "start_arb_bot":
        result = await _call_first(["start_arb_bot"], {})
        return {"success": True, "output": _format(result)}

    if head == "stop_arb_bot":
        result = await _call_first(["stop_arb_bot"], {})
        return {"success": True, "output": _format(result)}

    if head == "arb_status":
        result = await _call_first(["arb_status"], {})
        return {"success": True, "output": _format(result)}

    # ========= ENV =========
    if head == "apply_env":
        result = await _call_first(
            ["apply_best_env", "apply_env"],
            {}
        )
        return {"success": True, "output": _format(result)}

    # ========= REPLAY =========
    if head == "replay":
        result = await _call_first(
            ["replay_run", "replay"],
            {}
        )
        return {"success": True, "output": _format(result)}

    # ========= AUTO EVOLUTION =========
    if head == "auto_evolution":
        result = await _call_first(
            ["run_evolution_cycle", "auto_evolution"],
            {}
        )
        return {"success": True, "output": _format(result)}

    # ========= GENERIC =========
    payload = _parse_payload(tail)
    if "_raw" in payload:
        payload = {}

    result = await _call_tool(head, payload)

    if isinstance(result, dict) and "error" in result:
        return {"success": False, "output": result["error"]}

    return {"success": True, "output": _format(result)}
