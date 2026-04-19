import json
import inspect
import importlib.util
from pathlib import Path

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


def _find_plugins_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent.parent / "plugins" if parent.name == "app" else parent / "plugins"
        if candidate.exists():
            return candidate
    return Path("plugins")


def _load_tool(tool_name: str):
    plugins_root = _find_plugins_root()

    if not plugins_root.exists():
        return None

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


def _parse_payload(text: str):
    text = (text or "").strip()
    if not text:
        return {}

    if text.startswith("{") and text.endswith("}"):
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
                "/help\n"
                "/skills\n"
                "/providers\n"
                "/store\n"
                "/install <name> <url>\n"
                "/enable <name>\n"
                "/disable <name>\n"
                "/remove <name>\n"
                "/auto_optimize_env [json]\n"
                "/auto_optimize_and_save_env [json]\n"
                "/save_env_block {\"env_block\":\"...\",\"filename\":\"latest.env\"}\n"
                "/auto_opt\n"
                "/apply_env\n"
                "/replay [json]\n"
                "/replay_opt [json]\n"
                "/simulate_order {\"asset_id\":\"A\",\"side\":\"buy\",\"size\":1,\"book\":{...},\"order_type\":\"ioc\"}\n"
                "/simulate_fill {\"asset_id\":\"A\",\"side\":\"buy\",\"size\":1,\"book\":{...}}\n"
                "/clear\n"
            )
        }

    # ========= CLEAR =========
    if head == "clear":
        return {"success": True, "output": "__CLEAR__"}

    # ========= SKILLS =========
    if head in {"skills", "plugins"}:
        if not plugin_registry:
            return {"success": True, "output": "No plugins loaded"}

        lines = []
        for pid, info in plugin_registry.items():
            enabled = info.get("enabled", False)
            tools = [t.get("name") for t in info.get("manifest", {}).get("tools", [])]
            lines.append(f"{pid} [{'ON' if enabled else 'OFF'}]  tools={tools}")

        return {"success": True, "output": "\n".join(lines)}

    # ========= PROVIDERS =========
    if head in {"providers", "status"}:
        claude = await check_claude_status()
        openai = await check_openai_status()
        trading = check_trading_status()

        return {
            "success": True,
            "output": _format({
                "claude": claude,
                "openai": openai,
                "trading_api": trading,
            })
        }

    # ========= STORE =========
    if head == "store":
        items = []
        for pid, info in plugin_registry.items():
            items.append({
                "id": pid,
                "enabled": info.get("enabled", False),
                "tools": [t.get("name") for t in info.get("manifest", {}).get("tools", [])]
            })
        return {"success": True, "output": _format(items)}

    # ========= INSTALL =========
    if head == "install":
        if not tail:
            return {"success": False, "output": "Usage: /install <name> <url>"}

        try:
            name, url = tail.split(maxsplit=1)
        except ValueError:
            return {"success": False, "output": "Usage: /install <name> <url>"}

        ok = await install_plugin_from_url(name, url, remember=True)
        if ok:
            return {"success": True, "output": f"Installed: {name}"}
        return {"success": False, "output": f"Install failed: {name}"}

    # ========= ENABLE / DISABLE =========
    if head == "enable":
        if not tail:
            return {"success": False, "output": "Usage: /enable <name>"}
        ok = set_plugin_enabled(tail, True)
        return {
            "success": ok,
            "output": f"{'Enabled' if ok else 'Enable failed'}: {tail}"
        }

    if head == "disable":
        if not tail:
            return {"success": False, "output": "Usage: /disable <name>"}
        ok = set_plugin_enabled(tail, False)
        return {
            "success": ok,
            "output": f"{'Disabled' if ok else 'Disable failed'}: {tail}"
        }

    # ========= REMOVE =========
    if head in {"remove", "delete"}:
        if not tail:
            return {"success": False, "output": "Usage: /remove <name>"}
        ok = remove_plugin(tail)
        return {
            "success": ok,
            "output": f"{'Removed' if ok else 'Remove failed'}: {tail}"
        }

    # ========= ENV OPTIMIZER COMMANDS =========
    if head == "auto_optimize_env":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {}
        result = await _call_tool("auto_optimize_env", payload)
        return {"success": True, "output": _format(result)}

    if head == "auto_optimize_and_save_env":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {}
        result = await _call_tool("auto_optimize_and_save_env", payload)
        return {"success": True, "output": _format(result)}

    if head == "save_env_block":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            return {
                "success": False,
                "output": 'Usage: /save_env_block {"env_block":"...","filename":"latest.env"}'
            }
        result = await _call_tool("save_env_block", payload)
        return {"success": True, "output": _format(result)}

    # ========= AI AUTO TUNING SHORTCUTS =========
    if head == "auto_opt":
        result = await _call_tool("auto_optimize_env", {})
        return {"success": True, "output": _format(result)}

    if head == "apply_env":
        result = await _call_tool("apply_best_env", {})
        return {"success": True, "output": _format(result)}

    # ========= REPLAY SHORTCUTS =========
    if head == "replay":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {}
        result = await _call_tool("replay_run", payload)
        return {"success": True, "output": _format(result)}

    if head == "replay_opt":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            payload = {}
        result = await _call_tool("replay_optimize", payload)
        return {"success": True, "output": _format(result)}

    # ========= EXECUTION SIMULATOR SHORTCUTS =========
    if head == "simulate_order":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            return {
                "success": False,
                "output": (
                    'Usage: /simulate_order {"asset_id":"A","side":"buy","size":1,'
                    '"book":{"best_bid":0.49,"best_ask":0.51,"bids":[...],"asks":[...]},'
                    '"order_type":"ioc","price":0.51}'
                )
            }
        result = await _call_tool("simulate_order", payload)
        return {"success": True, "output": _format(result)}

    if head == "simulate_fill":
        payload = _parse_payload(tail)
        if "_raw" in payload:
            return {
                "success": False,
                "output": (
                    'Usage: /simulate_fill {"asset_id":"A","side":"buy","size":1,'
                    '"book":{"best_bid":0.49,"best_ask":0.51,"bids":[...],"asks":[...]}}'
                )
            }
        result = await _call_tool("simulate_fill", payload)
        return {"success": True, "output": _format(result)}

    # ========= GENERIC TOOL DISPATCH =========
    payload = _parse_payload(tail)
    if "_raw" in payload:
        payload = {}

    tool_fn = _load_tool(head)
    if tool_fn:
        result = await _call_tool(head, payload)
        return {"success": True, "output": _format(result)}

    return {"success": False, "output": f"Unknown command: {raw}"}
