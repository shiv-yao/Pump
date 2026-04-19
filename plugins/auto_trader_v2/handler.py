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


async def _call_tool(tool_name: str, payload: dict):
    fn = _load_tool(tool_name)
    if not fn:
        return {"error": f"tool not found: {tool_name}"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


async def run_fund(symbol: str, target: str = "solana", capital: float = 10.0, loops: int = 20):
    """
    symbol:
      - for solana target: mint or token symbol placeholder
      - for polymarket target: market/asset id placeholder
    target:
      - solana
      - polymarket
    loops:
      - how many iterations to run before returning
    """
    global RUNNING
    RUNNING = True

    logs = []

    for i in range(int(loops)):
        if not RUNNING:
            logs.append("stopped")
            break

        try:
            # 1. alpha
            alpha = await _call_tool("get_alpha_signal", {"symbol": "BTCUSDT"})
            if isinstance(alpha, str):
                try:
                    alpha = json.loads(alpha)
                except Exception:
                    alpha = {"error": alpha}

            if "error" in alpha:
                logs.append(f"[{i}] alpha error: {alpha}")
                await asyncio.sleep(1)
                continue

            score = float(alpha.get("score", 0))

            # normalize if some alpha plugin returns [-1, 1]
            if score < 0:
                score_for_decision = max(0.0, min(1.0, (score + 1) / 2))
            else:
                score_for_decision = max(0.0, min(1.0, score))

            # 2. risk
            can = await _call_tool("can_trade", {})
            if can is not True:
                logs.append(f"[{i}] risk blocked")
                await asyncio.sleep(1)
                continue

            # 3. decision
            action = await _call_tool("decide_trade", {"score": score_for_decision})
            if isinstance(action, dict):
                action = action.get("action", "hold")
            action = str(action).strip().lower()

            # 4. position size
            size = await _call_tool("position_size", {
                "score": score_for_decision,
                "capital": float(capital)
            })

            try:
                size = float(size)
            except Exception:
                size = float(capital) * 0.1

            # 5. hold -> skip
            if action == "hold":
                logs.append(f"[{i}] HOLD score={score_for_decision:.4f}")
                await asyncio.sleep(1)
                continue

            # 6. route order
            result = await _call_tool("route_order", {
                "target": target,
                "side": action,
                "symbol": symbol,
                "amount": size
            })

            logs.append({
                "loop": i,
                "score": score_for_decision,
                "action": action,
                "size": size,
                "result": result
            })

            # 7. optional risk update with pseudo pnl = 0 for now
            await _call_tool("check_risk", {"pnl": 0.0})

        except Exception as e:
            logs.append(f"[{i}] exception: {e}")

        await asyncio.sleep(1)

    return logs


async def stop_fund():
    global RUNNING
    RUNNING = False
    return "fund stopped"
