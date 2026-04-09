# app/engine/main.py

import asyncio
import time
from app.state import engine

from app.engine.fund import update_fund_allocator
from app.engine.agent import agent_update, agent_adjust_params
from app.engine.execution import execute_portfolio
from app.engine.features import fetch_alpha_candidates
from app.engine.risk import check_sell
from app.engine.state_runtime import update_runtime_stats


async def start_once():
    engine.running = True
    update_fund_allocator(force=True)


async def main_loop():
    await start_once()

    print("🔥 V74 TRUE FUSION GOD MODE START")

    while engine.running:
        try:
            # ================= AI =================
            agent_update()
            agent_adjust_params()

            # ================= FUND =================
            update_fund_allocator()

            # ================= DATA =================
            tokens = await fetch_alpha_candidates()

            # ================= SELL =================
            for p in list(engine.positions):
                await check_sell(p)

            # ================= BUY =================
            await execute_portfolio(tokens)

            # ================= STATS =================
            update_runtime_stats()

        except Exception as e:
            print("ENGINE ERROR:", e)

        await asyncio.sleep(2)
