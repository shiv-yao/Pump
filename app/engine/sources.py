import asyncio
import json
import random
from collections import deque

import httpx
import websockets

from app.data.market import get_quote
from app.engine import runtime as rt
from app.engine.utils import dedup, log, now, parse_out_amount, sf, valid_mint_like


# =========================================================
# INTERNAL
# =========================================================
def _ensure_runtime_state():
    if not hasattr(rt, "MEMPOOL_BUFFER") or rt.MEMPOOL_BUFFER is None:
        rt.MEMPOOL_BUFFER = []

    if not hasattr(rt, "MEMPOOL_SEEN_TS") or rt.MEMPOOL_SEEN_TS is None:
        rt.MEMPOOL_SEEN_TS = {}

    if not hasattr(rt, "MEMPOOL_HITS") or rt.MEMPOOL_HITS is None:
        rt.MEMPOOL_HITS = {}

    if not hasattr(rt, "LAST_PRICE") or rt.LAST_PRICE is None:
        rt.LAST_PRICE = {}

    if not hasattr(rt, "LAST_PRICE_SOURCE") or rt.LAST_PRICE_SOURCE is None:
        rt.LAST_PRICE_SOURCE = {}

    if not hasattr(rt, "SEARCH_TERMS") or rt.SEARCH_TERMS is None:
        rt.SEARCH_TERMS = ["SOL", "USDC", "BONK", "MEME", "PEPE", "DOG", "AI", "PUMP"]

    if not hasattr(rt, "MEME_SEARCH_TERMS") or rt.MEME_SEARCH_TERMS is None:
        rt.MEME_SEARCH_TERMS = ["pumpfun", "pepe", "doge", "meme", "cat", "frog", "moonshot"]

    if not hasattr(rt, "HTTP_GET_RETRY"):
        rt.HTTP_GET_RETRY = 2

    if not hasattr(rt, "QUOTE_TIMEOUT_RETRY"):
        rt.QUOTE_TIMEOUT_RETRY = 3

    if not hasattr(rt, "MIN_UNIVERSE"):
        rt.MIN_UNIVERSE = 20

    if not hasattr(rt, "BOOT_SYNTHETIC_UNIVERSE"):
        rt.BOOT_SYNTHETIC_UNIVERSE = False


# =========================================================
# HTTP
# =========================================================
async def http_get(url, params=None, headers=None):
    _ensure_runtime_state()

    retries = max(1, int(getattr(rt, "HTTP_GET_RETRY", 2)))
    timeout = getattr(rt, "HTTP_TIMEOUT", 8.0)

    for _ in range(retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                r = await client.get(url, params=params, headers=headers)
                r.raise_for_status()
                return r.json()
        except Exception:
            await asyncio.sleep(0.2)

    return None


# =========================================================
# MEMPOOL
# =========================================================
async def mempool_stream():
    _ensure_runtime_state()

    while True:
        try:
            async with websockets.connect(rt.MEMPOOL_WSS, ping_interval=20) as ws:
                sub = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [rt.JUPITER_PROGRAM_ID]},
                        {"commitment": "processed"},
                    ],
                }
                await ws.send(json.dumps(sub))

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    text = json.dumps(data)

                    for word in text.replace('"', " ").replace(",", " ").split():
                        if valid_mint_like(word):
                            row = {
                                "mint": word,
                                "source": "mempool",
                                "meta": {},
                                "ts": now(),
                            }

                            if isinstance(rt.MEMPOOL_BUFFER, deque):
                                rt.MEMPOOL_BUFFER.append(row)
                                while len(rt.MEMPOOL_BUFFER) > 300:
                                    rt.MEMPOOL_BUFFER.popleft()
                            else:
                                rt.MEMPOOL_BUFFER.append(row)
                                if len(rt.MEMPOOL_BUFFER) > 300:
                                    del rt.MEMPOOL_BUFFER[:-300]

                            rt.MEMPOOL_SEEN_TS[word] = now()
                            rt.MEMPOOL_HITS[word] = int(rt.MEMPOOL_HITS.get(word, 0)) + 1

        except Exception as e:
            log(f"MEMPOOL_ERR {e}")
            await asyncio.sleep(2)


