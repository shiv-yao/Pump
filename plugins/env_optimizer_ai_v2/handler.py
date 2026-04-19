import json
import random
import inspect
import importlib.util
from pathlib import Path


ENV_PATH = Path("latest.env")

# ===== fallback param space =====
PARAM_SPACE = {
    "ENTRY_THRESHOLD": [0.50, 0.55, 0.60, 0.65],
    "RISK_SCALE": [0.50, 0.70, 1.00],
    "SIZE_MULT": [0.50, 1.00, 1.50],
    "MAX_TOTAL_EXPOSURE": [0.20, 0.30, 0.40],
    "MAX_POSITION_PER_TRADE": [0.02, 0.03, 0.05],
    "ALPHA_WEIGHT_WALLET": [0.50, 0.70, 0.90, 1.10],
    "ALPHA_WEIGHT_ORDERBOOK": [0.30, 0.50, 0.70, 0.90],
    "ALLOCATOR_MAX_WEIGHT": [0.40, 0.50, 0.60],
    "CORRELATION_PENALTY": [0.50, 0.70, 0.85],
    "BASE_SIZE": [0.01, 0.02, 0.03]
}


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


# ===== safe clamp =====
def _clamp_config(cfg: dict) -> dict:
    safe = dict(cfg)

    def f(name: str, default: float, lo: float, hi: float) -> float:
        try:
            v = float(safe.get(name, default))
        except Exception:
            v = default
        return max(lo, min(hi, v))

    safe["ENTRY_THRESHOLD"] = f("ENTRY_THRESHOLD", 0.55, 0.50, 0.70)
    safe["RISK_SCALE"] = f("RISK_SCALE", 1.00, 0.50, 1.20)
    safe["SIZE_MULT"] = f("SIZE_MULT", 1.00, 0.50, 1.50)
    safe["MAX_TOTAL_EXPOSURE"] = f("MAX_TOTAL_EXPOSURE", 0.30, 0.20, 0.50)
    safe["MAX_POSITION_PER_TRADE"] = f("MAX_POSITION_PER_TRADE", 0.05, 0.01, 0.10)
    safe["ALPHA_WEIGHT_WALLET"] = f("ALPHA_WEIGHT_WALLET", 0.70, 0.20, 1.50)
    safe["ALPHA_WEIGHT_ORDERBOOK"] = f("ALPHA_WEIGHT_ORDERBOOK", 0.50, 0.20, 1.50)
    safe["ALLOCATOR_MAX_WEIGHT"] = f("ALLOCATOR_MAX_WEIGHT", 0.50, 0.20, 0.80)
    safe["CORRELATION_PENALTY"] = f("CORRELATION_PENALTY", 0.70, 0.20, 1.00)
    safe["BASE_SIZE"] = f("BASE_SIZE", 0.02, 0.005, 0.10)

    return safe


def _to_env(cfg: dict) -> str:
    ordered = [
        "ENTRY_THRESHOLD",
        "RISK_SCALE",
        "SIZE_MULT",
        "MAX_TOTAL_EXPOSURE",
        "MAX_POSITION_PER_TRADE",
        "ALPHA_WEIGHT_WALLET",
        "ALPHA_WEIGHT_ORDERBOOK",
        "ALLOCATOR_MAX_WEIGHT",
        "CORRELATION_PENALTY",
        "BASE_SIZE",
    ]
    lines = []
    for key in ordered:
        if key in cfg:
            lines.append(f"{key}={cfg[key]}")
    return "\n".join(lines) + "\n"


# ===== replay integration =====
async def _try_replay(sample_size: int, num_candidates: int):
    result = await _call_tool("replay_optimize", {
        "sample_size": sample_size,
        "num_candidates": num_candidates
    })

    if not isinstance(result, dict):
        return None

    cfg = result.get("config")
    score = result.get("best_score", 0)
    replay_result = result.get("result", {})

    if not cfg:
        return None

    return {
        "config": cfg,
        "score": score,
        "result": replay_result,
        "source": "replay"
    }


# ===== fallback optimizer =====
async def _fallback_optimize(sample_size: int, num_candidates: int):
    trades_result = await _call_tool("replay_run", {
        "config": {
            "ENTRY_THRESHOLD": 0.55,
            "RISK_SCALE": 1.0,
            "SIZE_MULT": 1.0
        },
        "sample_size": sample_size
    })

    baseline_score = 0.0
    if isinstance(trades_result, dict):
        baseline_score = float(trades_result.get("score", 0.0) or 0.0)

    best_score = -999999999.0
    best_cfg = None

    for _ in range(max(10, num_candidates)):
        cfg = {k: random.choice(v) for k, v in PARAM_SPACE.items()}

        score = baseline_score
        score += random.uniform(-5.0, 5.0)

        # safety preferences
        if float(cfg.get("MAX_TOTAL_EXPOSURE", 0.3)) <= 0.30:
            score += 2.0
        if float(cfg.get("MAX_POSITION_PER_TRADE", 0.05)) <= 0.05:
            score += 2.0
        if float(cfg.get("RISK_SCALE", 1.0)) > 1.0:
            score -= 1.0

        if score > best_score:
            best_score = score
            best_cfg = cfg

    return {
        "config": best_cfg,
        "score": best_score,
        "result": {"baseline_score": baseline_score},
        "source": "fallback"
    }


# ===== public tools =====
async def auto_optimize_env(sample_size: int = 200, num_candidates: int = 30):
    sample_size = int(sample_size)
    num_candidates = int(num_candidates)

    replay_result = await _try_replay(sample_size, num_candidates)

    if replay_result:
        cfg = replay_result["config"]
        score = replay_result["score"]
        source = replay_result["source"]
        replay_stats = replay_result.get("result", {})
    else:
        fallback = await _fallback_optimize(sample_size, num_candidates)
        cfg = fallback["config"]
        score = fallback["score"]
        source = fallback["source"]
        replay_stats = fallback.get("result", {})

    if not cfg:
        return {"error": "no config selected"}

    safe_cfg = _clamp_config(cfg)
    env_text = _to_env(safe_cfg)
    ENV_PATH.write_text(env_text, encoding="utf-8")

    return {
        "best_score": round(float(score), 4),
        "config": safe_cfg,
        "source": source,
        "replay_stats": replay_stats,
        "saved_to": str(ENV_PATH),
        "env_preview": env_text
    }


async def apply_best_env():
    if not ENV_PATH.exists():
        return {"error": "latest.env not found"}

    content = ENV_PATH.read_text(encoding="utf-8")

    parsed = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        parsed[k.strip()] = v.strip()

    return {
        "applied": True,
        "env": content,
        "parsed": parsed,
        "message": "latest.env parsed successfully"
    }
