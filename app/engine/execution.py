import asyncio

from app.execution.jupiter_exec import execute_swap

from app.engine import runtime as rt
from app.engine.agent import agent_effective_sl, agent_effective_tp
from app.engine.fund_brain import fund_multiplier, update_fund_perf
from app.engine.risk import (
    detect_regime,
    institutional_loss_pause_if_needed,
    update_breathing_state,
)
from app.engine.sources import get_price, safe_quote
from app.engine.utils import (
    clamp,
    extract_token_decimals,
    now,
    parse_out_amount,
    parse_signature,
    push_trade,
    safe_div,
    sf,
    source_stat_loss,
    source_stat_win,
    strategy_bucket_from_mode,
    strategy_stat_update,
    update_open_stats,
)


def _ensure_stats():
    if not hasattr(rt.engine, "stats") or not isinstance(rt.engine.stats, dict):
        rt.engine.stats = {}

    defaults = {
        "executed": 0,
        "wins": 0,
        "losses": 0,
        "trades": 0,
        "errors": 0,
        "signals": 0,
        "forced_trades": 0,
        "fees_paid_sol": 0.0,
        "realized_pnl_sol": 0.0,
        "jito_sent": 0,
        "jito_ok": 0,
        "jito_fail": 0,
    }
    for k, v in defaults.items():
        rt.engine.stats.setdefault(k, v)


def _log(msg: str):
    print(msg)
    if not hasattr(rt.engine, "logs") or rt.engine.logs is None:
        rt.engine.logs = []
    rt.engine.logs.append(str(msg))
    rt.engine.logs = rt.engine.logs[-1200:]


def _ensure_runtime_dicts():
    if not hasattr(rt, "JITO_STATS") or not isinstance(rt.JITO_STATS, dict):
        rt.JITO_STATS = {"sent": 0, "ok": 0, "fail": 0, "last_error": ""}

    for k, v in {"sent": 0, "ok": 0, "fail": 0, "last_error": ""}.items():
        rt.JITO_STATS.setdefault(k, v)

    if not hasattr(rt, "INSTITUTIONAL_STATE") or not isinstance(rt.INSTITUTIONAL_STATE, dict):
        rt.INSTITUTIONAL_STATE = {
            "pause_until": 0.0,
            "daily_realized_pnl_sol": 0.0,
            "day_bucket": 0,
            "last_reason": "boot",
        }

    for k, v in {
        "pause_until": 0.0,
        "daily_realized_pnl_sol": 0.0,
        "day_bucket": 0,
        "last_reason": "boot",
    }.items():
        rt.INSTITUTIONAL_STATE.setdefault(k, v)

    if not hasattr(rt, "FUND_ALLOCATOR") or not isinstance(rt.FUND_ALLOCATOR, dict):
        rt.FUND_ALLOCATOR = {
            "stable": 0.40,
            "sniper": 0.20,
            "momentum": 0.35,
            "explore": 0.05,
        }

    if not hasattr(rt, "LAST_TRADE") or rt.LAST_TRADE is None:
        rt.LAST_TRADE = {}
    if not hasattr(rt, "LAST_PRICE") or rt.LAST_PRICE is None:
        rt.LAST_PRICE = {}
    if not hasattr(rt, "LAST_MOMENTUM") or rt.LAST_MOMENTUM is None:
        rt.LAST_MOMENTUM = {}
    if not hasattr(rt, "BLACKLIST") or rt.BLACKLIST is None:
        rt.BLACKLIST = {}
    if not hasattr(rt, "BUY_TIMES") or rt.BUY_TIMES is None:
        rt.BUY_TIMES = []

    if not hasattr(rt.engine, "positions") or rt.engine.positions is None:
        rt.engine.positions = []
    if not hasattr(rt.engine, "capital"):
        rt.engine.capital = 0.0


def mempool_use_jito(f):
    _ensure_runtime_dicts()

    if not getattr(rt, "REAL_TRADING", False):
        return False
    if not getattr(rt, "USE_JITO", False):
        return False

    score = sf(f.get("_score", 0.0), 0.0)
    tier = str(f.get("_tier", "C"))
    mode_name = strategy_bucket_from_mode(f.get("_mode", "momentum"))

    if getattr(rt, "JITO_ONLY_A_PLUS", False) and tier != "A+":
        return False
    if score < sf(getattr(rt, "JITO_MIN_SCORE", 0.125), 0.125):
        return False

    return mode_name == "sniper"


