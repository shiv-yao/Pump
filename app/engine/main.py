import asyncio
import time

from app.state import engine
from app.engine import runtime as rt

from app.engine.features import fetch_alpha_candidates, process_candidates
from app.engine.execution import execute_ranked_portfolio
from app.engine.risk import check_sell
from app.engine.state_runtime import update_runtime_stats
from app.engine.metrics_runtime import update_metrics
from app.engine.ml_fund_brain import ml_adjust_allocator
from app.engine.strategy_stable import run_stable_engine
from app.engine.strategy_sniper import run_sniper_engine


def _log(msg: str):
    print(msg)
    if not hasattr(engine, "logs") or engine.logs is None:
        engine.logs = []
    engine.logs.append(str(msg))
    engine.logs = engine.logs[-1000:]


def _ensure_engine_defaults():
    if not hasattr(engine, "running"):
        engine.running = False
    if not hasattr(engine, "logs") or engine.logs is None:
        engine.logs = []
    if not hasattr(engine, "positions") or engine.positions is None:
        engine.positions = []
    if not hasattr(engine, "trade_history") or engine.trade_history is None:
        engine.trade_history = []
    if not hasattr(engine, "stats") or not isinstance(engine.stats, dict):
        engine.stats = {}
    if not hasattr(engine, "capital"):
        engine.capital = 5.0
    if not hasattr(engine, "no_trade_cycles"):
        engine.no_trade_cycles = 0
    if not hasattr(engine, "last_loop_ts"):
        engine.last_loop_ts = 0.0

    engine.stats.setdefault("errors", 0)
    engine.stats.setdefault("trades", 0)
    engine.stats.setdefault("signals", 0)
    engine.stats.setdefault("executed", 0)


async def main_loop():
    _ensure_engine_defaults()
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
                try:
                    await check_sell(p)
                except Exception as e:
                    _log(f"SELL ERROR: {e}")

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

            # ================= NORMAL EXECUTION =================
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

            # ================= FALLBACK BUY =================
            if not traded:
                no_trade_cycles = int(getattr(engine, "no_trade_cycles", 0) or 0)
                force_after = int(getattr(rt, "FORCE_TRADE_AFTER", 30) or 30)

                if no_trade_cycles >= force_after:
                    ranked = sorted(
                        momentum_ranked if isinstance(momentum_ranked, list) else [],
                        key=lambda x: x.get("_score", 0.0),
                        reverse=True,
                    )

                    fallback = []
                    min_liq = float(getattr(rt, "MIN_LIQUIDITY_OBSERVE", 1500) or 1500)

                    for f in ranked:
                        sc = float(f.get("_score", 0.0) or 0.0)
                        liq = float(f.get("liq", 0.0) or 0.0)
                        mint = f.get("mint")

                        if not mint:
                            continue

                        if any(p.get("mint") == mint for p in engine.positions):
                            continue

                        if sc >= 0.045 and liq >= min_liq:
                            fallback.append(f)

                    if fallback:
                        _log(
                            f"FORCE_TRADE fallback engaged "
                            f"cycles={no_trade_cycles} candidates={len(fallback)}"
                        )

                        traded = await execute_ranked_portfolio(
                            fallback[:1],
                            strategy_name="momentum",
                            weight=min(0.15, float(alloc.get("momentum", 0.3))),
                        )

            # ================= RUNTIME =================
            engine.last_loop_ts = time.time()
            engine.no_trade_cycles = 0 if traded else engine.no_trade_cycles + 1

            # ================= STATS =================
            update_runtime_stats()

            # ================= METRICS =================
            update_metrics()

            _log(
                f"LOOP | cap={engine.capital:.4f} "
                f"pos={len(engine.positions)} "
                f"tokens={len(tokens)} "
                f"stable={len(stable_ranked)} "
                f"sniper={len(sniper_ranked)} "
                f"momentum={len(momentum_ranked)} "
                f"alloc={alloc} "
                f"traded={traded} "
                f"no_trade_cycles={engine.no_trade_cycles}"
            )

        except Exception as e:
            engine.stats["errors"] = int(engine.stats.get("errors", 0)) + 1
            _log(f"ERROR: {e}")

        await asyncio.sleep(float(getattr(rt, "LOOP_SLEEP_SEC", 2.0) or 2.0))
