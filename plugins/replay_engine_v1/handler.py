import json
import random
import inspect
import importlib.util
from pathlib import Path


# ===== param space =====
PARAM_SPACE = {
    "ENTRY_THRESHOLD": [0.50, 0.55, 0.60, 0.65],
    "RISK_SCALE": [0.50, 0.70, 1.00],
    "SIZE_MULT": [0.50, 1.00, 1.50],
}


# ===== plugin tool loader =====
def _plugins_root() -> Path:
    cur = Path(__file__).resolve()
    for p in cur.parents:
        if (p / "plugins").exists():
            return p / "plugins"
    return Path(__file__).resolve().parent.parent


def _load_tool(tool_name: str):
    plugins_root = _plugins_root()

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


# ===== data loader =====
def _load_recent_trades(sample_size=200):
    """
    Reads recent trades from execution_engine_v7 source file namespace.
    """
    try:
        plugins_dir = _plugins_root()
        engine_file = plugins_dir / "execution_engine_v7" / "handler.py"
        if not engine_file.exists():
            return []

        namespace = {}
        code = engine_file.read_text(encoding="utf-8")
        exec(code, namespace, namespace)

        trades = namespace.get("TRADES", [])
        if not isinstance(trades, list):
            return []

        return trades[-sample_size:]
    except Exception:
        return []


# ===== synthetic book builder =====
def _build_synthetic_book(trade):
    """
    Build a simple book around the trade price.
    This is a v1 approximation for replay.
    """
    price = float(trade.get("price", 0.5) or 0.5)
    size = float(trade.get("size", 1.0) or 1.0)

    spread = max(0.01, price * 0.01)

    best_bid = max(0.0001, price - spread / 2)
    best_ask = price + spread / 2

    bids = [
        {"price": round(best_bid, 6), "size": max(1.0, size * 2)},
        {"price": round(best_bid * 0.995, 6), "size": max(1.0, size * 3)},
        {"price": round(best_bid * 0.990, 6), "size": max(1.0, size * 5)},
    ]

    asks = [
        {"price": round(best_ask, 6), "size": max(1.0, size * 2)},
        {"price": round(best_ask * 1.005, 6), "size": max(1.0, size * 3)},
        {"price": round(best_ask * 1.010, 6), "size": max(1.0, size * 5)},
    ]

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "bids": bids,
        "asks": asks,
    }


# ===== core replay =====
async def _replay_once(trades, cfg):
    pnl = 0.0
    wins = 0
    losses = 0

    eq = 0.0
    peak = 0.0
    max_dd = 0.0

    executed = 0
    skipped = 0

    entry_threshold = float(cfg.get("ENTRY_THRESHOLD", 0.55))
    risk_scale = float(cfg.get("RISK_SCALE", 1.0))
    size_mult = float(cfg.get("SIZE_MULT", 1.0))

    for t in trades:
        # v1 signal proxy:
        # use original pnl sign to derive a synthetic confidence band
        base_pnl = float(t.get("pnl_delta", 0.0))
        score = 0.60 if base_pnl > 0 else 0.45

        if score < entry_threshold:
            skipped += 1
            continue

        asset_id = str(t.get("asset_id", "UNKNOWN"))
        side = str(t.get("side", "buy")).lower()
        size = max(0.0001, float(t.get("size", 1.0)) * size_mult)

        book = _build_synthetic_book(t)

        sim = await _call_tool("simulate_fill", {
            "asset_id": asset_id,
            "side": side,
            "size": size,
            "book": book
        })

        if not isinstance(sim, dict) or not sim.get("filled"):
            skipped += 1
            continue

        executed += 1

        # v1 approximation:
        # use simulated avg price + fee, but retain trade directionality from historical pnl
        sim_fee = float(sim.get("fee", 0.0))
        sim_fill_size = float(sim.get("size", size))

        pnl_delta = base_pnl * risk_scale * (sim_fill_size / max(size, 1e-9))
        pnl_delta -= sim_fee

        pnl += pnl_delta

        if pnl_delta > 0:
            wins += 1
        else:
            losses += 1

        eq += pnl_delta
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    n = wins + losses
    winrate = wins / n if n else 0.0

    return {
        "pnl": pnl,
        "winrate": winrate,
        "drawdown": max_dd,
        "executed": executed,
        "skipped": skipped
    }


def _score_result(r):
    return (
        float(r.get("pnl", 0.0)) * 1.0
        + float(r.get("winrate", 0.0)) * 50.0
        - float(r.get("drawdown", 0.0)) * 2.0
    )


# ===== public tools =====
async def replay_run(config=None, sample_size=200):
    trades = _load_recent_trades(sample_size=int(sample_size))

    if not trades:
        return {"error": "no trades"}

    if not config:
        config = {
            "ENTRY_THRESHOLD": 0.55,
            "RISK_SCALE": 1.0,
            "SIZE_MULT": 1.0
        }

    result = await _replay_once(trades, config)

    return {
        "config": config,
        "result": result,
        "score": _score_result(result)
    }


async def replay_optimize(sample_size=200, num_candidates=30):
    trades = _load_recent_trades(sample_size=int(sample_size))

    if not trades:
        return {"error": "no trades"}

    best_score = -999999999.0
    best_cfg = None
    best_result = None

    num_candidates = max(5, int(num_candidates))

    for _ in range(num_candidates):
        cfg = {
            k: random.choice(v)
            for k, v in PARAM_SPACE.items()
        }

        result = await _replay_once(trades, cfg)
        s = _score_result(result)

        if s > best_score:
            best_score = s
            best_cfg = cfg
            best_result = result

    return {
        "best_score": best_score,
        "config": best_cfg,
        "result": best_result
    }