async def safe_execute_swap(
    input_mint: str,
    output_mint: str,
    amount: int,
    prefer_jito: bool = False,
    jito_context=None,
):
    _ensure_stats()
    _ensure_runtime_dicts()

    if prefer_jito and getattr(rt, "REAL_TRADING", False) and getattr(rt, "USE_JITO", False):
        try:
            rt.JITO_STATS["sent"] += 1
            jito_res = await rt.send_jito_bundle(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount,
                tip_sol=getattr(rt, "JITO_TIP_SOL", 0.0005),
                context=jito_context or {},
            )
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
        res["via"] = res.get("via", "paper")
        return res

    res["via"] = res.get("via", "jupiter")
    return res


def extract_fee_sol_from_res(res):
    if not isinstance(res, dict):
        return getattr(rt, "ESTIMATED_TX_FEE_SOL", 0.000005)

    fee_candidates = [
        res.get("fee_sol"),
        res.get("tx_fee_sol"),
        res.get("network_fee_sol"),
        (res.get("quote") or {}).get("fee_sol"),
        (res.get("quote") or {}).get("tx_fee_sol"),
    ]
    for x in fee_candidates:
        v = sf(x, None)
        if v is not None and v >= 0:
            return v

    return getattr(rt, "ESTIMATED_TX_FEE_SOL", 0.000005)


def _extract_best_decimals(f, res):
    candidates = []

    meta = f.get("meta", {}) if isinstance(f, dict) else {}
    if isinstance(meta, dict):
        candidates.extend([
            meta.get("decimals"),
            meta.get("token_decimals"),
            (meta.get("output_token") or {}).get("decimals")
            if isinstance(meta.get("output_token"), dict) else None,
            (meta.get("baseToken") or {}).get("decimals")
            if isinstance(meta.get("baseToken"), dict) else None,
            (meta.get("token") or {}).get("decimals")
            if isinstance(meta.get("token"), dict) else None,
        ])

    if isinstance(res, dict):
        quote = res.get("quote") or {}
        if isinstance(quote, dict):
            candidates.extend([
                quote.get("outputDecimals"),
                quote.get("outDecimals"),
                quote.get("decimals"),
                (quote.get("outputToken") or {}).get("decimals")
                if isinstance(quote.get("outputToken"), dict) else None,
                (quote.get("tokenMeta") or {}).get("decimals")
                if isinstance(quote.get("tokenMeta"), dict) else None,
            ])

    for v in candidates:
        try:
            iv = int(v)
            if 0 <= iv <= 18:
                return iv
        except Exception:
            pass

    return extract_token_decimals(meta)


def atomic_to_token_amount(out_amount, decimals):
    if out_amount <= 0:
        return 0.0
    try:
        return float(out_amount) / float(10 ** int(decimals))
    except Exception:
        return 0.0


def lamports_to_sol(lamports):
    try:
        return float(lamports) / float(getattr(rt, "SOL_DECIMALS", 1_000_000_000))
    except Exception:
        return 0.0


def allocate_size(score, n_candidates, strategy="momentum", ai_prob=0.5):
    _ensure_runtime_dicts()

    strategy = strategy_bucket_from_mode(strategy)
    if n_candidates <= 0:
        return 0.0

    capital = sf(getattr(rt.engine, "capital", 0.0), 0.0)
    if capital <= 0:
        return 0.0

    base = capital / max(n_candidates * 2, 2)
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

    base *= max(
        getattr(rt, "BREATHING_MIN_RISK_MULT", 0.45),
        min(
            getattr(rt, "BREATHING_MAX_RISK_MULT", 1.20),
            sf(getattr(rt, "BREATHING_STATE", {}).get("risk_mult", 1.0), 1.0),
        ),
    )
    base *= clamp(
        sf(getattr(rt, "AGENT_STATE", {}).get("risk_mult", 1.0), 1.0),
        getattr(rt, "AGENT_RISK_MIN", 0.45),
        getattr(rt, "AGENT_RISK_MAX", 1.35),
    )
    base *= fund_multiplier(strategy)

    if now() < sf(getattr(rt, "AGENT_STATE", {}).get("cooldown_until", 0.0), 0.0):
        base *= 0.60

    ai_prob = clamp(sf(ai_prob, 0.5), 0.0, 1.0)
    base *= (0.6 + ai_prob * 0.8)

    alloc_cap = clamp(rt.FUND_ALLOCATOR.get(strategy, 0.25), 0.05, 0.60)
    hard_cap = capital * alloc_cap

    strat_cap = capital * getattr(rt, "MAX_STRATEGY_EXPOSURE", 0.18)
    if strategy == "sniper":
        strat_cap = min(strat_cap, capital * getattr(rt, "MAX_SNIPER_EXPOSURE", 0.14))

    base = min(base, 0.20)
    return min(
        base,
        capital * getattr(rt, "MAX_POSITION_SIZE", 0.03),
        hard_cap,
        strat_cap,
    )


