
import asyncio
from core.alpha import compute_alpha, position_size
from core.pnl import Tracker
from core.config import *

pnl_tracker = Tracker()
positions = []

async def run():
    print("🔥 V500 PRO LIVE")

    while True:
        if pnl_tracker.realized < MAX_DAILY_LOSS:
            print("🛑 DAILY STOP")
            await asyncio.sleep(10)
            continue

        tokens = ["TOKEN1","TOKEN2","TOKEN3"]

        for mint in tokens:
            if len(positions) >= MAX_POSITIONS:
                break

            strength = 0.01
            liq = 80000
            impact = 0.1

            if liq < 50000 or impact > 0.15:
                continue

            alpha = compute_alpha(strength, liq, impact)

            if alpha < MIN_ALPHA:
                continue

            size = position_size(alpha)
            if size == 0:
                continue

            print(f"⚡ {mint} alpha={alpha:.2f} size={size}")

            pnl = pnl_tracker.record(0.02)
            positions.append(mint)

            print("✅ TRADE", mint, "PNL", pnl)

        await asyncio.sleep(3)
