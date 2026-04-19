import os
import httpx
import time

BASE = os.getenv("POLYMARKET_API", "").rstrip("/")
API_KEY = os.getenv("POLYMARKET_API_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


def _check():
    if not BASE:
        return {"error": "POLYMARKET_API not set"}
    if not API_KEY:
        return {"error": "POLYMARKET_API_KEY not set"}
    return None


# ========= 下單 =========
async def pm_limit(asset_id, side, price, size, ioc=False):
    err = _check()
    if err:
        return err

    payload = {
        "asset_id": str(asset_id),
        "side": side,
        "price": float(price),
        "size": float(size),
        "type": "IOC" if ioc else "LIMIT"
    }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(f"{BASE}/order", json=payload, headers=HEADERS)

        if r.status_code != 200:
            return {"error": f"order failed {r.status_code}", "text": r.text}

        data = r.json()

        return {
            "order_id": data.get("id"),
            "status": data.get("status", "submitted")
        }

    except Exception as e:
        return {"error": str(e)}


# ========= 查單 =========
async def pm_get_order(order_id):
    err = _check()
    if err:
        return err

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{BASE}/order/{order_id}", headers=HEADERS)

        if r.status_code != 200:
            return {"error": f"get_order {r.status_code}"}

        return {"order": r.json()}

    except Exception as e:
        return {"error": str(e)}


# ========= 取消 =========
async def pm_cancel(order_id):
    err = _check()
    if err:
        return err

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(f"{BASE}/cancel", json={"order_id": order_id}, headers=HEADERS)

        if r.status_code != 200:
            return {"error": f"cancel failed {r.status_code}"}

        return {"status": "cancelled"}

    except Exception as e:
        return {"error": str(e)}


# ========= 成交 =========
async def pm_get_fills(limit=20):
    err = _check()
    if err:
        return err

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{BASE}/fills?limit={limit}", headers=HEADERS)

        if r.status_code != 200:
            return {"error": f"fills failed {r.status_code}"}

        return {"fills": r.json()}

    except Exception as e:
        return {"error": str(e)}


# ========= 餘額 =========
async def pm_balance():
    err = _check()
    if err:
        return err

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{BASE}/balance", headers=HEADERS)

        if r.status_code != 200:
            return {"error": f"balance failed {r.status_code}"}

        return r.json()

    except Exception as e:
        return {"error": str(e)}
