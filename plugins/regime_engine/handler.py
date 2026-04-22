async def get_market_regime(symbol=None, **kwargs):
    symbol = symbol or "BTCUSDT"
    return {
        "regime": "trend",
        "confidence": 0.62,
        "symbol": symbol
    }
