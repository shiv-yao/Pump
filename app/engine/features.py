import asyncio
import random
from collections import defaultdict

from app.alpha.adaptive_filter import adaptive_filter
from app.alpha.helius_wallet_tracker import update_token_wallets
from app.engine import runtime as rt
from app.engine.fund_brain import fund_multiplier
from app.engine.strategy_router import apply_strategy_boost
from app.engine.risk import detect_regime
from app.engine.sources import get_price, get_price_info
from app.engine.utils import clamp, now, score_stat_add, sf
from app.state import engine

try:
    from app.engine.ai_predictor import predict_trade_quality
except Exception:
    def predict_trade_quality(f):
        return {
            "win_prob": 0.5,
            "expected_pnl": 0.0,
            "score": 0.0,
        }


def _ensure_runtime_state():
    if not hasattr(rt, "WALLET_GRAPH_CACHE") or rt.WALLET_GRAPH_CACHE is None:
        rt.WALLET_GRAPH_CACHE = {}
    if not hasattr(rt, "MEMPOOL_SEEN_TS") or rt.MEMPOOL_SEEN_TS is None:
        rt.MEMPOOL_SEEN_TS = {}
    if not hasattr(rt, "MEMPOOL_HITS") or rt.MEMPOOL_HITS is None:
        rt.MEMPOOL_HITS = defaultdict(int)
    if not hasattr(rt, "LAST_PRICE") or rt.LAST_PRICE is None:
        rt.LAST_PRICE = {}
    if not hasattr(rt, "LAST_MOMENTUM") or rt.LAST_MOMENTUM is None:
        rt.LAST_MOMENTUM = {}
    if not hasattr(rt, "LAST_PRICE_SOURCE") or rt.LAST_PRICE_SOURCE is None:
        rt.LAST_PRICE_SOURCE = {}
    if not hasattr(rt, "TOKEN_TRADE_COUNT") or rt.TOKEN_TRADE_COUNT is None:
        rt.TOKEN_TRADE_COUNT = defaultdict(int)
    if not hasattr(rt, "SOURCE_STATS") or rt.SOURCE_STATS is None:
        rt.SOURCE_STATS = defaultdict(
            lambda: {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0}
        )


def _get_wallet_graph_fn():
    fn = getattr(rt, "get_wallet_graph_score", None)
    if callable(fn):
        return fn

    async def _fallback(_mint: str, wallets=None):
        return {
            "score": 0.0,
            "cluster_size": 0,
            "smart_ratio": 0.0,
            "concentration": 0.0,
            "fresh_wallet_ratio": 0.0,
        }

    return _fallback


async def safe_update_token_wallets(mint: str):
    try:
        return await asyncio.wait_for(
            update_token_wallets(mint),
            timeout=getattr(rt, "WALLET_TRACKER_TIMEOUT_SEC", 1.2),
        )
    except Exception:
        return []


def safe_adaptive_filter(feature_row, _context=None, _no_trade_cycles=0):
    try:
        ok, meta = adaptive_filter(feature_row, _context, _no_trade_cycles)
        return bool(ok), meta if isinstance(meta, dict) else {}
    except Exception:
        score = sf(feature_row.get("_score", feature_row.get("score", 0.0)), 0.0)
        liq = sf(feature_row.get("liq", 0.0), 0.0)
        breakout = sf(feature_row.get("breakout", 0.0), 0.0)
        ok = score >= 0.08 and liq >= 3000 and breakout > -0.03
        return ok, {"fallback": True}


