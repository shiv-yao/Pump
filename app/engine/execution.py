from app.execution.jupiter_exec import execute_swap

from app.engine import runtime as rt
from app.engine.agent import agent_effective_sl, agent_effective_tp
from app.engine.features import safe_adaptive_filter
from app.engine.fund_brain import fund_multiplier, update_fund_perf
from app.engine.risk import detect_regime, institutional_loss_pause_if_needed, update_breathing_state
from app.engine.sources import get_price, safe_quote
from app.engine.utils import (
    clamp, exposure_by_strategy, extract_token_decimals, now, parse_out_amount, parse_signature,
    push_trade, safe_div, sf, source_stat_loss, source_stat_win, strategy_bucket_from_mode,
    strategy_stat_update, update_open_stats
)

def mempool_use_jito(f):
    if not rt.REAL_TRADING or not rt.USE_JITO:
        return False
    score = sf(f.get("_score", 0.0), 0.0)
    tier = str(f.get("_tier", "C"))
    mode_name = strategy_bucket_from_mode(f.get("_mode", "momentum"))
    if rt.JITO_ONLY_A_PLUS and tier != "A+":
        return False
    if score < rt.JITO_MIN_SCORE:
        return False
    return mode_name == "sniper"

async def safe_execute_swap(input_mint: str, output_mint: str, amount: int, prefer_jito=False, jito_context=None):
    if prefer_jito and rt.REAL_TRADING and rt.USE_JITO:
        try:
            rt.JITO_STATS["sent"] += 1
            jito_res = await rt.send_jito_bundle(input_mint=input_mint, output_mint=output_mint, amount=amount, tip_sol=rt.JITO_TIP_SOL, context=jito_context or {})
            if isinstance(jito_res, dict) and not jito_res.get("error"):
                rt.JITO_STATS["ok"] += 1
                jito_res["via"] = "jito"
                return jito_res
            if isinstance(jito_res, dict):
                rt.JITO_STATS["fail"] += 1
                rt.JITO_STATS["last_error"] = str(jito_res.get("error", "unknown"))
        except Exception as e:
            rt.JITO_STATS["fail"] += 1
            rt.JITO_STATS["last_error"] = str(e)

    try:
        res = await execute_swap(input_mint, output_mint, amount)
    except Exception as e:
        return {"error": f"execute_swap_exception: {e}"}
    if not isinstance(res, dict):
        return {"error": "execute_swap_invalid_response"}
    if res.get("paper"):
        q = await safe_quote(input_mint, output_mint, amount)
        out_amount = parse_out_amount(q)
        if out_amount <= 0:
            out_amount = 1
        res["quote"] = dict(res.get("quote") or {})
        res["quote"]["outAmount"] = str(out_amount)
        return res
    res["via"] = res.get("via", "jupiter")
    return res

def extract_fee_sol_from_res(res):
    if not isinstance(res, dict):
        return rt.ESTIMATED_TX_FEE_SOL
    fee_candidates = [res.get("fee_sol"), res.get("tx_fee_sol"), res.get("network_fee_sol"), (res.get("quote") or {}).get("fee_sol"), (res.get("quote") or {}).get("tx_fee_sol")]
    for x in fee_candidates:
        v = sf(x, None)
        if v is not None and v >= 0:
            return v
    return rt.ESTIMATED_TX_FEE_SOL

def atomic_to_token_amount(out_amount, decimals):
    if out_amount <= 0:
        return 0.0
    return out_amount / (10 ** decimals)

