# app/engine/main.py

import asyncio
import time

from app.state import engine

# =========================
# SAFE IMPORT（避免炸）
# =========================
try:
    from app.engine.fund import update_fund_allocator
except:
    def update_fund_allocator(*args, **kwargs):
        pass

try:
    from app.engine.agent import agent_update, agent_adjust_params
except:
    def agent_update(): pass
    def agent_adjust_params(): pass

try:
    from app.engine.execution import execute_portfolio
except:
    async def execute_portfolio(*args, **kwargs):
        return False

try:
    from app.engine.features import fetch_alpha_candidates
except:
    async def fetch_alpha_candidates():
        return []

try:
    from app.engine.risk import check_sell
except:
    async def check_sell(p):
        return False

try:
    from app.engine.state_runtime import update_runtime_stats
except:
    def update_runtime_stats():
        pass


# =========================
# INIT
# =========================
async def start_once():
    engine.running = True

    if not hasattr(engine, "positions"):
        engine.positions = []

    if not hasattr(engine, "capital"):
        engine.capital = 5.0

    if not hasattr(engine, "stats"):
        engine.stats = {
            "executed": 0,
            "wins": 0,
            "losses": 0,
            "trades": 0,
        }

    update_fund_allocator(force=True)


# =========================
# MAIN LOOP
# =========================
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

            # ================= FETCH =================
            tokens = await fetch_alpha_candidates()

            if not isinstance(tokens, list):
                tokens = []

            # ================= SELL =================
            for p in list(engine.positions):
                try:
                    await check_sell(p)
                except Exception as e:
                    print("SELL ERROR:", e)

            # ================= BUY =================
            traded = False
            try:
                traded = await execute_portfolio(tokens)
            except Exception as e:
                print("EXEC ERROR:", e)

            # ================= STATS =================
            try:
                update_runtime_stats()
            except Exception as e:
                print("STATS ERROR:", e)

            # ================= DEBUG =================
            print(
                f"LOOP | capital={engine.capital:.4f} "
                f"positions={len(engine.positions)} "
                f"traded={traded}"
            )

        except Exception as e:
            print("ENGINE LOOP ERROR:", e)

        await asyncio.sleep(2)
