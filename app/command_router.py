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

    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except Exception:
            return {"_raw": text}

    return {"_raw": text}


def _format(obj):
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
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

    head = parts[0].strip().lower()
    tail = parts[1].strip() if len(parts) > 1 else ""

    # ========= HELP =========
    if head in {"help", "?"}:
        return {
            "success": True,
            "output": (
                "/help\n"
                "/skills\n"
                "/providers\n"
                "/install <name> <url>\n"
                "/enable <name>\n"
                "/disable <name>\n"
                "/remove <name>\n"
                "/pump\n"
                "/pump_candidates\n"
                "/pump_candidates {\"limit\":5,\"max_age_sec\":120}\n"
                "/sniper_scan\n"
                "/start_sniper\n"
                "/stop_sniper\n"
                "/start_mempool\n"
                "/stop_mempool\n"
                "/dev_signal {\"asset_id\":\"<mint>\"}\n"
                "/decide BTCUSDT\n"
                "/decide {\"symbol\":\"BTCUSDT\",\"capital\":100}\n"
                "/price BTCUSDT\n"
                "/balance\n"
                "/positions\n"
                "/orders\n"
                "/buy BTCUSDT 0.01\n"
                "/sell BTCUSDT 0.01\n"
                "/scan BTCUSDT SOLUSDT\n"
                "/run_fund_cycle {\"symbol\":\"BTCUSDT\"}\n"
                "/state\n"
                "/start_engine\n"
                "/stop_engine\n"
                "/start_arb_bot\n"
                "/stop_arb_bot\n"
                "/arb_status\n"
                "/apply_env\n"
                "/replay\n"
                "/auto_evolution\n"
                "/automl\n"
                "/automl_status\n"
                "/start_automl\n"
                "/stop_automl\n"
                "/clear\n"
            )
        }

    # ========= CLEAR =========
    if head == "clear":
        return {"success": True, "output": "__CLEAR__"}

    # ========= SKILLS / PLUGINS =========
    if head in {"skills", "plugins"}:
        if not plugin_registry:
            return {"success": True, "output": "No plugins loaded"}

        lines = []
        for pid, info in plugin_registry.items():
            enabled = info.get("enabled", False)
            tools = [t.get("name") for t in info.get("manifest", {}).get("tools", [])]
            lines.append(f"{pid} [{'ON' if enabled else 'OFF'}] tools={tools}")

        return {"success": True, "output": "\n".join(lines)}

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

    # ========= INSTALL / ENABLE / DISABLE / REMOVE =========
    if head == "install":
        if not tail:
            return {"success": False, "output": "Usage: /install <name> <url>"}

        try:
            name, url = tail.split(maxsplit=1)
        except ValueError:
            return {"success": False, "output": "Usage: /install <name> <url>"}

        ok = await install_plugin_from_url(name, url, remember=True)
        return {
            "success": bool(ok),
            "output": f"{'Installed' if ok else 'Install failed'}: {name}"
        }

    if head == "enable":
        if not tail:
            return {"success": False, "output": "Usage: /enable <name>"}
        ok = set_plugin_enabled(tail, True)
        return {
            "success": bool(ok),
            "output": f"{'Enabled' if ok else 'Enable failed'}: {tail}"
        }

    if head == "disable":
        if not tail:
            return {"success": False, "output": "Usage: /disable <name>"}
        ok = set_plugin_enabled(tail, False)
        return {
            "success": bool(ok),
            "output": f"{'Disabled' if ok else 'Disable failed'}: {tail}"
        }

    if head in {"remove", "delete"}:
        if not tail:
            return {"success": False, "output": "Usage: /remove <name>"}
        ok = remove_plugin(tail)
        return {
            "success": bool(ok),
            "output": f"{'Removed' if ok else 'Remove failed'}: {tail}"
        }

    # ========= PUMP =========
    if head == "pump":
        result = await _call_first(["pump_latest"], {})
        return {"success": True, "output": _format(result)}

    if head == "pump_candidates":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {"limit": 10, "max_age_sec": 180}
        result = await _call_first(["pump_candidates"], payload)
        return {"success": True, "output": _format(result)}

    # ========= SNIPER =========
    if head == "sniper_scan":
        result = await _call_first(["sniper_scan"], {})
        return {"success": True, "output": _format(result)}

    if head == "start_sniper":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {}
        result = await _call_first(["start_sniper"], payload)
        return {"success": True, "output": _format(result)}

    if head == "stop_sniper":
        result = await _call_first(["stop_sniper"], {})
        return {"success": True, "output": _format(result)}

    # ========= MEMPOOL =========
    if head == "start_mempool":
        result = await _call_first(["start_mempool_sniper"], {})
        return {"success": True, "output": _format(result)}

    if head == "stop_mempool":
        result = await _call_first(["stop_mempool_sniper"], {})
        return {"success": True, "output": _format(result)}

    # ========= DEV WALLET =========
    if head == "dev_signal":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {}
        result = await _call_first(["get_dev_signal"], payload)
        return {"success": True, "output": _format(result)}

    # ========= FUND DECISION =========
    if head in {"decide", "fund_decide", "decide_trade"}:
        payload = _parse_payload(tail)

        if "_raw" in payload:
            symbol = tail.strip() or "BTCUSDT"
            payload = {"symbol": symbol}

        if not payload.get("symbol"):
            payload["symbol"] = payload.get("asset_id", "BTCUSDT")

        result = await _call_first(
            ["fund_decide_trade", "decide_trade"],
            payload
        )
        return {"success": True, "output": _format(result)}

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
            return {"success": False, "output": f"Usage: /{head} BTCUSDT 0.01"}

        symbol = args[0]

        try:
            size = float(args[1])
        except Exception:
            return {"success": False, "output": "size must be number"}

        result = await _call_first(
            [
                "trade_order",
                "buy_token" if head == "buy" else "sell_token",
                "simulate_order",
            ],
            {
                "symbol": symbol,
                "asset_id": symbol,
                "size": size,
                "amount": size,
                "side": head,
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

    # ========= FUND CYCLE =========
    if head == "run_fund_cycle":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {"symbol": "BTCUSDT"}
        result = await _call_first(["run_fund_cycle"], payload)
        return {"success": True, "output": _format(result)}

    # ========= ENGINE =========
    if head == "state":
        result = await _call_first(["get_state", "state"], {})
        return {"success": True, "output": _format(result)}

    if head == "start_engine":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {}
        result = await _call_first(
            ["start_engine", "start_v7_engine"],
            payload
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
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {}
        result = await _call_first(
            ["replay_run", "replay"],
            payload
        )
        return {"success": True, "output": _format(result)}

    # ========= AUTO EVOLUTION =========
    if head == "auto_evolution":
        result = await _call_first(
            ["run_evolution_cycle", "auto_evolution"],
            {}
        )
        return {"success": True, "output": _format(result)}

    # ========= AUTOML =========
    if head == "automl":
        result = await _call_first(["run_automl"], {})
        return {"success": True, "output": _format(result)}

    if head == "automl_status":
        result = await _call_first(
            ["get_automl_status", "automl_status"],
            {}
        )
        return {"success": True, "output": _format(result)}

    if head == "start_automl":
        result = await _call_first(
            ["start_automl_scheduler", "automl_start"],
            {}
        )
        return {"success": True, "output": _format(result)}

    if head == "stop_automl":
        result = await _call_first(
            ["stop_automl_scheduler", "automl_stop"],
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
