import time

def now():
    return time.time()

def sf(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def si(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default

def clamp(x, lo, hi):
    try:
        x = float(x)
    except Exception:
        x = lo
    return max(lo, min(hi, x))

def safe_div(a, b, default=0.0):
    try:
        a = float(a)
        b = float(b)
        if abs(b) < 1e-18:
            return default
        return a / b
    except Exception:
        return default

def log(msg):
    print(msg)

def dedup(rows):
    out = []
    seen = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        mint = r.get("mint")
        if not mint or mint in seen:
            continue
        seen.add(mint)
        out.append(r)
    return out

def valid_mint_like(s):
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    return 30 <= len(s) <= 50

def parse_signature(res):
    if not isinstance(res, dict):
        return ""

    for k in ["signature", "txid", "tx_sig", "sig"]:
        v = res.get(k)
        if v:
            return str(v)

    quote = res.get("quote") or {}
    for k in ["signature", "txid", "tx_sig", "sig"]:
        v = quote.get(k)
        if v:
            return str(v)

    return ""

def parse_out_amount(obj):
    if obj is None:
        return 0
    if isinstance(obj, (int, float)):
        return int(obj)
    if not isinstance(obj, dict):
        return 0

    candidates = [
        obj.get("outAmount"),
        obj.get("out_amount"),
        obj.get("amount_out"),
        obj.get("outputAmount"),
        (obj.get("quote") or {}).get("outAmount"),
        (obj.get("quote") or {}).get("out_amount"),
        (obj.get("quote") or {}).get("amount_out"),
        (obj.get("quote") or {}).get("outputAmount"),
    ]

    for v in candidates:
        try:
            if v is None:
                continue
            iv = int(float(v))
            if iv > 0:
                return iv
        except Exception:
            pass

    return 0

def extract_token_decimals(meta):
    if not isinstance(meta, dict):
        return 6

    candidates = [
        meta.get("decimals"),
        meta.get("token_decimals"),
        (meta.get("output_token") or {}).get("decimals") if isinstance(meta.get("output_token"), dict) else None,
        (meta.get("baseToken") or {}).get("decimals") if isinstance(meta.get("baseToken"), dict) else None,
        (meta.get("token") or {}).get("decimals") if isinstance(meta.get("token"), dict) else None,
    ]

    for v in candidates:
        try:
            iv = int(v)
            if 0 <= iv <= 18:
                return iv
        except Exception:
            pass

    return 6

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

def update_open_stats():
    try:
        from app.state import engine
    except Exception:
        return

    positions = getattr(engine, "positions", []) or []
    if not hasattr(engine, "stats") or not isinstance(engine.stats, dict):
        engine.stats = {}

    open_exposure = 0.0
    for p in positions:
        if not isinstance(p, dict):
            continue
        open_exposure += sf(p.get("entry_value", p.get("size", 0.0)), 0.0)

    engine.stats["open_positions"] = len(positions)
    engine.stats["open_exposure"] = open_exposure


def source_stat_win(src, pnl=0.0):
    try:
        from app.engine import runtime as rt
        if not hasattr(rt, "SOURCE_STATS") or rt.SOURCE_STATS is None:
            rt.SOURCE_STATS = {}
        s = rt.SOURCE_STATS.setdefault(src, {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
        s["count"] += 1
        s["wins"] += 1
        s["total_pnl"] += sf(pnl, 0.0)
    except Exception:
        pass


def source_stat_loss(src, pnl=0.0):
    try:
        from app.engine import runtime as rt
        if not hasattr(rt, "SOURCE_STATS") or rt.SOURCE_STATS is None:
            rt.SOURCE_STATS = {}
        s = rt.SOURCE_STATS.setdefault(src, {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
        s["count"] += 1
        s["losses"] += 1
        s["total_pnl"] += sf(pnl, 0.0)
    except Exception:
        pass


def strategy_stat_update(strategy, pnl=0.0):
    try:
        from app.engine import runtime as rt
        if not hasattr(rt, "STRATEGY_STATS") or rt.STRATEGY_STATS is None:
            rt.STRATEGY_STATS = {}
        s = rt.STRATEGY_STATS.setdefault(strategy, {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
        s["count"] += 1
        if sf(pnl, 0.0) > 0:
            s["wins"] += 1
        else:
            s["losses"] += 1
        s["total_pnl"] += sf(pnl, 0.0)
    except Exception:
        pass


def push_trade(trade):
    try:
        from app.state import engine
        if not hasattr(engine, "trade_history") or engine.trade_history is None:
            engine.trade_history = []
        engine.trade_history.append(trade)
        engine.trade_history = engine.trade_history[-1000:]
    except Exception:
        pass


def score_stat_add(name, value):
    try:
        from app.engine import runtime as rt
        if not hasattr(rt, "SCORE_COMPONENT_STATS") or rt.SCORE_COMPONENT_STATS is None:
            rt.SCORE_COMPONENT_STATS = {}
        s = rt.SCORE_COMPONENT_STATS.setdefault(name, {"count": 0, "sum": 0.0})
        s["count"] += 1
        s["sum"] += sf(value, 0.0)
    except Exception:
        pass
