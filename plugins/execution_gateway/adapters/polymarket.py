from utils.loader import call
from adapters.base import BaseAdapter


class PolymarketAdapter(BaseAdapter):

    async def place_order(self, asset_id, side, size, price=None, strategy_id=None):
        return await call("pm_limit", {
            "asset_id": asset_id,
            "side": side,
            "price": price,
            "size": size,
            "ioc": False
        })

    async def cancel_order(self, order_id):
        return await call("pm_cancel", {"order_id": order_id})

    async def get_balance(self):
        return await call("pm_balance", {})