def flush_mempool():
    _ensure_runtime_state()

    out = []

    if isinstance(rt.MEMPOOL_BUFFER, deque):
        while rt.MEMPOOL_BUFFER:
            out.append(rt.MEMPOOL_BUFFER.popleft())
    else:
        while rt.MEMPOOL_BUFFER:
            out.append(rt.MEMPOOL_BUFFER.pop(0))

    return out


# =========================================================
# CANDIDATE FETCHERS
# =========================================================
async def fetch_fusion_candidates():
    return []


async def fetch_pumpfun_candidates(limit=30):
    data = await http_get("https://frontend-api.pump.fun/coins/latest")
    out = []

    if not isinstance(data, list):
        return out

    for row in data[:limit]:
        if not isinstance(row, dict):
            continue

        mint = row.get("mint")
        if mint and valid_mint_like(mint):
            meta = {
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "reply_count": row.get("reply_count"),
                "market_cap": row.get("market_cap"),
            }
            out.append({
                "mint": mint,
                "source": "pumpfun",
                "meta": meta,
            })

    return out


async def fetch_jupiter_candidates(limit=80):
    urls = [
        "https://lite-api.jup.ag/tokens/v1/mints/tradable",
        "https://cache.jup.ag/tokens",
    ]

    all_rows = []
    for url in urls:
        data = await http_get(url)
        if isinstance(data, list):
            all_rows.extend(data)

    out = []
    random.shuffle(all_rows)

    for row in all_rows:
        if len(out) >= limit:
            break

        if isinstance(row, str):
            mint = row
            meta = {}
        elif isinstance(row, dict):
            mint = row.get("address") or row.get("mint")
            meta = row
        else:
            continue

        if mint and mint != rt.SOL and valid_mint_like(mint):
            out.append({
                "mint": mint,
                "source": "jupiter",
                "meta": {
                    "symbol": meta.get("symbol"),
                    "name": meta.get("name"),
                    "decimals": meta.get("decimals"),
                },
            })

    return out


async def fetch_dexscreener_candidates(query="SOL", limit=30):
    data = await http_get(
        "https://api.dexscreener.com/latest/dex/search/",
        params={"q": query},
    )

    out = []
    if not isinstance(data, dict):
        return out

    pairs = data.get("pairs", []) or []
    for row in pairs[:limit]:
        if not isinstance(row, dict):
            continue

        base = row.get("baseToken", {}) or {}
        mint = base.get("address")

        if mint and mint != rt.SOL and valid_mint_like(mint):
            out.append({
                "mint": mint,
                "source": "dexscreener",
                "meta": {
                    "symbol": base.get("symbol"),
                    "name": base.get("name"),
                    "liquidity_usd": (row.get("liquidity", {}) or {}).get("usd"),
                    "volume_h24": (row.get("volume", {}) or {}).get("h24"),
                    "price_native": row.get("priceNative"),
                },
            })

    return out


