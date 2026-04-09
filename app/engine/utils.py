import time
from collections import Counter

from app.engine import runtime as rt

def log(x):
    print(x)
    rt.engine.logs.append(str(x))
    rt.engine.logs = rt.engine.logs[-1200:]

def sf(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def safe_int(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default

def now():
    return time.time()

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def safe_div(a, b, default=0.0):
    try:
        if b == 0:
            return default
        return a / b
    except Exception:
        return default

def valid_mint_like(word: str) -> bool:
    return isinstance(word, str) and 32 <= len(word) <= 44 and word.isalnum()

def parse_out_amount(obj):
    if not isinstance(obj, dict):
        return 0
    candidates = [
        obj.get("outAmount"),
        (obj.get("quote") or {}).get("outAmount"),
        (obj.get("order") or {}).get("outAmount"),
        ((obj.get("routePlan") or [{}])[0] or {}).get("swapInfo", {}).get("outAmount"),
    ]
    for x in candidates:
        v = safe_int(x, 0)
        if v > 0:
            return v
    return 0

def parse_signature(obj):
    if not isinstance(obj, dict):
        return None
    candidates = [
        obj.get("signature"),
        obj.get("result"),
        (obj.get("result") or {}).get("signature") if isinstance(obj.get("result"), dict) else None,
    ]
    for x in candidates:
        if isinstance(x, str) and x:
            return x
    return None

def dedup(tokens):
    seen = set()
    out = []
    for t in tokens:
        m = t.get("mint")
        if not m or m in seen:
            continue
        seen.add(m)
        out.append(t)
    return out

def limit_token_frequency(tokens, max_per_token=2):
    count = Counter()
    out = []
    for t in tokens:
        m = t.get("mint")
        if not m:
            continue
        if count[m] >= max_per_token:
            continue
        count[m] += 1
        out.append(t)
    return out

def recent_closed_trades(n=5):
    return [x for x in (getattr(rt.engine, "trade_history", []) or []) if isinstance(x, dict)][-n:]

def extract_token_decimals(meta):
    d = None
    if isinstance(meta, dict):
        d = meta.get("decimals")
    try:
        d = int(d)
    except Exception:
        d = rt.DEFAULT_TOKEN_DECIMALS
    return max(0, min(d, 12))

def exposure():
    return sum(sf(p.get("entry_value", p.get("size", 0.0))) for p in rt.engine.positions)

def strategy_bucket_from_mode(mode_name: str) -> str:
    mode_name = str(mode_name or "momentum").lower()
    if mode_name in {"sniper", "smart", "momentum", "explore"}:
        return mode_name
    if "snipe" in mode_name:
        return "sniper"
    if "smart" in mode_name:
        return "smart"
    if "explore" in mode_name:
        return "explore"
    return "momentum"

def exposure_by_strategy(strategy_name: str):
    strategy_name = strategy_bucket_from_mode(strategy_name)
    return sum(
        sf(p.get("entry_value", p.get("size", 0.0)))
        for p in rt.engine.positions
        if strategy_bucket_from_mode(p.get("mode")) == strategy_name
    )

def update_open_stats():
    rt.engine.stats["open_positions"] = len(rt.engine.positions)
    rt.engine.stats["open_exposure"] = exposure()

def push_trade(row):
    rt.engine.trade_history.append(row)
    rt.engine.trade_history = rt.engine.trade_history[-1000:]
    rt.engine.stats["trades"] = len(rt.engine.trade_history)

def source_stat_win(src, pnl):
    s = rt.SOURCE_STATS[src]
    s["count"] += 1
    s["wins"] += 1
    s["total_pnl"] += pnl

def source_stat_loss(src, pnl):
    s = rt.SOURCE_STATS[src]
    s["count"] += 1
    s["losses"] += 1
    s["total_pnl"] += pnl

def strategy_stat_update(strategy, pnl):
    s = rt.STRATEGY_STATS[strategy]
    s["count"] += 1
    s["total_pnl"] += pnl
    if pnl > 0:
        s["wins"] += 1
    else:
        s["losses"] += 1

def score_stat_add(name, value):
    s = rt.SCORE_COMPONENT_STATS[name]
    s["count"] += 1
    s["sum"] += sf(value)

def is_a_plus_feature(f):
    return str(f.get("_tier", "C")) == "A+"
