import asyncio
import random
from datetime import datetime, timezone


class BinanceWS:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self._price = 100000.0

    async def next_tick(self) -> dict:
        await asyncio.sleep(0.2)
        drift = random.uniform(-0.003, 0.003)
        self._price *= 1 + drift
        return {
            "symbol": self.symbol,
            "price": round(self._price, 2),
            "change_pct": round(drift * 100, 4),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
