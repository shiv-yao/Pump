import time
import httpx

CACHE = {}
CACHE_TTL = 1800  # 30 min

JUP_TOKEN_API = "https://token.jup.ag/all"
DEX_API = "https://api.dexscreener.com/latest/dex/search"
PUMPFUN_API = "https://frontend-api.pump.fun/coins/latest"


# ===== cache =====
def _cache_get(k):
    v = CACHE.get(k)
    if not v:
        return None
    if time.time() - v["ts"] > CACHE_TTL:
        return None
    return v["data"]


def _cache_set(k, data):
    CACHE[k] = {"data": data, "ts": time.time()}


# ===== JUPITER =====
async def from_jupiter(symbol):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(JUP_TOKEN_API)
        tokens = res.json()

    symbol = symbol.upper()

    for t in tokens:
        if t.get("symbol") == symbol:
            return {
                "symbol": symbol,
                "mint": t["address"],
                "decimals": t.get("decimals", 6),
                "source": "jupiter",
                "verified": True
            }

    return None


# ===== DEXSCREENER =====
async def from_dex(symbol):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(DEX_API, params={"q": symbol})
        data = res.json()

    pairs = data.get("pairs", [])
    if not pairs:
        return None

    # 選 liquidity 最大的
    pairs = sorted(
        pairs,
        key=lambda x: float(x.get("liquidity", {}).get("usd", 0)),
        reverse=True
    )

    p = pairs[0]

    base = p.get("baseToken", {})
    return {
        "symbol": base.get("symbol"),
        "mint": base.get("address"),
        "decimals": 6,
        "source": "dexscreener",
        "liquidity": p.get("liquidity", {}).get("usd", 0),
        "verified": False
    }


# ===== PUMPFUN =====
async def from_pumpfun(symbol):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(PUMPFUN_API)
        coins = res.json()

    symbol = symbol.lower()

    for c in coins:
        if c.get("symbol", "").lower() == symbol:
            return {
                "symbol": c.get("symbol"),
                "mint": c.get("mint"),
                "decimals": 6,
                "source": "pumpfun",
                "verified": False
            }

    return None


# ===== MAIN =====
async def resolve_token(symbol=None, **kwargs):
    if not symbol:
        return {"error": "missing symbol"}

    symbol = symbol.strip()

    # ===== direct mint =====
    if len(symbol) > 30:
        return {
            "symbol": symbol,
            "mint": symbol,
            "source": "direct",
            "verified": False
        }

    # ===== cache =====
    cached = _cache_get(symbol)
    if cached:
        return cached

    # ===== try sources =====
    for fn in [from_jupiter, from_dex, from_pumpfun]:
        try:
            res = await fn(symbol)
            if res:
                _cache_set(symbol, res)
                return res
        except Exception:
            continue

    return {"error": f"token not found: {symbol}"}
