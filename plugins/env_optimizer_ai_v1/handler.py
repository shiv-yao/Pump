import json
import math
import os
import random
from pathlib import Path


ENV_PATH = Path("latest.env")


# ===== tunable search space =====
PARAM_SPACE = {
    "ENTRY_THRESHOLD": [0.50, 0.55, 0.60, 0.65, 0.70],
    "MAX_POSITION_PER_TRADE": [0.02, 0.03, 0.05, 0.07],
    "MAX_TOTAL_EXPOSURE": [0.20, 0.30, 0.40, 0.50],
    "ALPHA_WEIGHT_WALLET": [0.50, 0.70, 0.90, 1.10],
    "ALPHA_WEIGHT_ORDERBOOK": [0.30, 0.50, 0.70, 0.90],
    "RISK_SCALE": [0.50, 0.70, 0.90, 1.00, 1.10],
    "ALLOCATOR_MAX_WEIGHT": [0.40, 0.50, 0.60],
    "CORRELATION_PENALTY": [0.50, 0.70, 0.85],
    "BASE_SIZE": [0.01, 0.02, 0.03]
}


# ===== helpers =====
def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _get_recent_trades(sample_size=100):
    """
    Reads recent trades from execution_engine_v7.
    This assumes your runtime imports plugins as modules from disk.
    """
    try:
        root = Path(__file__).resolve()
        plugins_dir = None
        for p in root.parents:
            if (p / "plugins").exists():
                plugins_dir = p / "plugins"
                break

        if not plugins_dir:
            return []

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


def _calc_stats(trades):
    if not trades:
        return {
            "count": 0,
            "pnl": 0.0,
            "winrate": 0.0,
            "max_drawdown": 0.0,
            "avg_pnl": 0.0,
            "volatility": 0.0,
        }

    pnls = [_safe_float(t.get("pnl_delta", 0.0)) for t in trades]
    pnl = sum(pnls)
    count = len(pnls)
    avg_pnl = pnl / count if count else 0.0
    wins = sum(1 for x in pnls if x > 0)
    winrate = wins / count if count else 0.0

    # equity curve / drawdown
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    eq_curve = []
    for x in pnls:
        eq += x
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
        eq_curve.append(eq)

    # naive volatility proxy
    if count > 1:
        mean = avg_pnl
        var = sum((x - mean) ** 2 for x in pnls) / count
        vol = math.sqrt(var)
    else:
        vol = 0.0

    return {
        "count": count,
        "pnl": pnl,
        "winrate": winrate,
        "max_drawdown": max_dd,
        "avg_pnl": avg_pnl,
        "volatility": vol,
        "equity_curve": eq_curve,
    }


def _score_config(stats, cfg):
    """
    Conservative scoring:
    reward pnl + winrate
    penalize drawdown + volatility
    lightly bias toward safer configs
    """
    pnl = _safe_float(stats.get("pnl", 0.0))
    winrate = _safe_float(stats.get("winrate", 0.0))
    drawdown = _safe_float(stats.get("max_drawdown", 0.0))
    volatility = _safe_float(stats.get("volatility", 0.0))

    # base performance score
    score = 0.0
    score += pnl * 1.0
    score += winrate * 50.0
    score -= drawdown * 2.0
    score -= volatility * 5.0

    # safety bonuses / penalties
    if _safe_float(cfg.get("MAX_TOTAL_EXPOSURE", 0.3)) <= 0.30:
        score += 2.0
    if _safe_float(cfg.get("MAX_POSITION_PER_TRADE", 0.05)) <= 0.05:
        score += 2.0
    if _safe_float(cfg.get("RISK_SCALE", 1.0)) > 1.0 and drawdown > 0:
        score -= 3.0

    # encourage stronger wallet alpha when winrate is already decent
    wallet_w = _safe_float(cfg.get("ALPHA_WEIGHT_WALLET", 0.7))
    if winrate > 0.5:
        score += wallet_w * 2.0

    return score


def _sample_configs(n=30):
    out = []
    for _ in range(n):
        cfg = {}
        for k, values in PARAM_SPACE.items():
            cfg[k] = random.choice(values)
        out.append(cfg)
    return out


def _to_env_text(cfg):
    ordered = [
        "ENTRY_THRESHOLD",
        "MAX_POSITION_PER_TRADE",
        "MAX_TOTAL_EXPOSURE",
        "ALPHA_WEIGHT_WALLET",
        "ALPHA_WEIGHT_ORDERBOOK",
        "RISK_SCALE",
        "ALLOCATOR_MAX_WEIGHT",
        "CORRELATION_PENALTY",
        "BASE_SIZE",
    ]
    lines = []
    for k in ordered:
        if k in cfg:
            lines.append(f"{k}={cfg[k]}")
    return "\n".join(lines) + "\n"


# ===== public tools =====
async def auto_optimize_env(sample_size=100, num_candidates=30):
    sample_size = int(sample_size)
    num_candidates = int(num_candidates)

    trades = _get_recent_trades(sample_size=sample_size)
    if not trades:
        return {"error": "no trades found in execution_engine_v7"}

    stats = _calc_stats(trades)
    candidates = _sample_configs(n=max(5, num_candidates))

    best_score = -10**18
    best_cfg = None

    for cfg in candidates:
        s = _score_config(stats, cfg)

        # light exploration noise to avoid ties / identical plateau
        s += random.uniform(-1.0, 1.0)

        if s > best_score:
            best_score = s
            best_cfg = cfg

    if not best_cfg:
        return {"error": "no config selected"}

    env_text = _to_env_text(best_cfg)
    ENV_PATH.write_text(env_text, encoding="utf-8")

    return {
        "best_score": round(best_score, 4),
        "config": best_cfg,
        "stats": {
            "count": stats["count"],
            "pnl": round(stats["pnl"], 6),
            "winrate": round(stats["winrate"], 4),
            "max_drawdown": round(stats["max_drawdown"], 6),
            "avg_pnl": round(stats["avg_pnl"], 6),
            "volatility": round(stats["volatility"], 6),
        },
        "saved_to": str(ENV_PATH),
        "env_preview": env_text
    }


async def apply_best_env():
    if not ENV_PATH.exists():
        return {"error": "latest.env not found"}

    content = ENV_PATH.read_text(encoding="utf-8")

    # safe "apply" for now:
    # parse file and return key-values
    # real hot-reload can be connected later to your config loader
    applied = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        applied[k.strip()] = v.strip()

    return {
        "applied": True,
        "env": content,
        "parsed": applied,
        "message": "latest.env parsed successfully; connect this to your runtime reload if needed"
    }
