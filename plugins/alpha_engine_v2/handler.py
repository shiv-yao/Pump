import asyncio
import random

async def get_alpha_signal(symbol: str = "BTCUSDT"):
    # 模擬多來源（你之後替換成真資料）
    momentum = random.uniform(-1, 1)
    flow = random.uniform(-1, 1)
    onchain = random.uniform(-1, 1)

    score = (
        momentum * 0.4 +
        flow * 0.3 +
        onchain * 0.3
    )

    return {
        "symbol": symbol,
        "score": score,
        "components": {
            "momentum": momentum,
            "flow": flow,
            "onchain": onchain
        }
    }
