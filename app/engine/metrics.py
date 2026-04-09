import time
from collections import Counter

from app.engine import runtime as rt
from app.engine.agent import agent_effective_entry_threshold, agent_effective_sl, agent_effective_tp
from app.engine.fund_brain import _fund_perf
from app.engine.risk import breathing_risk_mult, buy_window_count, detect_regime, institutional_daily_loss_hit, institutional_paused
from app.engine.sources import get_price
from app.engine.utils import exposure, exposure_by_strategy, safe_div, sf

async def calc_position_market_value(p):
    price = await get_price(p["mint"])
    if price is None or price <= 0:
        return sf(p.get("entry_value", 0.0), 0.0), sf(p.get("entry_price", 0.0), 0.0)
    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    return token_amount * price, price

async def calc_unrealized_pnl_sol():
    total = 0.0
    for p in list(rt.engine.positions or []):
        entry_value = sf(p.get("entry_value", 0.0), 0.0)
        fees_paid = sf(p.get("fees_paid_sol", 0.0), 0.0)
        mv, _ = await calc_position_market_value(p)
        total += (mv - entry_value - fees_paid)
    return total

async def calc_equity():
    if not rt.ENABLE_EQUITY_MARK:
        return sf(rt.engine.capital, 0.0)
    total = sf(rt.engine.capital, 0.0)
    for p in list(rt.engine.positions or []):
        mv, _ = await calc_position_market_value(p)
        total += mv
    return total

def _avg_stat(name):
    s = rt.SCORE_COMPONENT_STATS.get(name, {"count": 0, "sum": 0.0})
    c = s.get("count", 0)
    return {"count": c, "avg_score": (s.get("sum", 0.0) / c if c else 0.0)}

