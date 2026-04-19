import httpx
async def get_trading_signal(symbol: str, timeframe: str = "1h") -> str:
    try:
        clean_symbol = symbol.upper().replace("/", "")
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={clean_symbol}")
            if r.status_code != 200: return f"無法取得 {symbol} 數據，HTTP {r.status_code}"
            data = r.json()
            price = float(data["lastPrice"]); change = float(data["priceChangePercent"]); volume = float(data["quoteVolume"])
            signal = "🟢 做多" if change > 2 else ("🔴 做空" if change < -2 else "⚪ 觀望")
            return f"📊 {symbol} 信號分析\n時間框架: {timeframe}\n現價: {price:,.4f}\n24h漲跌: {change:+.2f}%\n24h成交量: {volume:,.0f} USDT\n信號: {signal}"
    except Exception as e:
        return f"無法取得 {symbol} 數據: {e}"
