import httpx

async def get_trading_signal(symbol: str, timeframe: str = "1h") -> str:
    try:
        clean_symbol = symbol.upper().replace("/", "")
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={clean_symbol}"

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return f"無法取得 {symbol} 數據，HTTP {r.status_code}"

            data = r.json()
            price = float(data["lastPrice"])
            change = float(data["priceChangePercent"])
            volume = float(data["quoteVolume"])

            if change > 2:
                signal = "🟢 做多"
            elif change < -2:
                signal = "🔴 做空"
            else:
                signal = "⚪ 觀望"

            return (
                f"📊 {symbol} 信號分析\n"
                f"時間框架: {timeframe}\n"
                f"現價: {price:,.4f}\n"
                f"24h漲跌: {change:+.2f}%\n"
                f"24h成交量: {volume:,.0f} USDT\n"
                f"信號: {signal}"
            )
    except Exception as e:
        return f"無法取得 {symbol} 數據: {e}"
