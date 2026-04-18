import asyncio
import random
import time

RUNNING = False

async def arb_loop():
    global RUNNING

    while RUNNING:
        # 模擬抓 BTC 外部預測
        external_price = 100000 + random.uniform(-200, 200)

        # 模擬 Polymarket 價格
        market_price = 100000 + random.uniform(-200, 200)

        spread = (external_price - market_price) / market_price

        if abs(spread) > 0.003:
            print(f"[ARB SIGNAL] spread={spread:.4f}")

        await asyncio.sleep(1)


async def start_arb_bot():
    global RUNNING
    if RUNNING:
        return "Already running"

    RUNNING = True
    asyncio.create_task(arb_loop())

    return "Arbitrage bot started"


async def stop_arb_bot():
    global RUNNING
    RUNNING = False
    return "Stopped"


async def arb_status():
    return f"RUNNING={RUNNING}"