async def buy(m, f, position_size, mtype, forced=False):
    _ensure_stats()
    _ensure_runtime_dicts()

    if sf(f.get("_ai_win_prob", 0.5), 0.5) < 0.48:
        return False

    mtype = strategy_bucket_from_mode(mtype)
    order_sol = max(position_size, getattr(rt, "MIN_ORDER_SOL", 0.01))
    amt_atomic = int(order_sol * getattr(rt, "SOL_DECIMALS", 1_000_000_000))

    prefer_jito = mempool_use_jito(f)
    res = await safe_execute_swap(
        rt.SOL,
        m,
        amt_atomic,
        prefer_jito=prefer_jito,
        jito_context={
            "score": f.get("_score"),
            "tier": f.get("_tier"),
            "mode": mtype,
            "mint": m,
            "ai_win_prob": f.get("_ai_win_prob"),
        },
    )

    if not res:
        rt.engine.stats["errors"] += 1
        _log(f"BUY_EMPTY {m[:6]}")
        return False

    if res.get("error"):
        rt.engine.stats["errors"] += 1
        _log(f"BUY_FAIL {m[:6]} {res.get('error')}")
        return False

    out_amount = parse_out_amount(res)
    if out_amount <= 0:
        q = await safe_quote(rt.SOL, m, amt_atomic)
        out_amount = parse_out_amount(q)
        if isinstance(res, dict):
            res["quote"] = dict(res.get("quote") or {})
            if out_amount > 0:
                res["quote"]["outAmount"] = str(out_amount)

    if out_amount <= 0:
        rt.engine.stats["errors"] += 1
        _log(f"BUY_NO_OUT {m[:6]}")
        return False

    token_decimals = _extract_best_decimals(f, res)
    token_amount = atomic_to_token_amount(out_amount, token_decimals)

    if token_amount <= 0:
        rt.engine.stats["errors"] += 1
        _log(f"BUY_BAD_TOKEN_AMOUNT {m[:6]} out={out_amount} dec={token_decimals}")
        return False

    tx_sig = parse_signature(res)
    fee_sol = extract_fee_sol_from_res(res)
    via = res.get("via", "jupiter")

    rt.engine.capital = max(sf(rt.engine.capital, 0.0) - order_sol - fee_sol, 0.0)
    rt.engine.stats["fees_paid_sol"] += fee_sol

    if via == "jito":
        rt.engine.stats["jito_sent"] += 1
        if tx_sig:
            rt.engine.stats["jito_ok"] += 1
        else:
            rt.engine.stats["jito_fail"] += 1

    entry_price = sf(f.get("price", 0.0), 0.0)
    if entry_price <= 0:
        entry_price = safe_div(order_sol, token_amount, 0.0)

    mark_price = entry_price

    meta = dict(f.get("meta", {}) or {})
    meta.update({
        "source": f.get("source"),
        "strategy": mtype,
        "forced": forced,
        "breakout": f.get("breakout"),
        "momentum": f.get("momentum"),
        "smart_money": f.get("smart"),
        "wallet_graph_score": f.get("wallet_graph_score"),
        "cluster_size": f.get("cluster_size"),
        "smart_ratio": f.get("smart_ratio"),
        "concentration": f.get("concentration"),
        "fresh_wallet_ratio": f.get("fresh_wallet_ratio"),
        "liquidity": f.get("liq"),
        "wallet_count": f.get("wallet_count"),
        "price": entry_price,
        "score": f.get("_score"),
        "tier": f.get("_tier"),
        "regime": detect_regime(),
        "agent_mode": getattr(rt, "AGENT_STATE", {}).get("mode"),
        "token_decimals": token_decimals,
        "quote_out_amount": out_amount,
        "fund_alloc": dict(rt.FUND_ALLOCATOR),
        "mempool_age_sec": f.get("mempool_age_sec"),
        "mempool_hits": f.get("mempool_hits"),
        "via": via,
        "ai_win_prob": f.get("_ai_win_prob"),
        "ai_pnl": f.get("_ai_pnl"),
        "ai_score": f.get("_ai_score"),
    })

    position = {
        "mint": m,
        "entry": entry_price,
        "entry_price": entry_price,
        "price": mark_price,
        "mark_price": mark_price,
        "size": order_sol,
        "size_sol": order_sol,
        "entry_value": order_sol,
        "token_amount_atomic": out_amount,
        "token_amount": token_amount,
        "token_decimals": token_decimals,
        "fees_paid_sol": fee_sol,
        "time": now(),
        "mode": mtype,
        "source": f["source"],
        "meta": meta,
        "price_source": f.get("price_source"),
        "liq": f.get("liq", 0),
        "high": mark_price,
        "wallet_count": f.get("wallet_count", 0),
        "tx_buy": tx_sig,
        "forced": forced,
        "paper": bool(res.get("paper")),
        "score": f.get("_score", 0.0),
        "tier": f.get("_tier", "C"),
        "realized_partial_sol": 0.0,
        "via": via,
        "wallet_graph_score": f.get("wallet_graph_score", 0.0),
        "ai_win_prob": f.get("_ai_win_prob", 0.5),
        "ai_pnl": f.get("_ai_pnl", 0.0),
    }

    rt.engine.positions.append(position)

    rt.LAST_TRADE[m] = now()
    rt.BUY_TIMES.append(now())
    rt.engine.stats["executed"] += 1
    rt.engine.stats["signals"] += 1
    rt.engine.stats["trades"] += 1

    if forced:
        rt.engine.stats["forced_trades"] += 1

    update_open_stats()

    rt.engine.last_signal = (
        f"BUY {m[:6]} {mtype} tier={f.get('_tier','C')} "
        f"ai={f.get('_ai_win_prob',0.5):.2f} via={via} "
        f"score={f.get('_score',0):.4f} dec={token_decimals} out={out_amount}"
    )
    rt.engine.last_trade = rt.engine.last_signal
    _log(rt.engine.last_signal)
    return True


