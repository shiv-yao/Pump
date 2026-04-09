import asyncio
import random

from app.engine import runtime as rt
from app.engine.agent import agent_adjust_params, agent_effective_entry_threshold, agent_force_trade_allowed, agent_in_cooldown, agent_update, current_dynamic_threshold
from app.engine.bootstrap import ensure_engine
from app.engine.execution import allocate_size, buy, check_sell
from app.engine.features import features, safe_adaptive_filter, score_with_allocator
from app.engine.fund_brain import update_fund_allocator
from app.engine.metrics import calc_unrealized_pnl_sol, update_peak_capital
from app.engine.risk import buy_window_count, detect_regime, institutional_daily_loss_hit, institutional_day_reset, institutional_paused
from app.engine.sources import fetch_alpha_candidates, mempool_stream
from app.engine.utils import dedup, exposure, exposure_by_strategy, limit_token_frequency, log, now, sf, update_open_stats

async def process_candidates(tokens):
    ranked = []
    dyn_threshold = current_dynamic_threshold()
    regime = detect_regime()
    for t in tokens:
        m = t.get("mint")
        if not m:
            continue
        if (m in rt.BLACKLIST and now() - rt.BLACKLIST[m] < rt.BLACKLIST_TIME) or now() - rt.LAST_TRADE[m] < 30:
            continue
        f = await features(t)
        if not f:
            continue
        f["source"] = t.get("source", f.get("source", "unknown"))
        f["meta"] = t.get("meta", {})
        sc, mtype, detail = score_with_allocator(f)
        min_threshold = max(dyn_threshold * 0.90, agent_effective_entry_threshold())
        if regime == "bear":
            min_threshold = max(min_threshold, agent_effective_entry_threshold() + 0.005)
        elif regime == "bull":
            min_threshold *= 0.97
        if sc < min_threshold:
            continue
        f["_score"] = sc
        f["_mode"] = mtype
        f["_tier"] = "A+" if sc >= 0.145 else "A" if sc >= rt.STRICT_A_TIER_THRESHOLD else "B"
        if rt.SNIPER_A_PLUS_ONLY and mtype == "sniper" and f["_tier"] != "A+":
            continue
        ranked.append(f)
    ranked.sort(key=lambda x: x["_score"], reverse=True)
    if not ranked:
        for t in tokens[:5]:
            f = await features(t)
            if not f:
                continue
            sc, mtype, _ = score_with_allocator(f)
            if sc > rt.EXPLORATION_MIN_SCORE:
                f["_score"] = sc
                f["_mode"] = mtype
                f["_tier"] = "B"
                ranked.append(f)
    return ranked[:10]

async def exploration_trade():
    if not rt.EXPLORATION_ENABLE or institutional_paused() or institutional_daily_loss_hit():
        return False
    tokens = await fetch_alpha_candidates()
    if not isinstance(tokens, list):
        return False
    for t in tokens[:6]:
        f = await features(t)
        if not f:
            continue
        sc, _mtype, _ = score_with_allocator(f)
        if sc > rt.EXPLORATION_MIN_SCORE:
            f["_score"] = sc
            f["_mode"] = "explore"
            f["_tier"] = "B"
            size = min(rt.engine.capital * rt.EXPLORATION_SIZE_FRAC, rt.engine.capital * rt.MAX_POSITION_SIZE, rt.engine.capital * max(0.02, min(0.15, rt.FUND_ALLOCATOR.get("explore", 0.08))))
            return bool(await buy(t["mint"], f, size, "explore", forced=True))
    return False

