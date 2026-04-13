import time
from collections import defaultdict


# =========================================================
# BASIC SAFE HELPERS
# =========================================================
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


def now():
    return time.time()


def clamp(x, lo, hi):
    x = sf(x, lo)
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def safe_div(a, b, default=0.0):
    a = sf(a, 0.0)
    b = sf(b, 0.0)
    if abs(b) <= 1e-12:
        return default
    return a / b


# =========================================================
# LOG
# =========================================================
def log(msg):
    print(msg)
    try:
        from app.state import engine
        if not hasattr(engine, "logs") or engine.logs is None:
            engine.logs = []
        engine.logs.append(str(msg))
        engine.logs = engine.logs[-1200:]
    except Exception:
        pass


# =========================================================
# MINT / DEDUP
# =========================================================
def valid_mint_like(x):
    if not isinstance(x, str):
        return False
    x = x.strip()
    if len(x) < 32 or len(x) > 48:
        return False

    allowed = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return all(c in allowed for c in x)


def dedup(rows):
    out = []
    seen = set()

    for r in rows or []:
        if not isinstance(r, dict):
            continue

        mint = r.get("mint")
        if not mint:
            continue

        if mint in seen:
            continue

        seen.add(mint)
        out.append(r)

    return out


# =========================================================
# QUOTE / TX PARSERS
# =========================================================
def parse_out_amount(q):
    if not isinstance(q, dict):
        return 0

    candidates = [
        q.get("outAmount"),
        (q.get("quote") or {}).get("outAmount"),
        (q.get("data") or {}).get("outAmount"),
        q.get("amount_out"),
        q.get("amountOut"),
    ]

    for x in candidates:
        try:
            if x is None:
                continue
            return int(float(x))
        except Exception:
            pass

    return 0


def parse_signature(res):
    if not isinstance(res, dict):
        return ""

    candidates = [
        res.get("signature"),
        res.get("txid"),
        res.get("sig"),
        (res.get("data") or {}).get("signature"),
        (res.get("result") or {}).get("signature") if isinstance(res.get("result"), dict) else None,
    ]

    for x in candidates:
        if isinstance(x, str) and x.strip():
            return x.strip()

    return ""


def extract_token_decimals(meta, default=6):
    if not isinstance(meta, dict):
        return default

    candidates = [
        meta.get("decimals"),
        meta.get("token_decimals"),
        (meta.get("baseToken") or {}).get("decimals") if isinstance(meta.get("baseToken"), dict) else None,
        (meta.get("token") or {}).get("decimals") if isinstance(meta.get("token"), dict) else None,
        (meta.get("output_token") or {}).get("decimals") if isinstance(meta.get("output_token"), dict) else None,
    ]

    for x in candidates:
        try:
            v = int(x)
            if 0 <= v <= 18:
                return v
        except Exception:
            pass

    return default


# =========================================================
# POSITION / MARK-TO-MARKET
# =========================================================
def calc_position_market_value(p):
    if not isinstance(p, dict):
        return 0.0

    entry_value = sf(p.get("entry_value", p.get("size", 0.0)), 0.0)
    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    mark_price = sf(
        p.get("price", p.get("mark_price", p.get("entry_price", p.get("entry", 0.0)))),
        0.0,
    )

    if token_amount > 0 and mark_price > 0:
        return token_amount * mark_price

    return entry_value


def calc_position_unrealized_pnl(p):
    if not isinstance(p, dict):
        return 0.0

    entry_value = sf(p.get("entry_value", p.get("size", 0.0)), 0.0)
    market_value = calc_position_market_value(p)
    return market_value - entry_value


def mark_position_to_market(p, mark_price):
    if not isinstance(p, dict):
        return

    mp = sf(mark_price, 0.0)
    if mp <= 0:
        return

    p["price"] = mp
    p["mark_price"] = mp

    current_high = sf(p.get("high", 0.0), 0.0)
    if current_high <= 0:
        current_high = sf(p.get("entry_price", p.get("entry", mp)), mp)
    p["high"] = max(current_high, mp)


def mark_all_positions_to_market(price_map):
    try:
        from app.state import engine
    except Exception:
        return

    if not isinstance(price_map, dict):
        return

    for p in getattr(engine, "positions", []) or []:
        if not isinstance(p, dict):
            continue
        mint = p.get("mint")
        if not mint:
            continue
        mark_price = sf(price_map.get(mint), 0.0)
        if mark_price > 0:
            mark_position_to_market(p, mark_price)


