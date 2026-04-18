import importlib.util
import inspect
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

from app.db import load_installed_plugin_records, remember_installed_plugin
from app.settings import PLUGINS_DIR, REGISTRY_FILE

log = logging.getLogger(__name__)

plugin_registry: dict[str, dict] = {}


def load_plugin_manifest(plugin_dir: Path) -> Optional[dict]:
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        manifest_path = plugin_dir / "skill.json"
        if not manifest_path.exists():
            return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "id" not in data:
            data["id"] = data.get("name", plugin_dir.name)

        data.setdefault("name", data["id"])
        data.setdefault("description", "")
        data.setdefault("version", "1.0.0")
        data.setdefault("enabled", True)
        data.setdefault("category", "utility")
        data.setdefault("price", 0)
        data.setdefault("author", "local")
        data.setdefault("tools", [])

        return data
    except Exception as e:
        log.error(f"Failed loading manifest {manifest_path}: {e}")
        return None


def load_all_plugins():
    global plugin_registry
    plugin_registry = {}

    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    for path in PLUGINS_DIR.iterdir():
        if not path.is_dir():
            continue

        manifest = load_plugin_manifest(path)
        if not manifest:
            continue

        pid = manifest["id"]
        plugin_registry[pid] = {
            "manifest": manifest,
            "path": str(path),
            "enabled": manifest.get("enabled", True),
        }
        log.info(f"Loaded plugin: {pid}")

    log.info(f"Total plugins loaded: {len(plugin_registry)}")


def get_active_tools() -> list[dict]:
    tools = []
    for plugin in plugin_registry.values():
        if not plugin["enabled"]:
            continue
        tools.extend(plugin["manifest"].get("tools", []))
    return tools


async def execute_tool(tool_name: str, tool_input: dict):
    for plugin_id, plugin in plugin_registry.items():
        if not plugin["enabled"]:
            continue

        for tool in plugin["manifest"].get("tools", []):
            if tool.get("name") != tool_name:
                continue

            handler_file = Path(plugin["path"]) / "handler.py"
            if not handler_file.exists():
                return f"Tool '{tool_name}' handler.py not found in plugin '{plugin_id}'."

            try:
                spec = importlib.util.spec_from_file_location(f"plugin_{plugin_id}", handler_file)
                if spec is None or spec.loader is None:
                    return f"Tool '{tool_name}' load failed."

                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                if not hasattr(mod, tool_name):
                    return f"Tool '{tool_name}' function not found."

                fn = getattr(mod, tool_name)

                if inspect.iscoroutinefunction(fn):
                    result = await fn(**tool_input)
                else:
                    result = fn(**tool_input)

                if result is None:
                    return ""

                if isinstance(result, (dict, list)):
                    return json.dumps(result, ensure_ascii=False, indent=2)

                return str(result)

            except Exception:
                import traceback
                return f"Tool execution error:\n{traceback.format_exc()}"

    return f"tool not found: {tool_name}"


def get_store_registry():
    if not REGISTRY_FILE.exists():
        return []

    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


async def install_plugin_from_url(plugin_name: str, url: str, remember: bool = True) -> bool:
    plugin_dir = PLUGINS_DIR / plugin_name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    base = url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            manifest_resp = await client.get(f"{base}/plugin.json")
            if manifest_resp.status_code != 200:
                manifest_resp = await client.get(f"{base}/skill.json")
                if manifest_resp.status_code != 200:
                    log.error(f"plugin.json/skill.json not found from {base}")
                    return False

            handler_resp = await client.get(f"{base}/handler.py")

            manifest = manifest_resp.json()
            manifest.setdefault("id", plugin_name)
            manifest.setdefault("name", plugin_name)

            with open(plugin_dir / "plugin.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            if handler_resp.status_code == 200:
                with open(plugin_dir / "handler.py", "w", encoding="utf-8") as f:
                    f.write(handler_resp.text)

        load_all_plugins()

        if remember:
            remember_installed_plugin(plugin_name, url)

        return True
    except Exception as e:
        log.error(f"install_plugin_from_url error: {e}")
        return False


async def restore_installed_plugins():
    records = load_installed_plugin_records()
    if not records:
        log.info("No installed plugin records to restore.")
        return

    log.info(f"Restoring {len(records)} installed plugins...")

    for item in records:
        name = item.get("name", "").strip()
        url = item.get("url", "").strip()

        if not name or not url:
            continue

        ok = await install_plugin_from_url(name, url, remember=False)
        if ok:
            log.info(f"Restored plugin: {name}")
        else:
            log.warning(f"Failed to restore plugin: {name}")
