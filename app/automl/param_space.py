import random

def sample_params():
    return {
        "MIN_SCORE": random.uniform(0.55, 0.75),
        "MAX_SIZE": random.uniform(0.03, 0.07),
        "SNIPER_MIN_SCORE": random.uniform(0.65, 0.85),
        "EARLY_ENTRY_FRAC": random.uniform(0.003, 0.01),
        "WALLET_WEIGHT": random.uniform(0.3, 0.7),
    }
