from app.engine import runtime as rt
from app.engine.fund_brain import ensure_fund_state

def ensure_engine():
    rt.engine.positions = getattr(rt.engine, "positions", [])
    rt.engine.trade_history = getattr(rt.engine, "trade_history", [])
    rt.engine.logs = getattr(rt.engine, "logs", [])

    rt.engine.capital = float(getattr(rt.engine, "capital", 5.0))
    rt.engine.start_capital = float(getattr(rt.engine, "start_capital", rt.engine.capital))
    rt.engine.peak_capital = float(getattr(rt.engine, "peak_capital", rt.engine.capital))

    rt.engine.running = getattr(rt.engine, "running", True)
    rt.engine.no_trade_cycles = int(getattr(rt.engine, "no_trade_cycles", 0))

    rt.engine.last_signal = getattr(rt.engine, "last_signal", "")
    rt.engine.last_trade = getattr(rt.engine, "last_trade", "")

    rt.engine.stats = getattr(rt.engine, "stats", {})
    defaults = {
        "signals": 0, "executed": 0, "rejected": 0, "errors": 0,
        "open_positions": 0, "open_exposure": 0.0, "trades": 0,
        "wins": 0, "losses": 0, "forced_trades": 0,
        "fees_paid_sol": 0.0, "realized_pnl_sol": 0.0, "unrealized_pnl_sol": 0.0,
        "jito_sent": 0, "jito_ok": 0, "jito_fail": 0,
    }
    for k, v in defaults.items():
        rt.engine.stats.setdefault(k, v)
    ensure_fund_state()
