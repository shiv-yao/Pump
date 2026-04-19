import random
import math
from pathlib import Path


# ===== param space =====
PARAM_SPACE = {
    "ENTRY_THRESHOLD": [0.5, 0.55, 0.6, 0.65],
    "RISK_SCALE": [0.5, 0.7, 1.0],
    "SIZE_MULT": [0.5, 1.0, 1.5],
}


# ===== load trades =====
def load_trades():
    try:
        from execution_engine_v7 import handler as eng
        return eng.TRADES[-200:]
    except:
        return []


# ===== replay core =====
def replay_once(trades, cfg):
    pnl = 0
    wins = 0
    losses = 0

    eq = 0
    peak = 0
    max_dd = 0

    for t in trades:
        score = random.random()  # 模擬 signal score

        if score < cfg["ENTRY_THRESHOLD"]:
            continue

        pnl_delta = float(t.get("pnl_delta", 0))

        # ===== risk scaling =====
        pnl_delta *= cfg["RISK_SCALE"]

        # ===== position scaling =====
        pnl_delta *= cfg["SIZE_MULT"]

        pnl += pnl_delta

        if pnl_delta > 0:
            wins += 1
        else:
            losses += 1

        eq += pnl_delta
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    n = wins + losses
    winrate = wins / n if n else 0

    return {
        "pnl": pnl,
        "winrate": winrate,
        "drawdown": max_dd
    }


# ===== scoring =====
def score_result(r):
    return (
        r["pnl"] * 1.0 +
        r["winrate"] * 50 -
        r["drawdown"] * 2
    )


# ===== optimize =====
async def replay_optimize():
    trades = load_trades()

    if not trades:
        return {"error": "no trades"}

    best_score = -999999
    best_cfg = None
    best_result = None

    for _ in range(30):
        cfg = {
            k: random.choice(v)
            for k, v in PARAM_SPACE.items()
        }

        result = replay_once(trades, cfg)
        s = score_result(result)

        if s > best_score:
            best_score = s
            best_cfg = cfg
            best_result = result

    return {
        "best_score": best_score,
        "config": best_cfg,
        "result": best_result
    }


# ===== single run =====
async def replay_run(config=None):
    trades = load_trades()

    if not trades:
        return {"error": "no trades"}

    if not config:
        config = {
            "ENTRY_THRESHOLD": 0.55,
            "RISK_SCALE": 1.0,
            "SIZE_MULT": 1.0
        }

    result = replay_once(trades, config)

    return {
        "config": config,
        "result": result
    }
