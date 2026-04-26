import asyncio

from app.execution_gateway.config import GATEWAY_RETRY
from app.execution_gateway.logger import log
from app.execution_gateway.polymarket import (
    place_order,
    get_order,
    cancel_order,
    get_fills,
    get_balance,
)


async def _retry(fn, *args, **kwargs):
    last_error = None

    for attempt in range(GATEWAY_RETRY + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_error = str(e)
            log.error(f"gateway retry {attempt} failed: {e}")
            await asyncio.sleep(0.1)

    return {"error": f"all retries failed: {last_error}"}


async def route_place_order(payload: dict):
    return await _retry(place_order, payload)


async def route_get_order(order_id: str):
    return await _retry(get_order, order_id)


async def route_cancel_order(order_id: str):
    return await _retry(cancel_order, order_id)


async def route_get_fills(limit: int = 20):
    return await _retry(get_fills, limit)


async def route_get_balance():
    return await _retry(get_balance)
