import os
import httpx

BASE = os.getenv("POLYMARKET_API", "")
KEY = os.getenv("POLYMARKET_KEY", "")

HEADERS = {"Authorization": f"Bearer {KEY}"}


async def pm_balance():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BASE}/balance", headers=HEADERS)
        return r.json()


async def pm_positions():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BASE}/positions", headers=HEADERS)
        return r.json()


async def pm_buy(market: str, amount: float):
    payload = {"market": market, "amount": amount, "side": "buy"}
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/order", json=payload, headers=HEADERS)
        return r.json()


async def pm_sell(market: str, amount: float):
    payload = {"market": market, "amount": amount, "side": "sell"}
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/order", json=payload, headers=HEADERS)
        return r.json()
