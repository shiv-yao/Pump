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
    if not hasattr(engine, "last_signal"):
        engine.last_signal = ""
    if not hasattr(engine, "last_trade"):
        engine.last_trade = ""

    engine.stats.setdefault("errors", 0)
    engine.stats.setdefault("trades", 0)
    engine.stats.setdefault("signals", 0)
    engine.stats.setdefault("executed", 0)
    engine.stats.setdefault("forced_trades", 0)
    engine.stats.setdefault("wins", 0)
    engine.stats.setdefault("losses", 0)


def _ensure_runtime_defaults():
    if not hasattr(rt, "FUND_ALLOCATOR") or not isinstance(rt.FUND_ALLOCATOR, dict):
        rt.FUND_ALLOCATOR = {
            "stable": 0.40,
            "sniper": 0.20,
            "momentum": 0.35,
            "explore": 0.05,
        }

    if not hasattr(rt, "FUND_STATE") or not isinstance(rt.FUND_STATE, dict):
        rt.FUND_STATE = {"last_reason": "boot"}

    if not hasattr(rt, "FORCE_TRADE_AFTER"):
        rt.FORCE_TRADE_AFTER = 30

    if not hasattr(rt, "MIN_LIQUIDITY_OBSERVE"):
        rt.MIN_LIQUIDITY_OBSERVE = 1500

    if not hasattr(rt, "LOOP_SLEEP_SEC"):
        rt.LOOP_SLEEP_SEC = 2.0

    if not hasattr(rt, "MAX_POSITION_SIZE"):
        rt.MAX_POSITION_SIZE = 0.03


def _safe_alloc():
    raw = getattr(rt, "FUND_ALLOCATOR", {})
    if not isinstance(raw, dict):
        raw = {}

    alloc = {
        "stable": float(raw.get("stable", 0.40) or 0.40),
        "sniper": float(raw.get("sniper", 0.20) or 0.20),
        "momentum": float(raw.get("momentum", 0.35) or 0.35),
        "explore": float(raw.get("explore", 0.05) or 0.05),
    }

    for k in alloc:
        if alloc[k] != alloc[k]:  # NaN guard
            alloc[k] = 0.0
        alloc[k] = max(0.0, min(1.0, alloc[k]))

    s = alloc["stable"] + alloc["sniper"] + alloc["momentum"] + alloc["explore"]
    if s <= 0:
        return {"stable": 0.40, "sniper": 0.20, "momentum": 0.35, "explore": 0.05}

    for k in alloc:
        alloc[k] /= s

    return alloc


async def _run_sell_checks():
    positions = list(getattr(engine, "positions", []) or [])
    if not positions:
        return

    results = await asyncio.gather(
        *[check_sell(p) for p in positions],
        return_exceptions=True,
    )

    for r in results:
        if isinstance(r, Exception):
            _log(f"SELL ERROR: {r}")


