import json
import inspect
import importlib.util
from pathlib import Path


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

        spec = importlib.util.spec_from_file_location(f"plugin_{plugin_dir.name}", handler_path)
        if not spec or not spec.loader:
            continue

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool_name):
            return getattr(mod, tool_name)

    return None


async def _call_tool(tool_name: str, payload: dict):
    fn = _load_tool(tool_name)
    if not fn:
        return {"error": f"tool not found: {tool_name}"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


def _strategy_score(item: dict) -> float:
    pnl = float(item.get("pnl", 0.0))
    trades = int(item.get("trades", 0))
    winrate = float(item.get("winrate", 0.0))
    drawdown = float(item.get("drawdown", 0.0))
    enabled = bool(item.get("enabled", True))

    if not enabled:
        return 0.0

    # not enough data -> small starter weight
    if trades < 10:
        return 0.25

    # simple fund-style score
    # reward pnl + winrate, penalize dd
    score = 0.0
    score += max(0.0, pnl) * 0.30
    score += winrate * 1.20
    score -= drawdown * 0.80

    # if losing badly, strongly penalize
    if pnl < 0:
        score *= 0.5

    return max(0.0, score)


async def allocator_get_allocation_map(capital: float):
    capital = float(capital)

    stats = await _call_tool("strategy_get_stats", {})
    if not isinstance(stats, dict) or "error" in stats:
        return {"error": "strategy_get_stats failed", "raw": stats}

    scores = {}
    total_score = 0.0

    for strategy_id, item in stats.items():
        s = _strategy_score(item)
        scores[strategy_id] = s
        total_score += s

    allocations = {}

    if total_score <= 0:
        # equal tiny fallback for enabled strategies
        enabled = [k for k, v in stats.items() if bool(v.get("enabled", True))]
        if not enabled:
            return {"allocations": {}, "scores": scores}

        each = capital / len(enabled)
        for k in enabled:
            allocations[k] = each

        return {
            "allocations": allocations,
            "scores": scores
        }

    for strategy_id, s in scores.items():
        allocations[strategy_id] = capital * (s / total_score)

    return {
        "allocations": allocations,
        "scores": scores
    }


async def allocator_get_budget(strategy_id: str, capital: float):
    strategy_id = str(strategy_id)
    capital = float(capital)

    res = await allocator_get_allocation_map(capital=capital)
    if not isinstance(res, dict) or "allocations" not in res:
        return {"error": "allocation failed", "raw": res}

    return {
        "strategy_id": strategy_id,
        "budget": float(res["allocations"].get(strategy_id, 0.0)),
        "scores": res.get("scores", {})
    }
