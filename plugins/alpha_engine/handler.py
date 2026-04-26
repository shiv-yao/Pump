import httpx
import random

async def get_alpha_signal(symbol: str = "BTCUSDT"):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}")
        data = r.json()

    price = float(data["lastPrice"])
    change = float(data["priceChangePercent"])

    # 基礎 alpha（你可以換成 GNN / onchain）
    score = 0.5 + (change / 100)

    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "score": score
    }
