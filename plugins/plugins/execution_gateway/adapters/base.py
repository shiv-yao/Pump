class BaseAdapter:
    async def place_order(self, **kwargs):
        raise NotImplementedError

    async def cancel_order(self, order_id):
        raise NotImplementedError

    async def get_balance(self):
        return {}
