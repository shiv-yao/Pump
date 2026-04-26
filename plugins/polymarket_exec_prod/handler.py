from app.execution_gateway.router import (
    route_place_order,
    route_get_order,
    route_cancel_order,
    route_get_fills,
    route_get_balance,
)


async def pm_limit(asset_id, side, price, size, ioc=False):
    payload = {
        "asset_id": str(asset_id),
        "side": str(side),
        "price": float(price),
        "size": float(size),
        "type": "IOC" if ioc else "LIMIT",
    }

    result = await route_place_order(payload)

    if isinstance(result, dict):
        return {
            "order_id": result.get("id") or result.get("order_id"),
            "status": result.get("status", "submitted"),
            "raw": result,
        }

    return {"error": "invalid route_place_order result"}


async def pm_cancel(order_id):
    result = await route_cancel_order(str(order_id))
    return result


async def pm_get_order(order_id):
    result = await route_get_order(str(order_id))
    if isinstance(result, dict):
        return {"order": result}
    return {"error": "invalid route_get_order result"}


async def pm_get_fills(limit=20):
    result = await route_get_fills(int(limit))
    if isinstance(result, dict) and "fills" in result:
        return result
    if isinstance(result, list):
        return {"fills": result}
    return {"fills": [], "raw": result}


async def pm_balance():
    return await route_get_balance()
