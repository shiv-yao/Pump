import httpx

from app.execution_gateway.config import (
    TRADING_API_BASE,
    POLYMARKET_API_KEY,
    GATEWAY_TIMEOUT,
)


def _headers():
    headers = {
        "Content-Type": "application/json",
    }
    if POLYMARKET_API_KEY:
        headers["Authorization"] = f"Bearer {POLYMARKET_API_KEY}"
    return headers


async def place_order(payload: dict):
    if not TRADING_API_BASE:
        return {"error": "TRADING_API_BASE not set"}

    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        r = await client.post(
            f"{TRADING_API_BASE}/order",
            json=payload,
            headers=_headers(),
        )

    try:
        data = r.json()
    except Exception:
        return {"error": "invalid response", "status_code": r.status_code, "text": r.text}

    if r.status_code >= 400:
        return {"error": "order failed", "status_code": r.status_code, "data": data}

    return data


async def get_order(order_id: str):
    if not TRADING_API_BASE:
        return {"error": "TRADING_API_BASE not set"}

    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        r = await client.get(
            f"{TRADING_API_BASE}/order/{order_id}",
            headers=_headers(),
        )

    try:
        data = r.json()
    except Exception:
        return {"error": "invalid response", "status_code": r.status_code, "text": r.text}

    if r.status_code >= 400:
        return {"error": "get_order failed", "status_code": r.status_code, "data": data}

    return data


async def cancel_order(order_id: str):
    if not TRADING_API_BASE:
        return {"error": "TRADING_API_BASE not set"}

    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        r = await client.post(
            f"{TRADING_API_BASE}/cancel/{order_id}",
            headers=_headers(),
        )

    try:
        data = r.json()
    except Exception:
        return {"error": "invalid response", "status_code": r.status_code, "text": r.text}

    if r.status_code >= 400:
        return {"error": "cancel failed", "status_code": r.status_code, "data": data}

    return data


async def get_fills(limit: int = 20):
    if not TRADING_API_BASE:
        return {"error": "TRADING_API_BASE not set"}

    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        r = await client.get(
            f"{TRADING_API_BASE}/fills",
            params={"limit": limit},
            headers=_headers(),
        )

    try:
        data = r.json()
    except Exception:
        return {"error": "invalid response", "status_code": r.status_code, "text": r.text}

    if r.status_code >= 400:
        return {"error": "fills failed", "status_code": r.status_code, "data": data}

    return data


async def get_balance():
    if not TRADING_API_BASE:
        return {"error": "TRADING_API_BASE not set"}

    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        r = await client.get(
            f"{TRADING_API_BASE}/balance",
            headers=_headers(),
        )

    try:
        data = r.json()
    except Exception:
        return {"error": "invalid response", "status_code": r.status_code, "text": r.text}

    if r.status_code >= 400:
        return {"error": "balance failed", "status_code": r.status_code, "data": data}

    return data
