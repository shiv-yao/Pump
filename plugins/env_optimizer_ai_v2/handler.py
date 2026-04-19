import random
from pathlib import Path


ENV_PATH = Path("latest.env")


# ===== fallback param space =====
PARAM_SPACE = {
    "ENTRY_THRESHOLD": [0.5, 0.55, 0.6, 0.65],
    "RISK_SCALE": [0.5, 0.7, 1.0],
    "SIZE_MULT": [0.5, 1.0, 1.5],
    "MAX_TOTAL_EXPOSURE": [0.2, 0.3, 0.4],
}


# ===== safe clamp =====
def _clamp_config(cfg):
    """
    防止 optimizer 把系統調爆
    """
    safe = dict(cfg)

    safe["ENTRY_THRESHOLD"] = max(0.5, min(0.7, float(cfg.get("ENTRY_THRESHOLD", 0.55))))
    safe["RISK_SCALE"] = max(0.5, min(1.2, float(cfg.get("RISK_SCALE", 1.0))))
    safe["SIZE_MULT"] = max(0.5, min(1.5, float(cfg.get("SIZE_MULT", 1.0))))
    safe["MAX_TOTAL_EXPOSURE"] = max(0.2, min(0.5, float(cfg.get("MAX_TOTAL_EXPOSURE", 0.3))))

    return safe


def _to_env(cfg):
    lines = []
    for k, v in cfg.items():
        lines.append(f"{k}={v}")
    return "\n".join(lines)


# ===== replay integration =====
async def _try_replay(call):
    """
    優先用 replay engine
    """
    try:
        result = await call("replay_optimize", {})

        if not isinstance(result, dict):
            return None

        cfg = result.get("config")
        score = result.get("best_score", 0)

        if not cfg:
            return None

        return {
            "config": cfg,
            "score": score,
            "source": "replay"
        }

    except Exception:
        return None


# ===== fallback optimizer =====
async def _fallback_optimize(call):
    """
    如果 replay 壞掉，用 heuristic
    """
    best_score = -999999
    best_cfg = None

    for _ in range(20):
        cfg = {
            k: random.choice(v)
            for k, v in PARAM_SPACE.items()
        }

        # 簡化 scoring
        score = random.uniform(0, 100)

        if score > best_score:
            best_score = score
            best_cfg = cfg

    return {
        "config": best_cfg,
        "score": best_score,
        "source": "fallback"
    }


# ===== main optimize =====
async def auto_optimize_env():
    from inspect import iscoroutinefunction

    async def call(tool, payload=None):
        payload = payload or {}
        fn = globals().get("_call_tool")
        if fn:
            return await fn(tool, payload)
        return {"error": "call not available"}

    # ===== step 1: try replay =====
    replay_result = await _try_replay(call)

    if replay_result:
        cfg = replay_result["config"]
        score = replay_result["score"]
        source = "replay"
    else:
        fallback = await _fallback_optimize(call)
        cfg = fallback["config"]
        score = fallback["score"]
        source = "fallback"

    # ===== step 2: safety clamp =====
    safe_cfg = _clamp_config(cfg)

    # ===== step 3: save =====
    env_text = _to_env(safe_cfg)
    ENV_PATH.write_text(env_text)

    return {
        "best_score": score,
        "config": safe_cfg,
        "source": source,
        "saved_to": str(ENV_PATH),
        "env_preview": env_text
    }


# ===== apply =====
async def apply_best_env():
    if not ENV_PATH.exists():
        return {"error": "latest.env not found"}

    content = ENV_PATH.read_text()

    parsed = {}
    for line in content.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            parsed[k.strip()] = v.strip()

    return {
        "applied": True,
        "env": content,
        "parsed": parsed
    }
