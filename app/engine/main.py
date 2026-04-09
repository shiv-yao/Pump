import asyncio
import time

from app.state import engine
from app.engine import runtime as rt

# ===== SAFE IMPORT =====
from app.engine.features import fetch_alpha_candidates, process_candidates
from app.engine.execution import execute_ranked_portfolio
from app.engine.risk import check_sell
from app.engine.state_runtime import update_runtime_stats
from app.engine.metrics_runtime import update_metrics

from app.engine.ml_fund_brain import ml_adjust_allocator

# 👉 三策略
from app.engine.strategy_stable import run_stable_engine
from app.engine.strategy_sniper import run_sniper_engine


def _log(msg):
    print(msg)
    engine.logs.append(str(msg))
    engine.logs = engine.logs[-1000:]


async def main_loop():
    engine.running = True

    _log("🔥 V79 FINAL FUND SYSTEM START")

    while engine.running:
        traded = False

        try:
            # ================= FETCH =================
            tokens = await fetch_alpha_candidates()
            if not isinstance(tokens, list):
                tokens = []

            # ================= SELL =================
            for p in list(engine.positions):
                await check_sell(p)

            # ================= 三策略 =================
            stable_ranked = await run_stable_engine(tokens)
            sniper_ranked = await run_sniper_engine(tokens)
            momentum_ranked = await process_candidates(tokens)

            # ================= FUND BRAIN =================
            ml_adjust_allocator()
            alloc = getattr(rt, "FUND_ALLOCATOR", {
                "stable": 0.4,
                "sniper": 0.2,
                "momentum": 0.4,
            })

            # ================= EXECUTION =================
            traded_stable = await execute_ranked_portfolio(
                stable_ranked,
                strategy_name="stable",
                weight=alloc.get("stable", 0.4),
            )

            traded_sniper = await execute_ranked_portfolio(
                sniper_ranked,
                strategy_name="sniper",
                weight=alloc.get("sniper", 0.2),
            )

            traded_momentum = await execute_ranked_portfolio(
                momentum_ranked,
                strategy_name="momentum",
                weight=alloc.get("momentum", 0.4),
            )

            traded = traded_stable or traded_sniper or traded_momentum

            # ================= RUNTIME =================
            engine.last_loop_ts = time.time()
            engine.no_trade_cycles = 0 if traded else engine.no_trade_cycles + 1

            # ================= STATS =================
            update_runtime_stats()

            # ================= METRICS =================
            update_metrics()

            _log(
                f"LOOP | cap={engine.capital:.4f} pos={len(engine.positions)} "
                f"alloc={alloc} traded={traded}"
            )

        except Exception as e:
            engine.stats["errors"] += 1
            _log(f"ERROR: {e}")

        await asyncio.sleep(rt.LOOP_SLEEP_SEC)