async def safe_wallet_graph_score(mint: str, wallets=None):
    _ensure_runtime_state()

    cached = rt.WALLET_GRAPH_CACHE.get(mint)
    if cached and now() - cached.get("_ts", 0.0) < 20:
        return cached

    graph_fn = _get_wallet_graph_fn()

    try:
        res = await asyncio.wait_for(
            graph_fn(mint, wallets=wallets),
            timeout=getattr(rt, "WALLET_GRAPH_TIMEOUT_SEC", 1.0),
        )
        if not isinstance(res, dict):
            res = {"score": 0.0}
    except Exception:
        res = {"score": 0.0}

    out = {
        "score": clamp(sf(res.get("score", 0.0), 0.0), 0.0, 1.0),
        "cluster_size": int(sf(res.get("cluster_size", 0), 0)),
        "smart_ratio": clamp(sf(res.get("smart_ratio", 0.0), 0.0), 0.0, 1.0),
        "concentration": clamp(sf(res.get("concentration", 0.0), 0.0), 0.0, 1.0),
        "fresh_wallet_ratio": clamp(sf(res.get("fresh_wallet_ratio", 0.0), 0.0), 0.0, 1.0),
        "_ts": now(),
    }
    rt.WALLET_GRAPH_CACHE[mint] = out
    return out


def mempool_age_sec(mint: str):
    _ensure_runtime_state()
    ts = rt.MEMPOOL_SEEN_TS.get(mint)
    if not ts:
        return None
    return max(0.0, now() - ts)


def mempool_recent_bonus(mint: str):
    age = mempool_age_sec(mint)
    if age is None:
        return 0.0

    recent_window = getattr(rt, "SNIPER_RECENT_WINDOW_SEC", 18)
    max_age = getattr(rt, "MEMPOOL_MAX_AGE_SEC", 25)
    recent_bonus = getattr(rt, "MEMPOOL_RECENCY_BONUS", 0.028)

    if age <= recent_window:
        return recent_bonus
    if age <= max_age:
        return recent_bonus * 0.45
    return 0.0


async def features(t):
    _ensure_runtime_state()

    m = t.get("mint")
    if not m:
        return None

    pinfo = await get_price_info(m, prefer_clean=True)
    if not pinfo or pinfo.get("source") not in {"jupiter", "dexscreener"}:
        return None

    if getattr(rt, "HARD_REJECT_NON_JUPITER_PRICE", False) and pinfo.get("source") != "jupiter":
        return None

    liq = sf(pinfo.get("liq", 0), 0.0)
    if liq < getattr(rt, "MIN_LIQUIDITY_OBSERVE", 3000):
        return None

    price = pinfo["price"]
    prev = rt.LAST_PRICE.get(m)
    max_breakout_abs = getattr(rt, "MAX_BREAKOUT_ABS", 0.20)

    breakout = (price - prev) / prev if prev and prev > 0 else random.uniform(0.003, 0.015)
    breakout = clamp(breakout, -max_breakout_abs, max_breakout_abs)
    if abs(breakout) < 0.001:
        breakout = 0.003

    momentum = 0.0
    try:
        await asyncio.sleep(0.25)
        p2 = await get_price(m)
        if price and p2 and p2 > 0:
            momentum = (p2 - price) / price
    except Exception:
        momentum = 0.0

    momentum = clamp(momentum, -max_breakout_abs, max_breakout_abs)
    if abs(momentum) < 0.001:
        momentum = breakout * 0.5

    rt.LAST_MOMENTUM[m] = momentum
    rt.LAST_PRICE[m] = price
    rt.LAST_PRICE_SOURCE[m] = pinfo.get("source", "unknown")

    wallets = await safe_update_token_wallets(m)
    wallet_count = len(wallets)
    smart = min(wallet_count / 3.0, 1.0)

    graph = await safe_wallet_graph_score(m, wallets=wallets)

    sniper_boost = 0.0
    if t.get("source") == "pumpfun":
        sniper_boost += 0.05
    if t.get("source") == "mempool":
        sniper_boost += 0.08
    if pinfo.get("source") == "jupiter":
        sniper_boost += 0.02

    recent_window = getattr(rt, "SNIPER_RECENT_WINDOW_SEC", 18)
    early_entry_bonus = getattr(rt, "EARLY_ENTRY_BONUS", 0.018)
    mp_bonus = mempool_recent_bonus(m)
    early_bonus = (
        early_entry_bonus
        if t.get("source") == "mempool" and (mempool_age_sec(m) or 999) <= recent_window
        else 0.0
    )

    return {
        "mint": m,
        "price": price,
        "breakout": breakout,
        "momentum": momentum,
        "smart": smart,
        "sniper_boost": sniper_boost,
        "mempool_bonus": mp_bonus,
        "early_bonus": early_bonus,
        "is_new": prev is None,
        "wallet_count": wallet_count,
        "wallet_graph_score": clamp(sf(graph.get("score", 0.0), 0.0), 0.0, 1.0),
        "cluster_size": int(sf(graph.get("cluster_size", 0), 0)),
        "smart_ratio": clamp(sf(graph.get("smart_ratio", 0.0), 0.0), 0.0, 1.0),
        "concentration": clamp(sf(graph.get("concentration", 0.0), 0.0), 0.0, 1.0),
        "fresh_wallet_ratio": clamp(sf(graph.get("fresh_wallet_ratio", 0.0), 0.0), 0.0, 1.0),
        "source": t.get("source", "unknown"),
        "meta": t.get("meta", {}),
        "price_source": pinfo.get("source", "unknown"),
        "liq": liq,
        "mempool_hits": rt.MEMPOOL_HITS.get(m, 0),
        "mempool_age_sec": mempool_age_sec(m),
    }


