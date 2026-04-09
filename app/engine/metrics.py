import json
import time
from pathlib import Path
from collections import defaultdict

from app.state import engine

METRICS_FILE = Path("metrics.json")

EQUITY_HISTORY = []
MAX_HISTORY = 2000


def calc_equity():
    equity = engine.capital

    for p in getattr(engine, "positions", []):
        price = p.get("price", p.get("entry", 0))
        amount = p.get("token_amount", 0)
        equity += amount * price

    return equity


def calc_drawdown(equity):
    peak = getattr(engine, "peak_capital", equity)
    peak = max(peak, equity)
    engine.peak_capital = peak

    dd = (peak - equity) / peak if peak > 0 else 0
    return dd


def trade_stats():
    trades = getattr(engine, "trade_history", [])

    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]

    total = len(trades)

    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0

    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))

    return {
        "trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / total if total else 0,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": gross_win / gross_loss if gross_loss else 0,
        "expectancy": (avg_win * len(wins) + avg_loss * len(losses)) / total if total else 0,
    }


def alpha_breakdown():
    out = defaultdict(lambda: {"pnl": 0, "trades": 0})

    for t in getattr(engine, "trade_history", []):
        strat = t.get("mode", "unknown")
        out[strat]["pnl"] += t.get("pnl", 0)
        out[strat]["trades"] += 1

    return dict(out)


def exposure_stats():
    total = getattr(engine, "capital", 0)

    exp = 0
    by_token = {}

    for p in getattr(engine, "positions", []):
        val = p.get("entry_value", 0)
        exp += val
        by_token[p["mint"]] = val

    return {
        "total_exposure": exp,
        "exposure_ratio": exp / total if total else 0,
        "concentration": max(by_token.values()) / exp if by_token and exp else 0,
    }


def update_equity_curve(equity):
    EQUITY_HISTORY.append({
        "t": time.time(),
        "equity": equity
    })

    if len(EQUITY_HISTORY) > MAX_HISTORY:
        del EQUITY_HISTORY[:-MAX_HISTORY]


def build_metrics():
    equity = calc_equity()
    drawdown = calc_drawdown(equity)

    update_equity_curve(equity)

    return {
        "summary": {
            "capital": engine.capital,
            "equity": equity,
            "drawdown": drawdown,
            "positions": len(engine.positions),
            "running": engine.running,
        },
        "performance": trade_stats(),
        "alpha": alpha_breakdown(),
        "risk": exposure_stats(),
        "equity_curve": EQUITY_HISTORY[-300:],  # recent
        "timestamp": time.time(),
    }


def save_metrics():
    try:
        METRICS_FILE.write_text(json.dumps(build_metrics(), indent=2))
    except Exception as e:
        print("METRICS ERROR:", e)
