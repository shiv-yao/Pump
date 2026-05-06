import asyncio

class BinanceWS:
    async def run(self):
        while True:
            print("Receiving Binance market data...")
            await asyncio.sleep(5)