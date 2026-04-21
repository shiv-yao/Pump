import json
import inspect
import importlib.util
from pathlib import Path

# ===== config =====
BASE_WEIGHT = 0.2
MAX_WEIGHT = 0.6
MIN_WEIGHT = 0.05

DD_PENALTY = 1.5
VOL_SCALE = 1.2

# ===== boost state =====
BOOST = {}


# ===== plugin loader =====
def _plugins_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "plugins"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent


def _load_tool(tool_name: str):
    plugins_root = _plugins_root()

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


# ===== helpers =====
def _volatility_score(stats):
    win = float(stats.get("winrate", 0))
    dd = float(stats.get("drawdown", 0))

    stability = win * 1.2 - dd * 0.8
    return max(0.1, stability)


def _score_strategy(stats):
    pnl = float(stats.get("pnl", 0))
    win = float(stats.get("winrate", 0))
    dd = float(stats.get("drawdown", 0))

    score = 0.0
    score += pnl * 0.4
    score += win * 2.0
    score -= dd * DD_PENALTY

    return max(0.0, score)


# ===== boost controls =====
def allocator_boost(strategy_id, factor=1.2):
    factor = float(factor)
    BOOST[strategy_id] = BOOST.get(strategy_id, 1.0) * factor
    return {
        "ok": True,
        "strategy_id": strategy_id,
        "boost": BOOST[strategy_id]
    }


def allocator_reset_boost(strategy_id=None):
    if strategy_id:
        BOOST.pop(strategy_id, None)
        return {"ok": True, "strategy_id": strategy_id, "boost": 1.0}

    BOOST.clear()
    return {"ok": True, "reset_all": True}


def allocator_get_boosts():
    return {"boosts": BOOST}


# ===== allocation map =====
async def allocator_get_allocation_map(capital=1000):
    rankings = await _call_tool("strategy_get_rankings", {})

    if not isinstance(rankings, list) or len(rankings) == 0:
        return {}

    scores = {}
    total_score = 0.0

    for sid, stats in rankings:
        s = _score_strategy(stats)

        vol = _volatility_score(stats)
        s *= vol * VOL_SCALE

        boost = BOOST.get(sid, 1.0)
        s *= boost

        scores[sid] = s
        total_score += s

    if total_score <= 0:
        n = len(scores)
        return {k: 1 / n for k in scores}

    weights = {}
    for sid, s in scores.items():
        w = s / total_score
        w = max(MIN_WEIGHT, min(MAX_WEIGHT, w))
        weights[sid] = w

    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    return weights


# ===== main allocation =====
async def allocator_get_budget(strategy_id, capital):
    capital = float(capital)

    weights = await allocator_get_allocation_map(capital=capital)

    if not weights or strategy_id not in weights:
        base_budget = capital * BASE_WEIGHT
        boost = BOOST.get(strategy_id, 1.0)
        budget = base_budget * boost
        budget = max(capital * MIN_WEIGHT, min(capital * MAX_WEIGHT, budget))

        return {
            "budget": budget,
            "weight": budget / capital if capital > 0 else 0.0,
            "boost": boost
        }

    w = float(weights[strategy_id])
    boost = BOOST.get(strategy_id, 1.0)

    budget = capital * w
    budget *= boost

    budget = max(capital * MIN_WEIGHT, min(capital * MAX_WEIGHT, budget))
    final_weight = budget / capital if capital > 0 else 0.0

    return {
        "budget": budget,
        "weight": final_weight,
        "boost": boost
    }
