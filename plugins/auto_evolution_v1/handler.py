import json
import inspect
import importlib.util
import time
from pathlib import Path


STATE = {
    "last_run": 0,
    "cycles": 0,
    "last_result": {}
}


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


def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


# ===== strategy evaluation =====
async def evaluate_strategies():
    stats = await _call_tool("strategy_get_stats", {})

    if not isinstance(stats, dict):
        return {}

    decisions = {}

    for sid, s in stats.items():
        pnl = _safe_float(s.get("pnl", 0))
        winrate = _safe_float(s.get("winrate", 0))
        dd = _safe_float(s.get("drawdown", 0))
        trades = _safe_int(s.get("trades", 0))
        enabled = bool(s.get("enabled", True))

        decision = "keep"
        reason = "stable"

        # ===== disable =====
        if trades > 20 and winrate < 0.35:
            decision = "disable"
            reason = "low winrate"

        if trades > 20 and pnl < 0 and dd > abs(pnl) * 0.8:
            decision = "disable"
            reason = "high drawdown"

        # ===== boost =====
        if trades > 10 and winrate > 0.60 and pnl > 0:
            decision = "boost"
            reason = "strong strategy"

        decisions[sid] = {
            "decision": decision,
            "reason": reason,
            "enabled": enabled,
            "pnl": pnl,
            "winrate": winrate,
            "drawdown": dd,
            "trades": trades
        }

    return decisions


# ===== apply controls =====
async def apply_strategy_controls(decisions):
    results = {}

    for sid, d in decisions.items():
        action = d["decision"]

        if action == "disable":
            res = await _call_tool("strategy_disable", {"strategy_id": sid})
            results[sid] = {
                "action": "disabled",
                "result": res
            }

        elif action == "boost":
            res = await _call_tool("allocator_boost", {
                "strategy_id": sid,
                "factor": 1.5
            })
            results[sid] = {
                "action": "boosted",
                "result": res
            }

        else:
            results[sid] = {
                "action": "keep",
                "result": {"ok": True}
            }

    return results


# ===== env evolution =====
async def evolve_env():
    replay = await _call_tool("replay_run", {})
    optimizer = await _call_tool("auto_optimize_env", {})
    applied = await _call_tool("apply_best_env", {})

    return {
        "replay": replay,
        "optimizer": optimizer,
        "applied": applied
    }


# ===== main cycle =====
async def run_evolution_cycle():
    global STATE

    decisions = await evaluate_strategies()
    controls = await apply_strategy_controls(decisions)
    env = await evolve_env()

    STATE["last_run"] = time.time()
    STATE["cycles"] += 1
    STATE["last_result"] = {
        "decisions": decisions,
        "controls": controls,
        "env": env
    }

    return STATE["last_result"]


def evolution_status():
    return STATE