async def main_loop():
    _ensure_engine_defaults()
    _ensure_runtime_defaults()

    engine.running = True
    _log("🔥 V82 AI FUND SYSTEM START")

    while engine.running:
        traded = False

        try:
            # ================= GLOBAL RISK GATE =================
            try:
                from app.engine.risk import institutional_pause_active
                if institutional_pause_active():
                    _log("⛔ INSTITUTIONAL PAUSE ACTIVE")
                    await asyncio.sleep(float(getattr(rt, "LOOP_SLEEP_SEC", 2.0) or 2.0))
                    continue
            except Exception as e:
                _log(f"PAUSE CHECK ERROR: {e}")

            # ================= FETCH =================
            tokens = await fetch_alpha_candidates()
            if not isinstance(tokens, list):
                tokens = []

            # 沒候選就直接短休眠
            if not tokens:
                engine.last_loop_ts = time.time()
                engine.no_trade_cycles = int(getattr(engine, "no_trade_cycles", 0) or 0) + 1
                try:
                    update_runtime_stats()
                except Exception as e:
                    _log(f"STATS ERROR: {e}")
                try:
                    update_metrics()
                except Exception as e:
                    _log(f"METRICS ERROR: {e}")

                _log(
                    f"LOOP | cap={engine.capital:.4f} "
                    f"pos={len(engine.positions)} "
                    f"tokens=0 traded=False "
                    f"no_trade_cycles={engine.no_trade_cycles}"
                )
                await asyncio.sleep(min(float(getattr(rt, "LOOP_SLEEP_SEC", 2.0) or 2.0), 1.5))
                continue

            # ================= SELL =================
            try:
                await _run_sell_checks()
            except Exception as e:
                _log(f"SELL GATHER ERROR: {e}")

            # ================= STRATEGIES =================
            stable_ranked = await run_stable_engine(tokens)
            sniper_ranked = await run_sniper_engine(tokens)
            momentum_ranked = await process_candidates(tokens)

            # ================= FUND BRAIN =================
            try:
                ml_adjust_allocator()
            except Exception as e:
                _log(f"ALLOCATOR ERROR: {e}")

            alloc = _safe_alloc()

            # ================= NORMAL EXECUTION =================
            traded_stable = await execute_ranked_portfolio(
                stable_ranked,
                strategy_name="stable",
                weight=alloc.get("stable", 0.4),
                max_new=1,
            )

            traded_sniper = await execute_ranked_portfolio(
                sniper_ranked,
                strategy_name="sniper",
                weight=alloc.get("sniper", 0.2),
                max_new=1,
            )

            traded_momentum = await execute_ranked_portfolio(
                momentum_ranked,
                strategy_name="momentum",
                weight=alloc.get("momentum", 0.35),
                max_new=1,
            )

            traded = bool(traded_stable or traded_sniper or traded_momentum)

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
                        wg = float(f.get("wallet_graph_score", 0.0) or 0.0)
                        ai_prob = float(f.get("_ai_win_prob", 0.5) or 0.5)
                        source = str(f.get("source", "")).lower()

                        if not mint:
                            continue

                        if any((p.get("mint") == mint) for p in (engine.positions or [])):
                            continue

                        if sc < 0.045:
                            continue
                        if liq < min_liq:
                            continue
                        if wg < 0.15:
                            continue
                        if ai_prob < 0.48:
                            continue
                        if source == "dexscreener":
                            continue

                        fallback.append(f)

                    if fallback:
                        _log(
                            f"FORCE_TRADE fallback engaged "
                            f"cycles={no_trade_cycles} candidates={len(fallback)}"
                        )

                        traded = await execute_ranked_portfolio(
                            fallback[:1],
                            strategy_name="momentum",
                            weight=min(0.15, float(alloc.get("momentum", 0.35))),
                            max_new=1,
                        )

                        if traded:
                            engine.stats["forced_trades"] = int(engine.stats.get("forced_trades", 0)) + 1

            # ================= RUNTIME =================
            engine.last_loop_ts = time.time()
            engine.no_trade_cycles = 0 if traded else int(getattr(engine, "no_trade_cycles", 0) or 0) + 1

            # ================= DEFENSIVE MODE =================
            wins = int(engine.stats.get("wins", 0) or 0)
            losses = int(engine.stats.get("losses", 0) or 0)
            if losses > wins + 3:
                try:
                    rt.MAX_POSITION_SIZE = max(
                        float(getattr(rt, "MAX_POSITION_SIZE", 0.03)) * 0.7,
                        0.005,
                    )
                    _log(f"⚠️ DEFENSIVE MODE MAX_POSITION_SIZE={rt.MAX_POSITION_SIZE:.4f}")
                except Exception as e:
                    _log(f"DEFENSIVE MODE ERROR: {e}")

            # ================= STATS =================
            try:
                update_runtime_stats()
            except Exception as e:
                _log(f"STATS ERROR: {e}")

            # ================= METRICS =================
            try:
                update_metrics()
            except Exception as e:
                _log(f"METRICS ERROR: {e}")

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
