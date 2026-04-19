import httpx
import asyncio
import random

POLY_API = "https://clob.polymarket.com"


# -------------------------
# 1️⃣ 取得 orderbook
# -------------------------
async def get_orderbook(market_id: str):
    url = f"{POLY_API}/book?market={market_id}"

    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(url)

    if r.status_code != 200:
        return None

    return r.json()


# -------------------------
# 2️⃣ 計算 mid price
# -------------------------
def calc_mid(book):
    bids = book.get("bids", [])
    asks = book.get("asks", [])

    if not bids or not asks:
        return None

    best_bid = float(bids[0]["price"])
    best_ask = float(asks[0]["price"])

    return (best_bid + best_ask) / 2


# -------------------------
# 3️⃣ 外部 BTC price（alpha來源）
# -------------------------
async def get_btc_signal():
    async with httpx.AsyncClient() as c:
        r = await c.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT")

    data = r.json()

    change = float(data["priceChangePercent"])

    # normalize → probability shift
    score = 0.5 + (change / 100)

    return score


# -------------------------
# 4️⃣ 主 alpha
# -------------------------
async def get_polymarket_signal(market_id: str):
    book = await get_orderbook(market_id)

    if not book:
        return {"error": "orderbook failed"}

    mid = calc_mid(book)

    if mid is None:
        return {"error": "no liquidity"}

    external = await get_btc_signal()

    edge = external - mid

    # threshold
    if edge > 0.02:
        action = "buy_yes"
    elif edge < -0.02:
        action = "buy_no"
    else:
        action = "hold"

    return {
        "mid_price": mid,
        "external_prob": external,
        "edge": edge,
        "action": action
    }
