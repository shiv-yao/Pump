import time
from collections import defaultdict, deque

from app.state import engine

EQUITY_HISTORY = deque(maxlen=2000)
LAST_METRICS = {}


# =========================
# SAFE HELPERS
# =========================
def sf(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def si(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def sbool(x, default=False):
    try:
        return bool(x)
    except Exception:
        return default


def ensure_engine_defaults():
    if not hasattr(engine, "capital"):
        engine.capital = 0.0
    if not hasattr(engine, "start_capital"):
        engine.start_capital = sf(getattr(engine, "capital", 0.0), 0.0)
    if not hasattr(engine, "peak_capital"):
        engine.peak_capital = max(
            sf(getattr(engine, "capital", 0.0), 0.0),
            sf(getattr(engine, "start_capital", 0.0), 0.0),
        )
    if not hasattr(engine, "positions") or engine.positions is None:
        engine.positions = []
    if not hasattr(engine, "trade_history") or engine.trade_history is None:
        engine.trade_history = []
    if not hasattr(engine, "logs") or engine.logs is None:
        engine.logs = []
    if not hasattr(engine, "stats") or not isinstance(engine.stats, dict):
        engine.stats = {}
    if not hasattr(engine, "running"):
        engine.running = False
    if not hasattr(engine, "last_signal"):
        engine.last_signal = ""
    if not hasattr(engine, "last_trade"):
        engine.last_trade = ""
    if not hasattr(engine, "no_trade_cycles"):
        engine.no_trade_cycles = 0


# =========================
# CORE METRICS
# =========================
def calc_position_value(p):
    entry_price = sf(p.get("entry_price", p.get("entry", 0.0)), 0.0)
    mark_price = sf(
        p.get("price", p.get("mark_price", p.get("entry_price", p.get("entry", 0.0)))),
        entry_price,
    )
    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    entry_value = sf(p.get("entry_value", p.get("size", 0.0)), 0.0)

    market_value = token_amount * mark_price if token_amount > 0 and mark_price > 0 else entry_value

    return {
        "entry_price": entry_price,
        "mark_price": mark_price,
        "token_amount": token_amount,
        "entry_value": entry_value,
        "market_value": market_value,
    }


def calc_equity():
    ensure_engine_defaults()

    cash = sf(engine.capital, 0.0)
    equity = cash

    for p in getattr(engine, "positions", []):
        pv = calc_position_value(p)
        equity += sf(pv["market_value"], 0.0)

    return equity


def calc_drawdown(equity):
    ensure_engine_defaults()

    peak = sf(getattr(engine, "peak_capital", equity), equity)
    peak = max(peak, sf(equity, 0.0))
    engine.peak_capital = peak

    dd = (peak - equity) / peak if peak > 0 else 0.0
    return dd


def trade_stats():
    ensure_engine_defaults()

    trades = [t for t in getattr(engine, "trade_history", []) if isinstance(t, dict)]

    wins = [t for t in trades if sf(t.get("pnl", 0.0), 0.0) > 0]
    losses = [t for t in trades if sf(t.get("pnl", 0.0), 0.0) <= 0]

    total = len(trades)

    avg_win = sum(sf(t.get("pnl", 0.0), 0.0) for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(sf(t.get("pnl", 0.0), 0.0) for t in losses) / len(losses) if losses else 0.0

    gross_win = sum(sf(t.get("pnl", 0.0), 0.0) for t in wins)
    gross_loss = abs(sum(sf(t.get("pnl", 0.0), 0.0) for t in losses))

    realized_pnl_sol = sum(sf(t.get("pnl_sol", 0.0), 0.0) for t in trades)

    return {
        "trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / total if total else 0.0,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "profit_factor": gross_win / gross_loss if gross_loss else 0.0,
        "expectancy": ((avg_win * len(wins)) + (avg_loss * len(losses))) / total if total else 0.0,
        "realized_pnl_sol": realized_pnl_sol,
    }


def alpha_breakdown():
    ensure_engine_defaults()

    out = defaultdict(lambda: {"pnl": 0.0, "pnl_sol": 0.0, "trades": 0, "wins": 0, "losses": 0})

    for t in getattr(engine, "trade_history", []):
        if not isinstance(t, dict):
            continue

        strat = str(t.get("mode", "unknown"))
        pnl = sf(t.get("pnl", 0.0), 0.0)
        pnl_sol = sf(t.get("pnl_sol", 0.0), 0.0)

        out[strat]["pnl"] += pnl
        out[strat]["pnl_sol"] += pnl_sol
        out[strat]["trades"] += 1

        if pnl > 0:
            out[strat]["wins"] += 1
        else:
            out[strat]["losses"] += 1

    final = {}
    for k, v in out.items():
        t = v["trades"]
        final[k] = {
            **v,
            "win_rate": v["wins"] / t if t else 0.0,
        }
    return final


def exposure_stats():
    ensure_engine_defaults()

    capital = sf(getattr(engine, "capital", 0.0), 0.0)

    exp = 0.0
    by_token = {}
    by_strategy = defaultdict(float)

    for p in getattr(engine, "positions", []):
        if not isinstance(p, dict):
            continue

        mint = p.get("mint", "unknown")
        mode = p.get("mode", "unknown")
        val = sf(p.get("entry_value", p.get("size", 0.0)), 0.0)

        exp += val
        by_token[mint] = by_token.get(mint, 0.0) + val
        by_strategy[mode] += val

    concentration = max(by_token.values()) / exp if by_token and exp > 0 else 0.0

    return {
        "total_exposure": exp,
        "exposure_ratio_vs_cash": exp / capital if capital > 0 else 0.0,
        "concentration": concentration,
        "by_token": by_token,
        "by_strategy": dict(by_strategy),
    }


def open_positions_detail():
    ensure_engine_defaults()

    rows = []
    for p in getattr(engine, "positions", []):
        if not isinstance(p, dict):
            continue

        pv = calc_position_value(p)
        entry_value = sf(pv["entry_value"], 0.0)
        market_value = sf(pv["market_value"], 0.0)
        unrealized_pnl_sol = market_value - entry_value
        unrealized_pnl_pct = unrealized_pnl_sol / entry_value if entry_value > 0 else 0.0

        rows.append({
            "mint": p.get("mint"),
            "mode": p.get("mode"),
            "tier": p.get("tier"),
            "source": p.get("source"),
            "entry_price": pv["entry_price"],
            "mark_price": pv["mark_price"],
            "token_amount": pv["token_amount"],
            "entry_value": entry_value,
            "market_value": market_value,
            "unrealized_pnl_sol": unrealized_pnl_sol,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "wallet_graph_score": sf(p.get("wallet_graph_score", 0.0), 0.0),
            "via": p.get("via"),
            "hold_sec": max(0.0, time.time() - sf(p.get("time", time.time()), time.time())),
        })

    return rows


def update_equity_curve(equity):
    EQUITY_HISTORY.append({
        "t": time.time(),
        "equity": sf(equity, 0.0),
    })


# =========================
# BUILD METRICS
# =========================
def build_metrics():
    ensure_engine_defaults()

    equity = calc_equity()
    drawdown = calc_drawdown(equity)
    update_equity_curve(equity)

    cash = sf(getattr(engine, "capital", 0.0), 0.0)
    start_capital = sf(getattr(engine, "start_capital", cash), cash)
    peak_capital = sf(getattr(engine, "peak_capital", equity), equity)
    total_return = equity - start_capital
    return_pct = total_return / start_capital if start_capital > 0 else 0.0

    stats = dict(getattr(engine, "stats", {}) or {})
    perf = trade_stats()
    risk = exposure_stats()
    positions_detail = open_positions_detail()

    metrics = {
        "summary": {
            "capital": cash,
            "equity": equity,
            "start_capital": start_capital,
            "peak_capital": peak_capital,
            "equity_gain": total_return,
            "return_pct": return_pct,
            "drawdown": drawdown,
            "positions": len(getattr(engine, "positions", []) or []),
            "running": sbool(getattr(engine, "running", False), False),
            "last_signal": getattr(engine, "last_signal", ""),
            "last_trade": getattr(engine, "last_trade", ""),
            "no_trade_cycles": si(getattr(engine, "no_trade_cycles", 0), 0),
        },
        "performance": perf,
        "alpha": alpha_breakdown(),
        "risk": risk,
        "stats": stats,
        "recent_trades": (getattr(engine, "trade_history", []) or [])[-20:],
        "logs": (getattr(engine, "logs", []) or [])[-120:],
        "positions_detail": positions_detail,
        "equity_curve": list(EQUITY_HISTORY)[-300:],
        "timestamp": time.time(),
    }

    try:
        from app.engine import runtime as _rt
        metrics["fund_brain"] = {
            "allocator": dict(getattr(_rt, "FUND_ALLOCATOR", {}) or {}),
            "last_reason": getattr(_rt, "FUND_STATE", {}).get("last_reason", ""),
        }
    except Exception:
        metrics["fund_brain"] = {"allocator": {}, "last_reason": ""}


    metrics["trading"] = {
        "executed": si(stats.get("executed", 0), 0),
        "wins": si(stats.get("wins", 0), 0),
        "losses": si(stats.get("losses", 0), 0),
        "trades": si(stats.get("trades", perf["trades"]), perf["trades"]),
        "errors": si(stats.get("errors", 0), 0),
        "signals": si(stats.get("signals", 0), 0),
        "open_positions": len(getattr(engine, "positions", []) or []),
        "open_exposure": sf(risk.get("total_exposure", 0.0), 0.0),
    }

    return metrics


# =========================
# MEMORY UPDATE
# =========================
def update_metrics():
    global LAST_METRICS
    try:
        LAST_METRICS = build_metrics()
    except Exception as e:
        print("METRICS UPDATE ERROR:", e)
        LAST_METRICS = {
            "status": "metrics_error",
            "error": str(e),
            "timestamp": time.time(),
        }


def get_metrics():
    if not LAST_METRICS:
        update_metrics()
    return LAST_METRICS if LAST_METRICS else {"status": "warming_up"}
