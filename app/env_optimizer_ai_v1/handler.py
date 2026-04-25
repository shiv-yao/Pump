import random
import json
from pathlib import Path

ENV_PATH = Path("latest.env")

# ===== 你要優化的參數 =====
PARAM_SPACE = {
    "ENTRY_THRESHOLD": [0.5, 0.55, 0.6, 0.65],
    "MAX_POSITION_PER_TRADE": [0.02, 0.03, 0.05],
    "MAX_TOTAL_EXPOSURE": [0.2, 0.3, 0.4],
    "ALPHA_WEIGHT_WALLET": [0.5, 0.7, 0.9],
    "ALPHA_WEIGHT_ORDERBOOK": [0.3, 0.5, 0.7]
}

# ===== 評分函數（核心）=====
def score_config(trades):
    if not trades:
        return -999

    pnl = sum(t["pnl_delta"] for t in trades)
    wins = sum(1 for t in trades if t["pnl_delta"] > 0)
    n = len(trades)

    winrate = wins / n if n else 0

    # drawdown
    eq = 0
    peak = 0
    max_dd = 0

    for t in trades:
        eq += t["pnl_delta"]
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    # 🔥 核心 scoring（像 hedge fund）
    score = (
        pnl * 1.0 +
        winrate * 50 -
        max_dd * 2
    )

    return score


# ===== 生成參數組合 =====
def sample_configs(n=20):
    configs = []

    for _ in range(n):
        c = {}
        for k, v in PARAM_SPACE.items():
            c[k] = random.choice(v)
        configs.append(c)

    return configs


# ===== 主優化 =====
async def auto_optimize_env():
    from importlib import import_module

    # 讀 trades（直接從 execution engine）
    engine = import_module("execution_engine_v7.handler")
    trades = engine.TRADES[-100:]  # 最近100筆

    if not trades:
        return {"error": "no trades"}

    candidates = sample_configs(30)

    best_score = -999999
    best_config = None

    for cfg in candidates:
        # ⚠️ 簡化：目前用同一 trades 評分（未來可做 replay）
        s = score_config(trades)

        # 加一點 random exploration
        s += random.uniform(-5, 5)

        if s > best_score:
            best_score = s
            best_config = cfg

    # 存檔
    text = "\n".join(f"{k}={v}" for k, v in best_config.items())
    ENV_PATH.write_text(text)

    return {
        "best_score": best_score,
        "config": best_config
    }


# ===== 套用 =====
async def apply_best_env():
    if not ENV_PATH.exists():
        return {"error": "no env file"}

    content = ENV_PATH.read_text()

    # 這裡你可以接 reload config
    # 例如 call("reload_config")

    return {
        "applied": True,
        "env": content
    }
