import asyncio
import json
import random

import httpx
import websockets

from app.data.market import get_quote
from app.engine import runtime as rt
from app.engine.utils import dedup, log, now, parse_out_amount, sf, valid_mint_like

async def http_get(url, params=None, headers=None):
    for _ in range(max(1, rt.HTTP_GET_RETRY)):
        try:
            async with httpx.AsyncClient(timeout=rt.HTTP_TIMEOUT) as client:
                r = await client.get(url, params=params, headers=headers)
                r.raise_for_status()
                return r.json()
        except Exception:
            await asyncio.sleep(0.15)
    return None

async def mempool_stream():
    while True:
        try:
            async with websockets.connect(rt.MEMPOOL_WSS, ping_interval=20) as ws:
                sub = {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe", "params": [{"mentions": [rt.JUPITER_PROGRAM_ID]}, {"commitment": "processed"}]}
                await ws.send(json.dumps(sub))
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    text = json.dumps(data)
                    for word in text.replace('"', " ").replace(",", " ").split():
                        if valid_mint_like(word):
                            rt.MEMPOOL_BUFFER.append({"mint": word, "source": "mempool", "meta": {}, "ts": now()})
                            rt.MEMPOOL_SEEN_TS[word] = now()
                            rt.MEMPOOL_HITS[word] += 1
                            if len(rt.MEMPOOL_BUFFER) > 300:
                                del rt.MEMPOOL_BUFFER[:-300]
        except Exception as e:
            log(f"MEMPOOL_ERR {e}")
            await asyncio.sleep(2)

def flush_mempool():
    out = []
    while rt.MEMPOOL_BUFFER:
        out.append(rt.MEMPOOL_BUFFER.pop(0))
    return out

async def fetch_fusion_candidates():
    return []

async def fetch_pumpfun_candidates(limit=30):
    data = await http_get("https://frontend-api.pump.fun/coins/latest")
    out = []
    if not isinstance(data, list):
        return out
    for row in data[:limit]:
        mint = row.get("mint")
        if mint and valid_mint_like(mint):
            meta = {"symbol": row.get("symbol"), "name": row.get("name"), "reply_count": row.get("reply_count"), "market_cap": row.get("market_cap")}
            out.append({"mint": mint, "source": "pumpfun", "meta": meta})
    return out

async def fetch_jupiter_candidates(limit=80):
    urls = ["https://lite-api.jup.ag/tokens/v1/mints/tradable", "https://cache.jup.ag/tokens"]
    all_rows = []
    for url in urls:
        data = await http_get(url)
        if isinstance(data, list):
            all_rows.extend(data)
    out = []
    random.shuffle(all_rows)
    for row in all_rows[:limit]:
        if isinstance(row, str):
            mint, meta = row, {}
        else:
            mint, meta = row.get("address") or row.get("mint"), row
        if mint and mint != rt.SOL and valid_mint_like(mint):
            out.append({"mint": mint, "source": "jupiter", "meta": {"symbol": meta.get("symbol"), "name": meta.get("name"), "decimals": meta.get("decimals")}})
    return out

async def fetch_dexscreener_candidates(query="SOL", limit=30):
    data = await http_get("https://api.dexscreener.com/latest/dex/search/", params={"q": query})
    out = []
    if not data:
        return out
    for row in (data.get("pairs", []) or [])[:limit]:
        base = row.get("baseToken", {}) or {}
        mint = base.get("address")
        if mint and mint != rt.SOL and valid_mint_like(mint):
            out.append({"mint": mint, "source": "dexscreener", "meta": {"symbol": base.get("symbol"), "name": base.get("name"), "liquidity_usd": (row.get("liquidity", {}) or {}).get("usd"), "volume_h24": (row.get("volume", {}) or {}).get("h24"), "price_native": row.get("priceNative")}})
    return out

async def fetch_dex_bulk():
    tasks = [fetch_dexscreener_candidates(q) for q in rt.SEARCH_TERMS + rt.MEME_SEARCH_TERMS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged = []
    for r in results:
        if isinstance(r, list):
            merged.extend(r)
    return merged

async def fetch_alpha_candidates():
    results = await asyncio.gather(fetch_fusion_candidates(), fetch_pumpfun_candidates(), fetch_jupiter_candidates(), fetch_dex_bulk(), return_exceptions=True)
    merged = []
    for r in results:
        if isinstance(r, list):
            merged.extend(r)
    merged.extend(flush_mempool())
    out = dedup(merged)
    if len(out) < rt.MIN_UNIVERSE and rt.BOOT_SYNTHETIC_UNIVERSE:
        for i in range(10):
            out.append({"mint": f"SIM{i}{random.randint(1000,9999)}", "source": "synthetic", "meta": {}})
    return out

async def safe_quote(input_mint, output_mint, amount):
    for _ in range(max(1, rt.QUOTE_TIMEOUT_RETRY)):
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
    if in_amt <= 0 or out_amt <= 0 or out_amt < rt.MIN_OUT_AMOUNT:
        return None
    price = in_amt / out_amt
    if price <= 0 or price > rt.MAX_PRICE_JUPITER:
        return None
    return {"price": price, "liq": out_amt, "source": "jupiter"}

async def birdeye_price(m):
    if not rt.BIRDEYE_API_KEY:
        return None
    headers = {"X-API-KEY": rt.BIRDEYE_API_KEY}
    token_res = await http_get("https://public-api.birdeye.so/defi/price", params={"address": m}, headers=headers)
    sol_res = await http_get("https://public-api.birdeye.so/defi/price", params={"address": rt.SOL}, headers=headers)
    try:
        token_usd = sf(token_res["data"]["value"])
        sol_usd = sf(sol_res["data"]["value"])
        if token_usd <= 0 or sol_usd <= 0:
            return None
        price = token_usd / sol_usd
        if price <= 0 or price > rt.MAX_PRICE_FALLBACK:
            return None
        return {"price": price, "liq": 0, "source": "birdeye"}
    except Exception:
        return None

async def dexscreener_price(m):
    res = await http_get("https://api.dexscreener.com/latest/dex/search/", params={"q": m})
    if not res:
        return None
    try:
        pairs = sorted(res.get("pairs", []), key=lambda x: sf((x.get("liquidity", {}) or {}).get("usd", 0)), reverse=True)
        if not pairs:
            return None
        pair = pairs[0]
        native_price = sf(pair.get("priceNative", 0))
        liq = sf((pair.get("liquidity", {}) or {}).get("usd", 0))
        if native_price <= 0 or native_price > rt.MAX_PRICE_FALLBACK or liq < rt.MIN_LIQUIDITY_OBSERVE:
            return None
        return {"price": native_price, "liq": liq, "source": "dexscreener"}
    except Exception:
        return None

async def get_price_info(m, prefer_clean=False):
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
            if r.get("source") == "jupiter" and sf(r.get("liq", 0), 0.0) >= rt.MIN_LIQUIDITY_TRADE:
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
        return {"price": last, "liq": 0, "source": rt.LAST_PRICE_SOURCE.get(m, "last_price")}
    return None

async def get_price(m):
    info = await get_price_info(m, prefer_clean=False)
    return None if not info else info["price"]