async def sell(p, reason, price, sell_fraction=1.0):
    _ensure_stats()
    _ensure_runtime_dicts()

    m = p["mint"]
    sell_fraction = clamp(sell_fraction, 0.0, 1.0)
    if sell_fraction <= 0:
        return False

    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    entry_value_total = sf(p.get("entry_value", 0.0), 0.0)
    fees_paid_total = sf(p.get("fees_paid_sol", 0.0), 0.0)

    if token_amount <= 0 or entry_value_total <= 0:
        rt.engine.stats["errors"] += 1
        _log(f"SELL_BAD_POSITION {m[:6]}")
        return False

    token_amount_to_sell = token_amount * sell_fraction
    token_amount_remain = max(0.0, token_amount - token_amount_to_sell)

    token_decimals = int(p.get("token_decimals", getattr(rt, "DEFAULT_TOKEN_DECIMALS", 6)))
    atomic_sell = int(token_amount_to_sell * (10 ** token_decimals))

    if atomic_sell <= 0:
        rt.engine.stats["errors"] += 1
        _log(f"SELL_NO_AMOUNT {m[:6]}")
        return False

    prefer_jito = bool(
        getattr(rt, "USE_JITO", False)
        and strategy_bucket_from_mode(p.get("mode")) == "sniper"
        and p.get("tier") == "A+"
    )

    if p.get("paper"):
        res = {"paper": True, "via": "paper"}
        fee_sol = getattr(rt, "ESTIMATED_TX_FEE_SOL", 0.000005)
        exit_value = token_amount_to_sell * price
    else:
        res = await safe_execute_swap(
            m,
            rt.SOL,
            atomic_sell,
            prefer_jito=prefer_jito,
            jito_context={
                "reason": reason,
                "mode": p.get("mode"),
                "tier": p.get("tier"),
                "mint": m,
            },
        )
        fee_sol = extract_fee_sol_from_res(res)

        out_amount_sol_atomic = parse_out_amount(res)
        if out_amount_sol_atomic <= 0:
            q = await safe_quote(m, rt.SOL, atomic_sell)
            out_amount_sol_atomic = parse_out_amount(q)

        if out_amount_sol_atomic > 0:
            exit_value = lamports_to_sol(out_amount_sol_atomic)
        else:
            exit_value = token_amount_to_sell * price

    if not res or res.get("error"):
        rt.engine.stats["errors"] += 1
        _log(f"SELL_FAIL {m[:6]} {res.get('error') if res else 'empty'}")
        return False

    via = res.get("via", "jupiter")
    rt.engine.stats["fees_paid_sol"] += fee_sol

    entry_value_sold = entry_value_total * sell_fraction
    fees_allocated = fees_paid_total * sell_fraction + fee_sol

    pnl_sol = exit_value - entry_value_sold - fees_allocated
    pnl = clamp(
        safe_div(pnl_sol, entry_value_sold, 0.0),
        -getattr(rt, "MAX_PNL_ABS", 0.2),
        getattr(rt, "MAX_PNL_ABS", 0.2),
    )

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
        "mint": m,
        "entry": p.get("entry_price", p.get("entry")),
        "exit": price,
        "pnl": pnl,
        "pnl_sol": pnl_sol,
        "reason": reason,
        "size": entry_value_sold,
        "mode": strategy,
        "source": src,
        "price_source": p.get("price_source"),
        "time_open": p.get("time"),
        "time_close": now(),
        "tx_buy": p.get("tx_buy"),
        "meta": p.get("meta", {}),
        "sell_fraction": sell_fraction,
        "exit_value": exit_value,
        "entry_value": entry_value_sold,
        "fees_paid_sol": fees_allocated,
        "token_amount_sold": token_amount_to_sell,
        "via": via,
    })

    update_breathing_state()
    institutional_loss_pause_if_needed()
    update_open_stats()

    if is_full_exit:
        rt.BLACKLIST[m] = now()
        rt.engine.last_trade = (
            f"SELL {m[:6]} {reason} via={via} "
            f"pnl={pnl:.4f} pnl_sol={pnl_sol:.6f}"
        )
    else:
        rt.engine.last_trade = (
            f"PARTIAL {m[:6]} {reason} via={via} "
            f"pnl={pnl:.4f} pnl_sol={pnl_sol:.6f}"
        )

    _log(rt.engine.last_trade)
    return True