def mode(f):
    if f["is_new"]:
        return "sniper"
    if f["smart"] > 0.6 or sf(f.get("wallet_graph_score", 0.0), 0.0) > 0.55:
        return "smart"
    return "momentum"


def breakout_strength(b):
    b = clamp(sf(b), -getattr(rt, "MAX_BREAKOUT_ABS", 0.20), getattr(rt, "MAX_BREAKOUT_ABS", 0.20))
    if b <= 0:
        return 0.0
    return min(b / 0.05, 1.0) * 0.35


def momentum_strength(m):
    m = clamp(sf(m), -getattr(rt, "MAX_BREAKOUT_ABS", 0.20), getattr(rt, "MAX_BREAKOUT_ABS", 0.20))
    if m <= 0:
        return 0.0
    return min(m / 0.05, 1.0) * 0.30


def zero_detail():
    return {
        "bscore": 0.0,
        "mscore": 0.0,
        "sscore": 0.0,
        "lscore": 0.0,
        "wscore": 0.0,
        "nscore": 0.0,
        "gscore": 0.0,
        "erscore": 0.0,
    }


def score_alpha(f):
    breakout = sf(f.get("breakout", 0.0), 0.0)
    momentum = sf(f.get("momentum", 0.0), 0.0)
    smart = sf(f.get("smart", 0.0), 0.0)
    liq = sf(f.get("liq", 0.0), 0.0)
    price_source = f.get("price_source", "unknown")
    wallet_graph_score = clamp(sf(f.get("wallet_graph_score", 0.0), 0.0), 0.0, 1.0)
    concentration = clamp(sf(f.get("concentration", 0.0), 0.0), 0.0, 1.0)
    smart_ratio = clamp(sf(f.get("smart_ratio", 0.0), 0.0), 0.0, 1.0)
    fresh_wallet_ratio = clamp(sf(f.get("fresh_wallet_ratio", 0.0), 0.0), 0.0, 1.0)

    if liq < getattr(rt, "MIN_LIQUIDITY_OBSERVE", 3000):
        return 0.0, zero_detail()
    if concentration > getattr(rt, "MAX_WALLET_CLUSTER_CONCENTRATION", 0.65):
        return 0.0, zero_detail()
    if smart_ratio < getattr(rt, "MIN_SMART_RATIO", 0.0):
        return 0.0, zero_detail()
    if fresh_wallet_ratio < getattr(rt, "MIN_FRESH_WALLET_RATIO", 0.0):
        return 0.0, zero_detail()

    source_penalty = 1.0 if price_source == "jupiter" else 0.70
    if price_source == "jupiter" and liq < getattr(rt, "MIN_LIQUIDITY_TRADE", 20000):
        source_penalty = 0.85

    if momentum < getattr(rt, "MIN_CONFIRM_MOMENTUM", 0.002):
        momentum *= 0.5
    if breakout < getattr(rt, "MIN_CONFIRM_BREAKOUT", 0.003):
        breakout *= 0.5
    if breakout > 0.012 and momentum < 0:
        return 0.0, zero_detail()

    bscore = breakout_strength(breakout)
    mscore = momentum_strength(momentum)
    sscore = clamp(smart, 0.0, 1.0) * 0.40
    lscore = min(liq / 1_000_000, 1.0) * 0.12
    wc = f.get("wallet_count", 0)
    wscore = 0.08 if wc >= 3 else 0.05 if wc >= 2 else 0.02 if wc >= 1 else 0.0
    nscore = clamp(sf(f.get("sniper_boost", 0)), 0.0, 0.12)
    gscore = clamp(
        wallet_graph_score * getattr(rt, "WALLET_GRAPH_WEIGHT", 0.12),
        0.0,
        getattr(rt, "WALLET_GRAPH_BONUS_CAP", 0.18),
    )
    erscore = clamp(sf(f.get("mempool_bonus", 0.0), 0.0) + sf(f.get("early_bonus", 0.0), 0.0), 0.0, 0.06)

    for name, val in [
        ("breakout", breakout),
        ("momentum", momentum),
        ("smart_money", smart),
        ("liquidity", liq),
        ("wallet_count", wc),
        ("price", f.get("price", 0)),
        ("wallet_graph_score", wallet_graph_score),
    ]:
        score_stat_add(name, val)

    score = (
        bscore * getattr(rt, "ALPHA_BREAKOUT_WEIGHT", 0.35)
        + mscore * getattr(rt, "ALPHA_MOMENTUM_WEIGHT", 0.25)
        + sscore * getattr(rt, "ALPHA_SMART_WEIGHT", 0.25)
        + lscore * getattr(rt, "ALPHA_LIQ_WEIGHT", 0.10)
        + wscore * getattr(rt, "ALPHA_WALLET_WEIGHT", 0.05)
        + nscore * 0.05
        + gscore
        + erscore
    ) * source_penalty

    if wallet_graph_score < getattr(rt, "WALLET_GRAPH_MIN_SCORE", 0.0):
        score *= 0.85

    mtype = mode(f)
    if mtype == "sniper":
        score *= getattr(rt, "SNIPER_MULTIPLIER", 1.35)
        if f.get("mempool_bonus", 0) > 0:
            score *= 1.08
        if f.get("early_bonus", 0) > 0:
            score *= 1.05
    elif mtype == "smart":
        score *= getattr(rt, "SMART_MULTIPLIER", 1.18)
        if f.get("liq", 0) > 50000:
            score *= 1.05
    else:
        score *= getattr(rt, "MOMENTUM_MULTIPLIER", 1.05)
        if f.get("breakout", 0) > 0.01 and f.get("momentum", 0) > 0:
            score *= 1.05

    return clamp(score, 0.0, getattr(rt, "MAX_SCORE", 1.5)), {
        "bscore": bscore,
        "mscore": mscore,
        "sscore": sscore,
        "lscore": lscore,
        "wscore": wscore,
        "nscore": nscore,
        "gscore": gscore,
        "erscore": erscore,
    }


