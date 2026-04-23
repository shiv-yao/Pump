import math

def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def predict(features):
    # ===== 簡化版（你之後可換 XGBoost / NN）=====
    score = (
        0.4 * features.get("momentum", 0) +
        0.3 * features.get("wallet_score", 0) +
        0.2 * features.get("volume", 0) +
        0.1 * features.get("liquidity", 0)
    )

    prob = sigmoid(score)

    return {
        "score": prob,
        "action": "buy" if prob > 0.6 else "hold"
    }
