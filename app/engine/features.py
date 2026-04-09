import asyncio
import random

from app.alpha.adaptive_filter import adaptive_filter
from app.alpha.helius_wallet_tracker import update_token_wallets
from app.engine import runtime as rt
from app.engine.fund_brain import fund_multiplier
from app.engine.risk import detect_regime
from app.engine.sources import get_price, get_price_info
from app.engine.utils import clamp, now, score_stat_add, sf

async def safe_update_token_wallets(mint: str):
    try:
        return await asyncio.wait_for(update_token_wallets(mint), timeout=rt.WALLET_TRACKER_TIMEOUT_SEC)
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
        ok = score >= 0.08 and liq >= 3_000 and breakout > -0.03
        return ok, {"fallback": True}

async def safe_wallet_graph_score(mint: str, wallets=None):
    cached = rt.WALLET_GRAPH_CACHE.get(mint)
    if cached and now() - cached.get("_ts", 0.0) < 20:
        return cached
    try:
        res = await asyncio.wait_for(rt.get_wallet_graph_score(mint, wallets=wallets), timeout=rt.WALLET_GRAPH_TIMEOUT_SEC)
        if not isinstance(res, dict):
            res = {"score": 0.0}
    except Exception:
        res = {"score": 0.0}
    score = clamp(sf(res.get("score", 0.0), 0.0), 0.0, 1.0)
    out = {
        "score": score,
        "cluster_size": int(sf(res.get("cluster_size", 0), 0)),
        "smart_ratio": clamp(sf(res.get("smart_ratio", 0.0), 0.0), 0.0, 1.0),
        "concentration": clamp(sf(res.get("concentration", 0.0), 0.0), 0.0, 1.0),
        "fresh_wallet_ratio": clamp(sf(res.get("fresh_wallet_ratio", 0.0), 0.0), 0.0, 1.0),
        "_ts": now(),
    }
    rt.WALLET_GRAPH_CACHE[mint] = out
    return out

def mempool_age_sec(mint: str):
    ts = rt.MEMPOOL_SEEN_TS.get(mint)
    if not ts:
        return None
    return max(0.0, now() - ts)

def mempool_recent_bonus(mint: str):
    age = mempool_age_sec(mint)
    if age is None:
        return 0.0
    if age <= rt.SNIPER_RECENT_WINDOW_SEC:
        return rt.MEMPOOL_RECENCY_BONUS
    if age <= rt.MEMPOOL_MAX_AGE_SEC:
        return rt.MEMPOOL_RECENCY_BONUS * 0.45
    return 0.0

async def features(t):
    m = t.get("mint")
    if not m:
        return None
    pinfo = await get_price_info(m, prefer_clean=True)
    if not pinfo or pinfo.get("source") not in {"jupiter", "dexscreener"}:
        return None
    if rt.HARD_REJECT_NON_JUPITER_PRICE and pinfo.get("source") != "jupiter":
        return None
    liq = sf(pinfo.get("liq", 0), 0.0)
    if liq < rt.MIN_LIQUIDITY_TRADE:
        return None

    price = pinfo["price"]
    prev = rt.LAST_PRICE.get(m)
    breakout = (price - prev) / prev if prev and prev > 0 else random.uniform(0.003, 0.015)
    breakout = clamp(breakout, -rt.MAX_BREAKOUT_ABS, rt.MAX_BREAKOUT_ABS)
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

    momentum = clamp(momentum, -rt.MAX_BREAKOUT_ABS, rt.MAX_BREAKOUT_ABS)
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

    mp_bonus = mempool_recent_bonus(m)
    early_bonus = rt.EARLY_ENTRY_BONUS if (t.get("source") == "mempool" and (mempool_age_sec(m) or 999) <= rt.SNIPER_RECENT_WINDOW_SEC) else 0.0

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
    b = clamp(sf(b), -rt.MAX_BREAKOUT_ABS, rt.MAX_BREAKOUT_ABS)
    if b <= 0:
        return 0.0
    return min(b / 0.05, 1.0) * 0.35