def allocate_size(score, n_candidates, strategy="momentum"):
    strategy = strategy_bucket_from_mode(strategy)
    if n_candidates <= 0:
        return 0.0
    base = rt.engine.capital / max(n_candidates * 2, 2)
    regime = detect_regime()
    if regime == "bull":
        base *= 1.20
    elif regime == "bear":
        base *= 0.65
    if score > 0.16:
        base *= 2.0
    elif score > 0.14:
        base *= 1.65
    elif score > 0.12:
        base *= 1.15
    else:
        base *= 0.55
    base *= max(rt.BREATHING_MIN_RISK_MULT, min(rt.BREATHING_MAX_RISK_MULT, sf(rt.BREATHING_STATE.get("risk_mult", 1.0), 1.0)))
    base *= clamp(sf(rt.AGENT_STATE.get("risk_mult", 1.0), 1.0), rt.AGENT_RISK_MIN, rt.AGENT_RISK_MAX)
    base *= fund_multiplier(strategy)
    if now() < sf(rt.AGENT_STATE.get("cooldown_until", 0.0), 0.0):
        base *= 0.60
    alloc_cap = clamp(rt.FUND_ALLOCATOR.get(strategy, 0.25), 0.05, 0.60)
    hard_cap = rt.engine.capital * alloc_cap
    strat_cap = rt.engine.capital * rt.MAX_STRATEGY_EXPOSURE
    if strategy == "sniper":
        strat_cap = min(strat_cap, rt.engine.capital * rt.MAX_SNIPER_EXPOSURE)
    base = min(base, 0.20)
    return min(base, rt.engine.capital * rt.MAX_POSITION_SIZE, hard_cap, strat_cap)

async def buy(m, f, position_size, mtype, forced=False):
    mtype = strategy_bucket_from_mode(mtype)
    order_sol = max(position_size, rt.MIN_ORDER_SOL)
    amt_atomic = int(order_sol * rt.SOL_DECIMALS)
    prefer_jito = mempool_use_jito(f)
    res = await safe_execute_swap(rt.SOL, m, amt_atomic, prefer_jito=prefer_jito, jito_context={"score": f.get("_score"), "tier": f.get("_tier"), "mode": mtype, "mint": m})
    if not res:
        rt.engine.stats["errors"] += 1
        return False
    if res.get("error"):
        rt.engine.stats["errors"] += 1
        return False
    out_amount = parse_out_amount(res)
    if out_amount <= 0:
        q = await safe_quote(rt.SOL, m, amt_atomic)
        out_amount = parse_out_amount(q)
    if out_amount <= 0:
        rt.engine.stats["errors"] += 1
        return False
    token_decimals = extract_token_decimals(f.get("meta", {}))
    token_amount = atomic_to_token_amount(out_amount, token_decimals)
    if token_amount <= 0:
        rt.engine.stats["errors"] += 1
        return False
    tx_sig = parse_signature(res)
    fee_sol = extract_fee_sol_from_res(res)
    via = res.get("via", "jupiter")

    rt.engine.capital = max(rt.engine.capital - order_sol - fee_sol, 0.0)
    rt.engine.stats["fees_paid_sol"] += fee_sol
    if via == "jito":
        rt.engine.stats["jito_sent"] += 1
        if tx_sig:
            rt.engine.stats["jito_ok"] += 1
        else:
            rt.engine.stats["jito_fail"] += 1

    meta = dict(f.get("meta", {}) or {})
    meta.update({
        "source": f.get("source"), "strategy": mtype, "forced": forced,
        "breakout": f.get("breakout"), "momentum": f.get("momentum"), "smart_money": f.get("smart"),
        "wallet_graph_score": f.get("wallet_graph_score"), "cluster_size": f.get("cluster_size"),
        "smart_ratio": f.get("smart_ratio"), "concentration": f.get("concentration"),
        "fresh_wallet_ratio": f.get("fresh_wallet_ratio"), "liquidity": f.get("liq"),
        "wallet_count": f.get("wallet_count"), "price": f.get("price"), "score": f.get("_score"),
        "tier": f.get("_tier"), "regime": detect_regime(), "agent_mode": rt.AGENT_STATE.get("mode"),
        "token_decimals": token_decimals, "fund_alloc": dict(rt.FUND_ALLOCATOR),
        "mempool_age_sec": f.get("mempool_age_sec"), "mempool_hits": f.get("mempool_hits"), "via": via,
    })
    position = {
        "mint": m, "entry": f["price"], "entry_price": f["price"], "size": order_sol, "size_sol": order_sol,
        "entry_value": order_sol, "token_amount_atomic": out_amount, "token_amount": token_amount,
        "token_decimals": token_decimals, "fees_paid_sol": fee_sol, "time": now(), "mode": mtype,
        "source": f["source"], "meta": meta, "price_source": f.get("price_source"), "liq": f.get("liq", 0),
        "high": f["price"], "wallet_count": f.get("wallet_count", 0), "tx_buy": tx_sig, "forced": forced,
        "paper": bool(res.get("paper")), "score": f.get("_score", 0.0), "tier": f.get("_tier", "C"),
        "realized_partial_sol": 0.0, "via": via, "wallet_graph_score": f.get("wallet_graph_score", 0.0),
    }
    rt.engine.positions.append(position)
    rt.LAST_TRADE[m] = now()
    rt.BUY_TIMES.append(now())
    rt.engine.stats["executed"] += 1
    rt.engine.stats["signals"] += 1
    if forced:
        rt.engine.stats["forced_trades"] += 1
    update_open_stats()
    rt.engine.last_signal = f"BUY {m[:6]} {mtype} tier={f.get('_tier','C')} via={via} score={f.get('_score',0):.4f}"
    rt.engine.last_trade = rt.engine.last_signal
    return True

