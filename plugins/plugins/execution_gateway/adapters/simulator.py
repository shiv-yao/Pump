from utils.loader import call
from adapters.base import BaseAdapter


class SimulatorAdapter(BaseAdapter):

    async def place_order(self, asset_id, side, size, price=None, strategy_id=None):
        return await call("simulate_order", {
            "asset_id": asset_id,
            "side": side,
            "price": price,
            "size": size
        })

    async def cancel_order(self, order_id):
        return {"ok": True}

    async def get_balance(self):
        return {"sim_balance": 1000}
