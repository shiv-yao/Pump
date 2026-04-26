import asyncio
import importlib.util
import inspect
import json
from pathlib import Path

RUNNING = False


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

        if not any(t.get("name") == tool_name for t in manifest.get("tools", [])):
            continue

        spec = importlib.util.spec_from_file_location(
            f"plugin_{plugin_dir.name}", handler_path
        )
        if not spec or not spec.loader:
            continue

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool_name):
            return getattr(mod, tool_name)

    return None


async def _call(tool_name: str, payload: dict):
    fn = _load_tool(tool_name)
    if not fn:
        return {"error": f"{tool_name} not found"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


async def run_polymarket_fund(
    asset_id: str,
    symbol: str,
    capital: float = 10.0,
    loops: int = 999,
):
    """
    asset_id: Polymarket token/asset id
    symbol: external market symbol used by alpha model, e.g. BTCUSDT
    """

    global RUNNING
    RUNNING = True
    logs = []

    # 1) start websocket book stream
    start_result = await _call("start_polymarket_book", {"asset_ids": [asset_id]})
    logs.append({"stage": "start_ws", "result": start_result})

    for i in range(int(loops)):
        if not RUNNING:
            break

        try:
            # 2) alpha from websocket cache + REST fallback
            alpha = await _call("get_polymarket_signal_ws", {
                "asset_id": asset_id,
                "symbol": symbol,
            })

            if isinstance(alpha, str):
                try:
                    alpha = json.loads(alpha)
                except Exception:
                    alpha = {"error": alpha}

            if "error" in alpha:
                logs.append({"loop": i, "stage": "alpha", "error": alpha})
                await asyncio.sleep(1)
                continue

            action = alpha.get("action", "hold")
            confidence = float(alpha.get("confidence", 0.0))
            combined_score = float(alpha.get("combined_score", 0.0))

            # 3) risk gate
            can = await _call("can_trade", {})
            if can is not True:
                logs.append({"loop": i, "stage": "risk", "status": "blocked"})
                await asyncio.sleep(1)
                continue

            # 4) dynamic size from fund brain
            size = await _call("position_size", {
                "score": abs(combined_score),
                "capital": float(capital),
            })

            try:
                size = float(size)
            except Exception:
                size = float(capital) * 0.1

            if action == "hold":
                logs.append({
                    "loop": i,
                    "stage": "decision",
                    "action": "hold",
                    "score": combined_score,
                    "confidence": confidence,
                })
                await asyncio.sleep(1)
                continue

            # 5) map Polymarket alpha -> execution router
            if action == "buy_yes":
                side = "buy"
            elif action == "buy_no":
                side = "sell"
            else:
                logs.append({
                    "loop": i,
                    "stage": "decision",
                    "error": f"unsupported action: {action}",
                })
                await asyncio.sleep(1)
                continue

            result = await _call("route_order", {
                "target": "polymarket",
                "side": side,
                "symbol": asset_id,
                "amount": size,
            })

            logs.append({
                "loop": i,
                "stage": "execution",
                "score": combined_score,
                "confidence": confidence,
                "action": action,
                "size": size,
                "result": result,
            })

            # 6) risk accounting placeholder
            await _call("check_risk", {"pnl": 0.0})

        except Exception as e:
            logs.append({"loop": i, "stage": "exception", "error": str(e)})

        await asyncio.sleep(1)

    return logs


async def stop_fund():
    global RUNNING
    RUNNING = False
    try:
        await _call("stop_polymarket_book", {})
    except Exception:
        pass
    return "stopped"
