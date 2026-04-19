import os
import time
import json
import hmac
import hashlib
import httpx

# ========= 環境 =========

API_KEY = os.getenv("POLY_API_KEY", "")
API_SECRET = os.getenv("POLY_API_SECRET", "")
PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "")

BASE = "https://clob.polymarket.com"


# ========= 簽名（占位版） =========
# 👉 真實需 EIP-712 或官方 SDK
def sign_request(payload: dict):
    msg = json.dumps(payload, separators=(",", ":"))
    sig = hmac.new(API_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return sig


# ========= header =========

def build_headers(payload):
    ts = str(int(time.time() * 1000))
    sig = sign_request(payload)

    return {
        "Content-Type": "application/json",
        "POLY_API_KEY": API_KEY,
        "POLY_SIGNATURE": sig,
        "POLY_TIMESTAMP": ts,
    }


# ========= 下單核心 =========

async def send_order(market: str, side: str, amount: float):

    payload = {
        "asset_id": market,
        "side": side,        # BUY / SELL
        "size": amount,
        "price": None,       # market order（實務要填）
        "type": "market"
    }

    headers = build_headers(payload)

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{BASE}/orders", json=payload, headers=headers)

    try:
        data = r.json()
    except:
        return {"error": "invalid response", "status": r.status_code}

    return {
        "status": r.status_code,
        "data": data
    }


# ========= 封裝 =========

async def pm_buy(market: str, amount: float):
    return await send_order(market, "BUY", amount)


async def pm_sell(market: str, amount: float):
    return await send_order(market, "SELL", amount)


# ========= 查餘額 =========

async def pm_balance():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BASE}/balance", headers={
            "POLY_API_KEY": API_KEY
        })

    try:
        return r.json()
    except:
        return {"error": "balance fetch failed"}
