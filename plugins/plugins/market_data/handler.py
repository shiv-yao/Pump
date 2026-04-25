import httpx
import json

def _clean(symbol: str) -> str:
    return symbol.upper().replace("/", "")

async def get_spot_price(symbol: str) -> str:
    try:
        s = _clean(symbol)
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={s}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return f"price error {r.status_code}: {r.text}"
            data = r.json()
            return f"{s} spot = {data.get('price')}"
    except Exception as e:
        return f"get_spot_price error: {e}"

async def get_ticker_24h(symbol: str) -> str:
    try:
        s = _clean(symbol)
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={s}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return f"ticker error {r.status_code}: {r.text}"
            data = r.json()
            out = {
                "symbol": s,
                "lastPrice": data.get("lastPrice"),
                "priceChangePercent": data.get("priceChangePercent"),
                "quoteVolume": data.get("quoteVolume"),
                "highPrice": data.get("highPrice"),
                "lowPrice": data.get("lowPrice"),
            }
            return json.dumps(out, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"get_ticker_24h error: {e}"