def source_quality(source):
    return {
        "pumpfun": 1.18,
        "mempool": 1.22,
        "dexscreener": 0.75,
        "fusion": 1.05,
        "jupiter": 1.00,
        "synthetic": 0.25,
    }.get(source, 1.0)


def source_weight(src):
    _ensure_runtime_state()

    s = rt.SOURCE_STATS.get(src)
    if s is None:
        s = {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0}
        rt.SOURCE_STATS[src] = s

    wins = int(s.get("wins", 0))
    losses = int(s.get("losses", 0))
    total = wins + losses

    mem = 1.0
    if total >= 5:
        winrate = wins / total if total else 0.0
        if winrate > 0.6:
            mem = 1.12
        elif winrate < 0.3:
            mem = 0.82

    return mem * source_quality(src)


def score_with_allocator(f):
    _ensure_runtime_state()

    base, detail = score_alpha(f)
    base *= source_weight(f["source"])

    if rt.TOKEN_TRADE_COUNT.get(f["mint"], 0) > 2:
        base *= 0.7

    regime = detect_regime()
    if regime == "bull":
        base *= 1.08
    elif regime == "bear":
        base *= 0.88

    base, mtype = apply_strategy_boost(base, f)
    base *= fund_multiplier(mtype)

    min_by_strategy = {
        "stable": getattr(rt, "STABLE_ENTRY_THRESHOLD", 0.078),
        "sniper": getattr(rt, "SNIPER_ENTRY_THRESHOLD", 0.070),
        "momentum": getattr(rt, "MOMENTUM_ENTRY_THRESHOLD", 0.082),
    }

    threshold = min_by_strategy.get(mtype, getattr(rt, "ENTRY_THRESHOLD", 0.085))
    no_trade_cycles = int(getattr(engine, "no_trade_cycles", 0) or 0)

    if no_trade_cycles > 20:
        threshold *= 0.70
    elif no_trade_cycles > 10:
        threshold *= 0.85

    if no_trade_cycles > getattr(rt, "FORCE_TRADE_AFTER", 180):
        base = max(base, getattr(rt, "ENTRY_THRESHOLD", 0.085) * 0.95)

    if base < threshold:
        base *= 0.95

    return max(base, 0.0), mtype, detail


