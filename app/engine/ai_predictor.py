import math
from app.engine.utils import sf

# =========================================================
# SIMPLE ONLINE MODEL（輕量版）
# =========================================================
MODEL = {
    "w_breakout": 0.8,
    "w_momentum": 0.6,
    "w_smart": 0.7,
    "w_liq": 0.2,
    "w_wallet": 0.5,
    "bias": -0.2,
}


def _sigmoid(x):
    try:
        return 1 / (1 + math.exp(-x))
    except:
        return 0.5


# =========================================================
# FEATURE → PREDICTION
# =========================================================
def predict_trade_quality(f):
    breakout = sf(f.get("breakout", 0.0), 0.0)
    momentum = sf(f.get("momentum", 0.0), 0.0)
    smart = sf(f.get("smart", 0.0), 0.0)
    liq = sf(f.get("liq", 0.0), 0.0)
    wallet = sf(f.get("wallet_graph_score", 0.0), 0.0)

    # normalize
    liq_norm = min(liq / 100000, 1.0)

    score = (
        breakout * MODEL["w_breakout"]
        + momentum * MODEL["w_momentum"]
        + smart * MODEL["w_smart"]
        + liq_norm * MODEL["w_liq"]
        + wallet * MODEL["w_wallet"]
        + MODEL["bias"]
    )

    win_prob = _sigmoid(score)

    # 預測 pnl（簡化）
    expected_pnl = (
        breakout * 0.4
        + momentum * 0.3
        + smart * 0.3
    )

    return {
        "win_prob": win_prob,
        "expected_pnl": expected_pnl,
        "score": score,
    }
