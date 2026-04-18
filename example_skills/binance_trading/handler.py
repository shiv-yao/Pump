"""
Binance Trading Skill Handler
整合至 AI Agent Skill Store
"""
import httpx
import os


async def get_market_data(symbol: str) -> str:
    symbol = symbol.upper().replace("/", "").replace("-", "")
    if not symbol.endswith("USDT"):
        symbol += "USDT"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}")
            d = r.json()
            price = float(d["lastPrice"])
            change = float(d["priceChangePercent"])
            vol = float(d["quoteVolume"])
            high = float(d["highPrice"])
            low = float(d["lowPrice"])
            emoji = "🟢" if change > 0 else "🔴"
            return (
                f"{emoji} {symbol}\n"
                f"現價:  {price:,.4f} USDT\n"
                f"漲跌:  {change:+.2f}%\n"
                f"最高:  {high:,.4f}\n"
                f"最低:  {low:,.4f}\n"
                f"成交量: {vol:,.0f} USDT"
            )
    except Exception as e:
        return f"無法取得 {symbol} 數據: {e}"


async def analyze_trade_signal(symbol: str, timeframe: str = "1h") -> str:
    symbol = symbol.upper().replace("/", "").replace("-", "")
    if not symbol.endswith("USDT"):
        symbol += "USDT"

    tf_map = {"1h": "1h", "4h": "4h", "1d": "1d", "15m": "15m"}
    interval = tf_map.get(timeframe, "1h")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # 取 K 線
            r = await client.get(
                f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=50"
            )
            klines = r.json()
            closes = [float(k[4]) for k in klines]

            # 簡易 RSI
            def calc_rsi(prices, period=14):
                if len(prices) < period + 1:
                    return 50
                gains, losses = [], []
                for i in range(1, period + 1):
                    diff = prices[-(period + 1 - i)] - prices[-(period + 2 - i)]
                    (gains if diff > 0 else losses).append(abs(diff))
                ag = sum(gains) / period if gains else 0
                al = sum(losses) / period if losses else 1
                return 100 - 100 / (1 + ag / (al + 1e-9))

            rsi = calc_rsi(closes)
            price = closes[-1]
            ema20 = sum(closes[-20:]) / 20
            ema50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ema20

            trend = "上升趨勢" if ema20 > ema50 else "下降趨勢"

            if rsi < 35 and ema20 > ema50:
                signal = "🟢 做多"
                reason = f"RSI超賣({rsi:.1f}) + 上升趨勢"
            elif rsi > 65 and ema20 < ema50:
                signal = "🔴 做空"
                reason = f"RSI超買({rsi:.1f}) + 下降趨勢"
            elif rsi < 40:
                signal = "🟡 考慮做多"
                reason = f"RSI偏低({rsi:.1f})，等待確認"
            elif rsi > 60:
                signal = "🟡 考慮做空"
                reason = f"RSI偏高({rsi:.1f})，等待確認"
            else:
                signal = "⚪ 觀望"
                reason = f"RSI中性({rsi:.1f})，無明確信號"

            return (
                f"📊 {symbol} [{timeframe}] 信號分析\n"
                f"現價: {price:,.4f} USDT\n"
                f"趨勢: {trend}\n"
                f"EMA20: {ema20:,.4f} | EMA50: {ema50:,.4f}\n"
                f"RSI: {rsi:.1f}\n"
                f"信號: {signal}\n"
                f"原因: {reason}"
            )
    except Exception as e:
        return f"分析錯誤 {symbol}: {e}"


async def get_top_movers(limit: int = 5, direction: str = "gainers") -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.binance.com/api/v3/ticker/24hr")
            all_tickers = r.json()

        usdt_pairs = [t for t in all_tickers if t["symbol"].endswith("USDT")]
        reverse = direction == "gainers"
        sorted_pairs = sorted(
            usdt_pairs,
            key=lambda x: float(x["priceChangePercent"]),
            reverse=reverse
        )[:limit]

        lines = [f"{'📈 漲幅榜' if direction == 'gainers' else '📉 跌幅榜'} Top {limit}\n"]
        for i, t in enumerate(sorted_pairs, 1):
            sym = t["symbol"]
            chg = float(t["priceChangePercent"])
            vol = float(t["quoteVolume"]) / 1e6
            lines.append(f"{i}. {sym:<12} {chg:+.2f}%  成交量:{vol:.1f}M")
        return "\n".join(lines)
    except Exception as e:
        return f"取得排行失敗: {e}"
