import importlib.util
import inspect
import json
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


async def run_portfolio_v1(
    asset_id: str,
    capital: float,
    orderbook_score: float = 0.0,
    wallet_score: float = 0.0
):
    regime_res = await _call_tool("fb_get_regime", {"asset_id": asset_id})
    regime = regime_res.get("regime", "neutral") if isinstance(regime_res, dict) else "neutral"

    fused = await _call_tool("fuse_alpha", {
        "alpha_inputs": {
            "orderbook": float(orderbook_score),
            "wallet": float(wallet_score),
            "momentum": float(orderbook_score) * 0.5
        }
    })

    if not isinstance(fused, dict) or "error" in fused:
        return {"action": "hold", "size": 0.0, "reason": "fuse_alpha_failed"}

    decision = fused.get("decision", "hold")
    fused_score = float(fused.get("score", 0.0))

    alloc = await _call_tool("allocate_capital_v1", {
        "strategies": {
            "trend": {"pnl": 1.0 if regime == "trend" else 0.3, "winrate": 0.60 if regime == "trend" else 0.48},
            "mean": {"pnl": 0.8 if regime == "mean" else 0.2, "winrate": 0.55 if regime == "mean" else 0.45},
            "chop": {"pnl": 0.4 if regime == "chop" else 0.1, "winrate": 0.50 if regime == "chop" else 0.40}
        },
        "capital": float(capital)
    })

    allocations = alloc.get("allocations", {}) if isinstance(alloc, dict) else {}
    regime_capital = float(allocations.get(regime, capital * 0.1))

    size_pct = await _call_tool("fb_position_size", {
        "score": fused_score,
        "regime": regime
    })

    try:
        size_pct = float(size_pct)
    except Exception:
        size_pct = 0.01

    size = regime_capital * size_pct

    return {
        "action": decision,
        "size": size,
        "score": fused_score,
        "regime": regime,
        "allocations": allocations
    }