try:
    from app.engine.sources import fetch_alpha_candidates as _sources_fetch_alpha_candidates
except Exception:
    _sources_fetch_alpha_candidates = None


async def fetch_alpha_candidates():
    if _sources_fetch_alpha_candidates is not None:
        try:
            tokens = await _sources_fetch_alpha_candidates()
            if isinstance(tokens, list):
                return tokens
        except Exception:
            pass

    try:
        if hasattr(rt, "MEMPOOL_BUFFER") and isinstance(rt.MEMPOOL_BUFFER, list):
            tokens = list(rt.MEMPOOL_BUFFER)[-50:]
            if tokens:
                return tokens
    except Exception:
        pass

    return []


async def process_candidates(tokens):
    _ensure_runtime_state()

    ranked = []
    for t in tokens or []:
        try:
            f = await features(t)
            if not f:
                continue

            sc, mtype, detail = score_with_allocator(f)

            # V82 AI predictor
            ai = predict_trade_quality(f)
            f["_ai_win_prob"] = sf(ai.get("win_prob", 0.5), 0.5)
            f["_ai_pnl"] = sf(ai.get("expected_pnl", 0.0), 0.0)
            f["_ai_score"] = sf(ai.get("score", 0.0), 0.0)

            # AI filter
            if f["_ai_win_prob"] < 0.45:
                continue

            # AI reweight
            sc *= (0.7 + f["_ai_win_prob"] * 0.6)

            f["_score"] = clamp(sc, 0.0, getattr(rt, "MAX_SCORE", 1.5))
            f["_mode"] = mtype
            f["_tier"] = (
                "A+"
                if f["_score"] >= 0.145 else
                "A"
                if f["_score"] >= getattr(rt, "STRICT_A_TIER_THRESHOLD", 0.095)
                else "B"
            )
            f["_detail"] = detail
            ranked.append(f)
        except Exception:
            continue

    ranked.sort(key=lambda x: x.get("_score", 0.0), reverse=True)
    top_k = int(getattr(rt, "TOP_K_PRESELECT", 3))
    return ranked[:max(top_k, 3)]
