from app.state import engine
from app.engine import runtime as rt
from app.engine.utils import sf


# =========================================================
# INIT
# =========================================================
def _ensure_engine_defaults():
    if not hasattr(engine, "positions") or engine.positions is None:
        engine.positions = []

    if not hasattr(engine, "trade_history") or engine.trade_history is None:
        engine.trade_history = []

    if not hasattr(engine, "stats") or not isinstance(engine.stats, dict):
        engine.stats = {}

    # ⚠️ 不覆蓋 execution already tracking 的值
    defaults = {
        "signals": 0,
        "executed": 0,
        "wins": 0,
        "losses": 0,
        "trades": 0,
        "errors": 0,

        # runtime stats
        "open_positions": 0,
        "open_exposure": 0.0,
        "capital": sf(getattr(engine, "capital", 0.0), 0.0),
        "realized_pnl_sol": 0.0,
        "unrealized_pnl_sol": 0.0,
        "fees_paid_sol": 0.0,

        # extra
        "forced_trades": 0,
        "jito_sent": 0,
        "jito_ok": 0,
        "jito_fail": 0,
    }

    for k, v in defaults.items():
        if k not in engine.stats:
            engine.stats[k] = v


# =========================================================
# CALCULATIONS
# =========================================================
def _calc_open_exposure():
    total = 0.0
    for p in getattr(engine, "positions", []) or []:
        if not isinstance(p, dict):
            continue

        total += sf(
            p.get("entry_value", p.get("size", 0.0)),
            0.0,
        )
    return total


def _calc_unrealized_pnl():
    total = 0.0

    for p in getattr(engine, "positions", []) or []:
        if not isinstance(p, dict):
            continue

        entry_value = sf(p.get("entry_value", p.get("size", 0.0)), 0.0)
        token_amount = sf(p.get("token_amount", 0.0), 0.0)

        mark_price = sf(
            p.get(
                "price",
                p.get("mark_price", p.get("entry_price", p.get("entry", 0.0))),
            ),
            0.0,
        )

        if entry_value <= 0:
            continue

        if token_amount > 0 and mark_price > 0:
            market_value = token_amount * mark_price
        else:
            market_value = entry_value

        total += market_value - entry_value

    return total


# =========================================================
# MAIN UPDATE
# =========================================================
def update_runtime_stats():
    _ensure_engine_defaults()

    # =========================
    # BASIC STATE
    # =========================
    positions = getattr(engine, "positions", []) or []
    trades = getattr(engine, "trade_history", []) or []

    engine.stats["open_positions"] = len(positions)
    engine.stats["open_exposure"] = _calc_open_exposure()
    engine.stats["capital"] = sf(getattr(engine, "capital", 0.0), 0.0)
    engine.stats["unrealized_pnl_sol"] = _calc_unrealized_pnl()

    # =========================
    # TRADE COUNT SYNC（重要）
    # =========================
    engine.stats["trades"] = max(
        int(engine.stats.get("trades", 0)),
        len(trades),
    )

    # =========================
    # FUND BRAIN SNAPSHOT
    # =========================
    try:
        engine.fund_allocator = dict(getattr(rt, "FUND_ALLOCATOR", {}) or {})
    except Exception:
        engine.fund_allocator = {}

    try:
        engine.fund_perf = dict(getattr(rt, "FUND_PERF", {}) or {})
    except Exception:
        engine.fund_perf = {}

    # =========================
    # EXTRA DEBUG（很關鍵）
    # =========================
    try:
        engine.runtime_info = {
            "positions": len(positions),
            "exposure": engine.stats["open_exposure"],
            "capital": engine.stats["capital"],
            "unrealized": engine.stats["unrealized_pnl_sol"],
        }
    except Exception:
        engine.runtime_info = {}

    return engine.stats