async def execute_ranked_portfolio(ranked, strategy_name="stable", weight=0.3, max_new=1):
    _ensure_stats()
    _ensure_runtime_dicts()

    traded = False
    buys = 0

    ranked = ranked if isinstance(ranked, list) else []
    ranked = sorted(ranked, key=lambda x: x.get("_score", 0.0), reverse=True)

    if not ranked:
        return False

    current_positions = list(getattr(rt.engine, "positions", []) or [])

    for f in ranked:
        if buys >= max_new:
            break
        if not isinstance(f, dict):
            continue

        m = f.get("mint")
        if not m:
            continue

        if any((p.get("mint") == m) for p in current_positions if isinstance(p, dict)):
            continue

        score = sf(f.get("_score", 0.0), 0.0)
        ai_prob = sf(f.get("_ai_win_prob", 0.5), 0.5)

        try:
            base_size = allocate_size(
                score,
                max(len(ranked), 1),
                strategy=strategy_name,
                ai_prob=ai_prob,
            )
        except Exception:
            base_size = 0.0

        try:
            w = float(weight if weight is not None else 0.3)
        except Exception:
            w = 0.3

        w = max(0.05, min(1.0, w))
        pos_size = base_size * w

        min_order = sf(getattr(rt, "MIN_ORDER_SOL", 0.01), 0.01)
        max_pos_size = sf(getattr(rt, "MAX_POSITION_SIZE", 0.03), 0.03)
        capital = sf(getattr(rt.engine, "capital", 0.0), 0.0)

        if pos_size < min_order:
            pos_size = min_order

        pos_size = min(pos_size, max_pos_size, capital)

        if pos_size <= 0:
            continue
        if capital < min_order:
            continue

        try:
            ok = await buy(m, f, pos_size, strategy_name, forced=False)
        except Exception as e:
            rt.engine.stats["errors"] = int(rt.engine.stats.get("errors", 0)) + 1
            _log(f"EXECUTE_RANKED BUY ERROR {m[:6]} {e}")
            ok = False

        if ok:
            buys += 1
            traded = True
            current_positions = list(getattr(rt.engine, "positions", []) or [])

    return traded