def momentum_strength(m):
    m = clamp(sf(m), -rt.MAX_BREAKOUT_ABS, rt.MAX_BREAKOUT_ABS)
    if m <= 0:
        return 0.0
    return min(m / 0.05, 1.0) * 0.30

def zero_detail():
    return {"bscore": 0.0, "mscore": 0.0, "sscore": 0.0, "lscore": 0.0, "wscore": 0.0, "nscore": 0.0, "gscore": 0.0, "erscore": 0.0}

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

    if liq < rt.MIN_LIQUIDITY_OBSERVE or concentration > rt.MAX_WALLET_CLUSTER_CONCENTRATION or smart_ratio < rt.MIN_SMART_RATIO or fresh_wallet_ratio < rt.MIN_FRESH_WALLET_RATIO:
        return 0.0, zero_detail()

    source_penalty = 1.0 if price_source == "jupiter" else 0.70
    if price_source == "jupiter" and liq < rt.MIN_LIQUIDITY_TRADE:
        source_penalty = 0.85
    if momentum < rt.MIN_CONFIRM_MOMENTUM:
        momentum *= 0.5
    if breakout < rt.MIN_CONFIRM_BREAKOUT:
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
    gscore = clamp(wallet_graph_score * rt.WALLET_GRAPH_WEIGHT, 0.0, rt.WALLET_GRAPH_BONUS_CAP)
    erscore = clamp(sf(f.get("mempool_bonus", 0.0), 0.0) + sf(f.get("early_bonus", 0.0), 0.0), 0.0, 0.06)

    for name, val in [("breakout", breakout), ("momentum", momentum), ("smart_money", smart), ("liquidity", liq), ("wallet_count", wc), ("price", f.get("price", 0)), ("wallet_graph_score", wallet_graph_score)]:
        score_stat_add(name, val)

    score = (
        bscore * rt.ALPHA_BREAKOUT_WEIGHT + mscore * rt.ALPHA_MOMENTUM_WEIGHT +
        sscore * rt.ALPHA_SMART_WEIGHT + lscore * rt.ALPHA_LIQ_WEIGHT +
        wscore * rt.ALPHA_WALLET_WEIGHT + nscore * 0.05 + gscore + erscore
    ) * source_penalty

    if wallet_graph_score < rt.WALLET_GRAPH_MIN_SCORE:
        score *= 0.85

    mtype = mode(f)
    if mtype == "sniper":
        score *= rt.SNIPER_MULTIPLIER
    elif mtype == "smart":
        score *= rt.SMART_MULTIPLIER
    else:
        score *= rt.MOMENTUM_MULTIPLIER

    return clamp(score, 0.0, rt.MAX_SCORE), {"bscore": bscore, "mscore": mscore, "sscore": sscore, "lscore": lscore, "wscore": wscore, "nscore": nscore, "gscore": gscore, "erscore": erscore}

def source_quality(source):
    return {"pumpfun": 1.18, "mempool": 1.22, "dexscreener": 0.75, "fusion": 1.05, "jupiter": 1.00, "synthetic": 0.25}.get(source, 1.0)

def source_weight(src):
    s = rt.SOURCE_STATS[src]
    total = s["wins"] + s["losses"]
    mem = 1.0
    if total >= 5:
        winrate = s["wins"] / total if total else 0.0
        if winrate > 0.6:
            mem = 1.12
        elif winrate < 0.3:
            mem = 0.82
    return mem * source_quality(src)

def score_with_allocator(f):
    base, detail = score_alpha(f)
    base *= source_weight(f["source"])
    if rt.TOKEN_TRADE_COUNT[f["mint"]] > 2:
        base *= 0.7
    regime = detect_regime()
    if regime == "bull":
        base *= 1.08
    elif regime == "bear":
        base *= 0.88
    mtype = mode(f)
    base *= fund_multiplier(mtype)
    return max(base, 0.0), mtype, detail