async def execute_portfolio(ranked):
    if not ranked:
        return await exploration_trade()
    traded = False
    buys_this_cycle = 0
    ranked = sorted(ranked, key=lambda x: x["_score"], reverse=True)[:rt.TOP_K_PRESELECT]
    in_breathing_cooldown = now() < sf(rt.BREATHING_STATE.get("cooldown_until", 0.0), 0.0)
    if buy_window_count() >= rt.MAX_BUYS_PER_10MIN or institutional_paused() or institutional_daily_loss_hit():
        return False
    for f in ranked:
        m = f["mint"]
        mode_name = f.get("_mode", "momentum")
        if rt.engine.stats.get("executed", 0) > 10 and rt.engine.stats.get("wins", 0) == 0:
            return False
        allowed_tiers = {"A+"} if rt.AGENT_STATE.get("mode") == "defensive" else {"A", "A+"}
        if f.get("_mode") != "explore" and f.get("_tier") not in allowed_tiers:
            continue
        if f.get("_mode") == "sniper" and rt.SNIPER_A_PLUS_ONLY and f.get("_tier") != "A+":
            continue
        if any(p["mint"] == m for p in rt.engine.positions):
            continue
        if len(rt.engine.positions) >= rt.MAX_POSITIONS or exposure() >= rt.engine.capital * rt.MAX_EXPOSURE:
            break
        if now() - rt.LAST_TRADE[m] < rt.TOKEN_COOLDOWN:
            continue
        if sf(f.get("liq", 0), 0.0) < rt.MIN_LIQUIDITY_TRADE and f.get("_mode") != "explore":
            continue
        if exposure_by_strategy(mode_name) >= rt.engine.capital * (rt.MAX_SNIPER_EXPOSURE if mode_name == "sniper" else rt.MAX_STRATEGY_EXPOSURE):
            continue
        if (in_breathing_cooldown or agent_in_cooldown()) and f.get("_tier") != "A+" and sf(f.get("_score"), 0.0) < max(agent_effective_entry_threshold() + 0.02, 0.14):
            continue
        ok = True
        if not rt.SOFT_DISABLE_FILTER:
            ok, _meta = safe_adaptive_filter(f, None, rt.engine.no_trade_cycles)
            if not ok and f["_score"] >= rt.FILTER_SCORE_BYPASS:
                ok = True
        if not ok:
            continue
        pos_size = allocate_size(f["_score"], len(ranked), f.get("_mode", "momentum"))
        if f.get("_mode") == "explore":
            pos_size = min(pos_size, rt.engine.capital * rt.EXPLORATION_SIZE_FRAC)
        if in_breathing_cooldown:
            pos_size *= 0.70
        if pos_size <= 0 or rt.engine.capital < pos_size + rt.ESTIMATED_TX_FEE_SOL:
            continue
        success = await buy(m, f, pos_size, f["_mode"], forced=(f.get("_mode") == "explore"))
        if success:
            rt.TOKEN_TRADE_COUNT[m] += 1
            buys_this_cycle += 1
            traded = True
            if buys_this_cycle >= rt.MAX_NEW_BUYS_PER_CYCLE or rt.TOP_N_TO_TRADE <= 1:
                break
    return traded

async def start_once():
    global MEMPOOL_TASK
    ensure_engine()
    update_fund_allocator(force=True)
    institutional_day_reset()
    if rt.MEMPOOL_TASK is None or rt.MEMPOOL_TASK.done():
        rt.MEMPOOL_TASK = asyncio.create_task(mempool_stream())

async def main_loop():
    await start_once()
    log("V71 MODULAR ENGINE START")
    while rt.engine.running:
        try:
            institutional_day_reset()
            agent_update()
            agent_adjust_params()
            update_fund_allocator()
            tokens = await fetch_alpha_candidates()
            if not isinstance(tokens, list):
                tokens = []
            tokens = dedup(tokens)
            tokens = limit_token_frequency(tokens, max_per_token=2)
            random.shuffle(tokens)
            tokens = tokens[:rt.MAX_TOKENS_PER_CYCLE]
            if len(tokens) < 3:
                await asyncio.sleep(rt.LOOP_SLEEP_SEC)
                continue
            for p in list(rt.engine.positions):
                await check_sell(p)
            ranked = await process_candidates(tokens)
            traded = await execute_portfolio(ranked)
            rt.engine.no_trade_cycles = 0 if traded else rt.engine.no_trade_cycles + 1
            if agent_force_trade_allowed() and rt.engine.no_trade_cycles > rt.FORCE_TRADE_AFTER and len(rt.engine.positions) < rt.MAX_POSITIONS and exposure() < rt.engine.capital * rt.MAX_EXPOSURE:
                current_mints = {p["mint"] for p in rt.engine.positions}
                for f in ranked[:rt.TOP_K_PRESELECT]:
                    if f["mint"] in current_mints or f["_score"] < rt.STRICT_A_TIER_THRESHOLD or f.get("_tier") not in {"A", "A+"}:
                        continue
                    if exposure_by_strategy(f["_mode"]) >= rt.engine.capital * (rt.MAX_SNIPER_EXPOSURE if f["_mode"] == "sniper" else rt.MAX_STRATEGY_EXPOSURE):
                        continue
                    ok = await buy(f["mint"], f, allocate_size(max(f["_score"], rt.STRICT_A_TIER_THRESHOLD), 1, f["_mode"]), f["_mode"], forced=True)
                    if ok:
                        rt.TOKEN_TRADE_COUNT[f["mint"]] += 1
                        rt.engine.no_trade_cycles = 0
                        break
            update_open_stats()
            await update_peak_capital()
            if rt.ENABLE_EQUITY_MARK:
                rt.engine.stats["unrealized_pnl_sol"] = await calc_unrealized_pnl_sol()
            rt.engine.stats["jito_sent"] = rt.JITO_STATS["sent"]
            rt.engine.stats["jito_ok"] = rt.JITO_STATS["ok"]
            rt.engine.stats["jito_fail"] = rt.JITO_STATS["fail"]
        except Exception as e:
            rt.engine.stats["errors"] += 1
            log(f"ERR {e}")
        await asyncio.sleep(rt.LOOP_SLEEP_SEC)
