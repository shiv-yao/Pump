import httpx, json
def _clean(symbol: str) -> str: return symbol.upper().replace("/", "")
async def scan_market(symbols: list[str]) -> str:
    results = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for symbol in symbols:
                s = _clean(symbol)
                r = await client.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={s}")
                if r.status_code != 200:
                    results.append({"symbol": s, "score": -999, "status": f"HTTP {r.status_code}"}); continue
                data = r.json(); change = float(data["priceChangePercent"]); quote_volume = float(data["quoteVolume"])
                score = change + min(quote_volume / 10000000.0, 10.0)
                action = "BUY" if score >= 8 else ("WATCH" if score >= 3 else "SKIP")
                results.append({"symbol": s, "price": data.get("lastPrice"), "change_pct": change, "quote_volume": quote_volume, "score": round(score, 4), "action": action})
        results.sort(key=lambda x: x.get("score", -999), reverse=True)
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"scan_market error: {e}"
