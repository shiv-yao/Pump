import random
from app.utils.loader import call
from app.automl.param_space import sample_params
from app.automl.env_writer import apply_env


NUM_CANDIDATES = 20
SAMPLE_SIZE = 200


async def evaluate(params):
    # 👉 套參數（暫時覆蓋）
    for k, v in params.items():
        globals()[k] = v

    # 👉 replay 測試
    result = await call("replay_run", {
        "sample_size": SAMPLE_SIZE
    })

    if not isinstance(result, dict):
        return -999

    pnl = float(result.get("pnl", 0))
    winrate = float(result.get("winrate", 0))

    # 👉 scoring function（關鍵）
    score = pnl * 0.7 + winrate * 0.3

    return score


async def run_automl():
    best_score = -999
    best_params = None

    for i in range(NUM_CANDIDATES):
        params = sample_params()

        score = await evaluate(params)

        print(f"AutoML {i}: score={score:.4f}", params)

        if score > best_score:
            best_score = score
            best_params = params

    if best_params:
        apply_env(best_params)

    return {
        "best_score": best_score,
        "best_params": best_params
    }