# =========================================================
# ENGINE / TRADE HELPERS
# =========================================================
def push_trade(trade):
    try:
        from app.state import engine
        if not hasattr(engine, "trade_history") or engine.trade_history is None:
            engine.trade_history = []
        engine.trade_history.append(trade)
        engine.trade_history = engine.trade_history[-1000:]
    except Exception:
        pass


def update_open_stats():
    try:
        from app.state import engine
    except Exception:
        return

    positions = getattr(engine, "positions", []) or []

    if not hasattr(engine, "stats") or not isinstance(engine.stats, dict):
        engine.stats = {}

    open_exposure = 0.0
    unrealized_pnl = 0.0

    for p in positions:
        if not isinstance(p, dict):
            continue

        entry_value = sf(p.get("entry_value", p.get("size", 0.0)), 0.0)
        open_exposure += entry_value
        unrealized_pnl += calc_position_unrealized_pnl(p)

    engine.stats["open_positions"] = len(positions)
    engine.stats["open_exposure"] = open_exposure
    engine.stats["unrealized_pnl_sol"] = unrealized_pnl


# =========================================================
# SOURCE / STRATEGY STATS
# =========================================================
def source_stat_win(src, pnl=0.0):
    try:
        from app.engine import runtime as rt
        if not hasattr(rt, "SOURCE_STATS") or rt.SOURCE_STATS is None:
            rt.SOURCE_STATS = defaultdict(
                lambda: {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0}
            )

        s = rt.SOURCE_STATS[src]
        s["count"] += 1
        s["wins"] += 1
        s["total_pnl"] += sf(pnl, 0.0)
    except Exception:
        pass


def source_stat_loss(src, pnl=0.0):
    try:
        from app.engine import runtime as rt
        if not hasattr(rt, "SOURCE_STATS") or rt.SOURCE_STATS is None:
            rt.SOURCE_STATS = defaultdict(
                lambda: {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0}
            )

        s = rt.SOURCE_STATS[src]
        s["count"] += 1
        s["losses"] += 1
        s["total_pnl"] += sf(pnl, 0.0)
    except Exception:
        pass


def strategy_stat_update(strategy, pnl=0.0):
    try:
        from app.engine import runtime as rt
        if not hasattr(rt, "STRATEGY_STATS") or rt.STRATEGY_STATS is None:
            rt.STRATEGY_STATS = defaultdict(
                lambda: {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0}
            )

        s = rt.STRATEGY_STATS[strategy]
        s["count"] += 1
        if sf(pnl, 0.0) > 0:
            s["wins"] += 1
        else:
            s["losses"] += 1
        s["total_pnl"] += sf(pnl, 0.0)
    except Exception:
        pass


def score_stat_add(name, value):
    try:
        from app.engine import runtime as rt
        if not hasattr(rt, "SCORE_COMPONENT_STATS") or rt.SCORE_COMPONENT_STATS is None:
            rt.SCORE_COMPONENT_STATS = defaultdict(lambda: {"count": 0, "sum": 0.0})

        s = rt.SCORE_COMPONENT_STATS[name]
        s["count"] += 1
        s["sum"] += sf(value, 0.0)
    except Exception:
        pass


# =========================================================
# MODE NORMALIZER
# =========================================================
def strategy_bucket_from_mode(mode):
    m = str(mode or "").lower().strip()

    if m in {"stable"}:
        return "stable"

    if m in {"sniper", "early", "mempool"}:
        return "sniper"

    if m in {"smart", "smart_money", "wallet"}:
        return "smart"

    if m in {"momentum", "breakout", "trend"}:
        return "momentum"

    if m in {"explore", "experimental"}:
        return "explore"

    return "momentum"


# =========================================================
# RECENT CLOSED TRADES
# =========================================================
def recent_closed_trades(limit=20):
    try:
        from app.state import engine

        trades = getattr(engine, "trade_history", []) or []
        rows = []

        for t in reversed(trades):
            if not isinstance(t, dict):
                continue

            rows.append({
                "mint": t.get("mint"),
                "mode": t.get("mode"),
                "entry": sf(t.get("entry", 0.0), 0.0),
                "exit": sf(t.get("exit", 0.0), 0.0),
                "pnl": sf(t.get("pnl", 0.0), 0.0),
                "pnl_sol": sf(t.get("pnl_sol", 0.0), 0.0),
                "reason": t.get("reason", ""),
                "time_open": t.get("time_open"),
                "time_close": t.get("time_close"),
                "source": t.get("source", ""),
                "via": t.get("via", ""),
            })

            if len(rows) >= int(limit):
                break

        return rows

    except Exception:
        return []


def get_recent_closed_trades(limit=20):
    return recent_closed_trades(limit=limit)