async def sell(p, reason, price, sell_fraction=1.0):
    m = p["mint"]
    sell_fraction = clamp(sell_fraction, 0.0, 1.0)
    if sell_fraction <= 0:
        return False
    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    entry_value_total = sf(p.get("entry_value", 0.0), 0.0)
    fees_paid_total = sf(p.get("fees_paid_sol", 0.0), 0.0)
    if token_amount <= 0 or entry_value_total <= 0:
        rt.engine.stats["errors"] += 1
        return False
    token_amount_to_sell = token_amount * sell_fraction
    token_amount_remain = max(0.0, token_amount - token_amount_to_sell)
    token_decimals = int(p.get("token_decimals", rt.DEFAULT_TOKEN_DECIMALS))
    atomic_sell = int(token_amount_to_sell * (10 ** token_decimals))
    if atomic_sell <= 0:
        rt.engine.stats["errors"] += 1
        return False
    prefer_jito = bool(rt.USE_JITO and strategy_bucket_from_mode(p.get("mode")) == "sniper" and p.get("tier") == "A+")
    if p.get("paper"):
        res = {"paper": True}
        fee_sol = rt.ESTIMATED_TX_FEE_SOL
    else:
        res = await safe_execute_swap(m, rt.SOL, atomic_sell, prefer_jito=prefer_jito, jito_context={"reason": reason, "mode": p.get("mode"), "tier": p.get("tier"), "mint": m})
        fee_sol = extract_fee_sol_from_res(res)
    if not res or res.get("error"):
        rt.engine.stats["errors"] += 1
        return False
    via = res.get("via", "jupiter")
    rt.engine.stats["fees_paid_sol"] += fee_sol
    exit_value = token_amount_to_sell * price
    entry_value_sold = entry_value_total * sell_fraction
    fees_allocated = fees_paid_total * sell_fraction + fee_sol
    pnl_sol = exit_value - entry_value_sold - fees_allocated
    pnl = clamp(safe_div(pnl_sol, entry_value_sold, 0.0), -rt.MAX_PNL_ABS, rt.MAX_PNL_ABS)

    rt.engine.capital += max(0.0, exit_value - fee_sol)
    rt.engine.stats["realized_pnl_sol"] += pnl_sol
    rt.INSTITUTIONAL_STATE["daily_realized_pnl_sol"] += pnl_sol
    src = p.get("source", "unknown")
    strategy = strategy_bucket_from_mode(p.get("mode", "unknown"))
    is_full_exit = token_amount_remain <= 1e-12 or sell_fraction >= 0.999999

    if is_full_exit:
        if p in rt.engine.positions:
            rt.engine.positions.remove(p)
    else:
        p["token_amount"] = token_amount_remain
        p["token_amount_atomic"] = int(token_amount_remain * (10 ** token_decimals))
        p["entry_value"] = entry_value_total * (1.0 - sell_fraction)
        p["size"] = p["entry_value"]
        p["size_sol"] = p["entry_value"]
        p["fees_paid_sol"] = fees_paid_total * (1.0 - sell_fraction)
        p["realized_partial_sol"] = sf(p.get("realized_partial_sol", 0.0), 0.0) + pnl_sol

    if pnl_sol > 0:
        rt.engine.stats["wins"] += 1
        source_stat_win(src, pnl)
    else:
        rt.engine.stats["losses"] += 1
        source_stat_loss(src, pnl)
    strategy_stat_update(strategy, pnl)
    update_fund_perf(strategy, pnl)
    push_trade({
        "mint": m, "entry": p.get("entry_price", p.get("entry")), "exit": price, "pnl": pnl, "pnl_sol": pnl_sol,
        "reason": reason, "size": entry_value_sold, "mode": strategy, "source": src, "price_source": p.get("price_source"),
        "time_open": p.get("time"), "time_close": now(), "tx_buy": p.get("tx_buy"), "meta": p.get("meta", {}),
        "sell_fraction": sell_fraction, "exit_value": exit_value, "entry_value": entry_value_sold,
        "fees_paid_sol": fees_allocated, "token_amount_sold": token_amount_to_sell, "via": via,
    })
    update_breathing_state()
    institutional_loss_pause_if_needed()
    update_open_stats()
    if is_full_exit:
        rt.BLACKLIST[m] = now()
    return True

