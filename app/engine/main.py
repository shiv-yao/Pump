import asyncio
import time

from app.state import engine

# =========================
# SAFE IMPORT（避免炸）
# =========================
try:
    from app.engine.fund import update_fund_allocator
except Exception:
    def update_fund_allocator(*args, **kwargs):
        return None

try:
    from app.engine.agent import agent_update, agent_adjust_params
except Exception:
    def agent_update():
        return None

    def agent_adjust_params():
        return None

try:
    from app.engine.execution import execute_portfolio
except Exception:
    async def execute_portfolio(*args, **kwargs):
        return False

try:
    from app.engine.features import fetch_alpha_candidates
except Exception:
    async def fetch_alpha_candidates():
        return []

try:
    from app.engine.risk import check_sell
except Exception:
    async def check_sell(_p):
        return False

try:
    from app.engine.state_runtime import update_runtime_stats
except Exception:
    def update_runtime_stats():
        return None

try:
    from app.engine.metrics import save_metrics
except Exception:
    def save_metrics():
        return None


# =========================
# HELPERS
# =========================
def _ensure_attr(name, default):
    if not hasattr(engine, name):
        setattr(engine, name, default)
    return getattr(engine, name)


def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def _log(msg: str):
    print(msg)
    try:
        if not hasattr(engine, "logs") or engine.logs is None:
            engine.logs = []
        engine.logs.append(str(msg))
        engine.logs = engine.logs[-1200:]
    except Exception:
        pass


def _update_basic_runtime(traded: bool):
    try:
        engine.last_loop_ts = time.time()
    except Exception:
        pass

    try:
        if traded:
            engine.no_trade_cycles = 0
        else:
            engine.no_trade_cycles = _safe_int(getattr(engine, "no_trade_cycles", 0), 0) + 1
    except Exception:
        pass

    try:
        if hasattr(engine, "stats") and isinstance(engine.stats, dict):
            engine.stats["open_positions"] = len(getattr(engine, "positions", []) or [])
            engine.stats["capital"] = _safe_float(getattr(engine, "capital", 0.0), 0.0)
    except Exception:
        pass


# =========================
# INIT
# =========================
async def start_once():
    engine.running = True

    _ensure_attr("positions", [])
    _ensure_attr("trade_history", [])
    _ensure_attr("logs", [])

    engine.capital = _safe_float(getattr(engine, "capital", 5.0), 5.0)
    engine.start_capital = _safe_float(getattr(engine, "start_capital", engine.capital), engine.capital)
    engine.peak_capital = _safe_float(getattr(engine, "peak_capital", engine.capital), engine.capital)

    engine.no_trade_cycles = _safe_int(getattr(engine, "no_trade_cycles", 0), 0)
    engine.last_signal = getattr(engine, "last_signal", "")
    engine.last_trade = getattr(engine, "last_trade", "")
    engine.last_loop_ts = getattr(engine, "last_loop_ts", 0.0)

    if not hasattr(engine, "stats") or not isinstance(engine.stats, dict):
        engine.stats = {}

    defaults = {
        "executed": 0,
        "wins": 0,
        "losses": 0,
        "trades": 0,
        "errors": 0,
        "signals": 0,
        "open_positions": len(engine.positions),
        "capital": engine.capital,
        "realized_pnl_sol": 0.0,
        "unrealized_pnl_sol": 0.0,
        "fees_paid_sol": 0.0,
        "forced_trades": 0,
        "jito_sent": 0,
        "jito_ok": 0,
        "jito_fail": 0,
    }
    for k, v in defaults.items():
        engine.stats.setdefault(k, v)

    try:
        update_fund_allocator(force=True)
    except Exception as e:
        _log(f"FUND INIT ERROR: {e}")

    try:
        save_metrics()
    except Exception as e:
        _log(f"METRICS INIT ERROR: {e}")

    _log("✅ ENGINE START_ONCE OK")


# =========================
# MAIN LOOP
# =========================
async def main_loop():
    await start_once()

    _log("🔥 V74 TRUE FUSION GOD MODE START")

    while engine.running:
        traded = False

        try:
            # ================= AI =================
            try:
                agent_update()
            except Exception as e:
                _log(f"AGENT UPDATE ERROR: {e}")

            try:
                agent_adjust_params()
            except Exception as e:
                _log(f"AGENT PARAM ERROR: {e}")

            # ================= FUND =================
            try:
                update_fund_allocator()
            except Exception as e:
                _log(f"FUND UPDATE ERROR: {e}")

            # ================= FETCH =================
            try:
                tokens = await fetch_alpha_candidates()
                if not isinstance(tokens, list):
                    tokens = []
            except Exception as e:
                _log(f"FETCH ERROR: {e}")
                tokens = []

            # ================= SELL =================
            for p in list(getattr(engine, "positions", []) or []):
                try:
                    await check_sell(p)
                except Exception as e:
                    _log(f"SELL ERROR: {e}")

            # ================= BUY =================
            try:
                traded = await execute_portfolio(tokens)
            except Exception as e:
                _log(f"EXEC ERROR: {e}")
                traded = False

            # ================= BASIC RUNTIME =================
            try:
                _update_basic_runtime(traded)
            except Exception as e:
                _log(f"RUNTIME UPDATE ERROR: {e}")

            # ================= STATS =================
            try:
                update_runtime_stats()
            except Exception as e:
                _log(f"STATS ERROR: {e}")

            # ================= METRICS =================
            try:
                save_metrics()
            except Exception as e:
                _log(f"METRICS ERROR: {e}")

            # ================= DEBUG =================
            _log(
                f"LOOP | capital={_safe_float(getattr(engine, 'capital', 0.0), 0.0):.4f} "
                f"positions={len(getattr(engine, 'positions', []) or [])} "
                f"traded={traded} "
                f"no_trade_cycles={_safe_int(getattr(engine, 'no_trade_cycles', 0), 0)}"
            )

        except Exception as e:
            try:
                engine.stats["errors"] = _safe_int(engine.stats.get("errors", 0), 0) + 1
            except Exception:
                pass
            _log(f"ENGINE LOOP ERROR: {e}")

        await asyncio.sleep(2)