def _source_perf(src):
    s = rt.SOURCE_STATS.get(src, {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
    c = s["count"]
    return {"count": c, "wins": s["wins"], "losses": s["losses"], "total_pnl": s["total_pnl"], "avg_pnl": s["total_pnl"] / c if c else 0.0, "win_rate": s["wins"] / c if c else 0.0}

def _strategy_perf(name):
    s = rt.STRATEGY_STATS.get(name, {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
    c = s["count"]
    return {"count": c, "wins": s["wins"], "losses": s["losses"], "total_pnl": s["total_pnl"], "avg_pnl": s["total_pnl"] / c if c else 0.0, "win_rate": s["wins"] / c if c else 0.0}

async def update_peak_capital():
    eq = await calc_equity() if rt.ENABLE_EQUITY_MARK else sf(rt.engine.capital, 0.0)
    rt.engine.peak_capital = max(sf(rt.engine.peak_capital), sf(eq))

async def get_metrics_async():
    start_capital = sf(rt.engine.start_capital, 5.0)
    cash = sf(rt.engine.capital, start_capital)
    equity = await calc_equity()
    unrealized = await calc_unrealized_pnl_sol()
    rt.engine.stats["unrealized_pnl_sol"] = unrealized
    capital = equity
    peak = max(sf(rt.engine.peak_capital, capital), capital)
    total_return = capital - start_capital
    return_pct = total_return / start_capital if start_capital > 0 else 0.0
    drawdown = ((peak - capital) / peak) if peak > 0 else 0.0
    wins = int(rt.engine.stats.get("wins", 0))
    losses = int(rt.engine.stats.get("losses", 0))
    trades = int(rt.engine.stats.get("trades", 0))
    win_pnls = [sf(x.get("pnl")) for x in rt.engine.trade_history if sf(x.get("pnl")) > 0]
    loss_pnls = [sf(x.get("pnl")) for x in rt.engine.trade_history if sf(x.get("pnl")) <= 0]
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    gross_win = sum(win_pnls)
    gross_loss = abs(sum(loss_pnls))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else 0.0
    source_perf = {k: _source_perf(k) for k in rt.SOURCE_STATS.keys()}
    strategy_perf = {k: _strategy_perf(k) for k in rt.STRATEGY_STATS.keys()}
    fund_perf = {k: _fund_perf(k) for k in ["sniper", "smart", "momentum", "explore"]}

    open_positions_detail = []
    for p in (rt.engine.positions or []):
        px = await get_price(p.get("mint"))
        token_amount = sf(p.get("token_amount", 0.0), 0.0)
        mv = token_amount * px if px else 0.0
        entry_value = sf(p.get("entry_value", 0.0), 0.0)
        u_pnl_sol = mv - entry_value if px else 0.0
        u_pnl_pct = safe_div(u_pnl_sol, entry_value, 0.0)
        open_positions_detail.append({
            "mint": p.get("mint"), "tier": p.get("tier"), "source": p.get("source"), "mode": p.get("mode"),
            "entry": p.get("entry_price", p.get("entry")), "size": p.get("size_sol", p.get("size")),
            "entry_value": entry_value, "token_amount": token_amount, "mark_price": px, "market_value": mv,
            "unrealized_pnl_sol": u_pnl_sol, "unrealized_pnl_pct": u_pnl_pct,
            "hold_sec": round(time.time() - sf(p.get("time"), time.time()), 2), "high": p.get("high"),
            "price_source": p.get("price_source"), "last_momentum": sf(rt.LAST_MOMENTUM.get(p.get("mint"), 0.0), 0.0),
            "wallet_graph_score": sf(p.get("wallet_graph_score", 0.0), 0.0), "via": p.get("via"),
        })
    return {
        "summary": {"capital": capital, "cash": cash, "equity": equity, "unrealized_pnl_sol": unrealized, "realized_pnl_sol": sf(rt.engine.stats.get("realized_pnl_sol", 0.0), 0.0), "fees_paid_sol": sf(rt.engine.stats.get("fees_paid_sol", 0.0), 0.0), "start_capital": start_capital, "peak_capital": peak, "equity_gain": total_return, "return_pct": return_pct, "drawdown": drawdown, "running": bool(rt.engine.running), "mode": "REAL" if rt.REAL_TRADING else "PAPER", "regime": detect_regime()},
        "performance": {"trades": trades, "wins": wins, "losses": losses, "win_rate": (wins / trades) if trades else 0.0, "avg_win": avg_win, "avg_loss": avg_loss, "profit_factor": profit_factor, "total_return": total_return},
        "trading": {"signals": rt.engine.stats.get("signals", 0), "executed": rt.engine.stats.get("executed", 0), "rejected": rt.engine.stats.get("rejected", 0), "errors": rt.engine.stats.get("errors", 0), "open_positions": len(rt.engine.positions), "open_exposure": exposure(), "forced_trades": rt.engine.stats.get("forced_trades", 0), "no_trade_cycles": rt.engine.no_trade_cycles, "breathing_risk_mult": breathing_risk_mult(), "breathing_cooldown_left": max(0, int(sf(rt.BREATHING_STATE.get("cooldown_until", 0.0), 0.0) - time.time())), "buy_window_count": buy_window_count(), "agent_mode": rt.AGENT_STATE.get("mode"), "agent_risk_mult": rt.AGENT_STATE.get("risk_mult"), "agent_confidence": rt.AGENT_STATE.get("confidence"), "agent_cooldown_left": max(0, int(sf(rt.AGENT_STATE.get("cooldown_until", 0.0), 0.0) - time.time())), "agent_reason": rt.AGENT_STATE.get("last_reason"), "auto_entry_threshold": agent_effective_entry_threshold(), "auto_take_profit": agent_effective_tp(), "auto_stop_loss": agent_effective_sl()},
        "fund_brain": {"allocator": dict(rt.FUND_ALLOCATOR), "strategy_perf": fund_perf, "last_update": rt.FUND_STATE.get("last_update"), "last_reason": rt.FUND_STATE.get("last_reason")},
        "jito": {"enabled": rt.USE_JITO, "sent": rt.JITO_STATS["sent"], "ok": rt.JITO_STATS["ok"], "fail": rt.JITO_STATS["fail"], "last_error": rt.JITO_STATS["last_error"]},
        "institutional": {"paused": institutional_paused(), "pause_left": max(0, int(sf(rt.INSTITUTIONAL_STATE.get("pause_until", 0.0), 0.0) - time.time())), "daily_realized_pnl_sol": sf(rt.INSTITUTIONAL_STATE.get("daily_realized_pnl_sol", 0.0), 0.0), "daily_loss_limit_sol": rt.DAILY_LOSS_LIMIT_SOL, "last_reason": rt.INSTITUTIONAL_STATE.get("last_reason")},
        "positions": rt.engine.positions, "recent_trades": rt.engine.trade_history[-20:], "logs": rt.engine.logs[-120:], "source_stats": source_perf, "strategy_stats": strategy_perf,
        "score_component_stats": {k: _avg_stat(k) for k in ["breakout", "smart_money", "liquidity", "momentum", "wallet_count", "price", "wallet_graph_score"]},
        "portfolio": {"positions_by_source": dict(Counter([p.get("source", "unknown") for p in rt.engine.positions])), "positions_by_strategy": dict(Counter([p.get("mode", "unknown") for p in rt.engine.positions])), "total_exposure_ratio": exposure() / capital if capital > 0 else 0.0, "strategy_exposure": {k: exposure_by_strategy(k) for k in ["sniper", "smart", "momentum", "explore"]}},
        "open_positions_detail": open_positions_detail,
    }

def get_metrics():
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        return {
            "summary": {"capital": sf(rt.engine.capital, 0.0), "cash": sf(rt.engine.capital, 0.0), "start_capital": sf(rt.engine.start_capital, 0.0), "peak_capital": sf(rt.engine.peak_capital, 0.0), "equity_gain": sf(rt.engine.capital, 0.0) - sf(rt.engine.start_capital, 0.0), "return_pct": safe_div(sf(rt.engine.capital, 0.0) - sf(rt.engine.start_capital, 0.0), sf(rt.engine.start_capital, 0.0), 0.0), "drawdown": 0.0, "running": bool(rt.engine.running), "mode": "REAL" if rt.REAL_TRADING else "PAPER", "regime": detect_regime()},
            "positions": rt.engine.positions, "recent_trades": rt.engine.trade_history[-20:], "logs": rt.engine.logs[-120:],
        }
    return asyncio.run(get_metrics_async())