async def check_sell(p):
    m = p["mint"]
    price = await get_price(m)
    entry = sf(p.get("entry_price", p.get("entry")), 0.0)
    if price is None or entry <= 0:
        return False
    hold_sec = now() - sf(p.get("time"), now())
    if price < 1e-8 or hold_sec < 8:
        return False
    last = rt.LAST_PRICE.get(m)
    if last and last > 0:
        jump = abs(price - last) / last
        if jump > 0.25 and hold_sec < 20:
            return False
    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    entry_value = sf(p.get("entry_value", 0.0), 0.0)
    if token_amount <= 0 or entry_value <= 0:
        return False
    market_value = token_amount * price
    pnl = clamp(safe_div(market_value - entry_value, entry_value, 0.0), -rt.MAX_PNL_ABS, rt.MAX_PNL_ABS)
    p["high"] = max(sf(p.get("high"), entry), price)
    tier = p.get("tier") or (p.get("meta", {}) or {}).get("tier", "C")
    momentum_now = sf(rt.LAST_MOMENTUM.get(m, 0.0), 0.0)
    regime = detect_regime()

    if pnl <= rt.HARD_STOP_LOSS: return await sell(p, "HARD_STOP", price, 1.0)
    if hold_sec > rt.FORCE_EXIT_SEC: return await sell(p, "FORCE_EXIT", price, 1.0)
    fast_cut_line = -0.02 if regime != "bear" else -0.015
    if pnl < fast_cut_line and hold_sec > 20: return await sell(p, "FAST_CUT", price, 1.0)
    if pnl > 0 and momentum_now > 0.0035: return False
    if -0.02 < pnl < 0 and momentum_now > 0.0045: return False
    if pnl >= 0.008 and not p.get("tp1_done"):
        p["tp1_done"] = True
        return await sell(p, "PARTIAL_TP", price, 0.50)
    tp = agent_effective_tp()
    if tier == "A+": tp *= 2.2
    elif tier == "A": tp *= 1.8
    if regime == "bull": tp *= 1.15
    elif regime == "bear": tp *= 0.85
    if pnl >= tp: return await sell(p, "TP", price, 1.0)

    effective_sl = agent_effective_sl()
    if pnl <= effective_sl:
        import asyncio
        await asyncio.sleep(0.4)
        price2 = await get_price(m)
        if price2:
            market_value2 = token_amount * price2
            pnl2 = clamp(safe_div(market_value2 - entry_value, entry_value, 0.0), -rt.MAX_PNL_ABS, rt.MAX_PNL_ABS)
            if pnl2 <= effective_sl:
                return await sell(p, "SL", price2, 1.0)
        return False

    dynamic_trailing_gap = rt.TRAILING_GAP * (1.15 if tier == "A+" else 1.0) * (0.85 if regime == "bear" else 1.0)
    if price < p["high"] * (1 - dynamic_trailing_gap): return await sell(p, "TRAIL", price, 1.0)
    dynamic_hold = int(rt.MAX_HOLD_SEC * (1.25 if regime == "bull" else 0.70 if regime == "bear" else 1.0))
    if hold_sec > dynamic_hold:
        if tier in {"A", "A+"} and momentum_now > 0.0025 and pnl > 0:
            return False
        if pnl < 0.003:
            return await sell(p, "TIME", price, 1.0)
    return False