async def fetch_dex_bulk():
    _ensure_runtime_state()

    queries = list(rt.SEARCH_TERMS) + list(rt.MEME_SEARCH_TERMS)
    tasks = [fetch_dexscreener_candidates(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    merged = []
    for r in results:
        if isinstance(r, list):
            merged.extend(r)

    return merged


async def fetch_alpha_candidates():
    """
    Main universe builder.
    """
    _ensure_runtime_state()

    results = await asyncio.gather(
        fetch_fusion_candidates(),
        fetch_pumpfun_candidates(),
        fetch_jupiter_candidates(),
        fetch_dex_bulk(),
        return_exceptions=True,
    )

    merged = []
    for r in results:
        if isinstance(r, list):
            merged.extend(r)

    merged.extend(flush_mempool())

    out = dedup(merged) if merged else []

    # 不再塞假的 synthetic mint，避免 features / quote 全炸掉
    if not isinstance(out, list):
        out = []

    return out


# =========================================================
# QUOTE / PRICE
# =========================================================
async def safe_quote(input_mint, output_mint, amount):
    _ensure_runtime_state()

    for _ in range(max(1, int(getattr(rt, "QUOTE_TIMEOUT_RETRY", 3)))):
        try:
            q = await get_quote(input_mint, output_mint, amount)
            if q:
                return q
        except Exception:
            pass

        await asyncio.sleep(0.15)

    return None


async def jupiter_price(m):
    q = await safe_quote(rt.SOL, m, rt.AMOUNT)
    if not q:
        return None

    in_amt = sf(q.get("inAmount", rt.AMOUNT))
    out_amt = sf(parse_out_amount(q))

    if in_amt <= 0 or out_amt <= 0:
        return None

    if out_amt < getattr(rt, "MIN_OUT_AMOUNT", 300):
        return None

    price = in_amt / out_amt
    if price <= 0 or price > getattr(rt, "MAX_PRICE_JUPITER", 0.1):
        return None

    return {
        "price": price,
        "liq": out_amt,
        "source": "jupiter",
    }


async def birdeye_price(m):
    if not getattr(rt, "BIRDEYE_API_KEY", None):
        return None

    headers = {"X-API-KEY": rt.BIRDEYE_API_KEY}

    token_res = await http_get(
        "https://public-api.birdeye.so/defi/price",
        params={"address": m},
        headers=headers,
    )
    sol_res = await http_get(
        "https://public-api.birdeye.so/defi/price",
        params={"address": rt.SOL},
        headers=headers,
    )

    try:
        token_usd = sf(token_res["data"]["value"])
        sol_usd = sf(sol_res["data"]["value"])
        if token_usd <= 0 or sol_usd <= 0:
            return None

        price = token_usd / sol_usd
        if price <= 0 or price > getattr(rt, "MAX_PRICE_FALLBACK", 10):
            return None

        return {
            "price": price,
            "liq": 0,
            "source": "birdeye",
        }
    except Exception:
        return None


async def dexscreener_price(m):
    res = await http_get(
        "https://api.dexscreener.com/latest/dex/search/",
        params={"q": m},
    )
    if not isinstance(res, dict):
        return None

    try:
        pairs = sorted(
            res.get("pairs", []) or [],
            key=lambda x: sf((x.get("liquidity", {}) or {}).get("usd", 0)),
            reverse=True,
        )

        if not pairs:
            return None

        pair = pairs[0]
        native_price = sf(pair.get("priceNative", 0))
        liq = sf((pair.get("liquidity", {}) or {}).get("usd", 0))

        if native_price <= 0:
            return None

        if native_price > getattr(rt, "MAX_PRICE_FALLBACK", 10):
            return None

        if liq < getattr(rt, "MIN_LIQUIDITY_OBSERVE", 3000):
            return None

        return {
            "price": native_price,
            "liq": liq,
            "source": "dexscreener",
        }
    except Exception:
        return None


async def get_price_info(m, prefer_clean=False):
    _ensure_runtime_state()

    candidates = []

    for fn in (jupiter_price, birdeye_price, dexscreener_price):
        try:
            r = await fn(m)
            if r and r.get("price"):
                candidates.append(r)
        except Exception:
            pass

    if prefer_clean:
        for r in candidates:
            if (
                r.get("source") == "jupiter"
                and sf(r.get("liq", 0), 0.0) >= getattr(rt, "MIN_LIQUIDITY_TRADE", 20000)
            ):
                return r

        if candidates:
            return max(candidates, key=lambda x: sf(x.get("liq", 0), 0.0))

        return None

    for r in candidates:
        if r.get("source") == "jupiter":
            return r

    if candidates:
        return max(candidates, key=lambda x: sf(x.get("liq", 0), 0.0))

    last = rt.LAST_PRICE.get(m)
    if last:
        return {
            "price": last,
            "liq": 0,
            "source": rt.LAST_PRICE_SOURCE.get(m, "last_price"),
        }

    return None


async def get_price(m):
    info = await get_price_info(m, prefer_clean=False)
    return None if not info else info["price"]
