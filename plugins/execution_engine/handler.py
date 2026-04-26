import os
import httpx

TRADING_API = os.getenv("TRADING_API_BASE", "")

async def execute_trade(side: str, symbol: str, amount: float):
    if not TRADING_API:
        return "❌ TRADING_API_BASE 未設定"

    payload = {
        "symbol": symbol,
        "side": side,
        "amount": amount
    }

    async with httpx.AsyncClient() as c:
        r = await c.post(f"{TRADING_API}/trade", json=payload)

    return r.json()
