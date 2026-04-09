import time
from collections import deque
from app.state import engine

EQUITY_HISTORY = deque(maxlen=2000)
LAST_METRICS = {}

def calc_equity():
    equity = float(getattr(engine, "capital", 0.0))
    for p in getattr(engine, "positions", []) or []:
        price = p.get("price", p.get("entry", 0.0))
        amount = p.get("token_amount", 0.0)
        equity += amount * price
    return equity

def calc_drawdown(equity):
    peak = float(getattr(engine, "peak_capital", equity))
    peak = max(peak, equity)
    engine.peak_capital = peak
    return (peak - equity) / peak if peak > 0 else 0.0

def update_metrics():
    global LAST_METRICS
    equity = calc_equity()
    drawdown = calc_drawdown(equity)

    EQUITY_HISTORY.append({
        "t": time.time(),
        "equity": equity,
    })

    LAST_METRICS = {
        "summary": {
            "capital": float(getattr(engine, "capital", 0.0)),
            "equity": equity,
            "drawdown": drawdown,
            "positions": len(getattr(engine, "positions", []) or []),
            "running": bool(getattr(engine, "running", False)),
        },
        "stats": getattr(engine, "stats", {}),
        "equity_curve": list(EQUITY_HISTORY)[-200:],
        "timestamp": time.time(),
    }

def get_metrics():
    return LAST_METRICS if LAST_METRICS else {"status": "warming_up"}
